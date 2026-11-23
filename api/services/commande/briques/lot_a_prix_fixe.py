"""[.mark] Brique FOR11 : le lot de N produits à prix fixe (inventaire, famille 5 ; « 3 seniors 30 € »).

Une formule ``par_lot`` d'une seule ligne (sa quantité est N) est le prix affiché du restaurant : au chiffrage, les unités que sa ligne accepte forment des lots complets,
dans l'ordre du panier (règle déterministe : le code ne choisit aucun prix, décision du 19/11) ; le reste est facturé à l'unité. Un lot est une ligne de la formule
(ses N choix, chacun avec ses propres choix), ce qui part en caisse comme un deal.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from api.services.commande.briques.registre import Brique, enregistrer


def formules_par_lot(formules: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in formules.values() if f.get("par_lot") and len(f.get("lignes") or []) == 1 and int(f["lignes"][0].get("quantite") or 1) > 1]


def brique_for11_compter_les_lots(
    brouillon: list[dict[str, Any]], formules: list[dict[str, Any]], accepte: Callable[[dict[str, Any], str], bool],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(lignes, lots)`` : les lignes du panier où les unités acceptées par une formule par lot sont regroupées en lots complets (une ligne de la formule par lot),
    le reste gardé à l'unité ; ``lots`` dit ce qui a été compté (``formule``, ``nombre``)."""
    lignes = [copy.deepcopy(l) for l in brouillon]
    lots: list[dict[str, Any]] = []
    for f in formules:
        n = int(f["lignes"][0].get("quantite") or 1)
        unites = [(i, l) for i, l in enumerate(lignes) if not l.get("lot_de") and accepte(f, l.get("code_caisse")) for _ in range(int(l.get("quantite", 1)))]
        complets = len(unites) // n
        if not complets:
            continue
        prises: dict[int, int] = {}
        nouvelles = []
        for k in range(complets):
            paquet = unites[k * n:(k + 1) * n]
            for i, _ in paquet:
                prises[i] = prises.get(i, 0) + 1
            nouvelles.append({"code_caisse": f["code_caisse"], "quantite": 1, "lot_de": f["id"],
                              "choix": [{"option_code": l["code_caisse"], "quantite": 1, "choix": copy.deepcopy(l.get("choix") or []),
                                         "retires": list(l.get("retires") or [])} for _, l in paquet]})
        restes = []
        for i, l in enumerate(lignes):
            reste = int(l.get("quantite", 1)) - prises.get(i, 0)
            if reste > 0:
                restes.append({**l, "quantite": reste})
        lignes = restes + nouvelles
        lots.append({"formule": f["nom"], "nombre": complets})
    return lignes, lots


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        f["par_lot"] = False
    return carte


enregistrer(Brique(
    "FOR11", "formules", "C", (("formules", "par_lot"), ("formules", "lignes")), brique_for11_compter_les_lots,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR11",
    phrase="rien de nouveau : les lots se comptent au chiffrage, le reste à l'unité",
))
