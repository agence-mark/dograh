"""Lot 6, reprise B1 : à la réservation, le ``sens`` de la réponse reste vérifié et remis en forme par la règle commune (E8). L'agent relit, la personne dit
« oui », la fiche arrive avec « accepte} » ou « Accepte » : la réservation est enregistrée, jamais un « qu'est-ce que vous voulez changer ? » à la place."""

from __future__ import annotations

import pytest

from api.tests.mark import test_restauration_reservation as RESERVATION
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

salle = RESERVATION.salle  # la fixture de la réservation, reprise telle quelle

MOTS = "quatre personnes samedi à vingt heures au nom d'Alice"


@pytest.mark.parametrize("sens", ["accepte}", "Accepte", " accepte "])
async def test_un_oui_au_sens_mal_forme_enregistre_la_reservation(salle, monkeypatch, sens):
    e = EssaiReservation(salle, monkeypatch)
    a = await e.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    assert a["question"]["type"] == "recapitulatif", a
    b = await e.tour("oui", reponse={"question_id": a["question"]["id"], "sens": sens})
    assert b["statut"] == "ENREGISTREE", b
    assert await e.nombre_de_reservations() == 1


async def test_un_sens_hors_liste_est_refuse_sans_rien_enregistrer(salle, monkeypatch):
    e = EssaiReservation(salle, monkeypatch)
    a = await e.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    b = await e.tour("oui", reponse={"question_id": a["question"]["id"], "sens": "peut-etre"})
    assert b["statut"] == "REJETEE" and b["cases_refusees"] == ["reponse"], b
    assert await e.nombre_de_reservations() == 0
