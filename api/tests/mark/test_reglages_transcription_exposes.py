"""[.mark] Non-regression test for the Deepgram transcription settings.

The question this file answers, and it answers only this one:

    Are the fourteen classic Deepgram settings and the five Flux settings
    declared on the configuration, and do the ones that are filled in actually
    reach the request that goes out to Deepgram?

⛔ Read that scope literally. This file does NOT prove that a value improves
the agent, and it does not prove Deepgram accepts it. Acceptance is measured
on a real connection by ``verifier-reglages-transcription.mjs``; what a setting
DOES to a transcription needs a phone number (question n° 42). This file proves
only that nothing is silently dropped between the screen and the wire.

Why it exists
-------------
``endpointing`` commands the moment the agent takes the floor, so it caps the
perceived quality of the whole chain. It was written as a literal ``100`` in
the factory, chosen by nobody: it arrived on 2025-11-21 inside a commit about
embedded website domains. Fourteen other settings existed at Deepgram and two
were reachable.

The screen is generated from the Pydantic schema, so declaring the fields is
what puts them on screen. That is why this file asserts on the schema as well
as on the request: a field that leaves the schema disappears from the screen
without breaking anything else.

What "not sent" looks like here
-------------------------------
⛔ Not like Mistral. ``DeepgramSTTSettings`` uses a ``NOT_GIVEN`` sentinel,
but the CONNECTOR never sees it: ``DeepgramSTTService.__init__`` builds a
complete settings object with its own defaults (``numerals=False``,
``punctuate=True``, ``interim_results=True``...) and applies ours as a delta on
top. So a field we do not collect is not "absent from the request" -- it is
"left at the connector's default", which is exactly today's behaviour.

Measured through the factory on 2026-09-11, before this patch:

    classic: detect_entities=false diarize=false dictation=false
             endpointing=100 interim_results=true keyterm=[] numerals=false
             profanity_filter=false punctuate=true smart_format=false
    flux:    eager_eot_threshold=0.5 eot_threshold=0.7 eot_timeout_ms=3000
             mip_opt_out=true language_hint=<derived from the language>

``keywords``, ``redact``, ``replace``, ``search`` and ``utterance_end_ms`` are
genuinely absent from the request today, because the connector defaults them
to ``None`` and ``_build_connect_kwargs`` skips ``None``.

⛔ Expected RED before the patch, and it fails on the schema first: none of
the nineteen fields exist yet on ``DeepgramSTTConfiguration``. That is the
intended failure -- a rouge that names what is missing.
"""

from types import SimpleNamespace

import pytest

from api.services.configuration import registry as registre
from api.services.configuration.registry import (
    DeepgramSTTConfiguration,
    ServiceProviders,
)
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.service_factory import create_stt_service

# The fourteen classic settings, in the order Deepgram's own connector
# declares them. ⛔ ``keyterm`` is deliberately NOT here: it is fed by the
# agent's Dictionary and overwritten on every call, so declaring it would put
# a second live field for the same thing next to the Dictionary on the same
# screen (decision of Evan, 2026-09-11).
LES_QUATORZE = (
    "detect_entities",
    "diarize",
    "dictation",
    "endpointing",
    "interim_results",
    "keywords",
    "numerals",
    "profanity_filter",
    "punctuate",
    "redact",
    "replace",
    "search",
    "smart_format",
    "utterance_end_ms",
)

# The five Flux settings. Another service, another class, another set.
LES_CINQ_FLUX = (
    "eot_threshold",
    "eager_eot_threshold",
    "eot_timeout_ms",
    "language_hints",
    "min_confidence",
)

# The values that run today, written as literals in the factory before this
# patch. Declaring them as the defaults is what makes this visible on screen
# without changing a single call.
ENDPOINTING_ACTUEL = 100
PROFANITY_FILTER_ACTUEL = False
EOT_THRESHOLD_ACTUEL = 0.7
EAGER_EOT_THRESHOLD_ACTUEL = 0.5
EOT_TIMEOUT_MS_ACTUEL = 3000

# ⛔ The literal shape of today's request, measured through the factory on
# 2026-09-11. This is the ONLY thing that proves the patch changes nothing for
# a client who fills in nothing. Comparing against values re-derived from the
# code would make it tautological: the code is what moves.
REQUETE_CLASSIQUE_AUJOURDHUI = {
    "detect_entities": "false",
    "diarize": "false",
    "dictation": "false",
    "endpointing": "100",
    "interim_results": "true",
    "keyterm": [],
    "numerals": "false",
    "profanity_filter": "false",
    "punctuate": "true",
    "smart_format": "false",
    "model": "nova-3-general",
    "language": "fr",
    "encoding": "linear16",
    "channels": "1",
    "multichannel": "false",
    "sample_rate": "0",
    "mip_opt_out": "true",
}

REQUETE_FLUX_AUJOURDHUI = (
    "model=flux-general-multi"
    "&sample_rate=0"
    "&encoding=linear16"
    "&eager_eot_threshold=0.5"
    "&eot_threshold=0.7"
    "&eot_timeout_ms=3000"
    "&mip_opt_out=true"
    "&language_hint=fr"
)


def _audio_config():
    return AudioConfig(
        transport_in_sample_rate=16000,
        transport_out_sample_rate=24000,
    )


def _service(model="nova-3-general", language="fr", **reglages):
    """Build the STT service the runtime builds, through create_stt_service.

    ⛔ Through the public entry point and through the real Pydantic
    configuration, never a SimpleNamespace with the settings pasted on: that
    would skip the declaration, which is the half of this patch that puts the
    fields on screen.
    """
    user_config = SimpleNamespace(
        stt=DeepgramSTTConfiguration(
            api_key="deepgram-key",
            model=model,
            language=language,
            **reglages,
        )
    )
    return create_stt_service(user_config, _audio_config())


def _requete_classique(**reglages):
    """The connection parameters that would be handed to Deepgram."""
    return _service(**reglages)._build_connect_kwargs()


def _requete_flux(language="fr", **reglages):
    """The query string Flux dials with."""
    return _service(
        model="flux-general-multi", language=language, **reglages
    )._build_query_string()


def _collecte(nom):
    """The collection tuple, or a rouge that names it rather than an ImportError."""
    valeur = getattr(registre, nom, None)
    assert valeur is not None, (
        f"'{nom}' does not exist in registry.py. It is the single collection "
        f"point the factory reads to decide which settings to forward; without "
        f"it every setting would need its own branch."
    )
    return valeur


# --------------------------------------------------------------------------- #
# 1. Declared -- which is what puts them on screen
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("champ", LES_QUATORZE + LES_CINQ_FLUX)
def test_le_reglage_est_declare_donc_affiche(champ):
    """The settings screen is generated from this schema, field by field.

    A field missing here is a field missing on screen, and a setting that is
    not on screen is one we have agreed never to touch.
    """
    proprietes = DeepgramSTTConfiguration.model_json_schema()["properties"]

    assert champ in proprietes, (
        f"'{champ}' is not declared on DeepgramSTTConfiguration, so it cannot "
        f"appear on the transcription settings screen."
    )
    assert proprietes[champ].get("description"), (
        f"'{champ}' carries no description: the screen would show a bare input "
        f"with no sentence explaining what it does."
    )


def test_le_dictionnaire_de_lagent_nest_pas_duplique_a_lecran():
    """``keyterm`` stays where it belongs, and only there.

    It is overwritten on every call by the agent's Dictionary
    (``workflow_configurations["dictionary"]``). Declaring it would put a
    second live field for the same thing right next to the Dictionary, on the
    same screen, with the client's value losing every time.
    """
    proprietes = DeepgramSTTConfiguration.model_json_schema()["properties"]

    assert "keyterm" not in proprietes, (
        "'keyterm' is declared on the client configuration. It is fed by the "
        "agent's Dictionary and overwritten on every call, so the field would "
        "be filled in, saved, and ignored."
    )


def test_les_valeurs_qui_tournent_aujourdhui_sont_les_defauts():
    """The literals in the factory become the defaults, so nothing moves.

    100 ms and "profanity filter off" are not tastes, they are what runs. Same
    for the three Flux thresholds. Declaring them as defaults is what makes
    this patch invisible in behaviour and visible on screen at once.
    """
    config = DeepgramSTTConfiguration(api_key="deepgram-key")

    assert config.endpointing == ENDPOINTING_ACTUEL
    assert config.profanity_filter is PROFANITY_FILTER_ACTUEL
    assert config.eot_threshold == EOT_THRESHOLD_ACTUEL
    assert config.eager_eot_threshold == EAGER_EOT_THRESHOLD_ACTUEL
    assert config.eot_timeout_ms == EOT_TIMEOUT_MS_ACTUEL


@pytest.mark.parametrize(
    "champ",
    [
        champ
        for champ in LES_QUATORZE + LES_CINQ_FLUX
        if champ
        not in (
            "endpointing",
            "profanity_filter",
            "eot_threshold",
            "eager_eot_threshold",
            "eot_timeout_ms",
        )
    ],
)
def test_les_autres_reglages_sont_absents_par_defaut(champ):
    """Absent means not collected, which means the connector keeps its default.

    ⛔ Not the same thing as "absent from the request": the Deepgram connector
    fills in its own defaults for the booleans. Absent here means "we send
    nothing about it", which is today's behaviour exactly.
    """
    config = DeepgramSTTConfiguration(api_key="deepgram-key")

    assert getattr(config, champ) is None


# --------------------------------------------------------------------------- #
# 2. Transmitted -- the point of the whole patch
# --------------------------------------------------------------------------- #


def test_les_quatorze_reglages_arrivent_dans_la_requete():
    """One assertion per setting, so a rouge names the one that was dropped."""
    requete = _requete_classique(
        detect_entities=True,
        diarize=True,
        dictation=True,
        endpointing=450,
        interim_results=False,
        keywords=["veranda", "poele"],
        numerals=True,
        profanity_filter=True,
        punctuate=False,
        redact=["pci"],
        replace=["poil:poele"],
        search=["devis"],
        smart_format=True,
        utterance_end_ms=1200,
    )

    assert requete["detect_entities"] == "true"
    assert requete["diarize"] == "true"
    assert requete["dictation"] == "true"
    assert requete["endpointing"] == "450"
    assert requete["interim_results"] == "false"
    assert requete["keywords"] == ["veranda", "poele"]
    assert requete["numerals"] == "true"
    assert requete["profanity_filter"] == "true"
    assert requete["punctuate"] == "false"
    assert requete["redact"] == ["pci"]
    assert requete["replace"] == ["poil:poele"]
    assert requete["search"] == ["devis"]
    assert requete["smart_format"] == "true"
    assert requete["utterance_end_ms"] == "1200"


def test_lendpointing_configure_remplace_le_cent_ecrit_en_dur():
    """The literal in the factory is what this patch removes.

    Without this test the field could be declared, stored, shown on screen and
    still overwritten by 100 on the way out -- configured then ignored, the
    worst of both worlds. And this is the setting that caps the whole chain.
    """
    assert _requete_classique(endpointing=450)["endpointing"] == "450"


def test_les_quatre_reglages_flux_arrivent_dans_la_requete():
    """Flux is a different connector with a different query builder."""
    requete = _requete_flux(
        eot_threshold=0.85,
        eager_eot_threshold=0.4,
        eot_timeout_ms=4500,
    )

    assert "eot_threshold=0.85" in requete
    assert "eager_eot_threshold=0.4" in requete
    assert "eot_timeout_ms=4500" in requete


def test_les_indications_de_langue_configurees_gagnent_sur_la_deduction():
    """``language_hints`` is derived from the language today, and stays so.

    Filled in, it wins; left empty, the derivation from the chosen language
    applies exactly as it does now. ⚠️ Two fields commanding the same thing on
    one screen is the defect decision n° 2 refuses for ``keyterm`` -- flagged
    for Evan in A-VALIDER.md rather than settled here.
    """
    requete = _requete_flux(language="fr", language_hints=["es", "it"])

    assert "language_hint=es" in requete
    assert "language_hint=it" in requete


def test_le_seuil_de_confiance_ne_part_pas_chez_deepgram():
    """``min_confidence`` is a filter applied here, on what Deepgram returns.

    ⛔ It is the first genuinely "Pipecat" setting of the set. Asserting it in
    the query string would fail; asserting it lands in the connector's settings
    is what proves it is not dropped. Its description on screen has to say so,
    otherwise it is a setting we believe we know the location of.
    """
    service = _service(model="flux-general-multi", min_confidence=0.6)

    assert service._settings.min_confidence == 0.6
    assert "min_confidence" not in service._build_query_string()


# --------------------------------------------------------------------------- #
# 3. Nothing else moves -- the part that must stay boring
# --------------------------------------------------------------------------- #


def test_sans_reglage_la_requete_classique_est_celle_daujourdhui():
    """The whole dict, compared to a literal measured before the patch.

    🔑 This is the test of every client who never opens the screen. It is
    compared key by key rather than as a whole so a rouge names the parameter
    that moved instead of printing two walls of text.
    """
    requete = _requete_classique()

    assert set(requete) == set(REQUETE_CLASSIQUE_AUJOURDHUI), (
        f"parameters added: {sorted(set(requete) - set(REQUETE_CLASSIQUE_AUJOURDHUI))}, "
        f"removed: {sorted(set(REQUETE_CLASSIQUE_AUJOURDHUI) - set(requete))}"
    )
    for cle, attendu in REQUETE_CLASSIQUE_AUJOURDHUI.items():
        assert requete[cle] == attendu, (
            f"'{cle}' went out as {requete[cle]!r} where it used to go out as "
            f"{attendu!r}. Every existing client would change behaviour."
        )


def test_sans_reglage_la_requete_flux_est_celle_daujourdhui():
    """Same guarantee on the Flux path, query string included."""
    assert _requete_flux() == REQUETE_FLUX_AUJOURDHUI


def test_un_reglage_seul_nentraine_pas_les_autres():
    """Filling one field must not start sending the thirteen others.

    This is the failure mode of a "collect everything and pass it on" patch:
    handing Deepgram a wall of None or false values changes the behaviour of
    every agent that never touched the screen.
    """
    requete = _requete_classique(endpointing=450)

    attendu = dict(REQUETE_CLASSIQUE_AUJOURDHUI, endpointing="450")
    assert set(requete) == set(attendu), (
        f"parameters added: {sorted(set(requete) - set(attendu))}, "
        f"removed: {sorted(set(attendu) - set(requete))}"
    )
    for cle, valeur in attendu.items():
        assert requete[cle] == valeur


def test_les_autres_fournisseurs_de_transcription_ne_bougent_pas():
    """Six other STT providers go through the same factory.

    OpenAI is the witness: nothing was declared on its configuration, so it
    gains nothing and loses nothing.
    """
    from api.services.configuration.registry import OpenAISTTConfiguration

    service = create_stt_service(
        SimpleNamespace(
            stt=OpenAISTTConfiguration(
                api_key="openai-key", provider=ServiceProviders.OPENAI
            )
        ),
        _audio_config(),
    )

    assert service._settings.model == "gpt-4o-transcribe"


# --------------------------------------------------------------------------- #
# 4. The collection point cannot drift away from the declaration
# --------------------------------------------------------------------------- #


def test_le_point_de_collecte_classique_dit_la_meme_chose_que_la_declaration():
    """Two lists of field names is two chances to be right and one to be wrong.

    A field declared on the configuration but missing from the collection tuple
    is shown on screen, saved, and never sent -- and nothing complains.
    """
    collecte = _collecte("DEEPGRAM_STT_FIELDS")

    assert collecte == LES_QUATORZE

    declares = DeepgramSTTConfiguration.model_json_schema()["properties"]
    for champ in collecte:
        assert champ in declares


def test_le_point_de_collecte_flux_dit_la_meme_chose_que_la_declaration():
    collecte = _collecte("DEEPGRAM_FLUX_FIELDS")

    assert collecte == LES_CINQ_FLUX

    declares = DeepgramSTTConfiguration.model_json_schema()["properties"]
    for champ in collecte:
        assert champ in declares


def test_aucun_reglage_declare_nest_oublie_par_les_deux_collectes():
    """The direction that fails in silence.

    A twentieth field declared on the configuration but forgotten in both
    tuples would be shown on screen, saved, and never sent. Anything declared
    that is not plumbing (provider, model, language, credentials) has to be in
    one of the two.
    """
    PLOMBERIE = {"provider", "api_key", "model", "language", "base_url"}

    declares = set(DeepgramSTTConfiguration.model_json_schema()["properties"])
    collectes = set(_collecte("DEEPGRAM_STT_FIELDS")) | set(
        _collecte("DEEPGRAM_FLUX_FIELDS")
    )

    oublies = declares - PLOMBERIE - collectes
    assert not oublies, (
        f"declared on DeepgramSTTConfiguration but absent from both collection "
        f"tuples: {sorted(oublies)}. Such a field appears on screen, is saved, "
        f"and is never sent."
    )


# --------------------------------------------------------------------------- #
# 5. The screen test's copy of this schema cannot drift away from it
# --------------------------------------------------------------------------- #


def _copie_du_schema_cote_ecran() -> str:
    from pathlib import Path

    copie = (
        Path(__file__).resolve().parents[3]
        / "ui"
        / "src"
        / "components"
        / "mark"
        / "reglages-transcription-ecran.test.tsx"
    )
    assert copie.exists(), f"the screen test is gone: {copie}"
    return copie.read_text(encoding="utf-8")


def _branche_utile(declare: dict) -> dict:
    """The part of a property that carries the type and the bounds.

    An optional field is written by Pydantic as an ``anyOf`` with a null
    branch; the bounds live on the other one.
    """
    if "anyOf" not in declare:
        return declare
    return next(
        branche for branche in declare["anyOf"] if branche.get("type") != "null"
    )


@pytest.mark.parametrize("champ", LES_QUATORZE + LES_CINQ_FLUX)
def test_la_copie_du_schema_de_transcription_dit_la_meme_chose(champ):
    """The screen test carries a literal copy of what the API serves.

    That copy is deliberate — it is the contract between Python and the screen,
    and it must break loudly when one side moves. But a copy nobody compares is
    a copy that drifts: on the Mistral chantier it had already drifted the day
    it was written, a bound reading 0 on one side and 1 on the other. So the
    comparison is made here, from the side that owns the truth.

    ⛔ Every bound, the type, and the sentence — not a sample of them.
    """
    import re

    texte = _copie_du_schema_cote_ecran()
    declare = DeepgramSTTConfiguration.model_json_schema()["properties"][champ]
    utile = _branche_utile(declare)

    # The field's block in the TypeScript literal, from its name to the closing
    # brace at the same indentation.
    bloc = re.search(
        re.escape(champ) + r":\s*\{(.+?)\n        \},", texte, re.DOTALL
    )
    assert bloc, f"'{champ}' is missing from the screen test's copy of the schema"
    copie = bloc.group(1)

    for cle in ("minimum", "maximum", "exclusiveMinimum"):
        if cle not in utile:
            assert f"{cle}:" not in copie, (
                f"'{champ}': the screen test declares a {cle} that the schema "
                f"does not have."
            )
            continue
        attendu = utile[cle]
        rendu = str(int(attendu)) if float(attendu) == int(attendu) else str(attendu)
        assert f"{cle}: {rendu}" in copie, (
            f"'{champ}': the screen test says something else than "
            f"{cle}={rendu}. Realign the copy in "
            f"reglages-transcription-ecran.test.tsx."
        )

    assert f'type: "{utile["type"]}"' in copie, (
        f"'{champ}': the screen test types it as something other than "
        f"{utile['type']}, so it would render with the wrong control."
    )

    assert declare["description"] in copie, (
        f"'{champ}': the sentence in the screen test is not the sentence the "
        f"API serves. The screen shows the API's one, so the test would be "
        f"checking a sentence nobody reads."
    )
