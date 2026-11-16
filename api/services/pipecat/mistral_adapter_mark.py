"""[.mark] Mise en forme des messages pour Mistral : un résultat d'outil qui termine la conversation reste le
dernier message.

L'adaptateur de Pipecat range chaque message ``tool`` suivi de rien, ou d'autre chose qu'un ``assistant``, avec un
``assistant`` « » inséré derrière lui, puis pose ``prefix: true`` sur le dernier ``assistant``. Quand le résultat
d'outil est le dernier message (le cas de tout appel enchaîné : choisir le mode puis ajouter, sortie puis finaliser),
Mistral est alors forcé de continuer en TEXTE : il ne peut plus appeler un second outil et annonce à la place ce qu'il
n'a pas fait (défaut C1 des essais au clavier du 17/11/2026).

La documentation de Mistral (function calling) envoie le résultat de l'outil comme dernier message et laisse le
modèle répondre, y compris par un autre appel d'outil (« un modèle peut enchaîner un appel d'outil par un autre »).
L'``assistant`` intercalé reste donc nécessaire seulement quand un message qui n'est pas un ``assistant`` (la parole de
l'appelant) suit le résultat. Pipecat reste intact (sous-module épinglé) : la correction vit ici, branchée par
``adapter_class`` sur le service Mistral de Dograh. Aucun vocabulaire métier.
"""

from __future__ import annotations

import copy
from typing import Any, cast

from openai.types.chat import ChatCompletionMessageParam

from pipecat.adapters.services.mistral_adapter import MistralLLMAdapter


class MarkMistralLLMAdapter(MistralLLMAdapter):
    """``MistralLLMAdapter`` qui n'ajoute jamais d'``assistant`` derrière un résultat d'outil final."""

    def _transform_messages(
        self, messages: list[ChatCompletionMessageParam]
    ) -> list[ChatCompletionMessageParam]:
        if not messages:
            return messages

        msgs: list[dict[str, Any]] = copy.deepcopy([dict(m) for m in messages])

        # Étape 1 : un ``tool`` suivi d'autre chose qu'un ``assistant`` reçoit un ``assistant`` intercalé ;
        # un ``tool`` qui termine la conversation n'en reçoit pas.
        insert_at: list[int] = []
        for i, msg in enumerate(msgs[:-1]):
            if msg.get("role") == "tool" and msgs[i + 1].get("role") != "assistant":
                insert_at.append(i + 1)
        for idx in reversed(insert_at):
            msgs.insert(idx, {"role": "assistant", "content": " "})

        # Étape 2 : Mistral ne permet de ``system`` qu'en tête.
        premier = next((i for i, m in enumerate(msgs) if m.get("role") != "system"), len(msgs))
        for i in range(premier, len(msgs)):
            if msgs[i].get("role") == "system":
                msgs[i]["role"] = "user"

        # Étape 3 : un ``assistant`` final demande ``prefix``.
        dernier = msgs[-1]
        if dernier.get("role") == "assistant" and "prefix" not in dernier:
            dernier["prefix"] = True

        return cast(list[ChatCompletionMessageParam], msgs)
