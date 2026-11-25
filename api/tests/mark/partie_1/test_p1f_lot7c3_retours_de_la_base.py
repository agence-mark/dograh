"""[.mark] Lot 7b-C3, commit 3 : les retours de la base de la réservation qui ne sont pas des faits accomplis (déjà fait, déjà annulé, recherche) rendent le texte d'avant, au caractère près,
ET ce texte se refait des faits du résultat (``textes_de_secours``).

Les résultats de ``creer``, ``modifier`` et ``annuler`` passent par la porte : leurs faits sont ``resultats[].faits`` (``faits_publics``). Ceux de ``retrouver_reservation`` sont lus par le moteur, jamais par
le modèle (``reservations`` est gardé, E4) : leur texte se refait des faits du module (``r.faits``)."""

from __future__ import annotations

from api.db.bases_clients import restauration_reservation as RR
from api.services.reservation import textes_de_secours as TS
from api.tests.mark import test_restauration_reservation as RESA
from api.tests.mark.partie_1.aides_secours_de_la_reservation import faits_publics

salle, creer, TEL = RESA.salle, RESA.creer, RESA.TEL  # la fixture et les aides du classeur, reprises par affectation


async def test_deja_reserve_dit_quand(salle):
    await creer(salle)
    r = await creer(salle)
    assert (r.statut, r.suggestion) == ("DEJA_FAIT", "C'est déjà réservé pour samedi quatorze novembre à vingt heures.")
    assert r.suggestion == TS.deja_reservee(faits_publics(r)), r


async def test_deja_comme_cela(salle):
    numero = (await creer(salle)).faits["numero"]
    r = await RR.modifier_reservation(salle.c, salle.a, numero, {"prenom": "Alice"})
    assert (r.statut, r.suggestion) == ("DEJA_FAIT", "C'est déjà comme cela.")
    assert r.suggestion == TS.deja_comme_cela(faits_publics(r)), r


async def test_deja_annulee(salle):
    numero = (await creer(salle)).faits["numero"]
    await RR.annuler_reservation(salle.c, salle.a, numero)
    r = await RR.annuler_reservation(salle.c, salle.a, numero)
    assert (r.statut, r.suggestion) == ("DEJA_FAIT", "Cette réservation est déjà annulée.")
    assert r.suggestion == TS.deja_annulee(faits_publics(r)), r


async def test_retrouver_sans_critere_demande_le_nom_et_le_jour(salle):
    r = await RR.retrouver_reservation(salle.c, salle.a)
    assert (r.statut, r.manque, r.suggestion) == ("INCOMPLETE", "reference", "Sous quel nom, et pour quel jour ?")
    assert r.suggestion == TS.sous_quel_nom_et_quel_jour(r.faits), r


async def test_retrouver_ne_trouve_pas(salle):
    r = await RR.retrouver_reservation(salle.c, salle.a, telephone=TEL)
    assert (r.statut, r.suggestion) == ("INTROUVABLE", "Je ne trouve pas de réservation.")
    assert r.suggestion == TS.pas_de_reservation(r.faits), r


async def test_retrouver_une_reservation_dit_quand_et_pour_combien(salle):
    await creer(salle)
    r = await RR.retrouver_reservation(salle.c, salle.a, telephone=TEL)
    assert (r.statut, r.suggestion) == ("OK", "Vous avez une réservation samedi quatorze novembre à vingt heures pour deux personnes.")
    assert r.suggestion == TS.une_reservation(r.faits), r
    seule = {"reservations": [{"quand_dit": "demain à midi", "couverts": 4}]}
    assert TS.une_reservation(seule) == "Vous avez une réservation demain à midi pour quatre personnes."


async def test_retrouver_plusieurs_reservations_dit_leur_nombre(salle):
    await creer(salle)
    await creer(salle, appel_id="deux", debut=RESA.SAMEDI_20H.replace(hour=21))
    r = await RR.retrouver_reservation(salle.c, salle.a, telephone=TEL)
    assert (r.statut, r.suggestion) == ("OK", "Je trouve 2 réservations.")
    assert r.suggestion == TS.plusieurs_reservations(r.faits), r
