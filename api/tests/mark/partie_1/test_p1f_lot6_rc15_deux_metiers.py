"""Lot 6, RC15 : une fiche valide SANS ``reponse`` quand une question est posée vaut « autre » pour elle, aux deux métiers : la question reste posée sous le même
numéro, rien n'est refusé ni enregistré. Un seul mécanisme (``registre_des_questions.reponse_implicite``)."""

from __future__ import annotations

from api.tests.mark import test_restauration_reservation as RESERVATION
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

from .aides_de_la_commande import a_emporter, jusqu_au_recapitulatif, premier_article, question_posee, refuser_la_proposition

salle = RESERVATION.salle  # la fixture de la réservation, reprise telle quelle


async def test_commande_une_fiche_sans_reponse_laisse_la_relecture_posee(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    avant = await jusqu_au_recapitulatif(e)
    await e.tour("hum, une seconde", mode_de_retrait="emporter")
    apres = question_posee(e)
    assert apres.get("type") == "relecture" and apres["id"] == avant["id"], (avant, apres)
    assert not e.p.get("enregistree")


async def test_reservation_une_fiche_sans_reponse_laisse_la_relecture_posee(salle, monkeypatch):
    e = EssaiReservation(salle, monkeypatch)
    a = await e.tour("quatre personnes samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    b = await e.tour("Alice, oui Alice", nom="Alice")
    qa, qb = a.get("question") or {}, b.get("question") or {}
    assert qa.get("type") == qb.get("type") == "recapitulatif" and qa["id"] == qb["id"], (qa, qb)


async def test_reservation_une_fiche_valide_sans_reponse_n_est_ni_refusee_ni_enregistree(salle, monkeypatch):
    """Ce que la porte rend : la fiche est lue (pas de refus), la relecture reste posée sous le même numéro, rien n'est enregistré."""
    e = EssaiReservation(salle, monkeypatch)
    a = await e.tour("quatre personnes samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    b = await e.tour("hum, une seconde", nom="Alice")
    assert b["statut"] != "REJETEE" and not b.get("cases_refusees"), b
    assert (b.get("question") or {}).get("id") == a["question"]["id"], (a.get("question"), b.get("question"))
    assert await e.nombre_de_reservations() == 0
