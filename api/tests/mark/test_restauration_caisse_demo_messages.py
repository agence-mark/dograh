"""[.mark] Module Restauration, lot 20, étape 3 : les messages signés de la caisse de démo, leur rejeu et ses comportements.

La réception est un transport ENREGISTRÉ (jamais le réseau). La signature est vérifiée par la fonction même de la réception (``hubrise_reception.signature_valide``).

| Test | Ce qu'il prouve |
|---|---|
| signature | un message rendu porte la signature du corps brut avec le secret de l'application, que la réception reconnaît ; un autre secret, un corps changé : refusé |
| rejeu | échec : nouvelle tentative après 1, 2, 4, 8, 16 min ; au sixième échec le message est abandonné ; réussi à la troisième : rendu une fois, plus jamais ensuite |
| sans secret | sans secret d'application, rien ne part (jamais un secret de substitution) |
| doublon | le comportement « message en double » rend le MÊME message (même identifiant) deux fois |
| mode passif | sans adresse de rappel, le message est gardé, lu par ``GET /callback/events``, acquitté par ``DELETE`` ; un autre restaurant ne l'acquitte pas |
| cloisonnement | le message d'un restaurant n'arrive qu'à SON adresse de rappel |
| gestes | rupture, prix, état et statut changés « par la caisse » écrivent leur donnée et rendent leur message ; un code inconnu ne fait rien |
| acceptation | une commande acceptée par la caisse le dit par un message ``order.update`` ; « manuelle » : aucun message ; « refus » : ``rejected`` |
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from api.db import db_client
from api.db.bases_clients.horloge import remplacer
from api.services.restauration.caisse_demo import messages, restaurants
from api.services.restauration.caisse_demo.moteur import empreinte_du_jeton, moteur
from api.services.restauration.prises import hubrise_liaison
from api.services.restauration.prises import hubrise_reception as hr
from api.tests.mark.equipe_commun import creer_organisation

SECRET = "secret-de-notre-application"
T0 = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
CARTE = {
    "format": "mark-carte-commune/1", "categories": [], "groupes": [], "formules": [],
    "produits": [{"id": "P", "nom": "Pizza", "categorie_id": None, "groupes": [], "declinaisons": [{"id": "P-1", "nom": "P", "code_caisse": "P-1", "prix": 1000}]}],
}


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("HUBRISE_CLIENT_ID", "id-de-notre-application")
    monkeypatch.setenv("HUBRISE_CLIENT_SECRET", SECRET)


def _reception(code: int = 200, *, echecs: int = 0):
    """La réception enregistrée : garde ce qu'elle reçoit ; refuse (500) les ``echecs`` premiers envois."""
    recus: list[tuple[bytes, str]] = []

    def repondre(r: httpx.Request) -> httpx.Response:
        recus.append((r.content, r.headers.get("x-hubrise-hmac-sha256", "")))
        return httpx.Response(500 if len(recus) <= echecs else code, json={"ok": True})

    t = httpx.MockTransport(repondre)
    t.recus = recus
    return t


async def _restaurant(nom: str, *, rappel: bool = True, **plus):
    organisation = await creer_organisation(db_client, f"caisse-demo-{nom}")
    r = await restaurants.creer(organisation, nom, carte=CARTE, **plus)
    champs = {"jeton_empreinte": empreinte_du_jeton(f"jeton-{nom}")}
    if rappel:
        champs["callback_url"] = hubrise_liaison.adresse_de_rappel()
    return organisation, await db_client.modifier_restaurant_de_demo(organisation, r["id"], champs, T0)


async def _poster(organisation, r, *args, **plus):
    with remplacer(organisation, T0):  # le message est écrit à l'heure du test, comme son envoi
        return await messages.poster(r, *args, **plus)


async def test_un_message_rendu_porte_la_signature_que_la_reception_reconnait(db_session):
    organisation, r = await _restaurant("signature")
    identifiant = await _poster(organisation, r, "location", "update")
    reception = _reception()
    with remplacer(organisation, T0):
        bilan = await messages.envoyer_les_messages_dus(transport=reception, restaurant_id=r["id"])
    assert bilan["rendus"] >= 1
    corps, signature = next((c, s) for c, s in reception.recus if json.loads(c)["id"] == identifiant)
    assert hr.signature_valide(corps, signature, SECRET) and not hr.signature_valide(corps, signature, "autre-secret") and not hr.signature_valide(corps + b" ", signature, SECRET)
    message = hr.lire_le_message(corps)
    assert message and (message["resource_type"], message["event_type"], message["location_id"]) == ("location", "update", r["point_de_vente"])
    assert (await db_client.lire_message_de_demo(identifiant))["statut"] == "envoye"


async def test_un_echec_est_rejoue_apres_1_2_4_8_16_minutes_puis_abandonne(db_session):
    organisation, r = await _restaurant("rejeu")
    identifiant = await _poster(organisation, r, "location", "update")
    reception = _reception(echecs=99)
    delais = []
    horloge_courante = [T0]
    with remplacer(organisation, lambda: horloge_courante[0]):
        for _ in range(6):
            await messages.envoyer_les_messages_dus(transport=reception, restaurant_id=r["id"])
            ligne = await db_client.lire_message_de_demo(identifiant)
            if ligne["statut"] != "a_envoyer":
                break
            delais.append(int((ligne["prochaine_le"] - horloge_courante[0]).total_seconds() // 60))
            antes = len(reception.recus)
            await messages.envoyer_les_messages_dus(transport=reception, restaurant_id=r["id"])  # trop tôt : rien n'est renvoyé
            assert len(reception.recus) == antes
            horloge_courante[0] = ligne["prochaine_le"]
    assert delais == [1, 2, 4, 8, 16]
    ligne = await db_client.lire_message_de_demo(identifiant)
    assert (ligne["statut"], ligne["tentatives"]) == ("abandonne", 6)
    with remplacer(organisation, horloge_courante[0] + timedelta(days=1)):
        avant = len(reception.recus)
        await messages.envoyer_les_messages_dus(transport=reception, restaurant_id=r["id"])
        assert len(reception.recus) == avant  # abandonné : plus jamais rendu


async def test_reussi_a_la_troisieme_tentative_il_est_rendu_une_fois_puis_plus(db_session):
    organisation, r = await _restaurant("troisieme")
    identifiant = await _poster(organisation, r, "order", "update", order_id="x1")
    reception = _reception(echecs=2)
    heure = [T0]
    with remplacer(organisation, lambda: heure[0]):
        for _ in range(5):
            await messages.envoyer_les_messages_dus(transport=reception, restaurant_id=r["id"])
            ligne = await db_client.lire_message_de_demo(identifiant)
            if ligne["prochaine_le"]:
                heure[0] = ligne["prochaine_le"]
    assert (await db_client.lire_message_de_demo(identifiant))["statut"] == "envoye"
    assert len([1 for c, _ in reception.recus if json.loads(c)["id"] == identifiant]) == 3  # deux échecs, un succès


async def test_sans_secret_d_application_rien_ne_part(db_session, monkeypatch):
    organisation, r = await _restaurant("sanssecret")
    identifiant = await _poster(organisation, r, "location", "update")
    monkeypatch.delenv("HUBRISE_CLIENT_SECRET")
    reception = _reception()
    with remplacer(organisation, T0):
        assert await messages.envoyer_les_messages_dus(transport=reception, restaurant_id=r["id"]) == {"rendus": 0, "reportes": 0, "abandonnes": 0, "ignores": 0}
    assert reception.recus == [] and (await db_client.lire_message_de_demo(identifiant))["statut"] == "a_envoyer"


async def test_le_comportement_doublon_rend_le_meme_message_deux_fois(db_session):
    organisation, r = await _restaurant("doublon", comportement={"doublon": True})
    identifiant = await _poster(organisation, r, "order", "update", order_id="x2")
    reception = _reception()
    with remplacer(organisation, T0):
        await messages.envoyer_les_messages_dus(transport=reception, restaurant_id=r["id"])
    mes = [json.loads(c)["id"] for c, _ in reception.recus if json.loads(c)["id"] == identifiant]
    assert mes == [identifiant, identifiant]
    # la réception, elle, ne le prend qu'une fois : l'identifiant est le même (voir test_restauration_caisse_demo_bout_en_bout)


async def test_mode_passif_les_messages_sont_gardes_lus_puis_acquittes(db_session):
    organisation, r = await _restaurant("passif", rappel=False)
    autre_org, autre = await _restaurant("passif-autre", rappel=False)
    identifiant = await _poster(organisation, r, "inventory", "patch")
    assert (await db_client.lire_message_de_demo(identifiant))["statut"] == "garde"
    lus = await moteur.servir("jeton-passif", "GET", "/callback/events")
    assert [e["id"] for e in lus.corps] == [identifiant] and lus.corps[0]["resource_type"] == "inventory"
    refus = await moteur.servir("jeton-passif-autre", "DELETE", f"/callback/events/{identifiant}")
    assert refus.code == 404 and (await db_client.lire_message_de_demo(identifiant))["statut"] == "garde"  # pas celui d'un autre restaurant
    assert (await moteur.servir("jeton-passif", "DELETE", f"/callback/events/{identifiant}")).code == 200
    assert (await moteur.servir("jeton-passif", "GET", "/callback/events")).corps == []
    assert (await moteur.servir("jeton-passif-autre", "GET", "/callback/events")).corps == []
    with remplacer(organisation, T0):
        reception = _reception()
        await messages.envoyer_les_messages_dus(transport=reception, restaurant_id=r["id"])
    assert all(json.loads(c)["id"] != identifiant for c, _ in reception.recus)  # gardé : jamais poussé


async def test_le_message_d_un_restaurant_n_arrive_qu_a_son_adresse(db_session):
    organisation, a = await _restaurant("cloison-a")
    _, b = await _restaurant("cloison-b", rappel=False)
    ida = await _poster(organisation, a, "location", "update")
    idb = await _poster(organisation, b, "location", "update")
    reception = _reception()
    with remplacer(organisation, T0):
        await messages.envoyer_les_messages_dus(transport=reception, restaurant_id=a["id"])
    rendus = [json.loads(c) for c, _ in reception.recus]
    assert any(m["id"] == ida and m["location_id"] == a["point_de_vente"] for m in rendus)
    assert all(m["id"] != idb for m in rendus) and (await db_client.lire_message_de_demo(idb))["statut"] == "garde"


async def test_les_gestes_de_la_caisse_ecrivent_leur_donnee_et_rendent_leur_message(db_session):
    organisation, r = await _restaurant("gestes", etat="ouvert")
    assert await restaurants.poser_une_rupture(organisation, r["id"], "P-1", False)
    assert (await moteur.servir("jeton-gestes", "GET", f"/catalogs/{r['point_de_vente'].rsplit('-', 1)[0]}-cat/locations/{r['point_de_vente']}/inventory")).corps == [{"sku_ref": "P-1", "stock": "0.0", "expires_at": None}]
    assert await restaurants.poser_une_rupture(organisation, r["id"], "P-1", True)
    assert (await db_client.lire_restaurant_de_demo(organisation, r["id"]))["stocks"] == []
    assert await restaurants.changer_un_prix(organisation, r["id"], "P-1", 1100)
    assert (await db_client.lire_restaurant_de_demo(organisation, r["id"]))["carte"]["produits"][0]["declinaisons"][0]["prix"] == 1100
    assert await restaurants.changer_l_etat_par_la_caisse(organisation, r["id"], "deborde", 15)
    assert (await moteur.servir("jeton-gestes", "GET", "/location")).corps["order_acceptance"] == {"mode": "busy", "extra_preparation_time": 15, "resume_at": None}
    assert not await restaurants.poser_une_rupture(organisation, r["id"], "INCONNU", False)  # un code inconnu ne fait rien
    assert not await restaurants.changer_un_prix(organisation, r["id"], "INCONNU", 100) and not await restaurants.changer_un_prix(organisation, r["id"], "P-1", -1)
    types = [(m["corps"]["resource_type"], m["corps"]["event_type"]) for m in reversed(await db_client.lister_messages_de_demo(r["id"]))]
    assert types == [("inventory", "patch"), ("inventory", "patch"), ("catalog", "update"), ("location", "update")]


async def test_l_acceptation_de_la_caisse_se_dit_par_un_message(db_session):
    organisation, r = await _restaurant("acceptation", rappel=False)
    commande = {"status": "new", "private_ref": "N-1", "service_type": "collection", "items": [{"product_name": "Pizza", "sku_ref": "P-1", "price": "10.00 EUR", "quantity": "1"}]}
    cree = await moteur.servir("jeton-acceptation", "POST", "/location/orders", corps=commande)
    assert cree.code == 200 and cree.corps["status"] == "new"  # la réponse dit « nouvelle » ; l'acceptation vient après, par le message
    lu = await moteur.servir("jeton-acceptation", "GET", f"/location/orders/{cree.corps['id']}")
    assert lu.corps["status"] == "accepted"
    msgs = await db_client.lister_messages_de_demo(r["id"])
    assert [(m["corps"]["resource_type"], m["corps"]["event_type"], m["corps"]["order_id"]) for m in msgs] == [("order", "update", cree.corps["id"])]
    await restaurants.regler(organisation, r["id"], {"comportement": {"acceptation": "manuelle"}})
    manuelle = await moteur.servir("jeton-acceptation", "POST", "/location/orders", corps={**commande, "private_ref": "N-2"})
    assert (await moteur.servir("jeton-acceptation", "GET", f"/location/orders/{manuelle.corps['id']}")).corps["status"] == "new"
    await restaurants.regler(organisation, r["id"], {"comportement": {"acceptation": "refus"}})
    refus = await moteur.servir("jeton-acceptation", "POST", "/location/orders", corps={**commande, "private_ref": "N-3"})
    assert (await moteur.servir("jeton-acceptation", "GET", f"/location/orders/{refus.corps['id']}")).corps["status"] == "rejected"
    assert len(await db_client.lister_messages_de_demo(r["id"])) == 2  # manuelle : aucun message


async def test_la_tache_planifiee_ne_fait_rien_interrupteur_eteint_et_rend_les_messages_dus_allumee(db_session, monkeypatch):
    from api.tasks import arq as taches

    organisation, r = await _restaurant("tache")
    identifiant = await _poster(organisation, r, "location", "update")
    monkeypatch.delenv("CAISSE_DEMO_ACTIVE", raising=False)
    assert await messages.rendre_les_messages_de_la_caisse_de_demo() == {"rendus": 0, "reportes": 0, "abandonnes": 0, "ignores": 0}
    assert (await db_client.lire_message_de_demo(identifiant))["statut"] == "a_envoyer"  # éteint : rien n'a bougé
    monkeypatch.setenv("CAISSE_DEMO_ACTIVE", "1")
    # allumée : la tâche rend (vers une adresse qui ne répond pas ici : le message est reporté, jamais perdu)
    assert (await messages.envoyer_les_messages_dus(restaurant_id=r["id"], transport=_reception(500)))["reportes"] == 1
    assert any(getattr(c, "coroutine", None) is messages.rendre_les_messages_de_la_caisse_de_demo for c in taches.WorkerSettings.cron_jobs)  # branchée au planificateur
