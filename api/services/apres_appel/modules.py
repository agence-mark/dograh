"""[.mark] The after-call modules (A6, A7): set on the organization, switched on agent by
agent, off by default.

A module is one step of the chain: ``executer(contexte)`` does its sending and returns
what it did, or raises ``ModuleEnEchec`` (retried, A10). A new module = one entry in
``MODULES`` and its name in ``MODULES_CONNUS`` (``api/schemas/apres_appel.py``): the
chain does not change. L5 (connectors) and L6 (SMS) add theirs here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from api.schemas.apres_appel import ApresAppelAgent, ReglagesApresAppel
from api.services.apres_appel.reglages import CleManquante, secret

DELAI_WEBHOOK_S = 10.0
EN_TETE_SECRET = "X-Mark-Secret"


def nouveau_client(**options) -> httpx.AsyncClient:
    """The HTTP client of the modules (a test gives its stand-in here)."""
    return httpx.AsyncClient(**options)


class ModuleEnEchec(RuntimeError):
    """A sending failed. ``definitif``: retrying will not help (a setting is missing)."""

    def __init__(self, message: str, definitif: bool = False):
        super().__init__(message)
        self.definitif = definitif


class ModuleSansObjet(RuntimeError):
    """Nothing to send for this call (the step is shown « skipped », with the reason)."""


@dataclass
class ContexteModule:
    organization_id: int
    run: Any
    reglages: ReglagesApresAppel
    agent: ApresAppelAgent
    envoi: dict
    ecriture: dict = field(default_factory=dict)  # {appel_id, demande_id…} once written
    synthese: str | None = None
    tentative: int = 1
    fuseau: str | None = None  # the organization's timezone, for the texts


@dataclass
class ResultatModule:
    detail: str
    envois: list[dict] = field(default_factory=list)  # [{canal, destinataire, statut}]


Executeur = Callable[[ContexteModule], Awaitable[ResultatModule]]


def charge_utile(contexte: ContexteModule) -> dict:
    """What a module sends about the call: never the transcript, never the organization."""
    envoi = contexte.envoi
    return {
        "run_id": envoi.get("dograh_run_id"),
        "agent_id": envoi.get("dograh_workflow_id"),
        "agent": envoi.get("agent_nom"),
        "etablissement": envoi.get("etablissement"),
        "canal": envoi.get("canal"),
        "sens": envoi.get("sens"),
        "numero_appelant": envoi.get("numero_appelant"),
        "numero_appele": envoi.get("numero_appele"),
        "debut": envoi.get("debut"),
        "duree_s": envoi.get("duree_s"),
        "issue": envoi.get("issue"),
        "motif": envoi.get("motif"),
        "fiche": {c["nom"]: c["valeur"] for c in envoi.get("champs") or []},
        "demande": {
            **(envoi.get("demande") or {}),
            "id": contexte.ecriture.get("demande_id"),
        }
        if envoi.get("demande")
        else None,
        "appel_id": contexte.ecriture.get("appel_id"),
        "synthese": contexte.synthese,
    }


async def _webhook(contexte: ContexteModule) -> ResultatModule:
    reglage = contexte.reglages.webhook
    if not reglage.url:
        raise ModuleEnEchec(
            "No address set for the custom webhook (« After the call »).",
            definitif=True,
        )
    try:
        valeur = await secret(
            reglage.secret, contexte.organization_id, "webhook", "the webhook secret"
        )
    except CleManquante as erreur:
        raise ModuleEnEchec(str(erreur), definitif=True) from None
    try:
        async with nouveau_client(timeout=DELAI_WEBHOOK_S) as client:
            reponse = await client.post(
                reglage.url,
                json=charge_utile(contexte),
                headers={
                    EN_TETE_SECRET: valeur,
                    "Idempotency-Key": f"apres-appel-{contexte.run.id}",
                },
            )
    except httpx.HTTPError as erreur:
        raise ModuleEnEchec(
            f"The webhook does not answer ({type(erreur).__name__})."
        ) from None
    if reponse.status_code >= 400:
        raise ModuleEnEchec(
            f"The webhook answered HTTP {reponse.status_code}.",
            definitif=400 <= reponse.status_code < 500
            and reponse.status_code not in (408, 429),
        )
    return ResultatModule(
        detail=f"HTTP {reponse.status_code}",
        envois=[{"canal": "webhook", "destinataire": reglage.url, "statut": "envoyee"}],
    )


MODULES: dict[str, Executeur] = {
    "webhook": _webhook,
}
