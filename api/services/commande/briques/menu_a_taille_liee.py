"""[.mark] Brique FOR6 : le menu à taille liée (inventaire, famille 5 ; « en maxi », « King Size » +0,80 €).

Les tailles d'une formule (``tailles`` : ``[{"nom", "ecart", "declinaisons": {"<nom de ligne>": "<nom de déclinaison>"}}]``, la taille de base comprise) sont ses
déclinaisons ; la taille collée au nom se lit par ``lire_la_taille_collee_au_nom`` (lot 8 : « menu kebab maxi »). Passer à une taille change la déclinaison des
lignes qu'elle cite (la boisson en 50 cl) et ajoute son écart au prix. Conflit avec OPT1 (D34, conflit 3) : les choix faits sont GARDÉS, seule leur déclinaison
change ; un choix qui n'a pas la déclinaison de la taille est refusé avec les choix de l'étape qui l'ont (jamais remplacé à la place de la personne).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def tailles_de(formule: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in (formule.get("tailles") or []) if isinstance(t, dict) and t.get("nom")]


def declinaison_voulue(taille: dict[str, Any] | None, nom_de_ligne: str) -> str | None:
    """La déclinaison que la taille donne aux choix de cette ligne ; ``None`` : la taille ne la change pas."""
    return ((taille or {}).get("declinaisons") or {}).get(nom_de_ligne)


def brique_for6_passer_en_maxi(etape: dict[str, Any], choix: list[dict[str, Any]], taille: dict[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Les choix de cette étape à la taille de la formule : ``(choix, None)`` (le même produit, à la déclinaison de la taille), ou ``(choix d'avant, refus)``."""
    voulue = declinaison_voulue(taille, etape["nom"])
    if voulue is None:
        return choix, None
    sortie = []
    for c in choix:
        option = next((o for o in etape["options"] if o["code"] == c["option_code"]), None)
        cible = next((d for d in (option or {}).get("declinaisons_du_produit") or [] if d["nom"] == voulue and d["vendable"] and not d["rupture"]), None)
        if cible is None:
            admis = [o["produit"] for o in etape["options"] if any(d["nom"] == voulue and d["vendable"] for d in o.get("declinaisons_du_produit") or [])]
            return choix, {"raison": "choix_sans_la_taille", "valeur": c.get("nom") or c["option_code"], "etape": etape["nom"], "taille": (taille or {}).get("nom"),
                           "choix": list(dict.fromkeys(admis))}
        sortie.append({**c, "option_code": cible["code"], "nom": f"{option['produit']} {cible['nom']}"})
    return sortie, None


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        f["tailles"] = None
    return carte


enregistrer(Brique(
    "FOR6", "formules", "C", (("formules", "tailles"),), brique_for6_passer_en_maxi,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR6",
    phrase="les tailles de la formule sont ses variantes ; passer en grand garde les choix",
))
