"""[.mark] Chantier agents-specialises, lot 3 : la fiche de l'appel partagée.

Plan `Labo-agent-vocal/plans/agents-specialises/` (A4, A7 ; 2A, 2B, 2C du plan du 13/10).
Par les VRAIES routes du clavier (sessions, messages) ; seuls les modèles sont écrits
d'avance.

| Test | Ce qu'il prouve |
|---|---|
| fiche continue | un champ noté chez A reste noté chez B ; B a l'outil de note ; un champ propre à B s'ajoute à la fiche |
| même nom | même nom = un seul champ, la définition de l'agent qui a décroché |
| seul | B essayé seul garde sa fiche à lui |
| transfert à l'ouverture | un agent appelé dont la première étape porte un outil de transfert commence par le transfert, entreprise ouverte |
"""

import asyncio
import copy
from unittest.mock import AsyncMock, patch

import pytest

from api.services.groupe.fiche import champs_fusionnes
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_TRANSFERT_GARANTI,
    ReglagesFiche,
)
from api.services.workflow.pipecat_engine import (
    CLE_ETAT_OUVERTURE,
    TRACE_TRANSFERTS_GARANTIS,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_passation_clavier import (
    _agent_de_l_organisation,
    _appel,
    _dit,
    _outil_de_passation,
    _principal,
    _republier,
    _session,
    _specialise,
    _texte,
    _vide,
)
from pipecat.tests import MockLLMService

CHAMP_B = {"nom": "appareil", "origine": "dicte", "description": "L'appareil"}


def _fiche_b():
    return {
        "fiche_au_fil_de_leau": True,
        "fiche_champs": [
            {"nom": "nom", "origine": "dicte", "description": "AUTRE définition du nom"},
            CHAMP_B,
        ],
    }


def _noter(arguments, identifiant):
    return MockLLMService.create_function_call_chunks(
        "noter_information", arguments, tool_call_id=identifiant
    )


async def _groupe(db_session, async_session, *, reglages_b=None, definition_b=None, reglages_a=None):
    base = copy.deepcopy(FICHE)
    user, principal = await _monter(db_session, async_session, base, _principal())
    organisation = principal.organization_id
    specialise = await _agent_de_l_organisation(
        db_session,
        user,
        organisation,
        "Spécialisé",
        definition_b or _specialise(),
        {**(reglages_b or _fiche_b()), "agent_principal_id": principal.id},
    )
    outil = await _outil_de_passation(db_session, user, organisation, "Passer a S", specialise.id)
    await _republier(
        db_session,
        principal,
        _principal([outil.tool_uuid]),
        {**base, "agents_specialises": [specialise.id], **(reglages_a or {})},
    )
    return user, principal, specialise


@pytest.mark.asyncio
async def test_la_fiche_continue_chez_l_agent_appele_et_s_enrichit(
    db_session, async_session, test_client_factory
):
    user, principal, _ = await _groupe(db_session, async_session)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            # Tour 1 : A note le nom, puis passe la main.
            _dit(_noter({"nom": "Lemaire"}, "n1"), [*_appel("passer_a_s", "p1")]),
            _vide(),  # la fabrique
            _dit(_texte("Quel est votre appareil ?")),  # B ouvre
            # Tour 2 : modèle du premier agent (non joué), puis B note SON champ.
            _vide(),
            _dit(_noter({"appareil": "poêle"}, "n2"), _texte("C'est noté.")),
        ],
        ["je m'appelle Lemaire, j'ai une panne", "c'est un poêle"],
    )
    fiche = reponses[1]["checkpoint"]["gathered_context"]
    assert fiche.get("nom") == "Lemaire", fiche
    assert fiche.get("appareil") == "poêle", fiche
    assert any(
        e.get("champ") == "appareil" and e.get("statut") == "ecrit"
        for e in fiche.get("fiche_journal") or []
    ), fiche.get("fiche_journal")


def test_meme_nom_un_seul_champ_la_definition_de_celui_qui_a_decroche():
    fiche_a = ReglagesFiche.depuis(copy.deepcopy(FICHE))
    champs = champs_fusionnes(fiche_a, _fiche_b())
    noms = [c.nom for c in champs]
    assert noms.count("nom") == 1 and "appareil" in noms, noms
    nom = next(c for c in champs if c.nom == "nom")
    assert nom.description == "Nom de famille", nom.description
    # Rien de nouveau : rien à fusionner.
    assert champs_fusionnes(fiche_a, copy.deepcopy(FICHE)) is None
    # Un agent sans fiche : rien.
    assert champs_fusionnes(fiche_a, {}) is None
    assert champs_fusionnes(None, _fiche_b()) is None


@pytest.mark.asyncio
async def test_l_agent_appele_essaye_seul_garde_sa_fiche(
    db_session, async_session, test_client_factory
):
    _, _, specialise = await _groupe(db_session, async_session)
    from api.db.models import UserModel

    user = await db_session.get_user_by_id(specialise.user_id) if hasattr(
        db_session, "get_user_by_id"
    ) else None
    if user is None:
        pytest.skip("lecture de l'utilisateur indisponible dans ce client")
    assert isinstance(user, UserModel)
    reponses = await _session(
        test_client_factory,
        user,
        specialise,
        [_vide(), _dit(_noter({"appareil": "insert"}, "n1"), _texte("C'est noté."))],
        ["c'est un insert"],
    )
    fiche = reponses[0]["checkpoint"]["gathered_context"]
    assert fiche.get("appareil") == "insert", fiche


@pytest.mark.asyncio
async def test_l_agent_appele_a_transfert_commence_par_le_transfert(
    db_session, async_session, test_client_factory
):
    from api.services.pipecat import etat_ouverture
    from api.services.workflow import text_chat_runner

    base = copy.deepcopy(FICHE)
    user, principal = await _monter(db_session, async_session, base, _principal())
    organisation = principal.organization_id
    renvoi = await db_session.create_tool(
        organization_id=organisation,
        user_id=user.id,
        name="Transfer team",
        description="Transfer the caller to the team",
        category="transfer_call",
        definition={
            "schema_version": 1,
            "type": "transfer_call",
            "config": {"destination": "+33600000000", "timeout": 20},
        },
    )
    definition_b = _specialise()
    definition_b["nodes"][0]["data"]["tool_uuids"] = [renvoi.tool_uuid]
    specialise = await _agent_de_l_organisation(
        db_session,
        user,
        organisation,
        "Spécialisé",
        definition_b,
        {**base, "agent_principal_id": principal.id},
    )
    outil = await _outil_de_passation(db_session, user, organisation, "Passer a S", specialise.id)
    await _republier(
        db_session,
        principal,
        _principal([outil.tool_uuid]),
        {**base, CLE_TRANSFERT_GARANTI: True, "agents_specialises": [specialise.id]},
    )
    modeles = [
        _vide(),
        _dit([*_appel("passer_a_s", "p1")]),
        _vide(),
        _dit(_texte("Je vous mets en relation avec le magasin, ne quittez pas.")),
        *[_vide() for _ in range(3)],
    ]
    vrai = etat_ouverture.injecter_etat_ouverture

    def ouvert(contexte, *a, **k):
        return {**vrai(contexte, *a, **k), CLE_ETAT_OUVERTURE: "OUVERT"}

    async with test_client_factory(user) as client:
        with (
            patch(
                "api.services.workflow.text_chat_runner.create_llm_service",
                side_effect=modeles,
            ),
            patch(
                "api.services.workflow.text_chat_runner.db_client.has_active_recordings",
                new=AsyncMock(return_value=False),
            ),
            patch.object(text_chat_runner, "injecter_etat_ouverture", side_effect=ouvert),
        ):
            creee = await client.post(
                f"/api/v1/workflow/{principal.id}/text-chat/sessions", json={}
            )
            session = creee.json()
            run_id = session["workflow_run_id"]
            url = f"/api/v1/workflow/{principal.id}/runs/{run_id}/renvoi-en-test"

            async def page():
                for _ in range(200):
                    etat = await client.get(url)
                    if etat.status_code == 200 and etat.json()["en_attente"]:
                        await client.post(url, json={"accepte": True})
                        return
                    await asyncio.sleep(0.1)

            tache = asyncio.create_task(page())
            reponse = await client.post(
                f"/api/v1/workflow/{principal.id}/text-chat/sessions/{run_id}/messages",
                json={"text": "mon poêle est en panne", "expected_revision": session["revision"]},
            )
            tache.cancel()
    assert reponse.status_code == 200, reponse.text
    fiche = reponse.json()["checkpoint"]["gathered_context"]
    traces = fiche.get(TRACE_TRANSFERTS_GARANTIS) or []
    assert any(t.get("etat") == "lance" for t in traces), traces
