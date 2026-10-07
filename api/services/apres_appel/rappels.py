"""[.mark] The call-back requests decided DURING a call (chantier l-agent-collegue, P8, R-3, V6).

One mechanism for every action that cannot finish what the caller asked and promises a call-back
instead (never a lost caller):

- the planner found no slot, or could not book (L5, P8): ``origine`` absent or ``planificateur``;
- the person of the team did not answer the transfer, refused it, or the transfer failed
  (R-3, decision of Evan 07/10): ``origine = equipe``, the request assigned to her;
- the caller could not be verified after two attempts (L6, V6): ``origine = verification``.

During the call the action appends ONE entry to the record under ``CLE_RAPPEL`` (a list).
After the call, ``construire_envoi`` makes the request from the last one: it exists even with
nothing noted, and its summary says what is to be done (``resume_du_rappel``). Nothing here
is said to the caller: each action says its own sentence of the catalogue.

The key keeps its first name (``planificateur_rappel``, L5): runs already recorded read the same.
"""

from __future__ import annotations

CLE_RAPPEL = "planificateur_rappel"

ORIGINE_PLANIFICATEUR = "planificateur"
ORIGINE_EQUIPE = "equipe"
ORIGINE_VERIFICATION = "verification"


def origine(entree: dict) -> str:
    """An entry of before L6 has no origin: it is the planner's."""
    return str(entree.get("origine") or ORIGINE_PLANIFICATEUR)


def rappels_de(contexte: dict | None) -> list[dict]:
    brut = (contexte or {}).get(CLE_RAPPEL)
    return [r for r in brut if isinstance(r, dict)] if isinstance(brut, list) else []


def resume_du_rappel(entree: dict) -> str:
    """The summary of the request, in French (the client's database and the mails are)."""
    souhait = entree.get("souhait")
    if origine(entree) == ORIGINE_EQUIPE:
        qui = entree.get("prenom") or entree.get("personne") or "la personne demandée"
        morceaux = [f"Rappel à faire : {qui} n'a pas pu prendre l'appel transféré"]
        if entree.get("numero"):
            morceaux.append(f"numéro de l'appelant : {entree['numero']}")
        if entree.get("objet"):
            morceaux.append(f"objet : {entree['objet']}")
        if souhait:
            morceaux.append(f"créneau souhaité : « {souhait} »")
        return " ; ".join(morceaux) + "."
    if origine(entree) == ORIGINE_VERIFICATION:
        return (
            "Rappel à faire : l'appelant voulait des informations sur son dossier, "
            "son identité n'a pas pu être vérifiée pendant l'appel (rien ne lui a été lu)."
        )
    # The planner (L5): the text of before, kept word for word.
    return (
        "Rendez-vous à rappeler pour le fixer"
        + (f" (souhait de l'appelant : « {souhait} »)" if souhait else "")
        + (f" ; créneau choisi : {entree['creneau_choisi']}" if entree.get("creneau_choisi") else "")
        + "."
    )
