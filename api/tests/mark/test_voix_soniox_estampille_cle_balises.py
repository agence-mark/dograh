"""[.mark] Chantier voix-soniox, lots 4, 5 et 5 bis : l'estampille, la clé, les balises d'expression.

| Test | Preuve |
|---|---|
| la fiche d'appel dit « Soniox », l'adresse appelée et les réglages, lus par la MÊME fonction que la requête | lot 4 |
| l'estampille égale ce que la vraie fabrique envoie (voix vidée, adresse mondiale, vitesse) | lot 4 (R1) |
| le mode d'envoi du texte retenu (celui de la voix quand l'agent n'a rien demandé) est sur la fiche | lot 4 (D-10) |
| l'estampille des autres voix ne bouge pas | zéro perte |
| la clé de la VOIX est vérifiée selon la région de l'adresse de la voix ; la transcription ne bouge pas | lot 5 |
| le filtre du nom et de la civilité lit le mode RÉSOLU ; plus aucun lecteur du seul réglage d'agent | D-10 (même famille) |
| balises : permise passe, inconnue retirée, liste vide = tout retiré, casse et espaces | lot 5 bis |
| balises par la vraie route (``create_tts_service``) : Soniox d'office, ElevenLabs seulement si réglé | lot 5 bis |
| ni transcription affichée, ni verbatim conservé, ni fiche ne portent un crochet | lot 5 bis (D11) |
| corpus des 3 889 phrases réelles : aucune phrase sans crochet modifiée | lot 5 bis (zéro perte) |

⛔ Portée lue à la lettre : aucun appel à Soniox. Ces tests prouvent ce que le code écrit et envoie, pas que Soniox
accepte une balise ni qu'il ne lit pas un crochet à voix haute (cela se juge à l'oreille, au banc : D10).

⚠️ Constat de lecture (Pipecat, ``tts_service.py`` l. 1257 et ``soniox/tts.py`` l. 208) : une voix qui horodate les
mots reconstruit l'historique du modèle depuis ce qu'elle a DIT, donc depuis le texte transformé. Pour Soniox
l'historique porte les balises permises (et les nombres en mots), jamais les balises retirées. Ce fichier ne prétend
pas le contraire : il prouve ce qui est vrai (la transcription, le verbatim et la fiche, eux, n'en montrent aucune).
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.services.pipecat.balises_expression import (
    BALISES_PAR_DEFAUT,
    retirer_balises,
    retirer_balises_pour_la_voix,
    sans_balises,
)
from api.tests.mark.test_voix_soniox import (
    ADRESSE_EUROPE,
    ADRESSE_MONDIALE,
    _audio,
    _config,
    _flux,
    _voix,
)

RACINE_API = Path(__file__).resolve().parents[2]
CORPUS = Path(__file__).parent / "donnees" / "phrases-agent.jsonl"


def _base() -> dict:
    return {"tts_provider": "soniox", "tts_model": "tts-rt-v2"}


def _voix_avec(config, run_configs=None):
    """Le connecteur que l'appel construit, avec les réglages de l'agent, par la porte du produit."""
    from api.services.pipecat.service_factory import create_tts_service

    return create_tts_service(SimpleNamespace(tts=config), _audio(), run_configs=run_configs)


async def _dit(service, texte):
    """Le texte tel qu'il part à la voix : toute la file de transformations, dans l'ordre (comme Pipecat)."""
    for _type, transformation in service._text_transforms:
        texte = await transformation(texte, "*")
    return texte


def _eleven():
    from api.services.configuration.registry import ElevenlabsTTSConfiguration

    return ElevenlabsTTSConfiguration(
        api_key="el-key", model="eleven_flash_v2_5", voice="voix-eleven", speed=1.0
    )


# --------------------------------------------------------------------------- #
# Lot 4 : l'estampille
# --------------------------------------------------------------------------- #


def test_la_fiche_dit_soniox_l_adresse_appelee_et_les_reglages():
    from api.services.pipecat.service_factory import stamp_voice_settings

    stampe = stamp_voice_settings(_base(), _config())
    assert stampe["tts_provider"] == "soniox"  # déjà estampillé par l'appelant, intact
    assert stampe["tts_settings"] == {
        "voice": "Mathieu",
        "endpoint": ADRESSE_EUROPE,
        "language": "fr",
        "text_aggregation_mode": "sentence",
        "balises_permises": list(BALISES_PAR_DEFAUT),
    }


def test_la_vitesse_et_le_silence_reduit_ne_sont_estampilles_que_remplis():
    from api.services.pipecat.service_factory import stamp_voice_settings

    vide = stamp_voice_settings(_base(), _config())["tts_settings"]
    assert "speed" not in vide and "reduce_silence" not in vide
    rempli = stamp_voice_settings(_base(), _config(speed=1.2, reduce_silence=False))["tts_settings"]
    assert rempli["speed"] == 1.2
    assert rempli["reduce_silence"] is False  # une valeur, pas un vide


@pytest.mark.parametrize(
    "reglages",
    [
        {},
        {"voice": ""},
        {"voice": "Celine", "language": "en"},
        {"base_url": ADRESSE_MONDIALE},
        {"base_url": ""},
        {"speed": 1.2, "reduce_silence": True},
    ],
)
def test_l_estampille_est_ce_que_la_vraie_fabrique_envoie(reglages):
    """R1 : la fiche n'est pas recalculée à part, elle égale la requête construite par la porte du produit."""
    from api.services.pipecat.service_factory import stamp_voice_settings

    config = _config(**reglages)
    service = _voix(config)
    message = _flux(service)
    stampe = stamp_voice_settings(_base(), config)["tts_settings"]

    assert stampe["endpoint"] == service._url
    assert stampe["voice"] == message["voice"]
    assert stampe["language"] == message["language"]
    assert stampe.get("speed") == message.get("speed")
    assert stampe.get("reduce_silence") == message.get("reduce_silence")


def test_le_mode_d_envoi_du_texte_retenu_est_sur_la_fiche():
    """D-10 : la voix Soniox réglée « mot à mot » depuis l'écran de la voix l'emporte quand l'agent n'a rien demandé ;
    l'agent qui a demandé autre chose que le défaut garde la main."""
    from api.services.pipecat.service_factory import mode_d_envoi_du_texte, stamp_voice_settings

    def mode(config, run_configs=None):
        return stamp_voice_settings(_base(), config, run_configs)["tts_settings"]["text_aggregation_mode"]

    assert mode(_config()) == "sentence"
    assert mode(_config(text_aggregation_mode="token")) == "token"
    assert mode(_config(text_aggregation_mode="token"), {}) == "token"
    assert mode(_config(text_aggregation_mode="token"), {"tts_text_aggregation_mode": "sentence"}) == "token"
    assert mode(_config(), {"tts_text_aggregation_mode": "token"}) == "token"
    assert mode(_config(text_aggregation_mode="sentence"), {"tts_text_aggregation_mode": "token"}) == "token"
    # La même fonction répond partout.
    assert mode_d_envoi_du_texte(_config(text_aggregation_mode="token"), None) == "token"
    assert mode_d_envoi_du_texte(None, {"tts_text_aggregation_mode": "token"}) == "token"
    assert mode_d_envoi_du_texte(None, None) == "sentence"
    assert mode_d_envoi_du_texte(_eleven(), {"tts_text_aggregation_mode": None}) == "sentence"


def test_les_reglages_de_pipeline_de_la_fiche_disent_le_mode_retenu():
    """``pipeline_settings.tts_text_aggregation_mode`` : le mode EFFECTIF, pas le seul réglage d'agent."""
    from api.services.pipecat.service_factory import stamp_pipeline_settings

    config = _config(text_aggregation_mode="token")
    brut = stamp_pipeline_settings({}, {})["pipeline_settings"]["tts_text_aggregation_mode"]
    retenu = stamp_pipeline_settings({}, {}, tts_config=config)["pipeline_settings"][
        "tts_text_aggregation_mode"
    ]
    assert (brut, retenu) == ("sentence", "token")


def test_les_reglages_de_pipeline_de_la_fiche_disent_les_balises_resolues():
    """Relecture M1 : la liste RÉSOLUE, pour Soniox (défaut d'office) et pour un agent ElevenLabs qui l'a réglée ;
    un agent qui n'a rien réglé : ``None``, rien de plus."""
    from api.services.pipecat.service_factory import stamp_pipeline_settings

    def balises(run_configs, voix):
        return stamp_pipeline_settings({}, run_configs, tts_config=voix)["pipeline_settings"][
            "tts_balises_permises"
        ]

    assert balises({}, _config()) == list(BALISES_PAR_DEFAUT)
    assert balises({"tts_balises_permises": ["calm"]}, _config()) == ["calm"]
    assert balises({"tts_balises_permises": []}, _config()) == []
    assert balises({"tts_balises_permises": ["warm"]}, _eleven()) == ["warm"]
    assert balises({}, _eleven()) is None
    assert balises({}, None) is None


def test_le_chemin_telephonique_estampille_le_mode_retenu():
    """Lecture du code de l'appel (comme ``test_estampille_voix``) : l'appel passe le mode RÉSOLU à la fiche."""
    from api.services.pipecat import run_pipeline

    import inspect

    source = inspect.getsource(run_pipeline)
    assert "stamp_voice_settings(runtime_configuration, user_config.tts, run_configs)" in source
    assert 'tts_config=getattr(user_config, "tts", None)' in source


def test_l_estampille_des_autres_voix_ne_bouge_pas():
    from api.services.pipecat.service_factory import stamp_voice_settings

    stampe = stamp_voice_settings(
        {}, _eleven(), {"tts_text_aggregation_mode": "token", "tts_balises_permises": ["warm"]}
    )["tts_settings"]
    assert stampe["voice"] == "voix-eleven"
    for cle in ("text_aggregation_mode", "balises_permises", "language", "speed", "reduce_silence"):
        assert cle not in stampe, cle


@pytest.mark.asyncio
async def test_un_agent_transfere_estampille_la_voix_de_l_appel_et_son_mode():
    """L'agent reçu par transfert est estampillé comme le premier : la voix de l'APPEL, le mode retenu."""
    from api.tests.mark.test_agent_transfere_reglages_mark import _construire, _fabrique

    voix = _config(text_aggregation_mode="token", base_url=ADRESSE_MONDIALE)
    agent = await _construire(_fabrique(voix=voix), {})
    stampe = agent.runtime_configuration["tts_settings"]
    assert stampe["endpoint"] == ADRESSE_MONDIALE
    # Les réglages de l'agent de destination disent « sentence » : la voix réglée « mot à mot » l'emporte.
    assert stampe["text_aggregation_mode"] == "token"


# --------------------------------------------------------------------------- #
# D-10, même famille : le filtre du nom et de la civilité, et tout lecteur du mode
# --------------------------------------------------------------------------- #


def _filtre(run_configs, voix=None):
    from api.services.pipecat.filtre_nom_civilite import creer_filtre_nom_civilite

    return creer_filtre_nom_civilite({"interdire_nom_appelant": True, **run_configs}, dict, voix=voix)


def test_le_filtre_du_nom_lit_le_mode_resolu():
    # Voix Soniox « mot à mot » depuis l'écran de la voix, agent qui n'a rien demandé.
    assert _filtre({}, voix=_config(text_aggregation_mode="token"))._par_phrase is False
    assert _filtre({"tts_text_aggregation_mode": "sentence"}, voix=_config(text_aggregation_mode="token"))._par_phrase is False
    # Voix Soniox par défaut : phrase par phrase.
    assert _filtre({}, voix=_config())._par_phrase is True
    # L'agent qui a demandé autre chose que le défaut garde la main.
    assert _filtre({"tts_text_aggregation_mode": "token"}, voix=_config())._par_phrase is False
    # Agents existants : sans voix ou avec une autre voix, le réglage d'agent, comme avant.
    assert _filtre({})._par_phrase is True
    assert _filtre({"tts_text_aggregation_mode": "token"})._par_phrase is False
    assert _filtre({}, voix=_eleven())._par_phrase is True
    assert _filtre({"tts_text_aggregation_mode": "token"}, voix=_eleven())._par_phrase is False


def test_aucun_lecteur_du_seul_reglage_d_agent_ne_reste():
    """« Cherche-les tous » : le mode d'envoi du texte ne se lit que par ``service_factory`` (sa fonction résolue et
    les collecteurs qui reçoivent le dictionnaire résolu). Un lecteur de plus, ailleurs, ferait croire à la phrase par
    phrase sous une voix réglée mot à mot."""
    lecteur = re.compile(
        r"""\.get\(\s*["']tts_text_aggregation_mode["']|\[\s*["']tts_text_aggregation_mode["']\s*\]"""
        r"""|getattr\([^)]*["']tts_text_aggregation_mode["']"""
    )
    trouves = []
    for chemin in RACINE_API.rglob("*.py"):
        relatif = chemin.relative_to(RACINE_API).as_posix()
        if relatif.startswith(("tests/", ".venv", "alembic/")) or "/tests/" in relatif:
            continue
        if lecteur.search(chemin.read_text(encoding="utf-8", errors="replace")):
            trouves.append(relatif)
    assert trouves == ["services/pipecat/service_factory.py"], trouves


# --------------------------------------------------------------------------- #
# Lot 5 : la clé de la voix
# --------------------------------------------------------------------------- #


class _Reponse:
    def raise_for_status(self):
        return None


@pytest.mark.parametrize(
    "adresse, api_attendue",
    [
        ("", "https://api.eu.soniox.com/v1/models"),
        (ADRESSE_EUROPE, "https://api.eu.soniox.com/v1/models"),
        (ADRESSE_MONDIALE, "https://api.soniox.com/v1/models"),
        ("wss://tts-rt.eu.soniox.com/passerelle", "https://api.eu.soniox.com/v1/models"),
        ("wss://tts-rt.soniox.com/passerelle", "https://api.soniox.com/v1/models"),
    ],
)
def test_la_cle_de_la_voix_est_verifiee_dans_la_region_de_l_adresse_de_la_voix(monkeypatch, adresse, api_attendue):
    from api.services.configuration import check_validity

    appels = []
    monkeypatch.setattr(
        check_validity.httpx,
        "get",
        lambda url, headers=None, timeout=None: appels.append((url, headers)) or _Reponse(),
    )
    config = _config(base_url=adresse, adresse_libre=True)
    assert check_validity.UserConfigurationValidator()._validate_service(config, "tts") == []
    assert appels == [(api_attendue, {"Authorization": "Bearer soniox-key"})]


def test_la_voix_lit_la_region_par_la_fonction_de_la_voix(monkeypatch):
    """La fonction propre à la voix, pas celle de la transcription : on les distingue en lui faisant dire autre chose."""
    from api.services.configuration import check_validity

    appels = []
    monkeypatch.setattr(
        check_validity.httpx, "get", lambda url, headers=None, timeout=None: appels.append(url) or _Reponse()
    )
    monkeypatch.setattr(check_validity, "region_soniox_voix", lambda base_url: "eu")
    monkeypatch.setattr(check_validity, "region_soniox", lambda base_url: "global")
    check_validity.UserConfigurationValidator()._validate_service(_config(), "tts")
    assert appels == ["https://api.eu.soniox.com/v1/models"]

    appels.clear()
    from api.services.configuration.registry import SonioxSTTConfiguration

    check_validity.UserConfigurationValidator()._validate_service(
        SonioxSTTConfiguration(api_key="soniox-key"), "stt"
    )
    assert appels == ["https://api.soniox.com/v1/models"], "la transcription garde sa propre fonction de région"


def test_une_cle_refusee_dit_la_region_interrogee(monkeypatch):
    import httpx

    from api.services.configuration import check_validity

    def refuse(url, headers=None, timeout=None):
        raise httpx.HTTPStatusError(
            "401", request=httpx.Request("GET", url), response=httpx.Response(401, request=httpx.Request("GET", url))
        )

    monkeypatch.setattr(check_validity.httpx, "get", refuse)
    statuts = check_validity.UserConfigurationValidator()._validate_service(_config(), "tts")
    assert len(statuts) == 1 and "api.eu.soniox.com" in statuts[0]["message"]


# --------------------------------------------------------------------------- #
# Lot 5 bis : le garde-fou des balises, fonctions
# --------------------------------------------------------------------------- #


def test_une_balise_permise_passe_une_inconnue_est_retiree():
    permises = ["warm", "pause"]
    assert retirer_balises("[warm] Bonjour.", permises) == "[warm] Bonjour."
    assert retirer_balises("[fou] Bonjour.", permises) == "Bonjour."
    assert retirer_balises("[warm] Bonjour [fou] monsieur.", permises) == "[warm] Bonjour monsieur."
    assert retirer_balises("Oui [fou] d'accord", permises) == "Oui d'accord"
    assert retirer_balises("Voilà [fou].", permises) == "Voilà."
    assert retirer_balises("Voilà [fou]", permises) == "Voilà"
    assert retirer_balises("[fou]", permises) == ""
    assert retirer_balises("[warm][fou] Bonjour", permises) == "[warm] Bonjour"


def test_la_casse_les_espaces_et_les_crochets_de_la_liste_ne_comptent_pas():
    assert retirer_balises("[Warm] Bonjour", ["warm"]) == "[Warm] Bonjour"
    assert retirer_balises("[ warm ] Bonjour", ["warm"]) == "[ warm ] Bonjour"
    assert retirer_balises("[warm] Bonjour", ["[warm]"]) == "[warm] Bonjour"
    assert retirer_balises("[warm] Bonjour", [" WARM "]) == "[warm] Bonjour"
    assert retirer_balises("[long pause] Bonjour", ["pause"]) == "Bonjour"


@pytest.mark.parametrize("permises", [(), [], None, [""], ["", None]])
def test_liste_vide_ou_absente_tous_les_crochets_sont_retires(permises):
    assert retirer_balises("[warm] Bonjour [pause] monsieur.", permises) == "Bonjour monsieur."


def test_un_texte_sans_crochet_est_rendu_identique():
    texte = "Bonjour, il est 14 h 30. Vous voulez un rendez-vous ?"
    assert retirer_balises(texte, ["warm"]) is texte
    assert retirer_balises(texte, ()) is texte
    assert sans_balises(texte) is texte


def test_un_crochet_jamais_ferme_ou_trop_long_n_est_pas_touche():
    assert retirer_balises("Bonjour [warm", ()) == "Bonjour [warm"
    long = "[" + "x" * 200 + "]"
    assert retirer_balises(f"A {long} B", ()) == f"A {long} B"


@pytest.mark.asyncio
async def test_la_transformation_ne_leve_jamais(monkeypatch):
    from api.services.pipecat import balises_expression

    transformation = retirer_balises_pour_la_voix(["warm"])
    assert await transformation("[warm] A [fou] B", "*") == "[warm] A B"

    def casse(*_a, **_k):
        raise RuntimeError("panne")

    monkeypatch.setattr(balises_expression, "retirer_balises", casse)
    assert await transformation("[warm] A", "*") == "[warm] A"


# --------------------------------------------------------------------------- #
# Lot 5 bis : par la vraie route
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_voix_soniox_porte_le_garde_fou_d_office():
    service = _voix_avec(_config())
    assert await _dit(service, "[warm] Bonjour [fou] monsieur.") == "[warm] Bonjour monsieur."
    assert await _dit(service, "Bonjour monsieur.") == "Bonjour monsieur."


@pytest.mark.asyncio
async def test_la_liste_de_l_agent_remplace_la_liste_par_defaut():
    service = _voix_avec(_config(), {"tts_balises_permises": ["calm"]})
    assert await _dit(service, "[warm] A [calm] B") == "A [calm] B"


@pytest.mark.asyncio
async def test_reglage_eteint_tous_les_crochets_sont_retires():
    service = _voix_avec(_config(), {"tts_balises_permises": []})
    assert await _dit(service, "[warm] A [pause] B") == "A B"


@pytest.mark.asyncio
async def test_un_agent_elevenlabs_qui_n_a_rien_allume_garde_son_texte_tel_quel():
    """Zéro perte : pas de réglage, pas de transformation, même avec un crochet dans le texte."""
    service = _voix_avec(_eleven(), {})
    assert all(
        "balises" not in getattr(transformation, "__qualname__", "")
        for _type, transformation in service._text_transforms
    )
    assert await _dit(service, "Bonjour [fou] monsieur.") == "Bonjour [fou] monsieur."
    sans_run_configs = _voix_avec(_eleven())
    assert await _dit(sans_run_configs, "Bonjour [fou] monsieur.") == "Bonjour [fou] monsieur."


@pytest.mark.asyncio
async def test_elevenlabs_applique_la_liste_quand_l_agent_l_a_reglee():
    service = _voix_avec(_eleven(), {"tts_balises_permises": ["warm"]})
    assert await _dit(service, "[warm] Bonjour [fou] monsieur.") == "[warm] Bonjour monsieur."


@pytest.mark.asyncio
async def test_mot_a_mot_la_transformation_n_est_pas_posee():
    """Mot à mot, un crochet arrive en morceaux et ne peut pas être lu (comme les nombres en mots)."""
    par_la_voix = _voix_avec(_config(text_aggregation_mode="token"))
    par_l_agent = _voix_avec(_config(), {"tts_text_aggregation_mode": "token"})
    for service in (par_la_voix, par_l_agent):
        assert await _dit(service, "Bonjour [fou]") == "Bonjour [fou]"


@pytest.mark.asyncio
async def test_le_retrait_passe_apres_les_nombres_en_mots_et_avant_la_voix():
    """Dans la file, le retrait des balises est après le remplacement des prononciations, le dernier avant la voix."""
    from api.services.pipecat.service_factory import construire_remplacements_de_voix

    transformations = construire_remplacements_de_voix(
        {"tts_replacements": ["SAV:S. A. V."], "tts_balises_permises": ["warm"]}, langue_francaise=True
    )
    assert len(transformations) == 4  # prononciations, courriels, nombres, balises
    assert await transformations[-1][1]("[fou] Appelez le S. A. V.", "*") == "Appelez le S. A. V."


# --------------------------------------------------------------------------- #
# Lot 5 bis : jamais de crochet dans ce qui est lu
# --------------------------------------------------------------------------- #


def test_la_transcription_affichee_et_le_verbatim_ne_montrent_aucun_crochet():
    from api.services.pipecat.realtime_feedback_events import build_bot_text_event

    assert build_bot_text_event(text="[warm] Bonjour [pause] monsieur.")["payload"]["text"] == "Bonjour monsieur."
    assert build_bot_text_event(text="Bonjour monsieur.")["payload"]["text"] == "Bonjour monsieur."


@pytest.mark.asyncio
async def test_le_verbatim_conserve_par_le_tour_de_l_assistant_ne_porte_aucun_crochet():
    from api.services.pipecat.realtime_feedback_observer import register_turn_log_handlers

    gestionnaires = {}

    class _Agregateur:
        def event_handler(self, nom):
            def poser(fonction):
                gestionnaires[nom] = fonction
                return fonction

            return poser

    recu = []

    class _Coordinateur:
        async def record_assistant_transcript(self, text, timestamp, end_timestamp=None):
            recu.append(text)

        async def record_user_transcript(self, **_k):
            return None

    register_turn_log_handlers(_Coordinateur(), _Agregateur(), _Agregateur())
    message = SimpleNamespace(content="[warm] Bonjour [pause] monsieur.", timestamp="t", end_timestamp=None)
    await gestionnaires["on_assistant_turn_stopped"](None, message)
    assert recu == ["Bonjour monsieur."]


def test_la_fiche_ne_lit_aucun_crochet_et_l_historique_du_modele_reste_intact():
    from api.services.pipecat.greffier import message_du_greffier
    from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche

    historique = [
        {"role": "assistant", "content": "[warm] Bonjour [pause] monsieur."},
        {"role": "user", "content": "Bonjour, c'est pour un devis."},
    ]
    copie = [dict(m) for m in historique]
    message = message_du_greffier(ReglagesFiche(champs=()), {}, historique)
    assert "Agent : Bonjour monsieur." in message
    assert "[warm]" not in message and "[pause]" not in message
    assert historique == copie, "l'historique du modèle n'est pas touché"


# --------------------------------------------------------------------------- #
# Lot 5 bis : le corpus des phrases réelles, zéro perte
# --------------------------------------------------------------------------- #


def _phrases():
    with CORPUS.open(encoding="utf-8") as fichier:
        return [json.loads(ligne)["texte"] for ligne in fichier if ligne.strip()]


def test_corpus_aucune_phrase_sans_crochet_n_est_modifiee():
    phrases = _phrases()
    # ⛔ Le comptage dans les deux sens : un corpus mal lu rendrait ce test vert sans rien prouver.
    assert len(phrases) > 3000, f"corpus trop maigre : {len(phrases)} phrases"
    avec = [p for p in phrases if "[" in p or "]" in p]
    assert 0 < len(avec) < 40, f"{len(avec)} phrases avec crochet : loin des 7 relevées le 22/10"
    for phrase in phrases:
        if "[" in phrase or "]" in phrase:
            continue
        assert retirer_balises(phrase, ()) == phrase, phrase
        assert retirer_balises(phrase, BALISES_PAR_DEFAUT) == phrase, phrase
        assert sans_balises(phrase) == phrase, phrase


@pytest.mark.asyncio
async def test_corpus_la_file_de_la_voix_soniox_ne_change_que_les_phrases_a_crochet():
    """Par la vraie route : la file complète de la voix Soniox, phrase par phrase, comparée à celle d'un
    agent qui n'a rien allumé. Les nombres en mots (agent français) ne sont pas posés ici (pas de transcription)."""
    service = _voix_avec(_config())
    # La référence : la file d'un agent ElevenLabs qui n'a rien allumé (les autres transformations de la
    # voix, comme le retrait d'un appel de fonction écrit, y sont les mêmes ; seul le garde-fou manque).
    reference = _voix_avec(_eleven())
    phrases = _phrases()
    modifiees = 0
    for phrase in phrases:
        sortie = await _dit(service, phrase)
        if "[" not in phrase:
            assert sortie == await _dit(reference, phrase), phrase
        elif sortie != await _dit(reference, phrase):
            modifiees += 1
    assert modifiees > 0, "aucune des phrases à crochet n'a été touchée : le retrait ne joue pas"


# --------------------------------------------------------------------------- #
# Relecture : m4 (journal sans texte) et m6 (l'écran, pour toutes les voix, comme avant)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_journal_ne_garde_jamais_le_texte_envoye_a_la_voix():
    from loguru import logger

    lignes = []
    identifiant = logger.add(lambda m: lignes.append(str(m)), level="INFO")
    try:
        await retirer_balises_pour_la_voix(["warm"])("[warm] Bonjour monsieur Dupont [fou].", "*")
    finally:
        logger.remove(identifiant)
    journal = "".join(lignes)
    assert "fou" in journal and "1" in journal
    assert "Dupont" not in journal and "Bonjour" not in journal


async def _mots_montres(textes):
    from pipecat.frames.frames import TTSTextFrame
    from pipecat.observers.base_observer import FramePushed
    from pipecat.processors.frame_processor import FrameDirection
    from pipecat.transports.base_output import BaseOutputTransport

    from api.services.pipecat.realtime_feedback_observer import RealtimeFeedbackObserver

    envoyes = []

    async def envoyer(message):
        envoyes.append(message["payload"]["text"])

    observateur = RealtimeFeedbackObserver(envoyer)
    from unittest.mock import create_autospec

    source = create_autospec(BaseOutputTransport, instance=True)
    for texte in textes:
        trame = TTSTextFrame(texte, aggregated_by="word")
        await observateur.on_push_frame(
            FramePushed(
                source=source,
                destination=source,
                frame=trame,
                direction=FrameDirection.DOWNSTREAM,
                timestamp=0,
            )
        )
    return envoyes


@pytest.mark.asyncio
async def test_l_ecran_recoit_toujours_un_mot_d_espaces_et_saute_une_balise_seule():
    # Sans crochet : le comportement d'avant, à l'octet (un mot d'espaces part aussi).
    assert await _mots_montres([" ", "Bonjour"]) == [" ", "Bonjour"]
    # Une balise seule ne laisse rien à montrer ; un mot normal passe, balise retirée.
    assert await _mots_montres(["[warm]", "Bonjour", "[pause] ok"]) == ["Bonjour", "ok"]
