"""[.mark] Module Restauration, lot 19 (SA-20) : les DEUX DERNIÈRES commandes réelles du compte de test HubRise (16/11), rejouées.

Les fichiers ``reponses_hubrise/24*`` (commande 4 : planifiée au lendemain midi, annulée par nous, temps de préparation changé puis remis) et ``25*`` (commande 5 :
réception coupée puis rétablie, refus posé par nous, messages gardés) sont les vraies réponses. Aucun appel réel ici.

| Test | Ce qu'il prouve |
|---|---|
| corps envoyé | NOTRE traducteur écrit exactement le corps qui a été envoyé en réel (heure du lendemain midi, ``private_ref``) |
| prise | la prise lit « annulée » et l'heure annoncée sur la vraie réponse, et annule par un ``PATCH cancelled`` après recherche par ``private_ref`` |
| caisse de démo, commande 4 | temps de préparation SEUL accepté et gardé (24b : HubRise 200, la démo disait 422) ; commande planifiée, annulée, relue : même forme que HubRise ; l'heure n'est pas décalée |
| caisse de démo, commande 5 | un jamais-abonné rend ``events: {}`` (25a) ; un refus posé par NOTRE application ne revient pas dans nos messages (25e) ; refusée par la caisse, il revient |
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from api.db import db_client
from api.services.restauration.caisse_demo import restaurants
from api.services.restauration.caisse_demo.moteur import empreinte_du_jeton, moteur
from api.services.restauration.prises import hubrise_traduction as ht
from api.services.restauration.prises.hubrise_client import ClientHubrise
from api.services.restauration.prises.prise_hubrise import PriseHubrise
from api.tests.mark.equipe_commun import creer_organisation
from api.tests.mark.test_restauration_caisse_demo_moteur import _meme_forme

DOSSIER = Path(__file__).parent / "reponses_hubrise"
JETON = "jeton-sa20"


def _f(nom: str) -> dict:
    return json.loads((DOSSIER / f"{nom}.json").read_text(encoding="utf-8"))


def _commande_4() -> dict:
    return {
        "numero": "mark-test-4", "mode": "emporter", "client": {"telephone": "+33600000001", "prenom": "Camille"},
        "heure_voulue": datetime(2026, 11, 17, 12, 0, tzinfo=timezone(timedelta(hours=1))),
        "lignes": [{"nom": "Reine (Test)", "code_caisse": "REINE-S", "prix_unitaire": 1250, "quantite": 1}, {"nom": "Coca-Cola (Test)", "code_caisse": "COCA-33", "prix_unitaire": 250, "quantite": 1}],
    }


def test_notre_traducteur_ecrit_le_corps_envoye_en_reel_pour_les_deux_commandes():
    assert ht.commande_vers_hubrise(_commande_4()) == _f("24d-commande-planifiee-creee")["demande"]["corps"]
    sans_heure = {**_commande_4(), "numero": "mark-test-5", "heure_voulue": None}
    assert ht.commande_vers_hubrise(sans_heure) == _f("25c-commande-refusee-creee")["demande"]["corps"]


async def test_la_prise_lit_la_commande_annulee_et_l_annule_apres_l_avoir_cherchee_par_notre_numero():
    vraie, demandes = _f("24g-commande-planifiee-par-reference")["reponse"]["corps"], []

    def rendre(requete: httpx.Request) -> httpx.Response:
        demandes.append((requete.method, requete.url.path, requete.url.params.get("private_ref"), requete.content))
        return httpx.Response(200, json=vraie if requete.method == "GET" else vraie[0])

    prise = PriseHubrise(ClientHubrise("jeton-de-test", point_de_vente="w8xvp-0", transport=httpx.MockTransport(rendre)))
    lue = ht.commande_de_hubrise(_f("24f-commande-planifiee-relue")["reponse"]["corps"])
    assert (lue["etape"], lue["numero"], lue["heure_confirmee"]) == ("annulee", "mark-test-4", None)
    # preparation_time à 45 : HubRise ne décale pas l'heure demandée par le client
    assert lue["heure_annoncee"] == datetime(2026, 11, 17, 12, 0, tzinfo=timezone(timedelta(hours=1)))
    resultat = await prise.faire_annuler("mark-test-4")
    assert (resultat.statut, resultat.etape, resultat.ref_fournisseur) == ("ENVOYEE", "annulee", vraie[0]["id"])
    assert demandes[0][:3] == ("GET", "/v1/location/orders", "mark-test-4")
    assert demandes[1][0] == "PATCH" and json.loads(demandes[1][3]) == {"status": "cancelled"}


async def _caisse(nom: str, comportement: dict):
    organisation = await creer_organisation(db_client, nom)
    r = await restaurants.creer(organisation, "Test Beauvais", reglages={"enseigne": "Pizzeria .mark (Test)", "delai": 20}, comportement=comportement)
    r = await db_client.modifier_restaurant_de_demo(organisation, r["id"], {"jeton_empreinte": empreinte_du_jeton(JETON)}, restaurants.horloge(organisation).maintenant())
    return organisation, r


async def _rejouer(fichier: str):
    """Rejoue la demande enregistrée contre la caisse de démo."""
    d = _f(fichier)["demande"]
    chemin, _, requete = d["chemin"].partition("?")
    params = dict(x.split("=", 1) for x in requete.split("&") if x)
    return await moteur.servir(JETON, d["methode"], chemin, params, d["corps"])


def _comme_hubrise(fichier: str, rep) -> None:
    voulu = _f(fichier)["reponse"]
    assert rep.code == voulu["code"], fichier
    assert _meme_forme(voulu["corps"], rep.corps) == [], fichier


async def test_commande_4_le_temps_de_preparation_seul_est_accepte_puis_la_commande_planifiee_est_annulee_comme_chez_hubrise(db_session):
    await _caisse("sa20-c4", {"acceptation": "manuelle", "delai_s": 0.4})
    _comme_hubrise("24a-point-de-vente-avant", await _rejouer("24a-point-de-vente-avant"))
    apres = await _rejouer("24b-temps-de-preparation-change")
    _comme_hubrise("24b-temps-de-preparation-change", apres)
    # le mode n'est pas touché par un PATCH qui ne le cite pas
    assert apres.corps["preparation_time"] == 45 and apres.corps["order_acceptance"] == {"mode": "normal"}
    _comme_hubrise("24c-point-de-vente-apres", await _rejouer("24c-point-de-vente-apres"))
    cree = await _rejouer("24d-commande-planifiee-creee")
    _comme_hubrise("24d-commande-planifiee-creee", cree)
    assert (cree.corps["status"], cree.corps["asap"], cree.corps["expected_time"], cree.corps["confirmed_time"]) == ("new", False, "2026-11-17T12:00:00+01:00", None)
    await moteur.servir(JETON, "PATCH", f"/location/orders/{cree.corps['id']}", {}, {"status": "cancelled"})
    relue = await moteur.servir(JETON, "GET", f"/location/orders/{cree.corps['id']}")
    _comme_hubrise("24f-commande-planifiee-relue", relue)
    assert (relue.corps["status"], relue.corps["expected_time"], relue.corps["confirmed_time"]) == ("cancelled", "2026-11-17T12:00:00+01:00", None)
    _comme_hubrise("24g-commande-planifiee-par-reference", await moteur.servir(JETON, "GET", "/location/orders", {"private_ref": "mark-test-4"}))
    remis = await _rejouer("24h-temps-de-preparation-remis")
    assert remis.code == 200 and remis.corps["preparation_time"] == 20
    refuse = await moteur.servir(JETON, "PATCH", "/location", {}, {"preparation_time": "vite"})
    assert (refuse.code, refuse.corps["errors"][0]["field"]) == (422, "/preparation_time")
    assert (await moteur.servir(JETON, "PATCH", "/location", {}, {})).code == 422  # rien à changer : comme avant


async def test_commande_5_un_jamais_abonne_rend_des_evenements_vides_et_notre_propre_refus_ne_nous_revient_pas(db_session):
    organisation, r = await _caisse("sa20-c5", {"acceptation": "manuelle", "delai_s": 0.4})  # le compte de test n'a pas de caisse qui accepte
    _comme_hubrise("25a-abonnement-avant", await _rejouer("25a-abonnement-avant"))
    assert (await _rejouer("25b-messages-avant")).corps == _f("25b-messages-avant")["reponse"]["corps"] == []
    cree = await _rejouer("25c-commande-refusee-creee")
    _comme_hubrise("25c-commande-refusee-creee", cree)
    _comme_hubrise("25f-abonnement-passif-retabli", await _rejouer("25f-abonnement-passif-retabli"))
    assert (await moteur.servir(JETON, "GET", "/callback")).corps == _f("25g-abonnement-relu")["reponse"]["corps"]
    refuse = await moteur.servir(JETON, "PATCH", f"/location/orders/{cree.corps['id']}", {}, {"status": "rejected"})
    assert refuse.corps["status"] == "rejected"
    # HubRise ne rend pas à une application ses propres changements (25e)
    assert (await moteur.servir(JETON, "GET", "/callback/events")).corps == _f("25e-messages-apres-refus-par-nous")["reponse"]["corps"] == []
    # remise à « new », puis refusée PAR LA CAISSE (un autre client) : le message est gardé
    await moteur.servir(JETON, "PATCH", f"/location/orders/{cree.corps['id']}", {}, {"status": "new"})
    assert await restaurants.changer_une_commande(organisation, r["id"], cree.corps["id"], statut="rejected")
    gardes = (await moteur.servir(JETON, "GET", "/callback/events")).corps
    assert [(m["resource_type"], m["event_type"], m["order_id"], m["new_state"]) for m in gardes] == [("order", "update", cree.corps["id"], {"status": "rejected"})]
    assert (await moteur.servir(JETON, "DELETE", f"/callback/events/{gardes[0]['id']}")).code == 200
    assert (await moteur.servir(JETON, "GET", "/callback/events")).corps == []
