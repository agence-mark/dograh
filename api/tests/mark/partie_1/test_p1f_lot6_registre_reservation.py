"""[.mark] Lot 6 : la réservation a son registre de questions (RC9) : une question reposée sur le même objet garde son numéro."""

from __future__ import annotations

from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark import test_restauration_reservation as RESERVATION

salle = RESERVATION.salle  # la fixture de la réservation, reprise telle quelle


async def test_rc9_la_relecture_reposee_garde_son_numero(salle, monkeypatch):
    e = EssaiReservation(salle, monkeypatch)
    a = await e.tour("quatre personnes samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    b = await e.tour("plutôt cinq", personnes=5)
    qa, qb = a.get("question") or {}, b.get("question") or {}
    assert qa.get("type") == qb.get("type") == "recapitulatif", (qa, qb)
    assert qa["id"] == qb["id"], f"la même relecture change de numéro : {qa['id']} -> {qb['id']}"
