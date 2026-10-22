"""[.mark] Chantier voix-soniox, lot 0 bis (D17) : la case « saisie libre » des adresses.

Sur CHAQUE champ d'adresse d'un fournisseur (cerveau, transcription, voix,
plongements ; `base_url`, `endpoint`...), une case « saisie libre » :

- décochée (défaut) : le comportement d'aujourd'hui, contrôle propre au fournisseur ;
- cochée : tout schéma accepté (`https://`, `wss://`, `ws://`, `grpc://`...), seul
  reste le refus d'une adresse SANS HÔTE.

Le mécanisme est déclaré UNE fois (``BaseServiceConfiguration.adresse_libre``,
lu par ``__get_pydantic_json_schema__`` et par ``ServiceConfigurationForm.tsx``),
jamais recodé par fournisseur : un fournisseur ajouté plus tard en hérite sans
une ligne de code. Ce fichier balaie le registre pour que ce soit vrai.

⛔ Zéro perte : une configuration enregistrée sans la case se relit à
l'identique, se réécrit à l'identique (la clé n'est écrite que cochée), et les
requêtes des agents existants ne changent pas d'un octet.

| Test | Preuve |
|---|---|
| balayage : chaque champ d'adresse du registre porte la case | D17 |
| balayage indépendant : tout défaut qui ressemble à une adresse est reconnu | R7 |
| un fournisseur sans adresse n'a pas la case | D17 |
| décochée : refus d'aujourd'hui (Soniox : `https://`, `ftp://`, sans hôte) | D17 |
| cochée : `https://` sur Soniox, `grpc://` partout, refus du sans hôte | D17 |
| contrôle d'enregistrement (`check_validity`) et de la fabrique, hors `oss` | D17 |
| région affichée et vérification de la clé lisent l'adresse saisie | D17 |
| configurations enregistrées inchangées, aller-retour fusion, masque, surcharge | zéro perte |
"""

import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError

from api.services.configuration.registry import REGISTRY, ServiceType

# Ce qui ressemble à un nom d'adresse, indépendamment de la liste du registre.
NOM_D_ADRESSE = re.compile(r"(.*_)?(url|uri|endpoint|api_base)")
UNE_ADRESSE = re.compile(r"^(https?|wss?)://")


def _tous_les_fournisseurs():
    return [
        (type_, nom, classe)
        for type_, classes in REGISTRY.items()
        for nom, classe in classes.items()
    ]


def _champs_d_adresse(classe):
    return [nom for nom in classe.model_fields if NOM_D_ADRESSE.fullmatch(nom)]


IDENTIFIANTS = [f"{type_.name.lower()}-{getattr(nom, 'value', nom)}" for type_, nom, _ in _tous_les_fournisseurs()]


# --------------------------------------------------------------------------- #
# 1. Balayage du registre : la case est déclarée une fois et tout le monde en hérite
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("type_, nom, classe", _tous_les_fournisseurs(), ids=IDENTIFIANTS)
def test_chaque_champ_d_adresse_porte_la_case_saisie_libre(type_, nom, classe):
    schema = classe.model_json_schema()
    proprietes = schema["properties"]
    adresses = _champs_d_adresse(classe)
    if not adresses:
        assert "adresse_libre" not in proprietes, (
            f"{nom} n'a aucun champ d'adresse : la case n'a rien à côté de quoi s'afficher"
        )
        return
    assert "adresse_libre" in proprietes, f"{nom}: {adresses} sans case « saisie libre »"
    case = proprietes["adresse_libre"]
    assert case.get("default") is False, "décochée par défaut : le comportement d'aujourd'hui"
    assert case.get("mark_adresse_libre") is True
    libelle = case.get("mark_libelle") or {}
    assert libelle.get("en") and libelle.get("fr"), "la case n'a pas ses deux langues"
    for champ in adresses:
        assert proprietes[champ].get("mark_adresse") is True, (
            f"{nom}.{champ} : le champ n'annonce pas qu'il est une adresse, "
            "l'écran ne dessine pas la case à côté"
        )


def test_le_balayage_n_est_pas_vide():
    """Un balayage qui ne trouve rien ne prouve rien : le registre porte des dizaines d'adresses."""
    trouves = [(nom, champ) for _, nom, classe in _tous_les_fournisseurs() for champ in _champs_d_adresse(classe)]
    assert len(trouves) >= 20, trouves
    fournisseurs = {nom for nom, _ in trouves}
    for attendu in ("soniox", "deepgram", "mistral", "openai", "elevenlabs", "azure"):
        assert attendu in fournisseurs, attendu


def test_balayage_independant_tout_defaut_qui_ressemble_a_une_adresse_est_reconnu():
    """Deuxième outil, par un autre chemin (R7) : on ne cherche pas par le NOM du champ
    mais par la VALEUR de son défaut. Un champ dont le défaut est une adresse et que le
    mécanisme ne connaît pas échappe à la case en silence."""
    from api.services.configuration.registry import est_champ_adresse

    for _, nom, classe in _tous_les_fournisseurs():
        for champ, info in classe.model_fields.items():
            if isinstance(info.default, str) and UNE_ADRESSE.match(info.default):
                assert est_champ_adresse(champ), f"{nom}.{champ} = {info.default!r} n'est pas reconnu"


def test_la_route_des_defauts_sert_la_case_a_tous_les_fournisseurs_a_adresse():
    from api.routes.user import get_default_configurations
    from api.tests.mark.boucle_isolee import executer_sans_toucher_la_boucle_courante

    reponse = executer_sans_toucher_la_boucle_courante(get_default_configurations())
    vus = 0
    for service in ("llm", "tts", "stt", "embeddings", "realtime"):
        for nom, schema in getattr(reponse, service).items():
            proprietes = schema["properties"]
            if any(NOM_D_ADRESSE.fullmatch(champ) for champ in proprietes if champ != "adresse_libre"):
                assert "adresse_libre" in proprietes, f"{service}/{nom}"
                vus += 1
    assert vus >= 20


# --------------------------------------------------------------------------- #
# 2. Décochée = aujourd'hui. Cochée = tout schéma, sauf sans hôte
# --------------------------------------------------------------------------- #

ADRESSE_EUROPE = "wss://stt-rt.eu.soniox.com/transcribe-websocket"


def _soniox(**reglages):
    from api.services.configuration.registry import SonioxSTTConfiguration

    return SonioxSTTConfiguration(api_key="soniox-key", **reglages)


@pytest.mark.parametrize(
    "adresse",
    ["https://stt-rt.soniox.com", "ftp://stt-rt.soniox.com", "wss://", "stt-rt.soniox.com"],
)
def test_decochee_le_refus_d_aujourd_hui_est_inchange(adresse):
    with pytest.raises(ValidationError):
        _soniox(base_url=adresse)
    with pytest.raises(ValidationError):
        _soniox(base_url=adresse, adresse_libre=False)


@pytest.mark.parametrize(
    "adresse",
    [
        "https://proxy.example.net/soniox",
        "http://localhost:9000/transcribe",
        "ws://10.0.0.5:8080/stt",
        "grpc://stt.example.net:443",
        "stt-rt.soniox.com",
    ],
)
def test_cochee_tout_schema_est_accepte_sur_un_champ_qui_attendait_wss(adresse):
    config = _soniox(base_url=adresse, adresse_libre=True)
    assert config.base_url == adresse
    assert config.adresse_libre is True


@pytest.mark.parametrize("adresse", ["wss://", "https://", "grpc://", "ws:///chemin", "wss://:8080/x"])
def test_cochee_une_adresse_sans_hote_reste_refusee(adresse):
    with pytest.raises(ValidationError):
        _soniox(base_url=adresse, adresse_libre=True)


def test_cochee_une_adresse_vide_garde_son_sens_europe():
    """Vide veut dire Europe (D5 de la transcription) : ce n'est pas une adresse sans hôte."""
    config = _soniox(base_url="", adresse_libre=True)
    assert config.region == "eu"


@pytest.mark.parametrize("schema", ["wss", "ws", "https", "http", "grpc"])
def test_cochee_la_regle_vaut_aussi_pour_un_fournisseur_sans_controle_propre(schema):
    """Mistral n'a aucun contrôle propre : cochée, le schéma n'y change rien, l'hôte reste exigé."""
    from api.services.configuration.registry import MistralLLMConfiguration

    base = f"{schema}://api.eu.mistral.ai/v1"
    assert MistralLLMConfiguration(api_key="k", base_url=base, adresse_libre=True).base_url == base
    with pytest.raises(ValidationError):
        MistralLLMConfiguration(api_key="k", base_url=f"{schema}://", adresse_libre=True)


def test_le_discriminateur_accepte_la_case_envoyee_par_l_ecran():
    from api.services.configuration.registry import STTConfig

    config = TypeAdapter(STTConfig).validate_python(
        {
            "provider": "soniox",
            "api_key": "k",
            "model": "stt-rt-v5",
            "base_url": "https://proxy.example.net/soniox",
            "adresse_libre": True,
        }
    )
    assert config.adresse_libre is True


# --------------------------------------------------------------------------- #
# 3. Les deux autres contrôles : enregistrement (check_validity) et fabrique
# --------------------------------------------------------------------------- #


@pytest.fixture
def hors_oss(monkeypatch):
    """Les contrôles de schéma et d'IP ne tournent qu'hors `oss` (ils sont inertes chez nous)."""
    from api.utils import url_security

    monkeypatch.setattr(url_security, "DEPLOYMENT_MODE", "saas")


ADRESSE_PUBLIQUE = "93.184.216.34"  # une IP littérale publique : aucune résolution DNS


def test_l_utilitaire_decochee_refuse_un_schema_inconnu_hors_oss(hors_oss):
    from api.utils.url_security import validate_user_configured_service_url

    with pytest.raises(ValueError):
        validate_user_configured_service_url(f"grpc://{ADRESSE_PUBLIQUE}", field_name="base_url")
    validate_user_configured_service_url(f"wss://{ADRESSE_PUBLIQUE}", field_name="base_url")


def test_l_utilitaire_cochee_accepte_tout_schema_mais_garde_l_hote_et_l_ip(hors_oss):
    from api.utils.url_security import validate_user_configured_service_url

    validate_user_configured_service_url(
        f"grpc://{ADRESSE_PUBLIQUE}", field_name="base_url", schema_libre=True
    )
    with pytest.raises(ValueError):
        validate_user_configured_service_url("grpc://", field_name="base_url", schema_libre=True)
    # ⛔ Le garde-fou SaaS contre un hôte interne n'est PAS un contrôle de schéma : il reste.
    with pytest.raises(ValueError):
        validate_user_configured_service_url(
            "grpc://127.0.0.1:9000", field_name="base_url", schema_libre=True
        )


def test_l_utilitaire_refuse_le_sans_hote_meme_en_oss(monkeypatch):
    from api.utils import url_security

    monkeypatch.setattr(url_security, "DEPLOYMENT_MODE", "oss")
    # Décochée en oss : rien n'est contrôlé, comme aujourd'hui.
    url_security.validate_user_configured_service_url("grpc://", field_name="base_url")
    with pytest.raises(ValueError):
        url_security.validate_user_configured_service_url(
            "grpc://", field_name="base_url", schema_libre=True
        )


def _validateur_qui_accepte_la_cle():
    from api.services.configuration.check_validity import UserConfigurationValidator

    validateur = UserConfigurationValidator()
    for fournisseur in list(validateur._validator_map):
        validateur._validator_map[fournisseur] = lambda *a, **k: True
    return validateur


def test_l_enregistrement_decochee_refuse_un_schema_inconnu_cochee_l_accepte(hors_oss):
    from api.services.configuration.registry import MistralLLMConfiguration

    validateur = _validateur_qui_accepte_la_cle()
    base = f"grpc://{ADRESSE_PUBLIQUE}/v1"
    refus = validateur._validate_service(MistralLLMConfiguration(api_key="k", base_url=base), "llm")
    assert refus and "base_url" in refus[0]["message"]
    accepte = validateur._validate_service(
        MistralLLMConfiguration(api_key="k", base_url=base, adresse_libre=True), "llm"
    )
    assert accepte == []


def test_la_fabrique_decochee_refuse_un_schema_inconnu_cochee_le_construit(hors_oss):
    from api.services.configuration.registry import OpenAISTTConfiguration
    from api.services.pipecat.audio_config import AudioConfig
    from api.services.pipecat.service_factory import create_stt_service

    audio = AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=24000)
    base = f"grpc://{ADRESSE_PUBLIQUE}/v1"
    with pytest.raises(HTTPException):
        create_stt_service(
            SimpleNamespace(stt=OpenAISTTConfiguration(api_key="k", base_url=base)), audio
        )
    service = create_stt_service(
        SimpleNamespace(stt=OpenAISTTConfiguration(api_key="k", base_url=base, adresse_libre=True)),
        audio,
    )
    assert service is not None


def test_le_drapeau_de_la_fabrique_ne_fuit_pas_d_un_appel_a_l_autre(hors_oss):
    """Le drapeau est lu par appel : un service construit cochée ne laisse pas la porte
    ouverte au suivant, décoché."""
    from api.services.configuration.registry import OpenAISTTConfiguration
    from api.services.pipecat.audio_config import AudioConfig
    from api.services.pipecat.service_factory import create_stt_service

    audio = AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=24000)
    base = f"grpc://{ADRESSE_PUBLIQUE}/v1"
    create_stt_service(
        SimpleNamespace(stt=OpenAISTTConfiguration(api_key="k", base_url=base, adresse_libre=True)),
        audio,
    )
    with pytest.raises(HTTPException):
        create_stt_service(
            SimpleNamespace(stt=OpenAISTTConfiguration(api_key="k", base_url=base)), audio
        )


# --------------------------------------------------------------------------- #
# 4. La région affichée et la clé lisent l'adresse saisie
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "adresse, region",
    [
        ("https://stt-rt.soniox.com/proxy", "global"),
        ("https://stt-rt.eu.soniox.com/proxy", "eu"),
        ("grpc://stt.example.net:443", "stt.example.net:443"),
    ],
)
def test_la_region_de_soniox_suit_l_adresse_saisie_quel_que_soit_le_schema(adresse, region):
    assert _soniox(base_url=adresse, adresse_libre=True).region == region


@pytest.mark.parametrize(
    "adresse, hote",
    [
        ("wss://api.eu.deepgram.com", "api.eu.deepgram.com"),
        ("https://api.deepgram.com/proxy", "api.deepgram.com"),
        ("grpc://dg.example.net:8443", "dg.example.net:8443"),
    ],
)
def test_la_region_de_deepgram_suit_l_adresse_saisie(adresse, hote):
    from api.services.configuration.registry import DeepgramSTTConfiguration

    config = DeepgramSTTConfiguration(api_key="k", base_url=adresse, adresse_libre=True)
    assert config.region == hote


@pytest.mark.parametrize(
    "adresse, api_attendue",
    [
        ("https://stt-rt.soniox.com/proxy", "https://api.soniox.com/v1/models"),
        ("https://stt-rt.eu.soniox.com/proxy", "https://api.eu.soniox.com/v1/models"),
    ],
)
def test_la_cle_soniox_est_verifiee_dans_la_region_de_l_adresse_saisie(monkeypatch, adresse, api_attendue):
    from api.services.configuration import check_validity

    appels = []

    class _Reponse:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        check_validity.httpx, "get", lambda url, headers=None, timeout=None: appels.append(url) or _Reponse()
    )
    statuts = check_validity.UserConfigurationValidator()._validate_service(
        _soniox(base_url=adresse, adresse_libre=True), "stt"
    )
    assert statuts == []
    assert appels == [api_attendue]


# --------------------------------------------------------------------------- #
# 5. Zéro perte : les agents et organisations existants ne changent pas d'un octet
# --------------------------------------------------------------------------- #

CONFIGS_EXISTANTES = [
    ("soniox", {"provider": "soniox", "api_key": "k", "model": "stt-rt-v5", "language": "fr"}),
    ("deepgram", {"provider": "deepgram", "api_key": "k", "model": "nova-3-general"}),
    ("mistral", {"provider": "mistral", "api_key": "k", "model": "mistral-large-2512"}),
    ("openai", {"provider": "openai", "api_key": "k", "model": "gpt-4.1"}),
    ("elevenlabs", {"provider": "elevenlabs", "api_key": "k", "model": "eleven_flash_v2_5", "voice": "v"}),
]


def _adapter(service):
    from api.services.configuration.registry import LLMConfig, STTConfig, TTSConfig

    return TypeAdapter({"llm": LLMConfig, "stt": STTConfig, "tts": TTSConfig}[service])


@pytest.mark.parametrize(
    "service, donnees",
    [
        ("stt", CONFIGS_EXISTANTES[0][1]),
        ("stt", CONFIGS_EXISTANTES[1][1]),
        ("llm", CONFIGS_EXISTANTES[2][1]),
        ("llm", CONFIGS_EXISTANTES[3][1]),
        ("tts", CONFIGS_EXISTANTES[4][1]),
    ],
)
def test_une_configuration_enregistree_sans_la_case_se_relit_et_se_reecrit_a_l_identique(service, donnees):
    config = _adapter(service).validate_python(donnees)
    assert config.adresse_libre is False
    ecrite = config.model_dump(mode="json", exclude_none=True)
    # La clé n'est écrite que cochée : une configuration existante garde exactement ses clés.
    assert "adresse_libre" not in ecrite
    assert "adresse_libre" not in config.model_dump()
    # Et ce qui est écrit se relit pareil.
    assert _adapter(service).validate_python(ecrite).model_dump() == config.model_dump()


def test_cochee_la_case_est_ecrite_et_se_relit():
    config = _soniox(base_url="https://proxy.example.net/soniox", adresse_libre=True)
    ecrite = config.model_dump(mode="json", exclude_none=True)
    assert ecrite["adresse_libre"] is True
    assert _adapter("stt").validate_python(ecrite).adresse_libre is True


def test_l_aller_retour_de_l_enregistrement_garde_la_case():
    """La route d'enregistrement : fusion, validation, masque (clé masquée, case gardée)."""
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
    from api.services.configuration.masking import mask_user_config
    from api.services.configuration.merge import merge_user_configurations

    existant = EffectiveAIModelConfiguration.model_validate({"stt": CONFIGS_EXISTANTES[0][1]})
    fusion = merge_user_configurations(
        existant,
        {
            "stt": {
                **CONFIGS_EXISTANTES[0][1],
                "base_url": "https://proxy.example.net/soniox",
                "adresse_libre": True,
            }
        },
    )
    assert fusion.stt.adresse_libre is True
    assert mask_user_config(fusion)["stt"]["adresse_libre"] is True
    # Décochée à nouveau : la clé disparaît, la configuration revient à ce qu'elle était.
    retour = merge_user_configurations(fusion, {"stt": CONFIGS_EXISTANTES[0][1]})
    assert retour.stt.adresse_libre is False
    assert "adresse_libre" not in mask_user_config(retour)["stt"]
    assert retour.stt.model_dump() == existant.stt.model_dump()


def test_la_surcharge_par_agent_herite_de_la_case_ou_la_remplace():
    """`resolve.py` fusionne champ par champ : la case suit l'organisation, ou la surcharge."""
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
    from api.services.configuration.resolve import resolve_effective_config

    organisation = EffectiveAIModelConfiguration.model_validate(
        {
            "stt": {
                **CONFIGS_EXISTANTES[0][1],
                "base_url": "https://proxy.example.net/soniox",
                "adresse_libre": True,
            }
        }
    )
    herite = resolve_effective_config(organisation, {"stt": {"language": "en"}})
    assert herite.stt.adresse_libre is True and herite.stt.language == "en"
    decoche = resolve_effective_config(
        organisation, {"stt": {"base_url": ADRESSE_EUROPE, "adresse_libre": False}}
    )
    assert decoche.stt.adresse_libre is False
    assert decoche.stt.base_url == ADRESSE_EUROPE


@pytest.mark.asyncio
async def test_la_requete_soniox_d_un_agent_existant_est_identique_case_absente_ou_decochee():
    """Octet pour octet : le message de configuration que reçoit Soniox ne dépend pas de la case."""
    import json

    from api.services.pipecat.audio_config import AudioConfig
    from api.services.pipecat.service_factory import create_stt_service
    from api.tests.mark.test_soniox_expose import _FausseConnexion

    async def message(**reglages):
        service = create_stt_service(
            SimpleNamespace(stt=_soniox(**reglages)),
            AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=24000),
        )
        connexion = _FausseConnexion()

        async def se_connecter(adresse, *args, **kwargs):
            return connexion

        service._websocket_connect = se_connecter
        await service._connect_websocket()
        return json.loads(connexion.envois[0])

    assert await message() == await message(adresse_libre=False)


def test_le_cerveau_passe_par_la_meme_porte_decochee_refuse_cochee_construit(hors_oss):
    """`create_llm_service` : la porte du cerveau (l'appel principal), pas celle du détecteur."""
    from api.services.configuration.registry import OpenAILLMService
    from api.services.pipecat.service_factory import create_llm_service

    base = f"grpc://{ADRESSE_PUBLIQUE}/v1"
    with pytest.raises(HTTPException):
        create_llm_service(
            SimpleNamespace(llm=OpenAILLMService(api_key="k", model="gpt-4.1", base_url=base))
        )
    service = create_llm_service(
        SimpleNamespace(
            llm=OpenAILLMService(api_key="k", model="gpt-4.1", base_url=base, adresse_libre=True)
        )
    )
    assert service is not None


def test_la_voix_passe_par_la_meme_porte_decochee_refuse_cochee_construit(hors_oss):
    from api.services.configuration.registry import OpenAITTSService
    from api.services.pipecat.audio_config import AudioConfig
    from api.services.pipecat.service_factory import create_tts_service

    audio = AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=24000)
    base = f"grpc://{ADRESSE_PUBLIQUE}/v1"
    config = dict(api_key="k", model="gpt-4o-mini-tts", voice="alloy", base_url=base)
    with pytest.raises(HTTPException):
        create_tts_service(SimpleNamespace(tts=OpenAITTSService(**config)), audio)
    service = create_tts_service(
        SimpleNamespace(tts=OpenAITTSService(**config, adresse_libre=True)), audio
    )
    assert service is not None
