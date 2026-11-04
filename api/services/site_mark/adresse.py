"""[.mark] Revue serveur M2 : l'adresse du visiteur, lue derrière un relais de confiance, en un seul endroit.

Derrière Railway (ou nginx), ``request.client.host`` est l'adresse du RELAIS : tous les visiteurs d'un site partageraient la
même limite par adresse. L'adresse réelle est dans ``X-Forwarded-For``, mais cet en-tête s'écrit à la main : on ne le lit QUE
si la connexion vient d'un relais déclaré. Réglage : la variable ``FORWARDED_ALLOW_IPS`` (la même que celle d'uvicorn),
liste séparée par des virgules d'adresses, de réseaux (``10.0.0.0/8``) ou ``*``. Vide ou absente : aucune confiance, les
en-têtes sont ignorés (un visiteur ne choisit jamais l'adresse qu'on lui compte).

On lit ``X-Forwarded-For`` de droite à gauche en sautant les relais de confiance : la première adresse qui n'en est pas un est
celle du visiteur (ce que le visiteur a écrit à gauche de la chaîne ne compte jamais).
"""

from __future__ import annotations

import ipaddress
import os
from typing import Any

VARIABLE = "FORWARDED_ALLOW_IPS"


def _reseaux_de_confiance(valeur: str | None) -> tuple[bool, list[Any]]:
    """(tous, réseaux) d'après la variable ; une entrée illisible est ignorée (jamais de confiance par erreur)."""
    reseaux: list[Any] = []
    for morceau in (valeur or "").split(","):
        morceau = morceau.strip()
        if not morceau:
            continue
        if morceau == "*":
            return True, []
        try:
            reseaux.append(ipaddress.ip_network(morceau, strict=False))
        except ValueError:
            continue
    return False, reseaux


def _adresse(texte: str) -> Any | None:
    try:
        return ipaddress.ip_address(texte.strip())
    except ValueError:
        return None


def adresse_du_visiteur(request: Any, *, relais: str | None = None) -> str | None:
    """L'adresse du visiteur, ou ``None`` si la connexion n'en dit aucune. ``relais`` : le réglage (défaut : l'environnement)."""
    pair = request.client.host if getattr(request, "client", None) else None
    if not pair:
        return None
    tous, reseaux = _reseaux_de_confiance(os.environ.get(VARIABLE) if relais is None else relais)
    pair_ip = _adresse(pair)
    de_confiance = (lambda ip: True) if tous else (lambda ip: ip is not None and any(ip in r for r in reseaux))
    if not de_confiance(pair_ip):
        return pair
    chaine = request.headers.get("x-forwarded-for", "")
    morceaux = [m for m in chaine.split(",") if m.strip()]
    for morceau in reversed(morceaux):
        ip = _adresse(morceau)
        if ip is None:
            return pair  # chaîne illisible : on garde l'adresse du relais plutôt qu'une valeur choisie par le visiteur
        if not de_confiance(ip):
            return str(ip)
    # Toute la chaîne est faite de relais de confiance (réglage « * ») : la première adresse est celle du visiteur.
    premiere = _adresse(morceaux[0]) if morceaux else None
    return str(premiere) if premiere is not None else pair
