"""[.mark] Le filet des répliques inachevées (chantier repliques-coupees, lot 4, D2 et D10 du 14/10).

Constat du lot 2 (trace du fork, run 1185) : un modèle peut finir sa réponse en pleine phrase avec un
arrêt normal (« Parfait. Vous êtes dans quelle commune, et quel est le », ``finish_reason=stop``). Vu
chez Scaleway avec Qwen3.8 27B en réflexion coupée (``reasoning_effort: none``) : 8 fois sur 15 sur
ce tour-là. Pire que la coupure : la réplique coupée, gardée dans l'historique, est imitée aux tours
suivants (quatre coupures de suite au 1185). Le filet vaut pour tout modèle :

- seules des **phrases finies** partent à la voix ; un reste **sans ponctuation finale** à la fin de
  la réponse n'est **ni dit ni gardé** (l'historique est fait de ce qui est dit), et le modèle
  **reparle une fois** par réplique de l'appelant ;
- D10 : cette relance seule part avec la **réflexion de secours** de l'agent
  (``reflexion_de_relance``, ``low`` pour Qwen3.8 : 0 coupure sur 25 mesurées) ; la requête
  suivante reprend le réglage normal. Vide : la relance part avec le réglage de toujours ;
- la trace va dans ``repliques_inachevees`` (tour, reste retenu, relance oui ou non).

Latence : aucune au téléphone, la voix attend déjà la fin d'une phrase pour la dire.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

# La case de l'agent : la réflexion de la relance d'une réplique inachevée (D10).
CLE_REFLEXION_DE_RELANCE = "reflexion_de_relance"
REFLEXIONS = ("none", "minimal", "low", "medium", "high")
# La trace, dans la fiche de l'appel.
TRACE_INACHEVEES = "repliques_inachevees"
# L'attribut du moteur qui porte l'armement de la relance (le lecteur de portes le lit).
ATTRIBUT_RELANCE = "relance_de_secours"

# Une fin de phrase : « . », « ? », « ! » ou « … », suivis peut-être de guillemets ou de
# parenthèses fermants, puis de blancs.
_FIN_DE_PHRASE = re.compile(r"[.?!…][\s  ]*(?:[»\"”’)][\s  ]*)*")


# Les blancs de fin (insécables compris) et un « | » égaré ne comptent pas.
_BLANCS_DE_FIN = re.compile(r"[\s|]+$")


def fin_de_la_derniere_phrase(texte: str) -> int:
    """La position juste après la dernière phrase finie de ``texte`` (0 : aucune)."""
    fin = 0
    for trouve in _FIN_DE_PHRASE.finditer(texte):
        fin = trouve.end()
    return fin


def est_finie(texte: str) -> bool:
    """``texte`` se termine-t-il sur une phrase finie (les blancs de fin ne comptent pas) ?"""
    nu = _BLANCS_DE_FIN.sub("", texte)
    return bool(nu) and fin_de_la_derniere_phrase(nu) == len(nu)


class ReflexionDeRelanceMixin:
    """Mêlé au service compatible OpenAI (``DograhOpenAILLMService``). Armée par le filet,
    la PROCHAINE réponse de la conversation part avec ``mark_reflexion_de_relance`` ; une
    seule. ``mark_reflexion_de_relance`` à ``None`` (le défaut) : rien ne change."""

    mark_reflexion_de_relance: str | None = None
    _mark_relance_armee: bool = False
    _mark_secours_en_cours: bool = False

    def armer_la_relance(self) -> None:
        if self.mark_reflexion_de_relance:
            self._mark_relance_armee = True

    def desarmer_la_relance(self) -> None:
        self._mark_relance_armee = False

    async def get_chat_completions(self, context):  # type: ignore[override]
        self._mark_secours_en_cours = self._mark_relance_armee
        self._mark_relance_armee = False
        try:
            return await super().get_chat_completions(context)  # type: ignore[misc]
        finally:
            self._mark_secours_en_cours = False

    def _mark_appliquer_le_secours(self, params: dict) -> dict:
        """Appelé dans ``build_chat_completion_params`` : la réflexion de secours, pour la
        seule réponse armée (jamais ``run_inference``, qui ne passe pas ici armé)."""
        if self._mark_secours_en_cours and self.mark_reflexion_de_relance:
            params["reasoning_effort"] = self.mark_reflexion_de_relance
        return params


def brancher_la_relance(engine: Any, llm: Any, run_configs: dict | None) -> None:
    """La réflexion de secours de l'agent sur le service qui la porte, et l'armement sur le
    moteur (le lecteur de portes l'appelle). Valeur absente ou inconnue : rien. Ne lève jamais."""
    try:
        reflexion = (run_configs or {}).get(CLE_REFLEXION_DE_RELANCE)
        if reflexion not in REFLEXIONS or not isinstance(llm, ReflexionDeRelanceMixin):
            return
        llm.mark_reflexion_de_relance = reflexion
        setattr(engine, ATTRIBUT_RELANCE, llm)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[filet] réflexion de relance non branchée : {erreur!r}")
