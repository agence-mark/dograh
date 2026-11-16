"""[.mark] Module Restauration, lot 26 (M26) : le lexique de la restauration pour accorder ce que l'agent dit (« une pizza moitié-moitié », « deux tiramisus »).

La mise en mots (``services/mots_dits.py``) est commune et ne connaît aucun métier : ici vit ce qu'elle ne sait pas, le genre des plats et des boissons et ce
qui est un nom commun (« tiramisu » prend un s) ou un nom propre (« Regina » ne le prend pas). Ordre : le premier mot du nom, puis la catégorie quand c'est un
plat (« Napoli » est dans les pizzas : une Napoli), sinon le masculin (« un Perrier », « un Gustave »). Un mot inconnu ne casse rien : il reste « un ».
"""

from __future__ import annotations

import unicodedata

# Premier mot du nom (minuscule, sans accent, au singulier) -> genre. Les noms communs prennent la minuscule et la marque du pluriel.
COMMUNS: dict[str, str] = {
    "pizza": "f", "salade": "f", "bruschetta": "f", "pate": "f", "pates": "f", "boisson": "f", "biere": "f", "eau": "f", "limonade": "f", "glace": "f",
    "tarte": "f", "mousse": "f", "creme": "f", "entree": "f", "assiette": "f", "formule": "f", "soupe": "f", "frite": "f", "frites": "f", "crepe": "f",
    "tiramisu": "m", "burger": "m", "cheeseburger": "m", "dessert": "m", "jus": "m", "vin": "m", "cafe": "m", "the": "m", "flan": "m", "gateau": "m",
    "fondant": "m", "menu": "m", "panini": "m", "calamars": "m", "sandwich": "m", "cocktail": "m", "soda": "m", "verre": "m",
}
# Des noms propres de la carte dont le genre est connu (le reste des boissons est masculin).
PROPRES: dict[str, str] = {"cristaline": "f", "felicite": "f", "orangina": "m", "perrier": "m"}
# Catégories de PLATS : leur genre vaut pour leurs articles (« une Napoli », « une Carbonara »).
CATEGORIES_DE_PLATS: dict[str, str] = {"pizza": "f", "pate": "f", "salade": "f", "bruschetta": "f", "entree": "f", "burger": "m"}


def _sans_accent(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte.casefold()) if unicodedata.category(c) != "Mn")


def genre_et_commun(nom: str, categorie: str | None = None) -> tuple[str, bool]:
    """``("f", True)`` pour « Pizza moitié-moitié » ; ``("f", False)`` pour « Regina » dans les pizzas ; ``("m", False)`` pour « Coca-Cola »."""
    mots = _sans_accent(nom or "").split()
    premier = mots[0] if mots else ""
    if premier in COMMUNS:
        return COMMUNS[premier], True
    if premier in PROPRES:
        return PROPRES[premier], False
    tete = _sans_accent(categorie or "")
    for racine, genre in CATEGORIES_DE_PLATS.items():
        if racine in tete:
            return genre, False
    return "m", False
