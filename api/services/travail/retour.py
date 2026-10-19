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
4. **Jamais par-dessus une question** (18/10, runs 1460 et 1461) : si la dernière réplique de
   l'agent est une question encore sans réponse, le résultat entre dans la conversation SANS
   réveiller le modèle ; il est lu à la réponse de l'appelant. Sinon (l'agent s'est tu sans
   question, l'appelant attend), il réveille le modèle comme avant.
5. **Avec la réplique de l'appelant** (fiabilite-orchestration, lot 1, F1 ; run 1468 : le résultat
   a déclenché une réplique pendant que l'appelant dictait son mail) : l'appelant parle et l'agent
   est au repos, le résultat est posé sans réveiller le modèle ; la fin de son tour fait répondre
   le modèle, qui le lit avec sa réplique.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from loguru import logger
from pipecat.frames.frames import LLMMessagesAppendFrame, LLMRunFrame

from api.services.groupe.passations import (
    PREFIXE_RESULTAT_DU_TRAVAIL,
    est_la_note_de_passation,
    est_un_resultat_de_travail,
)

# Le rythme auquel la remise regarde si l'appel est redevenu calme.
PAS_D_ATTENTE_S = 0.1

TEXTE_VIDE = "aucun résultat"
TEXTE_ECHEC = "le travail n'a pas abouti"
TEXTE_DELAI = "le travail n'a pas abouti dans le temps imparti"


# fiabilite-orchestration (lot 7, R4, run 1468) : le fond répond en markdown (« **Résultat** : … »), le
# cerveau de conversation l'imite et la voix lit les astérisques. Le résultat est remis en texte simple.
_LIEN_MARKDOWN = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TITRE_OU_PUCE = re.compile(r"^[ 	]*(?:#{1,6}[ 	]*|>[ 	]*|[-+*•][ 	]+)", re.MULTILINE)
_SOULIGNE_GRAS = re.compile(r"(?<![\w])__(.+?)__(?![\w])")


def sans_mise_en_forme(texte: str) -> str:
    """``texte`` sans markdown : astérisques (gras, italique), dièses de titre, puces, citations,
    soulignés gras, accents graves, liens réduits à leur texte. Le sens et les mots restent."""
    propre = _LIEN_MARKDOWN.sub(r"\1", str(texte or ""))
    propre = _TITRE_OU_PUCE.sub("", propre)
    propre = _SOULIGNE_GRAS.sub(r"\1", propre)
    return propre.replace("*", "").replace("`", "")


def message_du_resultat(texte: str) -> str:
    """Le message du résultat, tel qu'il entre dans la conversation. Relecture du lot 6 : les
    crochets du résultat (texte d'un outil externe) deviennent des parenthèses, pour qu'il ne ferme
    jamais le message plus tôt ni n'imite un message du code (``[Fiche…``, ``[Résultat…``)."""
    contenu = " ".join(sans_mise_en_forme(texte).split()) or TEXTE_VIDE
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


def _texte(contenu: Any) -> str:
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return " ".join(
            str(p.get("text") or "") for p in contenu if isinstance(p, dict)
        )
    return ""


def question_en_suspens(messages: Any) -> bool:
    """La dernière parole de la conversation est-elle une question de l'agent, encore sans
    réponse de l'appelant ? Les messages du code (résultat d'un travail, note de passation) et les
    messages d'outil ne comptent pas comme une réponse. ⛔ Ne lève jamais."""
    try:
        for message in reversed(list(messages or [])):
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role == "user":
                if est_un_resultat_de_travail(message) or est_la_note_de_passation(message):
                    continue
                return False
            if role == "assistant":
                texte = _texte(message.get("content")).strip()
                if not texte:
                    continue  # un appel d'outil, sans parole
                return "?" in texte
        return False
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] conversation illisible : {erreur!r}")
        return False


def _l_appelant_parle_seul(moteur: Any) -> bool:
    """Lot 1 de fiabilite-orchestration : l'appelant parle, l'agent est au repos (ni voix, ni
    réponse en cours), aucune passation. Le résultat peut alors partir AVEC sa réplique."""
    if moteur.is_call_disposed() or moteur.transfer_in_progress:
        return False
    if moteur.selected_visit_id is None:
        return False
    moniteur = moteur.call_monitor
    return bool(moniteur.appelant_parle and moniteur.agent_au_repos)


async def _attendre_le_moment(moteur: Any, *, pas_s: float = PAS_D_ATTENTE_S) -> bool:
    """L'appel est calme, ou l'appelant parle seul. ``False`` si l'appel s'est terminé avant."""
    while True:
        if moteur.is_call_disposed():
            return False
        if appel_au_calme(moteur) or _l_appelant_parle_seul(moteur):
            return True
        await asyncio.sleep(pas_s)


# Après une remise glissée dans la réplique de l'appelant : combien de temps on attend que la fin
# de son tour fasse répondre le modèle avant de le réveiller soi-même.
ATTENTE_DE_LA_REPONSE_S = 3.0
ATTENTE_MAX_DE_LA_REPLIQUE_S = 30.0
_VEILLES: set[asyncio.Task] = set()


def _repondu_apres(messages: Any, message: str) -> bool | None:
    """Le modèle a-t-il parlé après ``message`` ? ``None`` si ``message`` n'est pas (plus) là."""
    liste = list(messages or [])
    for i in range(len(liste) - 1, -1, -1):
        m = liste[i]
        if isinstance(m, dict) and m.get("role") == "user" and _texte(m.get("content")) == message:
            return any(
                isinstance(x, dict) and x.get("role") == "assistant" for x in liste[i + 1 :]
            )
    return None


async def _veiller_sur_la_replique(moteur: Any, agent: Any, message: str) -> None:
    """Le résultat est parti avec la réplique de l'appelant : à la fin de son tour, le modèle
    répond et le lit. Si son tour se termine sans réponse (bruit écarté), le résultat ne reste pas
    en souffrance : le modèle est réveillé une fois, au calme."""
    limite = time.monotonic() + ATTENTE_MAX_DE_LA_REPLIQUE_S
    while moteur.call_monitor.appelant_parle and time.monotonic() < limite:
        if moteur.is_call_disposed():
            return
        await asyncio.sleep(PAS_D_ATTENTE_S)
    await asyncio.sleep(ATTENTE_DE_LA_REPONSE_S)
    if not await attendre_le_calme(moteur) or moteur.active_agent is not agent:
        return
    contexte = getattr(moteur, "context", None)
    if _repondu_apres(contexte.get_messages() if contexte else [], message) is not False:
        return
    if not moteur.agent_can_act(agent):
        return
    logger.info("[travail] réplique de l'appelant sans réponse : le modèle lit le résultat")
    moteur.expect_response()
    await agent.queue_frame(LLMRunFrame())


async def remettre_le_resultat(moteur: Any, message: str) -> bool:
    """Pousse ``message`` à l'agent qui a la main, au bon moment (lot 1 de fiabilite-orchestration,
    F1) : l'appel calme, il réveille le modèle (``run_llm=True``), sauf si une question de l'agent
    attend sa réponse (règle 4) ; l'appelant en train de parler, il part **avec sa réplique**
    (posé sans réveiller : la fin de son tour fait répondre le modèle, qui le lit). ``True`` si le
    message est parti. ⛔ Ne lève jamais (hors annulation)."""
    try:
        if not await _attendre_le_moment(moteur):
            logger.info("[travail] appel terminé avant la remise du résultat : perdu")
            return False
        agent = moteur.active_agent
        if not moteur.agent_can_act(agent):
            return False
        avec_la_replique = not appel_au_calme(moteur) and _l_appelant_parle_seul(moteur)
        contexte = getattr(moteur, "context", None)
        attendre = avec_la_replique or question_en_suspens(
            contexte.get_messages() if contexte else []
        )
        if not attendre:
            moteur.expect_response()
        await agent.queue_frame(
            LLMMessagesAppendFrame([{"role": "user", "content": message}], run_llm=not attendre)
        )
        if avec_la_replique:
            logger.info("[travail] résultat posé dans la réplique de l'appelant")
            # Hors de la tâche du travail : le travail est remis, il n'est plus « en cours ».
            veille = asyncio.get_running_loop().create_task(
                _veiller_sur_la_replique(moteur, agent, message), name="travail:veille"
            )
            _VEILLES.add(veille)
            veille.add_done_callback(_VEILLES.discard)
        elif attendre:
            logger.info("[travail] résultat posé sans réveiller le modèle : une question attend sa réponse")
        return True
    except asyncio.CancelledError:
        raise
    except Exception as erreur:  # noqa: BLE001 -- jamais l'appel
        logger.error(f"[travail] résultat non remis : {erreur!r}")
        return False
