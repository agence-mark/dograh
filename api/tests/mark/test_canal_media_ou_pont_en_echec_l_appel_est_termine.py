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

Les doublures sont posées aux ports sortants, jamais sur la classe testée : la couche réseau vers
Asterisk (``aiohttp.ClientSession``), Redis, la base, les places d'appel et la mise en file des intégrations.
Les requêtes vues par le faux Asterisk sont donc celles que ``_ari_request`` et ``_delete_channel``
émettent réellement.

La première assertion de chaque test est un témoin du montage : sans elle, une liste de suppressions
fausse pourrait venir d'une doublure qui a fait dérailler le code avant la branche visée.
"""

import json
from collections.abc import Callable
from types import SimpleNamespace

import aiohttp
import pytest

from api.services import workflow_run_failure
from api.services.telephony import ari_manager

ORGANISATION = 1
AUTRE_ORGANISATION = 2
RUN = 123
AGENT = "42"
CANAL_APPELANT = "canal-appelant"
CANAL_MEDIA = "canal-media"
CANAL_MEDIA_INATTENDU = "canal-media-inattendu"
PONT = "pont-1"
ADRESSE_ASTERISK = "http://asterisk.test:8088"

# Ce qu'Asterisk reçoit, écrit en dur : le test ne lit aucune constante du code.
CREATION_DU_CANAL_MEDIA = ("POST", "/channels/externalMedia")
CREATION_DU_PONT = ("POST", "/bridges")
AJOUT_DES_CANAUX_AU_PONT = ("POST", f"/bridges/{PONT}/addChannel")
SUPPRESSION_DU_CANAL_APPELANT = ("DELETE", f"/channels/{CANAL_APPELANT}")
REFUS = (500, "Allocation failed")
SUCCES_SANS_CORPS = (204, "")

# Ce qui est écrit sur le run et mis en file, écrit en dur pour la même raison.
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
MISE_EN_FILE_DES_INTEGRATIONS = ("run_integrations_post_workflow_run", RUN)


class _FausseReponse:
    def __init__(self, statut: int, corps: str) -> None:
        self.status = statut
        self._corps = corps

    async def text(self) -> str:
        return self._corps


class _FauxEchange:
    """Ce qu'ouvre ``async with session.request(...)`` : la réponse d'Asterisk à une requête."""

    def __init__(self, reponse: _FausseReponse) -> None:
        self._reponse = reponse

    async def __aenter__(self) -> _FausseReponse:
        return self._reponse

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _EchangeEnPanne:
    """Une requête qui n'aboutit pas : la panne de liaison se lève à l'ouverture, comme avec aiohttp."""

    def __init__(self, panne: Exception) -> None:
        self._panne = panne

    async def __aenter__(self) -> _FausseReponse:
        raise self._panne

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FausseSession:
    def __init__(self, asterisk: "_FauxAsterisk") -> None:
        self._asterisk = asterisk

    async def __aenter__(self) -> "_FausseSession":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def request(
        self, methode: str, url: str, *, auth: object, **options: object
    ) -> "_FauxEchange | _EchangeEnPanne":
        return self._asterisk.recevoir(methode, url, dict(options.get("params") or {}))

    def delete(self, url: str, *, auth: object) -> "_FauxEchange | _EchangeEnPanne":
        return self._asterisk.recevoir("DELETE", url, {})


class _FauxAsterisk:
    """Asterisk vu par sa couche réseau : garde chaque requête reçue, répond par un succès sauf scénario."""

    def __init__(self) -> None:
        self.requetes: list[tuple[str, str, dict]] = []
        # Par requête : une réponse (statut, corps), ou une panne de liaison qui se lève.
        self.reponses: dict[tuple[str, str], tuple[int, str] | Exception] = {}
        # Ce que le test veut relever à l'instant où chaque requête est reçue (l'état du run, par exemple).
        self.observer: Callable[[], object] | None = None
        self.observations: list[tuple[str, str, object]] = []
        # Une panne de liaison : toute requête est notée comme tentée, puis lève.
        self.panne: Exception | None = None

    def session(self) -> _FausseSession:
        return _FausseSession(self)

    def recevoir(
        self, methode: str, url: str, parametres: dict
    ) -> _FauxEchange | _EchangeEnPanne:
        prefixe = f"{ADRESSE_ASTERISK}/ari"
        assert url.startswith(prefixe), (
            f"requête partie ailleurs que vers Asterisk : {url}"
        )
        chemin = url.removeprefix(prefixe)
        self.requetes.append((methode, chemin, parametres))
        if self.observer is not None:
            self.observations.append((methode, chemin, self.observer()))
        if self.panne is not None:
            return _EchangeEnPanne(self.panne)
        reponse = self.reponses.get((methode, chemin), SUCCES_SANS_CORPS)
        if isinstance(reponse, Exception):
            return _EchangeEnPanne(reponse)
        return _FauxEchange(_FausseReponse(*reponse))

    def parametres_recus(self, methode: str, chemin: str) -> list[dict]:
        return [
            parametres
            for m, c, parametres in self.requetes
            if (m, c) == (methode, chemin)
        ]

    def observations_a(self, methode: str, chemin: str) -> list[object]:
        return [
            releve for m, c, releve in self.observations if (m, c) == (methode, chemin)
        ]

    def suppressions_recues(self) -> list[str]:
        prefixe = "/channels/"
        return [
            c.removeprefix(prefixe)
            for m, c, _ in self.requetes
            if m == "DELETE" and c.startswith(prefixe)
        ]


class _FauxRedis:
    def __init__(self) -> None:
        self.cles: dict[str, str] = {}

    async def set(self, cle: str, valeur: str, *, ex: int) -> None:
        self.cles[cle] = valeur

    async def getdel(self, cle: str) -> str | None:
        return self.cles.pop(cle, None)


class _FausseBase:
    """Les runs dans un dictionnaire. Une écriture fusionne les dictionnaires par clé, comme la vraie.

    La seule lecture d'un run qu'elle expose est la lecture bornée à une organisation : un code qui
    lirait le run sans borne tomberait sur une méthode absente.
    """

    def __init__(self, *runs: SimpleNamespace) -> None:
        self.runs = {run.id: run for run in runs}
        self.ecritures: list[tuple[int, dict]] = []
        # Une base qui refuse d'écrire : chaque écriture est notée comme refusée, puis lève.
        self.panne_a_l_ecriture: Exception | None = None
        self.ecritures_refusees: list[tuple[int, dict]] = []

    async def get_workflow_run(
        self, run_id: int, *, organization_id: int
    ) -> SimpleNamespace | None:
        run = self.runs.get(run_id)
        if run is None or run.workflow.organization_id != organization_id:
            return None
        return run

    async def update_workflow_run(self, run_id: int, **modifications: object) -> None:
        if self.panne_a_l_ecriture is not None:
            self.ecritures_refusees.append((run_id, modifications))
            raise self.panne_a_l_ecriture
        self.ecritures.append((run_id, modifications))
        run = self.runs[run_id]
        for nom, valeur in modifications.items():
            if isinstance(valeur, dict):
                getattr(run, nom).update(valeur)
            else:
                setattr(run, nom, valeur)

    async def get_organization_id_by_workflow_run_id(self, run_id: int) -> int:
        return self.runs[run_id].workflow.organization_id


class _FaussesPlaces:
    """Les runs qui tiennent une place d'appel. « La place est rendue » se lit sur cet ensemble."""

    def __init__(self, *runs: int) -> None:
        self.tenues = set(runs)

    async def unregister_active_call(self, workflow_run_id: int) -> bool:
        if workflow_run_id not in self.tenues:
            return False
        self.tenues.remove(workflow_run_id)
        return True


@pytest.fixture
def appel(monkeypatch, no_disposition_mapping):
    """Un appel décroché dont le flux audio n'a pas commencé, face à un faux Asterisk."""
    asterisk = _FauxAsterisk()
    monkeypatch.setattr(ari_manager.aiohttp, "ClientSession", asterisk.session)
    run = SimpleNamespace(
        id=RUN,
        workflow=SimpleNamespace(organization_id=ORGANISATION),
        call_type="inbound",
        state="initialized",
        is_completed=False,
        gathered_context={},
        usage_info={},
        logs={},
    )
    base = _FausseBase(run)
    monkeypatch.setattr(ari_manager, "db_client", base)
    monkeypatch.setattr(workflow_run_failure, "db_client", base)
    mises_en_file: list[tuple] = []

    async def mettre_en_file(nom: str, *arguments: object) -> None:
        mises_en_file.append((nom, *arguments))

    monkeypatch.setattr("api.tasks.arq.enqueue_job", mettre_en_file)
    places = _FaussesPlaces(RUN)
    monkeypatch.setattr(ari_manager, "call_concurrency", places)
    connexion = ari_manager.ARIConnection(
        organization_id=ORGANISATION,
        telephony_configuration_id=10,
        ari_endpoint=ADRESSE_ASTERISK,
        app_name="application-factice",
        app_password="factice",
        ws_client_name="liaison-factice",
    )
    connexion._redis_client = _FauxRedis()
    return SimpleNamespace(
        connexion=connexion,
        asterisk=asterisk,
        run=run,
        base=base,
        mises_en_file=mises_en_file,
        places=places,
    )


def _canal_media_demande(asterisk: _FauxAsterisk) -> str:
    """Témoin du montage : la demande de création du canal média est arrivée jusqu'à Asterisk, une fois."""
    creations = asterisk.parametres_recus(*CREATION_DU_CANAL_MEDIA)
    assert len(creations) == 1, (
        f"{len(creations)} demande(s) de création du canal média : le montage n'a pas atteint la branche visée"
    )
    return creations[0]["channelId"]


def _seule_ecriture_de_l_amont(canal_media: str) -> list[tuple[int, dict]]:
    """L'écriture que l'amont fait avant de demander le canal média : les identifiants des canaux.

    Un test qui attend exactement cette liste affirme que le geste, lui, n'a rien écrit sur le run.
    """
    canaux = {"ext_channel_id": canal_media, "call_id": CANAL_APPELANT}
    return [(RUN, {"gathered_context": canaux})]


async def _relier_les_canaux(appel: SimpleNamespace) -> None:
    """Ce que déclenche l'entrée du canal média dans l'application : la mise en place du pont."""
    en_attente = {"caller_channel_id": CANAL_APPELANT, "workflow_run_id": str(RUN)}
    await appel.connexion._complete_bridge_after_ext_ready(CANAL_MEDIA, en_attente)


def _pont_demande(asterisk: _FauxAsterisk) -> None:
    """Témoin du montage : la demande de création du pont est arrivée jusqu'à Asterisk, une fois."""
    creations = asterisk.parametres_recus(*CREATION_DU_PONT)
    assert len(creations) == 1, (
        f"{len(creations)} demande(s) de création du pont : le montage n'a pas atteint la branche visée"
    )


async def test_canal_media_refuse_l_appelant_est_raccroche(appel):
    appel.asterisk.reponses[CREATION_DU_CANAL_MEDIA] = REFUS

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    canal_media = _canal_media_demande(appel.asterisk)
    assert appel.asterisk.suppressions_recues() == [canal_media, CANAL_APPELANT]


async def test_canal_media_refuse_le_run_est_ferme_avant_le_raccrochage(appel):
    appel.asterisk.reponses[CREATION_DU_CANAL_MEDIA] = REFUS
    appel.asterisk.observer = lambda: appel.run.state

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    _canal_media_demande(appel.asterisk)
    assert (appel.run.state, appel.run.is_completed) == ("completed", True)
    assert appel.run.gathered_context["error"] == ERREUR_CANAL_MEDIA_REFUSE
    assert appel.mises_en_file == [MISE_EN_FILE_DES_INTEGRATIONS]
    etats_au_raccrochage = appel.asterisk.observations_a(*SUPPRESSION_DU_CANAL_APPELANT)
    assert etats_au_raccrochage == ["completed"]


async def test_canal_media_refuse_la_place_est_rendue(appel):
    appel.asterisk.reponses[CREATION_DU_CANAL_MEDIA] = REFUS
    appel.asterisk.observer = lambda: set(appel.places.tenues)

    await appel.connexion._handle_stasis_start(CANAL_APPELANT, "Up", str(RUN), AGENT)

    canal_media = _canal_media_demande(appel.asterisk)
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

    canal_media = _canal_media_demande(appel.asterisk)
    assert appel.base.ecritures == _seule_ecriture_de_l_amont(canal_media)
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

    canal_media = _canal_media_demande(appel.asterisk)
    assert appel.base.ecritures == _seule_ecriture_de_l_amont(canal_media)
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

    canal_media = _canal_media_demande(appel.asterisk)
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

    canal_media = _canal_media_demande(appel.asterisk)
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
