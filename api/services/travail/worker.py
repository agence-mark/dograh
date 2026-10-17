"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8) : le worker du cerveau de fond.

``WorkerDeFond`` est une sous-classe de ``BackendLLMWorker`` de Pipecat (R2 : aucun fichier de
Pipecat n'est modifié). Il a son propre contexte et ses propres outils, boucle sur les outils
jusqu'à une réponse finale, et rend cette réponse au demandeur par la réponse du job. **Il ne
dit jamais rien** : aucune sortie ne demande à être parlée (``prefers_spoken`` toujours faux), le
cerveau de conversation seul parle à l'appelant.

Un observateur lit ce que le worker produit sans rien changer : les jetons de chaque requête
(versés au coût de l'appel) et les outils appelés (tracés dans la fiche).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from loguru import logger
from pipecat.frames.frames import FunctionCallInProgressFrame, MetricsFrame
from pipecat.metrics.metrics import LLMUsageMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.workers.llm.backend_llm_worker import BackendLLMWorker, BackendOutput

PREFIXE_DU_NOM = "travail-"


def nom_du_worker(visit_id: str) -> str:
    """Le nom du worker de fond d'une visite d'agent (unique dans l'appel)."""
    return f"{PREFIXE_DU_NOM}{visit_id}"


async def _rien_a_dire(sortie: BackendOutput) -> BackendOutput:
    """Le fond ne parle jamais : même sa réponse finale ne demande pas à être dite."""
    return replace(sortie, prefers_spoken=False)


class ObservateurDuFond(BaseObserver):
    """Lit, sans rien changer, ce que produit le modèle du fond.

    ``jetons(entree, sortie)`` reçoit les jetons de chaque requête payée ; ``outil(nom)`` chaque
    outil appelé (une fois par appel). Un rapport qui lève ne coûte jamais le travail."""

    def __init__(
        self,
        llm: Any,
        *,
        jetons: Callable[[int | None, int | None], None],
        outil: Callable[[str], None],
    ):
        super().__init__()
        self._llm = llm
        self._jetons = jetons
        self._outil = outil
        self._appels_vus: set[str] = set()

    async def on_push_frame(self, data: FramePushed):
        if data.source is not self._llm:
            return
        frame = data.frame
        try:
            if isinstance(frame, MetricsFrame):
                for element in frame.data:
                    if isinstance(element, LLMUsageMetricsData):
                        self._jetons(
                            element.value.prompt_tokens, element.value.completion_tokens
                        )
            elif isinstance(frame, FunctionCallInProgressFrame):
                if frame.tool_call_id not in self._appels_vus:
                    self._appels_vus.add(frame.tool_call_id)
                    self._outil(frame.function_name)
        except Exception as erreur:  # noqa: BLE001 -- une mesure ne coûte jamais le travail
            logger.warning(f"[travail] mesure du fond non lue : {erreur!r}")


class WorkerDeFond(BackendLLMWorker):
    """Le cerveau de fond d'un agent : un job « run » à la fois, ses outils, sa consigne."""

    def __init__(
        self,
        *,
        llm: Any,
        nom: str,
        consigne: str = "",
        jetons: Callable[[int | None, int | None], None] | None = None,
        outil: Callable[[str], None] | None = None,
    ):
        contexte = LLMContext(
            messages=[{"role": "system", "content": consigne}] if consigne else []
        )
        super().__init__(
            llm=llm, context=contexte, name=nom, transform_output=_rien_a_dire
        )
        self._observateur = ObservateurDuFond(
            llm,
            jetons=jetons or (lambda _e, _s: None),
            outil=outil or (lambda _n: None),
        )
        self.add_observer(self._observateur)
