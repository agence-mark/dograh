"""[.mark] Soniox as a transcription provider, with every setting on screen.

The question this file answers (plan ``exposition-soniox``, 2026-09-29):

    Is Soniox declared, are its settings on the configuration, and does each
    setting that is filled in reach the configuration message Soniox receives
    -- through the factory the call uses, never a side door?

⛔ Read that scope literally. It does not prove that Soniox transcribes well,
nor that Soniox accepts a value: no Soniox key exists yet (decision of Evan and
Pierre, 2026-09-29, « plus tard »). It proves that nothing is dropped between
the screen and the wire, and that no agent running Deepgram changes.

Decisions it holds (plan, table of decisions):

- D3: Soniox decides the end of the turn by default (``endpoint_detection``).
  Switched off, Pipecat's local detector ends the turn and the three endpoint
  settings are hidden AND not sent: the same rule on screen and in code (E8).
- D5: the European address by default; an empty address also goes to Europe.
- D7/D8: no ceiling is declared for Soniox until it is probed, so Soniox
  receives NO list of terms.
- D10: the names are upstream's (``soniox``, ``SonioxSTTConfiguration``,
  ``options/soniox.py``), so the next version bump merges instead of doubling.
- Key check (Evan and Pierre, 2026-09-29): against the API of the region the
  address points to.

What "not sent" means here: the connector writes every key of its
configuration message, and a key we do not collect goes out as ``null``, which
Soniox reads as "use your own default". So "absent" below is ``None``.
"""

import json
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from api.services.pipecat.audio_config import AudioConfig

REGLAGES_FIN_DE_TOUR = (
    "max_endpoint_delay_ms",
    "endpoint_sensitivity",
    "endpoint_latency_adjustment_level",
)
REGLAGES_EXPOSES = (
    "language",
    "language_hints_strict",
    "enable_language_identification",
    "endpoint_detection",
    *REGLAGES_FIN_DE_TOUR,
    "enable_speaker_diarization",
    "domain_description",  # lot 5bis of communes-cp-et-lexique-soniox (Q5, 2026-10-02)
    "base_url",
    "region",
)
ADRESSE_EUROPE = "wss://stt-rt.eu.soniox.com/transcribe-websocket"
ADRESSE_MONDIALE = "wss://stt-rt.soniox.com/transcribe-websocket"


def _classe():
    from api.services.configuration import registry

    classe = getattr(registry, "SonioxSTTConfiguration", None)
    assert classe is not None, (
        "SonioxSTTConfiguration does not exist in registry.py: Soniox is not "
        "declared, so it is on no screen and no call can use it."
    )
    return classe


def _config(**reglages):
    return _classe()(api_key="soniox-key", **reglages)


def _audio_config():
    return AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=24000)


def _service(keyterms=None, **reglages):
    """The connector the call builds, through the factory the call uses."""
    from api.services.pipecat.service_factory import create_stt_service

    return create_stt_service(
        SimpleNamespace(stt=_config(**reglages)), _audio_config(), keyterms=keyterms
    )


class _FausseConnexion:
    def __init__(self):
        self.envois = []
        self.state = None

    async def send(self, message):
        self.envois.append(message)


async def _message_de_configuration(service):
    """What Soniox receives first on the socket: the whole configuration."""
    connexion = _FausseConnexion()
    adresses = []

    async def se_connecter(adresse, *args, **kwargs):
        adresses.append(adresse)
        return connexion

    service._websocket_connect = se_connecter
    await service._connect_websocket()
    assert connexion.envois, "the connector sent no configuration message"
    message = json.loads(connexion.envois[0])
    message["_adresse"] = adresses[0]
    return message


# --------------------------------------------------------------------------- #
# 1. Declared, under upstream's names -- which is what puts it on screen
# --------------------------------------------------------------------------- #


def test_soniox_est_un_fournisseur_de_transcription_declare():
    from api.services.configuration.registry import (
        REGISTRY,
        ServiceProviders,
        ServiceType,
    )

    assert ServiceProviders.SONIOX.value == "soniox"
    assert REGISTRY[ServiceType.STT]["soniox"] is _classe()


def test_la_route_des_defauts_sert_soniox_donc_il_est_dans_le_menu():
    from api.routes.organization import _byok_provider_schemas
    from api.services.configuration.registry import ServiceType

    assert "soniox" in _byok_provider_schemas(ServiceType.STT)


def test_les_listes_de_lamont_sont_reprises_sous_leurs_noms():
    from api.services.configuration.options import (
        SONIOX_STT_LANGUAGES,
        SONIOX_STT_MODELS,
    )

    assert "stt-rt-v5" in SONIOX_STT_MODELS
    assert "fr" in SONIOX_STT_LANGUAGES and "multi" in SONIOX_STT_LANGUAGES


@pytest.mark.parametrize("champ", REGLAGES_EXPOSES)
def test_le_reglage_est_declare_range_et_libelle(champ):
    proprietes = _classe().model_json_schema()["properties"]
    assert champ in proprietes, f"{champ} is not declared, so it is not on screen"
    assert proprietes[champ].get("mark_groupe"), f"{champ} has no sub-menu (E2)"
    libelle = proprietes[champ].get("mark_libelle") or {}
    assert libelle.get("en") and libelle.get("fr"), f"{champ} has no label in both languages"


def test_le_contexte_nest_pas_un_champ_a_lecran():
    """The list of terms is fed by the agent's lexicon, never typed here: a
    second live field for the same thing would be saved and ignored."""
    assert "context" not in _classe().model_json_schema()["properties"]


def test_les_valeurs_par_defaut_sont_celles_decidees():
    config = _config()
    assert config.model == "stt-rt-v5"
    assert config.language == "fr"
    assert config.endpoint_detection is True
    assert config.base_url == ADRESSE_EUROPE
    assert config.region == "eu"
    # ⛔ No value chosen by the chantier: Soniox's own default applies.
    for champ in (*REGLAGES_FIN_DE_TOUR, "language_hints_strict"):
        assert getattr(config, champ) is None, champ
    # Declared at the state the connector runs them, so the switch does not lie.
    assert config.enable_speaker_diarization is False
    assert config.enable_language_identification is False


@pytest.mark.parametrize(
    "champ, trop_bas, trop_haut",
    [
        ("max_endpoint_delay_ms", 499, 3001),
        ("endpoint_sensitivity", -1.01, 1.01),
        ("endpoint_latency_adjustment_level", -1, 4),
    ],
)
def test_les_bornes_de_la_documentation_sont_tenues(champ, trop_bas, trop_haut):
    for valeur in (trop_bas, trop_haut):
        with pytest.raises(ValidationError):
            _config(**{champ: valeur})


def test_le_discriminateur_accepte_ce_que_lecran_enverra():
    from api.services.configuration.registry import STTConfig

    config = TypeAdapter(STTConfig).validate_python(
        {
            "provider": "soniox",
            "api_key": "soniox-key",
            "model": "stt-rt-v5",
            "language": "fr",
            "max_endpoint_delay_ms": 1200,
        }
    )
    assert isinstance(config, _classe())
    assert config.max_endpoint_delay_ms == 1200


def test_une_langue_inconnue_est_refusee_a_lenregistrement():
    with pytest.raises(ValidationError):
        _config(language="klingon")


@pytest.mark.parametrize("langue", ["fr", "en", "de", "multi"])
def test_chaque_langue_proposee_se_construit(langue):
    """Every code the screen offers becomes a hint the connector accepts."""
    from api.services.configuration.options import SONIOX_STT_LANGUAGES

    assert langue in SONIOX_STT_LANGUAGES
    _service(language=langue)


def test_toutes_les_langues_proposees_se_construisent():
    from pipecat.transcriptions.language import Language

    from api.services.configuration.options import SONIOX_STT_LANGUAGES

    for code in SONIOX_STT_LANGUAGES:
        if code != "multi":
            Language(code)


def test_la_region_suit_ladresse():
    assert _config(base_url=ADRESSE_MONDIALE).region == "global"
    assert _config(base_url=ADRESSE_EUROPE).region == "eu"
    assert _config(base_url="").region == "eu"
    # A region written by hand does not survive: it is a mirror, not a choice.
    assert _config(base_url=ADRESSE_MONDIALE, region="eu").region == "global"


# --------------------------------------------------------------------------- #
# 2. Transmitted -- through the factory the call uses
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_sans_reglage_soniox_decide_en_europe_en_francais():
    message = await _message_de_configuration(_service())
    assert message["_adresse"] == ADRESSE_EUROPE
    assert message["model"] == "stt-rt-v5"
    assert message["language_hints"] == ["fr"]
    assert message["enable_endpoint_detection"] is True
    for champ in REGLAGES_FIN_DE_TOUR:
        assert message[champ] is None, champ
    assert message["context"] is None


@pytest.mark.asyncio
async def test_chaque_reglage_rempli_arrive_dans_le_message():
    message = await _message_de_configuration(
        _service(
            language="de",
            language_hints_strict=True,
            enable_language_identification=True,
            enable_speaker_diarization=True,
            max_endpoint_delay_ms=1200,
            endpoint_sensitivity=0.4,
            endpoint_latency_adjustment_level=2,
            base_url=ADRESSE_MONDIALE,
        )
    )
    assert message["_adresse"] == ADRESSE_MONDIALE
    assert message["language_hints"] == ["de"]
    assert message["language_hints_strict"] is True
    assert message["enable_language_identification"] is True
    assert message["enable_speaker_diarization"] is True
    assert message["max_endpoint_delay_ms"] == 1200
    assert message["endpoint_sensitivity"] == 0.4
    assert message["endpoint_latency_adjustment_level"] == 2


@pytest.mark.asyncio
async def test_multi_nenvoie_aucune_langue():
    message = await _message_de_configuration(_service(language="multi"))
    assert not message["language_hints"]


@pytest.mark.asyncio
async def test_une_adresse_vide_part_en_europe():
    message = await _message_de_configuration(_service(base_url="  "))
    assert message["_adresse"] == ADRESSE_EUROPE


@pytest.mark.parametrize(
    "adresse", ["ftp://stt-rt.soniox.com", "https://stt-rt.soniox.com", "wss://", "stt-rt.soniox.com"]
)
def test_une_adresse_invalide_est_refusee_a_lenregistrement(adresse):
    """Refused at the door, not mid-call. ⛔ The factory's URL check does
    nothing in an ``oss`` deployment (ours), and the connector dials whatever
    it is given: a wrong address would cost the call its transcription."""
    with pytest.raises(ValidationError):
        _config(base_url=adresse)


# --------------------------------------------------------------------------- #
# 3. The end of the turn: one rule, on screen and in code (E8)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_detecteur_local_les_trois_reglages_ne_partent_pas():
    """Switched off, the three settings are hidden -- and must not leave either."""
    message = await _message_de_configuration(
        _service(
            endpoint_detection=False,
            max_endpoint_delay_ms=1200,
            endpoint_sensitivity=0.4,
            endpoint_latency_adjustment_level=2,
        )
    )
    assert message["enable_endpoint_detection"] is False
    for champ in REGLAGES_FIN_DE_TOUR:
        assert message[champ] is None, champ


def test_lecran_masque_les_trois_reglages_sur_la_meme_regle():
    proprietes = _classe().model_json_schema()["properties"]
    for champ in REGLAGES_FIN_DE_TOUR:
        assert proprietes[champ].get("visible_when") == {"endpoint_detection": True}, champ


def test_qui_decide_de_la_fin_de_tour():
    from api.services.pipecat.service_factory import stt_uses_external_turns

    assert stt_uses_external_turns(SimpleNamespace(stt=_config())) is True
    assert (
        stt_uses_external_turns(SimpleNamespace(stt=_config(endpoint_detection=False)))
        is False
    )


def test_la_fin_de_tour_de_soniox_nest_pas_coupee_a_la_fabrique():
    assert _service()._vad_force_turn_endpoint is False
    assert _service(endpoint_detection=False)._vad_force_turn_endpoint is True


# --------------------------------------------------------------------------- #
# 4. The lexicon: no ceiling declared, so no list
# --------------------------------------------------------------------------- #


def test_aucun_plafond_nest_declare_pour_soniox_avant_la_sonde():
    from api.services.configuration.plafond_lexique import plafond_du_lexique

    assert plafond_du_lexique("soniox", "stt-rt-v5") is None


@pytest.mark.asyncio
async def test_une_liste_recue_quand_meme_ne_part_pas():
    """Belt and braces: even handed a list, the factory sends none until the
    ceiling is measured (rule Q1 of the lexicon, question n° 250)."""
    message = await _message_de_configuration(_service(keyterms=["poêle", "insert"]))
    assert message["context"] is None


# --------------------------------------------------------------------------- #
# 5. The stamp: what the call says it was played with
# --------------------------------------------------------------------------- #


def test_lestampille_dit_ce_que_le_message_porte():
    from api.services.pipecat.service_factory import stamp_transcription_settings

    config = _config(
        endpoint_detection=False, max_endpoint_delay_ms=1200, base_url=ADRESSE_MONDIALE
    )
    stamp = stamp_transcription_settings({}, config)["stt_settings"]
    assert stamp["endpoint_detection"] is False
    assert stamp["base_url"] == ADRESSE_MONDIALE
    assert stamp["language_hints"] == ["fr"]
    # Hidden and not sent, so not stamped either.
    assert "max_endpoint_delay_ms" not in stamp
    # ⛔ Nothing of Deepgram's on a Soniox call.
    assert "endpointing" not in stamp


# --------------------------------------------------------------------------- #
# 6. The key is checked against the region the address points to
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "adresse, api_attendue",
    [
        (ADRESSE_EUROPE, "https://api.eu.soniox.com/v1/models"),
        ("", "https://api.eu.soniox.com/v1/models"),
        (ADRESSE_MONDIALE, "https://api.soniox.com/v1/models"),
    ],
)
def test_la_cle_est_verifiee_dans_la_region_de_ladresse(monkeypatch, adresse, api_attendue):
    from api.services.configuration import check_validity

    appels = []

    class _Reponse:
        def raise_for_status(self):
            return None

    def faux_get(url, headers=None, timeout=None):
        appels.append((url, headers))
        return _Reponse()

    monkeypatch.setattr(check_validity.httpx, "get", faux_get)
    statuts = check_validity.UserConfigurationValidator()._validate_service(
        _config(base_url=adresse), "stt"
    )
    assert statuts == []
    assert appels == [(api_attendue, {"Authorization": "Bearer soniox-key"})]


# --------------------------------------------------------------------------- #
# 7. Nobody else moves
# --------------------------------------------------------------------------- #


def test_deepgram_reste_le_fournisseur_par_defaut():
    from api.services.configuration.defaults import DEFAULT_SERVICE_PROVIDERS

    assert DEFAULT_SERVICE_PROVIDERS["stt"] == "deepgram"


def test_flux_pilote_toujours_ses_tours():
    from api.services.configuration.registry import DeepgramSTTConfiguration
    from api.services.pipecat.service_factory import stt_uses_external_turns

    flux = DeepgramSTTConfiguration(api_key="k", model="flux-general-multi")
    nova = DeepgramSTTConfiguration(api_key="k", model="nova-3-general")
    assert stt_uses_external_turns(SimpleNamespace(stt=flux)) is True
    assert stt_uses_external_turns(SimpleNamespace(stt=nova)) is False


# --------------------------------------------------------------------------- #
# 8. Installed on every path (§4.4 of 18-ajout-fournisseur.md)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "chemin", ["api/Dockerfile", "scripts/setup_requirements.sh", "scripts/setup_requirements.ps1"]
)
def test_lextra_soniox_est_dans_chaque_chemin_dinstallation(chemin):
    """Empty in Pipecat 49ba358, declared anyway: on 2026-09-08 an extra fixed on
    one path only made the whole suite fall at collection."""
    import re
    from pathlib import Path

    texte = (Path(__file__).resolve().parents[3] / chemin).read_text(encoding="utf-8")
    listes = re.findall(r"pipecat(?:-ai)?\[([a-z0-9,\-]+)\]", texte)
    listes = [liste for liste in listes if "deepgram" in liste]
    assert listes, f"no pipecat install list found in {chemin}"
    for liste in listes:
        assert "soniox" in liste.split(","), f"soniox missing from {chemin}"


# --------------------------------------------------------------------------- #
# 9. Added after the independent review of 2026-09-29
# --------------------------------------------------------------------------- #

# What Pipecat's Soniox settings carry and is deliberately NOT a field here,
# each with its reason. Anything else Pipecat adds must be exposed, or listed.
NON_EXPOSES_ET_POURQUOI = {
    "model": "the model field, at the top of the provider",
    "language": "Pipecat's generic language; Soniox reads language_hints, fed by our `language`",
    "language_hints": "fed by our `language` field (upstream's name)",
    "context": "fed by the agent's lexicon, never typed here, and none sent before the probe",
    "client_reference_id": "an internal trace identifier, not a setting",
}


def test_chaque_reglage_de_pipecat_est_expose_ou_ecarte_par_ecrit():
    """The sweep of the plan (lot 1): a setting Pipecat gains at the next
    version bump fails here instead of leaving the screen in silence."""
    import dataclasses

    from pipecat.services.soniox.stt import SonioxSTTSettings
    from pipecat.services.stt_service import STTSettings

    herites = {champ.name for champ in dataclasses.fields(STTSettings)}
    propres = {champ.name for champ in dataclasses.fields(SonioxSTTSettings)} - herites
    declares = set(_classe().model_fields)
    manquants = propres - declares - set(NON_EXPOSES_ET_POURQUOI)
    assert not manquants, f"Pipecat's Soniox settings not exposed and not listed: {sorted(manquants)}"


def test_la_fabrique_masque_exactement_ce_que_lecran_masque():
    from api.services.pipecat.service_factory import SONIOX_FIN_DE_TOUR_FIELDS

    assert set(SONIOX_FIN_DE_TOUR_FIELDS) == set(REGLAGES_FIN_DE_TOUR)


def test_uniquement_cette_langue_est_refuse_sans_langue():
    with pytest.raises(ValidationError):
        _config(language="multi", language_hints_strict=True)
    assert _config(language="fr", language_hints_strict=True).language_hints_strict is True


def test_la_latence_de_transcription_est_ignoree_quand_soniox_decide():
    from api.services.pipecat.reglages_tour_de_parole import (
        appliquer_latence_de_transcription,
    )

    service = _service()
    avant = service._ttfs_p99_latency
    appliquer_latence_de_transcription(service, 0.9, pilote_les_tours=True)
    assert service._ttfs_p99_latency == avant

    local = _service(endpoint_detection=False)
    appliquer_latence_de_transcription(local, 0.9, pilote_les_tours=False)
    assert local._ttfs_p99_latency == 0.9
