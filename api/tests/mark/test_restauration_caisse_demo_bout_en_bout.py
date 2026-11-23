"""[.mark] Module Restauration, lot 20, étapes 4 à 6 : la VRAIE prise HubRise branchée sur la caisse de démo, de bout en bout (D9), et les gardes.

Vraies bases de clients, vrai Redis, vraie base de Dograh. Aucun réseau : la prise parle à la caisse de démo par ``TransportDeDemo`` (le même moteur que la route), et
les messages signés de la caisse arrivent à la réception par un transport qui fait ce que fait la route (signature vérifiée) puis le traitement de fond.

| Test | Ce qu'il prouve |
|---|---|
| parcours complet | commande enregistrée -> prise HubRise -> caisse de démo -> elle accepte -> message signé -> réception -> statut « acceptée » dans le classeur -> événement du direct |
| message en double | le même message rendu deux fois ne fait avancer la commande qu'une fois (un seul événement) |
| refus | une caisse stricte refuse un produit inconnu et un prix différent : « refusée », secours, rien n'est accepté |
| silence et lenteur | une caisse muette, ou plus lente que le délai de la requête : indisponible, à reprendre ; une caisse lente mais dans le délai : acceptée |
| rupture en plein appel | la caisse met un produit en rupture : message signé, la rupture arrive dans le classeur |
| prix changé en plein appel | la caisse change un prix : message signé, la carte est relue |
| garde | un établissement d'une organisation qui n'est pas le Labo ne se branche pas, interrupteur éteint non plus ; un jeton de caisse de démo dans le coffre d'un client ne donne aucun accès |
| route | éteinte : 404 ; jeton faux ou organisation cliente : 401 ; allumée, Labo, bon jeton : la réponse de HubRise |
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from api.db import db_client
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.services.restauration.caisse import envoi_caisse as ec
from api.services.restauration.caisse.caisse_demo import branchement, garde, messages, restaurants
from api.services.restauration.caisse.caisse_demo.moteur import catalogue_id_de, empreinte_du_jeton
from api.services.restauration.caisse.caisse_demo.transport import TransportDeDemo
from api.services.restauration.caisse.prises import hubrise_liaison as hl
from api.services.restauration.caisse.prises import hubrise_reception as hr
from api.services.restauration.caisse.prises import hubrise_traduction as ht
from api.services.restauration.caisse.prises.prise import ContexteDePrise
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import _corps, _etablissements_propres, _evenements  # noqa: F401
from api.tests.mark.test_restauration_envoi_caisse import Secours, _commande, _etat

SECRET = "secret-de-notre-application"


@pytest.fixture
def demo_allumee(monkeypatch):
    monkeypatch.setenv("CAISSE_DEMO_ACTIVE", "1")
    monkeypatch.setenv("HUBRISE_CLIENT_ID", "id-de-notre-application")
    monkeypatch.setenv("HUBRISE_CLIENT_SECRET", SECRET)


def _labo(monkeypatch, organisation: int):
    async def est_labo(o):
        return o == organisation

    monkeypatch.setattr(garde, "organisation_est_labo", est_labo)


class Reception:
    """Ce que fait la réception : vérifier la signature du corps brut, puis traiter le message (la route met en file, la tâche traite). Garde ses résultats."""

    def __init__(self, caisse: TransportDeDemo):
        self.resultats: list[dict] = []
        self.transport = httpx.MockTransport(self._repondre)
        self._caisse = caisse

    async def _repondre(self, r: httpx.Request) -> httpx.Response:
        if not hr.signature_valide(r.content, r.headers.get("x-hubrise-hmac-sha256"), SECRET):
            return httpx.Response(401, json={})
        self.resultats.append(await hr.traiter_le_message(None, hr.lire_le_message(r.content), transport=self._caisse))
        return httpx.Response(200, json={"ok": True})


async def _carte_de_la_caisse():
    return ht.carte_de_hubrise(_corps("04-carte-relue.json")).carte


async def _cas_branche(db_session, seconde_base, monkeypatch, **comportement):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    _labo(monkeypatch, cas.a)
    etab = cas.sites_a[0]
    r = await restaurants.creer(cas.a, "Pizzeria de test", carte=await _carte_de_la_caisse())
    caisse = TransportDeDemo(dormir=_pas_de_pause)
    bilan = await branchement.brancher(cas.a, cas.admin.id, r["id"], etab, transport=caisse)
    if comportement:  # le comportement se pose APRÈS le branchement (une caisse muette ne se laisserait pas brancher)
        await restaurants.regler(cas.a, r["id"], {"comportement": comportement})
    return cas, etab, r, caisse, bilan


async def _pas_de_pause(_secondes: float) -> None:
    return None


async def _livrer(cas, r, reception):
    return await messages.envoyer_les_messages_dus(transport=reception.transport, restaurant_id=r["id"])


async def test_parcours_complet_commande_prise_caisse_message_signe_statut_et_direct(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas, etab, r, caisse, bilan = await _cas_branche(db_session, seconde_base, monkeypatch)
    assert bilan["passif"] is False  # la caisse de démo a accepté NOTRE adresse de réception : messages signés, pas de relève
    assert bilan["import"] and bilan["import"]["erreur"] is None
    base = await schema.connecter(cas.base_a)
    try:
        liaison = await lia.liaison(base, etab)
        assert (liaison["prise"], liaison["etat"], liaison["point_de_vente"]) == ("hubrise", "ok", r["point_de_vente"])
    finally:
        await base.close()
    numero = await _commande(cas.base_a, etab)
    secours = Secours()
    issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse, secours=secours)
    assert issue.issue == "envoyee" and secours.messages == []
    recue = await db_client.lister_commandes_de_demo(r["id"], private_ref=numero)
    assert len(recue) == 1 and recue[0]["corps"]["items"][0]["sku_ref"] == "REINE-S"  # la caisse de démo a reçu NOTRE numéro et le bon code
    assert (await _etat(cas.base_a, numero))["statut"] == "envoyee"
    reception = Reception(caisse)
    assert (await _livrer(cas, r, reception))["rendus"] >= 1  # le message signé « la caisse a accepté » arrive à la réception
    assert [x["statut"] for x in reception.resultats if x["statut"] == "traite" and x["effet"] == "statut"] == ["traite"]
    assert (await _etat(cas.base_a, numero))["statut"] == "acceptee"
    evenements = await _evenements(cas.a, etab)
    assert ("commande.statut", {"numero": numero, "de": "envoyee", "vers": "acceptee", "source": "caisse"}) in evenements


async def test_le_message_rendu_en_double_ne_fait_avancer_la_commande_qu_une_fois(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas, etab, r, caisse, _ = await _cas_branche(db_session, seconde_base, monkeypatch, doublon=True)
    numero = await _commande(cas.base_a, etab)
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse, secours=Secours())
    reception = Reception(caisse)
    await _livrer(cas, r, reception)
    assert [x["statut"] for x in reception.resultats] == ["traite", "deja_vu"]
    acceptees = [e for e in await _evenements(cas.a, etab) if e[0] == "commande.statut" and e[1]["vers"] == "acceptee"]
    assert len(acceptees) == 1


async def test_une_caisse_stricte_refuse_un_produit_inconnu_et_un_prix_different(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas, etab, r, caisse, _ = await _cas_branche(db_session, seconde_base, monkeypatch, reponse="controle")
    secours = Secours()
    inconnu = await _commande(cas.base_a, etab)
    base = await schema.connecter(cas.base_a)
    try:
        await base.execute("UPDATE mark.resto_commande_ligne SET code_caisse = 'N-EXISTE-PAS' WHERE numero = $1", uuid.UUID(inconnu))
        prix = await _commande(cas.base_a, etab)
        await base.execute("UPDATE mark.resto_commande_ligne SET prix_unitaire = 900 WHERE numero = $1", uuid.UUID(prix))
    finally:
        await base.close()
    for numero in (inconnu, prix):
        issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse, secours=secours)
        assert issue.issue == "refusee", numero
        assert (await _etat(cas.base_a, numero))["statut"] == "refusee"
    assert len(secours.messages) == 2 and await db_client.lister_commandes_de_demo(r["id"]) == []  # rien n'est arrivé dans la caisse
    ok = await _commande(cas.base_a, etab)
    assert (await ec.envoyer_la_commande(cas.a, cas.base_a, etab, ok, transport=caisse, secours=Secours())).issue == "envoyee"  # le bon code, le bon prix : elle accepte


async def test_une_caisse_muette_ou_trop_lente_est_indisponible_une_caisse_lente_dans_le_delai_accepte(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas, etab, r, caisse, _ = await _cas_branche(db_session, seconde_base, monkeypatch, reponse="silence")
    muette = await _commande(cas.base_a, etab)
    assert (await ec.envoyer_la_commande(cas.a, cas.base_a, etab, muette, transport=caisse, secours=Secours())).issue == "a_reprendre"
    assert (await _etat(cas.base_a, muette))["statut"] == "envoyee"  # à reprendre : personne n'est dérangé, l'envoi sera repris
    await restaurants.regler(cas.a, r["id"], {"comportement": {"reponse": "accepte", "delai_s": 12}})  # plus que les 10 s de la requête
    trop_lente = await _commande(cas.base_a, etab)
    assert (await ec.envoyer_la_commande(cas.a, cas.base_a, etab, trop_lente, transport=caisse, secours=Secours())).issue == "a_reprendre"
    await restaurants.regler(cas.a, r["id"], {"comportement": {"reponse": "accepte", "delai_s": 6}})  # lente, mais elle répond
    lente = await _commande(cas.base_a, etab)
    assert (await ec.envoyer_la_commande(cas.a, cas.base_a, etab, lente, transport=caisse, secours=Secours())).issue == "envoyee"


async def test_une_rupture_et_un_prix_changes_par_la_caisse_pendant_l_appel_arrivent_par_message_signe(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas, etab, r, caisse, _ = await _cas_branche(db_session, seconde_base, monkeypatch)
    reception = Reception(caisse)
    assert await restaurants.poser_une_rupture(cas.a, r["id"], "TIRA-1", False)
    await _livrer(cas, r, reception)
    base = await schema.connecter(cas.base_a)
    try:
        assert (await lia.ruptures_de_la_caisse(base, etab)).get("TIRA-1") is False  # en rupture dans le classeur
        assert await restaurants.changer_un_prix(cas.a, r["id"], "REINE-S", 1350)
        await _livrer(cas, r, reception)
        assert await base.fetchval("SELECT prix FROM mark.resto_declinaison WHERE code_caisse = 'REINE-S' AND site_id = $1", etab) == 1350
    finally:
        await base.close()
    assert [x["effet"] for x in reception.resultats if x["statut"] == "traite"][0].startswith("ruptures")
    assert await restaurants.poser_une_rupture(cas.a, r["id"], "TIRA-1", True)
    await _livrer(cas, r, reception)
    base = await schema.connecter(cas.base_a)
    try:
        assert (await lia.ruptures_de_la_caisse(base, etab)).get("TIRA-1") in (True, None)
    finally:
        await base.close()


async def test_hors_labo_ou_interrupteur_eteint_la_caisse_de_demo_n_existe_pas(db_session, seconde_base, sans_preparation_des_organisations, monkeypatch):  # noqa: F811
    monkeypatch.setenv("HUBRISE_CLIENT_ID", "id")
    monkeypatch.setenv("HUBRISE_CLIENT_SECRET", SECRET)
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    r = await restaurants.creer(cas.a, "Test", carte=await _carte_de_la_caisse())
    # interrupteur éteint (même Labo) : refusé
    monkeypatch.delenv("CAISSE_DEMO_ACTIVE", raising=False)
    _labo(monkeypatch, cas.a)
    with pytest.raises(branchement.BranchementDeDemoRefuse) as e:
        await branchement.brancher(cas.a, cas.admin.id, r["id"], etab, transport=TransportDeDemo())
    assert e.value.code == "non_permis"
    # interrupteur allumé, organisation cliente (pas le Labo) : refusé
    monkeypatch.setenv("CAISSE_DEMO_ACTIVE", "1")
    _labo(monkeypatch, cas.b)
    with pytest.raises(branchement.BranchementDeDemoRefuse) as e:
        await branchement.brancher(cas.a, cas.admin.id, r["id"], etab, transport=TransportDeDemo())
    assert e.value.code == "non_permis"
    base = await schema.connecter(cas.base_a)
    try:
        assert await lia.liaison(base, etab) is None  # rien n'a été écrit
    finally:
        await base.close()
    # un jeton de caisse de démo rangé dans le coffre d'un CLIENT ne donne aucun accès : la prise refuse tout geste
    credential = await db_client.create_credential(
        cas.a, cas.admin.id, "caisse-hubrise-piratee", "bearer_token",
        {"token": "demo_x", "fournisseur": "hubrise", "point_de_vente": r["point_de_vente"], "catalogue": catalogue_id_de(r), "demo": True}, description="essai",
    )
    base = await schema.connecter(cas.base_a)
    try:
        await lia.poser_acces(base, etab, credential.credential_uuid)
        prise = await hl._fabrique(ContexteDePrise(base, cas.a, etab, cas.base_a, TransportDeDemo()))
        assert prise._client is None  # PrisePasBranchee à tout geste
    finally:
        await base.close()


async def test_la_route_est_eteinte_refuse_un_faux_jeton_et_une_organisation_cliente_puis_repond_comme_hubrise(db_session, seconde_base, sans_preparation_des_organisations, monkeypatch):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    r = await restaurants.creer(cas.a, "Test route", carte=await _carte_de_la_caisse())
    await db_client.modifier_restaurant_de_demo(cas.a, r["id"], {"jeton_empreinte": empreinte_du_jeton("jeton-route")}, restaurants.horloge(cas.a).maintenant())
    chemin = "/api/v1/restauration/caisse-demo/v1/location"
    monkeypatch.delenv("CAISSE_DEMO_ACTIVE", raising=False)
    async with client_http() as c:
        assert (await c.get(chemin, headers={"X-Access-Token": "jeton-route"})).status_code == 404  # éteinte
        monkeypatch.setenv("CAISSE_DEMO_ACTIVE", "1")
        _labo(monkeypatch, cas.b)  # le Labo n'est pas l'organisation du restaurant
        client = await c.get(chemin, headers={"X-Access-Token": "jeton-route"})
        assert client.status_code == 401 and client.json()["error_type"] == "unauthorized"
        _labo(monkeypatch, cas.a)
        assert (await c.get(chemin, headers={"X-Access-Token": "faux"})).status_code == 401
        assert (await c.get(chemin)).status_code == 401
        ok = await c.get(chemin, headers={"X-Access-Token": "jeton-route"})
        assert ok.status_code == 200 and ok.json()["id"] == r["point_de_vente"] and ok.json()["order_acceptance"] == {"mode": "normal"}
        assert (await c.get(chemin.replace("/location", "/location/orders/zzz"), headers={"X-Access-Token": "jeton-route"})).status_code == 404
        assert (await c.post(chemin + "/orders", content=b"pas du json", headers={"X-Access-Token": "jeton-route"})).status_code == 400
