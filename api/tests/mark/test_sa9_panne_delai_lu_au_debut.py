"""[.mark] Clôture, SA-9 (mineur 4) : le délai de Twilio se lit une fois au début de l'appel, jamais en base en pleine panne.

| Test | Ce qu'il prouve |
|---|---|
| renvoi | au renvoi de secours, la base n'est pas touchée et Twilio reçoit le délai du contexte |
| debut | le contexte de panne porte le délai réglé, lu au branchement (une seule lecture) |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api.db import db_client
from api.schemas.panne import PanneAgent, ReglagesPanne
from api.services.panne.gardien import ContextePanne, GardienPanne


def _contexte(**plus):
    return ContextePanne(
        run_id=7,
        organization_id=1,
        workflow_id=3,
        reglages=PanneAgent(actif=True),
        entrant=True,
        call_sid="CAessai",
        run=SimpleNamespace(initial_context={}),
        **plus,
    )


async def test_le_renvoi_ne_touche_pas_la_base_et_donne_a_twilio_le_delai_du_contexte():
    gardien = GardienPanne(_contexte(delai_twilio_s=11.0), SimpleNamespace())
    mise_a_jour = AsyncMock()
    base = AsyncMock(side_effect=AssertionError("la base est lue en pleine panne"))
    with (
        patch("api.services.telephony.factory.get_telephony_provider_for_run", AsyncMock(return_value=SimpleNamespace(account_sid="ACessai", auth_token="jeton-0123456789"))),
        patch("api.services.panne.gardien.client_twilio.mettre_a_jour_appel", mise_a_jour),
        patch.object(db_client, "get_configuration", base, create=True),
    ):
        resultat = await gardien._donner_la_consigne("<Response/>")
    assert resultat is None
    base.assert_not_called()
    assert mise_a_jour.await_args.args[4] == 11.0


async def test_le_contexte_porte_le_delai_regle_lu_au_branchement():
    from api.services.pipecat import run_pipeline

    pris = []
    with (
        patch("api.schemas.panne.panne_de_lagent", return_value=PanneAgent(actif=True)),
        patch("api.services.panne.routes.lire_reglages", AsyncMock(return_value=ReglagesPanne(delai_twilio_s=9.0))) as lecture,
        patch("api.services.panne.declencheurs.brancher", lambda engine, task, llm, tts, contexte: pris.append(contexte)),
    ):
        await run_pipeline._brancher_la_panne(
            None, None, None, None, SimpleNamespace(id=7, mode="twilio"), 1, 3, {}, None, "inbound", "CA1", False
        )
    assert len(pris) == 1 and pris[0].delai_twilio_s == 9.0
    assert lecture.await_count == 1
