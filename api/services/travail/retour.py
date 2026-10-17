"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8) : le retour du résultat, gardé.

Le résultat d'un travail de fond entre dans la conversation de l'appel comme un message
``[Résultat du travail : …]`` (``groupe.passations.est_un_resultat_de_travail`` : jamais lu comme
une parole de l'appelant, exclu des historiques de passation, du greffier et des indices), avec
``run_llm=True`` : le cerveau de conversation le dit à l'appelant avec ses mots.

Trois règles :

1. **Gardé** : tant que le robot parle, que l'appelant parle, qu'une réponse est en cours ou
   qu'une passation s'exécute, le résultat attend (même logique que ``relance_apres_outil`` : une
   relance du modèle pendant un tour de l'appelant ferait un second tour). Un nouveau tour de
   l'appelant n'est jamais coupé par un résultat.
2. **Routé vers l'agent qui a la main** : l'agent ACTIF au moment de la remise, jamais celui qui
   avait confié. Un résultat qui arrive après une passation est lu par le nouvel agent.
3. **Perdu seulement avec l'appel** : la remise est une tâche du fond ; la fin de l'appel
   l'annule (le résultat est trop tard, personne n'écoute).
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger
from pipecat.frames.frames import LLMMessagesAppendFrame

from api.services.groupe.passations import PREFIXE_RESULTAT_DU_TRAVAIL

# Le rythme auquel la remise regarde si l'appel est redevenu calme.
PAS_D_ATTENTE_S = 0.1

TEXTE_VIDE = "aucun résultat"
TEXTE_ECHEC = "le travail n'a pas abouti"
TEXTE_DELAI = "le travail n'a pas abouti dans le temps imparti"


def message_du_resultat(texte: str) -> str:
    """Le message du résultat, tel qu'il entre dans la conversation. Relecture du lot 6 : les
    crochets du résultat (texte d'un outil externe) deviennent des parenthèses, pour qu'il ne ferme
    jamais le message plus tôt ni n'imite un message du code (``[Fiche…``, ``[Résultat…``)."""
    contenu = " ".join(str(texte or "").split()) or TEXTE_VIDE
    contenu = contenu.replace("[", "(").replace("]", ")")
    return f"{PREFIXE_RESULTAT_DU_TRAVAIL} {contenu}]"


def appel_au_calme(moteur: Any) -> bool:
    """Le moment où le code peut parler au cerveau de conversation sans couper personne : un agent
    a la main (pas de passation en cours), ni le robot ni l'appelant ne parlent, aucune réponse
    n'est en cours."""
    if moteur.is_call_disposed() or moteur.transfer_in_progress:
        return False
    if moteur.selected_visit_id is None:
        return False
    return bool(moteur.call_monitor.appel_au_calme)


async def attendre_le_calme(moteur: Any, *, pas_s: float = PAS_D_ATTENTE_S) -> bool:
    """Attend que l'appel soit calme. ``False`` si l'appel s'est terminé avant. Annulable."""
    while True:
        if moteur.is_call_disposed():
            return False
        if appel_au_calme(moteur):
            return True
        await asyncio.sleep(pas_s)


async def remettre_le_resultat(moteur: Any, message: str) -> bool:
    """Pousse ``message`` à l'agent qui a la main, quand l'appel est calme, avec ``run_llm=True``.
    ``True`` si le message est parti. ⛔ Ne lève jamais (hors annulation)."""
    try:
        if not await attendre_le_calme(moteur):
            logger.info("[travail] appel terminé avant la remise du résultat : perdu")
            return False
        agent = moteur.active_agent
        if not moteur.agent_can_act(agent):
            return False
        moteur.expect_response()
        await agent.queue_frame(
            LLMMessagesAppendFrame([{"role": "user", "content": message}], run_llm=True)
        )
        return True
    except asyncio.CancelledError:
        raise
    except Exception as erreur:  # noqa: BLE001 -- jamais l'appel
        logger.error(f"[travail] résultat non remis : {erreur!r}")
        return False
