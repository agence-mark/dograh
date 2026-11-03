"""[.mark] Crisp (support): open a conversation with the caller's request (U3 sexies, point 8, F3).

State « À essayer ». Documentation read on 03/11/2026: https://docs.crisp.chat/references/rest-api/v1/
(``POST /v1/website/{website_id}/conversation``, 201, a new conversation stays hidden from the inbox
until a message is sent with ``from`` = ``user``; ``POST /v1/website/{website_id}/conversation/
{session_id}/message``, 202, body ``type``, ``from``, ``origin``, ``content``). ⚠️ NOT confirmed by
the pages read: the answer of the creation (``data.session_id`` is the usual field), the
authentication scheme (Basic with identifier and key, header ``X-Crisp-Tier``, left to Nango's
provider). To check on a test website. Through Nango's relay (integration ``crisp``).

- ``create_conversation`` (writes): two requests, the second built from the first answer
  (``suite``): the conversation, then the caller's request as his first message.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from api.services.integrations.connectors import nango
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES = {"site": ""}  # website id (a UUID)


def _site(ctx: ContexteAction) -> str:
    site = str({**REGLAGES, **ctx.reglages}.get("site") or "").strip()
    if not site:
        raise ValueError("Crisp: the website is not set.")
    return quote(site, safe="")


def _preparer(_params: dict, ctx: ContexteAction) -> Requete:
    return Requete("POST", f"/v1/website/{_site(ctx)}/conversation", json={})


async def _premier_message(reponse: Any, params: dict, ctx: ContexteAction) -> Any:
    session = ((reponse or {}).get("data") or {}).get("session_id")
    if not session or ctx.organization_id is None:
        raise ValueError("Crisp gave no conversation.")
    c = ctx.modele.contact
    texte = str(params["message"]).strip()
    if c.telephone:
        texte = f"{texte}\n\nTéléphone : {c.telephone}"
    await nango.relayer(
        ctx.organization_id,
        "crisp",
        Requete(
            "POST",
            f"/v1/website/{_site(ctx)}/conversation/{quote(str(session), safe='')}/message",
            json={"type": "text", "from": "user", "origin": "chat", "content": texte},
        ),
        delai=5.0,
        compte=ctx.compte,
    )
    return reponse


def _resultat(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    session = ((reponse or {}).get("data") or {}).get("session_id")
    if not session:
        raise ValueError("Crisp gave no conversation.")
    return {"cree": True, "identifiant": str(session)}


CRISP = declarer(
    Connecteur(
        nom="crisp",
        libelle="Crisp",
        integration="crisp",
        actions=(
            Action(
                nom="create_conversation",
                description="Open a conversation in the business's Crisp inbox with the caller's request.",
                parametres=(Parametre("message", description="What the caller asked, complete."),),
                ecrit=True,
                preparer=_preparer,
                resultat=_resultat,
                suite=_premier_message,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
