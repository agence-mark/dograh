"""[.mark] Lot 7b-C3, commit 3 (fin) : « C'est réservé… », « C'est modifié… » et « C'est annulé. » sont des faits accomplis qui engagent : dits par le code (``avant``, ``porte.textes_du_code``),
rangés avec les phrases du code de la commande (exception du plan : le fait accompli), mot pour mot comme avant. C6 n° 9 (décision d'Evan 25/11 9 h 30) : le modèle les dit ;
la base n'en rend plus que le texte de secours, gardé au journal du dit pour le repli."""

from __future__ import annotations

from api.db.bases_clients import restauration_reservation as RR
from api.services.commande import phrases_dites_par_le_code as PD
from api.tests.mark import test_restauration_reservation as RESA

salle, creer, SAMEDI_20H = RESA.salle, RESA.creer, RESA.SAMEDI_20H


def test_les_trois_phrases_sont_des_faits_accomplis_mot_pour_mot():
    assert PD.reservation_enregistree(personnes="deux personnes", quand="samedi à vingt heures", prenom="Alice") == "C'est réservé pour deux personnes, samedi à vingt heures, au nom de Alice."
    assert PD.reservation_modifiee(quand="dimanche à dix-neuf heures", personnes="3 personnes") == "C'est modifié : dimanche à dix-neuf heures, 3 personnes."
    assert PD.reservation_annulee() == "C'est annulé."
    assert {PD.PHRASES[c].exception for c in ("reservation_enregistree", "reservation_modifiee", "reservation_annulee")} == {PD.EXCEPTION_FAIT_ACCOMPLI}


async def test_la_base_dit_les_phrases_du_registre(salle):
    """C6 n° 9 (décision d'Evan 25/11 9 h 30) : la base ne rend plus les phrases du registre mais des textes de secours (gardés au journal pour le repli), nombres en lettres ; le modèle dit le fait."""
    from api.services.reservation import textes_de_secours as TS

    r = await creer(salle)
    assert r.statut == "ENREGISTREE"
    assert r.suggestion == TS.reservation_enregistree(r.faits) == PD.reservation_enregistree(personnes="deux personnes", quand=r.faits["quand_dit"], prenom="Alice"), r.suggestion
    m = await RR.modifier_reservation(salle.c, salle.a, r.faits["numero"], {"couverts": 3})
    assert m.statut == "OK" and m.suggestion == TS.reservation_modifiee(m.faits) == PD.reservation_modifiee(quand=m.faits["quand_dit"], personnes="trois personnes"), m
    a = await RR.annuler_reservation(salle.c, salle.a, r.faits["numero"])
    assert a.statut == "OK" and a.suggestion == TS.reservation_annulee(a.faits) == PD.reservation_annulee(), a
