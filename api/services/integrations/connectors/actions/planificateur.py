"""[.mark] The internal connector « Planner » (chantier l-agent-collegue, L5, P1).

No software of its own, no Nango: the actions run in the fork (``services/planificateur/action.py``)
and reach the client's calendar software through the hub's translator chosen in « Integrations »
(H2). Two generic actions, created in « Tools » as ``integration`` tools (no new tool category,
constat 3 of L0):

- ``proposer_creneaux`` reads, and may be ANTICIPATED (D17): its trigger fields launch it as soon
  as the record knows them;
- ``poser_rendez_vous`` writes, never anticipated, never retried after the call (its fallback is
  the call-back request, decided during the call, P8).

Not a workflow-control boundary (``peut_transferer`` false): a read of slots must never be taken
for a door of the record.
"""

from __future__ import annotations

from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    Parametre,
    declarer,
)


def _jamais(*_args, **_kwargs):
    raise RuntimeError("An internal action never goes through the relay.")


async def _executer(action, arguments, ctx, delai_s):
    from api.services.planificateur.action import executer

    return await executer(action, arguments, ctx, delai_s)


PLANIFICATEUR = declarer(
    Connecteur(
        nom="planificateur",
        libelle="Planner (internal)",
        integration="interne",
        interne=True,
        executer_interne=_executer,
        actions=(
            Action(
                nom="proposer_creneaux",
                description=(
                    "Find appointment slots for the caller. Give the kind of appointment and the "
                    "caller's own words about when he would like it; offer the slots returned, as given."
                ),
                parametres=(
                    Parametre(
                        "type",
                        description="The code of the kind of appointment (ask the caller if several exist).",
                        obligatoire=False,
                    ),
                    Parametre(
                        "souhait",
                        description="When the caller would like it, in his own words (« mardi matin », « après 17 heures »). Empty: the earliest.",
                        obligatoire=False,
                    ),
                ),
                ecrit=False,
                anticipable_permis=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="poser_rendez_vous",
                description="Book the slot the caller accepted, one of those just proposed.",
                parametres=(
                    Parametre(
                        "debut",
                        description="The start of the slot accepted, exactly as proposed (« debut »).",
                    ),
                ),
                ecrit=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
        ),
    )
)
