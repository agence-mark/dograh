"""[.mark] Module Restauration, lot 21 : le DIRECT DES APPELS, branché sur le déroulé RÉEL de l'appel (côté fork, jamais dans Pipecat, R9).

Pour un agent qui porte le module de commande (son interrupteur ``commande_sur_catalogue``) et dont l'appel sert un établissement connu de la base du client où le module Restauration est allumé, ce que l'appel dit
passe aussi dans le flux du lot 22 : ``appel.commence`` au décroché, ``appel.tour`` (la transcription FINALE seulement, D11 ; ce que dit l'agent en entier), ``appel.outil``
(appelé, terminé) et ``appel.fini`` avec son motif, quoi qu'il arrive à l'appel (coupure comprise : l'appel quitte « en cours » à la fin). Le portail le lit (lot 15) ; le fork n'affiche
rien (F17 : aucune pastille « En appel »).

Comment : le canal d'événements de l'appel (``ws_sender``, que l'observateur de l'amont appelle pour chaque événement) est COMPOSÉ avec le nôtre ; l'amont n'est pas touché. Le direct ne
fait JAMAIS attendre l'appel (R1) : chaque événement est déposé dans une file en mémoire et une seule tâche par appel écrit dans le flux, dans l'ordre, chaque écriture bornée ;
un flux en panne s'écrit au journal d'erreur et l'appel continue. Cloisonné par construction : la clé du flux porte l'organisation ET l'établissement de l'appel (``flux.cle_du_flux``).

Le motif de fin se lit dans le classeur, pas dans le nom d'un outil : une commande ou une réservation de CET appel (``appel_id`` = l'identifiant de l'exécution) -> « Commande » ou
« Réservation » ; sinon, l'appelant a parlé -> « Question » ; sinon -> « Abandonné ». « Réclamation » : l'appel est passé par ``passage_de_main`` avec le motif ``plainte`` (connecteur service, lot 7 ; la mesure de la fiche de l'appel), elle prime sur le reste.
Aucune donnée n'est gardée ici : le flux a sa propre durée de vie (lot 22) et le classeur ses règles de conservation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from api.db.bases_clients import connexion as base_client
from api.services.integrations.connectors import mesures
from api.services.restauration import flux
from api.services.restauration.appel import LieuIntrouvable, identifiant_de_l_etablissement

Envoi = Callable[[dict], Awaitable[None]]
DELAI_FERMETURE_S = 3.0
SIGNAUX_DE_FIN = {
    "Commande": "SELECT EXISTS (SELECT 1 FROM mark.resto_commande WHERE site_id = $1 AND appel_id = $2)",
    "Réservation": "SELECT EXISTS (SELECT 1 FROM mark.resto_reservation WHERE site_id = $1 AND appel_id = $2)",
}


class DirectDeLAppel:
    def __init__(self, organisation_id: int, etablissement_id: int, nom_base: str, agent_id: int, appel_id: int, telephone: str | None):
        self.organisation_id, self.etablissement_id, self.nom_base = organisation_id, etablissement_id, nom_base
        self.agent_id, self.appel_id, self.telephone = agent_id, appel_id, telephone
        self._file: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
        self._tache = asyncio.create_task(self._ecrire())
        self._appelant_a_parle = False
        self._fini = False

    # ---- l'écriture, hors de l'appel
    async def _ecrire(self) -> None:
        while True:
            element = await self._file.get()
            if element is None:
                return
            type_, donnees = element
            try:
                if type_ == "appel.tour":
                    await flux.emettre_tour_final(self.organisation_id, self.etablissement_id, self.appel_id, donnees["role"], donnees["texte"], final=True)
                else:
                    await flux.emettre(self.organisation_id, self.etablissement_id, type_, {"appel_id": str(self.appel_id), **donnees})
            except Exception as erreur:  # noqa: BLE001 -- R1 : une panne du flux ne casse jamais l'appel
                logger.error(f"[.mark] Call feed {type_} for run {self.appel_id} not written: {type(erreur).__name__}")

    def _deposer(self, type_: str, donnees: dict[str, Any]) -> None:
        if not self._fini:
            self._file.put_nowait((type_, donnees))

    # ---- ce que fait l'appel
    def commencer(self) -> None:
        self._deposer("appel.commence", {"agent_id": str(self.agent_id), "telephone_masque": flux.masquer_telephone(self.telephone)})

    def sur_evenement(self, message: dict[str, Any]) -> None:
        """Un événement du pipeline : traduit par ``flux.depuis_le_pipeline`` (le provisoire, le technique et le hors contrat n'y entrent pas)."""
        try:
            traduit = flux.depuis_le_pipeline(message)
        except Exception:  # noqa: BLE001 -- R1
            return
        if traduit is None:
            return
        type_, donnees = traduit
        if type_ == "appel.tour" and donnees["role"] == "appelant":
            self._appelant_a_parle = True
        self._deposer(type_, donnees)

    def composer(self, original: Envoi | None) -> Envoi:
        """Le canal de l'appel : le nôtre d'abord (il ne lève jamais et rend la main), puis celui de l'amont, tel qu'il est (ce qu'il lève, il le lève comme avant)."""

        async def envoyer(message: dict) -> None:
            self.sur_evenement(message)
            if original is not None:
                await original(message)

        return envoyer

    @staticmethod
    def _plainte(fiche: Any) -> bool:
        try:
            return any(m.get("detail") == "plainte" for m in mesures.lues(fiche) if m.get("mesure") == "service.passage_de_main")
        except Exception:  # noqa: BLE001
            return False

    async def _motif(self, fiche: Any = None) -> str:
        if self._plainte(fiche):
            return "Réclamation"
        try:
            connexion = await base_client.connecter(self.nom_base)
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"[.mark] Call feed end of run {self.appel_id}: no connection ({type(erreur).__name__})")
            connexion = None
        if connexion is not None:
            try:
                for motif, requete in SIGNAUX_DE_FIN.items():
                    if await connexion.fetchval(requete, self.etablissement_id, str(self.appel_id)):
                        return motif
            except Exception as erreur:  # noqa: BLE001
                logger.error(f"[.mark] Call feed end of run {self.appel_id}: reason not read ({type(erreur).__name__})")
            finally:
                await connexion.close()
        return "Question" if self._appelant_a_parle else "Abandonné"

    async def fermer(self, fiche: Any = None) -> None:
        """La fin de l'appel, quoi qu'il arrive : ``appel.fini`` (une seule fois), puis la file se vide dans un délai borné. Ne lève jamais."""
        if self._fini:
            return
        try:
            motif = await asyncio.wait_for(self._motif(fiche), DELAI_FERMETURE_S)
        except Exception:  # noqa: BLE001 -- jamais un appel qui reste « en cours » parce que le motif n'a pas pu se lire
            motif = "Réclamation" if self._plainte(fiche) else "Question" if self._appelant_a_parle else "Abandonné"
        self._deposer("appel.fini", {"motif": motif})
        self._fini = True
        self._file.put_nowait(None)
        try:
            await asyncio.wait_for(asyncio.shield(self._tache), DELAI_FERMETURE_S)
        except Exception as erreur:  # noqa: BLE001
            self._tache.cancel()
            logger.error(f"[.mark] Call feed of run {self.appel_id} not closed: {type(erreur).__name__}")


async def preparer_le_direct(
    *, organisation_id: int | None, workflow_id: int, workflow_run_id: int, run_configs: dict | None, cle_etablissement: str | None, contexte: dict | None
) -> DirectDeLAppel | None:
    """Le direct de cet appel, ou ``None`` (agent sans le module, établissement inconnu, base indisponible) : l'appel est alors celui d'avant, à l'octet. Ne lève jamais."""
    try:
        from api.services.base_client.rattachement import nom_de_la_base
        from api.services.modules.etat import interrupteur_allume
        from api.services.modules.registre import MODULES

        module = next((m for m in MODULES if m.code == "commande"), None)
        if organisation_id is None or module is None or not cle_etablissement or not interrupteur_allume(module, run_configs):
            return None
        nom_base = await nom_de_la_base(organisation_id)
        if not nom_base:
            return None
        connexion = await base_client.connecter(nom_base)
        try:
            etablissement_id = await identifiant_de_l_etablissement(connexion, cle_etablissement)
            # Le module Restauration doit aussi être allumé pour CET établissement (le signal que lisent le portail et le fork : ``resto_reglage.module_actif``).
            if not await connexion.fetchval("SELECT EXISTS (SELECT 1 FROM mark.resto_reglage WHERE site_id = $1 AND module_actif)", etablissement_id):
                return None
        finally:
            await connexion.close()
        telephone = (contexte or {}).get("caller_number")
        return DirectDeLAppel(organisation_id, etablissement_id, nom_base, workflow_id, workflow_run_id, telephone if isinstance(telephone, str) else None)
    except LieuIntrouvable:
        return None
    except Exception as erreur:  # noqa: BLE001 -- R1 : sans direct, l'appel se passe comme avant
        logger.error(f"[.mark] Call feed not prepared for run {workflow_run_id}: {type(erreur).__name__}")
        return None
