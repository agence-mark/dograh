"""[.mark] Clôture, lot C (D18) : la voix et la langue de Twilio pour la phrase de secours sont réglables (avancé).

| Test | Ce qu'il prouve |
|---|---|
| défauts | la voix et la langue d'avant (``Polly.Lea-Neural``, ``fr-FR``) : le TwiML est identique à celui d'avant |
| bornes | une voix ou une langue qui ressemble à une instruction (guillemet, chevron, espace) est refusée |
| consigne | la voix posée est celle du TwiML du renvoi et du rappel ; une valeur est échappée comme un attribut |
| gardien | le moteur de secours lit le réglage de l'agent (renvoi, rappel, excuse), pas seulement l'écran |
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas.panne import LANGUE_TWILIO, VOIX_TWILIO, PanneAgent
from api.services.panne import consigne


def test_les_defauts_sont_la_voix_et_la_langue_d_avant():
    p = PanneAgent()
    assert (p.voix_twilio, p.langue_twilio) == (VOIX_TWILIO, LANGUE_TWILIO) == ("Polly.Lea-Neural", "fr-FR")
    assert consigne.rappel("Au revoir.") == (
        '<?xml version="1.0" encoding="UTF-8"?><Response><Say language="fr-FR" voice="Polly.Lea-Neural">Au revoir.</Say><Hangup/></Response>'
    )


@pytest.mark.parametrize("champ, valeur", [("voix_twilio", 'x" onclick="y'), ("voix_twilio", "a b"), ("voix_twilio", "<Say>"), ("voix_twilio", ""), ("langue_twilio", "français"), ("langue_twilio", "fr_FR"), ("langue_twilio", 'fr-FR"')])
def test_une_valeur_qui_ressemble_a_une_instruction_est_refusee(champ, valeur):
    with pytest.raises(ValidationError):
        PanneAgent(**{champ: valeur})


def test_la_voix_posee_est_celle_du_twiml_et_une_valeur_est_echappee_en_attribut():
    r = consigne.rappel("Bonjour", "alice", "en-GB")
    assert 'language="en-GB"' in r and 'voice="alice"' in r
    renvoi = consigne.renvoi("Un instant", "+33612345678", 20, "https://x.example.org/r", "Polly.Joanna", "en-US")
    assert 'voice="Polly.Joanna"' in renvoi and 'language="en-US"' in renvoi
    # même si le schéma était contourné, la valeur reste un attribut
    assert "<Hangup/>" not in consigne._dire("t", 'a"><Hangup/><Say voice="b')


def test_le_gardien_lit_la_voix_de_l_agent_pour_le_rappel_l_excuse_et_le_renvoi():
    from types import SimpleNamespace

    from api.services.panne.gardien import ContextePanne, GardienPanne

    reglages = PanneAgent(actif=True, voix_twilio="Polly.Joanna", langue_twilio="en-US")
    ctx = ContextePanne(
        run_id=7, organization_id=1, workflow_id=3, reglages=reglages, entrant=False, call_sid="CAessai",
        run=SimpleNamespace(initial_context={}), url_resultat="https://dograh.example.org/r", reglages_annonce=None,
    )
    engine = SimpleNamespace(_gathered_context={"extracted_variables": {}}, _call_context_vars={})
    gardien = GardienPanne(ctx, engine)
    assert 'voice="Polly.Joanna"' in gardien.consigne_de_rappel() and 'language="en-US"' in gardien.consigne_de_rappel()
    from api.tests.mark.boucle_isolee import executer_sans_toucher_la_boucle_courante

    decision, twiml, _, _ = executer_sans_toucher_la_boucle_courante(gardien._choisir())  # appel sortant : l'excuse
    assert decision == "excuse" and 'voice="Polly.Joanna"' in twiml
