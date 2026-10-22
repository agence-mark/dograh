"""[.mark] Chantier voix-soniox, lots 2 bis et 3 : la liste des voix et ce que la fabrique pose elle-même.

Complète ``test_voix_soniox.py`` (écrit au lot 1) par ce que les lots 2 bis et 3 ajoutent :

| Test | Preuve |
|---|---|
| les 11 voix françaises sont dans la liste, Mathieu, Celine, Julien en tête | lot 2 bis (D2) |
| le menu de l'écran est cette liste, et l'écran reçoit aussi description, accent, genre | lot 2 bis |
| aucune description ni aucun genre inventé (``None`` = non relevé), date et source écrites | lot 2 bis |
| les langues de la voix sont celles du connecteur de NOTRE épinglage | lot 2 |
| la voix proposée d'office est française (jamais celle du connecteur), même champ vidé | lot 3 |
| format ``pcm_s16le`` et fréquence du transport posés par la fabrique | lot 3 |
| le mode d'envoi du texte : l'agent qui a demandé autre chose que le défaut garde la main | lot 3 (D3) |
| un autre fournisseur de voix : le dictionnaire de réglages d'agent est rendu INCHANGÉ | zéro perte |
| la garde du modèle (4 s) s'applique sous une voix Soniox, sous le délai de flux de Soniox | lot 3 (D16) |

⛔ Portée lue à la lettre : aucun appel à Soniox. Ces tests ne disent pas que Soniox accepte
une valeur, seulement que ce que l'écran déclare arrive, ou est refusé, par la porte du produit.
"""

import pytest

from api.tests.mark.test_voix_soniox import _audio, _classe, _config, _flux, _voix

FRANCAISES = (
    "Julien",
    "Olivier",
    "Elodie",
    "Camille",
    "Manon",
    "Mathieu",
    "Celine",
    "Baptiste",
    "Noemie",
    "Genevieve",
    "Antoine",
)


# --------------------------------------------------------------------------- #
# Lot 2 bis : la liste des voix
# --------------------------------------------------------------------------- #


def test_les_onze_voix_francaises_sont_dans_la_liste():
    from api.services.configuration.options import SONIOX_TTS_VOIX

    francaises = [voix["id"] for voix in SONIOX_TTS_VOIX if voix["francais"]]
    assert sorted(francaises) == sorted(FRANCAISES)
    assert len(francaises) == len(set(francaises)) == 11


def test_mathieu_celine_julien_sont_proposes_en_tete():
    from api.services.configuration.options import SONIOX_TTS_VOIX_IDS

    assert SONIOX_TTS_VOIX_IDS[:3] == ("Mathieu", "Celine", "Julien")


def test_le_menu_de_l_ecran_est_la_liste_et_la_saisie_libre_reste_ouverte():
    from api.services.configuration.options import SONIOX_TTS_VOIX_IDS

    voix = _classe().model_json_schema()["properties"]["voice"]
    assert tuple(voix["examples"]) == SONIOX_TTS_VOIX_IDS
    assert voix["allow_custom_input"] is True


def test_l_ecran_recoit_aussi_description_accent_genre_et_le_filtre_francais():
    voix = _classe().model_json_schema()["properties"]["voice"]["mark_voix"]
    assert [v["id"] for v in voix][:3] == ["Mathieu", "Celine", "Julien"]
    for v in voix:
        assert set(v) == {"id", "francais", "accent", "genre", "description"}
    assert {v["accent"] for v in voix if v["francais"]} == {"France", "Québec"}


def test_aucune_description_ni_genre_inventes_et_la_source_est_ecrite():
    """``None`` = non relevé. Tant que la liste complète n'est pas relevée par l'API (script prêt,
    jamais lancé dans ce chantier), on n'écrit que ce que la note du 21/10 consigne."""
    from api.services.configuration.options import (
        SONIOX_TTS_VOIX,
        SONIOX_TTS_VOIX_RELEVE,
        SONIOX_TTS_VOIX_SOURCE,
    )

    assert SONIOX_TTS_VOIX_RELEVE == "2026-10-21"
    assert "tts-models" in SONIOX_TTS_VOIX_SOURCE
    assert all(voix["genre"] is None for voix in SONIOX_TTS_VOIX)
    decrites = {voix["id"] for voix in SONIOX_TTS_VOIX if voix["description"]}
    assert decrites == {"Mathieu", "Celine", "Julien", "Manon"}


def test_le_script_de_releve_est_pret_et_ne_lance_rien_a_l_import():
    """Lot 2 bis : le relevé de la liste complète est un script à lancer à la main. L'importer ne
    fait aucun appel (⛔ aucun appel réseau dans ce chantier) ; ni la clé ni son nom ne sont écrits."""
    import importlib
    import inspect

    module = importlib.import_module("api.scripts.mark.releve_voix_soniox")
    assert callable(module.main)
    source = inspect.getsource(module)
    assert "/v1/tts-models" in source
    assert "print(cle" not in source and "print(f\"{cle" not in source


# --------------------------------------------------------------------------- #
# Lot 2 : les langues de la voix
# --------------------------------------------------------------------------- #


def test_les_langues_de_la_voix_sont_celles_du_connecteur_de_notre_epinglage():
    """Une langue que Pipecat ne sait pas dire tomberait au démarrage de l'appel ; une langue qu'il
    gagne à la montée de version doit apparaître ici au lieu de quitter l'écran en silence."""
    from pipecat.services.soniox.tts import language_to_soniox_tts_language
    from pipecat.transcriptions.language import Language

    from api.services.configuration.options import SONIOX_TTS_LANGUAGES

    codes = {language_to_soniox_tts_language(langue) for langue in Language} - {None}
    assert set(SONIOX_TTS_LANGUAGES) == codes
    assert "multi" not in SONIOX_TTS_LANGUAGES


# --------------------------------------------------------------------------- #
# Lot 3 : ce que la fabrique pose elle-même
# --------------------------------------------------------------------------- #


def test_la_voix_proposee_d_office_est_francaise_jamais_celle_du_connecteur():
    from api.services.configuration.options import SONIOX_TTS_VOIX_PAR_DEFAUT

    assert _config().voice == SONIOX_TTS_VOIX_PAR_DEFAUT == "Mathieu"
    assert _flux(_voix())["voice"] == "Mathieu"


@pytest.mark.parametrize("vide", ["", "   "])
def test_une_voix_videe_retombe_sur_la_voix_du_produit_pas_sur_celle_du_connecteur(vide):
    """Le connecteur a Bryce pour défaut, une voix anglaise : un agent français ne doit jamais
    s'ouvrir avec elle parce qu'un champ a été vidé."""
    assert _flux(_voix(voice=vide))["voice"] == "Mathieu"


def test_le_format_audio_et_la_frequence_sont_poses_par_la_fabrique():
    from api.services.pipecat.audio_config import AudioConfig
    from api.services.pipecat.service_factory import SONIOX_TTS_FORMAT_AUDIO, create_tts_service
    from types import SimpleNamespace

    assert SONIOX_TTS_FORMAT_AUDIO == "pcm_s16le"
    service = _voix()
    assert service._audio_format == "pcm_s16le"
    assert _flux(service)["audio_format"] == "pcm_s16le"
    # La fréquence du transport (ici 24 000), pas celle du pipeline : rien n'est rééchantillonné
    # sur une ligne téléphonique.
    assert service._init_sample_rate == _audio().transport_out_sample_rate == 24000
    telephone = create_tts_service(
        SimpleNamespace(tts=_config()),
        AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=8000),
    )
    assert telephone._init_sample_rate == 8000


def test_ni_le_format_ni_la_frequence_ne_sont_des_reglages_de_l_ecran():
    proprietes = _classe().model_json_schema()["properties"]
    assert "audio_format" not in proprietes
    assert "sample_rate" not in proprietes


def _mode(**kwargs):
    from types import SimpleNamespace

    from api.services.pipecat.service_factory import create_tts_service

    run_configs = kwargs.pop("run_configs", None)
    return create_tts_service(
        SimpleNamespace(tts=_config(**kwargs)), _audio(), run_configs=run_configs
    )._text_aggregation_mode


@pytest.mark.parametrize(
    "voix, agent, attendu",
    [
        ("sentence", None, "sentence"),  # rien allumé : comme aujourd'hui
        ("token", None, "token"),  # l'écran de la voix
        ("sentence", "token", "token"),  # l'agent a demandé autre chose que le défaut : il garde la main
        ("token", "token", "token"),
        ("token", "sentence", "token"),  # « sentence » est le défaut : l'écran de la voix décide
        ("sentence", "sentence", "sentence"),
    ],
)
def test_le_mode_d_envoi_du_texte_voix_et_agent(voix, agent, attendu):
    run_configs = {"tts_text_aggregation_mode": agent} if agent else None
    assert str(_mode(text_aggregation_mode=voix, run_configs=run_configs)) == attendu


def test_les_filtres_de_texte_suivent_le_mode_de_la_voix():
    """La phrase par phrase retire un appel de fonction écrit dans le texte ; mot à mot il arrive en
    morceaux et le retrait ne s'applique pas (réglage commun à toutes les voix). Le mode choisi à
    l'écran de la voix doit donc régler AUSSI ces transformations, pas seulement le connecteur."""
    from api.services.pipecat.service_factory import _run_configs_avec_le_mode_de_la_voix

    voix = _config(text_aggregation_mode="token")
    assert _run_configs_avec_le_mode_de_la_voix(voix, None) == {"tts_text_aggregation_mode": "token"}
    # Les autres réglages de l'agent sont conservés, le dictionnaire de l'agent n'est pas modifié.
    agent = {"tts_silence_time_s": 2.0}
    effectif = _run_configs_avec_le_mode_de_la_voix(voix, agent)
    assert effectif == {"tts_silence_time_s": 2.0, "tts_text_aggregation_mode": "token"}
    assert agent == {"tts_silence_time_s": 2.0}


def test_un_autre_fournisseur_de_voix_recoit_le_dictionnaire_d_agent_inchange():
    """Zéro perte : ElevenLabs (et tout autre) ne passe pas par le mode de la voix Soniox."""
    from api.services.configuration.registry import ElevenlabsTTSConfiguration
    from api.services.pipecat.service_factory import _run_configs_avec_le_mode_de_la_voix

    eleven = ElevenlabsTTSConfiguration(api_key="el-key")
    agent = {"tts_text_aggregation_mode": "token"}
    assert _run_configs_avec_le_mode_de_la_voix(eleven, agent) is agent
    assert _run_configs_avec_le_mode_de_la_voix(eleven, None) is None


def test_les_reglages_envoyes_sont_lus_une_seule_fois_pour_l_estampille_a_venir():
    """Même fonction pour la requête et (lot 4) l'estampille : jamais deux collectes (18 § 5.4)."""
    from api.services.pipecat.service_factory import _reglages_soniox_voix

    vide = _reglages_soniox_voix(_config())
    assert vide == {
        "base_url": "wss://tts-rt.eu.soniox.com/tts-websocket",
        "model": "tts-rt-v2",
        "voice": "Mathieu",
        "language": "fr",
    }
    plein = _reglages_soniox_voix(_config(speed=0.9, reduce_silence=False))
    assert plein["speed"] == 0.9
    assert plein["reduce_silence"] is False  # « faux » est une valeur, pas un champ vide


# --------------------------------------------------------------------------- #
# D16 : le modèle qui dépasse le délai de flux
# --------------------------------------------------------------------------- #


def test_la_garde_du_modele_s_arme_sous_une_voix_soniox_et_sous_le_delai_de_flux():
    """D16 : le défaut de Pipecat (un flux sans texte plus de ~5 s meurt) est corrigé en 1.13 et ne
    se corrige PAS ici. Ce que ce chantier prouve : notre garde du modèle (4 s, pour tous les agents)
    rend la main avant ce délai, quelle que soit la voix, et la voix Soniox garde son maintien de
    connexion. Reste à vérifier au banc, sur une copie, avec un tour long provoqué exprès."""
    from api.services.panne.garde_modele import DELAI_PAR_DEFAUT_S, delai_de_garde

    delai_de_flux_soniox_s = 5.0
    assert delai_de_garde(None) == DELAI_PAR_DEFAUT_S == 4.0
    assert delai_de_garde({}) < delai_de_flux_soniox_s
    service = _voix()
    assert hasattr(service, "_keepalive_task_handler")
