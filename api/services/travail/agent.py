"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8, D9, D12) : le travail de fond d'UN agent.

``TravailDeLAgent`` porte l'état d'un agent dont « Travail en arrière-plan » est allumé : son
worker de fond, la tâche en cours (une seule à la fois), la trace de chaque travail dans la fiche
de l'appel (``travaux``), les jetons comptés au coût de l'appel.

Le cerveau de conversation appelle l'outil ``confier_le_travail`` (``brancher_confier_le_travail``) :
``confier`` lance la tâche et **rend tout de suite** ``{"statut": "lancé"}`` (``run_llm=True`` : le
modèle parle, le micro de l'appelant n'est jamais coupé). La tâche envoie le job au worker de fond,
attend son résultat (au plus ``travail_delai_max_s``), le trace, puis le remet (``retour``) ; une
erreur d'outil ne tue pas le travail (le résultat dit l'échec), un échec ou un délai dépassé est un
résultat « le travail n'a pas abouti », jamais une exception dans l'appel.

⛔ Ne lève jamais dans l'appel : tout échec retombe sur l'appel d'avant (un agent sans cerveau de
fond), journalisé.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.pipeline.job_context import JobParams
from pipecat.workers.llm.backend_llm_worker import BACKEND_JOB_NAME

from api.services.pipecat.greffier import versement_du_cout
from api.services.travail.fabrique import preparer_le_service_du_travail
from api.services.travail.outils import MoteurDeFond, preparer_les_outils
from api.services.travail.reglages import (
    CLE_TRAVAUX,
    NOM_DU_COUT,
    NOM_OUTIL,
    ReglagesTravail,
)
from api.services.travail.retour import (
    TEXTE_DELAI,
    TEXTE_ECHEC,
    TEXTE_VIDE,
    message_du_resultat,
    remettre_le_resultat,
)
from api.services.travail.worker import WorkerDeFond, nom_du_worker
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

# Ce que la trace garde de la demande et du résultat (la fiche reste lisible).
LONGUEUR_MAX_DEMANDE = 2000
LONGUEUR_MAX_RESULTAT = 4000

STATUT_EN_COURS = "en_cours"
STATUT_FAIT = "fait"
STATUT_VIDE = "vide"
STATUT_ECHEC = "echec"
STATUT_DELAI = "delai"
STATUT_ANNULE = "annule"

# Ce que l'outil rend au cerveau de conversation.
RETOUR_LANCE = {"statut": "lancé"}
RETOUR_DEJA_EN_COURS = {"statut": "déjà en cours"}
RETOUR_INDISPONIBLE = {"statut": "indisponible"}

DESCRIPTION_OUTIL = (
    "Confie une demande à un second cerveau qui travaille avec ses propres outils pendant que la "
    "conversation continue. Il ne voit pas la conversation : écris une demande complète, avec tout "
    "ce qu'il faut pour la faire. L'outil rend tout de suite « lancé » : continue la conversation. "
    "Le résultat arrive plus tard, dans un message qui commence par « [Résultat du travail : », "
    "écrit par le système, jamais par l'appelant. Un seul travail à la fois : « déjà en cours » "
    "veut dire d'attendre le résultat."
)
DESCRIPTION_DEMANDE = (
    "La demande complète et autonome : ce qui est à faire, et les informations utiles de la fiche "
    "et de la conversation."
)

Executeur = Callable[["TravailDeLAgent", str], Awaitable[str]]
Remise = Callable[[Any, str], Awaitable[bool]]


def schema_de_l_outil() -> FunctionSchema:
    """Le schéma de l'outil « confier » : un seul paramètre, la demande."""
    return FunctionSchema(
        name=NOM_OUTIL,
        description=DESCRIPTION_OUTIL,
        properties={"demande": {"type": "string", "description": DESCRIPTION_DEMANDE}},
        required=["demande"],
    )


async def executer_par_l_appel(travail: "TravailDeLAgent", demande: str) -> str:
    """Au téléphone : le job part au worker de fond par le worker d'appel (bus local), au plus
    ``delai_max_s`` (attente du worker comprise). Lève ``JobError`` en cas d'échec ou de délai."""
    demandeur = travail.moteur.call_worker
    if demandeur is None:
        raise RuntimeError("no call worker to send the job from")
    params = JobParams(
        name=BACKEND_JOB_NAME,
        payload={"request": demande},
        timeout=float(travail.reglages.delai_max_s),
    )
    async with demandeur.job(travail.worker.name, params=params) as travail_en_cours:
        async for _evenement in travail_en_cours:
            pass
    return str(travail_en_cours.response.get("text", ""))


class TravailDeLAgent:
    """Le cerveau de fond d'un agent : une tâche à la fois, tracée, comptée, remise."""

    def __init__(
        self,
        *,
        moteur: Any,
        agent: Any,
        reglages: ReglagesTravail,
        service: Any,
        executeur: Executeur = executer_par_l_appel,
        remise: Remise = remettre_le_resultat,
    ):
        self.moteur = moteur
        self.agent = agent
        self.reglages = reglages
        self.service = service
        self._executeur = executeur
        self._remise = remise
        self._tache: asyncio.Task | None = None
        self._entree_courante: dict | None = None
        self._debut_courant = 0.0
        self._attache = False
        # Au téléphone, le worker de fond est enfant du worker d'appel ; au clavier il vit le
        # temps d'un mini-bus du tour (``executer_en_local``).
        self._enfant_de_l_appel = executeur is executer_par_l_appel
        self._outils_prets = False
        self._muet = MoteurDeFond(moteur)
        self._jetons = [0, 0]
        self._outils_appeles: list[str] = []
        self._verser = versement_du_cout(moteur, NOM_DU_COUT, service)
        self.worker = WorkerDeFond(
            llm=service,
            nom=nom_du_worker(getattr(agent, "visit_id", "") or "agent"),
            consigne=reglages.consigne,
            jetons=self._compter,
            outil=self._noter_l_outil,
        )

    # -- l'outil ---------------------------------------------------------------

    @property
    def occupe(self) -> bool:
        """Un travail est en cours."""
        return self._tache is not None and not self._tache.done()

    async def confier(self, demande: Any) -> dict:
        """Lance le travail et rend tout de suite (l'outil ne bloque jamais la conversation).
        ⛔ Ne lève jamais."""
        try:
            texte = str(demande or "").strip()
            if not texte:
                return {"statut": "demande vide"}
            if self.moteur.is_call_disposed():
                return dict(RETOUR_INDISPONIBLE)
            if self.occupe:
                return dict(RETOUR_DEJA_EN_COURS)
            if self._enfant_de_l_appel and not self._attache:
                logger.warning("[travail] worker de fond pas attaché à l'appel")
                return dict(RETOUR_INDISPONIBLE)
            self._jetons = [0, 0]
            self._outils_appeles = []
            # La trace existe dès que l'outil rend « lancé » : la fiche dit « en cours ».
            entree = self._ouvrir_la_trace(texte)
            self._entree_courante = entree
            self._debut_courant = time.monotonic()
            self._tache = asyncio.get_running_loop().create_task(
                self._travailler(texte, entree, self._debut_courant),
                name=f"travail:{self.worker.name}",
            )
            self._tache.add_done_callback(self._journaliser_la_fin)
            return dict(RETOUR_LANCE)
        except Exception as erreur:  # noqa: BLE001 -- l'outil ne casse jamais l'appel
            logger.error(f"[travail] travail non lancé : {type(erreur).__name__}")
            return dict(RETOUR_INDISPONIBLE)

    async def attacher(self) -> bool:
        """Ajoute le worker de fond à l'appel (enfant du worker d'appel, bus local). Une fois ;
        rien au clavier. ``False`` si l'appel n'est pas encore là. Ne lève jamais."""
        if self._attache or not self._enfant_de_l_appel:
            return self._attache
        try:
            demandeur = self.moteur.call_worker
            if demandeur is None:
                return False
            self._attache = True
            await demandeur.add_workers(self.worker)
            return True
        except Exception as erreur:  # noqa: BLE001 -- un fond sans worker rend « indisponible »
            self._attache = False
            logger.error(f"[travail] worker de fond non attaché : {type(erreur).__name__}")
            return False

    async def attendre(self, delai_s: float | None = None) -> None:
        """Attend la fin du travail en cours (le clavier, qui finit son tour). Ne lève jamais."""
        tache = self._tache
        if tache is None or tache.done():
            return
        limite = (delai_s if delai_s is not None else self.reglages.delai_max_s) + 5.0
        try:
            await asyncio.wait_for(asyncio.shield(tache), timeout=limite)
            # Les jetons de la dernière requête passent par l'observateur du worker : attendus,
            # pour que le coût du tour les compte.
            await asyncio.wait_for(self.worker.wait_for_observers(), timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[travail] attente du travail : {type(erreur).__name__}")

    async def fermer(self, *, forcer: bool = False) -> None:
        """Arrête ce cerveau de fond : la tâche en cours (si ``forcer``) et son worker. Un travail
        en cours est laissé finir quand l'agent se retire sans ``forcer`` (son résultat ira à
        l'agent suivant). Ne lève jamais."""
        try:
            if self.occupe and not forcer:
                return
            if self.occupe:
                self._tache.cancel()
                await asyncio.gather(self._tache, return_exceptions=True)
                # Annulé avant d'avoir démarré, la tâche n'a rien tracé : la trace le dit ici.
                entree = self._entree_courante
                if entree is not None and entree.get("statut") == STATUT_EN_COURS:
                    self._fermer_la_trace(entree, STATUT_ANNULE, self._debut_courant)
            if not self.worker.has_finished():
                await self.worker.cancel(reason="agent retired")
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[travail] fermeture du fond : {type(erreur).__name__}")

    # -- le travail --------------------------------------------------------------

    def _compter(self, entree: int | None, sortie: int | None) -> None:
        self._jetons[0] += int(entree or 0)
        self._jetons[1] += int(sortie or 0)
        self._verser(entree, sortie)

    def _noter_l_outil(self, nom: str) -> None:
        self._outils_appeles.append(nom)

    def _journaliser_la_fin(self, tache: asyncio.Task) -> None:
        if not tache.cancelled() and tache.exception() is not None:
            logger.error(f"[travail] tâche de fond tombée : {type(tache.exception()).__name__}")

    async def _preparer_les_outils(self) -> None:
        """Les outils du fond, au premier travail (les sessions MCP de l'agent sont alors
        ouvertes). Un échec = un fond sans outil."""
        if self._outils_prets:
            return
        self._outils_prets = True
        schemas, noms = await preparer_les_outils(
            self.moteur, self.agent, self.service, self.reglages.outils, self._muet
        )
        if schemas:
            self.worker.context.set_tools(ToolsSchema(standard_tools=schemas))
        logger.info(f"[travail] outils du fond : {noms or 'aucun'}")

    def _fiche(self) -> dict | None:
        fiche = getattr(self.moteur, "_gathered_context", None)
        return fiche if isinstance(fiche, dict) else None

    def _ouvrir_la_trace(self, demande: str) -> dict:
        entree: dict = {
            "agent": getattr(self.agent, "workflow_name", "") or None,
            "demande": demande[:LONGUEUR_MAX_DEMANDE],
            "statut": STATUT_EN_COURS,
            "outils": [],
            "duree_ms": None,
            "jetons_entree": None,
            "jetons_sortie": None,
            "resultat": None,
            "remis": False,
        }
        fiche = self._fiche()
        if fiche is not None:
            entree["tour"] = fiche.get(CLE_TOUR)
            fiche.setdefault(CLE_TRAVAUX, []).append(entree)
        return entree

    def _fermer_la_trace(
        self, entree: dict, statut: str, debut: float, resultat: str | None = None
    ) -> None:
        entree.update(
            statut=statut,
            outils=list(self._outils_appeles),
            duree_ms=round((time.monotonic() - debut) * 1000),
            jetons_entree=self._jetons[0],
            jetons_sortie=self._jetons[1],
            resultat=(resultat or "")[:LONGUEUR_MAX_RESULTAT] or None,
        )
        if self._muet.non_dites:
            entree["phrases_non_dites"] = list(self._muet.non_dites)
            self._muet.non_dites.clear()

    async def _travailler(self, demande: str, entree: dict, debut: float) -> None:
        statut, texte = STATUT_FAIT, ""
        try:
            await self._preparer_les_outils()
            texte = (await self._executeur(self, demande)).strip()
            if not texte:
                statut = STATUT_VIDE
        except asyncio.CancelledError:
            self._fermer_la_trace(entree, STATUT_ANNULE, debut)
            raise
        except Exception as erreur:  # noqa: BLE001 -- le résultat dit l'échec
            enclair = str(erreur).lower()
            delai = (
                isinstance(erreur, TimeoutError) or "timed out" in enclair or "timeout" in enclair
            )
            statut = STATUT_DELAI if delai else STATUT_ECHEC
            logger.warning(f"[travail] travail non abouti ({statut}) : {type(erreur).__name__}")
        message = message_du_resultat(
            texte
            if statut == STATUT_FAIT
            else {STATUT_VIDE: TEXTE_VIDE, STATUT_DELAI: TEXTE_DELAI}.get(statut, TEXTE_ECHEC)
        )
        self._fermer_la_trace(entree, statut, debut, texte)
        entree["message"] = message
        entree["remis"] = bool(await self._remise(self.moteur, message))
        logger.info(
            f"[travail] {statut} en {entree['duree_ms']} ms, outils {entree['outils'] or 'aucun'}, "
            f"remis={entree['remis']}"
        )


def brancher_confier_le_travail(
    moteur: Any, travail: TravailDeLAgent, agent: Any
) -> FunctionSchema:
    """Enregistre l'outil « confier » auprès du modèle de l'agent et rend son schéma. Le
    gestionnaire rend tout de suite (``run_llm`` par défaut : le modèle reparle) ; la garde
    ``agent_can_act`` est celle de tous les outils de l'agent."""

    async def gestionnaire(params) -> None:
        arguments = getattr(params, "arguments", None) or {}
        await params.result_callback(await travail.confier(arguments.get("demande")))

    agent.llm.register_function(NOM_OUTIL, agent.bind_tool(moteur, gestionnaire))
    return schema_de_l_outil()


async def preparer_le_travail(
    moteur: Any,
    agent: Any,
    *,
    user_config: Any = None,
    executeur: Executeur | None = None,
    remise: Remise | None = None,
) -> TravailDeLAgent | None:
    """Le cerveau de fond de ``agent``, ou ``None`` : éteint (le cas de tout agent non réglé),
    ou impossible à construire (journalisé). Posé sur ``agent.travail`` et dans
    ``moteur.travaux`` (arrêté au nettoyage de l'appel). ⛔ Ne lève jamais."""
    try:
        reglages_agent = getattr(agent, "reglages", None)
        if ReglagesTravail.depuis(reglages_agent).actif is not True:
            return None
        if getattr(agent, "travail", None) is not None:
            return agent.travail
        configuration = (
            user_config if user_config is not None else getattr(agent, "user_config", None)
        )
        if configuration is None:
            logger.warning("[travail] pas de configuration de modèle : agent joué sans fond")
            return None
        organisation = await moteur._get_organization_id()
        fabrique = getattr(moteur, "_agent_factory", None)
        reglages, service = await preparer_le_service_du_travail(
            reglages_agent,
            configuration,
            organisation,
            getattr(agent, "runtime_configuration", None),
            correlation_id=getattr(fabrique, "_mps_correlation_id", None),
        )
        if reglages is None or service is None:
            return None
        if executeur is None and getattr(moteur, "sans_sortie_audio", False):
            from api.services.travail.clavier import (
                executer_en_local,
                remettre_au_tour_suivant,
            )

            executeur, remise = executer_en_local, remise or remettre_au_tour_suivant
        travail = TravailDeLAgent(
            moteur=moteur,
            agent=agent,
            reglages=reglages,
            service=service,
            executeur=executeur or executer_par_l_appel,
            remise=remise or remettre_le_resultat,
        )
        agent.travail = travail
        moteur.travaux.append(travail)
        return travail
    except Exception as erreur:  # noqa: BLE001 -- l'agent est joué sans cerveau de fond
        logger.error(f"[travail] cerveau de fond non préparé : {type(erreur).__name__}")
        return None
