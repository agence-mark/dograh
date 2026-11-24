"""[.mark] Lot 7a : preuve que la table de la parole décide comme l'ancienne cascade (``_decision_du_tour`` d'avant 260210e9c), recopiée ici comme référence.

Sur une grille de retours, de phrases, de textes du code, de dossiers et d'états du tour : même mode, même motif, même phrase dite, même préfixe, et mêmes mouvements de
l'état du tour (fiches, rattrapage, retenues, question donnée, prix). La grille n'a aucune phrase à « ? » au milieu (seule la règle de la question, M4, a changé de forme)."""

from __future__ import annotations

import copy
import itertools

import pytest

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as P
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase, sans_balisage
from api.services.actions_communes.du import BLOQUANTS, CLE_DU, CLE_FAITS_A_DIRE, RETRAIT_D_UNE_LIGNE, RIEN_CHANGE
from api.services.actions_communes.parole import A_DIRE_SEUL, SECOND_PASSAGE, Decision, EtatDuTour
from api.services.actions_communes.repli import refuse


def _compose(retour):
    return any(isinstance(r, dict) and r.get("operation") == "ajouter" and isinstance((r.get("faits") or {}).get("composition"), list) for r in retour.get("resultats") or [])


def _remplace(retour, p, tour, prefixe):
    q = retour.get("question") if isinstance(retour.get("question"), dict) else None
    texte_q = sans_balisage(str((q or {}).get("texte") or "")) or None
    maximum = bool(prefixe) and any(isinstance(r, dict) and r.get("statut_du_module") == "MAXIMUM_ATTEINT" for r in retour.get("resultats") or [])
    ambiguite = q is not None and q.get("type") == "ambiguite" and texte_q is not None and P.question_nee_dans_ce_tour(p, tour)
    if maximum:
        return " ".join(x for x in (prefixe, texte_q if P.question_nee_dans_ce_tour(p, tour) else None) if x)
    if ambiguite:
        return " ".join(x for x in (prefixe, texte_q) if x)
    return None


def cascade_d_avant(retour, a_dire, etat, paroles, p, textes, objet_en_cours):
    """L'ancienne cascade, telle qu'elle était, avec les mêmes mouvements de l'état du tour."""
    etat.fiches += 1
    suffixe_avant = etat.suffixe
    etat.suffixe = None
    phrase = sans_balisage(str(a_dire or ""))
    prefixe = sans_balisage(str(textes.get("prefixe") or "")) or None
    avant = sans_balisage(str(textes.get("avant") or ""))
    q_dossier = CONV.question_de(p) if isinstance(p, dict) else None
    if avant:
        return Decision(A_DIRE_SEUL, a_dire=avant, motif="texte_du_code")
    remplace = _remplace(retour, p, etat.tour, prefixe)
    if remplace:
        return Decision(A_DIRE_SEUL, a_dire=remplace, motif="texte_du_code")
    if refuse(retour):
        return Decision(SECOND_PASSAGE, motif="refus", prefixe=prefixe)
    if retour.get(RIEN_CHANGE) and retour.get(CLE_FAITS_A_DIRE):
        etat.fiches -= 1
        return Decision(SECOND_PASSAGE, motif=P.FAITS_A_DIRE, prefixe=prefixe)
    question_deja_donnee = bool(
        P.question_nee_dans_ce_tour(p, etat.tour) and (q_dossier or {}).get("id") == etat.question_donnee and etat.question_donnee
        and (not retour.get("prix_dit_par_le_code_apres_ta_phrase") or suffixe_avant) and not prefixe and phrase and not chiffre_dans_la_phrase(phrase, etat.executees, paroles))
    if retour.get(RIEN_CHANGE) and not question_deja_donnee:
        etat.fiches -= 1
        if not etat.rattrapage_a_joue and (objet_en_cours or isinstance(q_dossier, dict)):
            etat.rattrapage_a_joue = True
            etat.retenues.append(P.SANS_OUTIL)
            return Decision(SECOND_PASSAGE, motif=RIEN_CHANGE, prefixe=prefixe)
        if not phrase or chiffre_dans_la_phrase(phrase, etat.executees, paroles):
            return Decision(SECOND_PASSAGE, motif="sans_phrase" if not phrase else "chiffre", prefixe=prefixe)
        reprise = P.reprise_apres_la_phrase(phrase, etat, p, rien_change=True) or (None if P.pose_une_question(phrase) else sans_balisage(str(retour.get("texte_a_dire") or "")) or None)
        if reprise:
            return Decision(A_DIRE_SEUL, a_dire=f"{phrase} {reprise}", motif=P.REPRISE)
        return Decision(A_DIRE_SEUL, a_dire=phrase, motif="fait")
    if retour.get("statut") in BLOQUANTS or (retour.get("faits") or {}).get("fait_bloquant"):
        return Decision(SECOND_PASSAGE, motif="fait_bloquant", prefixe=prefixe)
    if retour.get(CLE_FAITS_A_DIRE):
        return Decision(SECOND_PASSAGE, motif=P.FAITS_A_DIRE, prefixe=prefixe)
    if P.question_nee_dans_ce_tour(p, etat.tour) or retour.get("prix_dit_par_le_code_apres_ta_phrase"):
        question_id = (q_dossier or {}).get("id")
        if (question_id and question_id == etat.question_donnee and (not retour.get("prix_dit_par_le_code_apres_ta_phrase") or suffixe_avant) and not prefixe and phrase
                and not chiffre_dans_la_phrase(phrase, etat.executees, paroles)):
            if not P.pose_une_question(phrase):
                suite = P.repli_sans_le_fait_bloquant_de(p)
                if suite:
                    return Decision(A_DIRE_SEUL, a_dire=f"{phrase} {suite}", motif=P.QUESTION_DEJA_DONNEE)
            return Decision(A_DIRE_SEUL, a_dire=" ".join(x for x in (phrase, suffixe_avant) if x), motif=P.QUESTION_DEJA_DONNEE)
        etat.question_donnee = question_id
        etat.suffixe = sans_balisage(str(textes.get("suffixe") or "")) or None
        return Decision(SECOND_PASSAGE, motif="question_nouvelle", prefixe=prefixe)
    if prefixe:
        return Decision(SECOND_PASSAGE, motif="fait_bloquant", prefixe=prefixe)
    if "retirer_article" in (retour.get("cases_executees") or []):
        return Decision(SECOND_PASSAGE, motif="retrait")
    if _compose(retour):
        return Decision(SECOND_PASSAGE, motif=P.FORMULE_AJOUTEE)
    if not phrase:
        return Decision(SECOND_PASSAGE, motif="sans_phrase")
    if chiffre_dans_la_phrase(phrase, etat.executees, paroles):
        return Decision(SECOND_PASSAGE, motif="chiffre")
    if retour.get("texte_a_dire") and not P.pose_une_question(phrase):
        return Decision(SECOND_PASSAGE, motif=P.MANQUE)
    return Decision(A_DIRE_SEUL, a_dire=phrase, motif="fait")


QUESTION = {"id": "Q-1", "type": "variante", "texte": "Quelle taille ?"}
RETOURS = {
    "vide": {},
    "refus": {"statut": "REJETEE"},
    "bloquant": {"statut": "PARTIEL"},
    "rien": {RIEN_CHANGE: True},
    "rien_faits": {RIEN_CHANGE: True, CLE_FAITS_A_DIRE: True},
    "faits": {CLE_FAITS_A_DIRE: True},
    "manque": {"texte_a_dire": "Quelle taille ?"},
    "prix": {"prix_dit_par_le_code_apres_ta_phrase": True},
    "question": {"question": QUESTION},
    "ambiguite": {"question": {**QUESTION, "type": "ambiguite"}},
    "maximum": {"resultats": [{"statut_du_module": "MAXIMUM_ATTEINT"}]},
    "retrait": {"cases_executees": ["retirer_article"], CLE_DU: {"faits_qui_engagent": [RETRAIT_D_UNE_LIGNE]}},
    "formule": {"resultats": [{"operation": "ajouter", "faits": {"composition": ["x"]}}]},
}
PHRASES = ["", "Très bien.", "Très bien. Autre chose ?", "Cela fait 12 euros."]
TEXTES = [{}, {"prefixe": "Règle."}, {"avant": "Je vous relis la commande."}, {"suffixe": "Prix : 8 euros."}]
DOSSIERS = ["aucun", "objet", "question_nee"]
ETATS = [{}, {"rattrapage_a_joue": True}, {"question_donnee": "Q-1"}, {"question_donnee": "Q-1", "suffixe": "Prix : 8 euros."}]


def _dossier(nom):
    if nom == "aucun":
        return None
    p = {"lignes": [{}]}
    if nom == "question_nee":
        CONV.poser_question(p, {**QUESTION, "nee_au_tour": 3})
    return p


def _cle(d, e):
    return (d.mode, d.motif, d.a_dire, d.prefixe), (e.fiches, e.rattrapage_a_joue, tuple(e.retenues), e.question_donnee, e.suffixe)


@pytest.mark.parametrize("nom", list(RETOURS))
def test_la_table_decide_comme_l_ancienne_cascade(nom):
    ecarts = []
    for phrase, textes, dossier, etat in itertools.product(PHRASES, TEXTES, DOSSIERS, ETATS):
        retour, objet = RETOURS[nom], None if dossier == "aucun" else True
        e_ancien, e_nouveau = EtatDuTour(tour=3, **copy.deepcopy(etat)), EtatDuTour(tour=3, **copy.deepcopy(etat))
        ancien = cascade_d_avant(copy.deepcopy(retour), phrase, e_ancien, [], _dossier(dossier), copy.deepcopy(textes), objet)
        nouveau = P._decision_du_tour(copy.deepcopy(retour), phrase, e_nouveau, [], _dossier(dossier), None, copy.deepcopy(textes), objet)
        if _cle(ancien, e_ancien) != _cle(nouveau, e_nouveau):
            ecarts.append((phrase, textes, dossier, etat, _cle(ancien, e_ancien), _cle(nouveau, e_nouveau)))
    assert not ecarts, ecarts[:3]
