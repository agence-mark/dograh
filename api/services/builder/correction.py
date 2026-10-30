"""[.mark] Builder : la correction en plusieurs tours sur son brouillon (B37), côté moteur.

Tests -> correction -> rejeu, avec un plafond de tours (``tours_correction_max``) et le plafond de dépense de
la conversation. Jamais de publication : le cerveau n'a que les actions du registre.

Ce que le moteur attend de l'action ``tests_rejouer`` (point d'entrée du lot 6) : un dict
``{"ok": bool, "echecs": [ {...} ], "total": int}``, ``ok`` vrai si et seulement si TOUTE la suite passe, ou
``{"disponible": False}`` tant que le lot 6 n'est pas fait (le moteur le dit et ne dépense rien).

**B38** : « vérifié » n'est dit que si la dernière suite rejouée, APRÈS la dernière correction, est entièrement verte.
Après un plafond atteint ou des tours épuisés, le rapport dit « non revérifié » plutôt que de laisser croire.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from api.services.builder import moteur
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.cerveau.appel import Cerveau
from api.services.builder.cerveau.reglages import ReglagesCerveau

CONSIGNE_DE_CORRECTION = (
    "Des tests de l'agent ont échoué (tour {tour} sur {maximum}). Voici les échecs :\n{echecs}\n\n"
    "Dis d'abord, pour chacun, si l'échec vient de l'agent, du test ou de l'exécution. Corrige SEULEMENT ce qui vient "
    "de l'agent, sur le brouillon (opérations de construction). Ne publie rien. Si tu ne sais pas, pose la question."
)


async def corriger(
    ctx: Contexte, cerveau: Cerveau, reglages: ReglagesCerveau, *, parametres_de_rejeu: dict[str, Any] | None = None
) -> AsyncIterator[dict[str, Any]]:
    """Rejoue la suite, fait corriger par le cerveau, rejoue, jusqu'au vert ou au plafond. Événements du moteur + ``rapport``."""
    arguments = {"workflow_id": ctx.workflow_id, **(parametres_de_rejeu or {})}
    resultat = await executer("tests_rejouer", arguments, ctx)
    if resultat.get("disponible") is False:
        yield {"type": "rapport", "etat": "tests_non_disponibles", "message": resultat.get("message", "")}
        yield {"type": "fin", "raison": "tests_non_disponibles"}
        return
    verifie = bool(resultat.get("ok"))
    tour = 0
    raison = "vert" if verifie else "tours"
    while not verifie and tour < reglages.tours_correction_max:
        tour += 1
        conversation = await _depense_de_la_conversation(ctx)
        if (atteint := moteur.plafond_atteint(conversation, reglages)) is not None:
            raison = "plafond"
            yield {"type": "erreur", "code": "plafond", "message": f"The conversation's ceiling is reached ({atteint})."}
            break
        message = CONSIGNE_DE_CORRECTION.format(
            tour=tour,
            maximum=reglages.tours_correction_max,
            echecs=json.dumps(resultat.get("echecs") or [], ensure_ascii=False)[:6000],
        )
        arret = False
        async for evenement in moteur.conversation(ctx, message, cerveau, reglages):
            if evenement["type"] == "fin":
                continue  # un seul « fin » : celui du rapport
            yield evenement
            if evenement["type"] == "erreur":
                arret = True
        if arret:
            raison = "erreur"
            break
        # B38 : après CHAQUE correction, toute la suite est rejouée.
        resultat = await executer("tests_rejouer", arguments, ctx)
        verifie = bool(resultat.get("ok"))
        raison = "vert" if verifie else "tours"
    yield {
        "type": "rapport",
        "etat": "verifie" if verifie else "non_verifie",
        "tours": tour,
        "raison": raison,
        "echecs_restants": [] if verifie else (resultat.get("echecs") or []),
        "message": "" if verifie else "The last replay of the whole suite is not green: nothing is verified.",
    }
    yield {"type": "fin", "raison": raison}


async def _depense_de_la_conversation(ctx: Contexte) -> dict[str, Any]:
    from api.services.builder import contexte

    assert ctx.workflow_id is not None
    return (await contexte.charger(ctx.organisation_id, ctx.workflow_id))["depense"]
