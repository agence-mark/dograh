"""[.mark] Clôture, SA-3 (D18) : les limites du moteur du planificateur sont réglables (avancé).

| Test | Ce qu'il prouve |
|---|---|
| défauts | les valeurs d'avant (40 lieux, 8 en parallèle, 2,5 s, 1,5 s, 0,6, 1 h, 4 h) |
| bornes | une faute de frappe est refusée |
| route | un compte écrit et relit ses réglages ; une autre organisation garde les siens (vraie base) |
| géocodeur | le délai et la confiance minimale posés sont ceux de la requête |
| lieux | le plafond de lieux posé borne les adresses placées |
| pose | la durée posée est celle gardée par Redis |
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from api.schemas.planificateur import ReglagesMoteurPlanificateur
from api.services.planificateur import moteur, pose, trajets
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)


def test_les_defauts_sont_les_valeurs_d_avant():
    m = ReglagesMoteurPlanificateur()
    assert (m.max_lieux, m.parallele_lieux, m.temps_max_lieux_s, m.geocodage_delai_s, m.geocodage_score_min, m.geocodage_memoire_s, m.pose_duree_s) == (
        40, 8, 2.5, 1.5, 0.6, 3600, 4 * 3600)


@pytest.mark.parametrize("champ, mauvaise", [("max_lieux", 0), ("max_lieux", 9999), ("parallele_lieux", 0), ("temps_max_lieux_s", 0), ("geocodage_delai_s", 100),
                                             ("geocodage_score_min", 0), ("geocodage_score_min", 2), ("geocodage_memoire_s", 1), ("pose_duree_s", 5)])
def test_une_faute_de_frappe_est_refusee(champ, mauvaise):
    with pytest.raises(ValidationError):
        ReglagesMoteurPlanificateur(**{champ: mauvaise})


@pytest.mark.usefixtures("sans_preparation_des_organisations")
async def test_la_route_ecrit_et_relit_par_organisation(db_session):
    a = await creer_organisation(db_session, "sa3-mot-a")
    b = await creer_organisation(db_session, "sa3-mot-b")
    _, jeton = await creer_compte(db_session, "sa3-moteur@example.com", role="Administrateur", organisations=[a, b])
    async with client_http() as c:
        defaut = await c.get("/api/v1/organizations/planificateur-moteur", headers=entetes(jeton, a))
        ecrit = await c.put("/api/v1/organizations/planificateur-moteur", headers=entetes(jeton, a), json={**defaut.json(), "max_lieux": 12})
        relu_a = await c.get("/api/v1/organizations/planificateur-moteur", headers=entetes(jeton, a))
        relu_b = await c.get("/api/v1/organizations/planificateur-moteur", headers=entetes(jeton, b))
        refuse = await c.put("/api/v1/organizations/planificateur-moteur", headers=entetes(jeton, a), json={**defaut.json(), "max_lieux": 0})
    assert defaut.json()["max_lieux"] == 40
    assert ecrit.status_code == 200 and relu_a.json()["max_lieux"] == 12
    assert relu_b.json()["max_lieux"] == 40  # l'autre organisation garde les valeurs d'avant
    assert refuse.status_code == 422
    assert (await moteur.lire_reglages(a)).max_lieux == 12


async def test_le_geocodeur_lit_les_reglages_poses(monkeypatch):
    vus = {}

    def client(**options):
        vus["delai"] = options.get("timeout")
        corps = {"features": [{"properties": {"score": 0.55, "citycode": "60100", "label": "1 rue X"}, "geometry": {"coordinates": [2.5, 49.2]}}]}
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=corps)), **options)

    monkeypatch.setattr(trajets, "nouveau_client", client)
    trajets.oublier()
    trajets.MOTEUR.set(ReglagesMoteurPlanificateur(geocodage_score_min=0.5, geocodage_delai_s=4.0))
    assert (await trajets.geocoder("1 rue X Creil")) is not None and vus["delai"] == 4.0
    trajets.oublier()
    trajets.MOTEUR.set(None)  # sans réglage : 0,6 d'avant, 0,55 n'est pas cru
    assert (await trajets.geocoder("1 rue X Creil")) is None and vus["delai"] == 1.5
    trajets.oublier()


async def test_le_plafond_de_lieux_pose_borne_les_adresses_placees(monkeypatch):
    from api.services.hub import agenda as hub_agenda
    from api.services.planificateur import action

    demandes = []

    async def positionner(lieux, delai, parallele=8):
        demandes.append((len(lieux), parallele))
        return {}

    async def evenements(*a, **k):
        return [{"lieu": f"{i} rue de la Paix 60100 Creil", "debut": None, "fin": None} for i in range(30)]

    monkeypatch.setattr(action, "_positionner", positionner)
    monkeypatch.setattr(hub_agenda, "evenements", evenements)
    trajets.MOTEUR.set(ReglagesMoteurPlanificateur(max_lieux=7, parallele_lieux=3))
    ctx = type("C", (), {"organization_id": 1})()
    try:
        await action.etapes_des_agendas(ctx, "x", ["a"], None, None, 1.0)
    except Exception:  # noqa: BLE001 -- seule la borne des lieux nous intéresse
        pass
    assert demandes == [(7, 3)]
    trajets.MOTEUR.set(None)


async def test_la_pose_garde_la_duree_posee(db_session, monkeypatch):
    org = await creer_organisation(db_session, "sa3-mot-pose")
    await moteur.ecrire_reglages(org, ReglagesMoteurPlanificateur(pose_duree_s=900))
    vus = {}

    class Faux:
        async def set(self, cle, valeur, ex=None):
            vus["ex"] = ex

        async def delete(self, cle):
            pass

    async def faux_redis():
        return Faux()

    monkeypatch.setattr(pose, "_redis", faux_redis)
    await pose._ecrire(org, 5, {"en_cours": {"x": 1}})
    assert vus["ex"] == 900
