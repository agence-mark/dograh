"""[.mark] Running an action of the catalogue (plan connecteurs-agent D6 to D9, D17, D18).

- The organization is the ENGINE's (D6), passed by the caller; the model's arguments are cut
  down to the parameters the action declares (an ``organization_id`` the model sends is
  dropped, like any other undeclared key).
- Synchronous during the call (D7): a waiting phrase, a deadline (5 s by default); past it or
  on an error, the fallback phrase, and an action that WRITES is put aside for the after-call
  (``connecteurs_differes`` in the record), retried by the after-call module ``connecteurs``
  (A1, A6: no n8n). Every run is stamped (``connecteurs`` in the record): action, duration,
  outcome, anticipated or not and the time saved (D18).
- The agent receives the useful result only (D8).
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from api.services.integrations.connectors import nango
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    trouver,
)
from api.services.integrations.connectors.modele_commun import depuis_la_fiche

CLE_ESTAMPILLE = "connecteurs"
CLE_DIFFERES = "connecteurs_differes"
DELAI_DEFAUT_MS = 5000
PHRASE_REPLI_DEFAUT = "Je transmets votre demande, on vous rappelle pour la confirmer."


class ActionInconnue(ValueError):
    pass


@dataclass
class Resultat:
    statut: str  # ok | repli | erreur
    donnees: dict[str, Any] = field(default_factory=dict)
    duree_ms: int = 0
    message: str | None = None


def arguments_permis(
    action: Action, arguments: dict[str, Any] | None
) -> dict[str, Any]:
    """Only the declared parameters, never anything else the model sends (D6)."""
    noms = {p.nom for p in action.parametres}
    return {
        k: v for k, v in (arguments or {}).items() if k in noms and v not in (None, "")
    }


def manquants(action: Action, arguments: dict[str, Any]) -> list[str]:
    return [
        p.nom for p in action.parametres if p.obligatoire and p.nom not in arguments
    ]


def contexte_de(
    action: Action,
    reglages: dict | None,
    fiche: dict | None,
    numero: str | None = None,
    *,
    organization_id: int | None = None,
    appel: dict | None = None,
    run_id: int | None = None,
) -> ContexteAction:
    extraites = (
        (fiche or {}).get("extracted_variables")
        if isinstance((fiche or {}).get("extracted_variables"), dict)
        else (fiche or {})
    )
    return ContexteAction(
        reglages={**action.reglages_par_defaut, **(reglages or {})},
        modele=depuis_la_fiche(extraites or {}, None, numero),
        organization_id=organization_id,
        appel=dict(appel or {}),
        run_id=run_id,
        fiche=fiche if isinstance(fiche, dict) else None,
    )


async def appeler(
    organization_id: int,
    connecteur: Connecteur,
    action: Action,
    arguments: dict,
    ctx: ContexteAction,
    delai_s: float,
) -> dict:
    """One action, through the relay of THIS organization's connection. Raises on failure.

    l-agent-collegue (L5): an internal connector's action is computed in the fork
    (``executer_interne``), never sent to the relay; the organization is the engine's."""
    if connecteur.interne:
        if connecteur.executer_interne is None:
            raise RuntimeError("An internal action never goes through the relay.")
        if ctx.organization_id is None:
            ctx = dataclasses.replace(ctx, organization_id=organization_id)
        return await connecteur.executer_interne(action, arguments, ctx, delai_s)
    requetes = action.preparer(arguments, ctx)
    requetes = requetes if isinstance(requetes, list) else [requetes]
    reponse: Any = None
    for requete in requetes:
        reponse = await nango.relayer(
            organization_id,
            connecteur.integration,
            requete,
            delai=delai_s,
            base_url=connecteur.base_url,
        )
    if action.suite is not None:
        reponse = await action.suite(reponse, arguments, ctx)
    return action.resultat(reponse, arguments, ctx)


async def executer(
    organization_id: int,
    config: dict,
    arguments: dict | None,
    fiche: dict | None = None,
    numero: str | None = None,
    anticipee: asyncio.Future | None = None,
    appel: dict | None = None,
    run_id: int | None = None,
) -> Resultat:
    """Run the tool's action within its deadline. Never raises: an error is a fallback."""
    trouve = trouver(config.get("connecteur", ""), config.get("action", ""))
    if trouve is None:
        raise ActionInconnue(
            f"Unknown action « {config.get('connecteur')}.{config.get('action')} »."
        )
    connecteur, action = trouve
    args = arguments_permis(action, arguments)
    absents = manquants(action, args)
    if absents:
        return Resultat(
            "erreur",
            {"manque": absents},
            message=f"Ask the caller for: {', '.join(absents)}.",
        )
    delai_s = max(
        0.5, min(float(config.get("delai_ms") or DELAI_DEFAUT_MS), 15000) / 1000
    )
    ctx = contexte_de(
        action,
        config.get("reglages"),
        fiche,
        numero,
        organization_id=organization_id,
        appel=appel,
        run_id=run_id,
    )
    debut = time.monotonic()
    try:
        if anticipee is not None:
            donnees = await asyncio.wait_for(asyncio.shield(anticipee), timeout=delai_s)
        else:
            donnees = await asyncio.wait_for(
                appeler(organization_id, connecteur, action, args, ctx, delai_s),
                timeout=delai_s,
            )
        resultat = Resultat("ok", donnees, int((time.monotonic() - debut) * 1000))
        noter_au_hub(fiche, action, donnees, args, ctx)
        return resultat
    except (
        asyncio.TimeoutError,
        nango.NangoIndisponible,
        nango.ConnexionAbsente,
    ) as erreur:
        message = (
            "deadline passed"
            if isinstance(erreur, asyncio.TimeoutError)
            else str(erreur)
        )
    except Exception as erreur:  # noqa: BLE001 -- R1: logged, never swallowed in silence
        logger.error(
            f"[.mark] Connector action {connecteur.nom}.{action.nom} failed: {erreur!r}"
        )
        message = f"{type(erreur).__name__}"
    return Resultat("repli", {}, int((time.monotonic() - debut) * 1000), message)


def estampiller(fiche: dict | None, entree: dict) -> None:
    if isinstance(fiche, dict):
        fiche.setdefault(CLE_ESTAMPILLE, []).append(entree)


def mettre_de_cote(fiche: dict | None, config: dict, arguments: dict) -> None:
    """A writing action that fell back: retried after the call (module ``connecteurs``)."""
    if isinstance(fiche, dict):
        fiche.setdefault(CLE_DIFFERES, []).append(
            {
                "connecteur": config.get("connecteur"),
                "action": config.get("action"),
                "reglages": config.get("reglages") or {},
                "arguments": arguments,
            }
        )


CLE_HUB = "hub_rendez_vous"


def noter_au_hub(
    fiche: dict | None, action: Action, donnees: dict, arguments: dict, ctx: ContexteAction
) -> None:
    """l-agent-collegue (H6): what the action leaves for the hub, written after the call.
    Never raises: a note lost is logged, the call goes on."""
    if action.au_hub is None or not isinstance(fiche, dict):
        return
    try:
        entree = action.au_hub(donnees, arguments, ctx)
    except Exception as erreur:  # noqa: BLE001 -- R1: logged
        logger.error(f"[.mark] Hub note of {action.nom} not made: {erreur!r}")
        return
    if isinstance(entree, dict):
        fiche.setdefault(CLE_HUB, []).append(entree)
