"""[.mark] S2 / D175 / D188 : le chemin d'une page, normalisé, et l'agent qui la sert (le plus long préfixe par segments).

UNE seule fonction de normalisation sert l'enregistrement (unicité par site et chemin) et la lecture : elles ne
peuvent pas diverger. Le préfixe se compte par SEGMENTS : ``/sav`` couvre ``/sav`` et ``/sav/retours``, jamais
``/savoir-faire``. ``/`` est « tout le site ».
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

LONGUEUR_MAX = 512
TOUT_LE_SITE = "/"
_ESPACES = re.compile(r"/{2,}")


class CheminInvalide(ValueError):
    pass


def normaliser(chemin: str | None) -> str:
    """Minuscules, sans paramètres ni ancre, sans barre finale, accents décodés ; vide ou ``/`` : tout le site."""
    if chemin is None:
        return TOUT_LE_SITE
    brut = str(chemin).strip()
    if not brut:
        return TOUT_LE_SITE
    if len(brut) > LONGUEUR_MAX:
        raise CheminInvalide("path too long")
    # Une adresse complète est acceptée (on ne garde que son chemin).
    # (``//a`` n'est PAS une adresse : sans « :// », on ne lit que le chemin lui-même.)
    chemin_seul = urlsplit(brut).path if "://" in brut.split("?", 1)[0] else brut.split("?", 1)[0].split("#", 1)[0]
    decode = unquote(chemin_seul).lower()
    if "\x00" in decode or any(ord(c) < 32 for c in decode):
        raise CheminInvalide("invalid character in path")
    if not decode.startswith("/"):
        decode = "/" + decode
    decode = _ESPACES.sub("/", decode)
    segments = [s for s in decode.split("/") if s not in ("", ".")]
    if ".." in segments:
        raise CheminInvalide("path segments '..' are not allowed")
    return "/" + "/".join(segments) if segments else TOUT_LE_SITE


def couvre(chemin_agent: str, chemin_page: str) -> bool:
    """Le chemin de l'agent couvre la page : même chemin, ou préfixe par segments entiers (``/`` couvre tout)."""
    if chemin_agent == TOUT_LE_SITE:
        return True
    return chemin_page == chemin_agent or chemin_page.startswith(chemin_agent + "/")


def plus_long_prefixe(candidats: dict[str, object], chemin_page: str):
    """Parmi ``{chemin normalisé: valeur}``, la valeur du chemin le plus précis qui couvre la page, sinon ``None``."""
    page = normaliser(chemin_page)
    meilleur = None
    for chemin, valeur in candidats.items():
        if couvre(chemin, page) and (meilleur is None or len(chemin) > len(meilleur[0])):
            meilleur = (chemin, valeur)
    return meilleur[1] if meilleur else None
