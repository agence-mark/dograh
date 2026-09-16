"""[.mark] Non-regression test for Deepgram EU residency and training opt-out.

The question this file answers, and it answers only this one:

    Does the caller's raw audio still reach Deepgram on the European endpoint,
    with participation in the Model Improvement Program refused?

⛔ Read that scope literally. This file does NOT prove that no byte at all
leaves the EU. ``check_validity._check_deepgram_api_key`` deliberately stays
on the global endpoint, because Deepgram does not serve its management API in
the EU and pointing it there would break key validation for every valid key.
That call carries no caller audio: it lists the account's projects. So the
sentence this file protects is "the voice does not leave the EU", never "no
byte leaves the EU".

Why it exists
-------------
Dograh passed neither the endpoint nor the opt-out, so every call went to
``api.deepgram.com`` with the Model Improvement Program left on, and the
sentence in the sales material was false.

🔑 2026-09-16, decision d'Evan, et elle change ce que ce fichier prouve.
L'adresse est desormais MODIFIABLE, avec l'Europe pour valeur par defaut :
Dograh est notre outil interne, et refuser une montee de version pour garder un
champ ferme coute plus que ca ne protege. Ce fichier ne prouve donc plus que
l'Europe est imposee. Il prouve trois choses differentes, et la difference
compte :

1. **sans rien configurer, l'audio part en Europe** — sur les trois chemins,
2. **une adresse vide part en Europe aussi** — le repli, seul endroit ou une
   configuration ancienne pourrait basculer aux Etats-Unis en silence,
3. **une adresse saisie est HONOREE** — sinon "modifiable" serait un mensonge,
   et le champ afficherait une adresse ou l'audio ne va pas.

⛔ L'opposition a l'entrainement, elle, reste IMPOSEE par la fabrique : elle
n'a pas ete ouverte, et elle ne depend pas de la region.

There are THREE Deepgram code paths, not two, and they take three different
shapes of address:

* ``DeepgramSTTService``     -> ``base_url``, a host it derives both schemes from
* ``DeepgramFluxSTTService`` -> ``url``, the complete WebSocket URL with path
* ``DeepgramTTSService``     -> ``base_url``, a base with no path ("/v1/speak" added)

Passing one shape where another belongs yields a connector that still talks to
the American endpoint, silently and without raising. That is why each path is
covered twice: once for what the factory PASSES, once for what actually goes
out on the wire. A value can be accepted, stored, and then dropped in favour
of a default -- ``DeepgramSTTService`` swallows a bad base_url and falls back
to the default endpoint with only a log line.
"""

from types import SimpleNamespace
from unittest.mock import patch

from api.services.configuration.registry import ServiceProviders
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.deepgram_endpoints import (
    DEEPGRAM_EU_FLUX_URL,
    DEEPGRAM_EU_STT_BASE_URL,
    DEEPGRAM_EU_TTS_BASE_URL,
)
from api.services.pipecat.service_factory import create_stt_service, create_tts_service
from tests.mark.boucle_isolee import executer_sans_toucher_la_boucle_courante

# ⛔ This literal is the point. The "passed" tests below compare against the
# imported constants, which makes them tautological if a constant is mutated;
# the "honoured" tests below compare against THIS literal, which is what keeps
# the two layers independent. Replacing EU_HOST by the imported constant in the
# honoured tests would make the whole file tautological, and it would do so
# silently: every test would stay green while the audio moved to America.
EU_HOST = "api.eu.deepgram.com"


def _audio_config():
    return AudioConfig(
        transport_in_sample_rate=16000,
        transport_out_sample_rate=24000,
    )


def _stt_config(model: str):
    return SimpleNamespace(
        stt=SimpleNamespace(
            provider=ServiceProviders.DEEPGRAM.value,
            api_key="test-key",
            model=model,
            language="fr",
        )
    )


def _tts_config():
    return SimpleNamespace(
        tts=SimpleNamespace(
            provider=ServiceProviders.DEEPGRAM.value,
            api_key="test-key",
            model="aura-2-thalia-en",
            voice="aura-2-thalia-en",
        )
    )


def _capture_websocket_url(service, connect_coroutine):
    """Run a connector's websocket handshake and return the URL it dialled.

    Nothing reaches the network: the dialler is replaced by one that records
    its argument and aborts. This is the only way to prove the address the
    connector actually composes, as opposed to the one it was handed.
    """
    captured = {}

    async def fake_dial(url, *args, **kwargs):
        captured["url"] = url
        raise RuntimeError("handshake stopped on purpose")

    async def noop(*args, **kwargs):
        return None

    service._websocket_connect = fake_dial
    service.push_error_frame = noop
    service._call_event_handler = noop

    # ⛔ Pas `asyncio.run()` : il laisse le thread principal sans boucle et fait
    # tomber un test d'amont lance apres. Voir `boucle_isolee.py`.
    executer_sans_toucher_la_boucle_courante(connect_coroutine(service))
    return captured["url"]


# --------------------------------------------------------------------------
# Passed: the factory hands the values to each connector
# --------------------------------------------------------------------------


def test_classic_stt_is_pointed_at_the_eu_endpoint_and_opted_out():
    with patch("api.services.pipecat.service_factory.DeepgramSTTService") as mock:
        create_stt_service(_stt_config("nova-3-general"), _audio_config())

    kwargs = mock.call_args.kwargs
    assert kwargs["base_url"] == DEEPGRAM_EU_STT_BASE_URL
    assert kwargs["mip_opt_out"] is True


def test_flux_stt_is_pointed_at_the_eu_endpoint_and_opted_out():
    with patch("api.services.pipecat.service_factory.DeepgramFluxSTTService") as mock:
        create_stt_service(_stt_config("flux-general-en"), _audio_config())

    kwargs = mock.call_args.kwargs
    assert kwargs["url"] == DEEPGRAM_EU_FLUX_URL
    assert kwargs["mip_opt_out"] is True


def test_tts_is_pointed_at_the_eu_endpoint_and_opted_out():
    with patch("api.services.pipecat.service_factory.DeepgramTTSService") as mock:
        create_tts_service(_tts_config(), _audio_config())

    kwargs = mock.call_args.kwargs
    assert kwargs["base_url"] == DEEPGRAM_EU_TTS_BASE_URL
    assert kwargs["mip_opt_out"] is True


# --------------------------------------------------------------------------
# Honoured: the values reach what actually goes out on the wire
# --------------------------------------------------------------------------


def test_classic_stt_client_really_targets_the_eu_host():
    service = create_stt_service(_stt_config("nova-3-general"), _audio_config())

    # get_environment() is what the SDK calls on itself to resolve a route.
    environment = service._client._client_wrapper.get_environment()
    assert environment.base == f"https://{EU_HOST}"
    assert environment.production == f"wss://{EU_HOST}"


def test_classic_stt_sends_the_opt_out_in_its_request():
    service = create_stt_service(_stt_config("nova-3-general"), _audio_config())

    assert service._build_connect_kwargs()["mip_opt_out"] == "true"


def test_flux_stt_dials_the_eu_url_with_the_opt_out():
    service = create_stt_service(_stt_config("flux-general-en"), _audio_config())

    # Flux assembles its URL in _connect(), not in _connect_websocket(), so
    # the real assembly line only runs if we enter through _connect().
    url = _capture_websocket_url(service, lambda s: s._connect())
    assert url.startswith(f"wss://{EU_HOST}/v2/listen?")
    assert "mip_opt_out=true" in url


def test_tts_dials_the_eu_url_with_the_opt_out():
    service = create_tts_service(_tts_config(), _audio_config())

    url = _capture_websocket_url(service, lambda s: s._connect_websocket())
    assert url.startswith(f"wss://{EU_HOST}/v1/speak?")
    assert "mip_opt_out=true" in url


# --------------------------------------------------------------------------
# Le repli : une adresse VIDE part en Europe, pas au defaut mondial de l'amont
# --------------------------------------------------------------------------
#
# 🔴 C'est le seul chemin par lequel l'audio pourrait basculer aux
# Etats-Unis sans que personne ne l'ait demande : une section de configuration
# enregistree AVANT l'ouverture du champ, ou construite sans passer par le
# registre, arrive avec une adresse vide. L'amont replie alors sur
# ``api.deepgram.com``. Nous replions sur l'Europe.
#
# ⛔ Les trois chemins sont couverts separement : ils lisent la meme valeur
# mais la remettent en forme chacun a leur maniere, et c'est la remise en forme
# qui a deja fait partir de l'audio au mauvais endroit.


def _config_stt_sans_adresse(model: str):
    """Une section de transcription ou l'adresse est vide, comme avant le 16/09."""
    return SimpleNamespace(
        stt=SimpleNamespace(
            provider=ServiceProviders.DEEPGRAM.value,
            api_key="test-key",
            model=model,
            language="fr",
            base_url="",
        )
    )


def test_an_empty_endpoint_still_goes_to_europe_on_the_classic_path():
    service = create_stt_service(
        _config_stt_sans_adresse("nova-3-general"), _audio_config()
    )

    environment = service._client._client_wrapper.get_environment()
    assert environment.base == f"https://{EU_HOST}"
    assert environment.production == f"wss://{EU_HOST}"


def test_an_empty_endpoint_still_goes_to_europe_on_flux():
    service = create_stt_service(
        _config_stt_sans_adresse("flux-general-en"), _audio_config()
    )

    url = _capture_websocket_url(service, lambda s: s._connect())
    assert url.startswith(f"wss://{EU_HOST}/v2/listen?")


def test_an_empty_endpoint_still_goes_to_europe_on_the_voice():
    config = SimpleNamespace(
        tts=SimpleNamespace(
            provider=ServiceProviders.DEEPGRAM.value,
            api_key="test-key",
            model="aura-2-thalia-en",
            voice="aura-2-thalia-en",
            base_url="",
        )
    )
    service = create_tts_service(config, _audio_config())

    url = _capture_websocket_url(service, lambda s: s._connect_websocket())
    assert url.startswith(f"wss://{EU_HOST}/v1/speak?")


# --------------------------------------------------------------------------
# Honore : une adresse saisie est SUIVIE, sinon "modifiable" est un mensonge
# --------------------------------------------------------------------------
#
# 🔑 2026-09-16 : ces tests assertent l'INVERSE de ce que ce fichier
# assertait la veille, et c'est voulu. Ils sont ecrits avec l'adresse mondiale
# precisement parce que c'est celle dont on ne veut pas par defaut : si la
# fabrique la remplacait en douce par l'Europe, le champ afficherait une
# adresse ou l'audio ne va pas — la panne exacte que le miroir doit empecher,
# dans l'autre sens.
#
# ⛔ L'opposition a l'entrainement, elle, reste asserte a "true" DANS LE MEME
# test : elle n'a pas ete ouverte, et rien ne doit l'ouvrir par ricochet.

AUTRE_HOTE = "api.deepgram.com"


def _config_stt_avec_adresse(model: str, adresse: str):
    from api.services.configuration.registry import DeepgramSTTConfiguration

    return SimpleNamespace(
        stt=DeepgramSTTConfiguration(
            api_key="test-key",
            model=model,
            language="fr",
            base_url=adresse,
            mip_opt_out=False,
        )
    )


def test_the_classic_path_honours_a_configured_endpoint():
    service = create_stt_service(
        _config_stt_avec_adresse("nova-3-general", f"https://{AUTRE_HOTE}"),
        _audio_config(),
    )

    environment = service._client._client_wrapper.get_environment()
    assert environment.base == f"https://{AUTRE_HOTE}"
    assert environment.production == f"wss://{AUTRE_HOTE}"
    # ⛔ Ouvrir la region n'ouvre pas l'entrainement.
    assert service._build_connect_kwargs()["mip_opt_out"] == "true"


def test_flux_honours_a_configured_endpoint():
    service = create_stt_service(
        _config_stt_avec_adresse("flux-general-en", f"https://{AUTRE_HOTE}"),
        _audio_config(),
    )

    url = _capture_websocket_url(service, lambda s: s._connect())
    assert url.startswith(f"wss://{AUTRE_HOTE}/v2/listen?")
    assert "mip_opt_out=true" in url


def test_the_voice_honours_a_configured_endpoint():
    from api.services.configuration.registry import DeepgramTTSConfiguration

    config = SimpleNamespace(
        tts=DeepgramTTSConfiguration(
            api_key="test-key",
            voice="aura-2-thalia-en",
            base_url=f"wss://{AUTRE_HOTE}",
        )
    )
    service = create_tts_service(config, _audio_config())

    url = _capture_websocket_url(service, lambda s: s._connect_websocket())
    assert url.startswith(f"wss://{AUTRE_HOTE}/v1/speak?")
    assert "mip_opt_out=true" in url


# --------------------------------------------------------------------------
# La mise en forme de l'adresse saisie : trois pieges, trois gardes
# --------------------------------------------------------------------------
#
# 🔴 Ces trois tests gardent une DIVERGENCE avec l'amont, pas un comportement
# d'amont. Sans eux, la prochaine resolution de conflit restaure la ligne
# d'origine, les pieges reviennent, et rien ne rougit. C'est le motif que ce
# chantier a deja paye deux fois.


def test_a_connector_path_in_the_endpoint_is_not_doubled():
    """⛔ L'adresse que quelqu'un copie depuis la documentation Flux.

    `deepgram_endpoints.py` documente lui-meme cette forme
    (`wss://hote/v2/listen`), donc c'est celle qu'on a sous les yeux au moment
    de remplir le champ. Le connecteur ajoutant SON chemin, la garder
    produirait `wss://hote/v2/listen/v2/listen` : l'agent ne transcrit plus.
    """
    service = create_stt_service(
        _config_stt_avec_adresse("flux-general-en", f"https://{EU_HOST}/v2/listen"),
        _audio_config(),
    )

    url = _capture_websocket_url(service, lambda s: s._connect())
    assert url.startswith(f"wss://{EU_HOST}/v2/listen?")
    assert "/v2/listen/v2/listen" not in url


def test_a_path_that_no_connector_adds_is_preserved():
    """⚠️ Et l'inverse, qui est la raison de ne pas jeter TOUT chemin.

    Pipecat documente `base_url` comme acceptant un chemin, pour une instance
    auto-hebergee derriere un proxy a prefixe. Jeter le prefixe lui retirerait
    sa route, en silence. ⛔ Seuls les trois chemins qu'un connecteur rajoute
    de toute facon sont coupes.
    """
    from api.services.pipecat.service_factory import _deepgram_base_url

    section = SimpleNamespace(base_url="https://passerelle.interne/deepgram")

    assert _deepgram_base_url(section) == "https://passerelle.interne/deepgram"


def test_an_endpoint_without_a_host_goes_to_europe_rather_than_america():
    """🔴 Le trou mesure par la contre-relecture du 16/09.

    Une faute de frappe (`"https://"`) n'est pas une adresse vide, donc elle ne
    passait pas par le repli. ⛔ Et pipecat AVALE une base_url invalide : il se
    replie sur son endpoint par defaut AMERICAIN avec une simple ligne de
    journal. L'audio de l'appelant serait donc parti aux Etats-Unis sur une
    faute de frappe, sans rien lever.

    ⛔ Les deux bouts sont assertes ici : ce qui part sur le fil, ET ce que
    l'ecran annonce. Le jour ou ils divergent, l'un des deux ment.
    """
    from api.services.configuration.registry import DeepgramSTTConfiguration

    service = create_stt_service(
        _config_stt_sans_adresse("nova-3-general"), _audio_config()
    )
    service_casse = create_stt_service(
        SimpleNamespace(
            stt=SimpleNamespace(
                provider=ServiceProviders.DEEPGRAM.value,
                api_key="test-key",
                model="nova-3-general",
                language="fr",
                base_url="https://",
            )
        ),
        _audio_config(),
    )

    attendu = service._client._client_wrapper.get_environment().base
    assert attendu == f"https://{EU_HOST}"
    assert service_casse._client._client_wrapper.get_environment().base == attendu

    # Et l'ecran dit la meme chose que le fil.
    config = DeepgramSTTConfiguration(api_key="test-key", base_url="https://")
    assert config.region == EU_HOST


# --------------------------------------------------------------------------
# Le miroir : ce que l'ecran affiche SUIT ce qui est configure
# --------------------------------------------------------------------------


def test_the_shown_region_follows_the_configured_endpoint():
    """🔴 Le motif releve par la relecture du 11/09, dans l'autre sens.

    Tant que l'Europe etait imposee, le danger etait qu'une adresse americaine
    STOCKEE s'affiche comme la destination. Maintenant que l'adresse est
    honoree, le danger s'inverse : c'est l'ecran qui continuerait d'annoncer
    l'Europe pendant que l'audio partirait ailleurs. Dans les deux cas la panne
    est la meme — un ecran qui decrit autre chose que le fil.
    """
    from api.services.configuration.registry import DeepgramSTTConfiguration

    config = DeepgramSTTConfiguration(
        api_key="test-key",
        region=EU_HOST,
        mip_opt_out=False,
        base_url=f"https://{AUTRE_HOTE}",
    )

    assert config.region == AUTRE_HOTE
    assert config.base_url == f"https://{AUTRE_HOTE}"
    # ⛔ Et l'entrainement reste refuse, quoi qu'on demande.
    assert config.mip_opt_out is True


def test_the_endpoint_field_stays_typable_and_the_opt_out_stays_locked():
    """🔴 La garde qui manquait, relevee par la relecture du 16/09.

    Rien n'assertait la decision meme de ce chantier. Le test d'ecran qui
    pretend le faire lit une COPIE MANUSCRITE du schema, declaree dans le
    fichier de test : la prochaine resolution de conflit peut remettre
    ``readonly`` sur l'adresse, le champ redevient grise en production, et les
    531 tests serveur comme les 346 d'ecran restent verts.

    ⛔ Ce test lit le VRAI schema, celui que l'ecran recoit. Il tient les deux
    bouts dans le meme geste : l'adresse se saisit, l'opposition a
    l'entrainement ne se saisit pas.
    """
    from api.services.configuration.options import DEEPGRAM_BASE_URLS
    from api.services.configuration.registry import (
        DeepgramSTTConfiguration,
        DeepgramTTSConfiguration,
    )

    for classe in (DeepgramSTTConfiguration, DeepgramTTSConfiguration):
        champ = classe.model_json_schema()["properties"]["base_url"]
        assert champ.get("readonly") is not True, (
            f"{classe.__name__}.base_url est redevenu non modifiable"
        )
        assert champ["default"] == DEEPGRAM_EU_STT_BASE_URL
        assert champ["examples"] == list(DEEPGRAM_BASE_URLS)
        assert champ["allow_custom_input"] is True

    proprietes = DeepgramSTTConfiguration.model_json_schema()["properties"]
    # ⛔ Et l'inverse dans le meme test : ouvrir la region n'ouvre pas
    # l'entrainement, et la region reste DEDUITE.
    assert proprietes["mip_opt_out"]["readonly"] is True
    assert proprietes["region"]["readonly"] is True


def test_a_configuration_left_alone_shows_europe():
    """Sans y toucher, les deux classes et les trois constantes disent l'Europe.

    ⛔ Les trois formes ne sont pas interchangeables — la transcription prend
    un schema + hote, Flux une URL complete, la synthese une base sans chemin —
    donc chacune est comparee a SA constante.
    """
    from api.services.configuration.registry import (
        DeepgramSTTConfiguration,
        DeepgramTTSConfiguration,
    )

    config = DeepgramSTTConfiguration(api_key="test-key")

    assert config.region == EU_HOST
    # ⛔ Les deux classes stockent la MEME forme (https) depuis le 16/09 : la
    # mise en forme par connecteur est faite par la fabrique, et les tests du
    # fil plus haut prouvent que chacune des trois sort juste.
    assert config.base_url == DEEPGRAM_EU_STT_BASE_URL
    assert (
        DeepgramTTSConfiguration(api_key="test-key").base_url
        == DEEPGRAM_EU_STT_BASE_URL
    )
    assert EU_HOST in DEEPGRAM_EU_STT_BASE_URL
    assert EU_HOST in DEEPGRAM_EU_FLUX_URL
    assert EU_HOST in DEEPGRAM_EU_TTS_BASE_URL
    assert config.mip_opt_out is True
