"""[.mark] Lot 7b-C3, commit 3 : les retours de la base de la réservation qui ne sont pas des faits accomplis (déjà fait, déjà annulé, recherche) ne portent plus de texte (lot 7b-C7, B7) ;
C7 B9 : le catalogue supprimé, ce que disait le texte d'avant est vérifié dans les faits du résultat.

Les résultats de ``creer``, ``modifier`` et ``annuler`` passent par la porte : leurs faits sont ``resultats[].faits`` (``faits_publics``). Ceux de ``retrouver_reservation`` sont lus par le moteur, jamais par
le modèle (``reservations`` est gardé, E4)  : ce que disait leur texte est dans les faits du module (``r.faits``)."""

from __future__ import annotations

from api.db.bases_clients import restauration_reservation as RR
from api.tests.mark import test_restauration_reservation as RESA
from api.tests.mark.partie_1.aides_secours_de_la_reservation import faits_publics

salle, creer, TEL = RESA.salle, RESA.creer, RESA.TEL  # la fixture et les aides du classeur, reprises par affectation


async def test_deja_reserve_dit_quand(salle):
    await creer(salle)
    r = await creer(salle)
    assert (r.statut, r.suggestion) == ("DEJA_FAIT", ""), r
    assert faits_publics(r)["quand_dit"] == "samedi quatorze novembre à vingt heures", r


async def test_deja_comme_cela(salle):
    numero = (await creer(salle)).faits["numero"]
    r = await RR.modifier_reservation(salle.c, salle.a, numero, {"prenom": "Alice"})
    assert (r.statut, r.suggestion) == ("DEJA_FAIT", ""), r
    assert (faits_publics(r)["statut"], faits_publics(r)["prenom"]) == ("confirmee", "Alice"), r  # « déjà comme cela » : la réservation, encore confirmée, porte déjà la valeur


async def test_deja_annulee(salle):
    numero = (await creer(salle)).faits["numero"]
    await RR.annuler_reservation(salle.c, salle.a, numero)
    r = await RR.annuler_reservation(salle.c, salle.a, numero)
    assert (r.statut, r.suggestion) == ("DEJA_FAIT", ""), r
    assert faits_publics(r)["statut"] == "annulee", r  # « déjà annulée »


async def test_retrouver_sans_critere_demande_le_nom_et_le_jour(salle):
    r = await RR.retrouver_reservation(salle.c, salle.a)
    assert (r.statut, r.manque, r.suggestion) == ("INCOMPLETE", "reference", ""), r
    assert r.faits == {}, r  # « sous quel nom, et pour quel jour ? » : le manque ``reference`` seul


async def test_retrouver_ne_trouve_pas(salle):
    r = await RR.retrouver_reservation(salle.c, salle.a, telephone=TEL)
    assert (r.statut, r.suggestion) == ("INTROUVABLE", ""), r
    assert r.faits == {"reservations": []}, r


async def test_retrouver_une_reservation_dit_quand_et_pour_combien(salle):
    await creer(salle)
    r = await RR.retrouver_reservation(salle.c, salle.a, telephone=TEL)
    assert (r.statut, r.suggestion) == ("OK", ""), r
    assert [(v["quand_dit"], v["couverts"]) for v in r.faits["reservations"]] == [("samedi quatorze novembre à vingt heures", 2)], r


async def test_retrouver_plusieurs_reservations_dit_leur_nombre(salle):
    await creer(salle)
    await creer(salle, appel_id="deux", debut=RESA.SAMEDI_20H.replace(hour=21))
    r = await RR.retrouver_reservation(salle.c, salle.a, telephone=TEL)
    assert (r.statut, r.suggestion) == ("OK", ""), r
    assert len(r.faits["reservations"]) == 2, r
