"""[.mark] Module Restauration, lot 7 (E-14, E-15) : les quatorze allergènes, dits en français, pour le geste ``voir_produit``.

Le moteur de commande ne connaît pas le mot « allergène » : il lit des ``signalements`` (liste de ``{code, libelle, mots}``) que la source lui
donne. ``None`` = INCONNU (la fiche du produit ne le dit pas : jamais dit « sans »), ``[]`` = connu, aucun.
"""

from __future__ import annotations

import re
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


def codes_nommes(nom: str) -> list[str]:
    """M88 : les codes que le NOM d'une option affirme (« Pistache » → fruits à coque), au mot entier. Sert seulement à dire une PRÉSENCE,
    jamais une absence ; un nom qui dit « sans » n'affirme rien (« pâte sans gluten »)."""
    bas = nom.casefold()
    if re.search(r"(?<!\w)sans(?!\w)", bas):
        return []
    return [
        code for code, (_, mots) in LES_QUATORZE.items()
        if any(re.search(rf"(?<!\w){re.escape(m.casefold())}s?(?!\w)", bas) for m in mots)
    ]


def code_dit(texte: str) -> str | None:
    """Le code de l'allergène que l'appelant nomme (« cacahuètes », « le blé »), ou ``None``."""
    bas = texte.casefold()
    for code, (_, mots) in LES_QUATORZE.items():
        if any(m.casefold() in bas for m in mots):
            return code
    return None


# M104 : les régimes que l'appelant peut demander (« végétarien », « halal »). Le format de la carte n'en porte AUCUNE donnée (C26) et aucun ne
# se déduit des quatorze allergènes : ils ne servent qu'à répondre honnêtement « je ne peux pas le garantir », jamais à trier la carte.
# (expression dite à l'appelant, motif reconnu) ; « sans viande », « sans porc » seulement avec « sans » (« une pizza au porc » n'est pas un régime).
LES_REGIMES: tuple[tuple[str, str], ...] = (
    ("végétalien", r"v[ée]g[ée]talien|v[ée]gan"),
    ("végétarien", r"v[ée]g[ée]tarien"),
    ("halal", r"halal"),
    ("casher", r"casher|kasher|cacher"),
    ("sans viande", r"sans\s+(?:de\s+)?(?:la\s+)?viande"),
    ("sans porc", r"sans\s+(?:de\s+)?(?:du\s+)?porc"),
)


def regime_dit(texte: str) -> str | None:
    """Le régime que l'appelant nomme (l'expression à lui redire), ou ``None``."""
    bas = texte.casefold()
    for dit, motif in LES_REGIMES:
        if re.search(rf"(?<!\w)(?:{motif})", bas):
            return dit
    return None
