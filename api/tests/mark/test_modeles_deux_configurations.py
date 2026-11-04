"""[.mark] Partie 3, lot 13 (SE-24, M-2) : Modèles et clés garde DEUX configurations (la chaîne et le temps réel), bascule sans perte.

Vraies routes, vraie base de test (transaction annulée), validateur de fournisseurs remplacé : aucun appel à un tiers.

| Test | Ce qu'il prouve |
|---|---|
| enregistrer le temps réel | la chaîne (voix, transcription, cerveau) reste telle quelle, clés comprises |
| bascule dans les deux sens | le moteur d'appel (la vraie lecture de la configuration effective) lit la chaîne puis le temps réel puis la chaîne |
| rien à basculer | basculer vers une configuration jamais réglée est refusé et ne change rien |
| clés masquées | un enregistrement qui renvoie les clés masquées de l'autre configuration les retrouve |
| test chez le fournisseur | l'autre configuration n'est testée que si cet enregistrement la change |
| cloisonnement | basculer chez A ne touche pas B, et B sans configuration est refusée |
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from api.db import db_client
from api.services.configuration import ai_model_configuration as service
from api.services.configuration.check_validity import UserConfigurationValidator
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)

V2 = "/api/v1/organizations/model-configurations/v2"


@pytest.fixture(autouse=True)
def _decor(request, db_session, monkeypatch):
    """Transaction annulée (aucun compte ni configuration ne reste) et validateur des fournisseurs remplacé."""
    validateur = AsyncMock(return_value={"status": [{"model": "all", "message": "ok"}]})
    monkeypatch.setattr(UserConfigurationValidator, "validate", validateur)
    request.node.validateur = validateur
    yield


def chaine(suffixe="1"):
    return {
        "llm": {"provider": "openai", "api_key": f"cle-llm-chaine-{suffixe}", "model": "gpt-4.1"},
        "tts": {"provider": "elevenlabs", "api_key": f"cle-voix-{suffixe}", "model": "eleven_flash_v2_5", "voice": "voix-essai"},
        "stt": {"provider": "deepgram", "api_key": f"cle-transcription-{suffixe}", "model": "nova-3"},
    }


def temps_reel(suffixe="1"):
    return {
        "realtime": {
            "provider": "google_realtime",
            "api_key": f"cle-temps-reel-{suffixe}",
            "model": "gemini-3.1-flash-live-preview",
            "voice": "Puck",
            "language": "en",
        },
        "llm": {"provider": "google", "api_key": f"cle-llm-temps-reel-{suffixe}", "model": "gemini-3.5-flash"},
    }


def corps(mode, *, avec_chaine=None, avec_temps_reel=None):
    byok = {"mode": mode}
    if avec_chaine is not None:
        byok["pipeline"] = avec_chaine
    if avec_temps_reel is not None:
        byok["realtime"] = avec_temps_reel
    return {"version": 2, "mode": "byok", "byok": byok}


async def _decor_compte(nom):
    org = await creer_organisation(db_client, f"org-{nom}-{uuid.uuid4().hex[:8]}")
    _, jeton = await creer_compte(db_client, f"{nom}{uuid.uuid4().hex[:8]}@example.test", role="Administrateur", organisations=[org])
    return org, jeton


async def _stockee(org):
    return await service.get_organization_ai_model_configuration_v2(org)


async def _lue_par_le_moteur(org):
    """La vraie lecture qu'un appel fait de la configuration (clés de la bibliothèque résolues comprises)."""
    return await service.get_effective_ai_model_configuration_for_workflow(organization_id=org, workflow_configurations={})


async def test_enregistrer_le_temps_reel_ne_fait_pas_perdre_la_chaine(request):
    org, jeton = await _decor_compte("garde")
    async with client_http() as c:
        assert (await c.put(V2, json=corps("pipeline", avec_chaine=chaine()), headers=entetes(jeton, org))).status_code == 200
        # l'écran (ou un ancien écran) n'envoie QUE le temps réel
        r = await c.put(V2, json=corps("realtime", avec_temps_reel=temps_reel()), headers=entetes(jeton, org))
        assert r.status_code == 200
    stockee = await _stockee(org)
    assert stockee.byok.mode == "realtime"
    pipeline = stockee.byok.pipeline  # la chaîne est toujours là, voix et transcription comprises, avec leurs vraies clés
    assert (pipeline.tts.provider, pipeline.stt.provider, pipeline.llm.provider) == ("elevenlabs", "deepgram", "openai")
    assert pipeline.tts.api_key == "cle-voix-1" and pipeline.stt.api_key == "cle-transcription-1"
    # et la réponse montre les deux configurations, clés masquées
    assert r.json()["configuration"]["byok"]["pipeline"]["tts"]["api_key"] != "cle-voix-1"


async def test_la_bascule_dans_les_deux_sens_est_lue_par_le_moteur_d_appel_sans_rien_perdre():
    org, jeton = await _decor_compte("bascule")
    async with client_http() as c:
        h = entetes(jeton, org)
        await c.put(V2, json=corps("pipeline", avec_chaine=chaine()), headers=h)
        await c.put(V2, json=corps("realtime", avec_chaine=chaine(), avec_temps_reel=temps_reel()), headers=h)
        actif = await _lue_par_le_moteur(org)
        assert actif.is_realtime is True and actif.realtime.provider == "google_realtime" and actif.tts is None

        # temps réel -> chaîne
        r = await c.put(f"{V2}/mode", json={"mode": "pipeline"}, headers=h)
        assert r.status_code == 200 and r.json()["configuration"]["byok"]["mode"] == "pipeline"
        actif = await _lue_par_le_moteur(org)
        assert actif.is_realtime is False and (actif.tts.provider, actif.stt.provider) == ("elevenlabs", "deepgram")
        assert actif.tts.api_key == "cle-voix-1" and actif.llm.model == "gpt-4.1"

        # chaîne -> temps réel
        assert (await c.put(f"{V2}/mode", json={"mode": "realtime"}, headers=h)).status_code == 200
        actif = await _lue_par_le_moteur(org)
        assert actif.is_realtime is True and actif.realtime.model == "gemini-3.1-flash-live-preview" and actif.llm.provider == "google"

        # et de nouveau la chaîne : après deux bascules, rien n'a bougé
        await c.put(f"{V2}/mode", json={"mode": "pipeline"}, headers=h)
        actif = await _lue_par_le_moteur(org)
        assert actif.tts.voice == "voix-essai" and actif.stt.model == "nova-3"
    stockee = await _stockee(org)
    assert stockee.byok.realtime.realtime.api_key == "cle-temps-reel-1" and stockee.byok.pipeline.stt.api_key == "cle-transcription-1"


async def test_basculer_vers_une_configuration_jamais_reglee_est_refuse_et_ne_change_rien():
    org, jeton = await _decor_compte("rien")
    async with client_http() as c:
        h = entetes(jeton, org)
        sans_rien = await c.put(f"{V2}/mode", json={"mode": "pipeline"}, headers=h)
        assert sans_rien.status_code == 422
        await c.put(V2, json=corps("pipeline", avec_chaine=chaine()), headers=h)
        refus = await c.put(f"{V2}/mode", json={"mode": "realtime"}, headers=h)
        assert refus.status_code == 422 and "not set yet" in refus.json()["detail"]
        assert (await c.put(f"{V2}/mode", json={"mode": "inconnu"}, headers=h)).status_code == 422
    assert (await _stockee(org)).byok.mode == "pipeline"
    assert (await _lue_par_le_moteur(org)).is_realtime is False


async def test_un_enregistrement_qui_renvoie_les_cles_masquees_de_l_autre_configuration_les_retrouve():
    org, jeton = await _decor_compte("masque")
    async with client_http() as c:
        h = entetes(jeton, org)
        await c.put(V2, json=corps("pipeline", avec_chaine=chaine()), headers=h)
        lue = (await c.get(V2, headers=h)).json()["configuration"]["byok"]  # clés masquées
        assert lue["pipeline"]["stt"]["api_key"] != "cle-transcription-1"
        # on règle le temps réel et on renvoie la chaîne telle que l'écran l'a lue (masquée)
        r = await c.put(V2, json=corps("realtime", avec_chaine=lue["pipeline"], avec_temps_reel=temps_reel()), headers=h)
        assert r.status_code == 200
    pipeline = (await _stockee(org)).byok.pipeline
    assert pipeline.stt.api_key == "cle-transcription-1" and pipeline.tts.api_key == "cle-voix-1" and pipeline.llm.api_key == "cle-llm-chaine-1"


async def test_l_autre_configuration_n_est_testee_chez_le_fournisseur_que_si_l_enregistrement_la_change(request):
    org, jeton = await _decor_compte("teste")
    validateur = request.node.validateur
    async with client_http() as c:
        h = entetes(jeton, org)
        await c.put(V2, json=corps("pipeline", avec_chaine=chaine()), headers=h)
        assert validateur.await_count == 1  # la seule configuration qui existe
        await c.put(V2, json=corps("realtime", avec_temps_reel=temps_reel()), headers=h)
        assert validateur.await_count == 2  # l'active (temps réel) ; la chaîne, gardée telle quelle, n'est pas retestée
        await c.put(V2, json=corps("realtime", avec_chaine=chaine("2"), avec_temps_reel=temps_reel()), headers=h)
        assert validateur.await_count == 4  # la chaîne a changé : active + chaîne


async def test_basculer_chez_une_organisation_ne_touche_pas_l_autre():
    a, jeton_a = await _decor_compte("a")
    b, jeton_b = await _decor_compte("b")
    async with client_http() as c:
        await c.put(V2, json=corps("pipeline", avec_chaine=chaine("a"), avec_temps_reel=temps_reel("a")), headers=entetes(jeton_a, a))
        refus_b = await c.put(f"{V2}/mode", json={"mode": "realtime"}, headers=entetes(jeton_b, b))
        assert refus_b.status_code == 422  # B n'a aucune configuration : celle de A n'est ni vue ni changée
        await c.put(V2, json=corps("pipeline", avec_chaine=chaine("b")), headers=entetes(jeton_b, b))
        await c.put(f"{V2}/mode", json={"mode": "realtime"}, headers=entetes(jeton_a, a))
    assert (await _stockee(a)).byok.mode == "realtime"
    assert (await _stockee(b)).byok.mode == "pipeline" and (await _stockee(b)).byok.realtime is None
    assert (await _lue_par_le_moteur(b)).tts.api_key == "cle-voix-b"
