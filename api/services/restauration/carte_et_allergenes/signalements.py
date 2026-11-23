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


_COUPURES = re.compile(r"\s*(?:,|;|/|\+|(?<!\w)et(?!\w)|(?<!\w)ainsi que(?!\w)|(?<!\w)puis(?!\w))\s*", re.IGNORECASE)
_PAS_UN_ALLERGENE = re.compile(r"(?<!\w)noix de coco(?!\w)", re.IGNORECASE)  # la noix de coco n'est pas un des quatorze : jamais lue « fruits à coque »
_MOTS_VIDES = frozenset(
    "je suis ai allergique allergiques allergie allergies intolérant intolérante intolérance intolerance a au aux à de du des d la le les l un une en très "
    "sévère severe forte fort grave pour moi mon ma mes sinon aussi même meme".split()
)


def _mot_present(mot: str, bas: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(mot.casefold())}s?(?!\w)", bas) is not None


def codes_dits(texte: str) -> tuple[list[str], bool]:
    """A1 : TOUS les codes des quatorze que l'appelant nomme (« gluten et arachides », « le lactose et les cacahuètes »), au mot entier (« laitue » n'est pas du lait),
    dans l'ordre de la carte des quatorze ; et si une partie de ce qu'il dit n'est PAS reconnue (« gluten et kiwi ») : alors le fait est « à confirmer par l'équipe »
    (jamais une allergie passée sous silence). Une phrase sans aucun code est ``([], True)`` seulement quand elle porte un mot autre que de liaison."""
    bas = _PAS_UN_ALLERGENE.sub("coco", texte.casefold())
    trouves = [code for code, (_, mots) in LES_QUATORZE.items() if any(_mot_present(m, bas) for m in mots)]
    inconnu = False
    for morceau in _COUPURES.split(bas):
        if not morceau.strip():
            continue
        if any(_mot_present(m, morceau) for _, mots in LES_QUATORZE.values() for m in mots):
            continue
        # un morceau sans code reconnu : il compte seulement s'il porte autre chose que des mots de liaison (« allergique à » seul ne dit rien)
        if [m for m in re.findall(r"[\w'’-]+", morceau) if m.replace("'", "").replace("’", "") not in _MOTS_VIDES and m not in _MOTS_VIDES]:
            inconnu = True
    return trouves, inconnu


def code_dit(texte: str) -> str | None:
    """Le code de l'allergène que l'appelant nomme (« cacahuètes », « le blé »), ou ``None`` ; le premier quand il en nomme plusieurs (``codes_dits`` les rend tous)."""
    trouves, _ = codes_dits(texte)
    return trouves[0] if trouves else None


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


# Lot 15 (INF3, INF4) : le code de l'ÉTIQUETTE que la carte peut porter pour un régime dit ; un régime sans étiquette possible (casher, sans viande) n'a pas de code.
CODE_DU_REGIME: dict[str, str] = {"végétalien": "vegetalien", "végétarien": "vegetarien", "halal": "halal"}


def regime_code(texte: str) -> str | None:
    """Le code de l'étiquette du régime que l'appelant nomme, ou ``None`` (aucun régime, ou un régime que la carte n'étiquette pas)."""
    dit = regime_dit(texte)
    return CODE_DU_REGIME.get(dit) if dit else None


def regime_dit(texte: str) -> str | None:
    """Le régime que l'appelant nomme (l'expression à lui redire), ou ``None``."""
    bas = texte.casefold()
    for dit, motif in LES_REGIMES:
        if re.search(rf"(?<!\w)(?:{motif})", bas):
            return dit
    return None
