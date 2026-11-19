"""[.mark] Doublures communes des tests du gestionnaire Asterisk (chantier ``telephonie-mark``).

Elles se posent aux ports sortants, jamais sur la classe testée : la couche réseau vers Asterisk
(``aiohttp.ClientSession``), Redis, la base et les places d'appel. Les requêtes vues par le faux
Asterisk sont donc celles que ``_ari_request`` et ``_delete_channel`` émettent réellement.

Écrites à la main, sans ``MagicMock`` : une doublure qui a un comportement peut être fausse, donc
elle apprend quelque chose.
"""

import json
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from api.services import workflow_run_failure
from api.services.telephony import ari_manager

ORGANISATION = 1
AUTRE_ORGANISATION = 2
RUN = 123
AGENT = "42"
CANAL_APPELANT = "canal-appelant"
CONFIGURATION_TELEPHONIE = 10
ADRESSE_ASTERISK = "http://asterisk.test:8088"

# Ce qu'Asterisk reçoit et répond, et ce qui est mis en file, écrits en dur : les tests ne lisent
# aucune constante du code.
CREATION_DU_CANAL_MEDIA = ("POST", "/channels/externalMedia")
SUCCES_SANS_CORPS = (204, "")
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
    def __init__(self, asterisk: "FauxAsterisk") -> None:
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


class FauxAsterisk:
    """Asterisk vu par sa couche réseau : garde chaque requête reçue, répond comme un Asterisk sain sauf scénario."""

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
        reponse = self.reponses.get((methode, chemin))
        if reponse is None:
            reponse = self._reponse_saine(methode, chemin, parametres)
        if isinstance(reponse, Exception):
            return _EchangeEnPanne(reponse)
        return _FauxEchange(_FausseReponse(*reponse))

    @staticmethod
    def _reponse_saine(methode: str, chemin: str, parametres: dict) -> tuple[int, str]:
        """Sans scénario : le canal média est créé sous l'identifiant demandé, le reste réussit sans corps."""
        if (methode, chemin) == CREATION_DU_CANAL_MEDIA:
            return (200, json.dumps({"id": parametres["channelId"]}))
        return SUCCES_SANS_CORPS

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


class FauxRedis:
    def __init__(self) -> None:
        self.cles: dict[str, str] = {}

    async def set(self, cle: str, valeur: str, *, ex: int) -> None:
        self.cles[cle] = valeur

    async def getdel(self, cle: str) -> str | None:
        return self.cles.pop(cle, None)


class FausseBase:
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
        # L'accueil d'un appel entrant : le poste appelé mène à un agent, dont une version est
        # liée au run. Chaque version garde l'organisation qui la possède, pour la lecture bornée.
        self.postes: dict[str, SimpleNamespace] = {}
        self.agents: dict[int, SimpleNamespace] = {}
        self.versions: dict[int, tuple[int, dict]] = {}
        # La configuration des modèles de chaque organisation, et chaque lecture qui en est faite.
        self.configurations_des_modeles: dict[int, dict] = {}
        self.lectures_de_la_configuration_des_modeles: list[tuple[int, str]] = []

    async def find_active_phone_number_for_inbound(
        self, organization_id: int, poste: str, fournisseur: str
    ) -> SimpleNamespace | None:
        ligne = self.postes.get(poste)
        if ligne is None or ligne.organization_id != organization_id:
            return None
        return ligne

    async def get_workflow(
        self, workflow_id: int, *, organization_id: int
    ) -> SimpleNamespace | None:
        agent = self.agents.get(workflow_id)
        if agent is None or agent.organization_id != organization_id:
            return None
        return agent

    async def create_workflow_run(
        self,
        *,
        name: str,
        workflow_id: int,
        mode: str,
        user_id: int,
        call_type: object,
        initial_context: dict,
        gathered_context: dict,
        organization_id: int,
        definition_id: int | None,
    ) -> SimpleNamespace:
        # Comme la vraie : le run naît ``initialized``, et son sens est rangé par sa valeur.
        run = SimpleNamespace(
            id=RUN,
            workflow=SimpleNamespace(organization_id=organization_id),
            definition_id=definition_id,
            call_type=call_type.value,
            state="initialized",
            is_completed=False,
            gathered_context=dict(gathered_context),
            usage_info={},
            logs={},
        )
        self.runs[run.id] = run
        return run

    async def get_definition_configurations(
        self, definition_id: int | None, *, organization_id: int
    ) -> dict:
        organisation, configurations = self.versions.get(definition_id, (None, {}))
        return configurations if organisation == organization_id else {}

    async def get_configuration(
        self, organization_id: int, cle: str
    ) -> SimpleNamespace | None:
        self.lectures_de_la_configuration_des_modeles.append((organization_id, cle))
        valeur = self.configurations_des_modeles.get(organization_id)
        if valeur is None:
            return None
        return SimpleNamespace(value=valeur, last_validated_at=None)

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


class FaussesPlaces:
    """Les runs qui tiennent une place d'appel. « La place est rendue » se lit sur cet ensemble.

    Deux méthodes rendent une place, comme dans le vrai service : ``unregister_active_call`` ne lève
    jamais, ``release_workflow_run_slot`` peut lever. ``liberations`` note laquelle a servi.
    """

    def __init__(self, *runs: int) -> None:
        self.tenues = set(runs)
        self.liberations: list[tuple[str, int]] = []

    async def acquire_org_slot(
        self, organization_id: int, *, source: str, timeout: float
    ) -> SimpleNamespace:
        return SimpleNamespace(organization_id=organization_id)

    async def bind_workflow_run(self, slot: object, workflow_run_id: int) -> None:
        self.tenues.add(workflow_run_id)

    async def unregister_active_call(self, workflow_run_id: int) -> bool:
        self.liberations.append(("unregister_active_call", workflow_run_id))
        return self._rendre(workflow_run_id)

    async def release_workflow_run_slot(self, workflow_run_id: int) -> bool:
        self.liberations.append(("release_workflow_run_slot", workflow_run_id))
        return self._rendre(workflow_run_id)

    async def release_slot(self, slot: object) -> bool:
        return False

    def _rendre(self, workflow_run_id: int) -> bool:
        if workflow_run_id not in self.tenues:
            return False
        self.tenues.remove(workflow_run_id)
        return True


def monter_une_connexion(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Une connexion face à un faux Asterisk, une fausse base sans run et des places libres.

    À appeler depuis une fixture qui demande aussi ``no_disposition_mapping`` : la vraie
    ``mark_workflow_run_failed`` lit la correspondance des fins d'appel de l'organisation.
    """
    asterisk = FauxAsterisk()
    monkeypatch.setattr(ari_manager.aiohttp, "ClientSession", asterisk.session)
    base = FausseBase()
    monkeypatch.setattr(ari_manager, "db_client", base)
    monkeypatch.setattr(workflow_run_failure, "db_client", base)
    mises_en_file: list[tuple] = []

    async def mettre_en_file(nom: str, *arguments: object) -> None:
        mises_en_file.append((nom, *arguments))

    monkeypatch.setattr("api.tasks.arq.enqueue_job", mettre_en_file)
    places = FaussesPlaces()
    monkeypatch.setattr(ari_manager, "call_concurrency", places)
    connexion = ari_manager.ARIConnection(
        organization_id=ORGANISATION,
        telephony_configuration_id=CONFIGURATION_TELEPHONIE,
        ari_endpoint=ADRESSE_ASTERISK,
        app_name="application-factice",
        app_password="factice",
        ws_client_name="liaison-factice",
    )
    connexion._redis_client = FauxRedis()
    return SimpleNamespace(
        connexion=connexion,
        asterisk=asterisk,
        base=base,
        mises_en_file=mises_en_file,
        places=places,
    )


def monter_un_appel(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Un appel décroché dont le flux audio n'a pas commencé, face à un faux Asterisk.

    Le run est entrant, ``initialized``, de l'organisation de la connexion, et tient une place.
    """
    montage = monter_une_connexion(monkeypatch)
    montage.run = SimpleNamespace(
        id=RUN,
        workflow=SimpleNamespace(organization_id=ORGANISATION),
        call_type="inbound",
        state="initialized",
        is_completed=False,
        gathered_context={},
        usage_info={},
        logs={},
    )
    montage.base.runs[RUN] = montage.run
    montage.places.tenues.add(RUN)
    return montage


def canal_media_demande(asterisk: FauxAsterisk) -> str:
    """Témoin du montage : la demande de création du canal média est arrivée jusqu'à Asterisk, une fois."""
    creations = asterisk.parametres_recus(*CREATION_DU_CANAL_MEDIA)
    assert len(creations) == 1, (
        f"{len(creations)} demande(s) de création du canal média : le montage n'a pas atteint la branche visée"
    )
    return creations[0]["channelId"]


def seule_ecriture_de_l_amont(canal_media: str) -> list[tuple[int, dict]]:
    """L'écriture que l'amont fait avant de demander le canal média : les identifiants des canaux.

    Un test qui attend exactement cette liste affirme que le code du fork, lui, n'a rien écrit sur le run.
    """
    canaux = {"ext_channel_id": canal_media, "call_id": CANAL_APPELANT}
    return [(RUN, {"gathered_context": canaux})]
