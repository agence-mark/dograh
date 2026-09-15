"""[.mark] Are the date and time of the call frozen when it is picked up?

The question this file answers, and only this one:

    Does every call carry ``date_appel`` and ``heure_appel``, spoken French,
    Paris time, computed once at set-up -- on the phone and on the keyboard?

Why it exists
-------------
Measured on 2026-09-15: the global prompt of the agent read
``{{current_time_Europe/Paris}}`` to the second, at character 451, re-rendered
at every node. Everything after it changed on every request, and Mistral's
prompt cache stopped around 120 tokens. Decision D2 of the latence-modele plan:
the time is frozen when the call is picked up, and the prompt reads it.

Levels, stated honestly
-----------------------
The formats are computed directly. The phone wiring is asserted on the source,
order included. The keyboard path is RUN up to the engine, with the clock
fixed, and the prompt is rendered with ``render_template`` from the dictionary
handed to the engine.
"""

import inspect
import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.pipecat import etat_ouverture, run_pipeline
from api.services.pipecat.etat_ouverture import injecter_date_heure_appel
from api.services.workflow import text_chat_runner
from api.services.workflow.text_chat_runner import execute_text_chat_pending_turn
from api.utils.template_renderer import render_template

CONSIGNE = "Nous sommes le {{initial_context.date_appel}}, il est {{initial_context.heure_appel}}."


def _utc(texte: str) -> datetime:
    return datetime.fromisoformat(texte).replace(tzinfo=UTC)


# --------------------------------------------------------------------------- #
# 1. The formats
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "instant,date_attendue,heure_attendue",
    [
        # midnight, and the minute after it (« minuit 30 », Evan 2026-09-15)
        (_utc("2026-09-14T22:00"), "mardi 15 septembre 2026", "minuit"),
        (_utc("2026-09-14T22:30"), "mardi 15 septembre 2026", "minuit 30"),
        # noon on the dot
        (_utc("2026-09-15T10:00"), "mardi 15 septembre 2026", "12 heures"),
        # 9 h 05, and 1 h singular
        (_utc("2026-09-15T07:05"), "mardi 15 septembre 2026", "9 heures 05"),
        (_utc("2026-09-14T23:10"), "mardi 15 septembre 2026", "1 heure 10"),
        # the first of the month
        (_utc("2026-09-30T22:00"), "jeudi 1er octobre 2026", "minuit"),
        # 31 December, last minute, then the new year
        (_utc("2026-12-31T22:59"), "jeudi 31 décembre 2026", "23 heures 59"),
        (_utc("2026-12-31T23:00"), "vendredi 1er janvier 2027", "minuit"),
        # spring forward, 29 March 2026: 01:59 CET, then 03:00 CEST
        (_utc("2026-03-29T00:59"), "dimanche 29 mars 2026", "1 heure 59"),
        (_utc("2026-03-29T01:00"), "dimanche 29 mars 2026", "3 heures"),
        # fall back, 25 October 2026: 02:30 happens twice
        (_utc("2026-10-25T00:30"), "dimanche 25 octobre 2026", "2 heures 30"),
        (_utc("2026-10-25T01:30"), "dimanche 25 octobre 2026", "2 heures 30"),
    ],
)
def test_les_formats_parles(instant, date_attendue, heure_attendue):
    contexte = injecter_date_heure_appel({}, instant)
    assert contexte == {"date_appel": date_attendue, "heure_appel": heure_attendue}


def test_un_instant_sans_fuseau_se_lit_heure_de_paris():
    contexte = injecter_date_heure_appel({}, datetime(2026, 9, 15, 14, 32))
    assert contexte["heure_appel"] == "14 heures 32"


# --------------------------------------------------------------------------- #
# 2. What it must not do
# --------------------------------------------------------------------------- #


def test_une_valeur_fournie_est_conservee_une_valeur_vide_est_calculee():
    fournie = {"date_appel": "lundi 14 septembre 2026", "heure_appel": "", "direction": "inbound"}
    contexte = injecter_date_heure_appel(fournie, _utc("2026-09-15T12:32"))
    assert contexte == {
        "date_appel": "lundi 14 septembre 2026",
        "heure_appel": "14 heures 32",
        "direction": "inbound",
    }
    # the input is not modified in place
    assert fournie["heure_appel"] == ""


def test_ne_leve_jamais_et_rend_le_contexte_inchange():
    with patch.object(etat_ouverture, "heure_parlee", side_effect=RuntimeError("panne")):
        contexte = {"direction": "inbound"}
        assert injecter_date_heure_appel(contexte, _utc("2026-09-15T12:32")) is contexte


# --------------------------------------------------------------------------- #
# 3. The phone path: called, right after the opening state, before persistence
# --------------------------------------------------------------------------- #


def _position(source: str, motif: str, quoi: str) -> int:
    trouve = re.search(motif, source)
    assert trouve, f"{quoi} is no longer in the source."
    return trouve.start()


def test_le_chemin_telephonique_fige_la_date_juste_apres_letat_douverture():
    source = inspect.getsource(run_pipeline)
    etat = _position(source, r"merged_call_context_vars = injecter_etat_ouverture\(", "opening state")
    date = _position(
        source,
        r"merged_call_context_vars = injecter_date_heure_appel\(merged_call_context_vars\)",
        "The date and time injection on the phone path",
    )
    persistance = _position(
        source,
        r"update_workflow_run\(\s*workflow_run_id, initial_context=merged_call_context_vars",
        "persistence",
    )
    fetch = _position(source, r"execute_pre_call_fetch\(", "pre-call fetch")
    assert etat < date < persistance < fetch
    assert len(re.findall(r"injecter_date_heure_appel\(", source)) == 1


def test_le_chemin_clavier_fige_la_date_juste_apres_letat_douverture():
    source = inspect.getsource(text_chat_runner)
    etat = _position(source, r"initial_context = injecter_etat_ouverture\(", "opening state")
    date = _position(
        source,
        r"initial_context = injecter_date_heure_appel\(initial_context\)",
        "The date and time injection on the keyboard path",
    )
    fetch = _position(source, r"execute_pre_call_fetch\(", "pre-call fetch")
    assert etat < date < fetch
    assert len(re.findall(r"injecter_date_heure_appel\(", source)) == 1


# --------------------------------------------------------------------------- #
# 4. The keyboard path, RUN
# --------------------------------------------------------------------------- #


class _Arret(Exception):
    """Raised by the mocked engine: everything asserted here is decided before."""


def _definition() -> dict:
    return {
        "nodes": [
            {
                "id": "start",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {
                    "name": "Start",
                    "prompt": CONSIGNE,
                    "is_start": True,
                    "allow_interrupt": False,
                    "add_global_prompt": False,
                    "greeting_type": "text",
                    "greeting": "Bonjour.",
                },
            },
            {
                "id": "end",
                "type": "endCall",
                "position": {"x": 0, "y": 200},
                "data": {
                    "name": "End",
                    "prompt": "Termine.",
                    "is_end": True,
                    "allow_interrupt": False,
                    "add_global_prompt": False,
                },
            },
        ],
        "edges": [
            {
                "id": "start-end",
                "source": "start",
                "target": "end",
                "data": {"label": "End Call", "condition": "Quand c'est fini."},
            }
        ],
    }


def _heure_fixe(instant: datetime):
    class _Horloge(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant if tz is None else instant.astimezone(tz)

    return patch.object(etat_ouverture, "datetime", _Horloge)


async def _jouer_au_clavier(configurations: dict, contexte_initial: dict, instant: datetime):
    run = SimpleNamespace(
        workflow_id=6,
        name="essai",
        initial_context=dict(contexte_initial),
        definition=SimpleNamespace(workflow_json=_definition(), workflow_configurations=configurations),
        workflow=SimpleNamespace(organization_id=11, user=SimpleNamespace(id=1)),
    )
    agent = SimpleNamespace(id=6, organization_id=11, workflow_configurations=configurations)
    moteur = MagicMock(side_effect=_Arret)
    with (
        _heure_fixe(instant),
        patch.object(text_chat_runner, "db_client") as base,
        patch.object(text_chat_runner, "PipecatEngine", moteur),
        patch.object(text_chat_runner, "create_llm_service", MagicMock()),
        patch.object(text_chat_runner, "execute_pre_call_fetch", AsyncMock(return_value=None)),
        patch(
            "api.services.configuration.ai_model_configuration.get_effective_ai_model_configuration_for_workflow",
            AsyncMock(
                return_value=SimpleNamespace(
                    llm=SimpleNamespace(provider="openai", model="gpt-4.1"), embeddings=None
                )
            ),
        ),
        patch(
            "api.services.managed_model_services.ensure_mps_correlation_id",
            AsyncMock(return_value=None),
        ),
        patch.object(text_chat_runner, "stamp_sampling_settings", lambda cible, _llm: cible),
    ):
        base.get_workflow_run_with_context = AsyncMock(return_value=(run, None))
        base.get_workflow = AsyncMock(return_value=agent)
        base.update_workflow_run = AsyncMock()
        base.has_active_recordings = AsyncMock(return_value=False)
        with pytest.raises(_Arret):
            await execute_text_chat_pending_turn(
                workflow_run_id=7,
                workflow_id=6,
                session_data={"turns": [{"status": "pending", "user_message": None}]},
                checkpoint=None,
            )
        persiste = base.update_workflow_run.await_args.kwargs["initial_context"]
        donne_au_moteur = moteur.call_args.kwargs["call_context_vars"]
        assert donne_au_moteur == persiste
        return persiste, render_template(CONSIGNE, donne_au_moteur)


@pytest.mark.asyncio
async def test_clavier_un_agent_sans_horaires_recoit_la_date_et_lheure():
    persiste, consigne = await _jouer_au_clavier({}, {"direction": "inbound"}, _utc("2026-09-15T12:32"))
    assert persiste["date_appel"] == "mardi 15 septembre 2026"
    assert persiste["heure_appel"] == "14 heures 32"
    # The text the agent reads, not only the dictionary.
    assert consigne == "Nous sommes le mardi 15 septembre 2026, il est 14 heures 32."


@pytest.mark.asyncio
async def test_clavier_aux_tours_suivants_lheure_du_premier_tour_reste():
    """Frozen at pick-up: a later turn, at a later instant, keeps the first turn's time."""
    persiste, consigne = await _jouer_au_clavier(
        {},
        {"direction": "inbound", "date_appel": "mardi 15 septembre 2026", "heure_appel": "14 heures 32"},
        _utc("2026-09-15T12:40"),
    )
    assert persiste["heure_appel"] == "14 heures 32"
    assert consigne == "Nous sommes le mardi 15 septembre 2026, il est 14 heures 32."
