"""[.mark] Lot 7b-C3, commit 6 : les trois phrases du moteur de réservation dites par le code (la relecture, le récapitulatif d'un changement, la question d'annulation qui offre le déplacement) sont rangées
avec les phrases du code de la commande, chacune sous son exception du plan, mot pour mot comme avant."""

from __future__ import annotations

from api.services.commande import phrases_dites_par_le_code as PD


def test_la_relecture_de_la_reservation_dit_les_personnes_le_moment_le_nom_et_la_question():
    assert PD.relecture_de_la_reservation(personnes="deux personnes", quand="samedi à vingt heures", prenom="Alice") == "Je vous réserve pour deux personnes, samedi à vingt heures, au nom de Alice. C'est bon ?"
    assert PD.relecture_de_la_reservation(personnes="deux personnes", quand="samedi à vingt heures", prenom="Alice", question="Je note ce numéro ?").endswith("au nom de Alice. Je note ce numéro ?")
    assert PD.PHRASES["relecture_de_la_reservation"].exception == PD.EXCEPTION_RELECTURE


def test_le_recapitulatif_d_un_changement_relit_ce_qui_change():
    assert PD.relecture_du_changement("à vingt et une heures et au nom de Bob") == "Je change votre réservation : à vingt et une heures et au nom de Bob. C'est bon ?"
    assert PD.PHRASES["relecture_du_changement"].exception == PD.EXCEPTION_RELECTURE


def test_la_question_d_annulation_offre_le_deplacement_en_une_phrase_entiere():
    assert PD.annulation_de_la_reservation(quand="samedi à vingt heures", personnes="deux personnes") == "Je peux aussi la déplacer. Vous voulez annuler la réservation samedi à vingt heures pour deux personnes ?"
    assert PD.PHRASES["annulation_de_la_reservation"].exception == PD.EXCEPTION_DC4
