"""Lot 20 (relecture, n4) : « Laquelle ? » était dit seul, sans les réservations : la personne ne savait pas quoi choisir. La question du choix porte la
phrase du moteur (« Vous en avez plusieurs : … Laquelle ? »), et le code la dit lui-même (elle porte des jours et des heures)."""

from datetime import datetime, timedelta, timezone

from api.services.actions_communes.resultat import Resultat
from api.services.reservation.porte import _question_de, textes_du_code

PARIS = timezone(timedelta(hours=1))
SUGGESTION = "Vous en avez plusieurs : dimanche à dix-neuf heures, pour deux personnes ou dimanche à vingt et une heures, pour deux personnes. Laquelle ?"
CANDIDATS = [{"numero": "R1", "quand_dit": "dimanche à dix-neuf heures", "personnes": 2, "debut": datetime(2026, 11, 22, 19, tzinfo=PARIS), "dit": "a"},
             {"numero": "R2", "quand_dit": "dimanche à vingt et une heures", "personnes": 2, "debut": datetime(2026, 11, 22, 21, tzinfo=PARIS), "dit": "b"}]


def test_la_question_du_choix_dit_les_reservations_et_le_code_la_dit():
    q = _question_de("retrouver", Resultat("AMBIGU", {"candidats": CANDIDATS}, SUGGESTION, "reservation"), 1, 2)
    assert q["texte"] == SUGGESTION
    assert textes_du_code({}, Resultat("AMBIGU", {"candidats": CANDIDATS}, SUGGESTION, "reservation"), "retrouver", q, False) == {"avant": SUGGESTION}
