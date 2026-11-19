"""[.mark] Brique FOR14 : le plateau à contenu fixe (inventaire, famille 5 ; « le plateau Sakura »).

Une formule dont chaque ligne est obligatoire à un seul choix : tout est posé d'office (FOR8), rien n'est modifiable (un autre choix est hors de la ligne), le contenu
est relu à la demande (fait ``contenu`` : chaque pièce et sa quantité, dans l'ordre de la carte).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_for14_relire_le_contenu(groupes: list[dict[str, Any]]) -> list[str] | None:
    """Le contenu d'une formule fixe (« 8 California saumon avocat »), ou ``None`` : une de ses lignes laisse un choix."""
    if not groupes:
        return None
    contenu = []
    for g in groupes:
        vendables = [o for o in g["options"] if o["vendable"]]
        if g.get("role") != "etape" or g["min"] < 1 or len(vendables) != 1:
            return None
        contenu.append(f"{g['max']} {vendables[0]['nom']}")
    return contenu


def faits_de_la_formule(formule: dict[str, Any], groupes: list[dict[str, Any]]) -> dict[str, Any]:
    contenu = brique_for14_relire_le_contenu(groupes)
    return {"contenu": contenu} if contenu else {}


enregistrer(Brique(
    "FOR14", "formules", "C", (("formules", "lignes"),), brique_for14_relire_le_contenu,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/FOR14",
    phrase="la lecture rend le contenu fixe, rien n'est demandé",
))
