"""[.mark] Agent fiable (Evan, 17/11) : l'état que tiennent les connecteurs de l'étape, dans l'instruction système de chaque requête.

« La conversation est menée par le modèle ; le code apporte la fiabilité. » Un connecteur qui mène quelque chose dans l'appel déclare son ÉTAT
(``Connecteur.etat_pour_le_modele(fiche, appel)`` : quelques lignes de faits, ce qui est pris, ce qui manque ensuite). À chaque requête de
conversation, quand les outils offerts au modèle par cette requête comptent un outil de ce connecteur, le texte est recalculé et rangé en
dernier dans l'instruction système du service, par le même rangement que la fiche (D4, ``fiche_dans_le_systeme.ranger_un_bloc`` : l'API de
composition de Pipecat, toute famille de fournisseurs, aucun message ``system`` au milieu de la conversation, le bloc d'avant remplacé). Le
modèle pose alors lui-même la bonne question, sans appeler un outil pour la découvrir : un seul passage du modèle pour ce tour.

Activation sans case : par la présence d'un outil du connecteur parmi les outils de la requête (l'étape qui le porte). Un agent dont aucune étape
ne porte un tel outil n'a rien de posé : son instruction système est celle d'avant, à l'octet. Le connecteur de chaque outil est retenu quand les
outils de l'étape s'inscrivent (``inscrire_l_outil``, à côté de la case « doit aboutir »).

Appelé par ``pipecat/avant_la_requete.py`` (téléphone et clavier). Aucun mot de métier. ⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

# Posé sur le moteur : le connecteur de chaque outil inscrit, par nom de fonction (normalisé).
ATTRIBUT = "_mark_connecteur_des_fonctions"
# Posé sur le service : le texte du bloc rangé à la dernière requête (retrouvé pour le remplacer).
REPERE = "_mark_bloc_etat_des_connecteurs"


def _normaliser(nom: str) -> str:
    from api.services.workflow.enveloppe_des_actions import _normaliser as normaliser

    return normaliser(nom)


def inscrire_l_outil(moteur: Any, nom_fonction: str, outil: Any) -> None:
    """À l'inscription des outils d'une étape : retient le connecteur de l'outil (``config.connecteur``), ou l'oublie. ⛔ Ne lève jamais."""
    try:
        connecteur = (((getattr(outil, "definition", None) or {}).get("config")) or {}).get("connecteur")
        table = getattr(moteur, ATTRIBUT, None)
        if not isinstance(table, dict):
            table = {}
            setattr(moteur, ATTRIBUT, table)
        nom = _normaliser(nom_fonction)
        if connecteur:
            table[nom] = str(connecteur)
        else:
            table.pop(nom, None)
    except Exception as erreur:  # noqa: BLE001
        logger.debug(f"[etat] outil non inscrit : {erreur!r}")


def _noms_des_outils(outils: Any) -> list[str]:
    if outils is None:
        return []
    if hasattr(outils, "standard_tools"):
        return [str(getattr(t, "name", "")) for t in outils.standard_tools or []]
    if isinstance(outils, list):
        return [str((t.get("function") or {}).get("name") or "") for t in outils if isinstance(t, dict)]
    return []


def connecteurs_de_la_requete(moteur: Any, outils: Any) -> list[str]:
    """Les connecteurs dont un outil est offert par cette requête, dans l'ordre des outils, sans doublon."""
    table = getattr(moteur, ATTRIBUT, None)
    if not isinstance(table, dict) or not table:
        return []
    vus: list[str] = []
    for nom in _noms_des_outils(outils):
        c = table.get(_normaliser(nom)) if nom else None
        if c and c not in vus:
            vus.append(c)
    return vus


ENTETE_DE_L_APPEL = "[État de l'appel, tenu par le code]"


def etat_de_l_appel(fiche: Any) -> str | None:
    """Chantier Partie 1, lot 6 (E25, C4) : l'état de l'appel (une ligne par connecteur qui en déclare une, dans l'ordre du catalogue), montré à
    l'étape qui passe la main : l'accueil sait ce qui est commencé, fini ou annulé, et propose la reprise (textes de l'accueil repris). ⛔ Ne lève
    jamais."""
    try:
        from api.services.integrations.connectors.catalogue import connecteurs

        lignes = []
        for c in connecteurs():
            if c.etat_de_l_appel is None:
                continue
            ligne = c.etat_de_l_appel(fiche if isinstance(fiche, dict) else {})
            if isinstance(ligne, str) and ligne.strip():
                lignes.append(ligne.strip())
        return "\n".join([ENTETE_DE_L_APPEL, *lignes]) if lignes else None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[etat] état de l'appel non calculé : {erreur!r}")
        return None


def texte_de_l_etat(moteur: Any, outils: Any) -> str | None:
    """L'état des connecteurs de la requête qui en déclarent un, ou ``None``. Une requête qui offre ``passer_a`` (l'étape qui passe la main) reçoit
    l'état de l'appel à la place (lot 6). ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.passage_unique import NOM as PASSAGE

        if PASSAGE in _noms_des_outils(outils):
            return etat_de_l_appel(getattr(moteur, "_gathered_context", None))
        noms = connecteurs_de_la_requete(moteur, outils)
        if not noms:
            return None
        from api.services.integrations.connectors.catalogue import connecteur

        fiche = getattr(moteur, "_gathered_context", None)
        appel = getattr(moteur, "_call_context_vars", None)
        textes = []
        for nom in noms:
            c = connecteur(nom)
            if c is None or c.etat_pour_le_modele is None:
                continue
            try:
                t = c.etat_pour_le_modele(fiche if isinstance(fiche, dict) else {}, appel if isinstance(appel, dict) else {})
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[etat] état illisible ({nom}) : {erreur!r}")
                continue
            if isinstance(t, str) and t.strip():
                textes.append(t.strip())
        return "\n\n".join(textes) or None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[etat] état des connecteurs non calculé : {erreur!r}")
        return None


def placer_l_etat(moteur: Any, llm: Any, outils: Any) -> bool:
    """Range (ou retire) l'état des connecteurs de cette requête en fin d'instruction système de ``llm``. Rend ``True`` si un bloc est en place.
    Aucun connecteur à état et aucun bloc d'avant : rien n'est touché. ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.fiche_dans_le_systeme import ranger_un_bloc

        texte = texte_de_l_etat(moteur, outils)
        if texte is None and getattr(llm, REPERE, None) is None:
            return False
        return ranger_un_bloc(llm, REPERE, texte)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[etat] état non rangé : {erreur!r}")
        return False
