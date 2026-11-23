"""[.mark] Brique FOR8 : le jouet ou la surprise (inventaire, famille 5 ; KFC, Kinder).

Un produit ordinaire de la carte (vendu seul à son prix) que le menu enfant comprend sur une ligne à un seul choix : posé d'office dans la formule, à 0 €, rien n'est
demandé. Conflit avec FOR7 (D34, conflit 2) : jamais facturé deux fois ; demandé à part dans la même fiche que le menu, c'est la garde
``article_deja_choix_de_la_formule`` (le code ne devine pas s'il le veut en plus).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_for8_inclus_ou_vendu_seul(etape: dict[str, Any]) -> list[dict[str, Any]]:
    """Ce qu'une étape pose d'office : son seul choix possible, quand elle est obligatoire et n'en a qu'un (rien n'est choisi à la place de la personne sinon)."""
    vendables = [o for o in etape["options"] if o["vendable"] and not o["rupture"]]
    return vendables if len(vendables) == 1 and etape["min"] >= 1 else []


enregistrer(Brique(
    "FOR8", "formules", "C", (("formules", "lignes"),), brique_for8_inclus_ou_vendu_seul,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/FOR8",
    phrase="rien de nouveau : la ligne à un seul choix est posée d'office",
))
