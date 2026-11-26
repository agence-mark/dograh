"""[.mark] Lot 7b-C3, commit 3 (fin) : « C'est réservé… », « C'est modifié… » et « C'est annulé. » sont des faits accomplis qui engagent : dits par le code (``avant``, ``porte.textes_du_code``),
rangés avec les phrases du code de la commande (exception du plan : le fait accompli), mot pour mot comme avant. C6 n° 9 (décision d'Evan 25/11 9 h 30) : le modèle les dit ;
C7 (B7) : la base ne rend plus aucun texte ; B9 : le catalogue supprimé, ce que disait celui d'avant est dans ses faits, que le modèle reçoit."""

from __future__ import annotations

from api.db.bases_clients import restauration_reservation as RR
from api.tests.mark import test_restauration_reservation as RESA

salle, creer, SAMEDI_20H = RESA.salle, RESA.creer, RESA.SAMEDI_20H


async def test_la_base_dit_les_phrases_du_registre(salle):
    """C6 n° 9 (décision d'Evan 25/11 9 h 30) : la base ne rend plus les phrases du registre ; C7 B9 : plus de texte de secours, ses faits portent le fait ; le modèle le dit."""

    r = await creer(salle)
    assert r.statut == "ENREGISTREE"
    # C6 n° 12 (décision d'Evan 25/11 9 h 30) : le module des phrases du code est supprimé ; le texte de secours garde les mots d'avant
    # C7 (B7) : la base ne rend plus de texte ; celui d'avant se refait de ses faits (personnes, quand, nom), que le modèle reçoit
    assert r.suggestion == "" and (r.faits["couverts"], r.faits["quand_dit"], r.faits["prenom"]) == (2, "samedi quatorze novembre à vingt heures", "Alice"), r
    m = await RR.modifier_reservation(salle.c, salle.a, r.faits["numero"], {"couverts": 3})
    assert m.statut == "OK" and m.suggestion == "" and (m.faits["quand_dit"], m.faits["couverts"]) == ("samedi quatorze novembre à vingt heures", 3), m
    a = await RR.annuler_reservation(salle.c, salle.a, r.faits["numero"])
    assert a.statut == "OK" and a.suggestion == "" and a.faits["statut"] == "annulee", a
