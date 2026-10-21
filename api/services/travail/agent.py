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

Chantier fiabilite-orchestration, lot 1 (F1, F2, C1, C2, R15) :
- l'attente parlée : pendant un travail, une ligne du code (``LIGNE_TRAVAIL_EN_COURS``) entre dans
  chaque requête de conversation, juste avant la dernière parole de l'appelant (comme l'état de la
  fiche : hors historique, le cache reste servi) ; elle dit de ne poser aucune question ;
- l'appelant peut toujours **annuler** (``annuler_le_travail``) ou **modifier** : ``confier`` pendant
  un travail annule la demande précédente et lance la nouvelle ;
- la **phrase d'attente** (motif ``travail_dure`` des phrases du code, veille générique du diseur) est
  dite par la voix, sans le modèle, quand le travail dure au-delà de son délai d'attente du système
  (dès le lancement avec un délai de 0), avec ses redites et sa sortie ; l'annonce que l'agent écrit en
  confiant le travail (``annonce``, case de la règle) passe en première phrase ;
- l'échec du travail (motif ``travail_echoue``) : phrase, note dans la fiche, sortie, puis compte rendu
  en français dans le résultat remis au cerveau de conversation (correctifs-apres-banc-v4, lot 4) ;
- ``confier`` qui rend « lancé » ne relance pas le modèle quand la même réponse a déjà parlé (R15).
"""

from __future__ import annotations

import asyncio
import re
import time
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import FunctionCallResultProperties
from pipecat.pipeline.job_context import JobParams
from pipecat.workers.llm.backend_llm_worker import BACKEND_JOB_NAME

from api.services.phrases.catalogue import MOTIFS, TRAVAIL_DURE, TRAVAIL_ECHOUE
from api.services.phrases.compte_rendu import compte_rendu
from api.services.pipecat.greffier import versement_du_cout
from api.services.pipecat.parole_avant_outil import suivre_la_parole
from api.services.travail.fabrique import preparer_le_service_du_travail
from api.services.travail.outils import MoteurDeFond, preparer_les_outils
from api.services.travail.reglages import (
    CLE_TRAVAUX,
    NOM_DU_COUT,
    NOM_OUTIL,
    NOM_OUTIL_ANNULER,
    ReglagesTravail,
)
from api.services.travail.retour import (
    TEXTE_DELAI,
    TEXTE_ECHEC,
    TEXTE_SANS_OUTIL,
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
# correctifs-apres-banc-v4, lot 2 (6.4) : le fond avait des outils et a rendu un texte sans en appeler aucun.
STATUT_SANS_OUTIL = "sans_outil"
# Les statuts qui sont un échec du travail de fond (point d'appel du motif « le travail de fond échoue »).
STATUTS_D_ECHEC = (STATUT_ECHEC, STATUT_DELAI, STATUT_SANS_OUTIL)

# Ce que l'outil rend au cerveau de conversation.
RETOUR_LANCE = {"statut": "lancé"}
RETOUR_REMPLACE = {"statut": "lancé", "demande_precedente": "annulée"}
RETOUR_INDISPONIBLE = {"statut": "indisponible"}
RETOUR_ANNULE = {"statut": "annulé"}
RETOUR_AUCUN = {"statut": "aucun travail en cours"}

# C2 : la ligne écrite par le code pendant un travail en cours (F1, F2). Générique : aucun métier.
LIGNE_TRAVAIL_EN_COURS = (
    "Un travail est en cours : tu ne poses aucune question ; tu rassures, ou tu annules ou "
    "modifies la demande si la personne le dit."
)

DESCRIPTION_OUTIL = (
    "Confie une demande à un second cerveau qui travaille avec ses propres outils pendant que la "
    "conversation continue. Il ne voit pas la conversation : écris une demande complète, avec tout "
    "ce qu'il faut pour la faire. L'outil rend tout de suite « lancé » : continue la conversation. "
    "Le résultat arrive plus tard, dans un message qui commence par « [Résultat du travail : », "
    "écrit par le système, jamais par l'appelant. Un seul travail à la fois : appeler cet outil "
    "pendant un travail en cours annule la demande précédente et lance la nouvelle (pour la "
    "modifier, écris la demande complète corrigée)."
)
DESCRIPTION_ANNULER = (
    "Annule le travail en cours confié au second cerveau, quand la personne ne veut plus de sa "
    "demande. Sans travail en cours, ne fait rien."
)
# D-3 (Evan, 21/10) : la description exacte, mesurée au lot 0.
DESCRIPTION_ANNONCE = (
    "Une phrase courte dite à l'appelant pendant le travail, qui ne donne aucun résultat."
)
LONGUEUR_MAX_ANNONCE = 120
DESCRIPTION_DEMANDE = (
    "La demande complète et autonome : ce qui est à faire, et les informations utiles de la fiche "
    "et de la conversation."
)

Executeur = Callable[["TravailDeLAgent", str], Awaitable[str]]
Remise = Callable[[Any, str], Awaitable[bool]]
# Refait le service du fond pour un worker neuf : un service ne sert qu'à un seul worker.
Fabrique = Callable[[], Awaitable[Any]]


def schema_de_l_annulation() -> FunctionSchema:
    """Le schéma de l'outil « annuler » : aucun paramètre."""
    return FunctionSchema(
        name=NOM_OUTIL_ANNULER, description=DESCRIPTION_ANNULER, properties={}, required=[]
    )


def schema_de_l_outil(avec_annonce: bool = False) -> FunctionSchema:
    """Le schéma de l'outil « confier » : la demande ; et, quand la case « laisser l'agent écrire
    l'annonce » de la règle est cochée, l'annonce, OBLIGATOIRE (mesuré au lot 0 : facultative, jamais
    remplie ; obligatoire, 56/56 justes). Case éteinte : l'outil est inchangé."""
    proprietes: dict[str, Any] = {"demande": {"type": "string", "description": DESCRIPTION_DEMANDE}}
    requis = ["demande"]
    if avec_annonce:
        proprietes["annonce"] = {"type": "string", "description": DESCRIPTION_ANNONCE}
        requis.append("annonce")
    return FunctionSchema(
        name=NOM_OUTIL,
        description=DESCRIPTION_OUTIL,
        properties=proprietes,
        required=requis,
    )


def _mots_de(texte: Any) -> list[str]:
    return re.findall(r"\w+", str(texte or "").casefold())


def annonce_valide(annonce: Any, demande: Any) -> str | None:
    """L'annonce écrite par l'agent si elle est dicible : non vide, au plus ``LONGUEUR_MAX_ANNONCE``
    caractères, et qui ne recopie pas la demande (sinon : la phrase fixe de la règle). ``None``
    sinon. ⛔ Ne lève jamais."""
    try:
        texte = " ".join(str(annonce or "").split())
        if not texte or len(texte) > LONGUEUR_MAX_ANNONCE:
            return None
        a, d = " ".join(_mots_de(texte)), " ".join(_mots_de(demande))
        if not a:
            return None
        # Une recopie : la même suite de mots, ou l'une contenue dans l'autre (au moins trois mots).
        if a == d or (len(d.split()) >= 3 and (d in a or (len(a.split()) >= 3 and a in d))):
            return None
        return texte
    except Exception:  # noqa: BLE001
        return None


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
        refaire_le_service: Fabrique | None = None,
    ):
        self.moteur = moteur
        self.agent = agent
        self.reglages = reglages
        self.service = service
        self._executeur = executeur
        self._remise = remise
        self._refaire_le_service = refaire_le_service
        self._tache: asyncio.Task | None = None
        self._entree_courante: dict | None = None
        self._debut_courant = 0.0
        self._attache = False
        # Au téléphone, le worker de fond est enfant du worker d'appel ; au clavier il vit le
        # temps d'un mini-bus du tour (``executer_en_local``).
        self._enfant_de_l_appel = executeur is executer_par_l_appel
        self._outils_prets = False
        # Les outils que le fond a reçus (6.4) : sans eux, un texte sans appel d'outil est normal.
        self._outils_du_fond: list[str] = []
        self._muet = MoteurDeFond(moteur)
        self._jetons = [0, 0]
        self._outils_appeles: list[str] = []
        self._verser = versement_du_cout(moteur, NOM_DU_COUT, service)
        # Un travail non abouti (délai, échec, annulation) peut laisser le worker au milieu d'une
        # requête ou d'un outil : sa fin tardive irait au travail suivant. Le worker est alors
        # remplacé par un neuf (contexte vierge, nouveau nom) au travail suivant.
        self._generation = 0
        self._a_remplacer = False
        self._fermeture_differee: asyncio.Task | None = None
        # C1 : la seconde phrase d'attente du travail en cours (une tâche par travail).
        self._seconde_phrase: asyncio.Task | None = None
        self.worker = self._nouveau_worker()

    def _nouveau_worker(self) -> WorkerDeFond:
        nom = nom_du_worker(getattr(self.agent, "visit_id", "") or "agent")
        return WorkerDeFond(
            llm=self.service,
            nom=f"{nom}-{self._generation}" if self._generation else nom,
            consigne=self.reglages.consigne,
            jetons=self._compter,
            outil=self._noter_l_outil,
        )

    # -- l'outil ---------------------------------------------------------------

    @property
    def occupe(self) -> bool:
        """Un travail est en cours."""
        return self._tache is not None and not self._tache.done()

    async def confier(self, demande: Any, annonce: Any = None) -> dict:
        """Lance le travail et rend tout de suite (l'outil ne bloque jamais la conversation).
        ``annonce`` : la phrase que l'agent a écrite pour l'attente (utilisée si la règle le veut et
        si elle est valide). ⛔ Ne lève jamais."""
        try:
            texte = str(demande or "").strip()
            if not texte:
                return {"statut": "demande vide"}
            if self.moteur.is_call_disposed():
                return dict(RETOUR_INDISPONIBLE)
            # F2 : modifier = annuler la demande en cours, puis lancer la nouvelle.
            remplace = False
            if self.occupe:
                await self._annuler_le_travail_en_cours()
                remplace = True
            if self._a_remplacer and not await self._remplacer_le_worker():
                return dict(RETOUR_INDISPONIBLE)
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
            self._lancer_la_seconde_phrase(self._tache, annonce, texte)
            return dict(RETOUR_REMPLACE if remplace else RETOUR_LANCE)
        except Exception as erreur:  # noqa: BLE001 -- l'outil ne casse jamais l'appel
            logger.error(f"[travail] travail non lancé : {type(erreur).__name__}")
            return dict(RETOUR_INDISPONIBLE)

    async def annuler(self) -> dict:
        """F2 : l'appelant ne veut plus de sa demande. ⛔ Ne lève jamais."""
        try:
            if not self.occupe:
                return dict(RETOUR_AUCUN)
            await self._annuler_le_travail_en_cours()
            logger.info("[travail] travail annulé à la demande de l'appelant")
            return dict(RETOUR_ANNULE)
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"[travail] annulation en échec : {type(erreur).__name__}")
            return dict(RETOUR_INDISPONIBLE)

    async def _annuler_le_travail_en_cours(self) -> None:
        """Arrête la tâche en cours (sa trace dit « annulé », son résultat n'est jamais remis) ; le
        worker sera remplacé au travail suivant."""
        self._arreter_la_seconde_phrase()
        tache = self._tache
        if tache is None or tache.done():
            return
        tache.cancel()
        await asyncio.gather(tache, return_exceptions=True)
        entree = self._entree_courante
        if entree is not None and entree.get("statut") == STATUT_EN_COURS:
            self._fermer_la_trace(entree, STATUT_ANNULE, self._debut_courant)
        self._a_remplacer = True

    # -- C1 : la seconde phrase d'attente -------------------------------------------

    def _lancer_la_seconde_phrase(
        self, tache: asyncio.Task, annonce: Any = None, demande: Any = None
    ) -> None:
        """Au téléphone seulement (au clavier, le travail se fait dans le tour). La veille de la règle
        « le travail de fond travaille » démarre ICI, au moment où l'agent confie le travail : jamais
        avant l'appel de l'outil, jamais sans lui."""
        self._arreter_la_seconde_phrase()
        diseur = getattr(self.moteur, "phrases", None)
        if diseur is None or not self._enfant_de_l_appel:
            return
        self._seconde_phrase = asyncio.get_running_loop().create_task(
            self._dire_la_seconde_phrase(diseur, tache, annonce, demande),
            name=f"attente:{self.worker.name}",
        )

    async def _dire_la_seconde_phrase(
        self, diseur: Any, tache: asyncio.Task, annonce: Any = None, demande: Any = None
    ) -> None:
        try:
            agent = self.moteur.active_agent
            phrase = diseur.phrase(TRAVAIL_DURE, agent)
            if phrase is None or not phrase.active or phrase.delai_s is None:
                return
            # L'annonce de l'agent passe en première phrase seulement si la case de la règle est
            # cochée ; vide, trop longue ou recopiée de la demande, elle laisse la phrase fixe.
            premiere = annonce_valide(annonce, demande) if phrase.texte_de_l_agent else None
            if not (phrase.dite or premiere):
                return

            def en_cours() -> bool:
                return self._tache is tache and not tache.done()

            await diseur.veiller(
                TRAVAIL_DURE, en_cours, agent=agent, phrase=phrase, premiere=premiere
            )
        except asyncio.CancelledError:
            raise
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[travail] phrase d'attente : {erreur!r}")

    def _arreter_la_seconde_phrase(self) -> None:
        tache = self._seconde_phrase
        self._seconde_phrase = None
        if tache is not None and not tache.done() and tache is not asyncio.current_task():
            tache.cancel()

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

    async def _remplacer_le_worker(self) -> bool:
        """Arrête le worker d'un travail non abouti et en monte un neuf (attaché à l'appel au
        téléphone). ``False`` si le neuf n'a pas pu être attaché. Ne lève jamais."""
        ancien = self.worker
        self._a_remplacer = False
        if self._refaire_le_service is not None:
            try:
                service = await self._refaire_le_service()
            except Exception as erreur:  # noqa: BLE001
                logger.error(f"[travail] service du fond non refait : {type(erreur).__name__}")
                service = None
            if service is None:
                self._a_remplacer = True
                return False
            self.service = service
            self._verser = versement_du_cout(self.moteur, NOM_DU_COUT, service)
            from api.services.panne.garde_modele import garder_le_fond

            await garder_le_fond(self.moteur, self.agent, service, lambda: self.worker.context)
        self._generation += 1
        self._outils_prets = False
        self._attache = False
        self.worker = self._nouveau_worker()
        try:
            if not ancien.has_finished():
                await ancien.cancel(reason="replaced after an unfinished job")
        except Exception as erreur:  # noqa: BLE001 -- l'ancien ne retient jamais le neuf
            logger.warning(f"[travail] ancien worker de fond non arrêté : {type(erreur).__name__}")
        logger.info(f"[travail] worker de fond remplacé : {self.worker.name}")
        if self._enfant_de_l_appel:
            return await self.attacher()
        return True

    def apres_le_travail(self, fermeture: Callable[[], Awaitable[None]]) -> bool:
        """L'agent se retire pendant un travail : ``fermeture`` (ses sessions d'outils, MCP
        compris) attend la fin de ce travail, qui s'en sert encore, puis le fond s'arrête.
        ``False`` s'il n'y a aucun travail en cours (l'appelant ferme tout de suite)."""
        tache = self._tache
        if tache is None or tache.done():
            return False

        async def fermer_apres() -> None:
            await asyncio.gather(tache, return_exceptions=True)
            try:
                await fermeture()
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[travail] fermeture différée : {type(erreur).__name__}")
            await self.fermer()

        self._fermeture_differee = asyncio.get_running_loop().create_task(
            fermer_apres(), name=f"fermeture:{self.worker.name}"
        )
        return True

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
            self._arreter_la_seconde_phrase()
            if self.occupe:
                self._tache.cancel()
                await asyncio.gather(self._tache, return_exceptions=True)
                # Annulé avant d'avoir démarré, la tâche n'a rien tracé : la trace le dit ici.
                entree = self._entree_courante
                if entree is not None and entree.get("statut") == STATUT_EN_COURS:
                    self._fermer_la_trace(entree, STATUT_ANNULE, self._debut_courant)
            if not self.worker.has_finished():
                await self.worker.cancel(reason="agent retired")
            differee = self._fermeture_differee
            if forcer and differee is not None and differee is not asyncio.current_task():
                await asyncio.gather(differee, return_exceptions=True)
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
        self._outils_du_fond = list(noms or [])
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

    async def signaler_l_echec_du_fond(self, entree: dict, statut: str) -> None:
        """POINT D'APPEL UNIQUE du motif « le travail de fond échoue ».

        Appelé UNE fois par travail non abouti (échec, délai, ou 6.4 : texte rendu sans outil appelé),
        après la fermeture de la trace et avant la remise du résultat. ``entree`` est la trace du
        travail (``statut``, ``outils``, ``resultat``, ``message``), ``statut`` l'un de ``STATUTS_D_ECHEC``.
        La règle dit sa phrase (dans l'historique avant le message du résultat, qui entre ensuite), note
        dans la fiche et exécute sa sortie ; le compte rendu en français s'ajoute au message remis
        (``entree["message"]``). ⛔ Ne lève jamais."""
        try:
            diseur = getattr(self.moteur, "phrases", None)
            if diseur is None:
                return
            probleme = await diseur.signaler_un_probleme(TRAVAIL_ECHOUE, self.moteur.active_agent)
            if probleme.dit is None and probleme.issue is None:
                logger.info(f"[travail] échec du fond ({statut}) : aucune règle ne parle")
                return
            issue = probleme.issue
            lignes = compte_rendu(
                MOTIFS[TRAVAIL_ECHOUE].fait_fr,
                dit=probleme.dit,
                notes=probleme.notes,
                interdits=issue.interdit if issue is not None else (),
                crochets=False,
            )
            message = entree.get("message")
            if lignes and isinstance(message, str) and message.endswith("]"):
                entree["message"] = f"{message[:-1]}\n{lignes}]"
            if issue is not None and issue.prise_en_main:
                # La sortie a pris l'appel en main (transfert lancé, appel raccroché) : rien à remettre.
                entree["prise_en_main"] = True
        except asyncio.CancelledError:
            raise
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[travail] échec du fond non signalé : {type(erreur).__name__}")

    async def _travailler(self, demande: str, entree: dict, debut: float) -> None:
        statut, texte = STATUT_FAIT, ""
        try:
            await self._preparer_les_outils()
            texte = (await self._executeur(self, demande)).strip()
            if not texte:
                statut = STATUT_VIDE
            elif self._outils_du_fond and not self._outils_appeles:
                # 6.4 (run 1480) : le fond rend du texte (« réservation faite ») sans avoir appelé aucun
                # de ses outils : rien n'a été fait, le résultat dit l'échec. Le texte rendu reste dans
                # la trace (``resultat``) ; le cerveau de conversation ne lit que l'échec.
                statut = STATUT_SANS_OUTIL
        except asyncio.CancelledError:
            self._a_remplacer = True
            self._fermer_la_trace(entree, STATUT_ANNULE, debut)
            raise
        except Exception as erreur:  # noqa: BLE001 -- le résultat dit l'échec
            enclair = str(erreur).lower()
            delai = (
                isinstance(erreur, TimeoutError) or "timed out" in enclair or "timeout" in enclair
            )
            statut = STATUT_DELAI if delai else STATUT_ECHEC
            self._a_remplacer = True
            logger.warning(f"[travail] travail non abouti ({statut}) : {type(erreur).__name__}")
        message = message_du_resultat(
            texte
            if statut == STATUT_FAIT
            else {
                STATUT_VIDE: TEXTE_VIDE,
                STATUT_DELAI: TEXTE_DELAI,
                STATUT_SANS_OUTIL: TEXTE_SANS_OUTIL,
            }.get(statut, TEXTE_ECHEC)
        )
        self._fermer_la_trace(entree, statut, debut, texte)
        self._arreter_la_seconde_phrase()
        entree["message"] = message
        if statut in STATUTS_D_ECHEC:
            try:
                await self.signaler_l_echec_du_fond(entree, statut)
            except Exception as erreur:  # noqa: BLE001 -- un signalement raté ne coûte pas la remise
                logger.warning(f"[travail] échec du fond non signalé : {type(erreur).__name__}")
        # Une sortie qui a pris l'appel en main (transfert lancé, appel raccroché) : le résultat n'est
        # pas remis, personne ne l'attend. Sinon le message porte le compte rendu de la règle.
        if entree.get("prise_en_main"):
            entree["remis"] = False
        else:
            entree["remis"] = bool(await self._remise(self.moteur, entree.get("message") or message))
        logger.info(
            f"[travail] {statut} en {entree['duree_ms']} ms, outils {entree['outils'] or 'aucun'}, "
            f"remis={entree['remis']}"
        )


def annonce_demandee(moteur: Any, agent: Any, noeud: Any = None) -> bool:
    """La case « laisser l'agent écrire l'annonce » est-elle cochée sur la règle qui vaut pour cet agent à
    cette étape ? Sinon l'outil est inchangé. ⛔ Ne lève jamais."""
    try:
        diseur = getattr(moteur, "phrases", None)
        if diseur is None:
            return False
        identifiant = getattr(noeud, "id", None)
        phrase = diseur.phrase(
            TRAVAIL_DURE,
            agent,
            etape=getattr(noeud, "name", None),
            etape_id=identifiant if isinstance(identifiant, str) else None,
        )
        return bool(phrase is not None and phrase.active and phrase.texte_de_l_agent)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] case de l'annonce illisible : {erreur!r}")
        return False


def brancher_confier_le_travail(
    moteur: Any, travail: TravailDeLAgent, agent: Any, noeud: Any = None
) -> FunctionSchema:
    """Enregistre l'outil « confier » auprès du modèle de l'agent et rend son schéma. Le
    gestionnaire rend tout de suite (``run_llm`` par défaut : le modèle reparle) ; la garde
    ``agent_can_act`` est celle de tous les outils de l'agent."""

    proprietes = _proprietes_du_resultat(agent.llm)

    async def gestionnaire(params) -> None:
        # fiabilite-orchestration, lot 2 (C3) : la liste des champs de l'étape garde « confier »
        # comme les outils de l'étape (run 1468 : action lancée avec des champs encore « à venir »).
        from api.services.workflow.enveloppe_des_actions import garde_de_l_etape

        refus = garde_de_l_etape(moteur, agent)
        if refus is not None:
            await params.result_callback(refus)
            return
        arguments = getattr(params, "arguments", None) or {}
        resultat = await travail.confier(arguments.get("demande"), arguments.get("annonce"))
        await params.result_callback(resultat, properties=proprietes(params))

    agent.llm.register_function(NOM_OUTIL, agent.bind_tool(moteur, gestionnaire))
    montrer_le_travail_en_cours(moteur, agent.llm)
    return schema_de_l_outil(annonce_demandee(moteur, agent, noeud))


def brancher_annuler_le_travail(
    moteur: Any, travail: TravailDeLAgent, agent: Any
) -> FunctionSchema:
    """F2 : l'outil « annuler », offert avec « confier » et à toute étape où un travail est en
    cours. Sans travail en cours, il ne fait rien."""
    proprietes = _proprietes_du_resultat(agent.llm)

    async def annulation(params) -> None:
        await params.result_callback(await travail.annuler(), properties=proprietes(params))

    agent.llm.register_function(NOM_OUTIL_ANNULER, agent.bind_tool(moteur, annulation))
    return schema_de_l_annulation()


def _proprietes_du_resultat(llm: Any) -> Callable[[Any], FunctionCallResultProperties | None]:
    """R15 : un outil qui rend tout de suite ne relance pas le modèle quand la même réponse a déjà
    parlé ; sinon le comportement d'avant (le modèle parle : la phrase d'attente, F1)."""
    suivi = suivre_la_parole(llm)

    def proprietes(params: Any) -> FunctionCallResultProperties | None:
        if suivi is not None and suivi.a_parle_avant(getattr(params, "tool_call_id", None)):
            return FunctionCallResultProperties(run_llm=False)
        return None

    return proprietes


def ligne_du_travail(moteur: Any) -> str | None:
    """C2 : la ligne du code quand un travail est en cours dans l'appel (celui de l'agent qui a la
    main, ou celui qu'un autre agent a confié avant une passation : son résultat ira à l'agent qui
    a la main). ``None`` sinon. ⛔ Ne lève jamais."""
    try:
        for travail in getattr(moteur, "travaux", None) or []:
            if getattr(travail, "occupe", False):
                return LIGNE_TRAVAIL_EN_COURS
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] ligne du travail illisible : {erreur!r}")
    return None


_MARQUE_LIGNE = "_mark_ligne_du_travail"


def montrer_le_travail_en_cours(moteur: Any, llm: Any) -> bool:
    """C2 : pendant un travail, chaque requête de CONVERSATION de ``llm`` reçoit la ligne du code
    juste avant la dernière parole de l'appelant (``inserer_l_etat``, comme l'état de la fiche).
    Rien n'entre dans l'historique ni dans le prompt système : le cache reste servi. Branché une
    fois par service. ⛔ Ne lève jamais."""
    try:
        if getattr(llm, _MARQUE_LIGNE, False):
            return True
        if not (
            hasattr(llm, "get_chat_completions") and hasattr(llm, "build_chat_completion_params")
        ):
            return False
        from api.services.workflow.fiche_au_fil_de_leau import inserer_l_etat

        en_conversation: ContextVar[bool] = ContextVar("travail_en_conversation", default=False)
        obtenir = llm.get_chat_completions
        construire = llm.build_chat_completion_params

        async def get_chat_completions(context):
            jeton = en_conversation.set(True)
            try:
                return await obtenir(context)
            finally:
                en_conversation.reset(jeton)

        def build_chat_completion_params(params_from_context):
            params = construire(params_from_context)
            if en_conversation.get():
                try:
                    ligne = ligne_du_travail(moteur)
                    if ligne:
                        cle = "messages" if "messages" in params else "input"
                        params[cle] = inserer_l_etat(list(params[cle]), ligne)
                except Exception as erreur:  # noqa: BLE001
                    logger.error(f"[travail] ligne du travail non montrée : {erreur!r}")
            return params

        llm.get_chat_completions = get_chat_completions
        llm.build_chat_completion_params = build_chat_completion_params
        setattr(llm, _MARQUE_LIGNE, True)
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] ligne du travail non branchée : {erreur!r}")
        return False


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

        async def preparer():
            reglages_, service_ = await preparer_le_service_du_travail(
                reglages_agent,
                configuration,
                organisation,
                getattr(agent, "runtime_configuration", None),
                correlation_id=getattr(fabrique, "_mps_correlation_id", None),
            )
            # fiabilite-orchestration, lot 3 (F5, F6) : même fournisseur, même connexion.
            postes = getattr(fabrique, "postes", None)
            if service_ is not None and postes is not None:
                postes.partager(service_, f"{getattr(agent, 'workflow_name', None) or 'agent'} (fond)")
            return reglages_, service_

        async def refaire_le_service():
            return (await preparer())[1]

        reglages, service = await preparer()
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
            refaire_le_service=refaire_le_service,
        )
        agent.travail = travail
        moteur.travaux.append(travail)
        # fiabilite-orchestration, lot 8 (R12) : la trace du modèle suit le cerveau de fond
        # (case de l'agent), son nom en dit l'appartenance. Ne lève jamais.
        from api.services.pipecat.trace_modele import brancher_la_trace

        nom_agent = getattr(agent, "workflow_name", None)
        brancher_la_trace(
            moteur,
            service,
            reglages_agent,
            f"{nom_agent} (fond)" if nom_agent else "fond",
            parle=False,
        )
        # fiabilite-orchestration, lot 4 (F20, C5) : la garde du modèle du fond, avec son repli.
        from api.services.panne.garde_modele import garder_le_fond

        await garder_le_fond(moteur, agent, service, lambda: travail.worker.context)
        return travail
    except Exception as erreur:  # noqa: BLE001 -- l'agent est joué sans cerveau de fond
        logger.error(f"[travail] cerveau de fond non préparé : {type(erreur).__name__}")
        return None
