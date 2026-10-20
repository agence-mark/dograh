"""[.mark] Chantier ``ordre-outil-puis-parole`` (20/10/2026) : jamais une parole de l'appelant juste après un
résultat d'outil, dans la requête envoyée au modèle.

Depuis R15 (``fiabilite-orchestration``, lot 1), un outil qui rend tout de suite (« confier » qui rend « lancé ») ne
relance plus le modèle quand la même réponse a déjà parlé. L'historique finit alors par le résultat de l'outil, et la
parole suivante (réplique de l'appelant, ou résultat du fond remis comme une parole) arrive juste après lui. Le gabarit
de dialogue de Mistral chez Scaleway (Small 3.2) refuse cet enchaînement : 400 « Unexpected role 'user' after role
'tool' », et l'appel s'arrête (run 1469). Mistral Europe, Large 3 et Qwen l'acceptent ; l'ordre corrigé est accepté
partout (requête du 1469 rejouée le 20/10).

Le correctif : dans la COPIE des messages qui part au modèle (jamais l'historique), la phrase déjà dite par la réponse
qui a appelé l'outil est replacée juste après les résultats de l'outil. Le client entend la même chose ; seul l'ordre
envoyé change. Sans phrase dite, rien ne change (journalisé). Aucun vocabulaire métier, tous fournisseurs.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


def _texte(contenu: Any) -> str:
    if isinstance(contenu, str):
        return contenu.strip()
    if isinstance(contenu, list):
        return " ".join(
            str(p.get("text") or "") for p in contenu if isinstance(p, dict)
        ).strip()
    return ""


def _role(message: Any) -> str | None:
    return message.get("role") if isinstance(message, dict) else None


def remettre_la_parole_apres_l_outil(messages: list) -> list:
    """Une copie de ``messages`` où aucun ``user`` ne suit directement un ``tool`` quand la réponse qui a appelé
    l'outil avait parlé : cette parole est replacée juste après les résultats de l'outil. ``messages`` n'est jamais
    modifié ; sans rien à corriger, la même liste est rendue. ⛔ Ne lève jamais."""
    try:
        sortie = list(messages)
        i = 0
        while i < len(sortie):
            if _role(sortie[i]) != "tool":
                i += 1
                continue
            fin = i
            while fin + 1 < len(sortie) and _role(sortie[fin + 1]) == "tool":
                fin += 1
            if fin + 1 >= len(sortie) or _role(sortie[fin + 1]) != "user":
                i = fin + 1
                continue
            appel = i - 1
            if appel < 0 or _role(sortie[appel]) != "assistant" or not sortie[appel].get("tool_calls"):
                i = fin + 1
                continue
            parole = None
            if _texte(sortie[appel].get("content")):
                # La parole et l'appel dans le même message : la parole sort, l'appel reste.
                parole = {"role": "assistant", "content": sortie[appel]["content"]}
                sortie[appel] = {**sortie[appel], "content": None}
            elif appel - 1 >= 0 and _role(sortie[appel - 1]) == "assistant" \
                    and not sortie[appel - 1].get("tool_calls") and _texte(sortie[appel - 1].get("content")):
                # La parole rangée juste avant l'appel (le cas de R15) : elle passe après les résultats.
                parole = sortie.pop(appel - 1)
                i -= 1
                fin -= 1
            if parole is None:
                logger.info("[ordre] un résultat d'outil suivi d'une parole, sans phrase à replacer")
                i = fin + 1
                continue
            sortie.insert(fin + 1, parole)
            i = fin + 2
        return sortie
    except Exception as erreur:  # noqa: BLE001 -- dans le doute, la requête part comme avant
        logger.warning(f"[ordre] ordre des messages non corrigé : {erreur!r}")
        return messages


def ordre_outil_puis_parole(params: Any) -> Any:
    """Les paramètres d'une requête de conversation, l'ordre de ``messages`` corrigé (appelé à la fin de
    ``build_chat_completion_params`` des services de modèle du fork, Mistral et compatibles OpenAI). Une requête sans
    ``messages`` (API ``responses``) part telle quelle."""
    messages = params.get("messages") if isinstance(params, dict) else None
    if isinstance(messages, list):
        params["messages"] = remettre_la_parole_apres_l_outil(messages)
    return params
