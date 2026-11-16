"""[.mark] Mécanisme commun : une PLAGE de jours, d'heures et de dates (module Restauration, lot 2).

Aucune notion de métier : ``{"jours": [1..7], "heures": [["11:00", "14:30"]], "dates": {"du": "AAAA-MM-JJ", "au": "AAAA-MM-JJ"}}``.
Une clé absente ne restreint rien. L'heure testée est celle du fuseau de l'établissement, fournie par l'appelant.
"""

from __future__ import annotations

from datetime import date, datetime, time


def heure(texte: str) -> time:
    heures, minutes = texte.split(":")[:2]
    return time(int(heures), int(minutes))


def dans_la_plage(plage: dict | None, local: datetime) -> bool:
    if not plage:
        return True
    jours = plage.get("jours")
    if jours and local.isoweekday() not in jours:
        return False
    heures = plage.get("heures")
    if heures and not any(heure(debut) <= local.time() < heure(fin) for debut, fin in heures):
        return False
    dates = plage.get("dates")
    if dates:
        if dates.get("du") and local.date() < date.fromisoformat(dates["du"]):
            return False
        if dates.get("au") and local.date() > date.fromisoformat(dates["au"]):
            return False
    return True
