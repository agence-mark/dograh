"""[.mark] Appel entrant vers un agent sans les fournisseurs que le pipeline exige : refusé avant le décroché.

| Test | Ce qu'il prouve |
|---|---|
| chaîne incomplète | quand la version liée à l'appel ne résout pas une des sections que le pipeline lit en chaîne, l'appel est refusé avant le décroché : aucune demande de décroché, run fermé avec le texte exact qui nomme les sections absentes, place rendue, canal de l'appelant supprimé |
| temps réel complet | un agent en temps réel, avec sa section temps réel et son cerveau, est décroché sans transcription ni voix : le pipeline ne les lit pas dans ce mode |
| temps réel sans cerveau | la section temps réel ne suffit pas : sans cerveau le pipeline s'arrêterait après le décroché, l'appel est donc refusé avant, le texte nommant le cerveau seul |
| temps réel demandé sans section temps réel | le drapeau seul ne fait pas le mode : sans section temps réel le pipeline joue l'appel en chaîne, donc une chaîne complète est décrochée, et jamais refusée pour « section temps réel manquante » |
| la version liée fait foi | quand la version liée à l'appel porte ses propres fournisseurs au complet, l'appel est décroché alors que l'organisation n'en a aucun et que la colonne de l'agent (celle du brouillon) est vide (garde pure : verte dès l'écriture, rouge prouvé par deux mutants, « le contrôle résout sans la configuration de la version » et « le contrôle lit la colonne du brouillon ») |

La résolution de la configuration est la VRAIE, celle du pipeline : seule la base est doublée, posée sur
les trois modules qui la lisent (le gestionnaire, la clôture d'un run, la résolution).

Deux pièges que ces tests ferment exprès :

- le ``except`` de l'accueil entrant fait déjà, pour toute exception, ce qu'un refus fait (run fermé,
  place rendue, canal supprimé). Un test « refusé » compare donc le texte EXACT de l'erreur et vérifie
  qu'aucune demande de décroché n'est partie : sans cela il serait vert parce qu'une doublure a levé ;
- la résolution remplace en silence une configuration mal écrite par une configuration vide ou par celle
  de l'organisation. Chaque test fait donc résoudre son montage par la vraie fonction AVANT d'agir, et
  compare la liste des sections présentes à ce qu'il croit avoir monté.
"""

from types import SimpleNamespace

import pytest

from api import constants
from api.services.configuration import ai_model_configuration
from api.services.telephony import ari_manager
from api.tests.mark.telephonie_commun import (
    CANAL_APPELANT,
    CONFIGURATION_TELEPHONIE,
    CREATION_DU_CANAL_MEDIA,
    MISE_EN_FILE_DES_INTEGRATIONS,
    ORGANISATION,
    RUN,
    canal_media_demande,
    monter_une_connexion,
)

AGENT_APPELE = 42
VERSION_LIEE = 77
PROPRIETAIRE = 7
POSTE_APPELE = "8000"
EVENEMENT = {
    "channel": {
        "caller": {"number": "0100000000"},
        "dialplan": {"exten": POSTE_APPELE},
        "name": "PJSIP/poste-1",
    }
}

# Écrits en dur : le test ne lit aucune constante du code.
DECROCHE = ("POST", f"/channels/{CANAL_APPELANT}/answer")
LECTURE_DE_L_ORGANISATION = (ORGANISATION, "MODEL_CONFIGURATION_V2")
QUOTA_CONSULTE = (AGENT_APPELE, ORGANISATION, RUN)
REFUS = "Call refused before answer: missing model configuration for "
SECTIONS = ("llm", "stt", "tts", "realtime")

# Des sections valides pour le registre des fournisseurs. Une section mal écrite ne ferait pas
# échouer la résolution : elle disparaîtrait en silence, d'où la vérification de chaque montage.
CERVEAU = {"provider": "openai", "api_key": "cle-factice", "model": "gpt-4.1"}
VOIX = {"provider": "deepgram", "api_key": "cle-factice"}
TRANSCRIPTION = {"provider": "deepgram", "api_key": "cle-factice"}
TEMPS_REEL = {"provider": "openai_realtime", "api_key": "cle-factice"}
ORGANISATION_EN_TEMPS_REEL = {
    "version": 2,
    "mode": "byok",
    "byok": {"mode": "realtime", "realtime": {"realtime": TEMPS_REEL, "llm": CERVEAU}},
}
CHAINE_COMPLETE = {"llm": CERVEAU, "tts": VOIX, "stt": TRANSCRIPTION}
ORGANISATION_EN_CHAINE = {
    "version": 2,
    "mode": "byok",
    "byok": {"mode": "pipeline", "pipeline": CHAINE_COMPLETE},
}


@pytest.fixture
def appel(monkeypatch, no_disposition_mapping):
    """Un appel entrant qui sonne : le poste appelé mène à l'agent, dont une version sera liée au run."""
    montage = monter_une_connexion(monkeypatch)
    monkeypatch.setattr(ai_model_configuration, "db_client", montage.base)
    montage.base.postes[POSTE_APPELE] = SimpleNamespace(
        organization_id=ORGANISATION,
        telephony_configuration_id=CONFIGURATION_TELEPHONIE,
        inbound_workflow_id=AGENT_APPELE,
        address=POSTE_APPELE,
    )
    montage.agent = SimpleNamespace(
        id=AGENT_APPELE,
        user_id=PROPRIETAIRE,
        organization_id=ORGANISATION,
        # La colonne de configuration de l'agent, tenue à jour avec le brouillon : jamais celle de l'appel.
        workflow_configurations={},
        released_definition=SimpleNamespace(
            id=VERSION_LIEE, workflow_configurations={}
        ),
        current_definition=None,
    )
    montage.base.agents[AGENT_APPELE] = montage.agent
    _lier_la_version(montage, {})
    montage.quotas_consultes = []

    async def accorder_le_quota(
        *, workflow_id: int, organization_id: int, workflow_run_id: int
    ) -> SimpleNamespace:
        montage.quotas_consultes.append((workflow_id, organization_id, workflow_run_id))
        return SimpleNamespace(has_quota=True, error_message="")

    monkeypatch.setattr(ari_manager, "authorize_workflow_run_start", accorder_le_quota)
    # Délai du flux audio à zéro : la garde est désarmée, un appel décroché ne laisse aucune tâche de fond.
    monkeypatch.setattr(constants, "ARI_MEDIA_STREAM_TIMEOUT_SECONDS", 0)
    return montage


def _lier_la_version(appel: SimpleNamespace, configurations: dict) -> None:
    """La configuration de la version que l'appel liera à son run."""
    appel.base.versions[VERSION_LIEE] = (ORGANISATION, configurations)
    appel.agent.released_definition.workflow_configurations = configurations


async def _configuration_resolue(appel: SimpleNamespace) -> tuple[list[str], bool]:
    """Ce que la vraie résolution rend pour la version liée, avec les doublures du gestionnaire."""
    configurations = await appel.base.get_definition_configurations(
        VERSION_LIEE, organization_id=ORGANISATION
    )
    effective = (
        await ai_model_configuration.get_effective_ai_model_configuration_for_workflow(
            organization_id=ORGANISATION, workflow_configurations=configurations
        )
    )
    presentes = [nom for nom in SECTIONS if getattr(effective, nom) is not None]
    return presentes, effective.is_realtime


def _refuse_avant_le_decroche(appel: SimpleNamespace, sections_absentes: str) -> None:
    assert appel.quotas_consultes == [QUOTA_CONSULTE], (
        "le quota n'a pas été consulté pour le run : le contrôle n'a pas été atteint par le chemin normal"
    )
    assert appel.asterisk.parametres_recus(*DECROCHE) == []
    assert appel.asterisk.parametres_recus(*CREATION_DU_CANAL_MEDIA) == []
    run = appel.base.runs[RUN]
    assert (run.state, run.is_completed) == ("completed", True)
    assert run.gathered_context["error"] == REFUS + sections_absentes
    assert appel.mises_en_file == [MISE_EN_FILE_DES_INTEGRATIONS]
    assert appel.places.liberations == [("unregister_active_call", RUN)]
    assert appel.places.tenues == set()
    assert appel.asterisk.suppressions_recues() == [CANAL_APPELANT]


def _decroche(appel: SimpleNamespace) -> None:
    assert appel.quotas_consultes == [QUOTA_CONSULTE], (
        "le quota n'a pas été consulté pour le run : le contrôle n'a pas été atteint par le chemin normal"
    )
    assert len(appel.asterisk.parametres_recus(*DECROCHE)) == 1
    canal_media_demande(appel.asterisk)
    assert appel.asterisk.suppressions_recues() == []
    run = appel.base.runs[RUN]
    assert (run.state, run.is_completed) == ("initialized", False)
    assert "error" not in run.gathered_context
    assert appel.mises_en_file == []
    assert appel.places.liberations == []
    assert appel.places.tenues == {RUN}


@pytest.mark.parametrize(
    ("surcharges", "presentes", "absentes"),
    [
        pytest.param({}, [], "stt, tts, llm", id="aucune section"),
        pytest.param(
            {"tts": VOIX, "llm": CERVEAU},
            ["llm", "tts"],
            "stt",
            id="sans transcription",
        ),
        pytest.param(
            {"stt": TRANSCRIPTION, "llm": CERVEAU},
            ["llm", "stt"],
            "tts",
            id="sans voix",
        ),
        pytest.param(
            {"stt": TRANSCRIPTION, "tts": VOIX},
            ["stt", "tts"],
            "llm",
            id="sans cerveau",
        ),
    ],
)
async def test_chaine_incomplete_l_appel_est_refuse_avant_le_decroche(
    appel, surcharges, presentes, absentes
):
    _lier_la_version(appel, {"model_overrides": surcharges} if surcharges else {})
    assert await _configuration_resolue(appel) == (presentes, False)
    assert appel.base.lectures_de_la_configuration_des_modeles == [
        LECTURE_DE_L_ORGANISATION
    ]

    await appel.connexion._handle_inbound_stasis_start(
        CANAL_APPELANT, "Ring", EVENEMENT
    )

    _refuse_avant_le_decroche(appel, absentes)


async def test_temps_reel_complet_sans_transcription_ni_voix_l_appel_est_decroche(
    appel,
):
    appel.base.configurations_des_modeles[ORGANISATION] = ORGANISATION_EN_TEMPS_REEL
    assert await _configuration_resolue(appel) == (["llm", "realtime"], True)
    assert appel.base.lectures_de_la_configuration_des_modeles == [
        LECTURE_DE_L_ORGANISATION
    ]

    await appel.connexion._handle_inbound_stasis_start(
        CANAL_APPELANT, "Ring", EVENEMENT
    )

    _decroche(appel)


async def test_temps_reel_sans_cerveau_l_appel_est_refuse_avant_le_decroche(appel):
    surcharges = {"is_realtime": True, "realtime": TEMPS_REEL}
    _lier_la_version(appel, {"model_overrides": surcharges})
    assert await _configuration_resolue(appel) == (["realtime"], True)
    assert appel.base.lectures_de_la_configuration_des_modeles == [
        LECTURE_DE_L_ORGANISATION
    ]

    await appel.connexion._handle_inbound_stasis_start(
        CANAL_APPELANT, "Ring", EVENEMENT
    )

    _refuse_avant_le_decroche(appel, "llm")


async def test_temps_reel_demande_sans_section_temps_reel_la_chaine_complete_est_decrochee(
    appel,
):
    appel.base.configurations_des_modeles[ORGANISATION] = ORGANISATION_EN_CHAINE
    _lier_la_version(appel, {"model_overrides": {"is_realtime": True}})
    assert await _configuration_resolue(appel) == (["llm", "stt", "tts"], True)
    assert appel.base.lectures_de_la_configuration_des_modeles == [
        LECTURE_DE_L_ORGANISATION
    ]

    await appel.connexion._handle_inbound_stasis_start(
        CANAL_APPELANT, "Ring", EVENEMENT
    )

    _decroche(appel)


async def test_la_version_liee_a_l_appel_fait_foi_pas_l_organisation_ni_le_brouillon(
    appel,
):
    # Un remplacement complet par agent : la version liée porte toute la configuration, au
    # même format que celle d'une organisation.
    _lier_la_version(appel, {"model_configuration_v2_override": ORGANISATION_EN_CHAINE})
    assert appel.base.configurations_des_modeles == {}, (
        "l'organisation a une configuration : le test ne distinguerait plus les sources"
    )
    assert appel.agent.workflow_configurations == {}, (
        "la colonne du brouillon n'est pas vide : le test ne distinguerait plus les sources"
    )
    # Ici, et ici seulement, rien n'est affirmé sur la lecture de la configuration de
    # l'organisation : avec un remplacement complet, la résolution rend la main avant de la lire.
    assert await _configuration_resolue(appel) == (["llm", "stt", "tts"], False)

    await appel.connexion._handle_inbound_stasis_start(
        CANAL_APPELANT, "Ring", EVENEMENT
    )

    _decroche(appel)
