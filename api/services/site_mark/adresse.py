"""[.mark] Revue serveur M2 : l'adresse du visiteur, lue derrière des relais de confiance, en un seul endroit.

Derrière Railway (ou nginx), ``request.client.host`` est l'adresse du RELAIS : tous les visiteurs d'un site partageraient la
même limite par adresse. L'adresse réelle est dans ``X-Forwarded-For``, mais cet en-tête s'écrit à la main : on ne le lit
que si on déclare combien de relais de confiance précèdent le serveur.

Réglage : la variable ``MARK_RELAIS_DE_CONFIANCE`` (propre à .mark, distincte de ``FORWARDED_ALLOW_IPS`` d'uvicorn, qui peut
valoir ``*`` pour d'autres usages), un entier ``n``. L'adresse lue est le maillon de rang ``n`` en partant de la DROITE de
``X-Forwarded-For`` (chaque relais de confiance y ajoute l'adresse de celui qui s'y connecte ; ce que le visiteur écrit à
gauche ne compte jamais). Absente, vide, illisible ou ``0`` : aucune confiance, l'adresse est celle de la connexion.
"""

from __future__ import annotations

import ipaddress
import os
from typing import Any

VARIABLE = "MARK_RELAIS_DE_CONFIANCE"


def _nombre_de_relais(valeur: str | int | None) -> int:
    """Le nombre de relais d'après la variable ; tout ce qui n'est pas un entier positif vaut 0 (jamais de confiance par erreur)."""
    try:
        n = int(str(valeur).strip()) if valeur is not None else 0
    except ValueError:
        return 0
    return n if n > 0 else 0


def adresse_du_visiteur(request: Any, *, relais: str | int | None = None) -> str | None:
    """L'adresse du visiteur, ou ``None`` si la connexion n'en dit aucune. ``relais`` : le réglage (défaut : l'environnement)."""
    pair = request.client.host if getattr(request, "client", None) else None
    if not pair:
        return None
    n = _nombre_de_relais(os.environ.get(VARIABLE) if relais is None else relais)
    if n == 0:
        return pair
    morceaux = [m.strip() for m in request.headers.get("x-forwarded-for", "").split(",") if m.strip()]
    if len(morceaux) < n:
        return pair  # moins de maillons que de relais déclarés : la chaîne n'est pas celle qu'on attend
    try:
        return str(ipaddress.ip_address(morceaux[-n]))
    except ValueError:
        return pair  # maillon illisible : on garde l'adresse de la connexion plutôt qu'une valeur choisie par le visiteur
