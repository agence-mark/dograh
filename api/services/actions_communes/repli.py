"""[.mark] Chantier Partie 1, lot 6 : le repli A (B12 § 2, décision 1 ; D62 : repli A seul, aucun ``tool_choice``, B13 point 1 réfuté).

- ``refus_de_la_fiche(retour)`` : le retour refuse-t-il la FICHE (sa forme, ou une valeur qui ne vient pas d'elle) ? Lecture de la liste fermée du
  lot 2 (``enveloppe.REFUS_DE_LA_FICHE``), jamais du sens. Après un refus de la fiche, une phrase du modèle sans outil n'est jamais dite. Après un
  refus du métier (hors zone, rupture, minimum…), la phrase du modèle qui dit la raison reste dite.
- ``consigne_de_relance(p, fiche, etat, connecteur)`` (lot 7b-C5, décision d'Evan 25/11 8 h 45) : au bout des passes, sans phrase dicible, le code ne compose aucune phrase : il
  RELANCE le modèle une fois par tour avec le fait (JSON : les refus du tour, puis la question en attente ou ce qui manque). Si la relance échoue : le fait accompli que le code a déjà
  dit, sinon la phrase réglée de l'agent.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
import json
from typing import Any

from api.services.actions_communes.enveloppe import QUESTIONS_DITES_PAR_LE_CODE, REFUS_DE_LA_FICHE

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


# Point de contrôle du lot 7 (conv2, tour 1) : les FAITS du fait bloquant de la fiche de CE tour, posés par la porte du connecteur (hors zone : la raison et l'autre mode), ``{"tour": n, "faits": {métier: [...]}}``
# dans la fiche de l'appel (un groupe par métier : chaque porte ne retire que le sien). C5 : le texte de secours n'y est plus, la relance du modèle lit les faits.
CLE_FAIT_BLOQUANT = "faits_du_fait_bloquant"
CLE_DU_TOUR = "tour_de_la_personne"  # la même clé que la porte (contrat.CLE_DU_TOUR)


def poser_le_fait_bloquant(fiche: Any, tour: Any, de: str, faits: list[Any] | None = None) -> None:
    """La porte du métier ``de`` range les FAITS de son fait bloquant, les refus tels que le modèle les reçoit (``faits`` vide ou ``None`` : les siens sont retirés, jamais ceux d'un
    autre métier ; la case d'un autre tour est jetée). La relance du modèle (``consigne_de_relance``) les lit : jamais une phrase de secours."""
    if not isinstance(fiche, dict):
        return
    case = fiche.get(CLE_FAIT_BLOQUANT)
    valide = isinstance(case, dict)
    rangs = dict(case["faits"]) if valide and isinstance(case.get("faits"), dict) else {}
    tour_de_la_case = case.get("tour") if valide else None
    if tour is not None and tour_de_la_case != tour:
        rangs = {}
    rangs.pop(de, None)
    if faits:
        rangs[de] = list(faits)
        tour_de_la_case = tour
    if rangs:
        fiche[CLE_FAIT_BLOQUANT] = {"tour": tour_de_la_case, "faits": rangs}
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


# C5 (décision d'Evan 25/11 8 h 45) : le code ne compose plus de phrase vers la voix. Le modèle muet sur un refus, ou qui oublie la question due, est relancé UNE fois par tour de la personne avec le fait.
CONSIGNE_DE_RELANCE = (
    "- Ta réponse précédente n'a pas dit ce qui est dû à la personne : elle n'a pas été dite. Réponds-lui avec tes mots d'après ces faits (JSON, ne les recopie pas) : "
    "``a_dire`` est ce que tu lui dis d'abord, ``puis`` ce que tu lui demandes ensuite, en une seule question : "
)
# C6 (décision d'Evan 25/11 9 h 30) : après certaines phrases du modèle (la relecture), le CODE dit la phrase du total et la question. Une phrase du modèle qui les dit déjà est relancée UNE fois, par la même relance du fait que
# ci-dessus (``etat.relance_du_fait``) : un seul mécanisme.
CONSIGNE_DE_CE_QUE_LE_CODE_DIT = (
    "- Ta réponse précédente disait ce que le code dit lui-même juste après ta phrase (le total, ou la question) : elle n'a pas été dite. Redis-la sans prix et sans question : "
    "ta phrase seule, le code ajoute le reste."
)


CONSIGNE_DES_CHIFFRES_EXIGES = (
    "- Ta réponse précédente n'a pas été dite : elle ne disait pas ces valeurs du fait accompli. Redis-la avec ces valeurs, telles que les faits les donnent, sans prix et sans question "
    "(le code dit la suite juste après ta phrase) : "
)


def consigne_des_chiffres_exiges(etat: Any) -> str | None:
    """C6 n° 5 : la consigne qui relance le modèle quand sa phrase ne dit pas les valeurs que le code exige du fait accompli (``etat.exiges``, l'heure de la commande enregistrée) ;
    ``None`` quand la relance du tour est déjà faite (même compteur que les autres relances, C5). Les valeurs sont du JSON, jamais de la prose. L'appelant garde l'état."""
    if etat.relance_du_fait:
        return None
    etat.relance_du_fait = True
    etat.rattrapage_a_joue = etat.rattrapage_refus_joue = True
    return CONSIGNE_DES_CHIFFRES_EXIGES + json.dumps(etat.exiges or {}, ensure_ascii=False, default=str)


def consigne_de_ce_que_le_code_dit(etat: Any) -> str | None:
    """La consigne qui relance le modèle quand sa phrase dit ce que le code dit après elle ; ``None`` quand la relance du tour est déjà faite. L'appelant garde l'état."""
    if etat.relance_du_fait:
        return None
    etat.relance_du_fait = True
    etat.rattrapage_a_joue = etat.rattrapage_refus_joue = True
    return CONSIGNE_DE_CE_QUE_LE_CODE_DIT


CLES_DE_L_OBJET_D_UNE_QUESTION = ("article_en_question", "article_propose", "heure_dite", "choix", "candidats_dits")


def _libelles(candidats: Any) -> list[str]:
    return [str(c["libelle"]) for c in candidats or [] if isinstance(c, dict) and c.get("libelle")]


def question_pour_la_relance(q: dict[str, Any]) -> dict[str, Any]:
    """La question en attente donnée au modèle en faits : son numéro, son type, son objet (l'article, les candidats, les choix) ; jamais le texte de secours du module,
    sauf pour les questions que le code dit lui-même (``QUESTIONS_DITES_PAR_LE_CODE``, jusqu'à C6)."""
    sortie: dict[str, Any] = {"id": q.get("id"), "type": q.get("type")}
    for cle in CLES_DE_L_OBJET_D_UNE_QUESTION:
        if q.get(cle):
            sortie[cle] = q[cle]
    candidats = _libelles(q.get("candidats_par_identifiant"))
    if candidats:
        sortie["candidats"] = candidats
    if q.get("type") in QUESTIONS_DITES_PAR_LE_CODE and q.get("texte"):
        sortie["texte"] = q["texte"]
    return sortie


def _valeur_du_manque(p: dict[str, Any], connecteur: Any, fiche: Any) -> str | None:
    """La valeur fermée de ce qui manque ensuite (``Manque`` pour la commande, la liste de la réservation) : celle que déclare le connecteur de l'étape, sinon celle de la commande."""
    lire = getattr(connecteur, "valeur_du_manque", None)
    if callable(lire):
        return lire(p, fiche if isinstance(fiche, dict) else {})
    from api.services.commande.phrases_du_manque import valeur_du_manque

    return valeur_du_manque(p)


def consigne_de_relance(p: dict[str, Any] | None, fiche: Any, etat: Any, connecteur: Any = None) -> str | None:
    """La consigne qui relance le modèle avec le fait, une fois par tour de la personne (``etat.relance_du_fait``) : ``None`` au deuxième appel du tour, ou sans rien à dire.
    Les faits sont du JSON (``json.dumps``), jamais de la prose : ``a_dire`` = les refus du tour tels que le modèle les reçoit ; ``puis`` = la question en attente (son objet), sinon
    ce qui manque (valeur fermée). Jamais ``r.suggestion``, jamais ``q.texte`` d'une question que le modèle dit, jamais une phrase du catalogue du manque. L'appelant garde l'état."""
    if etat.relance_du_fait:
        return None
    faits: dict[str, Any] = {}
    a_dire = faits_du_fait_bloquant(fiche)
    if a_dire:
        faits["a_dire"] = a_dire
    q = CONV.question_de(p) if isinstance(p, dict) else None
    manque = None if q is not None or not isinstance(p, dict) else _valeur_du_manque(p, connecteur, fiche)
    if q is not None:
        faits["puis"] = {"question": question_pour_la_relance(q)}
    elif manque:
        faits["puis"] = {"manque": str(manque)}
    if not faits:
        return None
    etat.relance_du_fait = True
    etat.rattrapage_a_joue = etat.rattrapage_refus_joue = True  # la relance du fait EST le rattrapage de ce tour : sa réponse n'est pas retenue une seconde fois pour la même raison
    return CONSIGNE_DE_RELANCE + json.dumps(faits, ensure_ascii=False, default=str)
