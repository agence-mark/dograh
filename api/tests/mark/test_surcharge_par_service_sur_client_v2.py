"""[.mark] Non-regression test for a per-service override on a v2 client.

The question this file answers, and it answers only this one:

    Can an agent replace ONE service while still inheriting everything else
    from its client's configuration -- and does that inheritance stay alive
    when the client changes something?

Why it exists
-------------
Upstream never served this case. On their screens the two override formats
were exclusive: a client on the old format saw the per-service form, a client
on the new one saw the all-or-nothing replacement. We want both available to
the SAME client, because the offer is one organization per client and one
agent that changes its voice without freezing a copy of everything else.

The server side supports it -- the field-by-field merge is on the execution
path -- but "supports it" is a reading of the code, and a reading is not a
guarantee. This file turns it into one.

🚨 The part that was NOT supported, and that this file fixes
------------------------------------------------------------
Saving the organization's model configuration runs a migration over every
agent in that organization, which converts each per-service override into a
complete copy and then deletes it. That migration is not a one-off: it runs on
EVERY save of the organization configuration.

So a per-service override was silently converted into a frozen copy the next
time anyone touched the client's configuration -- and from that moment the
agent stopped inheriting anything. Nothing on any screen said so.

A per-service override written on purpose now carries a marker, and the
migration leaves marked overrides alone. Their own migration path, for the
legacy overrides it was built for, is unchanged.
"""

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.schemas.ai_model_configuration import (
    BYOKAIModelConfiguration,
    BYOKPipelineAIModelConfiguration,
    OrganizationAIModelConfigurationV2,
    compile_ai_model_configuration_v2,
)
from api.services.configuration.ai_model_configuration import (
    DELIBERATE_PER_SERVICE_OVERRIDE_KEY,
    WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY,
    migrate_workflow_configuration_model_override_to_v2,
)
from api.services.configuration.registry import (
    DeepgramSTTConfiguration,
    MistralLLMConfiguration,
    MistralTTSConfiguration,
)
from api.services.configuration.resolve import resolve_effective_config

# The marker the agent screen writes next to a deliberate per-service override.
# Written as a literal on purpose: this file is one of the two sides of the
# contract, so importing the constant here would make the comparison below
# compare a value to itself.
MARQUEUR = "mark_per_service_override"


def _client_au_nouveau_format(modele="mistral-medium-latest") -> OrganizationAIModelConfigurationV2:
    """One client, configured the way .mark configures a client."""
    return OrganizationAIModelConfigurationV2(
        mode="byok",
        byok=BYOKAIModelConfiguration(
            mode="pipeline",
            pipeline=BYOKPipelineAIModelConfiguration(
                llm=MistralLLMConfiguration(api_key="cle-client", model=modele, temperature=0.2),
                tts=MistralTTSConfiguration(api_key="cle-client", voice="fr_marie_neutral"),
                stt=DeepgramSTTConfiguration(api_key="cle-client", model="nova-3-general"),
            ),
        ),
    )


# The agent replaces the voice, and nothing else.
SURCHARGE_VOIX_SEULE = {
    "tts": {
        "provider": "mistral",
        "api_key": "cle-client",
        "voice": "fr_marie_curious",
    }
}


# --------------------------------------------------------------------------- #
# 1. One service replaced, the rest inherited
# --------------------------------------------------------------------------- #


def test_lagent_remplace_la_voix_et_herite_de_tout_le_reste():
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())

    effective = resolve_effective_config(client, SURCHARGE_VOIX_SEULE)

    # What the agent changed.
    assert effective.tts.voice == "fr_marie_curious"
    # What it must still inherit, field by field -- a rouge here names exactly
    # which part of the client's configuration stopped being inherited.
    assert effective.llm.model == "mistral-medium-latest"
    assert effective.llm.temperature == 0.2
    assert effective.stt.model == "nova-3-general"
    assert effective.tts.model == "voxtral-mini-tts-latest"


def test_le_client_reste_intact_quand_lagent_surcharge():
    """The client's own configuration is never mutated by an agent's override."""
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())

    resolve_effective_config(client, SURCHARGE_VOIX_SEULE)

    assert client.tts.voice == "fr_marie_neutral"


def test_lheritage_suit_le_client_quand_il_change_de_modele():
    """The whole point of inheriting rather than copying.

    A complete override would have frozen the model of the day it was written.
    """
    apres = compile_ai_model_configuration_v2(
        _client_au_nouveau_format(modele="mistral-large-2512")
    )

    effective = resolve_effective_config(apres, SURCHARGE_VOIX_SEULE)

    assert effective.llm.model == "mistral-large-2512"
    assert effective.tts.voice == "fr_marie_curious"


def test_les_reglages_du_client_traversent_la_surcharge():
    """The six settings live on the client. An agent that overrides only its
    voice must still be played with the client's sampling settings."""
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())
    client.llm = client.llm.model_copy(update={"seed": 424242, "max_tokens": 180})

    effective = resolve_effective_config(client, SURCHARGE_VOIX_SEULE)

    assert effective.llm.seed == 424242
    assert effective.llm.max_tokens == 180


# --------------------------------------------------------------------------- #
# 1 bis. ONE transcription setting overridden, the rest still inherited
# --------------------------------------------------------------------------- #
#
# 🔑 Since 2026-09-11 the transcription carries nineteen settings, so the
# difference between "override one field" and "override the block" stopped
# being theoretical: an override that carried the whole block would freeze the
# model, the language and seventeen settings on the day it was written.
#
# The screen now sends only what changed. These tests are the server-side half
# of that contract: they prove the small override is enough, and that the agent
# keeps following its client.

# What the screen sends after the client changes `endpointing` on one agent:
# the provider (which the server compares) and the one field. Nothing else.
SURCHARGE_ENDPOINTING_SEUL = {
    "stt": {
        "provider": "deepgram",
        "endpointing": 450,
    }
}


def test_lagent_change_un_reglage_de_transcription_et_herite_du_reste():
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())

    effective = resolve_effective_config(client, SURCHARGE_ENDPOINTING_SEUL)

    assert effective.stt.endpointing == 450
    # Everything else still comes from the client.
    assert effective.stt.model == "nova-3-general"
    assert effective.stt.api_key == "cle-client"
    assert effective.stt.profanity_filter is False


def test_le_reglage_surcharge_suit_le_client_quand_il_change_de_modele_deepgram():
    """The failure a whole-block override would have caused, made visible.

    ⛔ This is the test the chantier exists for: an agent that changed one
    setting used to freeze the client's Deepgram model with it, and from that
    day it stopped following the client. Nothing on any screen said so.
    """
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())
    client.stt = client.stt.model_copy(update={"model": "nova-3-medical"})

    effective = resolve_effective_config(client, SURCHARGE_ENDPOINTING_SEUL)

    assert effective.stt.model == "nova-3-medical"
    assert effective.stt.endpointing == 450


def test_les_reglages_de_transcription_du_client_traversent_une_surcharge_de_voix():
    """An agent that only changes its voice keeps the client's transcription."""
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())
    client.stt = client.stt.model_copy(
        update={"endpointing": 300, "smart_format": True, "replace": ["poil:poele"]}
    )

    effective = resolve_effective_config(client, SURCHARGE_VOIX_SEULE)

    assert effective.stt.endpointing == 300
    assert effective.stt.smart_format is True
    assert effective.stt.replace == ["poil:poele"]


def test_une_surcharge_invalide_est_REFUSEE_au_lieu_de_passer():
    """🔴 Trouvé par la relecture du 11/09, et plus large que ce chantier.

    ``model_copy(update=...)`` ne joue AUCUN validateur : ni les bornes d'un
    champ, ni un validateur qui compare deux champs. Une surcharge d'agent
    pouvait donc écrire une configuration que l'écran refuse.

    Mesuré avant correction : ``eager_eot_threshold=0.9`` par-dessus un
    ``eot_threshold`` de 0,7 passait en silence — **Flux refuse ce couple, et
    l'appelant aurait parlé dans le vide**. ``eot_timeout_ms=999999`` aussi.

    ⚠️ Le trou est plus ancien que les réglages qui l'ont rendu visible : il
    valait déjà pour les six réglages Mistral exposés le 10/09, où une
    surcharge posait une température de 99 sans un mot. D'où le témoin Mistral
    ci-dessous.
    """
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())

    # Le couple interdit par Flux : chaque valeur est dans sa plage.
    with pytest.raises(ValidationError):
        resolve_effective_config(
            client,
            {"stt": {"provider": "deepgram", "eager_eot_threshold": 0.9}},
        )

    # Une borne de champ, sur le même chemin.
    with pytest.raises(ValidationError):
        resolve_effective_config(
            client, {"stt": {"provider": "deepgram", "eot_timeout_ms": 999999}}
        )

    # ⛔ Le témoin : le trou n'était pas propre à la transcription.
    with pytest.raises(ValidationError):
        resolve_effective_config(
            client, {"llm": {"provider": "mistral", "temperature": 99.0}}
        )


def test_une_surcharge_valide_passe_toujours():
    """La contrepartie, et c'est elle qui doit rester ennuyeuse.

    Revalider ne doit refuser QUE ce qui est invalide. Un couple de seuils
    correct, une valeur en bord de plage, et la surcharge de voix qui tourne
    partout ailleurs dans ce fichier doivent continuer de passer.
    """
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())

    effective = resolve_effective_config(
        client,
        {
            "stt": {
                "provider": "deepgram",
                "eager_eot_threshold": 0.6,
                "eot_threshold": 0.9,
                "eot_timeout_ms": 60000,
            }
        },
    )

    assert effective.stt.eager_eot_threshold == 0.6
    assert effective.stt.eot_threshold == 0.9
    assert effective.stt.eot_timeout_ms == 60000


def test_une_surcharge_deja_en_base_ne_casse_NI_un_appel_NI_un_enregistrement():
    """🔴 Le revers de la validation, trouvé par la seconde relecture.

    Valider la fusion refuse une surcharge invalide À L'ÉCRITURE, ce qui est le
    but. Mais les mêmes lignes sont relues ailleurs :

    * au **démarrage d'un appel** -- une surcharge écrite avant cette règle
      empêcherait l'appel de démarrer, et l'appelant n'aurait rien du tout ;
    * à **l'enregistrement de la configuration du client** -- la migration
      tourne APRÈS l'écriture et hors de tout garde, donc chaque sauvegarde
      rendrait 500 **après avoir écrit**, indéfiniment.

    ⛔ Les deux chemins journalisent et se replient, comme le fait déjà l'amont
    pour une configuration d'organisation illisible. Refuser une donnée qu'on
    LIT ne la répare pas, ça propage la panne.
    """
    from api.services.configuration.ai_model_configuration import (
        migrate_workflow_configuration_model_override_to_v2,
    )

    import api.services.configuration.ai_model_configuration as amc

    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())
    invalide = {"llm": {"provider": "mistral", "temperature": 99.0}}

    # ① La migration laisse la surcharge en l'état plutôt que de lever.
    migre, change = migrate_workflow_configuration_model_override_to_v2(
        {"model_overrides": invalide}, client
    )

    assert change is False
    assert migre["model_overrides"] == invalide

    # ② Et l'appel démarre quand même, avec la configuration du client.
    # ⛔ Cette moitié-là manquait : le nom du test l'annonçait, le corps ne
    # l'exerçait pas (troisième relecture du 11/09). Un test qui ne couvre que
    # la moitié de ce qu'il nomme est un test dont on surestime la portée.
    class _Resolu:
        effective = client

    async def _faux_resolu(organization_id):
        return _Resolu()

    vrai = amc.get_resolved_ai_model_configuration
    amc.get_resolved_ai_model_configuration = _faux_resolu
    try:
        effective = asyncio.run(
            amc.get_effective_ai_model_configuration_for_workflow(
                organization_id=1,
                workflow_configurations={"model_overrides": invalide},
            )
        )
    finally:
        amc.get_resolved_ai_model_configuration = vrai

    # La surcharge est ignorée, le client s'applique : l'appel peut démarrer.
    assert effective.llm.temperature == 0.2


def test_la_conformite_survit_a_une_surcharge_qui_tente_de_la_defaire():
    """🔴 An override is a request body: it can carry anything.

    The two compliance values are shown read-only on screen, but the screen is
    not the lock. An override that asks for America must change nothing.
    """
    from api.services.pipecat.audio_config import AudioConfig
    from api.services.pipecat.service_factory import create_stt_service

    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())

    effective = resolve_effective_config(
        client,
        {
            "stt": {
                "provider": "deepgram",
                "region": "api.deepgram.com",
                "mip_opt_out": False,
            }
        },
    )

    service = create_stt_service(
        effective,
        AudioConfig(transport_in_sample_rate=16000, transport_out_sample_rate=24000),
    )
    environment = service._client._client_wrapper.get_environment()

    assert environment.base == "https://api.eu.deepgram.com"
    assert service._build_connect_kwargs()["mip_opt_out"] == "true"


# --------------------------------------------------------------------------- #
# 2. The migration, which used to eat the override on the next save
# --------------------------------------------------------------------------- #


def test_une_surcharge_deliberee_survit_a_lenregistrement_du_client():
    """⛔ Without the marker this is destructive, and destructive in silence.

    Saving the organization configuration converts the override into a frozen
    copy and deletes it. The agent then stops inheriting, and no screen says a
    word about it.
    """
    configurations = {
        "ambient_noise_configuration": {"enabled": False},
        "model_overrides": SURCHARGE_VOIX_SEULE,
        MARQUEUR: True,
    }

    migrees, change = migrate_workflow_configuration_model_override_to_v2(
        configurations,
        compile_ai_model_configuration_v2(_client_au_nouveau_format()),
    )

    assert change is False
    assert migrees["model_overrides"] == SURCHARGE_VOIX_SEULE
    assert WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY not in migrees


def test_leur_migration_dorigine_nest_pas_touchee():
    """An override with no marker is one of theirs, and keeps their behaviour.

    We are going against their interface, not against their product: an agent
    they migrated must still migrate exactly as before.
    """
    configurations = {
        "ambient_noise_configuration": {"enabled": False},
        "model_overrides": SURCHARGE_VOIX_SEULE,
    }

    migrees, change = migrate_workflow_configuration_model_override_to_v2(
        configurations,
        compile_ai_model_configuration_v2(_client_au_nouveau_format()),
    )

    assert change is True
    assert "model_overrides" not in migrees
    assert WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY in migrees


@pytest.mark.parametrize("valeur", [False, None])
def test_le_marqueur_ne_protege_que_sil_dit_oui(valeur):
    """A marker left over as false must not accidentally freeze the migration."""
    configurations = {"model_overrides": SURCHARGE_VOIX_SEULE, MARQUEUR: valeur}

    _, change = migrate_workflow_configuration_model_override_to_v2(
        configurations, compile_ai_model_configuration_v2(_client_au_nouveau_format())
    )

    assert change is True


def test_lecran_et_le_serveur_parlent_du_meme_marqueur():
    """Two files, two languages, one string. Nothing else ties them together.

    A rename on either side would silently switch the protection off: the
    screen would keep writing a key nobody reads, and the next save of the
    client's configuration would eat the override again.
    """
    assert DELIBERATE_PER_SERVICE_OVERRIDE_KEY == MARQUEUR

    composant = (
        Path(__file__).resolve().parents[3]
        / "ui"
        / "src"
        / "components"
        / "mark"
        / "PerServiceModelOverride.tsx"
    )
    assert composant.exists(), f"the agent screen block is gone: {composant}"
    assert f'"{MARQUEUR}"' in composant.read_text(encoding="utf-8"), (
        "the agent screen no longer writes the marker: an override saved there "
        "would be converted into a frozen copy on the next save of the client's "
        "configuration."
    )
