"""[.mark] Chantier Partie 1, lot 16 : la caisse HubRise.

Rendu de monnaie et consigne pour le livreur transmis ; le règlement dit au téléphone n'est jamais un paiement reçu (note de Pierre, Evan le 20/11) ; allergènes lus depuis la caisse
(26 valeurs HubRise ramenées aux 14) et émis par la caisse de démo (D22) ; « Vérifier depuis ma caisse » qui n'écrit rien ; une erreur de notre code n'est pas une panne de la caisse ;
la commande restée « nouvelle » cinq minutes pendant les heures d'ouverture alerte ; l'heure de la caisse ; les retraits de la démo ; « enregistrée », jamais « transmise » ; l'aller-retour
sur les quatre cartes de démo, formules et frais compris. Aucun appel à HubRise : des réponses enregistrées d'après la documentation officielle (``reponses_hubrise/``).
Un test = un essai à la fois.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.services.restauration.caisse.prises import hubrise_traduction as ht
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a, oui_au_numero_dicte
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import _corps, application_configuree  # noqa: F401
from api.tests.mark.test_restauration_envoi_caisse import (
    CaisseQuiRegistre,
    Secours,
    _commande,
    _etablissement_branche,
    _etat,
)

PARIS = ZoneInfo("Europe/Paris")


def _commande_du_format_commun(**plus) -> dict:
    """Une commande du format commun, comme la couche d'accès la rend à la prise (``commande_complete``)."""
    return {"numero": "n-1", "mode": "emporter", "client": {"telephone": "+33600000001", "prenom": "Léa"}, "total": 1250, "frais": 0,
            "lignes": [{"nom": "Reine", "code_caisse": "REINE-S", "quantite": 1, "prix_unitaire": 1250, "choix": []}], **plus}


# --------------------------------------------------------------------------- #
# La migration 047 (cause d'échec, consigne, heures)
# --------------------------------------------------------------------------- #


async def test_migration_047_montee_descente(base_prete):
    """Montée, descente, remontée : les colonnes du lot 16 apparaissent et disparaissent ; le seuil d'alerte par défaut est de cinq minutes."""
    colonnes = ("cause_echec", "consigne_livreur", "envoyee_le", "acceptee_le", "alerte_nouvelle_le")

    async def presentes(c) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_commande' AND column_name=$1", x)) for x in colonnes]

    async def seuil(c) -> str:
        return await c.fetchval("SELECT column_default FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_liaison' AND column_name='alerte_sans_reponse_min'")

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c)) and await seuil(c) == "5"
        for _ in range(2):
            await descendre_jusqu_a(c, 47)
            assert not any(await presentes(c)) and await seuil(c) == "3" and 47 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 47 in await schema.appliquer_migrations(c)
            assert all(await presentes(c)) and await seuil(c) == "5"
    finally:
        await c.close()


# --------------------------------------------------------------------------- #
# Le règlement, le rendu de monnaie, la consigne
# --------------------------------------------------------------------------- #


def test_rendu_de_monnaie_transmis():
    """Le billet et la monnaie arrivent à la caisse : la documentation HubRise n'a pas de champ pour le rendu, il part dans ``customer.delivery_notes`` ; la commande ne porte AUCUN paiement."""
    corps = ht.commande_vers_hubrise(_commande_du_format_commun(paiement={"moyens": [{"moyen": "especes", "montant": 1250}], "rendu_sur": 2000}))
    note = corps["customer"]["delivery_notes"]
    assert "Espèces 12.50 EUR" in note and "rendre la monnaie sur 20.00 EUR" in note, note


def test_paiement_au_comptoir_n_est_pas_un_paiement_recu():
    """Documentation HubRise (orders) : « If payments are omitted, the order should be considered as unpaid. » ; avec des paiements, leur somme doit valoir le total. Le moyen dit au téléphone
    (espèces, carte, titre-restaurant) est une INFORMATION pour la caisse (``delivery_notes``), jamais un paiement reçu : aucun ``payments`` n'est envoyé ; un règlement marqué REÇU, lui, part."""
    for moyen in ("especes", "carte", "titre_restaurant", "carte_livraison"):
        corps = ht.commande_vers_hubrise(_commande_du_format_commun(paiement={"moyens": [{"moyen": moyen, "montant": 1250}], "rendu_sur": None}))
        assert "payments" not in corps, (moyen, corps)
        assert ht.LIBELLE_MOYEN[moyen] in corps["customer"]["delivery_notes"]
    recu = ht.commande_vers_hubrise(_commande_du_format_commun(paiement={"moyens": [{"moyen": "carte", "montant": 1250, "recu": True}], "rendu_sur": None}))
    assert recu["payments"] == [{"name": "Carte bancaire", "ref": "carte", "amount": "12.50 EUR"}] and "delivery_notes" not in recu["customer"]


def test_consigne_dans_delivery_notes():
    """« code 1234 » arrive au livreur dans ``customer.delivery_notes`` ; la note de la commande, sans la consigne déjà dite, dans ``customer_notes`` ; une note sans consigne reste entière."""
    corps = ht.commande_vers_hubrise(_commande_du_format_commun(consigne_livreur="code 1234", note="bien cuite ; livreur : code 1234"))
    assert corps["customer"]["delivery_notes"] == "code 1234" and corps["customer_notes"] == "bien cuite"
    seul = ht.commande_vers_hubrise(_commande_du_format_commun(consigne_livreur="code 1234", note="Pour le livreur : code 1234"))
    assert "customer_notes" not in seul and seul["customer"]["delivery_notes"] == "code 1234"
    assert ht.commande_vers_hubrise(_commande_du_format_commun(note="bien cuite"))["customer_notes"] == "bien cuite"


async def test_consigne_enregistree_avec_la_commande(essai_de):
    """La consigne pour le livreur de CETTE commande est gardée à part (``resto_commande.consigne_livreur``) et rendue à la prise par ``commande_complete`` ; « aucune » n'en est pas une."""
    from api.db.bases_clients import restauration_commande as RC
    from api.services.commande import moteur

    assert moteur._consigne_du_livreur({"consigne_livreur": "code 1234"}) == "code 1234"
    assert moteur._consigne_du_livreur({"consigne_livreur": "aucune"}) is None
    assert moteur._consigne_du_livreur({moteur.CLE_NOTES_DU_GREFFIER: {"consigne_livreur": "sonner au 2e"}}) == "sonner au 2e"
    e = await essai_de("casa-italia")
    numero = uuid.uuid4()
    await e.monde.c.execute("INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut, telephone, consigne_livreur) VALUES ($1, 'C1', $2, 'livraison', 1250, 'nouvelle', '+33600000001', 'code 1234')", numero, e.monde.a)
    assert (await RC.commande_complete(e.monde.c, e.monde.a, numero))["consigne_livreur"] == "code 1234"


# --------------------------------------------------------------------------- #
# Les allergènes : lus depuis la caisse, émis par la caisse de démo
# --------------------------------------------------------------------------- #


def test_table_26_valeurs_hubrise_vers_14():
    """Les 26 valeurs de ``nutrition.allergens`` (documentation HubRise) sont toutes ramenées à l'un des 14 codes, et chacun des 14 est atteint."""
    from api.services.restauration.carte_et_allergenes.allergenes_suggeres import table_inco
    from api.services.restauration.carte_et_allergenes.signalements import LES_QUATORZE

    valeurs = table_inco()["hubrise"]["valeurs"]
    assert len(valeurs) == 26 and set(valeurs.values()) == set(LES_QUATORZE)


def test_allergenes_lus_depuis_la_caisse():
    """Le catalogue enregistré (d'après la documentation) : les 26 valeurs ramenées aux 14 (gluten_wheat → gluten, nuts_walnut → fruits à coque), ``[]`` reste « aucun », une donnée omise ou
    ``null`` reste INCONNUE, une valeur inconnue de nous rend l'ensemble inconnu (jamais un « aucun » deviné) ; les options aussi ; ingrédients et valeurs nutritionnelles repris."""
    carte = ht.carte_de_hubrise(_corps("25-catalogue-avec-nutrition.json")).carte
    par_id = {p["id"]: p for p in carte["produits"]}
    assert par_id["P-PIZZA"]["allergenes"] == ["gluten", "lait", "fruits_a_coque"] and [i["nom"] for i in par_id["P-PIZZA"]["ingredients"]] == ["farine", "fromage", "jambon"]
    assert par_id["P-PIZZA"]["nutrition"]["per_100_values"]["energy"] == {"unit": "kcal", "lower": 260}
    assert par_id["P-SALADE"]["allergenes"] == []
    assert par_id["P-TARTE"]["allergenes"] is None and par_id["P-NOUVEAU"]["allergenes"] is None
    options = {o["id"].split("-", 1)[-1]: o for g in carte["groupes"] for o in g["options"]}
    assert options["O-MOUTARDE"]["allergenes"] == ["moutarde", "oeufs"] and options["O-NATURE"]["allergenes"] == [] and "allergenes" not in options["O-MAISON"]


async def test_allergenes_de_la_caisse_valides_en_base(essai_de):
    """Importés depuis la caisse, les allergènes sont ``valide`` / source ``caisse`` (D22) ; ``null`` et ``[]`` restent distincts en base."""
    from api.db.bases_clients.restauration_carte import importer_carte

    e = await essai_de("briques/INF1")
    carte = ht.carte_de_hubrise(_corps("25-catalogue-avec-nutrition.json")).carte
    carte["etablissement"] = {}
    await importer_carte(e.monde.c, e.monde.a, carte, "caisse")
    lignes = {r["ref"]: r for r in await e.monde.c.fetch("SELECT ref, allergenes, allergenes_etat, allergenes_source FROM mark.resto_produit WHERE site_id = $1 AND ref LIKE 'P-%'", e.monde.a)}
    assert (list(lignes["P-PIZZA"]["allergenes"]), lignes["P-PIZZA"]["allergenes_etat"], lignes["P-PIZZA"]["allergenes_source"]) == (["gluten", "lait", "fruits_a_coque"], "valide", "caisse")
    assert list(lignes["P-SALADE"]["allergenes"]) == [] and lignes["P-SALADE"]["allergenes_source"] == "caisse"
    assert lignes["P-TARTE"]["allergenes"] is None


def test_caisse_demo_emet_les_allergenes():
    """La caisse de démo n'émet plus ``nutrition: None`` : les allergènes (dans les valeurs HubRise), les ingrédients, pour les articles et les options ; ``null`` n'est jamais écrit, ``[]`` oui ;
    relue par la même traduction, la carte retrouve les mêmes quatorze codes."""
    from api.services.restauration.caisse.caisse_demo import catalogue as demo
    from api.tests.mark.banc_a.commun import carte_de

    commune = carte_de("briques/INF2")
    commune["produits"][0]["allergenes"] = ["gluten", "lait"]
    commune["produits"][0]["ingredients"] = [{"nom": "poulet", "retirable": False}]
    lecture = demo.en_lecture(ht.carte_vers_hubrise(commune).donnees)
    tacos = next(p for p in lecture["products"] if p["ref"] == "P-TACOS")
    assert tacos["nutrition"] == {"allergens": ["gluten_wheat", "milk"], "ingredients": ["poulet"]}
    sauces = {o["ref"]: o["nutrition"] for liste in lecture["option_lists"] for o in liste["options"]}
    assert sauces["G-SAUCE-ALGERIENNE"] == {"allergens": ["mustard", "eggs"]} and sauces["G-SAUCE-KETCHUP"] == {"allergens": []} and sauces["G-SAUCE-MAISON"] is None
    relue = ht.carte_de_hubrise({"data": lecture}).carte
    assert next(p for p in relue["produits"] if p["id"] == "P-TACOS")["allergenes"] == ["gluten", "lait"]


async def test_verifier_depuis_ma_caisse_n_ecrase_rien(essai_de):
    """« Vérifier depuis ma caisse » : les écarts sont rendus (différent, la caisse seule le dit, ici seulement), avec ce que les ingrédients suggèrent ; AUCUNE valeur ni journal ne change."""
    from api.db.bases_clients import restauration_allergenes as A
    from api.services.restauration.carte_et_allergenes.allergenes_suggeres import (
        ecarts_caisse_et_suggestion,
        objets_a_comparer,
    )
    from api.tests.mark.banc_a.commun import carte_de

    e = await essai_de("briques/INF1")
    caisse = carte_de("briques/INF1")
    for p in caisse["produits"]:
        p["allergenes"] = {"P-REINE": ["gluten"], "P-SALADE": [], "P-TARTE": ["lait"]}[p["id"]]
    caisse["produits"][1]["allergenes"] = None  # la caisse ne dit rien de la salade
    avant = [tuple(r) for r in await e.monde.c.fetch("SELECT ref, allergenes, allergenes_etat, allergenes_source FROM mark.resto_produit WHERE site_id = $1 ORDER BY ref", e.monde.a)]
    journal = await e.monde.c.fetchval("SELECT count(*) FROM mark.resto_journal WHERE site_id = $1", e.monde.a)
    ecarts = ecarts_caisse_et_suggestion(await A.allergenes_en_place(e.monde.c, e.monde.a), objets_a_comparer(caisse))
    par_ref = {x["ref"]: x for x in ecarts}
    assert par_ref["P-REINE"]["nature"] == "different" and par_ref["P-REINE"]["ici"] == ["gluten", "lait"] and par_ref["P-REINE"]["caisse"] == ["gluten"]
    assert par_ref["P-SALADE"]["nature"] == "ici_seulement" and par_ref["P-TARTE"]["nature"] == "caisse_seule" and par_ref["P-TARTE"]["caisse"] == ["lait"]
    assert par_ref["P-REINE"]["suggestion"] == ["lait"]  # le fromage (jambon et champignons ne proposent rien)
    assert [tuple(r) for r in await e.monde.c.fetch("SELECT ref, allergenes, allergenes_etat, allergenes_source FROM mark.resto_produit WHERE site_id = $1 ORDER BY ref", e.monde.a)] == avant
    assert await e.monde.c.fetchval("SELECT count(*) FROM mark.resto_journal WHERE site_id = $1", e.monde.a) == journal


async def test_verifier_depuis_ma_caisse_autre_organisation_refusee(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    """La route : l'établissement d'une autre organisation (ou inconnu) est un 404 ; chez soi sans caisse lisible, 409 ; une clé d'API n'écrit pas (403) ; rien n'est écrit (D59)."""
    from api.tests.mark.equipe_commun import client_http
    from api.tests.mark.test_contacts_portail import _cle
    from api.tests.mark.test_restauration_ecran_routes import RACINE, _cas

    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    c_b = await schema.connecter(cas.base_b)
    try:
        chez_b = await c_b.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'trois', 'trois', 'Europe/Paris' FROM mark.entreprise LIMIT 1 RETURNING id")
    finally:
        await c_b.close()
    url = "allergenes/verifier-depuis-la-caisse"
    async with client_http() as c:
        for cible in (chez_b, max(cas.sites_a + cas.sites_b) + 1000):
            assert (await c.post(f"{RACINE}/etablissements/{cible}/{url}", headers=cas.session)).status_code == 404
        assert (await c.post(f"{RACINE}/etablissements/{etab}/{url}", headers=cas.session)).status_code == 409  # aucune caisse lisible n'est branchée
        assert (await c.post(f"{RACINE}/etablissements/{etab}/{url}", headers=_cle(cas.cle_a))).status_code == 403
    for base in (cas.base_a, cas.base_b):
        assert not await _lignes(base, "SELECT 1 FROM mark.resto_surcouche")


async def _lignes(base: str, requete: str, *args):
    c = await schema.connecter(base)
    try:
        return await c.fetch(requete, *args)
    finally:
        await c.close()


# --------------------------------------------------------------------------- #
# Une erreur de notre code n'est pas une panne ; l'alerte « restée nouvelle »
# --------------------------------------------------------------------------- #


async def test_erreur_de_code_n_est_pas_une_panne(db_session, seconde_base, sans_preparation_des_organisations, application_configuree, monkeypatch):  # noqa: F811
    """L'``AttributeError`` d'avant ``da009c9f`` rejoué : la traduction lève, la commande passe tout de suite en ``echec`` (cause ``code``), aucune nouvelle tentative, l'alerte part tout de suite
    et dit que c'est .mark, pas la caisse."""
    from api.services.restauration.caisse import envoi_caisse as ec

    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)

    def casse(_commande, **_plus):
        raise AttributeError("'NoneType' object has no attribute 'get'")

    monkeypatch.setattr(ht, "commande_vers_hubrise", casse)
    caisse, secours = CaisseQuiRegistre(), Secours()
    issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert issue.issue == "echec_code" and caisse.posts() == 0
    etat = await _lignes(cas.base_a, "SELECT statut, cause_echec, tentatives FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero))
    assert (etat[0]["statut"], etat[0]["cause_echec"]) == ("echec", "code") and etat[0]["tentatives"] == 1
    assert len(secours.messages) == 1 and "erreur de .mark" in secours.messages[0][2], secours.messages
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)  # rien de plus : pas de nouvel essai, pas de seconde alerte
    assert caisse.posts() == 0 and len(secours.messages) == 1


async def test_panne_cinq_essais_puis_alerte(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    """La règle saine gardée (vert attendu) : une vraie panne de la caisse (503) est reprise, et au cinquième essai raté la commande passe en ``echec`` (cause ``caisse``) avec l'alerte."""
    from api.services.restauration.caisse import envoi_caisse as ec

    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab, statut="envoyee", tentatives=ec.TENTATIVES_MAX - 1)
    caisse, secours = CaisseQuiRegistre(mode="panne"), Secours()
    issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert issue.issue == "a_reprendre"
    etat = await _lignes(cas.base_a, "SELECT statut, cause_echec FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero))
    assert (etat[0]["statut"], etat[0]["cause_echec"]) == ("echec", "caisse") and len(secours.messages) == 1


async def test_commande_restee_nouvelle_cinq_minutes_alerte(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    """Note de Pierre (Evan, 20/11) : une commande ARRIVÉE à la caisse mais encore ``envoyee`` (``new`` chez HubRise) cinq minutes après l'envoi, pendant les heures d'ouverture, alerte par
    l'échelle de secours existante, UNE seule fois ; l'heure de l'alerte et celle de l'acceptation sont gardées. Fermé : rien. Temps simulé, jamais l'heure réelle."""
    from api.db.bases_clients import restauration
    from api.services.restauration.caisse import rattrapage as rat

    cas, etab = await _etablissement_branche(db_session, seconde_base)
    c = await schema.connecter(cas.base_a)
    try:
        for jour in range(1, 8):
            await c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, '11:00'::text::time, '14:00'::text::time)", etab, jour)
        numero = await _commande(cas.base_a, etab, statut="envoyee")
        await c.execute("UPDATE mark.resto_commande SET ref_fournisseur = 'caisse-1' WHERE numero = $1", uuid.UUID(numero))
        envoi = datetime(2026, 11, 12, 12, 0, tzinfo=PARIS)  # un jeudi à midi, ouvert
        secours = Secours()

        async def passer(moment: datetime) -> int:
            with horloge.remplacer(cas.base_a, moment):
                return (await rat.alerte_des_commandes_sans_reponse(None, bases=[(cas.a, cas.base_a)], secours=secours))[str(cas.a)]

        with horloge.remplacer(cas.base_a, envoi):
            await c.execute("UPDATE mark.resto_commande SET envoyee_le = $2 WHERE numero = $1", uuid.UUID(numero), envoi)
        assert await c.fetchval("SELECT alerte_sans_reponse_min FROM mark.resto_liaison WHERE site_id = $1", etab) == 5
        assert await passer(envoi + timedelta(minutes=4)) == 0 and not secours.messages  # quatre minutes : trop tôt
        assert await passer(envoi + timedelta(minutes=5, seconds=10)) == 1 and len(secours.messages) == 1  # cinq minutes : l'alerte
        assert await passer(envoi + timedelta(minutes=9)) == 0 and len(secours.messages) == 1  # rejouée : sans effet double
        alerte = await c.fetchval("SELECT alerte_nouvelle_le FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero))
        assert alerte is not None and alerte == envoi + timedelta(minutes=5, seconds=10)
        # l'acceptation par la caisse : son heure est gardée
        with horloge.remplacer(cas.base_a, envoi + timedelta(minutes=12)):
            assert (await restauration.changer_statut(c, etab, numero, "envoyee", "acceptee", "caisse")).statut == "OK"
        assert await c.fetchval("SELECT acceptee_le FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)) == envoi + timedelta(minutes=12)
        # fermé (trois heures du matin) : une commande envoyée la veille au soir et restée nouvelle n'alerte pas
        autre = await _commande(cas.base_a, etab, statut="envoyee")
        nuit = datetime(2026, 11, 13, 3, 0, tzinfo=PARIS)
        await c.execute("UPDATE mark.resto_commande SET ref_fournisseur = 'caisse-2', envoyee_le = $2 WHERE numero = $1", uuid.UUID(autre), nuit - timedelta(hours=1))
        assert await passer(nuit) == 0 and len(secours.messages) == 1
    finally:
        await c.close()
    assert autre


# --------------------------------------------------------------------------- #
# L'heure de la caisse, les retraits de la démo
# --------------------------------------------------------------------------- #


def test_heure_de_la_caisse_seulement_si_changee():
    """``expected_time`` est NOTRE heure, renvoyée telle quelle : elle n'est jamais lue comme « l'heure de la caisse » ; seule ``confirmed_time`` (posée par la caisse) l'est."""
    ordre = {**_corps("12-commande-simple.json"), "expected_time": "2026-11-12T19:30:00+01:00", "confirmed_time": None}
    assert ht.commande_de_hubrise(ordre)["heure_confirmee"] is None
    change = ht.commande_de_hubrise({**ordre, "confirmed_time": "2026-11-12T19:50:00+01:00"})
    assert change["heure_confirmee"] == datetime.fromisoformat("2026-11-12T19:50:00+01:00")


async def test_heure_de_la_caisse_posee_seulement_si_la_caisse_l_a_changee(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    """De bout en bout : une caisse qui renvoie notre heure ne change pas l'heure annoncée ; une caisse qui la confirme autrement la change (et l'appelant est prévenu par le flux)."""
    from api.services.restauration.caisse import envoi_caisse as ec

    cas, etab = await _etablissement_branche(db_session, seconde_base)
    nous = datetime(2026, 11, 12, 19, 30, tzinfo=PARIS)

    def caisse_qui(confirmee: str | None) -> httpx.MockTransport:
        def repondre(r: httpx.Request) -> httpx.Response:
            if r.url.path == "/v1/location/orders" and r.method == "POST":
                corps = json.loads(r.content)
                return httpx.Response(200, json={**_corps("12-commande-simple.json"), "id": "caisse-" + corps["private_ref"][:8], "private_ref": corps["private_ref"], "status": "new",
                                                 "expected_time": (nous - timedelta(minutes=15)).isoformat(), "confirmed_time": confirmee})  # NOTRE heure voulue, renvoyée telle quelle
            return httpx.Response(404, json={})

        return httpx.MockTransport(repondre)

    for confirmee, attendue in ((None, nous), ("2026-11-12T19:50:00+01:00", datetime.fromisoformat("2026-11-12T19:50:00+01:00"))):
        numero = await _commande(cas.base_a, etab)
        await _lignes(cas.base_a, "UPDATE mark.resto_commande SET heure_annoncee = $2 WHERE numero = $1 RETURNING 1", uuid.UUID(numero), nous)
        await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse_qui(confirmee), secours=Secours())
        assert (await _lignes(cas.base_a, "SELECT heure_annoncee FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)))[0]["heure_annoncee"] == attendue


def test_retrait_lisible_dans_la_demo():
    """« Sans champignons » est un retrait (``removed``) : la lecture de la caisse de démo le range à part, jamais parmi les ajouts."""
    from api.routes.restauration_caisse_demo import _commande_rendue

    corps = {"service_type": "collection", "total": "12.50 EUR", "customer": {"delivery_notes": "code 1234"}, "items": [{
        "product_name": "Reine", "sku_name": "Normale", "quantity": "1.0", "subtotal": "12.50 EUR",
        "options": [{"name": "Olives", "price": "1.00 EUR"}, {"name": "Champignons", "price": "0.00 EUR", "removed": True}]}]}
    rendue = _commande_rendue({"ref": "r", "private_ref": "n-1", "statut": "new", "corps": corps, "cree_le": datetime(2026, 11, 12, 12, 0, tzinfo=PARIS)})
    ligne = rendue["lignes"][0]
    assert ligne["options"] == ["Olives"] and ligne["retires"] == ["Champignons"] and rendue["client"]["consigne_livraison"] == "code 1234"


# --------------------------------------------------------------------------- #
# « Enregistrée », jamais « transmise » ; l'envoi hors du tour ; l'aller-retour ; les frais
# --------------------------------------------------------------------------- #


async def test_jamais_transmise_avant_le_retour(essai_de):
    """La confirmation dit « enregistrée » (la caisse n'a encore rien répondu) et jamais « transmise » ni « en cuisine » ; vert attendu : déjà tenu par la phrase de l'enregistrement."""
    from api.tests.mark.partie_1.aides_briques import brique

    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    for _ in range(3):
        q = e.p.get("question") or {}
        if q.get("type") == "relecture":
            break
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = e.p["question"]
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    if not e.p.get("enregistree"):
        await e.tour("zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
    if not e.p.get("enregistree"):
        await e.tour("Léa", prenom="Léa")
    await oui_au_numero_dicte(e)
    assert e.p.get("enregistree")
    dite = json.dumps(e.retours[-1], ensure_ascii=False, default=str).casefold() + json.dumps(e.fiche_de_l_appel.get("textes_du_code") or {}, ensure_ascii=False).casefold()
    assert "enregistrée" in dite or "enregistree" in dite
    assert "transmis" not in dite.replace("transmise_a_l_equipe", "") and "en cuisine" not in dite


async def test_envoi_hors_du_tour(db_session, seconde_base, sans_preparation_des_organisations, application_configuree, monkeypatch):  # noqa: F811
    """L'existant, réutilisé tel quel (D61, point 5) : ``lancer_l_envoi`` rend la main AVANT l'envoi (tâche de fond) ; une commande que la caisse a déjà (la réponse s'est perdue) est reconnue
    par NOTRE numéro (``private_ref``) : jamais deux commandes."""
    from api.services.restauration.caisse import envoi_caisse as ec
    from api.services.restauration import source_commande as sc

    cas, etab = await _etablissement_branche(db_session, seconde_base)
    libere, fini = asyncio.Event(), asyncio.Event()

    async def envoi_lent(*_a):
        await libere.wait()
        fini.set()

    monkeypatch.setattr(sc, "_envoyer_en_fond", envoi_lent)
    sc.lancer_l_envoi(cas.base_a, etab, "hubrise", uuid.uuid4())
    assert not fini.is_set()  # l'enregistrement a rendu la main, l'envoi n'a pas eu lieu
    libere.set()
    await asyncio.wait_for(fini.wait(), 5)
    numero = await _commande(cas.base_a, etab)
    caisse, secours = CaisseQuiRegistre(mode="perd_la_reponse"), Secours()
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)  # la caisse l'a, la réponse est perdue
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)  # le renvoi cherche d'abord par notre numéro
    assert caisse.posts() == 1 and list(caisse.recues) == [numero]
    assert (await _etat(cas.base_a, numero))["ref_fournisseur"] == "caisse-" + numero[:8]


SLUGS = ["casa-italia", "etoile-d-or", "kebab-demo", "lusitalia"]


@pytest.mark.parametrize("slug", SLUGS)
async def test_aller_retour_quatre_cartes(slug, essai_de):
    """Catalogue de la carte → commande en livraison (frais de la zone non nuls) → corps ``POST /location/orders`` → lecture de la caisse de démo : la caisse recalcule NOTRE total au centime,
    sur les quatre cartes de démo, un article simple et une formule (quand la carte en a) compris."""
    from api.db.bases_clients import restauration_commande as RC
    from api.services.restauration.caisse.caisse_demo import moteur as demo
    from api.tests.mark.banc_a.commun import carte_de

    e = await essai_de(slug)
    carte = carte_de(slug)
    simple = next(p for p in carte["produits"] if len(p["declinaisons"]) == 1 and p["declinaisons"][0].get("code_caisse") and not p.get("groupes"))
    lignes = [{"code_caisse": simple["declinaisons"][0]["code_caisse"], "quantite": 2, "choix": []}]
    formule = next((f for f in carte.get("formules") or [] if f.get("code_caisse")), None)
    await e.monde.c.execute("UPDATE mark.resto_zone SET frais = 300 WHERE site_id = $1", e.monde.a)  # les zones des cartes de démo sont gratuites : des frais non nuls n'avaient jamais été joués
    zone = await e.monde.c.fetchrow("SELECT id, frais FROM mark.resto_zone WHERE site_id = $1 ORDER BY id LIMIT 1", e.monde.a)
    assert zone["frais"] == 300
    r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "livraison", lignes, zone["id"])
    assert r.statut == "OK" and r.faits["frais"] == zone["frais"], r
    adresse = {"voie": "1 rue de la Paix", "code_postal": "60000", "commune": "Beauvais"}
    corps = ht.commande_vers_hubrise({"numero": "n-1", "mode": "livraison", "client": {"telephone": "+33600000001"}, "adresse": adresse, "lignes": r.faits["lignes"], "remises": r.faits["remises"],
                                      "frais": r.faits["frais"], "paiement": {"moyens": [{"moyen": "carte_livraison", "montant": r.faits["total"]}], "rendu_sur": None}})
    assert corps["charges"] == [{"name": "Livraison", "price": ht.euros(zone["frais"])}] and "payments" not in corps
    calcul = demo._calculer(corps)
    assert calcul["total"] == r.faits["total"] and calcul["ecart"] == r.faits["total"], (slug, calcul, r.faits["total"])  # la caisse recalcule notre total ; rien n'est « payé »
    if formule is not None:
        rf = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": formule["code_caisse"], "quantite": 1, "choix": []}])
        if rf.statut == "OK":  # une formule dont les choix sont obligatoires n'est pas chiffrée sans eux : la règle est celle du lot 11
            corps_f = ht.commande_vers_hubrise({"numero": "n-2", "mode": "emporter", "client": {}, "lignes": rf.faits["lignes"], "remises": rf.faits["remises"]})
            assert demo._calculer(corps_f)["total"] == rf.faits["total"], (slug, "formule")


async def test_frais_jamais_doubles(essai_de):
    """Vérification (vert attendu) : les frais de livraison que la caisse de démo porte dans son catalogue ne s'ajoutent JAMAIS à ceux de la zone dans une commande : un seul poste ``charges``."""
    from api.services.restauration.caisse.caisse_demo import catalogue as demo_catalogue
    from api.services.restauration.caisse.caisse_demo import moteur as demo
    from api.tests.mark.banc_a.commun import carte_de

    carte = carte_de("casa-italia")
    lu = demo_catalogue.catalogue_de_lecture(catalogue_id="c", compte_id="a", nom="n", carte=carte, remises=[], cree_le=datetime(2026, 11, 12, tzinfo=PARIS),
                                             frais=[{"ref": "LIV-CAISSE", "name": "Livraison caisse", "price": "3.00 EUR"}])
    assert [f["ref"] for f in lu["data"]["charges"]] == ["LIV-CAISSE"]  # le catalogue de la caisse a son poste à lui
    corps = ht.commande_vers_hubrise(_commande_du_format_commun(mode="livraison", frais=300, adresse={"voie": "1 rue", "code_postal": "60000", "commune": "Beauvais"}, total=1550))
    assert corps["charges"] == [{"name": "Livraison", "price": "3.00 EUR"}]
    assert demo._calculer(corps)["total"] == 1550  # 12,50 + 3,00 de la zone, rien de plus
