"""[.mark] Lot 7a : la table de la parole, une ligne de test par ligne de table (``(Du, phrase) -> mode``). Chaque ligne se lit sur ce qui est dû et sur la forme de la
phrase, jamais sur ses mots. Les exemples de phrases vivent ici, jamais dans le code."""

from __future__ import annotations

import pytest

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import table_de_parole as T
from api.services.actions_communes import conversation as CONV
from api.services.actions_communes.du import CLE_FAITS_A_DIRE, RIEN_CHANGE
from api.services.actions_communes.parole import A_DIRE_SEUL, MANQUE, QUESTION_DEJA_DONNEE, SECOND_PASSAGE, EtatDuTour

QUESTION_NEE = {CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "variante", "nee_au_tour": 3, "texte": "Quelle taille ?"}}}
RETOUR_QUESTION = {"question": {"id": "Q-1", "type": "variante", "texte": "Quelle taille ?"}}


def _joue(retour: dict, phrase: str = "Très bien.", textes: dict | None = None, p: dict | None = None, **etat):
    e = EtatDuTour(tour=3, **{k: v for k, v in etat.items() if k != "apres_refus"})
    if etat.get("apres_refus"):  # ligne 23 du lot 7a : « après un refus » se lit au journal du dit, plus sur un drapeau de l'état
        p = p if p is not None else {}
        J.noter_dans_le_tour(p, J.REFUS, 3)
    entrees = T.entrees_du_retour(retour, phrase, e, [], p, textes or {}, None, None)
    return T.ligne_qui_decide(entrees), T.decider(entrees), e


CAS = [
    ("texte du code (exception § 2)", {}, "Oui.", {"avant": "Je vous relis la commande."}, None, {}, A_DIRE_SEUL),
    ("maximum atteint ou doute né dans le tour", {"resultats": [{"statut_du_module": "MAXIMUM_ATTEINT"}]}, "Oui.", {"prefixe": "Pas plus."}, None, {}, A_DIRE_SEUL),
    ("refus", {}, "Oui.", {}, None, {"apres_refus": True}, SECOND_PASSAGE),
    ("faits à dire sur une fiche vide", {RIEN_CHANGE: True, CLE_FAITS_A_DIRE: ["x"]}, "Oui.", {}, None, {}, SECOND_PASSAGE),
    ("rien n'a changé", {RIEN_CHANGE: True}, "Oui.", {}, {"lignes": [{}]}, {}, SECOND_PASSAGE),
    ("fait bloquant", {"statut": "PARTIEL"}, "Oui.", {}, None, {}, SECOND_PASSAGE),
    ("faits à dire", {CLE_FAITS_A_DIRE: ["x"]}, "Oui.", {}, None, {}, SECOND_PASSAGE),
    ("question née ou prix à dire", RETOUR_QUESTION, "Oui.", {}, QUESTION_NEE, {}, SECOND_PASSAGE),
    ("règle chiffrée qui bloque", {}, "Oui.", {"prefixe": "Règle."}, None, {}, SECOND_PASSAGE),
    ("ligne retirée", {"cases_executees": ["retirer_article"]}, "Oui.", {}, None, {}, SECOND_PASSAGE),
    ("formule ajoutée", {"resultats": [{"operation": "ajouter", "faits": {"composition": ["x"]}}]}, "Oui.", {}, None, {}, SECOND_PASSAGE),
    ("phrase vide", {}, "", {}, None, {}, SECOND_PASSAGE),
    ("phrase qui porte un chiffre", {}, "Cela fait 12 euros.", {}, None, {}, SECOND_PASSAGE),
    ("phrase dite", {}, "Très bien.", {}, None, {}, A_DIRE_SEUL),
]


@pytest.mark.parametrize("nom, retour, phrase, textes, p, etat, mode", CAS, ids=[c[0] for c in CAS])
def test_chaque_ligne_de_la_table_decide_comme_elle_le_dit(nom, retour, phrase, textes, p, etat, mode):
    ligne, decision, _ = _joue(retour, phrase, textes, p, **etat)
    assert (ligne, decision.mode) == (nom, mode), (ligne, decision)


def test_toutes_les_lignes_de_la_table_sont_jouees_par_un_cas():
    assert {c[0] for c in CAS} == {nom for nom, _, _ in T.LIGNES}


def test_ce_qui_manque_est_du_quand_la_phrase_ne_pose_pas_de_question():
    _, d, _ = _joue({"texte_a_dire": "Qu'est-ce que je vous mets ?"}, "Très bien.")
    assert (d.mode, d.motif) == (SECOND_PASSAGE, MANQUE)
    _, d, _ = _joue({"texte_a_dire": "Qu'est-ce que je vous mets ?"}, "Très bien. Autre chose ?")
    assert d.mode == A_DIRE_SEUL


def test_une_fiche_vide_est_retenue_une_fois_puis_dite_avec_la_question_en_attente():
    p = {"lignes": [{}], **QUESTION_NEE}
    _, premiere, e = _joue({RIEN_CHANGE: True}, "D'accord.", p=p)
    assert premiere.motif == RIEN_CHANGE and e.rattrapage_a_joue
    _, seconde, _ = _joue({RIEN_CHANGE: True}, "D'accord.", p=p, rattrapage_a_joue=True)
    assert seconde.mode == A_DIRE_SEUL and seconde.a_dire.startswith("D'accord.")


def test_la_question_deja_donnee_est_dite_au_passage_suivant():
    _, premiere, e = _joue(RETOUR_QUESTION, "Oui.", p=QUESTION_NEE)
    assert premiere.motif == "question_nouvelle" and e.question_donnee == "Q-1"
    _, seconde, _ = _joue(RETOUR_QUESTION, "Quelle taille vous voulez ?", p=QUESTION_NEE, question_donnee="Q-1")
    assert (seconde.mode, seconde.motif) == (A_DIRE_SEUL, QUESTION_DEJA_DONNEE)


@pytest.mark.parametrize("nom, retour, phrase, textes, p, etat, mode", CAS, ids=[c[0] for c in CAS])
def test_une_ligne_retiree_de_la_table_change_la_decision(monkeypatch, nom, retour, phrase, textes, p, etat, mode):
    """Le mécanisme débranché (R2) : sans sa ligne, la DÉCISION (mode, motif ou phrase dite) change pour son cas. Une ligne dont le retrait ne change rien ne sert à rien."""
    import copy

    _, avec, _ = _joue(copy.deepcopy(retour), phrase, copy.deepcopy(textes), copy.deepcopy(p), **copy.deepcopy(etat))
    reste = tuple(ligne for ligne in T.LIGNES if ligne[0] != nom)
    monkeypatch.setattr(T, "LIGNES", reste + ((("autre", lambda e: True, T._texte),) if nom == "phrase dite" else ()))
    _, sans, _ = _joue(copy.deepcopy(retour), phrase, copy.deepcopy(textes), copy.deepcopy(p), **copy.deepcopy(etat))
    assert (avec.mode, avec.motif, avec.a_dire, avec.prefixe) != (sans.mode, sans.motif, sans.a_dire, sans.prefixe), "la table sans cette ligne décide pareil : la ligne ne sert à rien"


def test_la_table_videe_ne_decide_plus(monkeypatch):
    monkeypatch.setattr(T, "LIGNES", ())
    with pytest.raises(StopIteration):
        _joue({}, "Très bien.")


@pytest.mark.parametrize("phrase", ["Vous voulez autre chose ? Je note.", "D'accord. Autre chose ?", "Quelle taille ? Normale ou grande ?", "C'est noté.", "Très bien, quelle taille ?!"])
def test_une_seule_regle_pour_dire_qu_une_phrase_pose_une_question(phrase):
    """M4 : la table et la reprise de la question en attente lisent la même ponctuation (la fin de la phrase), jamais un « ? » au milieu."""
    from api.services.actions_communes import parole as PAROLE

    p = {CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "variante", "texte": "Quelle taille ?", "repli": "Quelle taille ?"}}}
    reprise = PAROLE.reprise_apres_la_phrase(phrase, EtatDuTour(tour=1), p)
    assert (reprise is None) == PAROLE.pose_une_question(phrase), (phrase, reprise)
