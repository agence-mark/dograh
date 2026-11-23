"""[.mark] Module Restauration, lot 9, étape 3 : le client HTTP de HubRise et la prise HubRise, sur des réponses ENREGISTRÉES (aucun appel réel).

Les réponses viennent de ``reponses_hubrise/`` (enregistrées le 15/11 sur le compte de test) ; le transport est un ``httpx.MockTransport``.

| Test | Ce qu'il prouve |
|---|---|
| liste fermée | une adresse hors de la liste de la fiche n'est jamais appelée (rien ne sort) ; le jeton part en en-tête et n'apparaît jamais dans l'objet affiché |
| délai et tentatives | une panne est retentée 3 fois au plus, une lecture 5xx aussi ; un ``POST`` de commande n'est JAMAIS rejoué |
| 429 | l'attente demandée est respectée si elle est courte ; au-delà, ``limite_atteinte`` sans insister |
| 401 | ``jeton_refuse`` ; la prise prévient son écouteur (la liaison passera à « rompue ») |
| erreurs | un 422 devient un code fermé et le NOM du champ, jamais le message de HubRise |
| envoi | la commande part avec NOTRE numéro en ``private_ref`` ; la réponse donne l'identifiant de la caisse |
| recherche | ``chercher`` interroge par ``private_ref`` ; vide : ``None`` |
| état et ruptures | ``PATCH /location`` pour l'état ; la reprise d'un produit part en ``PATCH`` avec ``stock: null`` |
| sans accès | la prise du registre refuse tout geste (``PrisePasBranchee``) |
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from api.services.restauration.caisse.prises.adresses import AdresseRefusee
from api.services.restauration.caisse.prises.hubrise_client import ClientHubrise, ErreurHubrise, JetonRefuse, echanger_le_code
from api.services.restauration.caisse.prises.prise import PrisePasBranchee
from api.services.restauration.caisse.prises.prise_hubrise import PriseHubrise

DOSSIER = Path(__file__).parent / "reponses_hubrise"
JETON = "jeton-de-test-secret-123"


def _enregistree(nom: str) -> dict:
    return json.loads((DOSSIER / nom).read_text(encoding="utf-8"))["reponse"]["corps"]


class Faux:
    """Un transport enregistré : rend les réponses dans l'ordre (la dernière se répète) et note les demandes."""

    def __init__(self, *reponses):
        self.reponses, self.demandes = list(reponses), []

    def __call__(self, demande: httpx.Request) -> httpx.Response:
        self.demandes.append(demande)
        r = self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0]
        if isinstance(r, Exception):
            raise r
        return r


def _client(faux: Faux, **plus) -> ClientHubrise:
    pauses: list[float] = []

    async def attendre(s):
        pauses.append(s)

    c = ClientHubrise(JETON, point_de_vente="w8xvp-0", catalogue="3pmq9", liste_clients="w2dd8", transport=httpx.MockTransport(faux), attendre=attendre, **plus)
    c.pauses = pauses
    return c


def _json(code=200, corps=None, **tetes):
    return httpx.Response(code, json=corps, headers=tetes)


async def test_une_adresse_hors_de_la_liste_fermee_ne_sort_jamais_et_le_jeton_ne_s_affiche_pas():
    faux = Faux(_json(200, {}))
    mauvais = ClientHubrise(JETON, transport=httpx.MockTransport(faux), base="https://evil.example/v1")
    with pytest.raises(AdresseRefusee):
        await mauvais.requete("GET", "/location")
    assert faux.demandes == []
    bon = _client(faux)
    await bon.requete("GET", "/location")
    assert faux.demandes[0].headers["x-access-token"] == JETON
    assert JETON not in repr(bon)


async def test_une_panne_est_retentee_trois_fois_au_plus_un_post_de_commande_jamais():
    faux = Faux(httpx.ConnectError("boom"))
    c = _client(faux)
    with pytest.raises(ErreurHubrise) as e:
        await c.requete("GET", "/location")
    assert e.value.code == "caisse_injoignable" and len(faux.demandes) == 3 and len(c.pauses) == 2
    faux = Faux(_json(503, {}), _json(200, {"id": "w8xvp-0"}))
    assert (await _client(faux).requete("GET", "/location"))["id"] == "w8xvp-0" and len(faux.demandes) == 2
    faux = Faux(httpx.ReadTimeout("lent"))
    with pytest.raises(ErreurHubrise):
        await _client(faux).requete("POST", "/location/orders", corps={"status": "new"})
    assert len(faux.demandes) == 1  # jamais deux commandes


async def test_un_429_court_est_attendu_un_long_n_est_pas_insiste():
    faux = Faux(_json(429, {}, **{"retry-after": "2"}), _json(200, {"ok": 1}))
    c = _client(faux)
    assert (await c.requete("GET", "/location"))["ok"] == 1 and c.pauses == [2.0]
    faux = Faux(_json(429, {}, **{"retry-after": "60"}))
    c = _client(faux)
    with pytest.raises(ErreurHubrise) as e:
        await c.requete("GET", "/location")
    assert e.value.code == "limite_atteinte" and len(faux.demandes) == 1


async def test_un_401_est_un_jeton_refuse_et_la_prise_previent_la_liaison():
    prevenu = []

    async def ecouteur():
        prevenu.append(True)

    faux = Faux(httpx.Response(401, json=_enregistree("18-erreur-jeton-faux.json")))
    prise = PriseHubrise(_client(faux), sur_jeton_refuse=ecouteur)
    with pytest.raises(JetonRefuse):
        await prise.lire_etat()
    assert prevenu == [True] and len(faux.demandes) == 1  # pas de nouvelle tentative sur un jeton faux


async def test_un_422_devient_un_code_et_le_nom_du_champ_jamais_le_message():
    faux = Faux(httpx.Response(422, json=_enregistree("16-erreur-montant-mal-ecrit.json")))
    with pytest.raises(ErreurHubrise) as e:
        await _client(faux).requete("PUT", "/x")
    assert e.value.code == "reponse_inattendue" and e.value.champ == "/items/0/price" and "invalid" not in str(e.value)


async def test_l_envoi_part_avec_notre_numero_et_rend_l_identifiant_de_la_caisse():
    faux = Faux(httpx.Response(200, json=_enregistree("12-commande-simple.json")))
    prise = PriseHubrise(_client(faux))
    commande = {"numero": "8f0d6c64-6d62-4a42-9c0e-0c1c2c3c4c5c", "mode": "emporter", "client": {"telephone": "+33600000001"},
                "lignes": [{"code_caisse": "REINE-S", "nom": "Reine", "prix_unitaire": 1250, "quantite": 1}], "paiement": {"moyens": []}}
    r = await prise.envoyer_commande(commande)
    corps = json.loads(faux.demandes[0].content)
    assert faux.demandes[0].method == "POST" and faux.demandes[0].url.path.endswith("/location/orders") and corps["private_ref"] == commande["numero"]
    assert r.statut == "ENVOYEE" and r.ref_fournisseur and r.etape == "inconnu"  # « new » : pas encore reçue par la caisse, l'outil dira TRANSMISE


async def test_un_422_a_l_envoi_est_un_refus_et_une_panne_une_reprise():
    commande = {"numero": "n", "mode": "emporter", "client": {}, "lignes": [{"code_caisse": "X", "nom": "x", "prix_unitaire": 100, "quantite": 1}], "paiement": {"moyens": []}}
    # lot 19 bis (N4) : un 422 relit d'abord la commande par notre numéro (état) ; la caisse ne la connaît pas : c'est un vrai refus
    refus = await PriseHubrise(_client(Faux(httpx.Response(422, json=_enregistree("17-erreur-formule-absente.json")), httpx.Response(200, json=[])))).envoyer_commande(commande)
    assert (refus.statut, refus.raison) == ("REFUSEE", "autre")
    panne = await PriseHubrise(_client(Faux(httpx.Response(500, json={})))).envoyer_commande(commande)
    assert (panne.statut, panne.raison) == ("INDISPONIBLE", "caisse_injoignable")


async def test_chercher_par_notre_numero_etat_et_ruptures():
    faux = Faux(httpx.Response(200, json=_enregistree("20-commandes-par-reference.json")), httpx.Response(200, json=[]))
    prise = PriseHubrise(_client(faux))
    trouvee = await prise.chercher_commande("mark-test-1")
    assert faux.demandes[0].url.params["private_ref"] == "mark-test-1" and trouvee["ref_fournisseur"] == "8qknnxn"
    assert await prise.chercher_commande("autre") is None

    async def genre(code):
        return {"REINE-S": "declinaison", "SUPP-OEUF": "option"}.get(code)

    faux = Faux(httpx.Response(200, json={}))
    prise = PriseHubrise(_client(faux), genre_de_code=genre)
    await prise.poser_etat({"mode": "deborde", "minutes_en_plus": 15})
    assert faux.demandes[0].method == "PATCH" and json.loads(faux.demandes[0].content) == {"order_acceptance": {"mode": "busy", "extra_preparation_time": 15}}
    await prise.poser_rupture("REINE-S", True)
    r = faux.demandes[1]
    assert r.method == "PATCH" and r.url.path.endswith("/catalogs/3pmq9/locations/w8xvp-0/inventory") and json.loads(r.content) == [{"sku_ref": "REINE-S", "stock": None}]
    with pytest.raises(ErreurHubrise):
        await prise.poser_rupture("INCONNU", False)  # un code que la carte ne connaît pas n'est jamais poussé
    assert len(faux.demandes) == 2


async def test_l_echange_du_code_rend_le_jeton_et_un_code_use_est_refuse():
    ok = Faux(httpx.Response(200, json={"access_token": "t", "location_id": "w8xvp-0", "catalog_id": "3pmq9", "customer_list_id": "w2dd8"}))
    donnees = await echanger_le_code("code", "client", "secret", transport=httpx.MockTransport(ok))
    assert donnees["location_id"] == "w8xvp-0" and ok.demandes[0].headers["authorization"].startswith("Basic ") and b"secret" not in ok.demandes[0].content
    with pytest.raises(ErreurHubrise) as e:
        await echanger_le_code("code", "client", "secret", transport=httpx.MockTransport(Faux(httpx.Response(400, json={}))))
    assert e.value.code == "jeton_refuse"
    with pytest.raises(ErreurHubrise):
        await echanger_le_code("code", "client", "secret", transport=httpx.MockTransport(Faux(httpx.Response(200, json={"access_token": "t"}))))


async def test_la_prise_sans_acces_refuse_tout_geste():
    with pytest.raises(PrisePasBranchee):
        await PriseHubrise().chercher_commande("x")
