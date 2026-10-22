"""[.mark] Chantier voix-soniox, lot 7 bis : les réglages de la voix ElevenLabs à l'écran.

La question de ce fichier (D6 du plan « naturel de la conversation ») :

    ``stability``, ``similarity_boost``, ``style`` et ``use_speaker_boost`` vont-ils de
    l'écran (la configuration) à la requête ElevenLabs par la porte du produit
    (``create_tts_service``), et un agent qui n'a rien réglé envoie-t-il EXACTEMENT ce
    qu'il envoyait (0,8 / 0,75, rien d'autre) ?

⛔ Portée lue à la lettre : aucun appel à ElevenLabs. Le test lit ``voice_settings``, le
dictionnaire que le connecteur met dans chaque message (``build_elevenlabs_voice_settings``).

| Test | Preuve |
|---|---|
| agent qui n'a rien réglé : ``voice_settings`` identique à celui d'avant (0,8 / 0,75 / vitesse) | cond. 4 |
| chaque réglage de l'écran arrive dans la requête | cond. 2 |
| champ vide = valeur d'aujourd'hui ; ``style`` et ``use_speaker_boost`` vides = non envoyés | D6 |
| 0 est une valeur (pas un « vide ») | piège classique |
| configuration enregistrée avant ce lot : relue et réécrite à l'identique | zéro perte |
| bornes 0 à 1 refusées à l'écriture ; schéma : groupe et libellés EN et FR | écran |
| estampille : inchangée sans réglage, la valeur jouée quand il y en a un | lot 4 |
"""

from types import SimpleNamespace

import pytest

from api.services.configuration.registry import ElevenlabsTTSConfiguration
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.service_factory import create_tts_service, stamp_voice_settings

CHAMPS = ("stability", "similarity_boost", "style", "use_speaker_boost")


def _voix(**reglages):
    config = ElevenlabsTTSConfiguration(api_key="el-key", voice="voix-eleven", **reglages)
    audio = AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=24000)
    return create_tts_service(SimpleNamespace(tts=config), audio)


def _requete(service):
    """Le ``voice_settings`` que chaque message du flux porte."""
    from pipecat.services.elevenlabs.tts import build_elevenlabs_voice_settings

    return build_elevenlabs_voice_settings(service._settings)


def test_un_agent_qui_n_a_rien_regle_envoie_ce_qu_il_envoyait():
    assert _requete(_voix()) == {"stability": 0.8, "similarity_boost": 0.75, "speed": 1.0}


@pytest.mark.parametrize(
    "champ, valeur",
    [("stability", 0.3), ("similarity_boost", 0.9), ("style", 0.4), ("use_speaker_boost", True)],
)
def test_chaque_reglage_de_l_ecran_arrive_dans_la_requete(champ, valeur):
    requete = _requete(_voix(**{champ: valeur}))
    assert requete[champ] == valeur
    # Les autres gardent leur valeur d'aujourd'hui.
    attendu = {"stability": 0.8, "similarity_boost": 0.75, "speed": 1.0, champ: valeur}
    assert requete == attendu


def test_zero_est_une_valeur_pas_un_vide():
    requete = _requete(_voix(stability=0.0, similarity_boost=0.0, style=0.0, use_speaker_boost=False))
    assert requete == {
        "stability": 0.0,
        "similarity_boost": 0.0,
        "style": 0.0,
        "use_speaker_boost": False,
        "speed": 1.0,
    }


def test_les_quatre_reglages_ensemble():
    requete = _requete(_voix(stability=0.5, similarity_boost=0.6, style=0.2, use_speaker_boost=True))
    assert requete == {
        "stability": 0.5,
        "similarity_boost": 0.6,
        "style": 0.2,
        "use_speaker_boost": True,
        "speed": 1.0,
    }


def test_une_configuration_enregistree_avant_le_lot_se_relit_et_se_reecrit_a_l_identique():
    ancienne = {
        "provider": "elevenlabs",
        "api_key": "el-key",
        "voice": "voix-eleven",
        "speed": 1.0,
        "model": "eleven_flash_v2_5",
        "base_url": "https://api.elevenlabs.io",
    }
    relue = ElevenlabsTTSConfiguration.model_validate(ancienne)
    ecrite = relue.model_dump(mode="json")
    assert not set(CHAMPS) & set(ecrite), "une clé nouvelle apparaît dans une configuration qui n'a rien réglé"
    assert ecrite == ancienne


def test_un_reglage_est_ecrit_seulement_quand_il_est_regle():
    ecrite = ElevenlabsTTSConfiguration(api_key="k", style=0.0).model_dump(mode="json")
    assert ecrite["style"] == 0.0
    assert "stability" not in ecrite and "use_speaker_boost" not in ecrite


@pytest.mark.parametrize("champ", ["stability", "similarity_boost", "style"])
@pytest.mark.parametrize("valeur", [-0.1, 1.1])
def test_hors_de_0_a_1_est_refuse_a_l_ecriture(champ, valeur):
    with pytest.raises(ValueError):
        ElevenlabsTTSConfiguration(api_key="k", **{champ: valeur})


def test_le_schema_range_les_reglages_dans_un_groupe_avec_ses_deux_langues():
    proprietes = ElevenlabsTTSConfiguration.model_json_schema()["properties"]
    for champ in CHAMPS:
        assert proprietes[champ]["mark_groupe"] == "caractere_de_la_voix", champ
        libelle = proprietes[champ]["mark_libelle"]
        assert libelle["en"] and libelle["fr"], champ


def _fiche(tts):
    return stamp_voice_settings({}, tts).get("tts_settings", {})


def test_l_estampille_d_un_agent_qui_n_a_rien_regle_n_a_pas_de_cle_de_plus():
    fiche = _fiche(ElevenlabsTTSConfiguration(api_key="k", voice="voix-eleven"))
    assert set(fiche) == {"voice", "endpoint"}


def test_l_estampille_dit_ce_qui_est_joue_quand_un_reglage_existe():
    config = ElevenlabsTTSConfiguration(api_key="k", voice="voix-eleven", style=0.3)
    fiche = _fiche(config)
    # La même fonction que la requête : stabilité vide = 0,8, jamais « absente ».
    requete = _requete(_voix(style=0.3))
    for champ in ("stability", "similarity_boost", "style"):
        assert fiche[champ] == requete[champ], champ
    assert "use_speaker_boost" not in fiche


# --------------------------------------------------------------------------- #
# Les aides en deux langues (voix-soniox, D-52 et D-53) : l'écran ne montre plus d'anglais en mode français
# --------------------------------------------------------------------------- #


def _schema(classe):
    return classe.model_json_schema()["properties"]


def test_chaque_aide_de_la_voix_elevenlabs_a_ses_deux_langues_et_l_anglais_est_la_description():
    proprietes = _schema(ElevenlabsTTSConfiguration)
    for champ in ("voice", "speed", "model", *CHAMPS, "base_url"):
        aide = proprietes[champ]["mark_aide"]
        assert aide["en"] == proprietes[champ]["description"], f"{champ}: l'anglais n'est pas la description"
        assert aide["fr"].strip() and aide["fr"] != aide["en"], f"{champ}: pas de français"


def test_chaque_aide_de_la_voix_soniox_a_ses_deux_langues_et_le_menu_ses_valeurs_nommees():
    from api.services.configuration.registry import SonioxTTSConfiguration

    proprietes = _schema(SonioxTTSConfiguration)
    for champ in ("model", "voice", "language", "speed", "reduce_silence", "text_aggregation_mode", "base_url", "region"):
        aide = proprietes[champ]["mark_aide"]
        assert aide["en"] == proprietes[champ]["description"], champ
        assert aide["fr"].strip() and aide["fr"] != aide["en"], champ
    valeurs = proprietes["text_aggregation_mode"]["mark_valeurs"]
    assert set(valeurs) == set(proprietes["text_aggregation_mode"]["enum"])
    assert all(v["en"] and v["fr"] for v in valeurs.values())


def test_la_case_saisie_libre_dit_ce_qu_elle_est_dans_les_deux_langues():
    case = _schema(ElevenlabsTTSConfiguration)["adresse_libre"]
    assert "Saisie libre" in case["mark_libelle"]["fr"] and "Free entry" in case["mark_libelle"]["en"]
    assert "schéma" in case["mark_libelle"]["fr"]
    assert "wss://" in case["mark_aide"]["en"] and "wss://" in case["mark_aide"]["fr"]
