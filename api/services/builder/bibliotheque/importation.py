"""[.mark] Bibliothèque : importer une source du marché comme Candidat (B35), et comparer au réimport.

Une importation garde son **origine** (source, licence, date). Réimporter la même source ne remplace rien :
elle ajoute une version Candidat **si** le contenu a changé et rend le comparatif de ce qui a changé. Une
recette réimportée retombe donc en Candidat (le nouveau contenu n'est pas prouvé) ; l'ancienne version
reste dans l'historique avec son banc.

L'adresse se lit côté serveur (``lire_adresse``) : https seulement, jamais une adresse privée ou locale (le
nom est résolu AVANT la requête, toutes les adresses doivent être publiques), sans suivre de redirection,
texte seulement, taille bornée.
"""

from __future__ import annotations

import asyncio
import difflib
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlsplit

import httpx

from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Element, Origine
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import IMPORT_MAX_OCTETS

DELAI_LECTURE_S = 10.0


def comparatif(ancien: dict[str, Any], nouveau: dict[str, Any]) -> dict[str, Any]:
    """Ce qui a changé entre deux contenus : un diff ligne à ligne de leur JSON trié."""
    a = json.dumps(ancien, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    b = json.dumps(nouveau, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    diff = [ligne for ligne in difflib.unified_diff(a, b, "avant", "apres", lineterm="", n=1)]
    return {
        "identique": a == b,
        "ajoutees": sum(1 for ligne in diff if ligne.startswith("+") and not ligne.startswith("+++")),
        "retirees": sum(1 for ligne in diff if ligne.startswith("-") and not ligne.startswith("---")),
        "diff": "\n".join(diff),
    }


async def importer(
    famille: str,
    slug: str,
    titre: str,
    contenu: dict[str, Any],
    origine: Origine,
    auteur: str,
) -> dict[str, Any]:
    """Crée le Candidat, ou ajoute une version si la source a changé. Rend ``{element, comparatif, cree}``."""
    existant = await service.element_ou_none(famille, slug)
    if existant is None:
        element = await service.creer(famille, slug, titre, contenu, auteur, notes="Importé.", origine=origine)
        return {"element": element, "comparatif": None, "cree": True}
    ancienne = _derniere_importee(existant, origine.source)
    reference = ancienne.contenu if ancienne is not None else existant.courante.contenu
    diff = comparatif(reference, contenu)
    if diff["identique"]:
        return {"element": existant, "comparatif": diff, "cree": False}
    element = await service.ajouter_version(
        famille, slug, contenu, auteur, notes=f"Réimporté depuis {origine.source}.", origine=origine
    )
    return {"element": element, "comparatif": diff, "cree": False}


def _derniere_importee(element: Element, source: str):
    importees = [v for v in element.versions if v.origine is not None and v.origine.source == source]
    return max(importees, key=lambda v: v.numero) if importees else None


# --- l'adresse ----------------------------------------------------------------------------------------------


async def _adresses_publiques(hote: str) -> bool:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(hote, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


async def lire_adresse(adresse: str, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Le texte d'une page publique. 422 pour une adresse refusée ou illisible."""
    morceaux = urlsplit(adresse)
    if morceaux.scheme != "https" or not morceaux.hostname:
        raise ErreurBibliotheque("Only public https addresses are imported.")
    if not await _adresses_publiques(morceaux.hostname):
        raise ErreurBibliotheque("This address is not public: nothing is read from it.")
    try:
        async with httpx.AsyncClient(timeout=DELAI_LECTURE_S, follow_redirects=False, transport=transport) as client:
            async with client.stream("GET", adresse, headers={"Accept": "text/plain, text/markdown, application/json"}) as reponse:
                if reponse.status_code != 200:
                    raise ErreurBibliotheque(f"The address answered {reponse.status_code}.")
                morceaux_lus: list[bytes] = []
                total = 0
                async for morceau in reponse.aiter_bytes():
                    total += len(morceau)
                    if total > IMPORT_MAX_OCTETS:
                        raise ErreurBibliotheque(f"The page is too large (more than {IMPORT_MAX_OCTETS} bytes).")
                    morceaux_lus.append(morceau)
    except httpx.HTTPError:
        raise ErreurBibliotheque("The address could not be read.") from None
    try:
        return b"".join(morceaux_lus).decode("utf-8")
    except UnicodeDecodeError:
        raise ErreurBibliotheque("The page is not text.") from None
