"""[.mark] Is the opening state actually injected when a call is set up?

The question this file answers, and only this one:

    On the phone path and on the keyboard path, is ``injecter_etat_ouverture``
    CALLED with the agent's configuration, early enough that the pre-call fetch
    still wins and the persisted context carries the three variables?

Why a file of its own
---------------------
``test_etat_ouverture.py`` proves the computation. It stays green if nothing
calls it -- the exact failure measured three times on 2026-09-14 for the Pipecat
settings (``test_transmission_de_la_configuration.py``), and the exact state of
the calls of 2026-09-15: a mechanism able to inject, and nothing feeding it.

Two levels, stated honestly
---------------------------
1. Phone path (``run_pipeline``): asserted on the SOURCE text, order included.
   Running it needs a live pipeline, a database and a websocket.
2. Keyboard path (``text_chat_runner``): RUN, with the database mocked out, up
   to the engine construction. The assertion is on what is persisted and on the
   start-node prompt rendered from it, with ``render_template`` -- the function
   the engine calls on that context (``pipecat_engine.py``).

⚠️ What it does NOT catch: the engine rendering from a different dictionary
than the one handed to it. Nothing short of an end-to-end call would.
"""

import inspect
import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.pipecat import etat_ouverture, run_pipeline
from api.services.workflow import text_chat_runner
from api.services.workflow.text_chat_runner import execute_text_chat_pending_turn
from api.utils.template_renderer import render_template

HORAIRES = """lundi : 10:00-18:30 sur rendez-vous
mardi : 10:00-12:30 et 14:00-18:30
mercredi : 10:00-12:30 et 14:00-18:30
jeudi : 10:00-12:30 et 14:00-18:30
vendredi : 10:00-12:30 et 14:00-19:00
samedi : 10:00-19:00
dimanche : fermé
"""

CONSIGNE = (
    "État : {{initial_context.etat_ouverture}}. "
    "Réouverture : {{initial_context.reouverture}}."
)


# --------------------------------------------------------------------------- #
# 1. The call exists, and comes before the persistence and the pre-call fetch
# --------------------------------------------------------------------------- #


def _position(source: str, motif: str, quoi: str) -> int:
    trouve = re.search(motif, source)
    assert trouve, f"{quoi} is no longer in the source."
    return trouve.start()


def test_le_chemin_telephonique_injecte_avant_la_persistance_et_le_pre_call_fetch():
    source = inspect.getsource(run_pipeline)
    configs = _position(
        source, r"run_configs = run_definition\.workflow_configurations", "run_configs"
    )
    injection = _position(
        source,
        r"merged_call_context_vars = injecter_etat_ouverture\(\s*merged_call_context_vars,\s*run_configs\s*\)",
        "The opening-state injection on the phone path",
    )
    persistance = _position(
        source,
        r"update_workflow_run\(\s*workflow_run_id, initial_context=merged_call_context_vars",
        "The persistence of the call context",
    )
    fetch = _position(source, r"execute_pre_call_fetch\(", "The pre-call fetch")
    assert configs < injection < persistance < fetch, (
        "On the phone path the opening state must be computed after the agent's "
        "configuration is read, and before the context is persisted and the "
        "pre-call fetch fires -- otherwise the fetch no longer wins (D7) or the "
        "stored context does not say what the agent was told."
    )
    assert len(re.findall(r"injecter_etat_ouverture\(", source)) == 1


def test_le_chemin_clavier_injecte_avant_le_pre_call_fetch_et_la_persistance():
    source = inspect.getsource(text_chat_runner)
    construction = _position(
        source, r"initial_context = \{\s*\*\*base_initial_context", "initial_context"
    )
    injection = _position(
        source,
        r"initial_context = injecter_etat_ouverture\(initial_context, run_configs\)",
        "The opening-state injection on the keyboard path",
    )
    fetch = _position(source, r"execute_pre_call_fetch\(", "The pre-call fetch")
    persistance = _position(source, r"update_workflow_run\(", "The persistence")
    assert construction < injection < fetch < persistance
    assert len(re.findall(r"injecter_etat_ouverture\(", source)) == 1


# --------------------------------------------------------------------------- #
# 2 to 4. The keyboard path, RUN
# --------------------------------------------------------------------------- #


class _Arret(Exception):
    """Raised by the mocked engine: everything this file asserts is decided before."""


def _definition(pre_call_fetch_url: str | None = None) -> dict:
    depart = {
        "name": "Start",
        "prompt": CONSIGNE,
        "is_start": True,
        "allow_interrupt": False,
        "add_global_prompt": False,
        "greeting_type": "text",
        "greeting": "Bonjour.",
    }
    if pre_call_fetch_url:
        depart.update(
            pre_call_fetch_mode="always",
            pre_call_fetch_url=pre_call_fetch_url,
            pre_call_fetch_credential_uuid="credential-uuid",
        )
    return {
        "nodes": [
            {"id": "start", "type": "startCall", "position": {"x": 0, "y": 0}, "data": depart},
            {
                "id": "end",
                "type": "endCall",
                "position": {"x": 0, "y": 200},
                "data": {
                    "name": "End",
                    "prompt": "Wrap up the conversation.",
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
                "data": {"label": "End Call", "condition": "When the task is done."},
            }
        ],
    }


def _heure_fixe(quand: str):
    fixe = datetime.fromisoformat(quand).replace(tzinfo=etat_ouverture.PARIS)

    class _Horloge(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixe if tz is None else fixe.astimezone(tz)

    return patch.object(etat_ouverture, "datetime", _Horloge)


async def _jouer_le_premier_tour(
    configurations: dict,
    *,
    quand: str = "2026-09-15 13:00",
    contexte_initial: dict | None = None,
    pre_call_fetch: dict | None = None,
):
    """Run the keyboard path up to the engine; return (persisted context, rendered prompt)."""
    definition = _definition("https://example.test/fetch" if pre_call_fetch is not None else None)
    run = SimpleNamespace(
        workflow_id=1,
        name="essai",
        initial_context=dict(contexte_initial or {"direction": "inbound"}),
        definition=SimpleNamespace(workflow_json=definition, workflow_configurations=configurations),
        workflow=SimpleNamespace(organization_id=11, user=SimpleNamespace(id=1)),
    )
    agent = SimpleNamespace(id=1, organization_id=11, workflow_configurations=configurations)
    moteur = MagicMock(side_effect=_Arret)
    configuration_modele = SimpleNamespace(
        llm=SimpleNamespace(provider="openai", model="gpt-4.1"), embeddings=None
    )

    with (
        _heure_fixe(quand),
        patch.object(text_chat_runner, "db_client") as base,
        patch.object(text_chat_runner, "PipecatEngine", moteur),
        patch.object(text_chat_runner, "create_llm_service", MagicMock()),
        patch.object(text_chat_runner, "stamp_sampling_settings", lambda cible, _llm: cible),
        patch.object(
            text_chat_runner,
            "execute_pre_call_fetch",
            AsyncMock(return_value=pre_call_fetch),
        ),
        patch(
            "api.services.configuration.ai_model_configuration.get_effective_ai_model_configuration_for_workflow",
            AsyncMock(return_value=configuration_modele),
        ),
        patch(
            "api.services.managed_model_services.ensure_mps_correlation_id",
            AsyncMock(return_value=None),
        ),
    ):
        base.get_workflow_run_with_context = AsyncMock(return_value=(run, None))
        base.get_workflow = AsyncMock(return_value=agent)
        base.update_workflow_run = AsyncMock()
        base.has_active_recordings = AsyncMock(return_value=False)

        with pytest.raises(_Arret):
            await execute_text_chat_pending_turn(
                workflow_run_id=7,
                workflow_id=1,
                session_data={"turns": [{"status": "pending", "user_message": None}]},
                checkpoint=None,
            )

        assert base.update_workflow_run.await_count == 1
        persiste = base.update_workflow_run.await_args.kwargs["initial_context"]
        donne_au_moteur = moteur.call_args.kwargs["call_context_vars"]
        assert donne_au_moteur == persiste
        return persiste, render_template(CONSIGNE, donne_au_moteur)


@pytest.mark.asyncio
async def test_clavier_le_contexte_persiste_porte_les_trois_variables():
    persiste, consigne = await _jouer_le_premier_tour({"horaires_ouverture": HORAIRES})
    assert persiste["etat_ouverture"] == "PAUSE"
    assert persiste["reouverture"] == "aujourd'hui à 14 heures"
    assert persiste["horaires_ouverture"] == HORAIRES
    # ⛔ The failure of 2026-09-15 was exactly "État : ." -- asserted on the text
    # the agent reads, not only on the dictionary.
    assert consigne == "État : PAUSE. Réouverture : aujourd'hui à 14 heures."


@pytest.mark.asyncio
async def test_clavier_un_pre_call_fetch_qui_renvoie_letat_lemporte():
    persiste, consigne = await _jouer_le_premier_tour(
        {"horaires_ouverture": HORAIRES},
        pre_call_fetch={"etat_ouverture": "OUVERT", "reouverture": ""},
    )
    assert persiste["etat_ouverture"] == "OUVERT"
    assert persiste["reouverture"] == ""
    assert consigne == "État : OUVERT. Réouverture : ."


@pytest.mark.asyncio
async def test_clavier_une_valeur_injectee_au_rejeu_est_conservee():
    """D7: the replay tool injects ``etat_ouverture=FERME`` on a Tuesday at 11."""
    persiste, _ = await _jouer_le_premier_tour(
        {"horaires_ouverture": HORAIRES},
        quand="2026-09-15 11:00",
        contexte_initial={"direction": "inbound", "etat_ouverture": "FERME"},
    )
    assert persiste["etat_ouverture"] == "FERME"


@pytest.mark.asyncio
async def test_clavier_aux_tours_suivants_letat_du_premier_tour_reste():
    """D8 on the keyboard path: each turn builds a new pipeline, and the state
    persisted by the first turn is kept, not recomputed at the new instant."""
    persiste, _ = await _jouer_le_premier_tour(
        {"horaires_ouverture": HORAIRES},
        quand="2026-09-15 15:00",
        contexte_initial={
            "direction": "inbound",
            "etat_ouverture": "PAUSE",
            "reouverture": "aujourd'hui à 14 heures",
            "horaires_ouverture": HORAIRES,
        },
    )
    assert persiste["etat_ouverture"] == "PAUSE"
    assert persiste["reouverture"] == "aujourd'hui à 14 heures"


@pytest.mark.asyncio
@pytest.mark.parametrize("configurations", [{}, {"horaires_ouverture": None}])
async def test_clavier_sans_horaires_le_contexte_persiste_est_celui_davant(configurations):
    """D6. 🔒 Asserted as an exact dictionary: no opening-state key, not one more.

    ⚠️ Since the latence-modele chantier (D2, 2026-09-15) every agent also
    receives the date and time of the call, hours or not: those two keys are
    the only ones added, and ``test_date_heure_appel.py`` owns them.

    ⚠️ [.mark] Montee vers l'amont `23d22b95` (2026-09-16) : `workflow_run_id`
    s'ajoute a la liste. Il vient de l'amont, qui expose desormais
    l'identifiant d'execution dans le contexte initial -- pas de chez nous.
    🔑 C'est exactement ce que cette assertion exacte sert a voir : une cle qui
    apparait dans le contexte de TOUS les agents ne doit jamais passer
    inapercue, meme quand elle est inoffensive. On la constate, on l'inscrit.
    """
    persiste, consigne = await _jouer_le_premier_tour(configurations)
    assert persiste == {
        "direction": "inbound",
        "workflow_run_id": 7,
        "runtime_configuration": {"llm_provider": "openai", "llm_model": "gpt-4.1"},
        "date_appel": "mardi 15 septembre 2026",
        "heure_appel": "13 heures",
    }
    assert consigne == "État : . Réouverture : ."
