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


def _choix(e, numeros):
    from api.services.actions_communes.resultat import Resultat
    from api.services.reservation.porte import _question_de

    candidats = [{"numero": n, "quand_dit": "jeudi soir", "prenom": "Martin", "personnes": 2, "debut": None, "dit": f"la {n}"} for n in numeros]
    return _question_de("retrouver", Resultat("AMBIGU", {"candidats": candidats}), e, 3)


def test_rc9_deux_laquelle_sur_deux_recherches_ont_deux_numeros():
    e: dict = {}
    premiere = _choix(e, ["R1", "R2"])
    seconde = _choix(e, ["R3", "R4"])
    assert premiere["id"] != seconde["id"], (premiere["id"], seconde["id"])


def test_rc9_le_meme_laquelle_redit_garde_son_numero():
    e: dict = {}
    assert _choix(e, ["R1", "R2"])["id"] == _choix(e, ["R1", "R2"])["id"]
