"""[.mark] Chantier ``ordre-outil-puis-parole`` (20/10/2026) : jamais une parole de l'appelant juste après un
résultat d'outil, dans la requête envoyée au modèle.

Depuis R15 (``fiabilite-orchestration``, lot 1), un outil qui rend tout de suite (« confier » qui rend « lancé ») ne
relance plus le modèle quand la même réponse a déjà parlé. L'historique finit alors par le résultat de l'outil, et la
parole suivante (réplique de l'appelant, ou résultat du fond remis comme une parole) arrive juste après lui. Le gabarit
de dialogue de Mistral chez Scaleway (Small 3.2) refuse cet enchaînement : 400 « Unexpected role 'user' after role
'tool' », et l'appel s'arrête (run 1469). Mistral Europe, Large 3 et Qwen l'acceptent ; l'ordre corrigé est accepté
partout (requête du 1469 rejouée le 20/10).

Le correctif : dans la COPIE des messages qui part au modèle (jamais l'historique), la phrase déjà dite par la réponse
qui a appelé les outils est replacée juste après leurs résultats. Le client entend la même chose ; seul l'ordre envoyé
change. Une même réponse peut lancer plusieurs outils (Pipecat range chaque appel avec son résultat) : tout le groupe
est remonté. Les deux formats d'envoi sont couverts : ``messages`` (chat) et ``input`` (API ``responses``, où un appel
est un élément ``function_call`` et son résultat un ``function_call_output``). Sans phrase dite, rien ne change. Aucun
vocabulaire métier, tous fournisseurs.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.interventions_du_moteur import CLE_ORDRE_OUTIL_PUIS_PAROLE, intervention_du_service

APPEL, RESULTAT, PAROLE, APPELANT = "appel", "resultat", "parole", "appelant"


def _texte(contenu: Any) -> str:
    if isinstance(contenu, str):
        return contenu.strip()
    if isinstance(contenu, list):
        return " ".join(
            str(p.get("text") or "") for p in contenu if isinstance(p, dict)
        ).strip()
    return ""


def _nature(message: Any) -> str | None:
    """Ce qu'est un message, dans les deux formats : un appel d'outil, un résultat d'outil, une parole de
    l'assistant, une parole de l'appelant (``user``), ou autre chose (``None``)."""
    if not isinstance(message, dict):
        return None
    if message.get("type") == "function_call":
        return APPEL
    if message.get("role") == "tool" or message.get("type") == "function_call_output":
        return RESULTAT
    role = message.get("role")
    if role == "assistant":
        return APPEL if message.get("tool_calls") else PAROLE
    if role == "user":
        return APPELANT
    return None


def remettre_la_parole_apres_l_outil(messages: list) -> list:
    """Une copie de ``messages`` où aucune parole de l'appelant ne suit directement un résultat d'outil quand la
    réponse qui a appelé les outils avait parlé : cette parole est replacée juste après le dernier résultat du groupe.
    ``messages`` et ses messages ne sont jamais modifiés. ⛔ Ne lève jamais."""
    try:
        sortie = list(messages)
        i = 0
        while i < len(sortie):
            if _nature(sortie[i]) != RESULTAT:
                i += 1
                continue
            # Le groupe : appels et résultats d'une même réponse, d'un seul tenant, jusqu'au dernier résultat.
            fin = i
            while fin + 1 < len(sortie) and _nature(sortie[fin + 1]) in (APPEL, RESULTAT):
                fin += 1
            while _nature(sortie[fin]) != RESULTAT:
                fin -= 1
            if fin + 1 >= len(sortie) or _nature(sortie[fin + 1]) != APPELANT:
                i = fin + 1
                continue
            debut = i
            while debut - 1 >= 0 and _nature(sortie[debut - 1]) in (APPEL, RESULTAT):
                debut -= 1
            parole = None
            for k in range(debut, fin + 1):
                if _nature(sortie[k]) == APPEL and _texte(sortie[k].get("content")):
                    # La parole et l'appel dans le même message : la parole sort, l'appel reste (sans
                    # clé ``content``, comme Pipecat écrit un message d'appel).
                    parole = {"role": "assistant", "content": sortie[k]["content"]}
                    sortie[k] = {c: v for c, v in sortie[k].items() if c != "content"}
                    break
            if parole is None and debut - 1 >= 0 and _nature(sortie[debut - 1]) == PAROLE \
                    and _texte(sortie[debut - 1].get("content")):
                # La parole rangée juste avant le premier appel (le cas de R15) : elle passe après les résultats.
                parole = sortie.pop(debut - 1)
                fin -= 1
            if parole is None:
                logger.debug("[ordre] un résultat d'outil suivi d'une parole, sans phrase à replacer")
                i = fin + 1
                continue
            sortie.insert(fin + 1, parole)
            i = fin + 2
        return sortie
    except Exception as erreur:  # noqa: BLE001 -- dans le doute, la requête part comme avant
        logger.warning(f"[ordre] ordre des messages non corrigé : {erreur!r}")
        return messages


def ordre_outil_puis_parole(params: Any, llm: Any = None) -> Any:
    """Les paramètres d'une requête de conversation, l'ordre corrigé : ``messages`` (chat) ou ``input`` (API
    ``responses``). Appelé à la fin de ``build_chat_completion_params`` des services de modèle du fork (Mistral,
    compatibles OpenAI, Responses)."""
    if not isinstance(params, dict):
        return params
    # Lot 8 de builder-agent-vocal : l'interrupteur de l'agent, posé sur le service (éteint = la requête part comme enregistrée).
    if not intervention_du_service(llm, CLE_ORDRE_OUTIL_PUIS_PAROLE):
        return params
    for cle in ("messages", "input"):
        if isinstance(params.get(cle), list):
            params[cle] = remettre_la_parole_apres_l_outil(params[cle])
    return params
