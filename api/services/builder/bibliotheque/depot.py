"""[.mark] Bibliothèque : déposer un document (PDF, Word, Markdown, texte) qui entre en Candidat.

La conversion est celle des dépôts d'un agent (``dossiers.extraction``) : faite SUR PLACE, dans un processus à part avec un
délai, rien n'est envoyé à personne. Le texte rendu devient le contenu ``{"texte": ...}`` d'un élément Candidat, avec son
origine (le nom du fichier, la licence dite par la personne ou « inconnue », la date). Déposer le même fichier une seconde
fois ajoute une version Candidat si le texte a changé (comparatif rendu), comme tout réimport.

Un document illisible est refusé avec sa raison. Un texte plus long que le plafond d'un élément est refusé en le disant :
on le coupe en plusieurs éléments plutôt que de le tronquer en silence.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from api.services.builder.bibliotheque import importation, rangement, schemas, service
from api.services.builder.bibliotheque.modele import Origine
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import CONTENU_MAX_OCTETS, DEPOT_MAX_OCTETS
from api.services.builder.dossiers import extraction


def slug_du_fichier(nom: str) -> str:
    base = os.path.splitext(os.path.basename(nom or ""))[0]
    ascii_ = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:64] or "document"


def texte_des_pages(resultat: extraction.Extraction) -> str:
    return "\n\n".join(p.texte.strip() for p in resultat.pages if p.texte.strip())


async def deposer(
    famille: str,
    nom_du_fichier: str,
    donnees: bytes,
    auteur: str,
    *,
    slug: str | None = None,
    titre: str | None = None,
    licence: str = "inconnue",
    dossier: str = "",
    etiquettes: list[str] | None = None,
) -> dict[str, Any]:
    """Convertit le fichier et le range en Candidat. Rend ``{element, comparatif, cree, tronque}``."""
    await service._verifier_famille(famille)
    if famille in schemas.SCHEMAS:
        raise ErreurBibliotheque(f"« {famille} » holds structured content: a document cannot be dropped in it.")
    if len(donnees) > DEPOT_MAX_OCTETS:
        raise ErreurBibliotheque(f"The file is too large (at most {DEPOT_MAX_OCTETS // (1024 * 1024)} MB).", 413)
    resultat = await extraction.extraire_hors_boucle(nom_du_fichier, donnees)
    if resultat.illisible:
        raise ErreurBibliotheque(f"The document is not read: {resultat.illisible}")
    texte = texte_des_pages(resultat)
    if not texte:
        raise ErreurBibliotheque("The document holds no text.")
    contenu = {"texte": texte}
    taille = len(json.dumps(contenu, ensure_ascii=False).encode("utf-8"))
    if taille > CONTENU_MAX_OCTETS:
        raise ErreurBibliotheque(
            f"The text is {taille} bytes and an element holds at most {CONTENU_MAX_OCTETS}: split the document in several files."
        )
    origine = Origine(
        source=os.path.basename(nom_du_fichier)[:500] or "document",
        licence=licence.strip()[:100] or "inconnue",
        date=datetime.now(UTC).strftime("%Y-%m-%d"),
    )
    nom_propre = os.path.splitext(os.path.basename(nom_du_fichier))[0].strip() or "Document"
    rendu = await importation.importer(famille, slug or slug_du_fichier(nom_du_fichier), (titre or nom_propre)[:200], contenu, origine, auteur)
    element = rendu["element"]
    if dossier or etiquettes:
        element = await rangement.ranger(
            element.famille, element.slug, dossier=dossier or None, etiquettes_posees=etiquettes if etiquettes else None
        )
    return {"element": element, "comparatif": rendu["comparatif"], "cree": rendu["cree"], "tronque": resultat.tronque}
