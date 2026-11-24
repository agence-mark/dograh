"""[.mark] Module Restauration, lot 15 : la route du statut d'une commande, faite par le restaurant depuis le portail (Rush).

Vraie route, vraie authentification (clé d'API de l'organisation), vraie base du client, vrai Redis.

| Test | Ce qu'il prouve |
|---|---|
| le pas | un pas permis change le statut, rend ``{statut}``, journalise la source ``portail`` et émet ``commande.statut`` (source ``portail``) |
| rejeu | le même geste rejoué rend 409 ``DEJA_FAIT`` : rien n'est écrasé, rien n'est émis une seconde fois |
| chemin fermé | un retour en arrière, ou un ``de`` qui n'est plus le statut actuel : 409 ``INTERDIT``, statut inchangé, rien d'émis |
| cloisonnement | la clé d'une autre organisation ne touche pas la commande (404) ; la commande d'un autre établissement de la même organisation : 404 ; un établissement inconnu : 404 ; rien ne bouge, rien n'est émis |
| entrées | sans clé 401 ; statut hors liste, champ en trop, numéro qui n'est pas un identifiant : 422 |
| la caisse | une annulation est dite à la caisse quand la fiche de sa prise sait annuler ; les autres étapes ne lui sont rien dites ; une caisse en panne ne défait pas le geste ; sans prise liée, rien |
| permission | ``portail.ecrire`` pour une clé au registre ; la route est gelée dans le contrat avec le portail |
"""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from api.db.bases_clients import connexion as schema
from api.services.equipe_mark import registre_routes as registre
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.caisse import statut
from api.services.restauration.caisse.prises.fiches import TEST
from api.services.restauration.caisse.prises.prise_essai import PriseTest
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_flux import (  # noqa: F401
    _deux_organisations_avec_des_etablissements,
    _depuis_le_debut,
    _evenements,
    organisations,
)


@pytest.fixture(autouse=True)
def flux_court(monkeypatch):
    monkeypatch.setattr(flux, "BLOCAGE_LECTURE_MS", 150)
    monkeypatch.setattr(flux, "NB_BATTEMENTS_MAX", 1)


async def _commande(base: str, etablissement: int, statut_depart: str = "nouvelle") -> str:
    numero = uuid.uuid4()
    c = await schema.connecter(base)
    try:
        await c.execute(
            "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut) VALUES ($1, $2, $3, 'emporter', 1500, $4)",
            numero, f"C{numero.hex[:3]}", etablissement, statut_depart,
        )
    finally:
        await c.close()
    return str(numero)


async def _statut_de(base: str, numero: str) -> str:
    c = await schema.connecter(base)
    try:
        return await c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero))
    finally:
        await c.close()


async def _evenements_de(organisation: int, etablissement: int, role: str = "equipe") -> list[dict]:
    texte = "".join([m async for m in flux.ecouter(organisation, [etablissement], role=role, reprise=_depuis_le_debut(etablissement), nb_battements_max=1)])
    return [e for e in _evenements(texte) if e["event"] == "commande.statut"]


def _url(etablissement: int, numero: str) -> str:
    return f"/api/v1/restauration/etablissements/{etablissement}/commandes/{numero}/statut"


async def test_un_pas_permis_change_le_statut_journalise_la_source_et_emet(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    numero = await _commande(cas.base_a, etab, "acceptee")
    async with client_http() as c:
        r = await c.post(_url(etab, numero), json={"de": "acceptee", "vers": "en_preparation"}, headers=_cle(cas.cle_a))
    assert r.status_code == 200 and r.json() == {"statut": "en_preparation", "caisse_informee": False}
    assert await _statut_de(cas.base_a, numero) == "en_preparation"
    lus = await _evenements_de(cas.a, etab)
    assert [e["data"]["donnees"] for e in lus] == [{"numero": numero, "de": "acceptee", "vers": "en_preparation", "source": "portail"}]
    cn = await schema.connecter(cas.base_a)
    try:
        journal = await cn.fetch("SELECT * FROM mark.resto_journal ORDER BY 1 DESC LIMIT 3")
    finally:
        await cn.close()
    assert any("portail" in json.dumps(dict(ligne), default=str) for ligne in journal)  # le journal des changements sait la source


async def test_le_meme_geste_rejoue_est_deja_fait_sans_ecraser_ni_emettre_deux_fois(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    numero = await _commande(cas.base_a, etab, "prete")
    async with client_http() as c:
        premier = await c.post(_url(etab, numero), json={"de": "prete", "vers": "terminee"}, headers=_cle(cas.cle_a))
        second = await c.post(_url(etab, numero), json={"de": "prete", "vers": "terminee"}, headers=_cle(cas.cle_a))
    assert premier.status_code == 200
    assert second.status_code == 409 and second.json()["detail"] == {"code": "DEJA_FAIT", "statut": "terminee"}
    assert await _statut_de(cas.base_a, numero) == "terminee"
    assert len(await _evenements_de(cas.a, etab)) == 1


async def test_un_pas_interdit_ou_un_depart_perime_est_refuse_sans_rien_changer(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    numero = await _commande(cas.base_a, etab, "prete")
    async with client_http() as c:
        arriere = await c.post(_url(etab, numero), json={"de": "prete", "vers": "en_preparation"}, headers=_cle(cas.cle_a))
        perime = await c.post(_url(etab, numero), json={"de": "acceptee", "vers": "en_preparation"}, headers=_cle(cas.cle_a))
        d_une_annulee = await _commande(cas.base_a, etab, "annulee")
        depuis_annulee = await c.post(_url(etab, d_une_annulee), json={"de": "annulee", "vers": "prete"}, headers=_cle(cas.cle_a))
    for r in (arriere, perime, depuis_annulee):
        assert r.status_code == 409 and r.json()["detail"]["code"] == "INTERDIT"
    assert await _statut_de(cas.base_a, numero) == "prete" and await _statut_de(cas.base_a, d_une_annulee) == "annulee"
    assert await _evenements_de(cas.a, etab) == []


async def test_cloisonnement_autre_organisation_autre_etablissement_et_etablissement_inconnu(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    un, deux = cas.sites_a
    numero = await _commande(cas.base_a, un, "nouvelle")
    corps = {"de": "nouvelle", "vers": "annulee"}
    inconnu = max(cas.sites_a + cas.sites_b) + 1000
    async with client_http() as c:
        autre_organisation = await c.post(_url(un, numero), json=corps, headers=_cle(cas.cle_b))
        autre_etablissement = await c.post(_url(deux, numero), json=corps, headers=_cle(cas.cle_a))  # même organisation, mauvais établissement
        etablissement_inconnu = await c.post(_url(inconnu, numero), json=corps, headers=_cle(cas.cle_a))
        commande_inconnue = await c.post(_url(un, str(uuid.uuid4())), json=corps, headers=_cle(cas.cle_a))
    # La clé de B vise l'identifiant d'un établissement de A : refusé, qu'il existe ou non chez B.
    assert (autre_organisation.status_code, autre_etablissement.status_code, etablissement_inconnu.status_code, commande_inconnue.status_code) == (404, 404, 404, 404)
    assert await _statut_de(cas.base_a, numero) == "nouvelle"
    assert await _evenements_de(cas.a, un) == [] and await _evenements_de(cas.a, deux) == [] and await _evenements_de(cas.b, cas.sites_b[0]) == []


async def test_les_entrees_sont_validees(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    numero = await _commande(cas.base_a, etab)
    async with client_http() as c:
        sans_cle = await c.post(_url(etab, numero), json={"de": "nouvelle", "vers": "annulee"})
        mauvais = [
            await c.post(_url(etab, numero), json=corps, headers=_cle(cas.cle_a))
            for corps in ({"de": "nouvelle", "vers": "cuite"}, {"de": "nouvelle", "vers": "annulee", "source": "agent"}, {"de": "nouvelle"}, {})
        ]
        pas_un_identifiant = await c.post(_url(etab, "abc"), json={"de": "nouvelle", "vers": "annulee"}, headers=_cle(cas.cle_a))
        etab_zero = await c.post(_url(0, numero), json={"de": "nouvelle", "vers": "annulee"}, headers=_cle(cas.cle_a))
    assert sans_cle.status_code == 401
    assert [r.status_code for r in mauvais] == [422] * 4 and pas_un_identifiant.status_code == 422 and etab_zero.status_code == 422
    assert await _statut_de(cas.base_a, numero) == "nouvelle"


async def test_la_caisse_est_informee_d_une_annulation_seulement_quand_sa_fiche_sait_annuler(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    prise = PriseTest()

    async def resolveur(organisation: int, etablissement: int):
        assert (organisation, etablissement) == (cas.a, etab)
        return prise

    avance = await _commande(cas.base_a, etab, "acceptee")
    a_annuler = await _commande(cas.base_a, etab, "acceptee")
    with statut.remplacer_le_resolveur(resolveur):
        async with client_http() as c:
            r1 = await c.post(_url(etab, avance), json={"de": "acceptee", "vers": "prete"}, headers=_cle(cas.cle_a))
            r2 = await c.post(_url(etab, a_annuler), json={"de": "acceptee", "vers": "annulee"}, headers=_cle(cas.cle_a))
    assert r1.json()["caisse_informee"] is False and r2.json() == {"statut": "annulee", "caisse_informee": True}
    assert prise.annulees == [a_annuler]

    # Une fiche qui ne sait pas annuler : rien, sans erreur.
    prise_muette = PriseTest(capacites=replace(TEST, annulation=False))
    sans_geste = await _commande(cas.base_a, etab, "acceptee")
    with statut.remplacer_le_resolveur(lambda o, e: _rendre(prise_muette)):
        async with client_http() as c:
            r3 = await c.post(_url(etab, sans_geste), json={"de": "acceptee", "vers": "annulee"}, headers=_cle(cas.cle_a))
    assert r3.status_code == 200 and r3.json()["caisse_informee"] is False and prise_muette.annulees == []


async def _rendre(valeur):
    return valeur


async def test_sans_resolveur_la_fiche_de_liaison_de_l_etablissement_donne_la_prise(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    """Lot 9 branché : la prise vient de ``resto_liaison`` ; sans liaison (portail), la caisse n'est pas informée."""
    from api.services.restauration.caisse.prises.prise import poser_prise_de_test

    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    liee, libre = cas.sites_a
    prise = PriseTest()
    poser_prise_de_test(prise)
    try:
        c = await schema.connecter(cas.base_a)
        try:
            await c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test')", liee)
        finally:
            await c.close()
        avec_liaison = await _commande(cas.base_a, liee, "acceptee")
        sans_liaison = await _commande(cas.base_a, libre, "acceptee")
        async with client_http() as client:
            r1 = await client.post(_url(liee, avec_liaison), json={"de": "acceptee", "vers": "annulee"}, headers=_cle(cas.cle_a))
            r2 = await client.post(_url(libre, sans_liaison), json={"de": "acceptee", "vers": "annulee"}, headers=_cle(cas.cle_a))
    finally:
        poser_prise_de_test(None)
    assert r1.status_code == 200 and r1.json()["caisse_informee"] is True and prise.annulees == [avec_liaison]
    assert r2.status_code == 200 and r2.json()["caisse_informee"] is False


async def test_une_caisse_en_panne_ou_un_resolveur_qui_leve_ne_defait_pas_le_geste(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]

    class PrisePanne(PriseTest):
        async def faire_annuler(self, numero):
            raise ConnectionError("caisse injoignable")

    numero = await _commande(cas.base_a, etab, "acceptee")
    with statut.remplacer_le_resolveur(lambda o, e: _rendre(PrisePanne())):
        async with client_http() as c:
            r = await c.post(_url(etab, numero), json={"de": "acceptee", "vers": "annulee"}, headers=_cle(cas.cle_a))
    assert r.status_code == 200 and r.json() == {"statut": "annulee", "caisse_informee": False}
    assert await _statut_de(cas.base_a, numero) == "annulee"
    assert len(await _evenements_de(cas.a, etab)) == 1  # le portail relit : l'événement est parti malgré la caisse


# --------------------------------------------------------------------------- permission et contrat


def test_la_route_a_sa_permission_au_registre_ouverte_a_la_cle():
    from api.services.equipe_mark.permissions import PERMISSIONS_DE_CLE

    decision, _ = registre.decision_de("POST", "/restauration/etablissements/{etablissement_id}/commandes/{numero}/statut")
    assert isinstance(decision, registre.Permission) and decision.cle == "agents.modifier" and decision.pour_cle == "portail.ecrire"
    assert decision.pour_cle in PERMISSIONS_DE_CLE


def test_la_route_est_gelee_dans_le_contrat_avec_le_portail():
    from api.tests.mark.test_contrat_portail_fork import P, ROUTES_DU_PORTAIL

    cle = f"POST {P}/restauration/etablissements/{{etablissement_id}}/commandes/{{numero}}/statut"
    assert ("POST", cle.split(" ", 1)[1]) in ROUTES_DU_PORTAIL
    gele = json.loads((Path(__file__).with_name("contrat_portail_fork.json")).read_text(encoding="utf-8"))[cle]
    assert gele["ouverte_a_la_cle"] is True and gele["permission"] == "agents.modifier" and gele["permission_de_cle"] == "portail.ecrire"
    assert {(p["nom"], p["dans"]) for p in gele["parametres"]} >= {("etablissement_id", "path"), ("numero", "path")}
    assert set(gele["corps"]["application/json"]["properties"]) == {"de", "vers"}
