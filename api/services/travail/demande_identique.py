"""[.mark] fiabilite-de-la-conversation, lot B (B1, B2) : la demande identique au travail de fond.

Cause vérifiée sur les runs 1526, 1813 et 1950 : le fond n'échouait pas, l'agent lui renvoyait **la même demande,
mot pour mot**, dans la même étape (six fois la même recherche, quatre fois la même réservation qui répondait
« Manque : date »).

**B1, la règle commune « demande identique »** (un seul endroit ; le garde-fou de sortie d'impasse, lot A, la
réutilise : ``demandes_deja_faites``) : deux demandes au travail de fond sont identiques si elles sont faites
**dans la même étape** et que **leur texte normalisé** (casse, ponctuation, espaces) est le même. Le bloc
« Valeurs de la fiche de l'appel » que le code ajoute à la demande **n'entre pas** dans la règle (la fiche change
sans que la demande change, run 1950). Une demande qui cite un autre jour ou une autre date a un autre texte :
elle est nouvelle.

**B2, avant de confier** (``verdict_avant_de_confier``, lu par ``TravailDeLAgent.confier``, donc par le modèle ET
par le déclenchement automatique), à partir des traces ``travaux`` de l'appel :

- une demande identique déjà faite avec un **résultat utile** n'est pas relancée : le modèle reçoit tout de suite
  le résultat connu (même idée que V4 pour les écritures). Le résultat connu est périmé dès qu'une écriture ou
  une annulation réussie l'a suivi : l'appelant qui change d'avis (annuler, puis chercher ou réserver de
  nouveau) repart toujours ;
- une demande identique déjà **en échec** (``echec``, ``delai``, ``sans_outil``, ``outil_en_echec``, résultat vide
  ou qui commence par « Manque » / « Échec ») : **un seul nouvel essai** ; au-delà, elle n'est pas lancée et le modèle
  reçoit « déjà essayé, sans succès » ;
- une demande identique encore **en cours** n'est pas relancée.

Aucun mot de métier. ⛔ Ne lève jamais : dans le doute, la demande part comme avant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from loguru import logger

CLE_ETAPE = "etape"
CLE_JOURNAL_A_LA_FIN = "journal"
CLE_REDEMANDES = "redemandes"

# F-3 (Evan, 26/10) : une demande en échec est retentée UNE fois ; la deuxième panne la ferme.
ESSAIS_PERMIS_EN_ECHEC = 2

LANCER = "lancer"
DEJA_CONNU = "deja_connu"
DEJA_ESSAYE = "deja_essaye"
DEJA_EN_COURS = "deja_en_cours"

# Ce que lit le modèle (jamais dit à l'appelant) : générique, aucun métier.
CONSIGNE_DEJA_CONNU = (
    "Cette demande a déjà été faite avec le même texte : voici son résultat, utilise-le sans la renvoyer. "
    "Pour une autre demande (un autre jour, d'autres informations), écris-la autrement."
)
CONSIGNE_DEJA_ESSAYE = (
    "Cette demande a déjà été essayée sans succès, avec le même texte : ne la renvoie pas. Dis à la personne "
    "que tu n'as pas pu le faire, avec la phrase prévue pour ce cas dans ton étape."
)

# Décision d'Evan (26/10) : en position Automatique, c'est le code qui a confié ; le retour de l'outil ne revient donc à
# personne. Le modèle lit ces notices dans la requête du tour (jamais dans l'historique).
NOTICE_AUTOMATIQUE_DEJA_CONNU = (
    "Le travail de fond a déjà fait cette même demande, il ne la relance pas. Son résultat : {resultat} "
    "Utilise-le."
)
NOTICE_AUTOMATIQUE_DEJA_ESSAYE = (
    "Le travail de fond a déjà essayé cette même demande sans succès, il ne la relance pas. Dis à la personne que "
    "tu n'as pas pu le faire, avec la phrase prévue pour ce cas dans ton étape."
)

_MOTS = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Verdict:
    """Ce que B2 décide pour une demande. ``action`` : ``lancer``, ``deja_connu``, ``deja_essaye`` ou
    ``deja_en_cours`` ; ``entree`` : la trace identique qui fonde la décision."""

    action: str = LANCER
    entree: dict | None = None


# ---------------------------------------------------------------------------------------------------------
# B1 : la règle « demande identique »
# ---------------------------------------------------------------------------------------------------------


def texte_de_la_demande(demande: Any) -> str:
    """La demande de l'agent, sans le bloc « Valeurs de la fiche de l'appel » que le code ajoute derrière."""
    from api.services.travail.demande import ENTETE_DES_VALEURS

    texte = str(demande or "")
    return texte.split(ENTETE_DES_VALEURS, 1)[0]


def cle_de_la_demande(demande: Any) -> str:
    """Le texte de la demande normalisé : casse, ponctuation et espaces ne comptent pas."""
    return " ".join(_MOTS.findall(texte_de_la_demande(demande).casefold()))


def identifiant_de_l_etape(noeud: Any, agent: Any = None) -> str | None:
    """Ce qui désigne une étape dans les traces : son identifiant, sinon son nom, précédé de l'agent quand il est
    connu (revue du 26/10, R-1 : les agents d'un groupe, copiés du même squelette, ont les mêmes numéros d'étape ;
    même clé que le garde-fou d'impasse, ``agent:étape``)."""
    for attribut in ("id", "name"):
        valeur = getattr(noeud, attribut, None)
        if isinstance(valeur, (str, int)) and str(valeur):
            agent_id = getattr(agent, "workflow_id", None)
            return f"{agent_id}:{valeur}" if agent_id is not None else str(valeur)
    return None


def demandes_identiques(demande_a: Any, demande_b: Any) -> bool:
    """B1 : le texte de ces deux demandes est-il le même, une fois normalisé ? (L'étape se compare à part :
    ``demandes_deja_faites``.) Deux textes vides ne sont jamais identiques."""
    cle = cle_de_la_demande(demande_a)
    return bool(cle) and cle == cle_de_la_demande(demande_b)


def _traces(moteur: Any) -> list[dict]:
    from api.services.travail.reglages import CLE_TRAVAUX

    fiche = getattr(moteur, "_gathered_context", None)
    traces = fiche.get(CLE_TRAVAUX) if isinstance(fiche, dict) else None
    return [t for t in (traces or []) if isinstance(t, dict)]


def demandes_deja_faites(moteur: Any, demande: Any, etape: Any) -> list[dict]:
    """B1, la lecture partagée avec le lot A : les traces ``travaux`` de l'appel dont la demande est identique à
    ``demande`` (voir la règle en tête) **dans la même étape** (``etape`` : l'identifiant de
    ``identifiant_de_l_etape``). Dans l'ordre où elles ont été faites ; une demande annulée n'a rien fait et n'y
    est pas. ⛔ Ne lève jamais."""
    try:
        from api.services.travail.agent import STATUT_ANNULE
        from api.services.travail.agent import LONGUEUR_MAX_DEMANDE

        cle = cle_de_la_demande(str(demande or "")[:LONGUEUR_MAX_DEMANDE])
        if not cle:
            return []
        return [
            t
            for t in _traces(moteur)
            if t.get("statut") != STATUT_ANNULE
            and t.get(CLE_ETAPE) == etape
            and cle_de_la_demande(t.get("demande")) == cle
        ]
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] demandes identiques illisibles : {erreur!r}")
        return []


# ---------------------------------------------------------------------------------------------------------
# B2 : ce que les traces disent d'une demande identique
# ---------------------------------------------------------------------------------------------------------


def _en_echec(entree: dict) -> bool:
    from api.services.travail.agent import _DEBUTS_HONNETES, STATUT_VIDE, STATUTS_D_ECHEC

    statut = entree.get("statut")
    if statut in STATUTS_D_ECHEC or statut == STATUT_VIDE:
        return True
    resultat = str(entree.get("resultat") or "").strip()
    return not resultat or resultat.casefold().startswith(_DEBUTS_HONNETES)


def _perime(moteur: Any, entree: dict) -> bool:
    """Une écriture ou une annulation réussie a suivi ce travail : son résultat n'est peut-être plus vrai."""
    rang = entree.get(CLE_JOURNAL_A_LA_FIN)
    if not isinstance(rang, int):
        return False
    from api.services.workflow.verite_des_actions import ecriture_ou_annulation_depuis

    return ecriture_ou_annulation_depuis(moteur, rang)


def verdict_avant_de_confier(moteur: Any, demande: Any, etape: Any) -> Verdict:
    """B2 : faut-il lancer cette demande ? Voir la règle en tête. ⛔ Ne lève jamais : ``lancer`` dans le doute."""
    try:
        from api.services.travail.agent import STATUT_EN_COURS

        identiques = demandes_deja_faites(moteur, demande, etape)
        if not identiques:
            return Verdict()
        for entree in identiques:
            if entree.get("statut") == STATUT_EN_COURS:
                return Verdict(DEJA_EN_COURS, entree)
        for entree in reversed(identiques):
            if not _en_echec(entree) and not _perime(moteur, entree):
                return Verdict(DEJA_CONNU, entree)
        echecs = [e for e in identiques if _en_echec(e)]
        if len(echecs) >= ESSAIS_PERMIS_EN_ECHEC:
            return Verdict(DEJA_ESSAYE, echecs[-1])
        return Verdict()
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] demande identique non jugée : {erreur!r}")
        return Verdict()


def retour_du_verdict(verdict: Verdict) -> dict:
    """Ce que l'outil « confier » rend au modèle quand la demande n'est pas relancée. La trace identique
    compte la redemande (``redemandes``)."""
    from api.services.travail.agent import RETOUR_LANCE

    entree = verdict.entree if isinstance(verdict.entree, dict) else {}
    entree[CLE_REDEMANDES] = int(entree.get(CLE_REDEMANDES) or 0) + 1
    if verdict.action == DEJA_EN_COURS:
        return {**RETOUR_LANCE, "deja_en_cours": True}
    if verdict.action == DEJA_CONNU:
        return {
            "statut": DEJA_CONNU,
            "resultat": str(entree.get("resultat") or ""),
            "consigne": CONSIGNE_DEJA_CONNU,
        }
    return {"statut": DEJA_ESSAYE, "consigne": CONSIGNE_DEJA_ESSAYE}


def notice_du_retour(retour: Any) -> str | None:
    """La notice au modèle quand le code a confié lui-même (position Automatique) et que B2 n'a pas relancé :
    résultat connu, ou déjà essayé sans succès. Une demande encore en cours n'en a pas (la ligne du travail en cours
    la dit déjà). ⛔ Ne lève jamais."""
    try:
        if not isinstance(retour, dict):
            return None
        if retour.get("statut") == DEJA_CONNU:
            return NOTICE_AUTOMATIQUE_DEJA_CONNU.format(resultat=str(retour.get("resultat") or "").strip())
        if retour.get("statut") == DEJA_ESSAYE:
            return NOTICE_AUTOMATIQUE_DEJA_ESSAYE
        return None
    except Exception:  # noqa: BLE001
        return None
