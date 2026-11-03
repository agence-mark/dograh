"""[.mark] Le module de versement de la bibliothèque (builder partie 2, § 6 bis) : le contenu à verser vit DANS LE DÉPÔT.

Pourquoi : la nuit, aucune écriture dans une base distante (MCP ``dograh`` compris). Tout ce que le chantier écrit pour la
bibliothèque (méthode du builder, consigne de synthèse, fiches de famille, recettes, personnages, scénarios, grille du
juge) est un fichier ``contenu/<famille>/<slug>.json``, versionné, relu en revue, testé sur la base locale, et versé au
démarrage du serveur (``scripts/start_services_docker.sh``, après les migrations) par ``python -m api.scripts.mark.verser``.

Forme d'un fichier : ``{"titre": str, "contenu": {...}, "notes": str?, "origine": {"source", "licence", "date"}?,
"dossier": str?, "etiquettes": [str]?}``. Le sous-dossier et les étiquettes (U7) rangent l'élément À SA CRÉATION, ou plus tard
tant qu'il n'a ni l'un ni l'autre : une personne qui l'a déplacé ou étiqueté n'est jamais défaite.

Idempotent, et jamais contre une personne :

* élément absent : créé (Candidat), auteur ``versement:<empreinte>`` ;
* déjà versé avec cette empreinte (une version, n'importe laquelle, porte cet auteur) : rien ;
* la version courante vient d'un versement précédent : le nouveau contenu entre comme version suivante (Candidat) ;
* la version courante a été écrite par une personne ou par le builder : **rien n'est écrasé**, le rapport le dit
  (``garde``) ; la personne décide à l'écran.

Rien n'est jamais passé en Recette ni supprimé par le versement. Sans organisation de bibliothèque réglée : rien, et dit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from api.services.builder.bibliotheque import fiches, rangement, service
from api.services.builder.bibliotheque.familles import FAMILLES
from api.services.builder.bibliotheque.modele import Origine
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import organisation_bibliotheque

CONTENU = Path(__file__).resolve().parent / "contenu"
PREFIXE_AUTEUR = "versement:"


@dataclass
class Rapport:
    crees: list[str] = field(default_factory=list)
    mis_a_jour: list[str] = field(default_factory=list)
    inchanges: list[str] = field(default_factory=list)
    gardes: list[str] = field(default_factory=list)  # modifiés par une personne : non écrasés
    erreurs: list[str] = field(default_factory=list)
    fiches: list[str] = field(default_factory=list)  # familles dont la fiche de départ vient d'être écrite
    non_configure: bool = False

    def en_json(self) -> dict[str, Any]:
        return {
            "crees": self.crees,
            "mis_a_jour": self.mis_a_jour,
            "inchanges": self.inchanges,
            "gardes": self.gardes,
            "erreurs": self.erreurs,
            "fiches": self.fiches,
            "non_configure": self.non_configure,
        }


@dataclass
class Fichier:
    famille: str
    slug: str
    titre: str
    contenu: dict[str, Any]
    notes: str
    origine: Origine | None
    dossier: str = ""
    etiquettes: tuple[str, ...] = ()

    @property
    def empreinte(self) -> str:
        brut = json.dumps({"titre": self.titre, "contenu": self.contenu}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]

    @property
    def auteur(self) -> str:
        return f"{PREFIXE_AUTEUR}{self.empreinte}"


def lire_les_fichiers(dossier: Path = CONTENU) -> list[Fichier]:
    """Tous les fichiers du dossier, triés. Une famille inconnue ou un fichier mal formé lève ``ValueError`` (le test le voit)."""
    fichiers = []
    for chemin in sorted(dossier.glob("*/*.json")):
        famille, slug = chemin.parent.name, chemin.stem
        if famille not in FAMILLES:
            raise ValueError(f"{chemin.name} : famille inconnue {famille}")
        brut = json.loads(chemin.read_text(encoding="utf-8"))
        if not isinstance(brut.get("contenu"), dict) or not str(brut.get("titre") or "").strip():
            raise ValueError(f"{famille}/{slug} : « titre » et « contenu » (objet) sont obligatoires")
        origine = Origine.model_validate(brut["origine"]) if brut.get("origine") else None
        fichiers.append(
            Fichier(
                famille,
                slug,
                brut["titre"].strip(),
                brut["contenu"],
                str(brut.get("notes") or ""),
                origine,
                str(brut.get("dossier") or ""),
                tuple(str(e) for e in brut.get("etiquettes") or ()),
            )
        )
    return fichiers


async def verser_un(fichier: Fichier, rapport: Rapport) -> None:
    nom = f"{fichier.famille}/{fichier.slug}"
    element = await service.element_ou_none(fichier.famille, fichier.slug)
    if element is None:
        await service.creer(
            fichier.famille, fichier.slug, fichier.titre, fichier.contenu, fichier.auteur, notes=fichier.notes, origine=fichier.origine
        )
        await _ranger(fichier, "", [])
        rapport.crees.append(nom)
        return
    if any(v.auteur == fichier.auteur for v in element.versions):
        await _ranger(fichier, element.dossier, element.etiquettes)
        rapport.inchanges.append(nom)
        return
    if not element.courante.auteur.startswith(PREFIXE_AUTEUR):
        rapport.gardes.append(nom)
        return
    await service.ajouter_version(
        fichier.famille,
        fichier.slug,
        fichier.contenu,
        fichier.auteur,
        notes=fichier.notes,
        origine=fichier.origine,
        titre=fichier.titre,
    )
    await _ranger(fichier, element.dossier, element.etiquettes)
    rapport.mis_a_jour.append(nom)


async def _ranger(fichier: Fichier, dossier_actuel: str, etiquettes_actuelles: list[str]) -> None:
    """Le sous-dossier et les étiquettes du fichier, seulement si l'élément n'est pas encore rangé (jamais contre une personne)."""
    if (fichier.dossier or fichier.etiquettes) and not dossier_actuel and not etiquettes_actuelles:
        await rangement.ranger(
            fichier.famille, fichier.slug, dossier=fichier.dossier or None, etiquettes_posees=list(fichier.etiquettes) or None
        )


async def verser(dossier: Path = CONTENU) -> Rapport:
    rapport = Rapport()
    # Lancé au démarrage dans un processus neuf, le cache du Labo est vide : le lire en base d'abord (C8).
    from api.services.equipe_mark.espaces import rafraichir_labo

    await rafraichir_labo(force=True)
    if organisation_bibliotheque() is None:
        rapport.non_configure = True
        logger.warning("[.mark] versement : organisation de la bibliothèque non réglée, rien n'est versé")
        return rapport
    for fichier in lire_les_fichiers(dossier):
        try:
            await verser_un(fichier, rapport)
        except ErreurBibliotheque as erreur:
            rapport.erreurs.append(f"{fichier.famille}/{fichier.slug} : {erreur}")
    # Les fiches de famille (E49) : écrites au départ, jamais remplacées une fois qu'une personne les a corrigées.
    rapport.fiches = await fiches.verser_celles_de_depart()
    logger.info(f"[.mark] versement de la bibliothèque : {rapport.en_json()}")
    return rapport
