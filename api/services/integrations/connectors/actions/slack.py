"""[.mark] Slack (messages): alert the team after a call (U3 sexies, point 8, F3).

State « À essayer ». Documentation read on 03/11/2026: https://docs.slack.dev/reference/methods/
chat.postMessage (``POST https://slack.com/api/chat.postMessage``, JSON body ``channel`` and ``text``,
scope ``chat:write``; the answer is HTTP 200 with ``ok`` false and an ``error`` code on failure).
Through Nango's relay (integration ``slack``).

- ``post_message`` (writes, never anticipated): the channel is the CLIENT's setting, never a value the
  model chooses (it would be a way to write anywhere in his workspace).
"""

from __future__ import annotations

from typing import Any

from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES = {"canal": ""}  # a channel id (C...) or name of the client's workspace
LONGUEUR_MAX = 3000


def _preparer(params: dict, ctx: ContexteAction) -> Requete:
    canal = str({**REGLAGES, **ctx.reglages}.get("canal") or "").strip()
    if not canal:
        raise ValueError("Slack: the channel is not set.")
    texte = str(params["message"]).strip()
    if ctx.modele.motif:
        texte = f"{texte}\nMotif : {ctx.modele.motif}"
    return Requete("POST", "/api/chat.postMessage", json={"channel": canal, "text": texte[:LONGUEUR_MAX]})


def _resultat(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    if not (reponse or {}).get("ok"):
        raise ValueError(f"Slack refused: {(reponse or {}).get('error') or 'unknown'}.")
    return {"publie": True}


SLACK = declarer(
    Connecteur(
        nom="slack",
        libelle="Slack",
        integration="slack",
        actions=(
            Action(
                nom="post_message",
                description="Alert the business's team in its Slack channel with what the caller asked.",
                parametres=(Parametre("message", description="The alert, two sentences at most."),),
                ecrit=True,
                preparer=_preparer,
                resultat=_resultat,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
