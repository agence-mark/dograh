"""[.mark] Canal média ou pont en échec pendant la mise en place d'un appel Asterisk : l'appel est terminé.

| Test | Ce qu'il prouve |
|---|---|
| canal média refusé, l'appelant est raccroché | quand Asterisk refuse de créer le canal média, le canal média demandé puis le canal de l'appelant sont supprimés, dans cet ordre et rien d'autre |
| canal média refusé, le run est fermé avant le raccrochage | le run entrant encore ``initialized`` est fermé par la vraie ``mark_workflow_run_failed`` avec son erreur, une seule mise en file des intégrations, et il est déjà fermé quand Asterisk reçoit la suppression du canal de l'appelant |
| canal média refusé, la place est rendue | la place d'appel du run est rendue, et elle l'est déjà quand Asterisk reçoit la première suppression : elle n'attend ni un événement d'Asterisk ni la réponse d'un Asterisk lent |
| run d'une autre organisation | quand la lecture du run bornée à l'organisation de la connexion ne rend rien, le geste n'écrit rien sur le run, ne met rien en file et ne rend pas sa place : seuls les canaux de la connexion sont supprimés |
| appel sortant | les canaux sont supprimés et la place rendue, mais le run sortant n'est ni fermé ni mis en file : sa clôture passerait par la comptabilité des campagnes, hors de ce geste |
| identifiant inattendu | quand Asterisk crée le canal média sous un autre identifiant que celui demandé, ce canal-là est supprimé aussi (le run ne le connaît pas, rien d'autre ne le supprimerait), le run est fermé avec sa propre erreur et la place rendue |
| Asterisk injoignable | quand toute requête vers Asterisk lève, suppressions comprises, le run est quand même fermé une seule fois et la place rendue, les deux suppressions sont quand même tentées, et aucune exception ne sort de la mise en place |
| pont refusé | quand Asterisk refuse de créer le pont, le canal média puis le canal de l'appelant sont supprimés, le run est fermé avec sa propre erreur, une seule mise en file, et la place rendue |
| pont refusé alors que le flux est arrivé | un run déjà ``running`` ou déjà ``completed`` n'est pas écrit du tout (c'est le pipeline qui porte sa clôture), rien n'est mis en file, mais les canaux sont supprimés et la place rendue |
| création du pont interrompue | quand la demande de création du pont lève une panne de liaison, l'appel est terminé comme pour un pont refusé, avec sa propre erreur |
| pont établi, identifiant non enregistré | quand le pont existe et que seule l'écriture de son identifiant sur le run échoue, l'appel est gardé : aucune suppression, run inchangé, place toujours tenue (garde : verte sur le code d'origine, rouge contre un geste posé dans le ``except`` large de la mise en place du pont) |

Les doublures (``telephonie_commun.py``) sont posées aux ports sortants, jamais sur la classe testée :
la couche réseau vers Asterisk (``aiohttp.ClientSession``), Redis, la base, les places d'appel et la mise
en file des intégrations. Les requêtes vues par le faux Asterisk sont donc celles que ``_ari_request`` et
``_delete_channel`` émettent réellement.

La première assertion de chaque test est un témoin du montage : sans elle, une liste de suppressions
fausse pourrait venir d'une doublure qui a fait dérailler le code avant la branche visée.
"""

import json
from types import SimpleNamespace

import aiohttp
import pytest

from api.tests.mark.telephonie_commun import (
    AGENT,
    AUTRE_ORGANISATION,
    CANAL_APPELANT,
    CREATION_DU_CANAL_MEDIA,
    MISE_EN_FILE_DES_INTEGRATIONS,
    RUN,
    FauxAsterisk,
    canal_media_demande,
    monter_un_appel,
    seule_ecriture_de_l_amont,
)

CANAL_MEDIA = "canal-media"
CANAL_MEDIA_INATTENDU = "canal-media-inattendu"
PONT = "pont-1"

# Ce qu'Asterisk reçoit, écrit en dur : le test ne lit aucune constante du code.
CREATION_DU_PONT = ("POST", "/bridges")
AJOUT_DES_CANAUX_AU_PONT = ("POST", f"/bridges/{PONT}/addChannel")
SUPPRESSION_DU_CANAL_APPELANT = ("DELETE", f"/channels/{CANAL_APPELANT}")
REFUS = (500, "Allocation failed")

# Ce qui est écrit sur le run, écrit en dur pour la même raison.
ERREUR_CANAL_MEDIA_REFUSE = (
    "Call setup failed: Asterisk did not create the media channel"
)
ERREUR_IDENTIFIANT_INATTENDU = (
    "Call setup failed: Asterisk created the media channel under an unexpected id"
)
ERREUR_MISE_EN_PLACE_INTERROMPUE = (
    "Call setup failed: the media channel setup was interrupted by an error"
)
ERREUR_PONT_REFUSE = "Call setup failed: Asterisk did not create the bridge"
ERREUR_PONT_INTERROMPU = (
    "Call setup failed: the bridge creation was interrupted by an error"
)


@pytest.fixture
def appel(monkeypatch, no_disposition_mapping):
    """Un appel décroché dont le flux audio n'a pas commencé, face à un faux Asterisk."""
    return monter_un_appel(monkeypatch)


async def _relier_les_canaux(appel: SimpleNamespace) -> None:
    """Ce que déclenche l'entrée du canal média dans l'application : la mise en place du pont."""
    en_attente = {"caller_channel_id": CANAL_APPELANT, "workflow_run_id": str(RUN)}
    await appel.connexion._complete_bridge_after_ext_ready(CANAL_MEDIA, en_attente)


def _pont_demande(asterisk: FauxAsterisk) -> None:
    """Témoin du montage : la demande de création du pont est arrivée jusqu'à Asterisk, une fois."""
    creations = asterisk.parametres_recus(*CREATION_DU_PONT)
    assert len(creations) == 1, (
        f"{len(creations)} demande(s) de création du pont : le montage n'a pas atteint la branche visée"
    )


async def test_canal_media_refuse_l_appelant_est_raccroche(appel):
    appel.asterisk.reponses[CREATION_DU_CANAL_MEDIA] = REFUS

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    canal_media = canal_media_demande(appel.asterisk)
    assert appel.asterisk.suppressions_recues() == [canal_media, CANAL_APPELANT]


async def test_canal_media_refuse_le_run_est_ferme_avant_le_raccrochage(appel):
    appel.asterisk.reponses[CREATION_DU_CANAL_MEDIA] = REFUS
    appel.asterisk.observer = lambda: appel.run.state

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    canal_media_demande(appel.asterisk)
    assert (appel.run.state, appel.run.is_completed) == ("completed", True)
    assert appel.run.gathered_context["error"] == ERREUR_CANAL_MEDIA_REFUSE
    assert appel.mises_en_file == [MISE_EN_FILE_DES_INTEGRATIONS]
    etats_au_raccrochage = appel.asterisk.observations_a(*SUPPRESSION_DU_CANAL_APPELANT)
    assert etats_au_raccrochage == ["completed"]


async def test_canal_media_refuse_la_place_est_rendue(appel):
    appel.asterisk.reponses[CREATION_DU_CANAL_MEDIA] = REFUS
    appel.asterisk.observer = lambda: set(appel.places.tenues)

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    canal_media = canal_media_demande(appel.asterisk)
    places_a_l_echec = appel.asterisk.observations_a(*CREATION_DU_CANAL_MEDIA)
    assert places_a_l_echec == [{RUN}], (
        "le run ne tenait pas de place au moment de l'échec : le test ne prouverait rien"
    )
    assert appel.places.tenues == set()
    premiere_suppression = ("DELETE", f"/channels/{canal_media}")
    assert appel.asterisk.observations_a(*premiere_suppression) == [set()]


async def test_run_d_une_autre_organisation_seuls_les_canaux_sont_supprimes(appel):
    appel.run.workflow.organization_id = AUTRE_ORGANISATION
    appel.asterisk.reponses[CREATION_DU_CANAL_MEDIA] = REFUS

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    canal_media = canal_media_demande(appel.asterisk)
    assert appel.base.ecritures == seule_ecriture_de_l_amont(canal_media)
    assert (appel.run.state, appel.run.is_completed) == ("initialized", False)
    assert appel.mises_en_file == []
    assert appel.places.tenues == {RUN}
    assert appel.asterisk.suppressions_recues() == [canal_media, CANAL_APPELANT]


async def test_appel_sortant_le_canal_et_la_place_sont_rendus_le_run_est_laisse_tel_quel(
    appel,
):
    appel.run.call_type = "outbound"
    appel.asterisk.reponses[CREATION_DU_CANAL_MEDIA] = REFUS

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    canal_media = canal_media_demande(appel.asterisk)
    assert appel.base.ecritures == seule_ecriture_de_l_amont(canal_media)
    assert (appel.run.state, appel.run.is_completed) == ("initialized", False)
    assert appel.mises_en_file == []
    assert appel.places.tenues == set()
    assert appel.asterisk.suppressions_recues() == [canal_media, CANAL_APPELANT]


async def test_identifiant_inattendu_l_appel_est_termine_et_le_canal_media_cree_est_supprime(
    appel,
):
    appel.asterisk.reponses[CREATION_DU_CANAL_MEDIA] = (
        200,
        json.dumps({"id": CANAL_MEDIA_INATTENDU}),
    )

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    canal_media = canal_media_demande(appel.asterisk)
    assert appel.asterisk.suppressions_recues() == [
        canal_media,
        CANAL_MEDIA_INATTENDU,
        CANAL_APPELANT,
    ]
    assert (appel.run.state, appel.run.is_completed) == ("completed", True)
    assert appel.run.gathered_context["error"] == ERREUR_IDENTIFIANT_INATTENDU
    assert appel.mises_en_file == [MISE_EN_FILE_DES_INTEGRATIONS]
    assert appel.places.tenues == set()


async def test_asterisk_injoignable_pendant_la_mise_en_place_le_run_est_ferme_et_la_place_rendue(
    appel,
):
    appel.asterisk.panne = aiohttp.ClientConnectionError("Asterisk injoignable")

    # Aucune exception ne doit sortir d'ici : elle remonterait jusqu'à l'accueil de l'appel entrant,
    # qui fermerait le run une seconde fois.
    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    canal_media = canal_media_demande(appel.asterisk)
    assert appel.asterisk.suppressions_recues() == [canal_media, CANAL_APPELANT]
    assert (appel.run.state, appel.run.is_completed) == ("completed", True)
    assert appel.run.gathered_context["error"] == ERREUR_MISE_EN_PLACE_INTERROMPUE
    assert appel.mises_en_file == [MISE_EN_FILE_DES_INTEGRATIONS]
    assert appel.places.tenues == set()


async def test_pont_refuse_l_appel_est_termine_et_le_canal_media_supprime(appel):
    appel.asterisk.reponses[CREATION_DU_PONT] = REFUS

    await _relier_les_canaux(appel)

    _pont_demande(appel.asterisk)
    assert appel.asterisk.suppressions_recues() == [CANAL_MEDIA, CANAL_APPELANT]
    assert (appel.run.state, appel.run.is_completed) == ("completed", True)
    assert appel.run.gathered_context["error"] == ERREUR_PONT_REFUSE
    assert appel.mises_en_file == [MISE_EN_FILE_DES_INTEGRATIONS]
    assert appel.places.tenues == set()


@pytest.mark.parametrize(("etat", "termine"), [("running", False), ("completed", True)])
async def test_pont_refuse_alors_que_le_flux_est_arrive_le_run_est_laisse_au_pipeline(
    appel, etat, termine
):
    appel.run.state = etat
    appel.run.is_completed = termine
    appel.asterisk.reponses[CREATION_DU_PONT] = REFUS

    await _relier_les_canaux(appel)

    _pont_demande(appel.asterisk)
    assert appel.base.ecritures == []
    assert (appel.run.state, appel.run.is_completed) == (etat, termine)
    assert appel.mises_en_file == []
    assert appel.places.tenues == set()
    assert appel.asterisk.suppressions_recues() == [CANAL_MEDIA, CANAL_APPELANT]


async def test_creation_du_pont_interrompue_l_appel_est_termine(appel):
    appel.asterisk.reponses[CREATION_DU_PONT] = aiohttp.ClientConnectionError(
        "liaison coupée"
    )

    await _relier_les_canaux(appel)

    _pont_demande(appel.asterisk)
    assert appel.asterisk.suppressions_recues() == [CANAL_MEDIA, CANAL_APPELANT]
    assert (appel.run.state, appel.run.is_completed) == ("completed", True)
    assert appel.run.gathered_context["error"] == ERREUR_PONT_INTERROMPU
    assert appel.mises_en_file == [MISE_EN_FILE_DES_INTEGRATIONS]
    assert appel.places.tenues == set()


async def test_pont_etabli_mais_identifiant_non_enregistre_l_appel_est_garde(appel):
    appel.asterisk.reponses[CREATION_DU_PONT] = (200, json.dumps({"id": PONT}))
    appel.base.panne_a_l_ecriture = RuntimeError("écriture refusée")

    await _relier_les_canaux(appel)

    _pont_demande(appel.asterisk)
    canaux_relies = appel.asterisk.parametres_recus(*AJOUT_DES_CANAUX_AU_PONT)
    assert canaux_relies == [{"channel": f"{CANAL_APPELANT},{CANAL_MEDIA}"}], (
        "les deux canaux n'ont pas été ajoutés au pont : le test ne prouverait rien"
    )
    assert appel.asterisk.suppressions_recues() == []
    # La seule écriture tentée est celle de l'identifiant du pont, et elle a été refusée :
    # le geste n'a donc rien tenté d'écrire sur le run.
    identifiant_du_pont = {"ext_channel_id": CANAL_MEDIA, "bridge_id": PONT}
    assert appel.base.ecritures_refusees == [
        (RUN, {"gathered_context": identifiant_du_pont})
    ]
    assert (appel.run.state, appel.run.is_completed) == ("initialized", False)
    assert appel.mises_en_file == []
    assert appel.places.tenues == {RUN}
