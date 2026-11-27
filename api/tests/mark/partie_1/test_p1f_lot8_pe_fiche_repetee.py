"""[.mark] Lot 8, PE-1, Q1/Q2 (c corrigé par Pierre, 26/11) : une fiche qui AJOUTE et qui est identique à celle du tour d'avant n'est ni ignorée ni ajoutée tout de suite.

Le code ne l'applique pas, la refuse en entier (``fiche_identique_au_tour_d_avant``) avec le fait (les articles et quantités lus dans la fiche) ; le MODÈLE demande au client si c'est
un de plus ou le même. Client « Une regina. » ... « Une regina. » / Avant : deux reginas, rien de dit. / Après : une regina, le modèle demande « une deuxième, ou la même ? » ;
« une autre » (même fiche, tour suivant) : deux reginas ; « c'était la même » (fiche vide) : une seule."""

from __future__ import annotations

from collections import Counter

from api.tests.mark.partie_1.aides_de_la_commande import a_emporter, jusqu_au_recapitulatif, premier_article, question_posee, refuser_la_proposition

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


async def test_refus_11_la_meme_fiche_avec_une_reponse_differente_est_identique_t34(essai_de):
    """Avant T34, le « même » se lisait sur toute la fiche : la même case ``ajouter`` avec une réponse à la proposition posée s'appliquait. T34 (Pierre, 27/11 10 h 49,
    ``decisions-du-coordinateur.md``, dernière ligne) : la comparaison se fait sur les articles seuls, la réponse comprise parmi les autres cases : la question, une seule regina."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une regina", ajouter=[REGINA])
    q = question_posee(e)
    assert q.get("type") == "proposition", q
    r = await e.tour("non merci, et une autre regina", ajouter=[REGINA], reponse={"question_id": q["id"], "sens": "refuse"})
    assert _reginas(e) == 1 and r.get("raison") == RAISON, r


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


async def test_le_meme_article_inconnu_redit_n_est_pas_un_de_plus_il_reste_refuse_comme_avant(essai_de):
    """Le cas voisin (``test_p1f_lot7c_seuils_de_sortie.py``, refus 11) : un article que la carte ne connaît pas n'est jamais « pris » ; le redire au tour d'après reste le refus de l'article
    (journal des refus, sortie), jamais « une deuxième, ou la même ? »."""
    e = await essai_de()
    await a_emporter(e)
    for _ in range(2):
        r = await e.tour("un zzzquoi", ajouter=[{"article": "zzzquoi", "quantite": 1}])
        assert r.get("raison") != RAISON, r


async def test_le_meme_article_sans_sa_taille_redit_est_un_de_plus_demande(essai_de):
    """Une ligne posée dont la taille attend (``CHOIX_OBLIGATOIRE``) est prise : la même fiche redite au tour d'après est la même question que le cas de la regina complète."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
    r = await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
    assert r.get("raison") == RAISON, r


async def test_la_fiche_refaite_dans_le_meme_tour_apres_un_refus_partiel_compte_pour_le_tour_d_apres(essai_de):
    """Reprise R2 de l'audit : « une regina » dite avec un téléphone que la personne n'a pas dit : le téléphone est refusé, la regina entre ; la fiche refaite dans le MÊME tour (la regina
    seule, sa case déjà faite) est la fiche que le modèle redit au tour d'après (« je répète ») : elle est refusée comme identique, jamais une seconde regina sans rien demander."""
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    await jusqu_au_recapitulatif(e)
    await e.tour("une regina", ajouter=[REGINA], telephone="0699999999")
    avant = _reginas(e)
    await e.fiche(ajouter=[REGINA])
    assert _reginas(e) == avant
    r = await e.tour("je répète", ajouter=[REGINA])
    assert _reginas(e) == avant and r.get("raison") == RAISON, r
