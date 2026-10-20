"""[.mark] Chantier fiabilite-orchestration (lot 1, R15) : la réponse a-t-elle parlé avant ses outils ?

Au 1463, « Je regarde les disponibilités. Avez-vous une adresse mail ? » a été dit deux fois : le
modèle a parlé **et** appelé ``confier_le_travail`` dans la même réponse, l'outil a rendu « lancé »
aussitôt, et la relance après outil a réinterrogé le modèle, qui a redit sa phrase. Règle générale :
un outil qui rend tout de suite ne relance pas le modèle quand la même réponse portait déjà une
phrase. Ce module relève, pour chaque appel d'outil, si du texte est parti à la voix avant lui dans
la même réponse.

Trois points d'accroche du service de modèle (ceux du A1 de la fiche,
``fiche_au_fil_de_leau.ACCROCHES_A1``), enveloppés **une fois** par service : un service partagé
par plusieurs agents (préchauffage hybride) garde un seul suivi. Absents (autre fournisseur, montée
de Pipecat), rien n'est su : ``a_parle_avant`` rend faux et le comportement d'avant reste.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from loguru import logger

ACCROCHES = ("_process_context", "_push_llm_text", "_run_or_defer_function_calls")
_MARQUE = "_mark_parole_avant_outil"


class SuiviDeLaParole:
    def __init__(self) -> None:
        self.texte = ""
        self._apres_parole: set[str] = set()

    def reponse_commencee(self) -> None:
        self.texte = ""

    def appels_emis(self, appels: Iterable[Any]) -> None:
        if self.texte.strip():
            self._apres_parole.update(
                str(getattr(a, "tool_call_id", "") or "") for a in appels or []
            )
        self.texte = ""

    def a_parle_avant(self, tool_call_id: Any) -> bool:
        """La réponse qui a émis cet appel avait-elle déjà parlé ? (lu une fois)"""
        cle = str(tool_call_id or "")
        if cle and cle in self._apres_parole:
            self._apres_parole.discard(cle)
            return True
        return False


def suivre_la_parole(llm: Any) -> SuiviDeLaParole | None:
    """Le suivi de ``llm``, branché à la première demande. ``None`` sans les points d'accroche.
    ⛔ Ne lève jamais."""
    try:
        deja = getattr(llm, _MARQUE, None)
        if isinstance(deja, SuiviDeLaParole):
            return deja
        if not all(hasattr(llm, nom) for nom in ACCROCHES):
            logger.warning(
                f"[outil] {type(llm).__name__} sans {', '.join(ACCROCHES)} : la parole avant "
                "un outil n'est pas suivie"
            )
            return None
        suivi = SuiviDeLaParole()
        traiter = llm._process_context
        pousser = llm._push_llm_text
        emettre = llm._run_or_defer_function_calls

        async def _process_context(context):
            suivi.reponse_commencee()
            return await traiter(context)

        async def _push_llm_text(text):
            suivi.texte += text or ""
            return await pousser(text)

        async def _run_or_defer_function_calls(function_calls, **kwargs):
            suivi.appels_emis(function_calls or [])
            return await emettre(function_calls, **kwargs)

        llm._process_context = _process_context
        llm._push_llm_text = _push_llm_text
        llm._run_or_defer_function_calls = _run_or_defer_function_calls
        setattr(llm, _MARQUE, suivi)
        return suivi
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[outil] suivi de la parole non branché : {erreur!r}")
        return None
