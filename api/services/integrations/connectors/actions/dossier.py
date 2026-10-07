"""[.mark] The internal connector « Record » (chantier l-agent-collegue, L6, V1 to V7).

No Nango of its own: the actions run in the fork (``services/verification/action.py``) and read
the record in the client's database (the hub), or through the translator of the software that
holds the records (« Caller verification » of the organization). Two ``integration`` tools,
created in « Tools » (no new tool category, constat 3 of L0), off unless the agent's switch
``verification_appelant`` is on (V7):

- ``verifier_appelant``: the code checks the caller's identity on the factors the client declared
  (V2); never anticipated (it counts attempts, it may send an SMS);
- ``lire_dossier``: what the caller may hear of his record, ONLY after the code verified him
  (V1); never anticipated.

The model never says who is verified: there is no parameter for it, and anything it sends that
is not declared below is dropped (D6).
"""

from __future__ import annotations

from api.schemas.verification import CHAMPS_CONTROLE, TYPES_LISIBLES
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    Parametre,
    declarer,
)

_DESCRIPTIONS_CONTROLE = {
    "reference": "The number of one of his requests, as he says it.",
    "nom": "His last name, as he says it.",
    "code_postal": "The postcode of his address, as he says it.",
    "commune": "The town of his address, as he says it.",
    "mail": "His e-mail address, as he says it.",
}


def _jamais(*_args, **_kwargs):
    raise RuntimeError("An internal action never goes through the relay.")


async def _executer(action, arguments, ctx, delai_s):
    from api.services.verification.action import executer

    return await executer(action, arguments, ctx, delai_s)


DOSSIER = declarer(
    Connecteur(
        nom="dossier",
        libelle="Record (internal)",
        integration="interne",
        interne=True,
        executer_interne=_executer,
        actions=(
            Action(
                nom="verifier_appelant",
                description=(
                    "Verify the caller's identity before telling him anything from his record. Give "
                    "only what he said, in his words; the code decides. Call again with the answers "
                    "asked for."
                ),
                parametres=tuple(
                    Parametre(c, description=_DESCRIPTIONS_CONTROLE[c], obligatoire=False)
                    for c in CHAMPS_CONTROLE
                )
                + (
                    Parametre(
                        "envoyer_code",
                        type="boolean",
                        description="True to send a verification code by SMS to the number of his record.",
                        obligatoire=False,
                    ),
                    Parametre(
                        "code",
                        description="The code he received by SMS, as he says it.",
                        obligatoire=False,
                    ),
                ),
                ecrit=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="lire_dossier",
                description=(
                    "Read what the caller may hear of his record, once verified. Say only what is "
                    "returned."
                ),
                parametres=(
                    Parametre(
                        "quoi",
                        description="demandes: his requests and where they stand; rendez_vous: his coming appointments.",
                        choix=tuple(TYPES_LISIBLES),
                    ),
                ),
                ecrit=False,
                preparer=_jamais,
                resultat=_jamais,
            ),
        ),
    )
)
