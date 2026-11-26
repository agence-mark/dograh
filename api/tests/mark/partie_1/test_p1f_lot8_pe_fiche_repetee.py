"""[.mark] Lot 8, PE-1, Q1/Q2 (c corrigé par Pierre, 26/11) : une fiche qui AJOUTE et qui est identique à celle du tour d'avant n'est ni ignorée ni ajoutée tout de suite.

Le code ne l'applique pas, la refuse en entier (``fiche_identique_au_tour_d_avant``) avec le fait (les articles et quantités lus dans la fiche) ; le MODÈLE demande au client si c'est
un de plus ou le même. Client « Une regina. » ... « Une regina. » / Avant : deux reginas, rien de dit. / Après : une regina, le modèle demande « une deuxième, ou la même ? » ;
« une autre » (même fiche, tour suivant) : deux reginas ; « c'était la même » (fiche vide) : une seule."""

from __future__ import annotations

from collections import Counter

from api.tests.mark.partie_1.aides_de_la_commande import a_emporter, question_posee

REGINA = {"article": "regina", "quantite": 1, "variante": "Normale"}
RAISON = "fiche_identique_au_tour_d_avant"


def _reginas(e) -> int:
    return sum(Counter({l["nom"].casefold(): l["quantite"] for l in e.p["lignes"]}).values())


async def test_la_meme_fiche_au_tour_suivant_n_ajoute_rien_puis_un_autre_ajoute(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une regina", ajouter=[REGINA])
    assert _reginas(e) == 1
    r = await e.tour("je répète", ajouter=[REGINA])
    assert _reginas(e) == 1 and r.get("raison") == RAISON and r.get("fiche_appliquee") is False, r
    assert r["faits"]["articles"] == [{"article": "regina", "quantite": 1}], r  # des faits bruts lus dans la fiche, jamais une phrase
    r = await e.tour("un autre", ajouter=[REGINA])
    assert _reginas(e) == 2 and r.get("raison") != RAISON, r


async def test_c_etait_le_meme_fiche_vide_garde_une_seule(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une regina", ajouter=[REGINA])
    await e.tour("je répète", ajouter=[REGINA])
    await e.tour("c'était la même")
    assert _reginas(e) == 1


async def test_le_scenario_je_repete_deux_pizzas_ne_sont_pas_doublees(essai_de):
    e = await essai_de()
    await a_emporter(e)
    deux = [{"article": "margherita", "quantite": 1, "variante": "Normale"}, REGINA]
    await e.tour("une margherita normale et une regina normale", ajouter=deux)
    avant = e.lignes()
    r = await e.tour("je répète", ajouter=deux)
    assert e.lignes() == avant and r.get("raison") == RAISON, (avant, e.lignes(), r)


async def test_refus_11_la_meme_fiche_avec_une_reponse_differente_n_est_pas_identique(essai_de):
    """Le « même » se lit sur toute la fiche : la même case ``ajouter`` avec une réponse à la proposition posée est une autre fiche, elle s'applique."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une regina", ajouter=[REGINA])
    q = question_posee(e)
    assert q.get("type") == "proposition", q
    r = await e.tour("non merci, et une autre regina", ajouter=[REGINA], reponse={"question_id": q["id"], "sens": "refuse"})
    assert _reginas(e) == 2 and r.get("raison") != RAISON, r


async def test_une_fiche_sans_ajout_identique_n_est_pas_refusee(essai_de):
    """Le cas voisin : une fiche qui ne porte pas ``ajouter`` (le mode redit) n'est pas concernée."""
    e = await essai_de()
    await a_emporter(e)
    r = await e.tour("à emporter", mode_de_retrait="emporter")
    assert r.get("raison") != RAISON, r


async def test_le_modele_qui_a_ecrit_c_est_note_n_est_pas_dit_et_il_est_relance(essai_de):
    """La phrase écrite avant l'exécution (« C'est noté. ») affirmerait un ajout qui n'a pas eu lieu : le refus est un refus DE LA FICHE, la phrase n'est pas dite, le modèle est relancé."""
    from api.services.actions_communes.parole import SECOND_PASSAGE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await essai_de()
    await a_emporter(e)
    await e.tour("une regina", ajouter=[REGINA])
    r = await e.tour("je répète", ajouter=[REGINA])
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est noté.", "ajouter": [REGINA]})
    assert (r.get("raison"), d.a_dire, d.mode) == (RAISON, None, SECOND_PASSAGE), d
