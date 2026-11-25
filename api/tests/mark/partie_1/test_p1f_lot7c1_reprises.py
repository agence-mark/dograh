"""[.mark] Lot 7b-C1, reprises de l'audit du 25/11 : un test par reprise (R2 à R6), chacun vu rouge avant son correctif."""

from __future__ import annotations

from api.services.commande import phrases_dites_par_le_code as PHRASES_DITES


def test_la_note_de_moitie_est_une_phrase_du_code_relue_dans_la_relecture():
    """R2 : la note « sans X sur la moitié Y » est relue à la personne (relecture) : elle vit au registre, avec son exception, pas dans une fonction identité."""
    assert PHRASES_DITES.note_de_moitie(ingredient="oignons", moitie="Regina") == "sans oignons sur la moitié Regina"
    assert PHRASES_DITES.PHRASES["note_de_moitie"].exception == PHRASES_DITES.EXCEPTION_RELECTURE
