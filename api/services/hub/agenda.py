"""[.mark] The agenda domain of the hub (L4, H6 to H8): who is busy when, and booking.

The planner (L5) speaks only this common format; the translator chosen by the organization
(« Integrations ») talks to the software. A new calendar software is a new translator: nothing
here changes.

- ``occupations``: for each agenda asked, its busy intervals between two instants. An agenda
  the software does not know (or refuses) is ABSENT from the answer: the caller treats it as
  unknown, never as free.
- ``evenements`` (R-6): the appointments of ONE agenda with where they are (``lieu``), read by the
  translator's ``chercher`` of ``rendez_vous`` (times and place only, nothing else is asked).
  The planner starts a journey from the previous appointment's address.
- ``poser``: the appointment in one agenda; returns the software's identifier, kept in the
  hub as ``lien_externe`` (written after the call with the ``rendez_vous`` row).
"""

from __future__ import annotations

from datetime import datetime

from api.services.hub.traducteurs import operer

Intervalle = tuple[datetime, datetime]


async def occupations(
    organization_id: int,
    systeme: str,
    agendas: list[str],
    debut: datetime,
    fin: datetime,
    *,
    delai: float,
) -> dict[str, list[Intervalle]]:
    if not agendas:
        return {}
    return await operer(
        organization_id,
        systeme,
        "disponibilites",
        "chercher",
        {"agendas": list(agendas), "debut": debut.isoformat(), "fin": fin.isoformat()},
        delai=delai,
    )


async def evenements(
    organization_id: int,
    systeme: str,
    agenda: str,
    debut: datetime,
    fin: datetime,
    *,
    delai: float,
) -> list[dict]:
    """The appointments of one agenda between two instants, in the hub's format and in the order
    of their start: ``{debut, fin}`` as aware datetimes, ``lieu`` (text or None). All-day,
    cancelled and « free » events are left out by the translator. Raises like ``operer`` (a
    translator without ``chercher`` on ``rendez_vous`` included): the caller falls back."""
    brut = await operer(
        organization_id,
        systeme,
        "rendez_vous",
        "chercher",
        {"agenda": agenda, "debut": debut.isoformat(), "fin": fin.isoformat()},
        delai=delai,
    )
    sortie = []
    for e in brut or []:
        try:
            a = datetime.fromisoformat(str(e["debut"]).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(e["fin"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if a.tzinfo is None or b.tzinfo is None:
            continue
        sortie.append({"debut": a, "fin": b, "lieu": (e.get("lieu") or "").strip() or None})
    return sorted(sortie, key=lambda x: x["debut"])


async def poser(
    organization_id: int, systeme: str, rendez_vous: dict, *, delai: float
) -> str | None:
    """``rendez_vous``: the common format (``agenda``, ``debut``, ``fin``, ``fuseau``,
    ``titre``, ``description``, ``lieu``). The software's identifier, or None."""
    resultat = await operer(
        organization_id, systeme, "rendez_vous", "creer", rendez_vous, delai=delai
    )
    return (resultat or {}).get("id_externe")
