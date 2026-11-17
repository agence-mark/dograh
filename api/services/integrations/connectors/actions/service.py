"""[.mark] The internal connector « Service » (module Restauration, lot 7, W44, W23, E-15): practical information, a message for the team, the hand-over.

No software, no Nango: the actions run in the fork (``services/service_client/action.py``). Three tools, created in « Tools » as ``integration`` tools:

- ``infos_pratiques`` reads a practical piece of information (hours, access, payment…) in the agent's knowledge, ONE DOCUMENT PER TOPIC of a closed list; no document, no answer:
  it says it cannot confirm, never invents, and never hands over for that (E-15);
- ``laisser_un_message`` writes a call-back request for the team (message, who calls, a number) with its urgency taken from a closed list;
- ``passage_de_main`` is the door before a transfer: only for a complaint or a real problem (2 reasons); anything else becomes a call-back request.
"""

from __future__ import annotations

from api.services.integrations.connectors.catalogue import Action, Connecteur, Parametre, declarer
from api.services.service_client import action as service


def _jamais(*_args, **_kwargs):
    raise RuntimeError("An internal action never goes through the relay.")


async def _executer(action, arguments, ctx, delai_s):
    return await service.executer(action, arguments, ctx, delai_s)


SERVICE = declarer(
    Connecteur(
        nom="service",
        libelle="Service (internal)",
        integration="interne",
        interne=True,
        executer_interne=_executer,
        actions=(
            Action(
                nom="infos_pratiques",
                description=(
                    "A practical piece of information the place wrote down, by topic. Say what it returns as it is. If it says it cannot confirm, say so: "
                    "never invent, and do not hand the caller over for that."
                ),
                parametres=(Parametre("sujet", description="The topic the caller asks about.", choix=tuple(service.SUJETS)),),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="laisser_un_message",
                description=(
                    "Leave the team a message from ANY caller (customer, supplier, administration, salesperson): what it is about, who calls "
                    "(first and last name, the organisation if any) and a number to call back. Give what the caller said; the tool asks for "
                    "ONE missing piece at a time and keeps what was already given. The number shown for the call is known: never ask for it, "
                    "pass « telephone » only when the caller gives another one. One message per call: a new one replaces the previous one. "
                    "Urgent only when the caller says it cannot wait."
                ),
                parametres=(
                    Parametre("objet", description="The message, as the caller said it.", obligatoire=False),
                    Parametre("prenom", description="The caller's first name.", obligatoire=False),
                    Parametre("nom", description="The caller's last name.", obligatoire=False),
                    Parametre("organisme", description="The company or administration the caller speaks for, if any.", obligatoire=False),
                    Parametre("telephone", description="A number to call back, only if the caller gives one.", obligatoire=False),
                    Parametre("urgence", description="normale (default) or urgente.", choix=service.URGENCES, obligatoire=False),
                ),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="passage_de_main",
                description=(
                    "Before handing the caller to the team: ONLY for a complaint or a real problem. It answers PASSER (then hand over with the team tool) "
                    "or RAPPEL_NOTE (a call-back is noted: say so, do not hand over). Any other reason is « autre »."
                ),
                parametres=(
                    Parametre("motif", description="Why: plainte (a complaint), probleme_reel (a real problem), autre (anything else).", choix=service.MOTIFS_DITS),
                    Parametre("objet", description="What it is about, in a short sentence.", obligatoire=False),
                ),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
        ),
    )
)
