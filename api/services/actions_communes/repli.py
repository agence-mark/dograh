"""[.mark] Chantier Partie 1, lot 6 : le repli A (B12 § 2, décision 1 ; D62 : repli A seul, aucun ``tool_choice``, B13 point 1 réfuté).

- ``refus_de_la_fiche(retour)`` : le retour refuse-t-il la FICHE (sa forme, ou une valeur qui ne vient pas d'elle) ? Lecture de la liste fermée du
  lot 2 (``enveloppe.REFUS_DE_LA_FICHE``), jamais du sens. Après un refus de la fiche, une phrase du modèle sans outil n'est jamais dite. Après un
  refus du métier (hors zone, rupture, minimum…), la phrase du modèle qui dit la raison reste dite.
- ``repli_dit_par_le_code(p)`` : au bout des passes, sans phrase dicible, le code redit, dans cet ordre, la question en attente par sa phrase du code
  (une proposition par sa phrase de B8 ; une étape de menu par ses choix), sinon la phrase de ce qui manque (``phrases_du_manque``), sinon rien (le
  tour est compté faux). Le code ne choisit rien : il redemande.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
import re
from typing import Any

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.enveloppe import REFUS_DE_LA_FICHE

RAPPEL_APRES_REFUS = (
    "- Ta réponse précédente n'avait pas d'appel d'outil après le refus de ta fiche : elle n'a pas été dite, et rien n'est changé."
)


def _raisons(x: Any, sortie: list[str]) -> list[str]:
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "raison" and isinstance(v, str):
                sortie.append(v)
            else:
                _raisons(v, sortie)
    elif isinstance(x, list):
        for v in x:
            _raisons(v, sortie)
    return sortie


def refus_de_la_fiche(retour: Any) -> bool:
    """Vrai si le retour porte une raison rangée « fiche » (``REFUS_DE_LA_FICHE``)."""
    return any(r in REFUS_DE_LA_FICHE for r in _raisons(retour, []))


# Les statuts du module qui NE refusent PAS : une réussite, une lecture, un manque (``INCOMPLETE`` : le numéro, le prénom), une précision à demander (``AMBIGU``, ``CHOIX_OBLIGATOIRE``), un
# enregistrement, le minimum de la zone (dit par le code, son propre fait) et une fermeture planifiable (l'heure est LA question). Tout AUTRE statut du module refuse (C2, lot 19 bis :
# liste d'EXCLUSION, jamais d'inclusion : un refus nouveau d'un module est dit par le code sans qu'il faille y penser ; le plafond des titres-restaurant, un moyen non accepté, une
# remise refusée, ``FERME`` au choix du mode passaient en « FAIT » muet).
STATUTS_QUI_NE_REFUSENT_PAS = frozenset({
    "OK", "RETENU", "LU", "TROUVE", "AMBIGU", "CHOIX_OBLIGATOIRE", "INCOMPLETE", "ENREGISTREE", "TRANSMISE", "DEJA_FAIT", "RIEN_A_CHANGER", "MINIMUM_NON_ATTEINT", "FERME_PLANIFIABLE",
})


def statut_qui_refuse(statut: Any) -> bool:
    """Le statut d'un résultat du module est-il un refus ? Tout statut hors de ``STATUTS_QUI_NE_REFUSENT_PAS``."""
    return isinstance(statut, str) and bool(statut) and statut not in STATUTS_QUI_NE_REFUSENT_PAS


class _StatutsQuiRefusent:
    """``statut in STATUTS_QUI_REFUSENT`` : l'appartenance se lit par exclusion (``statut_qui_refuse``)."""

    def __contains__(self, statut: Any) -> bool:
        return statut_qui_refuse(statut)


STATUTS_QUI_REFUSENT = _StatutsQuiRefusent()


def refuse(retour: Any) -> bool:
    """Le retour refuse-t-il quelque chose : la fiche (``REJETEE``, une liste de refus), ou le métier (un statut du module qui refuse, hors zone,
    rupture, introuvable) ? ``a_faire`` seul n'en est pas un (une proposition née dans ce tour en porte un, la fiche restant FAIT), ni un fait
    bloquant qui ne refuse pas (un manque, le minimum de la zone dit par le code). Égalité à la vraie boucle (L06-41)."""
    if not isinstance(retour, dict):
        return False
    if retour.get("statut") in ("REJETEE", "INTROUVABLE") or retour.get("refus"):
        return True
    bloquant = (retour.get("faits") or {}).get("fait_bloquant") or {}
    return bloquant.get("statut_du_module") in STATUTS_QUI_REFUSENT or any(
        r.get("statut_du_module") in STATUTS_QUI_REFUSENT for r in retour.get("resultats") or [] if isinstance(r, dict))


# Point de contrôle du lot 7 (conv2, tour 1) : la phrase du fait bloquant de la fiche de CE tour, posée par la porte du connecteur (hors zone : la
# raison et l'autre mode), ``{"tour": n, "textes": {métier: "..."}}`` dans la fiche de l'appel (un texte par métier : chaque porte ne retire que le sien). Le repli la dit d'abord : un fait bloquant se dit avant tout.
CLE_FAIT_BLOQUANT = "phrase_du_fait_bloquant"
CLE_DU_TOUR = "tour_de_la_personne"  # la même clé que la porte (contrat.CLE_DU_TOUR)


def poser_le_fait_bloquant(fiche: Any, tour: Any, texte: str | None, de: str, faits: list[Any] | None = None) -> None:
    """La porte du métier ``de`` range la phrase de son fait bloquant (``None`` : le sien est retiré, jamais celui d'un autre métier ; la case d'un autre tour est
    jetée), et à côté d'elle ses ``faits`` : les refus tels que le modèle les reçoit (C5 : la relance du modèle les lit, jamais la phrase). Ce que le journal de ce qui est dit a déjà
    donné en préfixe (la raison) n'y est pas : la porte ne range que ce qui reste à dire."""
    if not isinstance(fiche, dict):
        return
    case = fiche.get(CLE_FAIT_BLOQUANT)
    valide = isinstance(case, dict)
    textes = dict(case["textes"]) if valide and isinstance(case.get("textes"), dict) else {}
    rangs = dict(case["faits"]) if valide and isinstance(case.get("faits"), dict) else {}
    tour_de_la_case = case.get("tour") if valide else None
    if tour is not None and tour_de_la_case != tour:
        textes, rangs = {}, {}
    textes.pop(de, None)
    rangs.pop(de, None)
    if texte and texte.strip():
        textes[de] = texte.strip()
        if faits:
            rangs[de] = list(faits)
        tour_de_la_case = tour
    if textes:
        fiche[CLE_FAIT_BLOQUANT] = {"tour": tour_de_la_case, "textes": textes, "faits": rangs}
    else:
        fiche.pop(CLE_FAIT_BLOQUANT, None)


def faits_du_fait_bloquant(fiche: Any) -> list[Any]:
    """Les faits des faits bloquants posés dans CE tour de la personne (un groupe par métier, dans l'ordre où les portes les ont écrits), à plat ; vide sans fait bloquant."""
    if not isinstance(fiche, dict):
        return []
    f = fiche.get(CLE_FAIT_BLOQUANT)
    if not isinstance(f, dict) or f.get("tour") != fiche.get(CLE_DU_TOUR):
        return []
    return [x for groupe in (f.get("faits") or {}).values() for x in groupe]


def phrase_du_fait_bloquant(fiche: Any) -> str | None:
    """Les phrases des faits bloquants posés dans CE tour de la personne (une par métier, dans l'ordre où les portes les ont écrites), jointes d'une espace, sinon ``None``."""
    if not isinstance(fiche, dict):
        return None
    f = fiche.get(CLE_FAIT_BLOQUANT)
    if not isinstance(f, dict) or f.get("tour") != fiche.get(CLE_DU_TOUR):
        return None
    texte = " ".join(str(t).strip() for t in (f.get("textes") or {}).values() if str(t).strip())
    return texte or None


def repli_dit_par_le_code(p: dict[str, Any] | None, texte_du_manque: Any = None, fiche: Any = None) -> str | None:
    """La phrase que le code dit quand le modèle n'a rien de dicible au bout des passes (``appel_b12.repli_dit_par_le_code``). Un fait bloquant de ce
    tour se dit d'abord (règle du lot 6 : la phrase du modèle est jetée sur un fait bloquant, qui se dit en premier) ; s'il propose déjà quelque chose
    (une question), la question en attente reste posée sans être redite (une question à la fois), sinon elle suit."""
    bloquant = phrase_du_fait_bloquant(fiche)
    suite = _repli_sans_le_fait_bloquant(p, texte_du_manque, fiche)
    if bloquant is None:
        return suite
    if bloquant.endswith("?") or not suite:
        return bloquant
    return f"{bloquant} {suite}"


def _repli_sans_le_fait_bloquant(p: dict[str, Any] | None, texte_du_manque: Any = None, fiche: Any = None) -> str | None:
    if not isinstance(p, dict):
        return None
    suite = _question_ou_manque(p, texte_du_manque, fiche)
    if suite:
        return suite
    # B2 (M3, règle 3 ; C5, DF5) : rien n'attend et rien ne manque parce qu'une action est faite : le repli redit le fait accompli ; « je n'ai pas
    # bien saisi » ne reste que pour un tour où rien ne s'est fait
    return J.fait_accompli(p)


def _question_ou_manque(p: dict[str, Any], texte_du_manque: Any = None, fiche: Any = None) -> str | None:
    q = CONV.question_de(p)
    if isinstance(q, dict):
        if q.get("type") == "proposition":
            return q.get("repli") or None
        texte = str(q.get("texte") or "").strip()
        if q.get("type") == "etape" and texte:
            return re.sub(r", ligne \d+ :", " :", texte).rstrip(" .?") + " ?"  # la question finit déjà par « ? » (lot 11 : « ? ? »)
        return texte or None
    if callable(texte_du_manque):  # lot 7 : le connecteur de l'étape dit ce qui manque (la réservation)
        return texte_du_manque(p, fiche if isinstance(fiche, dict) else {})
    from api.services.commande.phrases_du_manque import texte_a_dire

    return texte_a_dire(p)
