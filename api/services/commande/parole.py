"""[.mark] Mécanisme commun : les petites phrases proposées par le moteur. La mise en mots (montants, heures, noms accordés) vit dans ``services/mots_dits.py`` ;
ce fichier la ré-exporte pour les gestes du moteur et de la réservation. Lot 6 : ``a_dire_dicible``, la barrière des chiffres appliquée à la phrase de
la fiche de la commande (``actions_communes/barriere_des_chiffres.py``)."""

from __future__ import annotations

from collections.abc import Iterable

from api.services.mots_dits import (  # noqa: F401
    _lettres, _lettres_f, article_indefini, chiffres_en_lettres, duree_en_lettres, genre_du_mot, heure_en_lettres, liste_dite, liste_dite_et,
    montant_en_lettres, nom_dit, nombre_en_lettres, phrase_nette, pluriel_du_mot,
)


def a_dire_dicible(a_dire: str, executes: Iterable[dict] = (), paroles: Iterable[str] = ()) -> bool:
    """La phrase de la fiche (``a_dire``) peut-elle être dite telle quelle ? Non si elle porte un chiffre que le code doit dire (lot 6, E14)."""
    from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase

    return bool(str(a_dire or "").strip()) and not chiffre_dans_la_phrase(a_dire, executes, paroles)
