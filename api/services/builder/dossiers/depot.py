"""[.mark] Builder, lot 3 : ce qui est déposé pour un agent (dossiers d'audit, adresse du site).

Rangement (aucune migration, R0-6) :

* l'**index** des dépôts : ``MARK_BUILDER:<agent>:depot`` (organisation du client), un petit JSON ;
* le **fichier d'origine** et le **texte extrait** (page par page) : ``services/storage.py`` (MinIO / S3), sous
  ``builder/<organisation>/<agent>/<dépôt>/`` ; le texte extrait y reste pour la traçabilité, la fiche n'en garde
  que les lignes et leur source.

Un dépôt illisible est GARDÉ dans l'index avec sa raison (la carte l'affiche) : on ne le perd pas en silence et on ne
l'invente pas.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from api.services.builder import stock
from api.services.builder.bibliotheque.modele import maintenant
from api.services.builder.constantes import cle_builder
from api.services.builder.dossiers import extraction, site
from api.services.builder.dossiers.extraction import Extraction, Page

DEPOTS_MAX = 40
NOM_MAX = 120


class ErreurDepot(Exception):
    pass


# --- le stockage de fichiers (une couture : les tests la remplacent par une mémoire) -----------------------------


async def ecrire_octets(cle: str, donnees: bytes) -> None:
    from api.services.storage import storage_fs

    if not await storage_fs.acreate_file_from_bytes(cle, donnees):
        raise ErreurDepot("The file could not be stored.")


async def lire_octets(cle: str) -> bytes | None:
    from api.services.storage import storage_fs

    descripteur, chemin = tempfile.mkstemp()
    os.close(descripteur)
    try:
        if not await storage_fs.adownload_file(cle, chemin):
            return None
        return await asyncio.to_thread(Path(chemin).read_bytes)
    finally:
        os.unlink(chemin)


async def supprimer_octets(cle: str) -> None:
    from api.services.storage import storage_fs

    try:
        await storage_fs.adelete_file(cle)
    except Exception:  # noqa: BLE001 -- un fichier déjà parti ne bloque pas le retrait du dépôt
        logger.info("[builder] fichier de dépôt déjà absent")


# --- l'index -----------------------------------------------------------------------------------------------------


def cle(workflow_id: int) -> str:
    return cle_builder(workflow_id, "depot")


def _racine(organization_id: int, workflow_id: int, depot_id: str) -> str:
    return f"builder/{organization_id}/{workflow_id}/{depot_id}"


def nom_propre(nom: str) -> str:
    """Le nom d'un fichier sans chemin, sans caractère de contrôle, borné : il sert de source et de clé de stockage."""
    base = re.split(r"[\\/]", nom or "")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().strip(".")
    return (base or "document")[:NOM_MAX]


async def lister(organization_id: int, workflow_id: int) -> list[dict[str, Any]]:
    brut = await stock.lire(organization_id, cle(workflow_id))
    return list((brut or {}).get("depots") or [])


async def _ecrire_index(organization_id: int, workflow_id: int, depots: list[dict[str, Any]]) -> None:
    await stock.ecrire(organization_id, cle(workflow_id), {"depots": depots})


def vue(depot: dict[str, Any]) -> dict[str, Any]:
    """Ce que l'écran et le cerveau voient d'un dépôt (jamais les clés de stockage)."""
    return {k: v for k, v in depot.items() if not k.startswith("cle_")}


async def _enregistrer(
    organization_id: int, workflow_id: int, depots: list[dict[str, Any]], depot: dict[str, Any], resultat: Extraction, texte_cle: str
) -> dict[str, Any]:
    if resultat.illisible:
        depot.update(statut="illisible", raison=resultat.illisible, pages=0, caracteres=0)
    else:
        corps = json.dumps(
            {"pages": [{"numero": p.numero, "texte": p.texte, "etiquette": p.etiquette} for p in resultat.pages]},
            ensure_ascii=False,
        ).encode("utf-8")
        await ecrire_octets(texte_cle, corps)
        depot.update(
            statut="lu", pages=len(resultat.pages), caracteres=resultat.caracteres, tronque=resultat.tronque, cle_texte=texte_cle
        )
    depots.append(depot)
    await _ecrire_index(organization_id, workflow_id, depots)
    return depot


def _nouveau(nom: str, genre: str, auteur: str) -> dict[str, Any]:
    return {"id": uuid.uuid4().hex[:12], "nom": nom, "genre": genre, "ajoute_par": auteur, "ajoute_le": maintenant().isoformat()}


async def deposer_fichier(organization_id: int, workflow_id: int, nom: str, contenu: bytes, auteur: str) -> dict[str, Any]:
    depots = await lister(organization_id, workflow_id)
    if len(depots) >= DEPOTS_MAX:
        raise ErreurDepot(f"At most {DEPOTS_MAX} deposits per agent: remove one first.")
    nom = nom_propre(nom)
    if any(d["nom"].casefold() == nom.casefold() for d in depots):
        raise ErreurDepot(f"« {nom} » is already deposited: remove it first to replace it.")
    resultat = await extraction.extraire_hors_boucle(nom, contenu)
    depot = _nouveau(nom, "fichier", auteur)
    racine = _racine(organization_id, workflow_id, depot["id"])
    if len(contenu) <= extraction.OCTETS_MAX:  # l'original est gardé (traçabilité), même illisible
        depot["cle_fichier"] = f"{racine}/original"
        await ecrire_octets(depot["cle_fichier"], contenu)
    depot["octets"] = len(contenu)
    return vue(await _enregistrer(organization_id, workflow_id, depots, depot, resultat, f"{racine}/texte.json"))


async def deposer_site(organization_id: int, workflow_id: int, adresse: str, auteur: str, **options: Any) -> dict[str, Any]:
    """Lit le site (pages publiques) et le range comme un dépôt dont chaque « page » est une page du site."""
    depots = await lister(organization_id, workflow_id)
    if len(depots) >= DEPOTS_MAX:
        raise ErreurDepot(f"At most {DEPOTS_MAX} deposits per agent: remove one first.")
    try:
        propre = site.normaliser(adresse)
        lecture = await site.lire_le_site(propre, **options)
    except site.SiteRefuse as erreur:
        raise ErreurDepot(str(erreur)) from None
    if any(d["nom"].casefold() == propre.casefold() for d in depots):
        raise ErreurDepot(f"« {propre} » is already deposited: remove it first to read it again.")
    depot = _nouveau(propre, "site", auteur)
    depot["refusees"] = [{"adresse": a, "raison": r} for a, r in lecture.refusees]
    racine = _racine(organization_id, workflow_id, depot["id"])
    return vue(await _enregistrer(organization_id, workflow_id, depots, depot, lecture.en_extraction(), f"{racine}/texte.json"))


async def retirer(organization_id: int, workflow_id: int, depot_id: str) -> bool:
    depots = await lister(organization_id, workflow_id)
    depot = next((d for d in depots if d["id"] == depot_id), None)
    if depot is None:
        return False
    for clef in ("cle_fichier", "cle_texte"):
        if depot.get(clef):
            await supprimer_octets(depot[clef])
    await _ecrire_index(organization_id, workflow_id, [d for d in depots if d["id"] != depot_id])
    return True


async def pages_de(organization_id: int, depot: dict[str, Any]) -> list[Page]:
    """Les pages extraites d'un dépôt lu. Vide si le dépôt est illisible ou si le texte a disparu du stockage."""
    if depot.get("statut") != "lu" or not depot.get("cle_texte"):
        return []
    brut = await lire_octets(depot["cle_texte"])
    if not brut:
        return []
    try:
        pages = json.loads(brut.decode("utf-8")).get("pages") or []
        return [Page(numero=int(p["numero"]), texte=str(p["texte"]), etiquette=str(p.get("etiquette") or "p.")) for p in pages]
    except (ValueError, KeyError, TypeError):
        return []


def etiquette_de_source(depot: dict[str, Any], page: Page) -> str:
    """La source d'une page : « audit.pdf, p. 3 » ; pour un site, l'adresse de la page elle-même."""
    if depot.get("genre") == "site":
        return page.etiquette
    return extraction.source(depot["nom"], page)


def source_deposee(depots: list[dict[str, Any]], source: str) -> bool:
    """Une source de la fiche est-elle un dépôt connu, ou la réponse d'une personne ?"""
    bas = (source or "").casefold()
    if bas.startswith(("réponse", "reponse", "answer")):
        return True
    return any(d["nom"].casefold() in bas for d in depots if d.get("statut") == "lu") or any(
        d.get("genre") == "site" and d["nom"].casefold().split("//")[-1].split("/")[0] in bas for d in depots
    )
