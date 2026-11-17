"""[.mark] M104 (appel 2591) : « vous avez des pizzas sans gluten ? », « un plat sans lactose ? », « quelque chose de végétarien ? ».

``voir_produit`` cherchait un article nommé « pizzas sans gluten » : introuvable, « je ne peux pas vous le confirmer ». Le moteur cherche
désormais dans la carte ce qui est SANS une chose, d'après la donnée seulement.

| Test | Ce qu'il prouve |
|---|---|
| sans dans une catégorie | seuls les articles dont la donnée prouve l'absence sont nommés ; les autres, « je ne peux pas le garantir » |
| tous en contiennent | « je ne peux pas vous garantir de pizzas sans gluten : il y en a partout » |
| donnée absente | jamais un faux « sans » : « la fiche ne le précise pas, l'équipe peut vous répondre » |
| choix obligatoire inconnu | un article dont un choix obligatoire est sans donnée n'est jamais « sans » |
| toute la carte | ``produit`` vide et ``a_eviter`` : la carte entière, seuls les « sûrs » nommés |
| régime | « végétarien » ne se déduit d'aucune donnée : réponse honnête, aucun article nommé |
| un article précis | « la Regina sans gluten » reste la question sur UN article (comme avant) |
"""

from __future__ import annotations

from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401

PIZZAS = ("pizzas-tomate", "pizzas-creme", "pizzas-eccellenza")


async def _vu(commerce, allergenes_des_pizzas: str | None = None):
    from api.services.commande import moteur
    from api.tests.mark.test_restauration_commande_finaliser import Appel

    if allergenes_des_pizzas is not None:
        await commerce.c.execute("UPDATE mark.resto_produit SET allergenes = $1::text[] WHERE categorie_ref = ANY($2)", allergenes_des_pizzas.split(","), list(PIZZAS))
    appel = Appel(commerce)
    return lambda produit, signale=None: moteur.voir_produit(appel.source, appel.p, appel.regles, produit, signale)


async def test_pizzas_sans_gluten_nomme_seulement_celles_que_la_donnee_prouve(commerce):
    vu = await _vu(commerce, "gluten,lait")
    await commerce.c.execute("UPDATE mark.resto_produit SET allergenes = '{lait}' WHERE nom = 'Margherita'")
    await commerce.c.execute("UPDATE mark.resto_produit SET allergenes = NULL WHERE nom = 'Regina'")
    r = await vu("pizzas sans gluten")
    assert r.statut == "OK", r
    assert r.faits["recherche"] == "sans" and r.faits["code"] == "gluten" and len(r.faits["categories"]) == 3
    assert r.faits["sans"] == ["Margherita"] and r.faits["inconnus"] == 1
    assert r.suggestion == "D'après la fiche, Margherita ne contient pas de gluten. Pour les autres, je ne peux pas le garantir."
    # même question, par le paramètre : « pizzas » et « gluten » séparés
    assert (await vu("des pizzas", "sans gluten")).faits["sans"] == ["Margherita"]


async def test_toutes_en_contiennent_le_dit_sans_jamais_dire_sans(commerce):
    vu = await _vu(commerce, "gluten,lait")
    r = await vu("pizzas sans gluten")
    assert r.faits["sans"] == [] and r.faits["inconnus"] == 0 and r.faits["contiennent"] > 1
    assert r.suggestion == "Je ne peux pas vous garantir de pizzas sans gluten : d'après la fiche, il y en a partout."


async def test_une_donnee_absente_n_est_jamais_sans(commerce):
    vu = await _vu(commerce)  # les pizzas de la carte d'essai n'ont aucune donnée d'allergènes
    r = await vu("pizzas sans gluten")
    assert r.faits["sans"] == [] and r.faits["inconnus"] > 0
    assert r.suggestion == "Je ne peux pas vous garantir de pizzas sans gluten : la fiche ne le précise pas, l'équipe peut vous répondre."
    assert "INTROUVABLE" != r.statut and "ne contient pas" not in r.suggestion


async def test_un_choix_obligatoire_sans_donnee_n_est_jamais_sans(commerce):
    vu = await _vu(commerce)
    await commerce.c.execute("UPDATE mark.resto_produit SET allergenes = '{oeufs,lait}' WHERE ref = 'P-DESSERTS-TIRAMISU'")
    r = await vu("desserts sans gluten")
    assert "Tiramisu" not in r.faits["sans"] and r.faits["inconnus"] >= 1, r


async def test_toute_la_carte_quand_rien_n_est_nomme(commerce):
    vu = await _vu(commerce, "gluten,lait")
    r = await vu(None, "lactose")
    assert r.statut == "OK" and r.faits["code"] == "lait" and r.faits["categories"] == []
    assert r.faits["sans"], r  # les boissons de la carte d'essai portent leur donnée
    assert not any(n in r.faits["sans"] for n in ("Margherita", "Regina"))
    assert "ne contiennent pas de lait" in r.suggestion
    # « un plat sans lactose » : « plat » ne nomme aucune catégorie de cette carte, la carte entière
    assert (await vu("un plat sans lactose")).faits["sans"] == r.faits["sans"]


async def test_un_regime_ne_se_deduit_jamais(commerce):
    vu = await _vu(commerce, "gluten,lait")
    for produit, signale in (("qu'est-ce que vous avez de végétarien", None), ("pizzas", "végétarien"), (None, "halal")):
        r = await vu(produit, signale)
        assert r.statut == "OK" and r.faits["renseigne"] is False and "sans" not in r.faits, r
        assert r.suggestion.startswith("Je ne peux pas vous garantir ce qui est ") and "l'équipe peut vous répondre" in r.suggestion


async def test_un_article_precis_reste_la_question_sur_un_article(commerce):
    vu = await _vu(commerce)
    r = await vu("Regina sans gluten")
    assert r.statut == "OK" and "recherche" not in r.faits and r.faits["article"] == "Regina", r
    r = await vu("Regina", "gluten")
    assert "recherche" not in r.faits and r.faits["signalement"] == "inconnu"


def test_l_etat_d_un_article():
    from api.services.commande.moteur import _etat_sans

    gluten = [{"code": "gluten"}]
    assert _etat_sans({"signalements": None}, "gluten") == "inconnu"
    assert _etat_sans({"signalements": gluten}, "gluten") == "contient"
    assert _etat_sans({"signalements": []}, "gluten") == "sur"
    # un choix obligatoire : une option sûre suffit ; toutes qui en contiennent par leur nom = contient ; sinon inconnu
    sure = {"nom": "Riz", "signalements": [], "signalements_du_nom": []}
    nommee = {"nom": "Blé", "signalements": None, "signalements_du_nom": ["gluten"]}
    inconnue = {"nom": "Sauce", "signalements": None, "signalements_du_nom": []}
    assert _etat_sans({"signalements": [], "obligatoires": [[sure, nommee]]}, "gluten") == "sur"
    assert _etat_sans({"signalements": [], "obligatoires": [[nommee]]}, "gluten") == "contient"
    assert _etat_sans({"signalements": [], "obligatoires": [[inconnue, nommee]]}, "gluten") == "inconnu"


def test_les_regimes_reconnus():
    from api.services.restauration.signalements import regime_dit

    assert regime_dit("vous avez des pizzas végétariennes") == "végétarien"
    assert regime_dit("un plat vegan") == "végétalien"
    assert regime_dit("c'est halal ?") == "halal"
    assert regime_dit("une pizza sans viande") == "sans viande"
    assert regime_dit("une pizza au porc") is None  # sans « sans », ce n'est pas un régime
