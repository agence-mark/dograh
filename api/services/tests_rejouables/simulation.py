"""[.mark] Lot H (correctif de clôture, 29/10) : au rejeu d'un test, les outils sortants sont SIMULÉS.

Rejouer un test, c'est faire parler le vrai modèle sur la copie d'un agent. Si le modèle appelle un outil qui écrit ou
qui envoie (SMS, mail, réservation, annulation, transfert), l'appel NE PART PAS : l'outil est noté (nom, arguments,
catégorie) dans ``gathered_context["outils_simules"]`` du run d'essai, et le modèle reçoit un résultat neutre de
réussite pour que la conversation continue. Le critère « outil appelé avec ses arguments » se lit sur l'appel du
modèle (l'événement ``tool_call_started``), jamais sur l'exécution : il marche donc toujours.

Quels outils : ce que le code sait déjà, jamais un nom de métier.

- la catégorie de l'outil : appel HTTP, serveur MCP, connecteur, transfert d'appel ;
- les actions qui remplissent (``rempli_par_outil``) ou défont (``annule_par_outil``) un champ de la fiche
  (``verite_des_actions.outils_d_ecriture`` / ``outils_d_annulation``), quelle que soit leur catégorie.

Le plus prudent a été tranché pour les outils de LECTURE (une recherche) : ils sont simulés aussi (un appel HTTP ou un
connecteur peut écrire sans que rien ne le dise ; une recherche simulée ne rend aucune donnée, jamais une donnée
inventée). Ils restent distingués dans la note (``ecriture: false``).

Ne sont PAS simulés : la calculatrice (pure), la fin d'appel et la passation à un autre agent de l'appel (internes,
sans effet hors de l'appel : le test d'un passage doit les voir marcher), et les outils du moteur lui-même
(``noter_information``, ``laisser_la_parole``, ``signaler_un_probleme``, travail de fond).

Hors rejeu : ``simuler_si_rejeu`` rend le gestionnaire tel quel (aucun enrobage). ⛔ Zéro vocabulaire métier.
⛔ Ne lève jamais dans le chemin de l'appel.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from loguru import logger

from api.enums import ToolCategory

# Posées dans la fiche du run d'essai par ``rejeu.py`` (et nulle part ailleurs) : un vrai appel n'a jamais cette clé.
CLE_REJEU = "rejeu_sortants_simules"
CLE_NOTES = "outils_simules"
MAX_NOTES_PAR_ESSAI = 50
LONGUEUR_MAX_DES_ARGUMENTS = 2000

CATEGORIES_SORTANTES = frozenset(
    {
        ToolCategory.HTTP_API.value,
        ToolCategory.MCP.value,
        ToolCategory.INTEGRATION.value,
        ToolCategory.TRANSFER_CALL.value,
    }
)

# Le résultat neutre de réussite rendu au modèle : ni donnée inventée, ni mot qui trahirait le rejeu.
RESULTAT_NEUTRE = {"statut": "ok", "message": "Fait."}

Gestionnaire = Callable[[Any], Awaitable[None]]


def en_rejeu(moteur: Any) -> bool:
    """Le run en cours est-il l'essai d'un test rejouable ? Se lit dans la fiche de l'appel. ⛔ Ne lève jamais."""
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        return isinstance(fiche, dict) and fiche.get(CLE_REJEU) is True
    except Exception:  # noqa: BLE001
        return False


def _valeur(categorie: Any) -> str:
    return str(getattr(categorie, "value", categorie) or "")


def est_ecriture(moteur: Any, nom: str) -> bool:
    """Le nom est-il celui d'une action qui remplit ou défait un champ de la fiche ? ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser
        from api.services.workflow.verite_des_actions import outils_d_annulation, outils_d_ecriture

        return _normaliser(nom) in (outils_d_ecriture(moteur) | outils_d_annulation(moteur))
    except Exception:  # noqa: BLE001
        return False


def est_sortant(moteur: Any, categorie: Any, nom: str) -> bool:
    return _valeur(categorie) in CATEGORIES_SORTANTES or est_ecriture(moteur, nom)


def _noter(moteur: Any, nom: str, categorie: Any, arguments: Any) -> None:
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        if not isinstance(fiche, dict):
            return
        from api.services.fiche.traces import CLE_TOUR

        notes = fiche.setdefault(CLE_NOTES, [])
        if not isinstance(notes, list) or len(notes) >= MAX_NOTES_PAR_ESSAI:
            return
        notes.append(
            {
                "nom": nom,
                "categorie": _valeur(categorie) or None,
                "ecriture": est_ecriture(moteur, nom),
                "arguments": _borne(arguments),
                "tour": fiche.get(CLE_TOUR),
            }
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[rejeu] outil simulé non noté : {erreur!r}")


def _borne(arguments: Any) -> Any:
    """Les arguments tels qu'ils sont, ou leur texte coupé s'ils sont énormes (la note reste dans la fiche)."""
    try:
        import json

        texte = json.dumps(arguments, ensure_ascii=False, default=str)
        return arguments if len(texte) <= LONGUEUR_MAX_DES_ARGUMENTS else texte[:LONGUEUR_MAX_DES_ARGUMENTS]
    except Exception:  # noqa: BLE001
        return None


def simuler_si_rejeu(moteur: Any, categorie: Any, nom: str, gestionnaire: Gestionnaire) -> Gestionnaire:
    """Le gestionnaire de l'outil ``nom`` : celui qu'on lui donne, ou, au rejeu d'un outil sortant, un gestionnaire qui
    note l'appel et rend le résultat neutre sans rien exécuter. ⛔ Ne lève jamais."""
    try:
        if not en_rejeu(moteur) or not est_sortant(moteur, categorie, nom):
            return gestionnaire

        async def simule(params: Any) -> None:
            _noter(moteur, nom, categorie, getattr(params, "arguments", None))
            logger.info(f"[rejeu] {nom} simulé : rien n'est parti")
            await params.result_callback(dict(RESULTAT_NEUTRE))

        return simule
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[rejeu] simulation non posée pour {nom} : {erreur!r}")
        return gestionnaire
