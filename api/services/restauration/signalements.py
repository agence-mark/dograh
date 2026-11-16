"""[.mark] Module Restauration, lot 7 (E-14, E-15) : les quatorze allergènes, dits en français, pour le geste ``voir_produit``.

Le moteur de commande ne connaît pas le mot « allergène » : il lit des ``signalements`` (liste de ``{code, libelle, mots}``) que la source lui
donne. ``None`` = INCONNU (la fiche du produit ne le dit pas : jamais dit « sans »), ``[]`` = connu, aucun.
"""

from __future__ import annotations

from typing import Any

# code (les 14 de la fiche produit, migration 025) -> (libellé dit, mots que l'appelant peut employer)
LES_QUATORZE: dict[str, tuple[str, tuple[str, ...]]] = {
    "gluten": ("le gluten", ("gluten", "blé", "ble", "farine", "céréale", "cereale")),
    "crustaces": ("les crustacés", ("crustacé", "crustace", "crevette", "homard", "langoustine", "crabe")),
    "oeufs": ("les œufs", ("oeuf", "œuf", "oeufs", "œufs")),
    "poissons": ("le poisson", ("poisson", "anchois", "thon", "saumon")),
    "arachides": ("les arachides", ("arachide", "cacahuète", "cacahuete", "cacahouète")),
    "soja": ("le soja", ("soja",)),
    "lait": ("le lait", ("lait", "lactose", "laitage", "produit laitier", "fromage", "crème", "creme")),
    "fruits_a_coque": ("les fruits à coque", ("fruit à coque", "fruits à coque", "noix", "noisette", "amande", "pistache", "cajou", "pécan", "pecan")),
    "celeri": ("le céleri", ("céleri", "celeri")),
    "moutarde": ("la moutarde", ("moutarde",)),
    "sesame": ("le sésame", ("sésame", "sesame")),
    "sulfites": ("les sulfites", ("sulfite", "sulfites")),
    "lupin": ("le lupin", ("lupin",)),
    "mollusques": ("les mollusques", ("mollusque", "moule", "huître", "huitre", "escargot", "calamar", "poulpe")),
}


def signalements_de(allergenes: list[str] | None) -> list[dict[str, Any]] | None:
    """``None`` : la fiche ne dit rien (inconnu). Sinon la liste, vide quand le produit n'en porte aucun."""
    if allergenes is None:
        return None
    return [{"code": c, "libelle": LES_QUATORZE[c][0], "mots": list(LES_QUATORZE[c][1])} for c in allergenes if c in LES_QUATORZE]


def code_dit(texte: str) -> str | None:
    """Le code de l'allergène que l'appelant nomme (« cacahuètes », « le blé »), ou ``None``."""
    bas = texte.casefold()
    for code, (_, mots) in LES_QUATORZE.items():
        if any(m.casefold() in bas for m in mots):
            return code
    return None
