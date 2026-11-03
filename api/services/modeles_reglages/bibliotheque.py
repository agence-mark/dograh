"""[.mark] builder partie 2, D1 (U4, E45) : les modèles de réglages vivent dans la BIBLIOTHÈQUE.

Famille ``modeles-reglages`` (mode « appliqué »). Un modèle = un élément versionné de la bibliothèque du Labo :

* ``slug``  = l'identifiant du modèle (``kebab`` tiré du nom, suffixé ``-2``, ``-3``... si pris) ;
* ``titre`` = son nom (renommer ne change ni la version ni le statut) ;
* contenu   = ``{"valeurs": {...}, "sections": [...], "origine": {...}?, "commit": str?}`` : le MÊME ``valeurs`` que lisent le
  builder (``appliquer_un_element``) et l'application à l'écran ; aucune clé d'accès, jamais (M3).

Ce qui reste par organisation : la MENTION du dernier modèle appliqué à chaque agent (``MODELES_REGLAGES.applications``), car
elle dit quelque chose d'un agent, pas du modèle.

Reprise des modèles déjà en base (``reprendre_les_existants``) : donnée DÉPLACÉE, aucune migration. Idempotente, jamais contre une
personne : un élément qui existe déjà et dont la version courante n'a pas été écrite par une reprise n'est pas touché ; un
modèle déjà repris (même empreinte) n'est pas recopié ; les lignes d'origine ne sont JAMAIS supprimées (rien ne se supprime sans go).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from api.schemas.modeles_reglages import ModeleDeReglages, OrigineDuModele, StockModeles
from api.services.builder.bibliotheque import service as bibliotheque
from api.services.builder.bibliotheque.modele import Element, Statut
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import CONTENU_MAX_OCTETS
from api.services.modeles_reglages import classement as cl

FAMILLE = "modeles-reglages"
PREFIXE_REPRISE = "reprise:"


def slug_depuis(nom: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:60] or "modele"


def contenu_du_modele(
    valeurs: dict[str, Any], sections: list[str], origine: OrigineDuModele | None, commit: str | None
) -> dict[str, Any]:
    contenu: dict[str, Any] = {"valeurs": valeurs, "sections": sections}
    if origine is not None:
        contenu["origine"] = origine.model_dump(mode="json")
    if commit:
        contenu["commit"] = commit
    return contenu


def _verifier_la_taille(contenu: dict[str, Any]) -> None:
    taille = len(json.dumps(contenu, ensure_ascii=False).encode("utf-8"))
    if taille > CONTENU_MAX_OCTETS:
        raise ErreurBibliotheque(
            f"The template is too large for the library ({taille} bytes, at most {CONTENU_MAX_OCTETS}).", 422
        )


def vers_le_modele(element: Element) -> ModeleDeReglages:
    """La vue qu'ont les écrans et l'application : la version COURANTE de l'élément."""
    courante = element.courante
    contenu = courante.contenu
    valeurs = dict(contenu.get("valeurs") or {})
    origine = contenu.get("origine")
    return ModeleDeReglages(
        id=element.slug,
        nom=element.titre,
        cree_le=min(v.date for v in element.versions),
        origine=OrigineDuModele.model_validate(origine) if isinstance(origine, dict) else None,
        commit=contenu.get("commit") or None,
        sections=list(contenu.get("sections") or cl.sections_presentes(valeurs)),
        valeurs=valeurs,
        statut=element.statut.value,
        version=element.version_courante,
    )


def statut_de(element: Element) -> Statut:
    return element.statut


async def lister_les_elements() -> list[Element]:
    return await bibliotheque.elements_de(FAMILLE)


async def lire_le_modele(modele_id: str) -> Element | None:
    return await bibliotheque.element_ou_none(FAMILLE, modele_id)


def nom_pris(elements: list[Element], nom: str, sauf: str | None = None) -> bool:
    vise = nom.strip().casefold()
    return any(e.titre.strip().casefold() == vise and e.slug != sauf for e in elements)


def slug_libre(elements: list[Element], nom: str) -> str:
    pris = {e.slug for e in elements}
    base = slug_depuis(nom)
    slug, rang = base, 2
    while slug in pris:
        slug, rang = f"{base[:56]}-{rang}", rang + 1
    return slug


async def creer(
    nom: str,
    valeurs: dict[str, Any],
    origine: OrigineDuModele | None,
    commit: str | None,
    auteur: str,
    notes: str = "",
) -> Element:
    elements = await lister_les_elements()
    contenu = contenu_du_modele(valeurs, cl.sections_presentes(valeurs), origine, commit)
    _verifier_la_taille(contenu)
    return await bibliotheque.creer(FAMILLE, slug_libre(elements, nom), nom, contenu, auteur, notes=notes)


# --------------------------------------------------------------------------- #
# Reprise des modèles déjà en base
# --------------------------------------------------------------------------- #


@dataclass
class RapportDeReprise:
    repris: list[str] = field(default_factory=list)
    deja_repris: list[str] = field(default_factory=list)
    gardes: list[str] = field(default_factory=list)  # un élément écrit par une personne porte déjà ce nom : non touché
    trop_gros: list[str] = field(default_factory=list)
    illisibles: list[int] = field(default_factory=list)  # organisations dont la ligne n'a pas pu être lue
    non_configure: bool = False

    def en_json(self) -> dict[str, Any]:
        return {
            "repris": self.repris,
            "deja_repris": self.deja_repris,
            "gardes": self.gardes,
            "trop_gros": self.trop_gros,
            "illisibles": self.illisibles,
            "non_configure": self.non_configure,
        }


def empreinte(modele: ModeleDeReglages) -> str:
    brut = json.dumps({"nom": modele.nom, "valeurs": modele.valeurs}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]


def auteur_de_reprise(organization_id: int, modele: ModeleDeReglages) -> str:
    return f"{PREFIXE_REPRISE}{organization_id}:{empreinte(modele)}"


async def reprendre_un_modele(organization_id: int, modele: ModeleDeReglages, rapport: RapportDeReprise) -> None:
    nom = f"{organization_id}:{modele.nom}"
    auteur = auteur_de_reprise(organization_id, modele)
    elements = await lister_les_elements()
    if any(v.auteur == auteur for e in elements for v in e.versions):
        rapport.deja_repris.append(nom)
        return
    valeurs = {c: cl.valeur_pour_le_modele(c, v) for c, v in modele.valeurs.items()}
    contenu = contenu_du_modele(valeurs, cl.sections_presentes(valeurs), modele.origine, modele.commit)
    try:
        _verifier_la_taille(contenu)
    except ErreurBibliotheque:
        rapport.trop_gros.append(nom)
        return
    # Le nom est celui du modèle ; pris par un autre élément (d'une autre organisation ou d'une personne), il est suffixé
    # par l'organisation d'origine : deux modèles de même nom ne s'écrasent jamais.
    titre = modele.nom if not nom_pris(elements, modele.nom) else f"{modele.nom} (org. {organization_id})"
    if nom_pris(elements, titre):
        rapport.gardes.append(nom)
        return
    await bibliotheque.creer(
        FAMILLE,
        slug_libre(elements, titre),
        titre,
        contenu,
        auteur,
        notes=f"Repris des modèles de l'organisation {organization_id}.",
    )
    rapport.repris.append(nom)


async def reprendre_les_existants() -> RapportDeReprise:
    """Recopie en éléments de la bibliothèque les modèles stockés par organisation. Aucune suppression."""
    from pydantic import ValidationError

    from api.db import db_client
    from api.enums import OrganizationConfigurationKey
    from api.services.builder.constantes import organisation_bibliotheque

    rapport = RapportDeReprise()
    if organisation_bibliotheque() is None:
        rapport.non_configure = True
        return rapport
    lignes = await db_client.get_all_configurations_by_key(OrganizationConfigurationKey.MODELES_REGLAGES.value)
    for ligne in sorted(lignes, key=lambda l: l["organization_id"]):
        try:
            stock = StockModeles.model_validate(ligne["value"])
        except (ValidationError, ValueError):
            rapport.illisibles.append(ligne["organization_id"])
            continue
        for modele in sorted(stock.modeles, key=lambda m: (m.cree_le or datetime.min, m.id)):
            await reprendre_un_modele(ligne["organization_id"], modele, rapport)
    return rapport
