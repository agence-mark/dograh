"""[.mark] The internal connector « Booking » (module Restauration, lot 8, E-48): the reservation by capacity, taken in the call.

No software, no Nango: the actions run in the fork (``services/reservation/action.py``) and the capacity is a SOURCE (the client's database,
through ``services/restauration/source_reservation.py``, is the first one). Five tools, created in « Tools » as ``integration`` tools:

- ``disponibilites`` says when there is room for a number of people on a day (the nearest to a time, or one per hour); nothing is booked;
- ``reserver`` leads to the booking one missing piece at a time (people, day, time, name, number), reads it back, and books only on the
  caller's « yes » (``confirmer``); the room is checked again at the booking and a refusal returns the nearest free times;
- ``modifier_reservation`` and ``annuler_reservation`` work on the caller's booking (found by the number that shows, or by its number); the
  cancellation is done in two steps; a past booking never changes;
- ``retrouver_reservation`` says where the caller's booking stands, read in the book.

Every answer is a closed status (never a software's own text), the facts, and a SENTENCE PROPOSED. The code computes days, hours and room:
the model never does.
"""

from __future__ import annotations

from api.services.integrations.connectors.catalogue import Action, Connecteur, Parametre, declarer


def _jamais(*_args, **_kwargs):
    raise RuntimeError("An internal action never goes through the relay.")


async def _executer(action, arguments, ctx, delai_s):
    from api.services.reservation.action import executer

    return await executer(action, arguments, ctx, delai_s)


def _source_de_la_capacite() -> None:
    import api.services.restauration.source_reservation  # noqa: F401  # the client's database registers itself on import


_source_de_la_capacite()

_JOUR = Parametre("jour", description="The day as the caller said it (« tomorrow », « Saturday », « the 24th »). Never compute a date yourself.", obligatoire=False)
_HEURE = Parametre("heure", description="The time as the caller said it (« half past seven in the evening »).", obligatoire=False)
_PERSONNES = Parametre(
    "personnes", type="number",
    description="The number of people, only as the caller said it. Never guess or default it: if he did not say, leave it empty and the tool asks.",
    obligatoire=False,
)
_REFERENCE = Parametre(
    "reference",
    description="The booking's number, only when the tool asked which one (it returns them). Empty: the booking of the number that shows.",
    obligatoire=False,
)
_CONFIRMER = Parametre("confirmer", type="boolean", description="True ONLY once the caller said yes to what was just read back.", obligatoire=False)

def _action_ouverte(fiche: dict) -> dict | None:
    """Une réservation relue à l'appelant et pas confirmée (la relecture est effacée à l'enregistrement) : à finir par ``reserver``."""
    from api.services.reservation.moteur import CLE

    etat = fiche.get(CLE) if isinstance(fiche, dict) else None
    if isinstance(etat, dict) and etat.get("lecture"):
        return {"outil": "reserver"}
    return None


def _etat_de_l_appel(fiche: dict) -> str:
    """Chantier Partie 1, lot 6 : la ligne de la réservation dans l'état de l'appel montré à l'accueil (``banc-b13`` ``etat_appel_v6``, résumé
    ``reservation_b10.resume``). Le détail d'une réservation enregistrée (personnes, quand, nom) est versé avec la fiche de la réservation (lot 7)."""
    from api.services.reservation.moteur import CLE

    etat = fiche.get(CLE) if isinstance(fiche, dict) else None
    if isinstance(etat, dict) and etat.get("derniere"):
        resume = "enregistrée"
    elif isinstance(etat, dict) and etat:
        resume = "commencée, pas encore enregistrée"
    else:
        resume = "aucune"
    return f"- Réservation de cet appel : {resume}."


RESERVATION = declarer(
    Connecteur(
        nom="reservation",
        action_ouverte=_action_ouverte,
        etat_de_l_appel=_etat_de_l_appel,
        libelle="Booking (internal)",
        integration="interne",
        interne=True,
        executer_interne=_executer,
        actions=(
            Action(
                nom="disponibilites",
                description=(
                    "When there is room, for a number of people, on a day. With a time, the three nearest times; without, one per hour. "
                    "Nothing is booked. Complete: say so, never invent a time."
                ),
                parametres=(Parametre("jour", description="The day as the caller said it."), _HEURE, _PERSONNES),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="reserver",
                description=(
                    "Lead a booking to its saving, ONE missing piece at a time (people, day, time, name, number): call it each time the caller gives something. "
                    "It reads the booking back first; call it with confirmer true ONLY once the caller said yes. The number he calls from is kept without asking."
                ),
                parametres=(
                    _JOUR, _HEURE, _PERSONNES,
                    Parametre("prenom", description="The name the booking is made under.", obligatoire=False),
                    Parametre("telephone", description="A number the caller dictated, only when his own is hidden or he asks for another.", obligatoire=False),
                    Parametre("note", description="A request about the booking (a birthday, a high chair), as he said it.", obligatoire=False),
                    _CONFIRMER,
                ),
                serialise_avec="reservation",
                ecrit=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="modifier_reservation",
                description=(
                    "Change the caller's booking: time (day and time together, or only the time), number of people, name, note. It reads the change back; "
                    "call it with confirmer true ONLY once the caller said yes. A booking in the past or cancelled cannot change."
                ),
                parametres=(_REFERENCE, _JOUR, _HEURE, _PERSONNES, Parametre("prenom", description="A new name.", obligatoire=False), Parametre("note", description="A new note.", obligatoire=False), _CONFIRMER),
                serialise_avec="reservation",
                ecrit=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="annuler_reservation",
                description=(
                    "Cancel the caller's booking in TWO steps: the first call says which booking and asks; call it again with confirmer true ONLY once "
                    "the caller said yes to that booking. A booking in the past cannot be cancelled."
                ),
                parametres=(_REFERENCE, _CONFIRMER),
                serialise_avec="reservation",
                ecrit=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="retrouver_reservation",
                description="Where the caller's booking stands, read in the book (by the number that shows, by its number, or by name and day). Never guess.",
                parametres=(_REFERENCE, _JOUR, Parametre("prenom", description="The name of the booking, with the day.", obligatoire=False)),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
        ),
    )
)
