"""[.mark] The internal connector « Team » (chantier l-agent-collegue, L2, C7 to C10).

No software, no Nango: the action runs in the fork (``services/equipe/diriger.py``). It is an
``integration`` tool like the others (constat 3 of L0: no new tool category), created in
« Tools » and placed on the steps that need it.

- ``diriger_vers_personne`` (writes, never anticipated): the model names a person by her KEY,
  chosen in the closed list built at pick-up (``equipe_cles``, given to the model as ``enum``);
  the code decides the gesture it can make -- transfer the call when the person may be
  reached that way and has a phone number, otherwise pass the request on to her -- and
  resolves her number from the in-memory copy. The model never gives a number nor an e-mail.
"""

from __future__ import annotations

from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    Parametre,
    declarer,
)

GESTES = ("transferer", "transmettre")

REGLAGES_DIRIGER = {
    # Seconds the person's phone rings before the request is passed on instead (C9).
    "delai_transfert_s": 30,
}


def _jamais(*_args, **_kwargs):
    raise RuntimeError("An internal action never goes through the relay.")


def _gestionnaire(manager, tool, nom_de_fonction):
    from api.services.equipe.diriger import creer_gestionnaire

    return creer_gestionnaire(manager, tool, nom_de_fonction)


EQUIPE = declarer(
    Connecteur(
        nom="equipe",
        libelle="Team (internal)",
        integration="interne",
        interne=True,
        gestionnaire_interne=_gestionnaire,
        actions=(
            Action(
                nom="diriger_vers_personne",
                description=(
                    "Direct the caller to a person of the team: transfer the call to her, or pass "
                    "the request on to her. Name the person by her key from the team list."
                ),
                parametres=(
                    Parametre(
                        "personne",
                        description="The key of the person, from the team list (never a phone number nor an e-mail).",
                        liste_du_contexte="equipe_cles",
                    ),
                    Parametre(
                        "geste",
                        description=(
                            "transferer: put the caller through to her now; transmettre: pass the "
                            "request on to her. The code falls back to transmettre when a transfer "
                            "is not possible."
                        ),
                        obligatoire=False,
                        choix=GESTES,
                    ),
                    Parametre(
                        "motif",
                        description="What the caller wants, in a few words.",
                        obligatoire=False,
                    ),
                ),
                ecrit=True,
                preparer=_jamais,
                resultat=_jamais,
                reglages_par_defaut=REGLAGES_DIRIGER,
            ),
        ),
    )
)
