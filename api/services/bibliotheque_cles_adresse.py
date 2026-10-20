"""[.mark] L'adresse rattachée à une clé de la bibliothèque (fiabilite-orchestration, lot 10, F10).

Une clé de fournisseur peut porter l'adresse de son fournisseur (``https://api.exemple.test/v1``).
Elle ne part alors que vers cette adresse : un réglage qui vise un autre serveur ne reçoit pas la
clé, et le dit (erreur à l'enregistrement, journal d'erreur à l'appel). Une clé sans adresse (toutes
celles d'avant) se comporte exactement comme avant.

Module sans dépendance (ni base, ni routes) : ``cles_reference.py`` l'importe sans circuit, comme
``masking.py`` importe ``cles_reference.py``.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit


class AdresseInvalide(ValueError):
    """L'adresse donnée n'est pas une adresse de service utilisable (jamais la valeur dans le message)."""


def normaliser_l_adresse(adresse: Optional[str]) -> Optional[str]:
    """L'adresse d'un fournisseur sous sa forme rangée : ``https://hote[:port][/chemin]`` sans
    barre finale. ``None`` si vide. Refuse ce qui n'est pas http(s) avec un hôte, et tout ce qui
    pourrait porter un secret (identifiants dans l'adresse, paramètres, ancre)."""
    texte = (adresse or "").strip()
    if not texte:
        return None
    try:
        morceaux = urlsplit(texte)
        hote = morceaux.hostname
        _ = morceaux.port  # lève si le port est illisible
    except ValueError:
        raise AdresseInvalide("The address is not readable") from None
    if morceaux.scheme not in ("http", "https") or not hote:
        raise AdresseInvalide(
            "The address must start with http:// or https:// and name a host"
        )
    if morceaux.username or morceaux.password or morceaux.query or morceaux.fragment:
        raise AdresseInvalide(
            "The address must not carry credentials, parameters or a fragment: "
            "the key is stored apart"
        )
    return texte.rstrip("/")


def origine_de(adresse: Optional[str]) -> Optional[tuple[str, str, int]]:
    """``(schéma, hôte, port)`` d'une adresse, pour dire si deux adresses visent le même serveur
    (le chemin ne compte pas) ; ``None`` si elle n'est pas lisible."""
    try:
        morceaux = urlsplit((adresse or "").strip())
        if morceaux.scheme not in ("http", "https") or not morceaux.hostname:
            return None
        port = morceaux.port or (443 if morceaux.scheme == "https" else 80)
        return (morceaux.scheme, morceaux.hostname.lower(), port)
    except ValueError:
        return None


def meme_serveur(adresse_cle: Optional[str], adresse_service: Optional[str]) -> bool:
    """``True`` si la clé n'a pas d'adresse (clé d'avant : rien ne change) ou si les deux adresses
    visent le même serveur."""
    if not adresse_cle:
        return True
    cle = origine_de(adresse_cle)
    return cle is not None and cle == origine_de(adresse_service)
