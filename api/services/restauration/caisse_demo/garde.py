"""[.mark] Module Restauration, lot 20 : les GARDES de la caisse de démo (D4, D5) : Labo seulement, interrupteur éteint par défaut.

- l'**interrupteur d'environnement** ``CAISSE_DEMO_ACTIVE`` (éteint par défaut) : éteint, la caisse de démo n'existe pas (404 partout, aucune prise ne s'y branche) ;
- l'**organisation de type Labo** : seule l'organisation marquée Labo peut créer des restaurants de test, les brancher, ou être servie par la caisse de démo.
  Une organisation cliente est refusée partout, même avec un jeton de caisse de démo en main (jamais une prise d'un client branchée sur une caisse de démo).
"""

from __future__ import annotations

import os

VARIABLE = "CAISSE_DEMO_ACTIVE"
VALEURS_ALLUMEES = frozenset({"1", "true", "oui", "yes", "on"})


def interrupteur_allume() -> bool:
    return os.environ.get(VARIABLE, "").strip().lower() in VALEURS_ALLUMEES


async def organisation_est_labo(organization_id: int | None) -> bool:
    """Vrai seulement pour l'organisation marquée Labo (relue en base, repli par variable : comme le reste du Labo)."""
    if organization_id is None:
        return False
    from api.services.builder.constantes import organisation_bibliotheque
    from api.services.equipe_mark.espaces import rafraichir_labo

    marque = await rafraichir_labo()
    labo = marque if marque is not None else organisation_bibliotheque()
    return labo is not None and labo == organization_id


async def caisse_de_demo_permise(organization_id: int | None) -> bool:
    return interrupteur_allume() and await organisation_est_labo(organization_id)
