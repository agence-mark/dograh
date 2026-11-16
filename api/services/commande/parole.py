"""[.mark] Mécanisme commun : les petites phrases proposées par le moteur. La mise en mots (montants, heures, noms accordés) vit dans ``services/mots_dits.py`` ;
ce fichier la ré-exporte pour les gestes du moteur et de la réservation."""

from __future__ import annotations

from api.services.mots_dits import (  # noqa: F401
    _lettres, _lettres_f, article_indefini, chiffres_en_lettres, duree_en_lettres, genre_du_mot, heure_en_lettres, liste_dite, liste_dite_et,
    montant_en_lettres, nom_dit, nombre_en_lettres, phrase_nette, pluriel_du_mot,
)
