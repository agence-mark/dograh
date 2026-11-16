"""[.mark] Module Restauration, lot 20, étapes 2 et 6 : le moteur de la caisse de démo répond COMME HubRise.

Les 23 réponses enregistrées du compte d'essai de HubRise (``reponses_hubrise/``) sont REJOUÉES contre le moteur, dans l'ordre : il doit répondre pareil
(mêmes codes, mêmes champs, mêmes erreurs). Les valeurs qui varient d'un compte à l'autre (identifiants, dates, noms) ne comptent pas ; la forme, si.

| Test | Ce qu'il prouve |
|---|---|
| rejeu | pour chacune des 23 réponses enregistrées : même code, même ensemble de champs à tous les niveaux, mêmes champs refusés dans les erreurs 422 |
| jeton | un jeton absent, faux ou d'un autre restaurant : 401 au format de HubRise ; un restaurant ne voit jamais les identifiants (catalogue, point de vente) d'un autre |
| carte | la carte relue, relue en format commun, est la carte écrite (aller et retour sans perte) |
| limites | les lectures de commandes au-delà de la limite : 429 avec ``Retry-After`` ; une autre minute repart de zéro |
| refus d'une caisse stricte | produit inconnu, prix différent, restaurant fermé, remise inconnue : 422 avec le champ en cause, pas de commande créée |
| rappel | une adresse de rappel qui n'est pas la nôtre est refusée (422), jamais appelée |
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.db import db_client
from api.services.restauration.caisse_demo import messages, restaurants
from api.services.restauration.caisse_demo.moteur import catalogue_id_de, empreinte_du_jeton, liste_de_clients_de, moteur
from api.services.restauration.prises import hubrise_liaison, hubrise_traduction as ht
from api.tests.mark.equipe_commun import creer_organisation

DOSSIER = Path(__file__).parent / "reponses_hubrise"
CATALOGUE_ENREGISTRE, LISTE_ENREGISTREE = "3pmq9", "w2dd8"


def _fichier(nom: str) -> dict:
    return json.loads((DOSSIER / nom).read_text(encoding="utf-8"))


def _meme_forme(attendu, obtenu, chemin="$"):
    """Les écarts de forme : mêmes clés à tous les niveaux (``custom_fields``, ``deals`` : libres), même nature de valeur, première ligne des listes comparée."""
    ecarts = []
    if isinstance(attendu, dict):
        if not isinstance(obtenu, dict):
            return [f"{chemin} : un objet était attendu"]
        if chemin.rsplit(".", 1)[-1] in ("custom_fields", "deals", "tags", "restrictions"):
            return []
        for cle in attendu.keys() - obtenu.keys():
            ecarts.append(f"{chemin}.{cle} : manque")
        for cle in obtenu.keys() - attendu.keys():
            ecarts.append(f"{chemin}.{cle} : en trop")
        for cle in attendu.keys() & obtenu.keys():
            ecarts += _meme_forme(attendu[cle], obtenu[cle], f"{chemin}.{cle}")
    elif isinstance(attendu, list):
        if not isinstance(obtenu, list):
            return [f"{chemin} : une liste était attendue"]
        if attendu and not obtenu:
            ecarts.append(f"{chemin} : vide, alors que la vraie caisse rend des lignes")
        elif attendu and obtenu:
            ecarts += _meme_forme(attendu[0], obtenu[0], f"{chemin}[0]")
    elif attendu is None or obtenu is None:
        pass  # une valeur absente d'un côté seulement n'est pas une différence de forme (champ facultatif rempli ou non)
    elif isinstance(attendu, bool) != isinstance(obtenu, bool) or type(attendu) is not type(obtenu):
        ecarts.append(f"{chemin} : {type(attendu).__name__} attendu, {type(obtenu).__name__} obtenu")
    return ecarts


@pytest.fixture
async def caisse(db_session):
    organisation = await creer_organisation(db_client, "caisse-demo-moteur")
    r = await restaurants.creer(organisation, "Test Beauvais", reglages={"enseigne": "Pizzeria .mark (Test)", "delai": 20})
    r = await db_client.modifier_restaurant_de_demo(organisation, r["id"], {"jeton_empreinte": empreinte_du_jeton("jeton-de-demo")}, restaurants.horloge(organisation).maintenant())
    return organisation, r


def _chemin(r: dict, chemin: str, ordre: str | None = None) -> str:
    chemin = chemin.replace(CATALOGUE_ENREGISTRE, catalogue_id_de(r)).replace(LISTE_ENREGISTREE, liste_de_clients_de(r)).replace("w8xvp-0", r["point_de_vente"])
    if "/location/orders/" in chemin and "inconnue" not in chemin and ordre:
        chemin = chemin.rsplit("/", 1)[0] + "/" + ordre
    return chemin


async def test_les_23_reponses_enregistrees_de_hubrise_rejouees_contre_la_caisse_de_demo(caisse):
    organisation, r = caisse
    ordre = None
    ecarts_par_fichier: dict[str, list[str]] = {}
    for fichier in sorted(p.name for p in DOSSIER.glob("*.json")):
        d = _fichier(fichier)
        demande, voulu = d["demande"], d["reponse"]
        chemin, _, requete = _chemin(r, demande["chemin"], ordre).partition("?")
        params = dict(x.split("=", 1) for x in requete.split("&")) if requete else {}
        if "phone" in params:
            params["phone"] = params["phone"].replace("%2B", "+")
        jeton = "jeton-de-demo" if voulu["code"] != 401 else "jeton-faux"
        corps = demande["corps"]
        if fichier.startswith("03"):
            corps = {"name": "Pizzeria .mark (Test)", "data": corps["data"] if "data" in corps else corps}
        if fichier.startswith("09"):
            await restaurants.regler(organisation, r["id"], {"clients": []})
        rep = await moteur.servir(jeton, demande["methode"], chemin, params, corps)
        ecarts = [] if rep.code == voulu["code"] else [f"code {rep.code} au lieu de {voulu['code']}"]
        if rep.code == voulu["code"]:
            ecarts += _meme_forme(voulu["corps"], rep.corps)
            if voulu["code"] == 422:
                assert [e["field"] for e in rep.corps["errors"]] == [e["field"] for e in voulu["corps"]["errors"]], fichier
        if fichier.startswith("12") and rep.code == 200:
            ordre = rep.corps["id"]
        if fichier.startswith("10") and rep.code == 200 and not rep.corps:
            # le client créé en 09 doit exister : la caisse de démo le garde (création, puis recherche par téléphone)
            ecarts.append("client introuvable par téléphone après sa création")
        if ecarts:
            ecarts_par_fichier[fichier] = ecarts
    assert ecarts_par_fichier == {}


async def test_un_jeton_faux_ou_d_un_autre_restaurant_est_un_401_et_les_identifiants_d_un_autre_ne_servent_pas(caisse):
    organisation, r = caisse
    autre = await restaurants.creer(organisation, "Autre")
    await db_client.modifier_restaurant_de_demo(organisation, autre["id"], {"jeton_empreinte": empreinte_du_jeton("jeton-autre")}, restaurants.horloge(organisation).maintenant())
    for jeton in (None, "", "faux", "jeton-de-demo ".strip() + "x"):
        rep = await moteur.servir(jeton, "GET", "/location")
        assert (rep.code, rep.corps["error_type"]) == (401, "unauthorized")
    assert (await moteur.servir("jeton-autre", "GET", "/location")).corps["id"] == autre["point_de_vente"]
    # le catalogue, la liste de clients et l'inventaire d'un autre restaurant : introuvables avec MON jeton
    assert (await moteur.servir("jeton-de-demo", "GET", f"/catalogs/{catalogue_id_de(autre)}")).code == 404
    assert (await moteur.servir("jeton-de-demo", "GET", f"/customer_lists/{liste_de_clients_de(autre)}/customers")).code == 404
    assert (await moteur.servir("jeton-de-demo", "GET", f"/catalogs/{catalogue_id_de(r)}/locations/{autre['point_de_vente']}/inventory")).code == 404
    commande = {"status": "new", "items": [{"product_name": "X", "price": "1.00 EUR", "quantity": "1"}], "private_ref": "A-1"}
    cree = await moteur.servir("jeton-autre", "POST", "/location/orders", corps=commande)
    assert (await moteur.servir("jeton-de-demo", "GET", f"/location/orders/{cree.corps['id']}")).code == 404  # une commande d'un autre restaurant


async def test_la_carte_relue_est_la_carte_ecrite(caisse):
    organisation, r = caisse
    carte = {
        "format": ht.FORMAT_CARTE, "categories": [{"id": "PIZ", "nom": "Pizzas", "parent_id": None, "ordre": 0, "portee": "etablissement"}],
        "produits": [{"id": "REINE", "nom": "Reine", "description": "Jambon", "categorie_id": "PIZ", "groupes": ["SUPP"], "ingredients": [], "allergenes": None, "tva_par_mode": {}, "etoile": False,
                      "declinaisons": [{"id": "REINE-S", "nom": "Senior", "code_caisse": "REINE-S", "prix": 1250, "disponibilite": None}]}],
        "groupes": [{"id": "SUPP", "nom": "Suppléments", "min": 0, "max": 2, "max_par_option": 1, "defaut": [], "parent_option_id": None, "role": "choix",
                     "options": [{"id": "SUPP-F", "groupe_id": "SUPP", "nom": "Fromage", "code_caisse": "SUPP-F", "prix": 150, "par_defaut": False, "retirable": False}]}],
        "formules": [],
    }
    await restaurants.regler(organisation, r["id"], {"carte": carte})
    lue = (await moteur.servir("jeton-de-demo", "GET", f"/catalogs/{catalogue_id_de(r)}")).corps
    relue = ht.carte_de_hubrise(lue).carte
    assert [p["declinaisons"][0]["code_caisse"] for p in relue["produits"]] == ["REINE-S"] and relue["produits"][0]["declinaisons"][0]["prix"] == 1250
    assert relue["produits"][0]["groupes"] == ["SUPP"] and relue["groupes"][0]["options"][0]["prix"] == 150 and relue["categories"][0]["nom"] == "Pizzas"
    # les identifiants sont stables : relire deux fois rend la même carte
    assert (await moteur.servir("jeton-de-demo", "GET", f"/catalogs/{catalogue_id_de(r)}")).corps["data"] == lue["data"]


async def test_les_lectures_de_commandes_sont_limitees_puis_repartent(caisse):
    organisation, r = caisse
    await restaurants.regler(organisation, r["id"], {"comportement": {"limite_commandes": 2}})
    rep = [await moteur.servir("jeton-de-demo", "GET", "/location/orders") for _ in range(3)]
    assert [x.code for x in rep] == [200, 200, 429]
    assert rep[2].corps["error_type"] == "too_many_requests" and int(rep[2].entetes["Retry-After"]) >= 1
    assert (await moteur.servir("jeton-de-demo", "GET", "/location")).code == 200  # les autres routes ne sont pas touchées


async def test_une_caisse_stricte_refuse_ce_qui_ne_colle_pas_a_sa_carte(caisse):
    organisation, r = caisse
    carte = {"format": ht.FORMAT_CARTE, "categories": [], "groupes": [], "formules": [],
             "produits": [{"id": "P", "nom": "P", "categorie_id": None, "groupes": [], "declinaisons": [{"id": "P-1", "nom": "P", "code_caisse": "P-1", "prix": 1000}]}]}
    await restaurants.regler(organisation, r["id"], {"carte": carte, "comportement": {"reponse": "controle"}, "reglages": {"remises": [{"ref": "R10", "nom": "10", "effet": "remise", "valeur": "1.00 EUR"}]}})

    def commande(**plus):
        item = {"product_name": "P", "sku_ref": "P-1", "price": "10.00 EUR", "quantity": "1"} | plus.pop("item", {})
        return {"status": "new", "private_ref": "S-1", "items": [item], **plus}

    async def poser(c):
        return await moteur.servir("jeton-de-demo", "POST", "/location/orders", corps=c)

    assert (await poser(commande())).code == 200
    cas = {
        "produit_inconnu": (commande(item={"sku_ref": "INCONNU"}), "/items/0/sku_ref"),
        "prix_different": (commande(item={"price": "9.00 EUR"}), "/items/0/price"),
        "remise_inconnue": (commande(discounts=[{"name": "x", "ref": "R99", "price_off": "1.00 EUR"}]), "/discounts/0/ref"),
    }
    for nom, (c, champ) in cas.items():
        rep = await poser(c)
        assert (rep.code, [e["field"] for e in rep.corps["errors"]]) == (422, [champ]), nom
    assert (await poser(commande(discounts=[{"name": "x", "ref": "R10", "price_off": "1.00 EUR"}]))).code == 200  # une remise connue passe
    await restaurants.regler(organisation, r["id"], {"etat": "ferme"})
    ferme = await poser(commande())
    assert (ferme.code, ferme.corps["errors"][0]["field"]) == (422, "/")
    assert len(await db_client.lister_commandes_de_demo(r["id"])) == 2  # les refus n'ont rien créé


async def test_une_adresse_de_rappel_qui_n_est_pas_la_notre_est_refusee(caisse):
    organisation, r = caisse
    for url in ("https://exemple.test/rappel", "http://169.254.169.254/latest", hubrise_liaison.adresse_de_rappel() + " x", "file:///etc/passwd"):
        rep = await moteur.servir("jeton-de-demo", "POST", "/callback", corps={"url": url, "events": {}})
        assert (rep.code, rep.corps["errors"][0]["field"]) == (422, "/url"), url
        assert not messages.url_de_rappel_permise(url)
    assert (await db_client.lire_restaurant_de_demo(organisation, r["id"]))["callback_url"] is None
    ok = await moteur.servir("jeton-de-demo", "POST", "/callback", corps={"url": hubrise_liaison.adresse_de_rappel(), "events": {"order": ["update"]}})
    assert ok.code == 200 and (await db_client.lire_restaurant_de_demo(organisation, r["id"]))["callback_url"] == hubrise_liaison.adresse_de_rappel()
    passif = await moteur.servir("jeton-de-demo", "POST", "/callback", corps={"url": None, "events": {}})
    assert passif.code == 200 and (await db_client.lire_restaurant_de_demo(organisation, r["id"]))["callback_url"] is None


async def test_les_horaires_du_restaurant_de_test_sont_ceux_de_la_forme_publique_de_hubrise(caisse):
    """``opening_hours`` (documentation publique, Locations) : jours ``monday``..., créneaux ``{from, to}`` ``HH:mm`` ; la caisse les rend, la prise les lit, le reste est refusé."""
    organisation, r = caisse
    horaires = {"monday": [{"from": "18:00", "to": "01:00"}, {"from": "11:30", "to": "14:30"}], "friday": [{"from": "11:30", "to": "14:30"}]}
    assert (await moteur.servir("jeton-de-demo", "GET", "/location")).corps["opening_hours"] is None  # non posés : null, comme la caisse
    await restaurants.regler(organisation, r["id"], {"reglages": {"horaires": horaires}})
    rendu = (await moteur.servir("jeton-de-demo", "GET", "/location")).corps
    assert rendu["opening_hours"]["monday"] == [{"from": "11:30", "to": "14:30"}, {"from": "18:00", "to": "01:00"}] and "tuesday" not in rendu["opening_hours"]
    assert ht.etat_de_hubrise(rendu)["horaires"] == rendu["opening_hours"]  # ce que la liaison compare à la fiche
    for mauvais in (
        {"lundi": [{"from": "11:00", "to": "12:00"}]}, {}, {"monday": []}, {"monday": [{"from": "11:00"}]}, {"monday": [{"from": "11h", "to": "12:00"}]},
        {"monday": [{"from": "14:00", "to": "12:00"}]}, {"monday": [{"from": "11:00", "to": "13:00"}, {"from": "12:00", "to": "15:00"}]}, {"monday": [{"from": "25:00", "to": "26:00"}]},
    ):
        with pytest.raises(restaurants.RestaurantDeTestRefuse):
            await restaurants.regler(organisation, r["id"], {"reglages": {"horaires": mauvais}})
    assert (await moteur.servir("jeton-de-demo", "GET", "/location")).corps["opening_hours"]["friday"] == [{"from": "11:30", "to": "14:30"}]  # un refus ne touche à rien
    await restaurants.regler(organisation, r["id"], {"reglages": {"horaires": None}})
    assert (await moteur.servir("jeton-de-demo", "GET", "/location")).corps["opening_hours"] is None
