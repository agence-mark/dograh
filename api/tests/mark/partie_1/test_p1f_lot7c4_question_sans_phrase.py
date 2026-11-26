"""[.mark] Lot 7b-C4, canal 3 : la question que voit le modèle n'a de texte que si le code la dit lui-même (liste fermée), jamais la phrase de secours."""

from __future__ import annotations

from api.services.actions_communes import enveloppe as E
from api.services.commande import registre as RQ
from api.services.phrases import catalogue as CAT

# Chaque type de la liste fermée, lié au motif réglé qui le dit (C6 n° 12, décision d'Evan 25/11 9 h 30 : ``PHRASES_DU_CODE`` remplace les exceptions du plan) : une question dite par le
# code est une phrase réglée de la liste fermée. C6 n° 3b et 8 : la relecture de la commande, les récapitulatifs et l'annulation de la réservation n'y sont plus, le modèle les dit.
MOTIF_DU_TYPE = {
    RQ.TYPE_DU_NUMERO_DICTE: CAT.NUMERO_DICTE_RELU,
}


def test_chaque_type_dit_par_le_code_a_son_motif_de_la_liste_fermee():
    assert set(MOTIF_DU_TYPE) == E.QUESTIONS_DITES_PAR_LE_CODE
    assert all(m in CAT.PHRASES_DU_CODE for m in MOTIF_DU_TYPE.values())


def test_une_question_dite_par_le_code_garde_son_texte_les_autres_n_en_ont_plus():
    for type_ in E.QUESTIONS_DITES_PAR_LE_CODE:
        assert E.Question("Q-1", type_, "Je vous relis.").vers_json()["texte"] == "Je vous relis."
    for type_ in ("relecture", "variante", "ambiguite", "choix", "heure_proposee", RQ.TYPE_ANNULATION, "proposition", "etape", "plusieurs_choix"):
        assert E.Question("Q-1", type_, "Quelle taille ?").vers_json()["texte"] == "", type_


def test_la_fermeture_deja_dite_est_un_fait_simple_pour_le_modele():
    """Correctif d'audit C1 : une fois la fermeture dite (journal ``J``), le modèle reçoit ``fermeture_dite`` (un booléen) et la redit plus ; avant, rien."""
    from api.services.actions_communes import journal_du_dit as J
    from api.services.commande import porte

    from api.services.commande import panier as P

    p = P.nouveau()
    assert "fermeture_dite" not in porte._faits_de_la_fiche(p, False, None, (), (), None)
    assert J.une_fois(p, J.FERMETURE)
    assert porte._faits_de_la_fiche(p, False, None, (), (), None)["fermeture_dite"] is True
