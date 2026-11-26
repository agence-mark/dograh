"""Lot 20 (relecture, n4) : « Laquelle ? » était dit seul, sans les réservations : la personne ne savait pas quoi choisir. La question du choix porte la
phrase du moteur (« Vous en avez plusieurs : … Laquelle ? »). Lot 7b-C4 (§ 0, décision du coordinateur) : le code ne la dit plus ; les réservations sont des faits donnés au modèle (``candidats_dits``),
et la phrase reste au registre pour le repli, qui la dit si le modèle se tait. Lot 7b-C7 (B3) : la question n'a plus de texte ; le modèle relancé lit ses candidats
(``question_pour_la_relance``) ; son identité est son objet (les réservations en cause), jamais un texte."""

from datetime import datetime, timedelta, timezone

from api.services.actions_communes import registre_des_questions as RC
from api.services.actions_communes.enveloppe import Question
from api.services.actions_communes.repli import question_pour_la_relance
from api.services.actions_communes.resultat import Resultat
from api.services.reservation.porte import TABLE, _question_de, textes_du_code

PARIS = timezone(timedelta(hours=1))
SUGGESTION = "Vous en avez plusieurs : dimanche à dix-neuf heures, pour deux personnes ou dimanche à vingt et une heures, pour deux personnes. Laquelle ?"
CANDIDATS = [{"numero": "R1", "quand_dit": "dimanche à dix-neuf heures", "personnes": 2, "debut": datetime(2026, 11, 22, 19, tzinfo=PARIS), "dit": "a"},
             {"numero": "R2", "quand_dit": "dimanche à vingt et une heures", "personnes": 2, "debut": datetime(2026, 11, 22, 21, tzinfo=PARIS), "dit": "b"}]


def test_la_question_du_choix_porte_les_reservations_et_le_code_ne_la_dit_pas():
    q = _question_de("retrouver", Resultat("AMBIGU", {"candidats": CANDIDATS}, SUGGESTION, "reservation"), {}, 2)
    assert q["texte"] == "" and q["candidats_dits"] == ["a", "b"]  # C7 (B3) : aucun texte au registre ; les réservations sont des faits
    assert textes_du_code({}, Resultat("AMBIGU", {"candidats": CANDIDATS}, SUGGESTION, "reservation"), "retrouver", q, False) == {}
    assert Question("Q-1", q["type"], q["texte"]).vers_json()["texte"] == ""  # le modèle ne la reçoit pas


def test_la_question_vide_reste_posee_avec_ses_candidats_pour_la_relance():
    """C7 (B3) : modèle muet sur « laquelle ? » / avant, la relance pouvait lire la phrase du moteur / après, elle lit les réservations (``candidats_dits``), jamais un texte."""
    q = _question_de("retrouver", Resultat("AMBIGU", {"candidats": CANDIDATS}, "", "reservation"), {}, 2)
    relance = question_pour_la_relance(q)
    assert relance["candidats_dits"] == ["a", "b"] and "texte" not in relance, relance


def test_deux_laquelle_sur_des_reservations_differentes_restent_deux_questions():
    """Refus 11 : deux « laquelle ? » sans texte, à deux recherches sur des réservations différentes, ne sont jamais pris pour la même question (l'objet fait l'identité)."""
    e: dict = {}
    autres = [{**c, "numero": c["numero"] + "-bis"} for c in CANDIDATS]
    q1 = _question_de("retrouver", Resultat("AMBIGU", {"candidats": CANDIDATS}, "", "reservation"), e, 2)
    RC.ouvrir(TABLE, e, q1)
    q2 = _question_de("retrouver", Resultat("AMBIGU", {"candidats": autres}, "", "reservation"), e, 3)
    RC.ouvrir(TABLE, e, q2)
    assert q1["texte"] == q2["texte"] == "" and q1["id"] != q2["id"] and q1["objet"] != q2["objet"], (q1, q2)
    redite = _question_de("retrouver", Resultat("AMBIGU", {"candidats": CANDIDATS}, "", "reservation"), e, 4)
    assert redite["id"] == q1["id"], (redite, q1)  # la même question redonnée garde son numéro
