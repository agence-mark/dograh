"""[.mark] Le post-scriptum au clavier (plan mode-prise-de-notes, lot 5).

Plan `Labo-agent-vocal/plans/mode-prise-de-notes/`. Règle C8 (correctifs-banc-34) : le clavier
construit l'appel comme le téléphone, sinon le banc au clavier mesure un agent que les appelants
n'entendent jamais. En post-scriptum, le même processeur est placé juste après le modèle.

Par les VRAIES routes HTTP du clavier ; seul le modèle (réponses écrites d'avance) est remplacé.

| Test | Ce qu'il prouve |
|---|---|
| fiche | la note du post-scriptum remplit la fiche du tour, source `post_scriptum`, trace « present » |
| affichage et mémoire | la réponse affichée et la mémoire du modèle ne contiennent ni séparateur ni JSON |
| refus | une valeur jamais dite est refusée comme avec l'outil |
| outil | en mode outil, le clavier est celui d'avant : la même réponse est dite telle quelle, rien n'est noté |
"""

import pytest

from api.services.pipecat.post_scriptum import PRESENT, TRACE_POST_SCRIPTUM
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    CLE_MODE,
    MODE_OUTIL,
    MODE_POST_SCRIPTUM,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _converser, _monter
from pipecat.tests import MockLLMService

POST_SCRIPTUM = {**FICHE, CLE_MODE: MODE_POST_SCRIPTUM}
REPONSE = 'Merci, et que puis-je faire pour vous ?\n|||\n{"nom": "Lemaire"}'


def _dits_par_l_agent(charge: dict) -> list[str]:
    """Ce que l'agent a dit : la réponse affichée et sa mémoire (messages
    « assistant » du point de reprise)."""
    messages = charge["checkpoint"]["messages"]
    dits = [
        str(m.get("content") or "") for m in messages if m.get("role") == "assistant"
    ]
    for cle in ("assistant_text", "text", "reply"):
        if isinstance(charge.get(cle), str):
            dits.append(charge[cle])
    for tour in charge.get("turns") or []:
        if tour.get("role") == "assistant":
            dits.append(str(tour.get("text") or tour.get("content") or ""))
    return dits


@pytest.mark.asyncio
async def test_au_clavier_le_post_scriptum_remplit_la_fiche(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, POST_SCRIPTUM)
    charge, run_id = await _converser(
        test_client_factory,
        user,
        workflow,
        [MockLLMService.create_text_chunks(REPONSE)],
        "je m'appelle Lemaire",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert fiche.get("nom") == "Lemaire", fiche
    assert any(
        e.get("champ") == "nom" and e.get("source") == MODE_POST_SCRIPTUM
        for e in fiche.get(CLE_JOURNAL) or []
    ), fiche.get(CLE_JOURNAL)
    assert [t["etat"] for t in fiche.get(TRACE_POST_SCRIPTUM) or []] == [PRESENT]
    run = await db_session.get_workflow_run_by_id(run_id)
    assert (run.gathered_context or {}).get("nom") == "Lemaire", run.gathered_context


@pytest.mark.asyncio
async def test_au_clavier_ni_separateur_ni_json_dans_ce_que_dit_l_agent(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, POST_SCRIPTUM)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [MockLLMService.create_text_chunks(REPONSE)],
        "je m'appelle Lemaire",
    )
    dits = _dits_par_l_agent(charge)
    assert any("que puis-je faire pour vous" in d for d in dits), charge
    for dit in dits:
        assert "|||" not in dit and "{" not in dit and '"nom"' not in dit, dit


@pytest.mark.asyncio
async def test_au_clavier_une_valeur_jamais_dite_est_refusee(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, POST_SCRIPTUM)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [MockLLMService.create_text_chunks('Très bien.\n|||\n{"nom": "Martin"}')],
        "je m'appelle Lemaire",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert "nom" not in fiche, fiche
    assert any(
        e.get("champ") == "nom" and e.get("statut") == "refuse"
        for e in fiche.get(CLE_JOURNAL) or []
    ), fiche.get(CLE_JOURNAL)


@pytest.mark.asyncio
async def test_en_mode_outil_le_clavier_est_celui_d_avant(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(
        db_session, async_session, {**FICHE, CLE_MODE: MODE_OUTIL}
    )
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [MockLLMService.create_text_chunks(REPONSE)],
        "je m'appelle Lemaire",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert "nom" not in fiche and TRACE_POST_SCRIPTUM not in fiche, fiche
    assert any("|||" in d for d in _dits_par_l_agent(charge))
