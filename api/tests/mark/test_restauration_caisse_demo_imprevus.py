"""[.mark] Module Restauration, lot 20 (E-53) : les IMPRÉVUS PENDANT L'APPEL, déclenchés tout seuls par la caisse de démo (maquette F11).

Vraies bases, aucun réseau : on parle au moteur comme la prise (jeton, ``/v1``) et on lit ce que la caisse a écrit (commandes, stocks, messages signés à rendre).

| Test | Ce qu'il prouve |
|---|---|
| rupture | une commande qui contient le produit visé est reçue puis REFUSÉE, le produit passe en rupture et la caisse le dit (``order.update``, ``inventory.patch``) ; une commande sans lui n'est pas touchée ; éteint : rien ; « auto » vise le premier produit |
| carte changée | la première lecture de la carte rend la carte d'avant, le prix monte juste après (``catalog.update``), une seule fois ; une caisse stricte refuse alors l'ancien prix |
| deux fois | la commande est reçue deux fois (même ``private_ref``, deux identifiants) ; éteint : une seule |
| réglages | les trois comportements se valident ; une caisse neuve répond en 400 ms ; mettre un comportement en place remet « le prix a déjà changé » à zéro ; les scénarios de la maquette sont livrés |
"""

from __future__ import annotations

import pytest

from api.db import db_client
from api.services.restauration.caisse_demo import restaurants, scenarios
from api.services.restauration.caisse_demo.moteur import catalogue_id_de, empreinte_du_jeton, moteur
from api.tests.mark.equipe_commun import creer_organisation

CARTE = {
    "format": "mark-carte-commune/1", "categories": [], "groupes": [], "formules": [],
    "produits": [
        {"id": "REINE", "nom": "Reine", "categorie_id": None, "groupes": [], "declinaisons": [{"id": "REINE-S", "nom": "Senior", "code_caisse": "REINE-S", "prix": 1250}]},
        {"id": "COLA", "nom": "Coca-Cola", "categorie_id": None, "groupes": [], "declinaisons": [{"id": "COLA-33", "nom": "33 cl", "code_caisse": "COLA-33", "prix": 250}]},
    ],
}


def _commande(code: str, prix: str = "12.50 EUR", ref: str = "essai-1") -> dict:
    return {"status": "new", "service_type": "collection", "private_ref": ref, "items": [{"product_name": "X", "sku_ref": code, "price": prix, "quantity": "1"}]}


async def _restaurant(comportement: dict, nom: str = "imprevus", jeton: str = "jeton"):
    organisation = await creer_organisation(db_client, nom)
    r = await restaurants.creer(organisation, "Test", carte=CARTE, comportement=comportement)
    r = await db_client.modifier_restaurant_de_demo(organisation, r["id"], {"jeton_empreinte": empreinte_du_jeton(jeton)}, restaurants.horloge(organisation).maintenant())
    return organisation, r


async def _messages(r) -> list[tuple[str, str]]:
    return [(m["corps"]["resource_type"], m["corps"]["event_type"]) for m in await db_client.lister_messages_de_demo(r["id"])]


async def test_la_rupture_en_plein_appel_refuse_la_commande_qui_contient_le_produit_et_le_dit(db_session):
    organisation, r = await _restaurant({"reponse": "accepte", "acceptation": "auto", "rupture_plein_appel": "COLA"})
    sans = await moteur.servir("jeton", "POST", "/location/orders", corps=_commande("REINE-S"))
    avec = await moteur.servir("jeton", "POST", "/location/orders", corps=_commande("COLA-33", "2.50 EUR", "essai-2"))
    assert (sans.code, avec.code) == (200, 200)  # la caisse reçoit les deux : c'est après qu'elle refuse
    statuts = {c["private_ref"]: c["statut"] for c in await db_client.lister_commandes_de_demo(r["id"])}
    assert statuts == {"essai-1": "accepted", "essai-2": "rejected"}
    r = await db_client.lire_restaurant_de_demo(organisation, r["id"])
    assert [s["sku_ref"] for s in r["stocks"]] == ["COLA-33"] and r["stocks"][0]["stock"] == "0.0"
    assert ("inventory", "patch") in await _messages(r) and ("order", "update") in await _messages(r)
    # éteint : rien ne se passe
    organisation2, r2 = await _restaurant({"reponse": "accepte", "acceptation": "auto"}, "imprevus-eteint", "jeton-2")
    await moteur.servir("jeton-2", "POST", "/location/orders", corps=_commande("COLA-33"))
    assert (await db_client.lire_restaurant_de_demo(organisation2, r2["id"]))["stocks"] == []


async def test_la_rupture_automatique_vise_le_premier_produit_de_la_carte(db_session):
    organisation, r = await _restaurant({"reponse": "accepte", "acceptation": "auto", "rupture_plein_appel": "auto"})
    await moteur.servir("jeton", "POST", "/location/orders", corps=_commande("REINE-S"))
    assert [c["statut"] for c in await db_client.lister_commandes_de_demo(r["id"])] == ["rejected"]


async def test_la_carte_change_apres_la_premiere_lecture_une_seule_fois(db_session):
    organisation, r = await _restaurant({"reponse": "accepte", "carte_changee": True})
    chemin = f"/catalogs/{catalogue_id_de(r)}"
    lue = await moteur.servir("jeton", "GET", chemin)
    assert lue.code == 200
    assert "12.50 EUR" in str(lue.corps)  # la carte rendue est celle d'avant
    apres = await db_client.lire_restaurant_de_demo(organisation, r["id"])
    assert apres["carte"]["produits"][0]["declinaisons"][0]["prix"] == 1300 and apres["reglages"]["prix_change_fait"] is True
    assert ("catalog", "update") in await _messages(r)
    await moteur.servir("jeton", "GET", chemin)
    assert (await db_client.lire_restaurant_de_demo(organisation, r["id"]))["carte"]["produits"][0]["declinaisons"][0]["prix"] == 1300  # pas deux fois


async def test_une_caisse_stricte_refuse_l_ancien_prix_apres_le_changement(db_session):
    organisation, r = await _restaurant({"reponse": "controle", "controles": ["prix_different"], "carte_changee": True})
    await moteur.servir("jeton", "GET", f"/catalogs/{catalogue_id_de(r)}")
    refusee = await moteur.servir("jeton", "POST", "/location/orders", corps=_commande("REINE-S", "12.50 EUR"))
    assert refusee.code == 422


async def test_la_commande_recue_deux_fois_a_deux_identifiants_et_la_meme_reference(db_session):
    organisation, r = await _restaurant({"reponse": "accepte", "acceptation": "auto", "commande_deux_fois": True})
    rep = await moteur.servir("jeton", "POST", "/location/orders", corps=_commande("REINE-S"))
    lignes = await db_client.lister_commandes_de_demo(r["id"])
    assert len(lignes) == 2 and {c["private_ref"] for c in lignes} == {"essai-1"} and len({c["ref"] for c in lignes}) == 2 and rep.corps["id"] in {c["ref"] for c in lignes}
    organisation2, r2 = await _restaurant({"reponse": "accepte", "acceptation": "auto"}, "imprevus-une-fois", "jeton-2")
    await moteur.servir("jeton-2", "POST", "/location/orders", corps=_commande("REINE-S"))
    assert len(await db_client.lister_commandes_de_demo(r2["id"])) == 1


async def test_les_imprevus_se_valident_la_caisse_neuve_repond_en_400_ms_et_les_scenarios_de_la_maquette_sont_livres(db_session):
    organisation = await creer_organisation(db_client, "imprevus-reglages")
    neuve = await restaurants.creer(organisation, "Neuve")
    assert neuve["comportement"] == {"delai_s": 0.4}
    # M53 : une caisse neuve ne porte ni types de commande ni moyens de paiement (le module les tient)
    assert not {"types_de_commande", "paiements", "zones"} & set(neuve["reglages"])
    for mauvais in ({"rupture_plein_appel": 12}, {"rupture_plein_appel": ""}, {"rupture_plein_appel": "x" * 90}):
        with pytest.raises(restaurants.RestaurantDeTestRefuse):
            restaurants.comportement_valide(mauvais)
    assert restaurants.comportement_valide({"rupture_plein_appel": "COLA", "carte_changee": 1, "commande_deux_fois": 0}) == {"rupture_plein_appel": "COLA", "carte_changee": True, "commande_deux_fois": False}
    assert restaurants.comportement_valide({"rupture_plein_appel": None}) == {}
    # mettre un comportement en place remet à zéro « le prix a déjà changé »
    await db_client.modifier_restaurant_de_demo(organisation, neuve["id"], {"reglages": {**neuve["reglages"], "prix_change_fait": True}}, restaurants.horloge(organisation).maintenant())
    r = await restaurants.regler(organisation, neuve["id"], {"comportement": {"carte_changee": True}})
    assert r["reglages"]["prix_change_fait"] is False
    livres = await scenarios.livrer(organisation)
    for cle in ("rupture-en-plein-appel", "refus-prix-different", "commande-recue-deux-fois"):
        assert cle in livres
        assert restaurants.comportement_valide(livres[cle]["comportement"]) == livres[cle]["comportement"]
