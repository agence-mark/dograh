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
