"""[.mark] Lot 7a, lignes 19 et 20 : la phrase jetée d'un tour (refus ou formule ajoutée) vit au journal de ce qui est dit, sur UNE place, propre au tour ; plus de
``a_dire_jetee``, ``apres_formule`` ni ``_meme_phrase`` dans l'état de la parole. À comportement égal : recopiée au second passage, elle n'est jamais dite."""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import parole as PAROLE
from api.services.workflow import parole_de_la_fiche as PF

PHRASE = "C'est noté, une pizza au caviar."


async def _refusee(essai_de):
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    cases = {"ajouter": [{"article": "pizza au caviar", "quantite": 1}]}
    r = await e.tour("une pizza au caviar", **cases)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": PHRASE, **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE, (d, r)
    return e


async def test_la_phrase_jetee_sur_un_refus_n_est_pas_dite_quand_le_modele_la_recopie(essai_de):
    e = await _refusee(essai_de)
    etat = PAROLE.etat_du_tour(e.fiche_de_l_appel)
    etat.rattrapage_refus_joue = True  # le premier rattrapage après refus est déjà passé : la phrase recopiée est la seconde
    recopiee = PAROLE.phrase_libre_retenue(PHRASE.upper().rstrip("."), etat, objet_en_cours=True, question_en_attente=False, paroles=[], p=e.p)
    assert recopiee == PAROLE.REPLI_A, recopiee  # aux espaces, à la casse et à la ponctuation de fin près
    autre = PAROLE.phrase_libre_retenue("Cette pizza n'existe pas, désolé.", etat, objet_en_cours=True, question_en_attente=False, paroles=[], p=e.p)
    assert autre is None, autre


async def test_la_phrase_jetee_est_au_journal_et_propre_au_tour(essai_de):
    e = await _refusee(essai_de)
    assert J.jetee(e.p, PHRASE, PAROLE.etat_du_tour(e.fiche_de_l_appel).tour, apres_un_refus=True), e.p.get("conversation")
    assert not J.jetee(e.p, PHRASE, "un autre tour", apres_un_refus=True)  # le tour suivant, la même phrase redevient dicible
    assert not hasattr(PAROLE.EtatDuTour(), "a_dire_jetee") and not hasattr(PAROLE.EtatDuTour(), "apres_formule") and not hasattr(PAROLE, "_meme_phrase")
