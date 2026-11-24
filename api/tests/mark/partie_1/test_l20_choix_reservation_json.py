"""Lot 20 (banc final, n5) : au clavier, « annuler ma réservation » avec deux réservations possibles cassait l'enregistrement du tour
(« Object of type datetime is not JSON serializable »). Source : la question « laquelle ? » (``porte._question_de``) gardait les candidats
avec leur heure en objet date, alors que l'état de l'appel s'enregistre en JSON. La question est écrite en JSON, et le choix lit l'heure écrite.
"""

import json
from datetime import datetime, timedelta, timezone

from api.services.actions_communes.resultat import Resultat
from api.services.reservation import moteur
from api.services.reservation.porte import _question_de

PARIS = timezone(timedelta(hours=1))
CANDIDATS = [
    {"numero": "R1", "quand_dit": "jeudi soir", "prenom": "Martin", "personnes": 2, "debut": datetime(2026, 11, 26, 19, 0, tzinfo=PARIS), "dit": "jeudi soir, pour 2"},
    {"numero": "R2", "quand_dit": "jeudi soir", "prenom": "Martin", "personnes": 2, "debut": datetime(2026, 11, 26, 21, 0, tzinfo=PARIS), "dit": "jeudi soir, pour 2"},
]


def test_la_question_du_choix_s_ecrit_en_json_et_se_choisit_encore_par_l_heure():
    question = _question_de("retrouver", Resultat("AMBIGU", {"candidats": CANDIDATS}), {}, 3)
    relue = json.loads(json.dumps(question))  # le point de reprise du clavier
    assert [c["numero"] for c in moteur.choisir_le_candidat(relue["candidats"], ["celle de 21h"])] == ["R2"]
    assert [c["numero"] for c in moteur.choisir_le_candidat(CANDIDATS, ["celle de 19h"])] == ["R1"]
