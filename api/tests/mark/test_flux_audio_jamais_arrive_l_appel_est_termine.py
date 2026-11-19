"""[.mark] Flux audio qui n'arrive jamais après la création du canal média : l'appel est terminé après un délai réglable.

| Test | Ce qu'il prouve |
|---|---|
| flux audio jamais arrivé | quand le canal média est créé et que le run est encore ``initialized`` au bout du délai, l'appel est terminé comme pour un canal média en échec ; le délai par défaut est de 10 secondes, et rien n'est fait avant la fin de l'attente |
| run d'une autre organisation | quand la lecture du run bornée à l'organisation de la connexion ne rend rien au bout du délai, la garde n'a aucun signal et ne fait rien : ni suppression de canal, ni place rendue, ni écriture (à la différence d'un canal média en échec, où l'échec est certain et les canaux sont supprimés) |
| flux audio arrivé avant le délai | quand le run est passé à ``running`` pendant l'attente (ce que fait la route à l'arrivée du flux), ou qu'il est déjà ``completed``, l'appel est laissé tel quel : aucune suppression, place toujours tenue, run inchangé |
| le délai est celui du réglage | la durée demandée à l'attente est exactement la valeur du réglage, lue au moment de l'appel et non écrite en dur |
| délai nul ou négatif | la garde est désarmée : aucune tâche n'est créée, aucune attente n'est demandée, l'appel n'est pas touché (garde : verte sur le code d'avant, rouge contre une garde armée quel que soit le délai, qui raccrocherait tout appel à l'instant) |
| garde finie | une garde qui a fini n'est plus tenue par la connexion : l'ensemble des gardes ne grossit pas d'une tâche morte par appel |
| arrêt de la connexion | une garde encore dans son attente est annulée par ``stop()``, qui l'attend avant de rendre la main : aucune tâche de fond ne survit à la connexion, et l'appel n'est pas touché |
| sans attente injectée | avec l'attente que la connexion porte par défaut et un délai réel de 0,01 s, l'appel dont le flux n'arrive pas est bien terminé : la garde fonctionne sans la doublure des autres tests (garde : verte dès l'écriture, rouge prouvé par le mutant « l'attente par défaut ne rend jamais la main ») |

Aucun délai réel, sauf dans le dernier test : l'attente est celle que la connexion porte dans un attribut,
remplacée ici par une fausse attente qui note la durée demandée et rend la main tout de suite.
``asyncio.sleep`` n'est remplacé pour personne d'autre. Le dernier test ne remplace rien et attend
réellement un centième de seconde : sans lui, casser l'attente par défaut rendrait la garde inopérante en
production sans faire rougir aucun test.

Les noms que le code donne au réglage et à l'ensemble de ses gardes sont lus par ``getattr`` et posés
avec ``raising=False`` : joué sur un code qui ne les connaît pas, un test échoue sur son assertion
(aucune attente demandée, aucune garde armée) et jamais sur un nom absent.
"""

import asyncio
import os
from collections.abc import Callable

import pytest

from api import constants
from api.tests.mark.telephonie_commun import (
    AGENT,
    AUTRE_ORGANISATION,
    CANAL_APPELANT,
    MISE_EN_FILE_DES_INTEGRATIONS,
    RUN,
    canal_media_demande,
    monter_un_appel,
    seule_ecriture_de_l_amont,
)

# Écrits en dur : le test ne lit aucune constante du code.
REGLAGE = "ARI_MEDIA_STREAM_TIMEOUT_SECONDS"
GARDES = "_gardes_du_flux_audio"
DELAI_PAR_DEFAUT_S = 10
# Sous une seconde, exprès : tout délai strictement positif arme la garde, même très court.
DELAI_REGLE_S = 0.5
# Le seul délai réellement attendu de ce fichier : celui du test qui garde l'attente par défaut.
DELAI_REEL_TRES_COURT_S = 0.01
ERREUR_FLUX_AUDIO_JAMAIS_ARRIVE = (
    "Call setup failed: the audio stream did not arrive in time"
)
# Garde-fou des tests eux-mêmes : une garde qui ne finirait pas fait échouer le test au lieu de le figer.
ECHEANCE_DU_TEST_S = 2


class _FausseAttente:
    """L'attente injectée dans la connexion : note la durée demandée et rend la main tout de suite."""

    def __init__(self) -> None:
        self.durees: list[float] = []
        # Ce que le test veut relever, ou faire arriver, à l'instant où l'attente est demandée.
        self.pendant: Callable[[], object] | None = None
        self.releves: list[object] = []
        # Une attente qui ne rend jamais la main : la garde y reste jusqu'à son annulation.
        self.sans_fin = False
        self.demandee = asyncio.Event()

    async def __call__(self, duree: float) -> None:
        self.durees.append(duree)
        self.demandee.set()
        if self.pendant is not None:
            self.releves.append(self.pendant())
        if self.sans_fin:
            await asyncio.Event().wait()


@pytest.fixture
def appel_sans_attente_injectee(monkeypatch, no_disposition_mapping):
    """Un appel dont Asterisk crée le canal média. L'attente est celle que la connexion porte par défaut."""
    assert REGLAGE not in os.environ, (
        f"{REGLAGE} est posée dans l'environnement des tests : le délai par défaut ne serait pas celui du code"
    )
    montage = monter_un_appel(monkeypatch)
    yield montage
    for garde in list(getattr(montage.connexion, GARDES, ())):
        garde.cancel()


@pytest.fixture
def appel(appel_sans_attente_injectee):
    """Le même appel, avec une attente injectée qui ne dure pas."""
    montage = appel_sans_attente_injectee
    montage.attente = _FausseAttente()
    montage.connexion._attendre = montage.attente
    return montage


async def _laisser_finir_les_gardes(connexion: object) -> list[asyncio.Task]:
    """Rend les gardes que la connexion tient, après les avoir laissées finir."""
    gardes = list(getattr(connexion, GARDES, ()))
    if gardes:
        await asyncio.wait_for(asyncio.gather(*gardes), timeout=ECHEANCE_DU_TEST_S)
    return gardes


async def test_flux_audio_jamais_arrive_l_appel_est_termine_apres_le_delai(appel):
    appel.attente.pendant = lambda: (
        appel.asterisk.suppressions_recues(),
        set(appel.places.tenues),
    )

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)
    await _laisser_finir_les_gardes(appel.connexion)

    canal_media = canal_media_demande(appel.asterisk)
    assert appel.attente.durees == [DELAI_PAR_DEFAUT_S]
    assert appel.attente.releves == [([], {RUN})], (
        "quelque chose a été fait avant la fin de l'attente"
    )
    assert appel.asterisk.suppressions_recues() == [canal_media, CANAL_APPELANT]
    assert (appel.run.state, appel.run.is_completed) == ("completed", True)
    assert appel.run.gathered_context["error"] == ERREUR_FLUX_AUDIO_JAMAIS_ARRIVE
    assert appel.mises_en_file == [MISE_EN_FILE_DES_INTEGRATIONS]
    assert appel.places.tenues == set()


async def test_run_d_une_autre_organisation_la_garde_ne_fait_rien(appel):
    appel.run.workflow.organization_id = AUTRE_ORGANISATION

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)
    await _laisser_finir_les_gardes(appel.connexion)

    canal_media = canal_media_demande(appel.asterisk)
    assert len(appel.attente.durees) == 1, (
        "la garde n'a pas attendu : le test ne prouverait rien"
    )
    assert appel.asterisk.suppressions_recues() == []
    assert appel.places.tenues == {RUN}
    assert appel.base.ecritures == seule_ecriture_de_l_amont(canal_media)
    assert appel.mises_en_file == []


@pytest.mark.parametrize(("etat", "termine"), [("running", False), ("completed", True)])
async def test_flux_audio_arrive_avant_le_delai_l_appel_est_laisse_tel_quel(
    appel, etat, termine
):
    def le_flux_arrive() -> None:
        appel.run.state = etat
        appel.run.is_completed = termine

    appel.attente.pendant = le_flux_arrive

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)
    await _laisser_finir_les_gardes(appel.connexion)

    canal_media = canal_media_demande(appel.asterisk)
    assert len(appel.attente.durees) == 1, (
        "la garde n'a pas attendu : le test ne prouverait rien"
    )
    assert appel.asterisk.suppressions_recues() == []
    assert appel.places.tenues == {RUN}
    assert appel.base.ecritures == seule_ecriture_de_l_amont(canal_media)
    assert (appel.run.state, appel.run.is_completed) == (etat, termine)
    assert appel.mises_en_file == []


async def test_le_delai_d_attente_du_flux_est_celui_du_reglage(appel, monkeypatch):
    monkeypatch.setattr(constants, REGLAGE, DELAI_REGLE_S, raising=False)

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)
    await _laisser_finir_les_gardes(appel.connexion)

    canal_media_demande(appel.asterisk)
    assert appel.attente.durees == [DELAI_REGLE_S]


@pytest.mark.parametrize("delai", [0, -1])
async def test_un_delai_nul_ou_negatif_desarme_la_garde(appel, monkeypatch, delai):
    monkeypatch.setattr(constants, REGLAGE, delai, raising=False)

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)
    gardes = await _laisser_finir_les_gardes(appel.connexion)

    canal_media = canal_media_demande(appel.asterisk)
    assert gardes == []
    assert appel.attente.durees == []
    assert appel.asterisk.suppressions_recues() == []
    assert appel.places.tenues == {RUN}
    assert appel.base.ecritures == seule_ecriture_de_l_amont(canal_media)
    assert appel.mises_en_file == []


async def test_une_garde_finie_n_est_plus_tenue_par_la_connexion(appel):
    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)
    gardes = await _laisser_finir_les_gardes(appel.connexion)

    canal_media_demande(appel.asterisk)
    assert len(gardes) == 1, "aucune garde n'a été armée : le test ne prouverait rien"
    assert set(getattr(appel.connexion, GARDES, ())) == set()


async def test_l_arret_de_la_connexion_annule_les_gardes_en_attente(appel):
    appel.attente.sans_fin = True

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)
    gardes = list(getattr(appel.connexion, GARDES, ()))
    assert len(gardes) == 1, "aucune garde n'a été armée : le test ne prouverait rien"
    # La garde est entrée dans son attente, et elle y reste.
    await asyncio.wait_for(appel.attente.demandee.wait(), timeout=ECHEANCE_DU_TEST_S)

    # Borné : un arrêt qui attendrait une garde sans l'avoir annulée ne finirait jamais.
    await asyncio.wait_for(appel.connexion.stop(), timeout=ECHEANCE_DU_TEST_S)

    canal_media = canal_media_demande(appel.asterisk)
    assert gardes[0].cancelled()
    assert set(getattr(appel.connexion, GARDES, ())) == set()
    assert appel.asterisk.suppressions_recues() == []
    assert appel.places.tenues == {RUN}
    assert appel.base.ecritures == seule_ecriture_de_l_amont(canal_media)
    assert appel.mises_en_file == []


async def test_sans_attente_injectee_l_appel_est_termine_apres_un_delai_reel(
    appel_sans_attente_injectee, monkeypatch
):
    appel = appel_sans_attente_injectee
    monkeypatch.setattr(constants, REGLAGE, DELAI_REEL_TRES_COURT_S, raising=False)

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)
    gardes = list(getattr(appel.connexion, GARDES, ()))
    assert len(gardes) == 1, "aucune garde n'a été armée : le test ne prouverait rien"
    # Borné, et sans lever : une garde qui ne finit pas fait échouer l'assertion qui suit.
    _, encore_en_attente = await asyncio.wait(gardes, timeout=ECHEANCE_DU_TEST_S)

    canal_media = canal_media_demande(appel.asterisk)
    assert not encore_en_attente, (
        "la garde n'a pas fini : l'attente par défaut de la connexion ne rend pas la main"
    )
    assert appel.asterisk.suppressions_recues() == [canal_media, CANAL_APPELANT]
    assert (appel.run.state, appel.run.is_completed) == ("completed", True)
    assert appel.run.gathered_context["error"] == ERREUR_FLUX_AUDIO_JAMAIS_ARRIVE
    assert appel.mises_en_file == [MISE_EN_FILE_DES_INTEGRATIONS]
    assert appel.places.tenues == set()
