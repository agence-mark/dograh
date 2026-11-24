"""[.mark] Plan final Partie 1, lot 10 (A4, reprise 2e audit) : un 403 n'est définitif que sur le point de vente, comme le 404 ; le 401 l'est partout.

Scénario : la connexion n'a pas le droit de lire la liste des clients : ``GET /customer_lists/...`` répond 403 pendant un appel. Avant, tout 403 était un refus définitif : la liaison passait à « rompue »
alors que les commandes partent toujours. De même, un 403 à l'abonnement (``POST /callback``) faisait échouer le branchement au lieu de passer en mode passif comme avant le lot.
"""

from __future__ import annotations

import httpx
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.services.restauration.caisse.prises import hubrise_client as hc
from api.services.restauration.caisse.prises import hubrise_liaison as liaison
from api.tests.mark import equipe_commun as _equipe
from api.tests.mark import test_contacts_portail as _contacts
from api.tests.mark import test_restauration_caisse_routes as _routes
from api.tests.mark.test_restauration_envoi_caisse import _etablissement_branche

sans_preparation_des_organisations = _equipe.sans_preparation_des_organisations
seconde_base = _contacts.seconde_base
application_configuree = _routes.application_configuree


async def _sans_attente(secondes: float) -> None:
    return None


def _client(code: int) -> hc.ClientHubrise:
    return hc.ClientHubrise("jeton", point_de_vente="pdv", transport=httpx.MockTransport(lambda r: httpx.Response(code, json={})), attendre=_sans_attente)


async def test_un_403_sur_la_liste_des_clients_n_est_pas_un_refus_definitif():
    with pytest.raises(hc.ErreurHubrise) as erreur:
        await _client(403).requete("GET", "/customer_lists/liste-1")
    assert erreur.value.definitif is False  # avant : JetonRefuse, la liaison était rompue


@pytest.mark.parametrize("chemin", ["/location", "/location/orders"])
async def test_un_403_sur_le_point_de_vente_reste_un_refus_definitif(chemin):
    with pytest.raises(hc.JetonRefuse):
        await _client(403).requete("GET", chemin)


@pytest.mark.parametrize("chemin", ["/location", "/customer_lists/liste-1", "/callback"])
async def test_un_401_reste_definitif_partout(chemin):
    with pytest.raises(hc.JetonRefuse):
        await _client(401).requete("GET", chemin)


async def test_un_403_a_l_abonnement_passe_en_mode_passif_au_lieu_de_faire_echouer_le_branchement(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    cas, etab = await _etablissement_branche(db_session, seconde_base)

    def abonnement_refuse_puis_passif(requete: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if b'"url":null' in requete.content.replace(b" ", b"") else 403, json={})

    client = hc.ClientHubrise("jeton", point_de_vente="pdv", transport=httpx.MockTransport(abonnement_refuse_puis_passif), attendre=_sans_attente)
    c = await schema.connecter(cas.base_a)
    try:
        assert await liaison.s_abonner(client, c, etab) is True  # avant : JetonRefuse, le branchement échouait
        assert (await lia.liaison(c, etab))["etat"] != "rompue"
    finally:
        await c.close()
