"""Lot 6 (G3) : deux objets, la commande et la conversation. Ce que le code tient pour mener l'appel vit sous UNE clé, jamais à plat dans la commande."""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import du as DU
from api.services.actions_communes import idempotence as ID
from api.services.actions_communes import registre_des_questions as RC

A_PLAT = ("tour_de_l_appel", "questions_ouvertes", "numeros_des_questions", "prochain_q", "hesitations_nees", "fiches_executees", "questions_fermees", "derniere_question_fermee", "boucle")


def test_la_conversation_ne_change_pas_ce_que_la_personne_vit():
    p = {"lignes": [{"n": 1, "ref": "a", "quantite": 1}], "question": None}
    avant = DU.ce_qui_se_voit(p)
    CONV.de(p)["tour_de_l_appel"] = 9
    CONV.de(p)["fiches_executees"] = ["x"]
    assert DU.ce_qui_se_voit(p) == avant


def test_la_memoire_des_fiches_et_les_numeros_vivent_dans_la_conversation():
    p: dict = {}
    assert ID.deja_executee(p, "cle") is False and ID.deja_executee(p, "cle") is True
    assert RC.numero(p, "objet:1") == "Q-1" and RC.numero(p, "objet:2") == "Q-2" and RC.numero(p, "objet:1") == "Q-1"
    assert [k for k in A_PLAT if k in p] == [] and set(p) == {CONV.CLE}
