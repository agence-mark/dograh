"""[.mark] Lot 7a : preuve que la table de la parole décide comme l'ancienne cascade (``_decision_du_tour`` d'avant 260210e9c), recopiée ici comme référence, SANS le préfixe : lot 7b (Q1), le code ne dit plus rien avant la phrase du modèle (un refus au chiffre
ou au lieu, un maximum atteint, est un fait que le modèle dit ; la cascade de référence a perdu ces deux cas). Lot 7b-C4 (E1 = A, Evan 25/11) : le doute « Vous voulez dire… ? » est rendu au
modèle avec ses candidats ; la cascade de référence a perdu le troisième cas, la question d'ambiguïté dite mot pour mot.

Sur une grille de retours, de phrases, de textes du code, de dossiers et d'états du tour : même mode, même motif, même phrase dite, et mêmes mouvements de
l'état du tour (fiches, rattrapage, retenues, question donnée, prix). Lot 7b-C5 (décision d'Evan 25/11 8 h 45) : la référence ne complète plus la phrase par la question ou le manque, elle relance le modèle une fois. La grille n'a aucune phrase à « ? » au milieu (seule la règle de la question, M4, a changé de forme)."""

from __future__ import annotations

import copy
import itertools

import pytest

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import parole as P
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase, sans_balisage
from api.services.actions_communes.du import BLOQUANTS, CLE_DU, CLES_DES_FAITS_DU_REFUS, CLE_FAITS_A_DIRE, RETRAIT_D_UNE_LIGNE, RIEN_CHANGE
from api.services.actions_communes.parole import A_DIRE_SEUL, SECOND_PASSAGE, Decision, EtatDuTour
from api.services.actions_communes.repli import refuse


def _compose(retour):
    return any(isinstance(r, dict) and r.get("operation") == "ajouter" and isinstance((r.get("faits") or {}).get("composition"), list) for r in retour.get("resultats") or [])


def cascade_d_avant(retour, a_dire, etat, paroles, p, textes, objet_en_cours):
    """L'ancienne cascade, telle qu'elle était, avec les mêmes mouvements de l'état du tour."""
    etat.fiches += 1
    suffixe_avant = etat.suffixe
    etat.suffixe = None
    phrase = sans_balisage(str(a_dire or ""))
    avant = sans_balisage(str(textes.get("avant") or ""))
    q_dossier = CONV.question_de(p) if isinstance(p, dict) else None
    if avant:
        return Decision(A_DIRE_SEUL, a_dire=avant, motif="texte_du_code")
    if refuse(retour):
        return Decision(SECOND_PASSAGE, motif="refus")
    if retour.get(RIEN_CHANGE) and retour.get(CLE_FAITS_A_DIRE):
        etat.fiches -= 1
        return Decision(SECOND_PASSAGE, motif=P.FAITS_A_DIRE)
    question_deja_donnee = bool(
        P.question_nee_dans_ce_tour(p, etat.tour) and (q_dossier or {}).get("id") == etat.question_donnee and etat.question_donnee
        and (not retour.get("prix_dit_par_le_code_apres_ta_phrase") or suffixe_avant) and phrase and not chiffre_dans_la_phrase(phrase, etat.executees, paroles))
    if retour.get(RIEN_CHANGE) and not question_deja_donnee:
        etat.fiches -= 1
        if not etat.rattrapage_a_joue and (objet_en_cours or isinstance(q_dossier, dict)):
            etat.rattrapage_a_joue = True
            etat.retenues.append(P.SANS_OUTIL)
            return Decision(SECOND_PASSAGE, motif=RIEN_CHANGE)
        if not phrase or chiffre_dans_la_phrase(phrase, etat.executees, paroles):
            return Decision(SECOND_PASSAGE, motif="sans_phrase" if not phrase else "chiffre")
        due = not P.pose_une_question(phrase) and (isinstance(q_dossier, dict) or bool((retour.get(CLE_DU) or {}).get("manque")))
        if due and not etat.relance_du_fait:  # lot 7b-C5 (décision d'Evan 25/11 8 h 45) : le modèle repasse une fois au lieu que le code complète sa phrase
            etat.relance_du_fait = True
            etat.suffixe = suffixe_avant
            return Decision(SECOND_PASSAGE, motif=P.MANQUE)
        reprise = None if due or P.pose_une_question(phrase) or not isinstance(p, dict) else J.fait_accompli(p)
        if reprise:
            return Decision(A_DIRE_SEUL, a_dire=f"{phrase} {reprise}", motif=P.REPRISE)
        return Decision(A_DIRE_SEUL, a_dire=phrase, motif="fait")
    if retour.get("statut") in BLOQUANTS or any((retour.get("faits") or {}).get(k) for k in CLES_DES_FAITS_DU_REFUS):
        return Decision(SECOND_PASSAGE, motif="fait_bloquant")
    if retour.get(CLE_FAITS_A_DIRE):
        return Decision(SECOND_PASSAGE, motif=P.FAITS_A_DIRE)
    if P.question_nee_dans_ce_tour(p, etat.tour) or retour.get("prix_dit_par_le_code_apres_ta_phrase"):
        question_id = (q_dossier or {}).get("id")
        if (question_id and question_id == etat.question_donnee and (not retour.get("prix_dit_par_le_code_apres_ta_phrase") or suffixe_avant) and phrase
                and not chiffre_dans_la_phrase(phrase, etat.executees, paroles)):
            if not P.pose_une_question(phrase) and not etat.relance_du_fait:  # lot 7b-C5 : le modèle repasse une fois au lieu que le code complète sa phrase
                etat.relance_du_fait = True
                etat.suffixe = suffixe_avant
                return Decision(SECOND_PASSAGE, motif=P.MANQUE)
            return Decision(A_DIRE_SEUL, a_dire=" ".join(x for x in (phrase, suffixe_avant) if x), motif=P.QUESTION_DEJA_DONNEE)
        etat.question_donnee = question_id
        etat.suffixe = sans_balisage(str(textes.get("suffixe") or "")) or None
        return Decision(SECOND_PASSAGE, motif="question_nouvelle")
    if "retirer_article" in (retour.get("cases_executees") or []):
        return Decision(SECOND_PASSAGE, motif="retrait")
    if _compose(retour):
        return Decision(SECOND_PASSAGE, motif=P.FORMULE_AJOUTEE)
    if not phrase:
        return Decision(SECOND_PASSAGE, motif="sans_phrase")
    if chiffre_dans_la_phrase(phrase, etat.executees, paroles):
        return Decision(SECOND_PASSAGE, motif="chiffre")
    if (retour.get(CLE_DU) or {}).get("manque") and not P.pose_une_question(phrase):
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
    "manque": {CLE_DU: {"manque": "Quelle taille ?"}},
    "prix": {"prix_dit_par_le_code_apres_ta_phrase": True},
    "question": {"question": QUESTION},
    "ambiguite": {"question": {**QUESTION, "type": "ambiguite"}},
    "maximum": {"resultats": [{"statut_du_module": "MAXIMUM_ATTEINT"}]},
    "minimum": {"faits": {"minimum_de_la_commande": {"commune": "X", "minimum": 5000, "manque": 100}}},
    "retrait": {"cases_executees": ["retirer_article"], CLE_DU: {"faits_qui_engagent": [RETRAIT_D_UNE_LIGNE]}},
    "formule": {"resultats": [{"operation": "ajouter", "faits": {"composition": ["x"]}}]},
}
PHRASES = ["", "Très bien.", "Très bien. Autre chose ?", "Cela fait 12 euros."]
TEXTES = [{}, {"avant": "Je vous relis la commande."}, {"suffixe": "Prix : 8 euros."}]
DOSSIERS = ["aucun", "objet", "question_nee"]
ETATS = [{}, {"rattrapage_a_joue": True}, {"question_donnee": "Q-1"}, {"question_donnee": "Q-1", "suffixe": "Prix : 8 euros."}, {"rattrapage_a_joue": True, "relance_du_fait": True}]


def _dossier(nom):
    if nom == "aucun":
        return None
    p = {"lignes": [{}]}
    if nom == "question_nee":
        CONV.poser_question(p, {**QUESTION, "nee_au_tour": 3})
    return p


def _cle(d, e):
    return (d.mode, d.motif, d.a_dire), (e.fiches, e.rattrapage_a_joue, tuple(e.retenues), e.question_donnee, e.suffixe, e.relance_du_fait)


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
