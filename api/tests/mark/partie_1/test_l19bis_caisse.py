"""[.mark] Chantier Partie 1, lot 19 bis, étape A : la caisse (HubRise), rejouée sur les VRAIES réponses du 20/11 (``reponses_hubrise/19bis/``).

Aucun test n'appelle HubRise : le transport est enregistré (``httpx.MockTransport``) et ne rend que ce que HubRise a rendu en réel.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from api.services.restauration import envoi_caisse as ec
from api.services.restauration.prises import hubrise_client
from api.services.restauration.prises import hubrise_traduction as ht
from api.services.restauration.prises.hubrise_client import ClientHubrise
from api.services.restauration.prises.prise_hubrise import PriseHubrise
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import application_configuree  # noqa: F401
from api.tests.mark.test_restauration_envoi_caisse import (
    Secours,
    _commande,
    _etablissement_branche,
    _etat,
)

DOSSIER = Path(__file__).parents[1] / "reponses_hubrise" / "19bis"


def _f(nom: str) -> dict:
    """Un fichier enregistré : ``{"demande": ..., "reponse": {"code", "corps"}}``."""
    return json.loads((DOSSIER / f"{nom}.json").read_text(encoding="utf-8"))


def _rendue(nom: str):
    """La réponse enregistrée, prête à être rendue par un transport simulé."""
    r = _f(nom)["reponse"]
    return httpx.Response(r["code"], json=r["corps"])


def _prise(rendre) -> PriseHubrise:
    return PriseHubrise(ClientHubrise("jeton-de-test", point_de_vente="w8xvp-0", transport=httpx.MockTransport(rendre)))


# --------------------------------------------------------------------------- K2


def test_quantite_decimale_relue_de_la_caisse():
    """K2 : HubRise relit ``"0.25"``, ``"1.0"`` et ``"0.123457"`` (01b, 03, 206c) : la lecture ne les refuse plus."""
    assert ht._quantite("0.25") == ht.Decimal("0.25")
    assert ht._quantite("1.0") == 1 and ht._quantite("0.123457") == ht.Decimal("0.123457")
    lue = ht.commande_de_hubrise(_f("01b-poids-relu")["reponse"]["corps"])
    # 16,00 x 0,25 = 4,00 ; 12,00 x 0,333333 = 3,999996 tronqué à 3,99 (la caisse a compté 7,99) : la lecture rend la valeur de la ligne, jamais une erreur
    assert [(l["prix_unitaire"], l["quantite"], l["quantite_lue"]) for l in lue["lignes"]] == [(400, 1, "0.25"), (399, 1, "0.333333")]
    assert lue["total"] == 799


async def test_reponse_illisible_apres_envoi_reussi_jamais_echec():
    """K2 : le POST a réussi (200, ``quantity "0.25"``, 01b) : une lecture qui échoue ensuite ne fait JAMAIS un échec, la commande est en caisse (``ENVOYEE``, ``id`` brut)."""
    vraie = _f("01b-poids-relu")["reponse"]["corps"]
    # une réponse que notre lecture ne sait pas lire (un montant mal écrit), mais que HubRise a bien acceptée
    illisible = {**vraie, "total": "7,99 EUR"}
    prise = _prise(lambda r: httpx.Response(200, json=illisible))
    commande = {"numero": "mark-19bis-poids", "mode": "emporter", "lignes": [{"nom": "Mozzarella", "code_caisse": "MOZ", "prix_unitaire": 400, "quantite": 1}]}
    resultat = await prise.faire_envoyer(commande)
    assert (resultat.statut, resultat.ref_fournisseur) == ("ENVOYEE", vraie["id"])


# --------------------------------------------------------------------------- K1 (la caisse en panne au renvoi : essais comptés, restaurant prévenu au 5e)

async def test_caisse_injoignable_au_renvoi_passe_en_echec_et_alerte(db_session, seconde_base, sans_preparation_des_organisations, application_configuree, monkeypatch):  # noqa: F811
    """K1 : la commande est déjà ``envoyee`` (renvoi), la caisse ne répond ni à la recherche par notre numéro ni à l'envoi : chaque essai est compté, au 5e la commande passe en ``echec`` et le restaurant est prévenu UNE fois."""
    monkeypatch.setattr(hubrise_client, "PAUSES_S", (0.0, 0.0))
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab, statut="envoyee")
    demandes: list[httpx.Request] = []

    def en_panne(requete: httpx.Request) -> httpx.Response:
        demandes.append(requete)
        return httpx.Response(503, json={})

    secours = Secours()
    transport = httpx.MockTransport(en_panne)
    for essai in range(1, ec.TENTATIVES_MAX):
        issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=transport, secours=secours)
        assert issue is not None and issue.issue == "a_reprendre", essai
        assert (await _etat(cas.base_a, numero))["tentatives"] == essai and secours.messages == []
    dernier = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=transport, secours=secours)
    assert dernier is not None and dernier.issue == "a_reprendre"
    assert (await _etat(cas.base_a, numero))["statut"] == "echec" and len(secours.messages) == 1
    assert [r.method for r in demandes if r.method == "POST"] == []  # le renvoi n'est jamais tenté sans savoir si la caisse a déjà la commande


# --------------------------------------------------------------------------- K3 / N2 / K4 (ce que la commande envoyée porte : options, poids, retraits)


def _formule_avec_options() -> dict:
    """La commande du 03 : un menu de deux pizzas, la première avec deux suppléments fromage, la seconde avec deux suppléments œuf ; prix de la ligne tout compris (23,25 €)."""
    return {
        "numero": "mark-19bis-menu", "mode": "emporter", "client": {"telephone": "+33600000001", "prenom": "Camille"},
        "lignes": [
            {
                "code_caisse": "DUO", "nom": "2e pizza à moitié prix (Test)", "prix_unitaire": 2325, "quantite": 1, "formule_id": "DUO",
                "choix": [
                    {"option_code": "REINE-S", "nom": "Reine (Test)", "produit_nom": "Reine (Test)", "prix": 1250, "quantite": 1, "groupe": "1re pizza",
                     "choix": [{"option_code": "SUPP-FROMAGE", "nom": "Supplément fromage", "prix": 150, "quantite": 2, "groupe": "Suppléments"}]},
                    {"option_code": "MARG-S", "nom": "Margherita (Test)", "produit_nom": "Margherita (Test)", "prix": 575, "quantite": 1, "groupe": "2e pizza",
                     "choix": [{"option_code": "SUPP-OEUF", "nom": "Supplément œuf", "prix": 100, "quantite": 2, "groupe": "Suppléments"}]},
                ],
            }
        ],
    }


async def _envoyee_par_la_prise(commande: dict, reponse: str) -> dict:
    """Le corps que la prise HubRise envoie (par ``envoyer_commande``, donc après ``adapter_commande``), le transport rendant la réponse enregistrée ``reponse``."""
    envoyes: list[dict] = []

    def rendre(requete: httpx.Request) -> httpx.Response:
        envoyes.append(json.loads(requete.content))
        return _rendue(reponse)

    prise = _prise(rendre)
    await prise.envoyer_commande(commande)
    return envoyes[0]


def _total_des_articles(corps: dict) -> int:
    """Ce que HubRise somme : chaque article à sa quantité, avec ses options (chacune multipliée par la quantité de l'article, prouvé en 02), ses retraits à leur prix."""
    total = 0
    for a in corps["items"]:
        quantite = ht._quantite(a["quantity"])
        options = sum(ht.centimes(o["price"]) * o.get("quantity", 1) for o in a.get("options") or [])
        total += int(ht._tronque_au_centime((ht.centimes(a["price"]) + options) * quantite))
    return total


async def test_menu_avec_options_envoye_avec_ses_options():
    """K3 : sur le 03, la sauce et le fromage partent comme OPTIONS de l'article du menu, jamais comme des produits ; le total de la caisse (23,25 €) est le nôtre."""
    corps = await _envoyee_par_la_prise(_formule_avec_options(), "03-menu-options-cree")
    assert [a["sku_ref"] for a in corps["items"]] == ["REINE-S", "MARG-S"]
    assert [sorted({o["ref"] for o in a["options"]}) for a in corps["items"]] == [["SUPP-FROMAGE"], ["SUPP-OEUF"]]
    assert _total_des_articles(corps) == 2325 == ht.centimes(_f("03-menu-options-cree")["reponse"]["corps"]["total"])


def _poids_avec_barquette() -> dict:
    """Le 02 : 250 g de mozzarella à 16,00 € le kilo (4,00 €) et une barquette à 0,50 € : 4,50 € de notre côté."""
    return {
        "numero": "mark-19bis-poids-option", "mode": "emporter", "client": {"telephone": "+33600000001", "prenom": "Camille"},
        "lignes": [
            {
                "code_caisse": "MOZ-KILO", "nom": "Mozzarella au poids (Test)", "prix_unitaire": 450, "quantite": 1, "poids_g": 250,
                "choix": [{"option_code": None, "nom": "Barquette", "prix": 50, "quantite": 1, "groupe": "Emballage"}],
            }
        ],
    }


async def test_poids_avec_option_meme_total_en_caisse():
    """K4 : HubRise multiplie les options par la quantité de l'article (02 : 4,00 + 0,50 x 0,25 = 4,125 tronqué à 4,12 au lieu de nos 4,50). Une ligne au poids qui porte un choix payant part en quantité ENTIÈRE, le poids dans le nom."""
    reel = _f("02-poids-option-cree")
    # la règle de la caisse, relue sur la vraie réponse : l'ancien corps donnait bien 4,12 (le contrôle du calcul lui-même)
    assert _total_des_articles(reel["demande"]["corps"]) == ht.centimes(reel["reponse"]["corps"]["total"]) == 412
    corps = await _envoyee_par_la_prise(_poids_avec_barquette(), "02-poids-option-cree")
    ligne = corps["items"][0]
    assert ligne["quantity"] == "1" and "250 g" in ligne["product_name"]
    assert _total_des_articles(corps) == 450


async def test_poids_sans_option_garde_la_quantite_decimale_prouvee():
    """K4, ce qui ne change pas : une ligne au poids SANS option garde le prix au kilo et la quantité décimale (01 : 0,250 donne 4,00 chez HubRise)."""
    commande = {"numero": "mark-19bis-poids", "mode": "emporter", "lignes": [{"code_caisse": "MOZ-KILO", "nom": "Mozzarella au poids (Test)", "prix_unitaire": 400, "quantite": 1, "poids_g": 250}]}
    corps = await _envoyee_par_la_prise(commande, "01-poids-cree")
    assert (corps["items"][0]["price"], corps["items"][0]["quantity"]) == ("16.00 EUR", "0.250")
    assert _total_des_articles(corps) == 400


async def test_total_different_en_caisse_alerte_sans_rien_renvoyer(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    """K4 : après l'envoi, le ``total`` rendu par la caisse (jamais ``total_discrepancy``, déprécié) est comparé au nôtre ; un écart prévient le restaurant (UNE fois) sans renvoyer ni refuser : la commande est en caisse."""
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)  # notre total : 12,50 €
    reel = _f("02-poids-option-cree")["reponse"]["corps"]  # la caisse a compté 4,12 €

    def rendre(requete: httpx.Request) -> httpx.Response:
        corps = json.loads(requete.content)
        return httpx.Response(200, json={**reel, "private_ref": corps["private_ref"], "id": "caisse-ecart", "total_discrepancy": "9.99 EUR"})

    secours = Secours()
    issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=httpx.MockTransport(rendre), secours=secours)
    assert issue.issue == "envoyee" and (await _etat(cas.base_a, numero))["statut"] == "envoyee"
    assert len(secours.messages) == 1
    _sujet, texte = secours.messages[0][1:]
    assert "12,50" in texte and "4,12" in texte and "9,99" not in texte


# --------------------------------------------------------------------------- K6 (horaires qui passent minuit)


def test_horaires_de_la_caisse_apres_minuit():
    """K6 : sur la vraie réponse 05b, vendredi ``18:00 -> 01:00`` finit samedi à 1 h, samedi ``18:00 -> 00:00`` finit à minuit : le soir n'est jamais lu « fermé »."""
    from datetime import time

    from api.db.bases_clients import horaires_caisse as hc

    point_de_vente = _f("05b-horaires-relus")["reponse"]["corps"]
    jours = hc.jours_de_la_caisse(ht.etat_de_hubrise(point_de_vente)["horaires"])
    assert jours[5] == [(time(11, 30), time(14, 0)), (time(18, 0), hc.FIN_DE_JOURNEE)]  # vendredi, jusqu'à la fin du jour
    assert jours[6] == [(time(0, 0), time(1, 0)), (time(18, 0), hc.FIN_DE_JOURNEE)]  # samedi : la fin de vendredi (1 h), puis son propre soir
    assert sorted(jours) == [5, 6]  # un jour que la caisse dit vide ([]) n'a aucune plage
    texte = hc.texte_de_la_fiche(jours)
    assert "samedi : 00:00-01:00 et 18:00-" in texte and "lundi : fermé" in texte
    # « 24:00 » (que HubRise refuse, 05c, mais qu'une autre caisse peut écrire) se lit comme la fin du jour ; une fin après le cutoff (05d) reste une horaire illisible, ignorée
    assert hc.jours_de_la_caisse({"friday": [{"from": "18:00", "to": "24:00"}]}) == {5: [(time(18, 0), hc.FIN_DE_JOURNEE)]}
    assert hc.jours_de_la_caisse({"friday": [{"from": "18:00", "to": "07:00"}]}) == {}
    # dimanche 22:00 -> 02:00 finit lundi : le dimanche suivant la semaine ferme sur lundi
    assert hc.jours_de_la_caisse({"sunday": [{"from": "22:00", "to": "02:00"}]}) == {7: [(time(22, 0), hc.FIN_DE_JOURNEE)], 1: [(time(0, 0), time(2, 0))]}


# --------------------------------------------------------------------------- N4 (renvoi : « déjà en caisse » n'est pas un refus)


async def test_renvoi_deja_en_caisse_jamais_refuse():
    """N4 : un POST rejoué après une réponse perdue rend 422 « /private_ref is already used » (07b) : la commande EST en caisse, on la relit par ``private_ref`` (07c) et on la rend ``ENVOYEE`` ; tout autre 422 reste « REFUSEE »."""
    demandes: list[tuple[str, str | None]] = []

    def rendre(requete: httpx.Request) -> httpx.Response:
        demandes.append((requete.method, requete.url.params.get("private_ref")))
        return _rendue("07b-renvoi-second") if requete.method == "POST" else _rendue("07c-renvoi-par-reference")

    commande = {"numero": "mark-19bis-renvoi", "mode": "emporter", "lignes": [{"nom": "Coca-Cola (Test)", "code_caisse": "COCA-33", "prix_unitaire": 250, "quantite": 1}]}
    resultat = await _prise(rendre).faire_envoyer(commande)
    vraie = _f("07c-renvoi-par-reference")["reponse"]["corps"][0]
    assert (resultat.statut, resultat.ref_fournisseur, resultat.etape, resultat.total_caisse) == ("ENVOYEE", vraie["id"], "inconnu", 250)  # « new » n'est pas une étape de la fiche : la commande reste ``envoyee``
    assert demandes == [("POST", None), ("GET", "mark-19bis-renvoi")]

    # un 422 sur un autre champ (04 : « must be positive ») est un vrai refus : jamais relu, jamais « envoyée »
    autres: list[str] = []

    def refus(requete: httpx.Request) -> httpx.Response:
        autres.append(requete.method)
        return _rendue("204-retrait-payant")

    refuse = await _prise(refus).faire_envoyer(commande)
    assert refuse.statut == "REFUSEE" and autres == ["POST"]
