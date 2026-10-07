"""[.mark] Non-regression test for the fairness window of the « in turn » distribution (chantier
l-agent-collegue, R-7, retouche du planificateur; migration 013).

The questions this file answers (R-7, G1, R1, R7):

    Is the window a setting of the planner's table with its inheritance (organization, then
    establishment, 30 days by default) and its bounds (1 to 365), in the schema AND in the database?
    Is migration 013 additive (an organization's rows survive, a version-12 database is read without
    failing)? Can it be set by hand (the documented route, a row of the table), journalled like the
    rest of the referential? And, through the engine's REAL dispatcher and a real client database:
    does the number of days set really decide whose turn it is (the known red case: three
    appointments given 20 days ago count with the default window, and do not with 10 days)?

Why it exists
-------------
🔴 R1/R7: a setting that is saved but never read is a lie on screen. Only the real route, with
appointments given at a known date, catches it.

No request leaves the machine; no SMS, no call.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.schemas.planificateur import (
    DEFAUTS,
    Planificateur,
    ReglagesPlanificateur,
    effectifs,
)
from api.tests.mark import test_planificateur as _planificateur
from api.tests.mark.test_planificateur import (  # noqa: F401
    _appeler,
    _moteur,
    _outil,
    _regles,
    base_essai,
    base_v4,
    modele,
    smtp,
)

base_prete = _planificateur.base_prete  # the client database, fully migrated
installe = _planificateur.installe  # the planner's fixture (the world of the real-route tests)

# --------------------------------------------------------------------------- #
# 1. The setting, its inheritance and its bounds
# --------------------------------------------------------------------------- #


def test_la_fenetre_vaut_trente_jours_par_defaut_et_ses_bornes_sont_un_a_trois_cent_soixante_cinq():
    assert DEFAUTS.fenetre_equite_jours == 30
    assert ReglagesPlanificateur().fenetre_equite_jours is None  # empty = inherited
    assert effectifs().fenetre_equite_jours == 30
    assert ReglagesPlanificateur(fenetre_equite_jours=1).fenetre_equite_jours == 1
    assert ReglagesPlanificateur(fenetre_equite_jours=365).fenetre_equite_jours == 365
    for hors in (0, -3, 366):
        with pytest.raises(ValidationError):
            ReglagesPlanificateur(fenetre_equite_jours=hors)
    # Published to the screen with its bounds (the form shows them, the server enforces them).
    propriete = ReglagesPlanificateur.model_json_schema()["properties"]["fenetre_equite_jours"]
    assert {"minimum": 1, "maximum": 365} == {k: v for k, v in
                                              next(a for a in propriete["anyOf"] if "minimum" in a).items()
                                              if k in ("minimum", "maximum")}


def test_l_etablissement_herite_de_l_organisation_qui_herite_du_defaut():
    organisation = ReglagesPlanificateur(fenetre_equite_jours=45)
    nord = ReglagesPlanificateur(fenetre_equite_jours=7)
    sud = ReglagesPlanificateur()  # nothing of its own
    assert effectifs(organisation, nord).fenetre_equite_jours == 7
    assert effectifs(organisation, sud).fenetre_equite_jours == 45
    assert effectifs(ReglagesPlanificateur(), sud).fenetre_equite_jours == 30


# --------------------------------------------------------------------------- #
# 2. The database: migration 013 (additive), bounds, journal, by hand
# --------------------------------------------------------------------------- #


async def test_la_migration_013_est_additive_et_une_base_en_version_12_se_lit_sans_echec(base_prete):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.planificateur import (
        ecrire_planificateur,
        lire_planificateur,
    )

    connexion = await schema.connecter_proprietaire(base_prete)  # DDL and « Upgrade »: the owner's
    try:
        assert schema.version_attendue() == 13 and await schema.version_de(connexion) == 13
        await connexion.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('E')")
        await ecrire_planificateur(
            connexion, Planificateur(reglages=ReglagesPlanificateur(nombre_creneaux=2, repartition="tour_de_role")), "test")
        # Back to version 12: the column and the version row are gone (what a database not yet upgraded is).
        await connexion.execute("ALTER TABLE mark.reglage_planificateur DROP COLUMN fenetre_equite_jours")
        await connexion.execute("DELETE FROM mark.schema_version WHERE version = 13")
        lu = await lire_planificateur(connexion)  # a call in the gap between the deployment and « Upgrade »
        assert lu.reglages.nombre_creneaux == 2 and lu.reglages.fenetre_equite_jours is None
        assert effectifs(lu.reglages).fenetre_equite_jours == 30
        # « Upgrade »: only 013 is played, the organization's row survives, the new field is empty.
        assert await schema.appliquer_migrations(connexion) == [13]
        lu = await lire_planificateur(connexion)
        assert (lu.reglages.nombre_creneaux, lu.reglages.repartition, lu.reglages.fenetre_equite_jours) == (
            2, "tour_de_role", None)
        assert await schema.version_de(connexion) == 13
    finally:
        await connexion.close()


async def test_la_base_refuse_une_fenetre_hors_bornes_et_journalise_le_changement_a_la_main(base_prete):
    import asyncpg

    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.planificateur import lire_planificateur

    connexion = await schema.connecter(base_prete)
    try:
        await connexion.execute("INSERT INTO mark.reglage_planificateur (site_id) VALUES (NULL)")
        for hors in (0, 366):
            with pytest.raises(asyncpg.CheckViolationError):
                await connexion.execute("UPDATE mark.reglage_planificateur SET fenetre_equite_jours = $1", hors)
        # By hand, on the row of the table: read as set, and written to the journal of the referential.
        await connexion.execute("UPDATE mark.reglage_planificateur SET fenetre_equite_jours = 14")
        assert (await lire_planificateur(connexion)).reglages.fenetre_equite_jours == 14
        assert await connexion.fetchval(
            "SELECT count(*) FROM mark.journal_modif WHERE table_nom = 'reglage_planificateur' "
            "AND champ = 'update' AND apres ->> 'fenetre_equite_jours' = '14'"
        ) == 1
    finally:
        await connexion.close()


def test_la_route_documentee_regle_la_fenetre_et_refuse_les_bornes(base_prete, monkeypatch):
    """G1, « by hand »: GET/PUT /organizations/planificateur."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import base_client as route
    from api.services.auth.depends import get_user_with_selected_organization

    async def nom(_organisation):
        return base_prete

    monkeypatch.setattr(route.rattachement, "nom_de_la_base", nom)
    app = FastAPI()
    app.include_router(route.routeur_planificateur)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, provider_id="p", selected_organization_id=1, email="essai@example.org")
    client = TestClient(app)
    lu = client.get("/organizations/planificateur").json()
    assert lu["defauts"]["fenetre_equite_jours"] == 30 and lu["reglages"].get("fenetre_equite_jours") is None
    assert client.put("/organizations/planificateur", json={"reglages": {"fenetre_equite_jours": 0}}).status_code == 422
    assert client.put("/organizations/planificateur", json={"reglages": {"fenetre_equite_jours": 366}}).status_code == 422
    bon = client.put("/organizations/planificateur", json={"reglages": {"fenetre_equite_jours": 45}})
    assert bon.status_code == 200, bon.text
    assert client.get("/organizations/planificateur").json()["reglages"]["fenetre_equite_jours"] == 45
    # Emptied: inherited again.
    vide = client.put("/organizations/planificateur", json={"reglages": {"fenetre_equite_jours": None}})
    assert vide.status_code == 200 and vide.json()["reglages"].get("fenetre_equite_jours") is None


# --------------------------------------------------------------------------- #
# 3. Through the engine's real dispatcher: the number of days decides whose turn it is (R1)
# --------------------------------------------------------------------------- #


async def _donner_trois_rendez_vous_a_camille_il_y_a_vingt_jours(installe) -> None:
    from api.db.bases_clients import connexion as schema

    connexion = await schema.connecter(installe.base)
    try:
        camille = await connexion.fetchval("SELECT id FROM mark.personne WHERE cle = 'camille'")
        contact = await connexion.fetchval("INSERT INTO mark.contact (nom) VALUES ('Essai') RETURNING id")
        demande = await connexion.fetchval(
            "INSERT INTO mark.demande (contact_id, type, resume) VALUES ($1, 'sav', 'essai') RETURNING id", contact)
        for _ in range(3):
            rendez_vous = await connexion.fetchval(
                "INSERT INTO mark.rendez_vous (demande_id, debut, fin, origine) "
                "VALUES ($1, now() - interval '20 days', now() - interval '20 days' + interval '1 hour', 'agent') RETURNING id",
                demande)
            await connexion.execute(
                "INSERT INTO mark.attribution (rendez_vous_id, personne_id, type_code, mode, rang, le) "
                "VALUES ($1, $2, 'visite', 'tour_de_role', 1, now() - interval '20 days')", rendez_vous, camille)
    finally:
        await connexion.close()


async def _premiere_personne(installe, monkeypatch) -> str:
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux")])
    await mgr.register_handlers(["uuid-Creneaux"])
    reponse = await _appeler(enregistres["creneaux"][0], {"souhait": "jeudi"})
    assert reponse["creneaux"]
    [estampille] = engine._gathered_context["planificateur"]
    premier = estampille["creneaux"][0]
    assert premier["rang"] == 1  # the first of the order gives the first slot
    return premier["personne"]


async def test_le_nombre_de_jours_regle_decide_a_qui_c_est_le_tour_par_le_vrai_repartiteur(installe, monkeypatch):
    await _donner_trois_rendez_vous_a_camille_il_y_a_vingt_jours(installe)
    # Default window (30 days): Camille already has 3 appointments in it, Sacha none -> Sacha's turn.
    await _regles(installe, repartition="tour_de_role")
    assert await _premiere_personne(installe, monkeypatch) == "sacha"
    # A window of 10 days forgets them (given 20 days ago): both at zero, the team's order -> Camille.
    await _regles(installe, repartition="tour_de_role", fenetre_equite_jours=10)
    assert await _premiere_personne(installe, monkeypatch) == "camille"
    # 20 days is not enough to forget them, 21 days still counts them: the window's edge.
    await _regles(installe, repartition="tour_de_role", fenetre_equite_jours=21)
    assert await _premiere_personne(installe, monkeypatch) == "sacha"
    await _regles(installe, repartition="tour_de_role", fenetre_equite_jours=19)
    assert await _premiere_personne(installe, monkeypatch) == "camille"
