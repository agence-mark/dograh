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

import difflib
import json
from typing import Any
from urllib.parse import urlsplit

import httpx

from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Element, Origine
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import IMPORT_MAX_OCTETS
from api.services.builder.dossiers import site

DELAI_LECTURE_S = 10.0
TYPES_IMPORTES = ("text/plain", "text/markdown", "text/x-markdown", "application/json", "application/octet-stream")


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


async def lire_adresse(
    adresse: str, *, transport: httpx.AsyncBaseTransport | None = None, resolveur: site.Resolveur | None = None
) -> str:
    """Le texte d'une page publique. 422 pour une adresse refusée ou illisible.

    Revue N1 : la lecture passe par la requête à adresse épinglée du site d'un client (``site._requete``) : l'adresse est
    résolue une fois, la connexion part vers elle (pas de rebond DNS entre le contrôle et la requête), une IPv4 écrite
    en IPv6 compte comme l'IPv4. Aucune redirection n'est suivie ici."""
    morceaux = urlsplit(adresse)
    if morceaux.scheme != "https" or not morceaux.hostname:
        raise ErreurBibliotheque("Only public https addresses are imported.")
    try:
        propre = site.normaliser(adresse)
        async with httpx.AsyncClient(
            transport=transport, timeout=DELAI_LECTURE_S, follow_redirects=False, trust_env=False, verify=True
        ) as client:
            _, reponse = await site._requete(
                client,
                propre,
                resolveur or site.resoudre_par_dns,
                redirections=0,
                types_permis=TYPES_IMPORTES,
                octets_max=IMPORT_MAX_OCTETS,
                accepte="text/plain, text/markdown, application/json",
            )
    except site.SiteRefuse as erreur:
        raise ErreurBibliotheque(f"This address is not read: {erreur}") from None
    except httpx.HTTPError:
        raise ErreurBibliotheque("The address could not be read.") from None
    morceaux_lus = [reponse.content]
    try:
        return b"".join(morceaux_lus).decode("utf-8")
    except UnicodeDecodeError:
        raise ErreurBibliotheque("The page is not text.") from None
