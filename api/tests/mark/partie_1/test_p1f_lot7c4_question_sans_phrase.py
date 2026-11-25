"""[.mark] Lot 7b-C4, canal 3 : la question que voit le modèle n'a de texte que si le code la dit lui-même (liste fermée), jamais la phrase de secours."""

from __future__ import annotations

from api.services.actions_communes import enveloppe as E
from api.services.commande import phrases_dites_par_le_code as PD
from api.services.commande import registre as RQ

# Chaque type de la liste fermée, lié à son exception du plan (§ 2 de phrases_dites_par_le_code) : une question dite par le code est une exception écrite.
EXCEPTION_DU_TYPE = {
    "relecture": PD.EXCEPTION_RELECTURE,
    RQ.TYPE_DU_NUMERO_DICTE: PD.EXCEPTION_NUMERO,
    "recapitulatif": PD.EXCEPTION_RELECTURE,
    "recap_modif": PD.EXCEPTION_RELECTURE,
    "annulation": PD.EXCEPTION_DC4,
}


def test_chaque_type_dit_par_le_code_a_son_exception_du_plan():
    assert set(EXCEPTION_DU_TYPE) == E.QUESTIONS_DITES_PAR_LE_CODE
    assert all(ex in PD.EXCEPTIONS_DU_PLAN for ex in EXCEPTION_DU_TYPE.values())


def test_une_question_dite_par_le_code_garde_son_texte_les_autres_n_en_ont_plus():
    for type_ in E.QUESTIONS_DITES_PAR_LE_CODE:
        assert E.Question("Q-1", type_, "Je vous relis.").vers_json()["texte"] == "Je vous relis."
    for type_ in ("variante", "ambiguite", "choix", "heure_proposee", RQ.TYPE_ANNULATION, "proposition", "etape", "plusieurs_choix"):
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
