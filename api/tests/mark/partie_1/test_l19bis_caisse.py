"""[.mark] Chantier Partie 1, lot 19 bis, étape A : la caisse (HubRise), rejouée sur les VRAIES réponses du 20/11 (``reponses_hubrise/19bis/``).

Aucun test n'appelle HubRise : le transport est enregistré (``httpx.MockTransport``) et ne rend que ce que HubRise a rendu en réel.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx

from api.db.bases_clients import connexion as schema
from api.services.restauration import envoi_caisse as ec
from api.services.restauration.annulation_caisse import dire_l_annulation
from api.services.restauration.prises import hubrise_client
from api.services.restauration.prises import hubrise_traduction as ht
from api.services.restauration.prises.hubrise_client import ClientHubrise
from api.services.restauration.prises.prise_hubrise import PriseHubrise
from api.services.restauration.rattrapage import rattrapage_des_envois
from api.services.restauration.statut import changer_le_statut, poser_resolveur_de_prise
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
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
        if requete.method == "POST":
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
    """N4 : un POST rejoué après une réponse perdue rend 422 (07b) : sur tout 422 on relit par ``private_ref`` (07c) ; la commande EST en caisse : ``ENVOYEE``."""
    demandes: list[tuple[str, str | None]] = []

    def rendre(requete: httpx.Request) -> httpx.Response:
        demandes.append((requete.method, requete.url.params.get("private_ref")))
        return _rendue("07b-renvoi-second") if requete.method == "POST" else _rendue("07c-renvoi-par-reference")

    commande = {"numero": "mark-19bis-renvoi", "mode": "emporter", "lignes": [{"nom": "Coca-Cola (Test)", "code_caisse": "COCA-33", "prix_unitaire": 250, "quantite": 1}]}
    resultat = await _prise(rendre).faire_envoyer(commande)
    vraie = _f("07c-renvoi-par-reference")["reponse"]["corps"][0]
    assert (resultat.statut, resultat.ref_fournisseur, resultat.etape, resultat.total_caisse) == ("ENVOYEE", vraie["id"], "inconnu", 250)  # « new » n'est pas une étape de la fiche : la commande reste ``envoyee``
    assert demandes == [("POST", None), ("GET", "mark-19bis-renvoi")]


async def test_vrai_refus_422_reste_refuse():
    """N4 : un 422 qui n'est pas un doublon (montant mal écrit, 16) : la relecture par ``private_ref`` ne trouve rien, la commande reste « REFUSEE »."""
    vues: list[tuple[str, str | None]] = []
    refus = json.loads((DOSSIER.parent / "16-erreur-montant-mal-ecrit.json").read_text(encoding="utf-8"))["reponse"]

    def rendre(requete: httpx.Request) -> httpx.Response:
        vues.append((requete.method, requete.url.params.get("private_ref")))
        return httpx.Response(422, json=refus["corps"]) if requete.method == "POST" else httpx.Response(200, json=[])

    commande = {"numero": "mark-19bis-refus", "mode": "emporter", "lignes": [{"nom": "Coca-Cola (Test)", "code_caisse": "COCA-33", "prix_unitaire": 250, "quantite": 1}]}
    resultat = await _prise(rendre).faire_envoyer(commande)
    assert resultat.statut == "REFUSEE" and vues == [("POST", None), ("GET", "mark-19bis-refus")]


# --------------------------------------------------------------------------- N5 / N2 (retraits à prix, options répétées)


def _reine_sans_jambon(prix_du_retrait: int) -> dict:
    """La Reine à 12,50 € dont le client retire le jambon ; le retrait change le prix de ``prix_du_retrait`` centimes (le prix de la ligne est tout compris)."""
    return {
        "numero": "mark-19bis-s2-retrait", "mode": "emporter", "client": {"telephone": "+33600000001", "prenom": "Camille"}, "total": 1250 + prix_du_retrait,
        "lignes": [
            {
                "code_caisse": "REINE-S", "nom": "Reine (Test)", "prix_unitaire": 1250 + prix_du_retrait, "quantite": 1,
                "choix": [{"option_code": None, "nom": "Sans jambon", "prix": prix_du_retrait, "quantite": 1, "groupe": "Retirer", "retire": True}],
            }
        ],
    }


async def test_retrait_rembourse_part_en_remise():
    """N5 : « Sans jambon -1 € » faisait refuser TOUTE la commande (204 : 422 « must be positive »). Le retrait à prix négatif part en remise (nom du retrait, montant positif) ; la cuisine le lit toujours (retrait à 0 €) ; le total envoyé reste le nôtre. Un retrait à prix POSITIF reste une option ``removed`` à son prix (204b : HubRise l'ajoute)."""
    corps = await _envoyee_par_la_prise(_reine_sans_jambon(-100), "204-retrait-payant")
    assert corps["discounts"] == [{"name": "Sans jambon", "price_off": "1.00 EUR"}]
    options = corps["items"][0]["options"]
    assert options == [{"option_list_name": "Retirer", "name": "Sans jambon", "price": "0.00 EUR", "removed": True}]  # jamais un prix négatif (HubRise refuse), jamais perdu pour la cuisine
    assert _total_des_articles(corps) - sum(ht.centimes(d["price_off"]) for d in corps["discounts"]) == 1150  # le total de la commande : 12,50 - 1,00

    positif = await _envoyee_par_la_prise(_reine_sans_jambon(100), "204b-retrait-prix-positif")
    assert "discounts" not in positif
    accepte = _f("204b-retrait-prix-positif")["demande"]["corps"]["items"][0]  # le corps que HubRise a accepté (200, 13,50 €) : même prix, mêmes options
    assert (positif["items"][0]["price"], positif["items"][0]["options"]) == (accepte["price"], accepte["options"])


async def test_option_repetee_un_objet_par_unite():
    """N2 : une option prise deux fois part en DEUX objets, jamais en un objet à ``quantity`` (le guide d'intégration le préfère ; les deux sont acceptés, 03)."""
    commande = {
        "numero": "n-2", "mode": "emporter",
        "lignes": [{"code_caisse": "REINE-S", "nom": "Reine", "prix_unitaire": 1550, "quantite": 1,
                    "choix": [{"option_code": "SUPP-FROMAGE", "nom": "Supplément fromage", "prix": 150, "quantite": 2, "groupe": "Suppléments"}]}],
    }
    corps = await _envoyee_par_la_prise(commande, "03-menu-options-cree")
    options = corps["items"][0]["options"]
    assert len(options) == 2 and all("quantity" not in o and o["ref"] == "SUPP-FROMAGE" for o in options)
    assert _total_des_articles(corps) == 1550


# --------------------------------------------------------------------------- N1 (on ne suit que nos commandes)


async def test_abonnement_suit_nos_seules_commandes():
    """N1 : l'abonnement demande ``own_order.update`` (accepté seul par HubRise, 06h) et plus ``order.update`` ; ``order.create`` reste pour les commandes créées dans la caisse (M10). Le message reçu (06i) garde la forme que la réception traite."""
    from api.services.restauration.prises import hubrise_liaison as hl
    from api.services.restauration.prises import hubrise_reception as hr

    assert hl.EVENEMENTS["own_order"] == ["update"] and hl.EVENEMENTS["order"] == ["create"]
    posts: list[dict] = []

    def rendre(requete: httpx.Request) -> httpx.Response:
        posts.append(json.loads(requete.content))
        return _rendue("06h-abonnement-own-order-seul")

    class _Connexion:
        async def execute(self, *a, **k):
            return None

    client = ClientHubrise("jeton-de-test", point_de_vente="w8xvp-0", transport=httpx.MockTransport(rendre))
    try:
        await hl.s_abonner(client, _Connexion(), 1)
    except Exception:  # noqa: BLE001 -- la pose de la veille en base n'est pas l'objet du test
        pass
    assert posts and posts[0]["events"]["own_order"] == ["update"] and posts[0]["events"]["order"] == ["create"]
    # le message tel que HubRise le rend (06i), traité comme une mise à jour de commande
    recu = {**_f("06i-messages-own-order-seul")["reponse"]["corps"][0], "location_id": "w8xvp-0"}
    message = hr.lire_le_message(json.dumps(recu).encode())
    assert message is not None and (message["resource_type"], message["event_type"], message["order_id"]) == ("order", "update", "3qk95vg")


# --------------------------------------------------------------------------- K5 (l'annulation perdue est rejouée) et sa migration 048


async def _colonnes_d_annulation(base: str, numero: str) -> dict:
    c = await schema.connecter(base)
    try:
        return dict(await c.fetchrow(
            "SELECT annulation_a_dire_le IS NOT NULL AS a_dire, annulation_essais, annulation_alertee_le IS NOT NULL AS alertee, statut FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)
        ))
    finally:
        await c.close()


async def _vieillir_l_annulation(base: str, numero: str) -> None:
    c = await schema.connecter(base)
    try:
        await c.execute("UPDATE mark.resto_commande SET annulation_essai_le = annulation_essai_le - interval '1 hour', annulation_a_dire_le = annulation_a_dire_le - interval '1 hour' WHERE numero = $1", uuid.UUID(numero))
    finally:
        await c.close()


async def test_annulation_rejouee_quand_la_caisse_revient(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    """K5 : l'annulation faite pendant une panne de la caisse reste « à dire » (au lieu d'être avalée) ; le rattrapage la rejoue quand la caisse revient (PATCH cancelled, rejouable sans risque : 04a, 04b) ; une caisse qui ne connaît pas encore la commande (04h) est réessayée ; au 5e essai raté UNE alerte part."""
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab, statut="envoyee", tentatives=1)
    panne = httpx.MockTransport(lambda r: httpx.Response(503, json={}))
    secours = Secours()

    # 1. la caisse est en panne au moment de l'annulation (par le geste du portail) : l'annulation est gardée
    caisse_en_panne = PriseHubrise(ClientHubrise("jeton-de-test", point_de_vente="w8xvp-0", transport=panne))

    async def resolveur(_org, _etab):
        return caisse_en_panne

    poser_resolveur_de_prise(resolveur)
    c = await schema.connecter(cas.base_a)
    try:
        monnaie = hubrise_client.PAUSES_S
        hubrise_client.PAUSES_S = (0.0, 0.0)
        try:
            resultat, informee = await changer_le_statut(cas.a, c, etab, numero, "envoyee", "annulee")
        finally:
            hubrise_client.PAUSES_S = monnaie
    finally:
        await c.close()
        poser_resolveur_de_prise(None)
    assert resultat.statut == "OK" and informee is False
    assert await _colonnes_d_annulation(cas.base_a, numero) == {"a_dire": True, "annulation_essais": 1, "alertee": False, "statut": "annulee"}

    # 2. la caisse revient : le rattrapage rejoue (la commande est cherchée par notre numéro, puis PATCH cancelled)
    vue: list[tuple[str, str]] = []

    def revenue(requete: httpx.Request) -> httpx.Response:
        vue.append((requete.method, requete.url.path))
        if requete.method == "GET":
            return httpx.Response(200, json=_f("07c-renvoi-par-reference")["reponse"]["corps"])
        return _rendue("04a-annule-depuis-new")

    await rattrapage_des_envois(None, bases=[(cas.a, cas.base_a)], transport=httpx.MockTransport(revenue), secours=secours)
    assert vue == []  # l'essai de 2 minutes n'est pas encore dû : jamais de harcèlement
    await _vieillir_l_annulation(cas.base_a, numero)
    await rattrapage_des_envois(None, bases=[(cas.a, cas.base_a)], transport=httpx.MockTransport(revenue), secours=secours)
    assert [m for m, _ in vue] == ["GET", "PATCH"]
    assert (await _colonnes_d_annulation(cas.base_a, numero))["a_dire"] is False and secours.messages == []
    avant = len(vue)
    await rattrapage_des_envois(None, bases=[(cas.a, cas.base_a)], transport=httpx.MockTransport(revenue), secours=secours)
    assert len(vue) == avant  # dite : plus rejouée

    # 3. une caisse qui ne connaît pas la commande (recherche vide, 404 de 04h) : réessayée, alerte UNE fois au 5e essai
    autre = await _commande(cas.base_a, etab, statut="annulee", tentatives=1)
    c = await schema.connecter(cas.base_a)
    try:
        assert await dire_l_annulation(c, cas.a, etab, PriseHubrise(ClientHubrise("jeton-de-test", point_de_vente="w8xvp-0", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])))), autre, secours=secours) is False
        inconnue = PriseHubrise(ClientHubrise("jeton-de-test", point_de_vente="w8xvp-0", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))))
        for _ in range(ec.TENTATIVES_MAX - 1):
            await _vieillir_l_annulation(cas.base_a, autre)
            await dire_l_annulation(c, cas.a, etab, inconnue, autre, secours=secours)
        await dire_l_annulation(c, cas.a, etab, inconnue, autre, secours=secours)
    finally:
        await c.close()
    assert (await _colonnes_d_annulation(cas.base_a, autre))["alertee"] is True and len(secours.messages) == 1
    assert "annulée" in secours.messages[0][1] and secours.messages[0][0] == cas.a


async def test_migration_048_montee_descente(base_prete):  # noqa: F811
    """Montée, descente, remontée : les colonnes de l'annulation à dire apparaissent et disparaissent."""
    colonnes = ("annulation_a_dire_le", "annulation_essais", "annulation_essai_le", "annulation_alertee_le")

    async def presentes(c) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_commande' AND column_name=$1", x)) for x in colonnes]

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c))
        for _ in range(2):
            await descendre_jusqu_a(c, 48)
            assert not any(await presentes(c)) and 48 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 48 in await schema.appliquer_migrations(c)
            assert all(await presentes(c))
    finally:
        await c.close()



# --------------------------------------------------------------------------- N6 (le motif du refus de la caisse est gardé), sa migration 049


def test_motif_du_refus_lu_sur_la_commande():
    """N6 : le message écrit par la caisse en refusant est dans ``seller_notes`` (210a) ; la lecture le rend, sans motif elle rend ``None`` (208a : une commande acceptée n'en porte pas)."""
    lue = ht.commande_de_hubrise(_f("210a-a-refuser-relue")["reponse"]["corps"])
    assert (lue["etape"], lue["motif_de_la_caisse"]) == ("refusee", "Plus de pate a pizza ce soir, desole")
    assert ht.commande_de_hubrise(_f("01b-poids-relu")["reponse"]["corps"])["motif_de_la_caisse"] is None


async def test_motif_du_refus_de_la_caisse_garde(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    """N6 : la commande refusée dans la caisse (message ``order.update``, relue : ``rejected`` et ``seller_notes``, 210a) garde le motif sur la commande et le joint à l'alerte, UNE fois."""
    from api.tests.mark.test_restauration_caisse_routes import _caisse_enregistree
    from api.tests.mark.test_restauration_hubrise_reception import _commande_envoyee
    from api.tests.mark.test_restauration_hubrise_reception import _etablissement_branche as branche

    pdv = "pdv-n6-" + uuid.uuid4().hex[:6]
    cas, etab = await branche(db_session, seconde_base, pdv)
    numero = await _commande_envoyee(cas.base_a, etab, ref="ev57p9y")
    refusee = {**_f("210a-a-refuser-relue")["reponse"]["corps"], "private_ref": numero}
    caisse = _caisse_enregistree(pdv=pdv, ordres={"ev57p9y": refusee})
    prevenus: list[str] = []

    async def secours(organisation, sujet, texte):
        prevenus.append(texte)

    from api.services.restauration.prises import hubrise_reception as hr

    message = {**_f("06i-messages-own-order-seul")["reponse"]["corps"][0], "order_id": "ev57p9y", "location_id": pdv}
    assert (await hr.traiter_le_message(None, message, transport=caisse, secours=secours))["effet"] == "statut"
    c = await schema.connecter(cas.base_a)
    try:
        assert await c.fetchval("SELECT motif_refus_caisse FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)) == "Plus de pate a pizza ce soir, desole"
    finally:
        await c.close()
    assert len(prevenus) == 1 and "Plus de pate a pizza ce soir, desole" in prevenus[0]


async def test_migration_049_montee_descente(base_prete):  # noqa: F811
    """Montée, descente, remontée : la colonne du motif de refus apparaît et disparaît."""
    async def presente(c) -> bool:
        return bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_commande' AND column_name='motif_refus_caisse'"))

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert await presente(c)
        for _ in range(2):
            await descendre_jusqu_a(c, 49)
            assert not await presente(c) and 49 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 49 in await schema.appliquer_migrations(c)
            assert await presente(c)
    finally:
        await c.close()


# --------------------------------------------------------------------------- K-046 (la descente de la 046 ne valide rien)


async def test_descente_046_ne_valide_rien(base_prete):  # noqa: F811
    """K-046 : après la descente, l'ancien code lit la colonne ``allergenes`` du produit comme VALIDÉE (il ne connaît pas l'état). Un allergène seulement PROPOSÉ (suggestion tirée des ingrédients) doit donc redevenir « inconnu » (NULL), un allergène validé reste."""
    c = await schema.connecter_proprietaire(base_prete)
    try:
        await c.execute(
            "INSERT INTO mark.resto_produit (portee, ref, nom, allergenes, allergenes_etat, allergenes_source) VALUES "
            "('enseigne', 'K046-PROPOSE', 'Tarte', ARRAY['gluten'], 'propose', 'suggestion'), ('enseigne', 'K046-VALIDE', 'Reine', ARRAY['gluten', 'lait'], 'valide', 'restaurateur')"
        )
        await descendre_jusqu_a(c, 46)
        lues = {r["ref"]: r["allergenes"] for r in await c.fetch("SELECT ref, allergenes FROM mark.resto_produit WHERE ref LIKE 'K046-%'")}
        assert lues == {"K046-PROPOSE": None, "K046-VALIDE": ["gluten", "lait"]}
        await descendre_jusqu_a(c, 46)  # rejouable : la colonne n'existe plus, rien ne casse
        assert 46 in await schema.appliquer_migrations(c)
    finally:
        await c.execute("DELETE FROM mark.resto_produit WHERE ref LIKE 'K046-%'")
        await c.close()


# --------------------------------------------------------------------------- K-reinst (réinstaller ne défait pas ce qui a été réglé au portail)


async def test_reinstallation_garde_les_reglages_du_portail(base_prete):  # noqa: F811
    """K-reinst : l'installation rejouée (la même clé) garde les horaires, les zones et ``gratuite_des`` déjà posés, au lieu de les remplacer par ceux du formulaire ; ce que le formulaire ajoute (une zone neuve) entre."""
    from api.db.bases_clients.restauration_formulaire import ecrire_le_formulaire

    premier = {
        "nom_etablissement": "Pizzeria K-reinst", "horaires": {"5": [["11:00", "14:00"]]},
        "zones": [{"nom": "Centre", "minimum": 1500, "frais": 200, "delai": 30, "gratuite_des": 2500, "communes": ["Beauvais"]}],
    }
    c = await schema.connecter_proprietaire(base_prete)
    try:
        site = (await ecrire_le_formulaire(c, "k-reinst", premier, "installation:1"))["etablissement_id"]
        # le restaurateur règle son portail : autres horaires, zone au minimum et à la gratuité changés, une zone ajoutée
        await c.execute("DELETE FROM mark.horaire WHERE site_id = $1", site)
        await c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, 6, '18:00', '23:00')", site)
        await c.execute("UPDATE mark.resto_zone SET minimum = 2000, gratuite_des = 4000 WHERE site_id = $1 AND nom = 'Centre'", site)
        await c.execute("INSERT INTO mark.resto_zone (site_id, nom, forme, communes, minimum, frais, delai) VALUES ($1, 'Portail', 'communes', '{Auneuil}', 0, 0, 0)", site)
        # l'installation est rejouée avec le même formulaire (une zone de plus)
        rejoue = {**premier, "zones": [*premier["zones"], {"nom": "Nord", "minimum": 1000, "frais": 300, "delai": 40, "gratuite_des": 3000, "communes": ["Creil"]}]}
        assert (await ecrire_le_formulaire(c, "k-reinst", rejoue, "installation:1"))["etablissement_id"] == site
        horaires = [(r["jour"], str(r["ouverture"]), str(r["fermeture"])) for r in await c.fetch("SELECT jour, ouverture, fermeture FROM mark.horaire WHERE site_id = $1", site)]
        assert horaires == [(6, "18:00:00", "23:00:00")]
        zones = {r["nom"]: (r["minimum"], r["gratuite_des"]) for r in await c.fetch("SELECT nom, minimum, gratuite_des FROM mark.resto_zone WHERE site_id = $1", site)}
        assert zones == {"Centre": (2000, 4000), "Portail": (0, None), "Nord": (1000, 3000)}
    finally:
        await c.close()


# --------------------------------------------------------------------------- K7 (la fin du service pour ce soir est un instant) et sa migration 050


async def test_fin_du_service_apres_minuit(essai_de):
    """K7 : un restaurant ouvert jusqu'à 2 h. À 22 h, « arrêt à 00 h 30 » ne coupe PAS tout de suite (avant : ``22:00 >= 00:30``) et coupe à 0 h 30 ; « arrêt à 23 h 30 » tient encore à 0 h 01 (avant : la date avait changé, l'agent reprenait jusqu'à 2 h) ; la fin ne compte plus au jour de service suivant (06 h)."""
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    from api.db.bases_clients import horloge
    from api.db.bases_clients import restauration_carte as carte
    from api.db.bases_clients import restauration_temps as temps
    from api.db.bases_clients.connexion import nom_de_la_base
    from api.db.bases_clients.instantane import instantane_de

    paris = ZoneInfo("Europe/Paris")
    e = await essai_de("casa-italia")
    c, site = e.monde.c, e.monde.a
    await c.execute("DELETE FROM mark.horaire WHERE site_id = $1 AND jour IN (5, 6)", site)
    await c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, 5, '11:00', '23:59:59.999999'), ($1, 6, '00:00', '02:00'), ($1, 6, '11:00', '23:59:59.999999')", site)
    await c.execute("UPDATE mark.resto_reglage_type SET fin_par_jour = '{}' WHERE site_id = $1", site)
    base = nom_de_la_base(c)

    async def etat(moment: datetime) -> dict:
        inst = instantane_de(c)
        if inst is not None:
            inst.nouveau_geste()
        return await carte.etat_combine(c, site, "emporter", moment)

    vendredi_22h = datetime(2026, 11, 13, 22, 0, tzinfo=paris)
    with horloge.remplacer(base, vendredi_22h):
        assert (await temps.ecrire_fin_d_aujourd_hui(c, site, "emporter", time(0, 30))).statut == "OK"
    assert (await etat(datetime(2026, 11, 13, 22, 5, tzinfo=paris)))["ouvert"] is True  # avant : fermé tout de suite
    assert (await etat(datetime(2026, 11, 14, 0, 20, tzinfo=paris)))["ouvert"] is True
    coupe = await etat(datetime(2026, 11, 14, 0, 35, tzinfo=paris))
    assert (coupe["ouvert"], coupe["raison"]) == (False, "fin_du_jour"), coupe
    assert (await etat(datetime(2026, 11, 14, 11, 30, tzinfo=paris)))["ouvert"] is True  # le jour de service suivant : effacée seule

    with horloge.remplacer(base, vendredi_22h):
        assert (await temps.ecrire_fin_d_aujourd_hui(c, site, "emporter", time(23, 30))).statut == "OK"
    assert (await etat(datetime(2026, 11, 13, 23, 35, tzinfo=paris)))["raison"] == "fin_du_jour"
    apres_minuit = await etat(datetime(2026, 11, 14, 0, 1, tzinfo=paris))
    assert (apres_minuit["ouvert"], apres_minuit["raison"]) == (False, "fin_du_jour"), apres_minuit  # avant : rouvert à 0 h 01
    assert (await etat(datetime(2026, 11, 14, 1, 30, tzinfo=paris)))["raison"] == "fin_du_jour"


async def test_migration_050_montee_descente(base_prete):  # noqa: F811
    """Montée, descente, remontée : la colonne ``fin_aujourd_hui_a`` apparaît ; les anciennes valeurs (heure + jour) deviennent l'instant, et la descente les restitue."""
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo

    from api.db.bases_clients.restauration_formulaire import ecrire_le_formulaire

    paris = ZoneInfo("Europe/Paris")
    c = await schema.connecter_proprietaire(base_prete)
    try:
        site = (await ecrire_le_formulaire(c, "k7-migration", {"nom_etablissement": "K7", "services": ["emporter"]}, "installation:1"))["etablissement_id"]
        await descendre_jusqu_a(c, 50)
        assert not await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_reglage_type' AND column_name='fin_aujourd_hui_a'")
        await c.execute("UPDATE mark.resto_reglage_type SET fin_aujourd_hui = '00:30', fin_aujourd_hui_le = '2026-11-13' WHERE site_id = $1 AND type = 'emporter'", site)
        assert 50 in await schema.appliquer_migrations(c)
        ligne = await c.fetchrow("SELECT fin_aujourd_hui_a, fin_aujourd_hui, fin_aujourd_hui_le FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'emporter'", site)
        assert ligne["fin_aujourd_hui_a"] == datetime(2026, 11, 14, 0, 30, tzinfo=paris)  # 00 h 30 est la nuit qui suit le 13
        assert (ligne["fin_aujourd_hui"], ligne["fin_aujourd_hui_le"]) == (None, None)
        await c.execute("UPDATE mark.resto_reglage_type SET fin_aujourd_hui_a = $2 WHERE site_id = $1 AND type = 'emporter'", site, datetime(2026, 11, 13, 21, 30, tzinfo=paris))
        await descendre_jusqu_a(c, 50)
        ligne = await c.fetchrow("SELECT fin_aujourd_hui, fin_aujourd_hui_le FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'emporter'", site)
        assert (ligne["fin_aujourd_hui"], ligne["fin_aujourd_hui_le"]) == (time(21, 30), date(2026, 11, 13))
        assert 50 in await schema.appliquer_migrations(c)
    finally:
        await c.close()


# --------------------------------------------------------------------------- gardes déjà en place (HubRise ne les fait pas : 203, 206a, 212b, 213a), confirmées par un test


async def test_gardes_de_la_caisse_deja_en_place(essai_de):
    """HubRise accepte une heure passée (203), une quantité 0 (206a), une commande pendant la pause (212b) et un produit en rupture (213a) : c'est NOTRE code qui les refuse, avant tout envoi."""
    from datetime import timedelta

    from api.db.bases_clients import restauration_commande as RC
    from api.db.bases_clients.restauration_commun import maintenant

    e = await essai_de("casa-italia")
    c, site = e.monde.c, e.monde.a
    code = "BOI-COCA-COLA-33-CL"
    ligne = [{"code_caisse": code, "quantite": 1, "choix": []}]
    chiffre = await RC.chiffrer_panier(c, site, "emporter", ligne)
    assert chiffre.statut == "OK"  # le cas de référence : la commande passe

    # quantité 0 (206a) : refusée avant d'être chiffrée, donc jamais envoyée
    zero = await RC.chiffrer_panier(c, site, "emporter", [{**ligne[0], "quantite": 0}])
    assert (zero.statut, zero.manque) == ("ARGUMENT_INVALIDE", "quantite")

    # heure voulue passée (203) : refusée à l'enregistrement
    brouillon = {"mode": "emporter", "client": {"telephone": "+33612345678"}, "lignes": ligne, "appel_id": "appel-1",
                 "paiement": {"moyens": [{"moyen": "carte", "montant": chiffre.faits["total"]}]}}
    passee = await RC.enregistrer_commande(c, site, {**brouillon, "heure_voulue": (await maintenant(c)) - timedelta(hours=1)}, "relu")
    assert (passee.statut, passee.manque) == ("ARGUMENT_INVALIDE", "heure_voulue")

    # produit en rupture (213a) : refusé à l'enregistrement (qui relit les ruptures posées pendant l'appel)
    from api.db.bases_clients.instantane import instantane_de

    inst = instantane_de(c)
    prise = await RC.enregistrer_commande(c, site, brouillon, "relu")
    assert prise.statut == "ENREGISTREE", (prise.statut, prise.faits, prise.manque)  # sans rupture : la commande est prise
    await c.execute("INSERT INTO mark.resto_rupture (site_id, code_caisse, disponible, debut) VALUES ($1, $2, false, $3)", site, code, (await maintenant(c)) - timedelta(hours=1))
    assert (await RC.enregistrer_commande(c, site, {**brouillon, "appel_id": "appel-2"}, "relu-2")).statut == "RUPTURE"
    await c.execute("DELETE FROM mark.resto_rupture WHERE site_id = $1 AND code_caisse = $2", site, code)

    # restaurant en pause (212b) : l'enregistrement est refusé (le moment même)
    await c.execute("UPDATE mark.site SET etat_force = 'PAUSE', etat_force_jusqu_a = NULL WHERE id = $1", site)
    if inst is not None:
        inst.nouveau_geste()
    en_pause = await RC.enregistrer_commande(c, site, {**brouillon, "appel_id": "appel-3"}, "relu-3")
    assert en_pause.statut in ("PAUSE_TYPE", "FERME"), en_pause
