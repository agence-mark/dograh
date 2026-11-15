"""[.mark] Module Restauration, lot 15 : la commande qui se remplit pendant un appel, lue par le portail.

Vraie route, vraie authentification (clé d'API de l'organisation), vrai Redis.

| Test | Ce qu'il prouve |
|---|---|
| le geste | un geste qui change le panier le garde (mode, lignes nom et quantité) avant d'émettre ``commande.panier`` ; un geste qui ne le change pas ne le touche pas |
| la lecture | la route rend le panier de l'appel ; jamais le nom ni l'adresse de l'appelant (aucun autre champ) |
| cloisonnement | la clé d'une autre organisation, un autre établissement de la même organisation, un établissement inconnu : 404 ; un appel inconnu : 404 |
| permission | ``conversations.voir`` au registre ; la route est gelée dans le contrat avec le portail |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.equipe_mark import registre_routes as registre
from api.services.restauration import flux
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements, organisations  # noqa: F401

PANIER = {
    "version": 3, "mode": "emporter", "client": {"prenom": "Sophie", "telephone": "0600000000"}, "adresse": "1 rue des Lilas",
    "lignes": [{"n": 1, "nom": "Regina", "quantite": 2, "code": "R1", "choix": ["grande"], "note": "sans champignons"}, {"n": 2, "nom": "Tiramisu", "quantite": 1}],
}


def _url(etablissement: int, appel: int | str) -> str:
    return f"/api/v1/restauration/etablissements/{etablissement}/appels/{appel}/panier"


async def test_la_route_rend_le_panier_de_l_appel_sans_rien_de_l_appelant(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    await flux.poser_le_panier(cas.a, etab, 4242, PANIER)
    async with client_http() as c:
        r = await c.get(_url(etab, 4242), headers=_cle(cas.cle_a))
    assert r.status_code == 200
    assert r.json() == {"version": 3, "mode": "emporter", "lignes": [{"nom": "Regina", "quantite": 2}, {"nom": "Tiramisu", "quantite": 1}]}
    assert "Sophie" not in r.text and "0600000000" not in r.text and "Lilas" not in r.text and "champignons" not in r.text


async def test_cloisonnement_autre_organisation_autre_etablissement_inconnu(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    un, deux = cas.sites_a
    await flux.poser_le_panier(cas.a, un, 77, PANIER)
    inconnu = max(cas.sites_a + cas.sites_b) + 1000
    async with client_http() as c:
        autre_organisation = await c.get(_url(un, 77), headers=_cle(cas.cle_b))
        autre_etablissement = await c.get(_url(deux, 77), headers=_cle(cas.cle_a))
        etablissement_inconnu = await c.get(_url(inconnu, 77), headers=_cle(cas.cle_a))
        appel_inconnu = await c.get(_url(un, 78), headers=_cle(cas.cle_a))
        sans_cle = await c.get(_url(un, 77))
        mal_forme = await c.get(_url(un, "abc"), headers=_cle(cas.cle_a))
    assert [r.status_code for r in (autre_organisation, autre_etablissement, etablissement_inconnu, appel_inconnu)] == [404, 404, 404, 404]
    assert sans_cle.status_code == 401 and mal_forme.status_code == 422


async def test_un_geste_qui_change_le_panier_le_garde_puis_emet_un_geste_sans_effet_ne_touche_a_rien(organisations):  # noqa: F811
    org, etab = organisations[0], 5
    source = SimpleNamespace(lieu=SimpleNamespace(etablissement_id=etab))
    ctx = SimpleNamespace(organization_id=org, run_id=9001)
    await SourceClasseur.apres_le_geste(source, "ajouter", 2, PANIER, SimpleNamespace(statut="OK", faits={}), ctx)
    assert (await flux.lire_le_panier(org, etab, 9001))["lignes"][0] == {"nom": "Regina", "quantite": 2}
    await SourceClasseur.apres_le_geste(source, "ajouter", 2, {**PANIER, "version": 2, "lignes": []}, SimpleNamespace(statut="OK", faits={}), ctx)  # version inchangée
    assert (await flux.lire_le_panier(org, etab, 9001))["lignes"]  # rien n'a été réécrit


def test_la_route_est_au_registre_avec_sa_permission():
    decision = registre.decision_de("GET", "/restauration/etablissements/{etablissement_id}/appels/{appel_id}/panier")
    assert decision is not None and decision[1] is False
