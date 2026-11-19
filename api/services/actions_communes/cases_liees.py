"""[.mark] Le filet des cases liées (chantier Partie 1, lot 3 ; D8 ; table du banc ``banc-b5/contrat_b5.py`` ``LIEES``, ``DEPEND_DE_TOUT``).

Quand une case est refusée pour une règle LÉGITIME (valeur hors liste, valeur pas dans ses mots, récapitulatif pas accepté), les cases
indépendantes sont exécutées ; les cases liées à la case refusée ne le sont pas (jamais un bloc exécuté à moitié). Le filet ne sert JAMAIS à
rattraper un texte ambigu : il n'agit que sur un refus nommé. Chaque ligne de la table a son test.
"""

from __future__ import annotations

from collections.abc import Iterable

# Le lieu de livraison forme un bloc ; espèces et billet forment un bloc.
LIEES: tuple[tuple[str, ...], ...] = (
    ("mode_de_retrait", "adresse", "commune", "consigne_livreur"),
    ("moyen_de_paiement", "rendu_sur"),
)
# Ces cases agissent sur toute la commande : jamais exécutées si une autre case de la même fiche est refusée.
DEPEND_DE_TOUT: tuple[str, ...] = ("c_est_tout", "vider_le_panier", "annuler_la_commande")
TOUTES = "*"


def cases_ecartees(refusees: Iterable[str]) -> set[str]:
    """Les cases à ne pas exécuter quand ``refusees`` le sont : elles-mêmes, leurs cases liées, et les cases qui dépendent de toute la fiche."""
    ecartees = set(refusees)
    if not ecartees:
        return set()
    if TOUTES in ecartees:
        return {TOUTES}
    for bloc in LIEES:
        if ecartees & set(bloc):
            ecartees |= set(bloc)
    return ecartees | set(DEPEND_DE_TOUT)
