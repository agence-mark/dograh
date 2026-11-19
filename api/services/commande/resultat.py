"""[.mark] Le retour fermé d'un geste de la commande : le même que celui du classeur (``Resultat(statut, faits, suggestion, manque)``).

Chantier Partie 1, lot 7 (R15, S11) : les définitions vivent dans ``actions_communes/resultat.py`` (la réservation les importe de là, jamais d'un module de
la commande) ; ce fichier les re-exporte pour les importeurs de la commande, sans copie.
"""

from api.services.actions_communes.resultat import (  # noqa: F401
    CLE_NUMERO_AFFICHE,
    CLE_NUMERO_RETENU,
    CLE_NUMERO_S_AFFICHE,
    CLE_SECOND_NUMERO_RETENU,
    STATUTS,
    Resultat,
    avec_le_fait_du_numero_affiche,
    avec_numero_affiche,
    avec_numeros_retenus,
    numero_est_dit,
    question_apres_enregistrement,
    question_du_numero_affiche,
)

__all__ = [
    "STATUTS", "Resultat", "avec_le_fait_du_numero_affiche", "avec_numero_affiche", "avec_numeros_retenus", "question_apres_enregistrement", "question_du_numero_affiche",
]
