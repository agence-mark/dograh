"""[.mark] Lot 7b-C3, commit 3 (fin) : « C'est réservé… », « C'est modifié… » et « C'est annulé. » sont des faits accomplis qui engagent : dits par le code (``avant``, ``porte.textes_du_code``),
rangés avec les phrases du code de la commande (exception du plan : le fait accompli), mot pour mot comme avant. C6 n° 9 (décision d'Evan 25/11 9 h 30) : le modèle les dit ;
C7 (B7) : la base ne rend plus aucun texte ; celui d'avant se refait de ses faits, que le modèle reçoit."""

from __future__ import annotations

from api.db.bases_clients import restauration_reservation as RR
from api.tests.mark import test_restauration_reservation as RESA

salle, creer, SAMEDI_20H = RESA.salle, RESA.creer, RESA.SAMEDI_20H


async def test_la_base_dit_les_phrases_du_registre(salle):
    """C6 n° 9 (décision d'Evan 25/11 9 h 30) : la base ne rend plus les phrases du registre mais des textes de secours (gardés au journal pour le repli), nombres en lettres ; le modèle dit le fait."""
    from api.services.reservation import textes_de_secours as TS

    r = await creer(salle)
    assert r.statut == "ENREGISTREE"
    # C6 n° 12 (décision d'Evan 25/11 9 h 30) : le module des phrases du code est supprimé ; le texte de secours garde les mots d'avant
    # C7 (B7) : la base ne rend plus de texte ; celui d'avant se refait de ses faits (personnes, quand, nom), que le modèle reçoit
    assert r.suggestion == "" and TS.reservation_enregistree(r.faits) == f"C'est réservé pour deux personnes, {r.faits['quand_dit']}, au nom de Alice.", r
    m = await RR.modifier_reservation(salle.c, salle.a, r.faits["numero"], {"couverts": 3})
    assert m.statut == "OK" and m.suggestion == "" and TS.reservation_modifiee(m.faits) == f"C'est modifié : {m.faits['quand_dit']}, trois personnes.", m
    a = await RR.annuler_reservation(salle.c, salle.a, r.faits["numero"])
    assert a.statut == "OK" and a.suggestion == "" and TS.reservation_annulee(a.faits) == "C'est annulé.", a
