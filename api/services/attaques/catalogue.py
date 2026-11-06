"""[.mark] U11 (§ 17) : « Attaquer l'agent », le catalogue (famille ``jeux-d-attaques`` de la bibliothèque).

Catalogue FERMÉ : les 15 techniques du constructeur de Cognigy (code libre, licence MIT). Un jeu de la bibliothèque ne peut
qu'en choisir parmi elles et leur donner des messages ; une technique hors de cette liste est écartée avec sa raison (jamais
exécutée). Le fichier versé sert de secours si la bibliothèque n'est pas lisible. Aucun mot du métier ici.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

FAMILLE = "jeux-d-attaques"
JEU = "cognigy-15-techniques"
REGLES = "regles-de-sondage"
DOSSIER = Path(__file__).resolve().parents[1] / "builder" / "versement" / "contenu" / FAMILLE
MENTION_MIT = "Techniques reprises du skill agent-red-team de Cognigy, code libre sous licence MIT (Copyright Cognigy GmbH)."

TECHNIQUES: tuple[str, ...] = (
    "demande_directe",
    "cadrage_preference",
    "fausse_autorite",
    "hypothese",
    "format_detourne",
    "escalade_progressive",
    "fausse_premisse",
    "traduction",
    "codage",
    "extraction_du_prompt",
    "outil_force",
    "injection_donnee",
    "injection_connaissance",
    "verification_du_fonde",
    "flatterie",
)
GRAVITES = ("critique", "haute", "moyenne", "basse")
TOURS_PAR_SONDE_MAX = 6
LONGUEUR_MESSAGE_MAX = 600
REPONSE_MAX_RANGEE = 1200  # la réponse de l'agent est rangée mot pour mot, bornée


class JeuIllisible(Exception):
    pass


def _du_fichier(nom: str) -> dict[str, Any]:
    try:
        return dict(json.loads((DOSSIER / f"{nom}.json").read_text(encoding="utf-8"))["contenu"])
    except Exception as erreur:  # noqa: BLE001
        raise JeuIllisible(f"The attack set {nom!r} cannot be read ({type(erreur).__name__}).") from None


async def _de_la_bibliotheque(slug: str) -> dict[str, Any] | None:
    try:
        from api.services.builder.bibliotheque import service

        element = await service.element_ou_none(FAMILLE, slug)
        return dict(element.courante.contenu) if element else None
    except Exception as erreur:  # noqa: BLE001 -- bibliothèque illisible : le fichier versé
        logger.warning(f"[attaques] bibliothèque non lue ({type(erreur).__name__})")
        return None


def valider(contenu: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """(techniques retenues, écartées avec leur raison). Forme fermée : id du catalogue, messages courts, gravité connue."""
    retenues: list[dict[str, Any]] = []
    ecartees: list[dict[str, str]] = []
    vues: set[str] = set()
    for brute in contenu.get("techniques") or []:
        identifiant = str((brute or {}).get("id") or "") if isinstance(brute, dict) else ""
        if identifiant not in TECHNIQUES:
            ecartees.append({"id": identifiant[:60], "raison": "not one of the 15 techniques of the catalogue"})
            continue
        if identifiant in vues:
            ecartees.append({"id": identifiant, "raison": "twice in the set"})
            continue
        sondes = []
        for s in brute.get("sondes") or []:
            tours = [str(t)[:LONGUEUR_MESSAGE_MAX] for t in (s.get("tours") or []) if str(t).strip()][:TOURS_PAR_SONDE_MAX]
            if not tours or not isinstance(s.get("id"), str):
                continue
            sondes.append({"id": s["id"][:80], "tours": tours, "temoin": str(s.get("temoin") or "")[:LONGUEUR_MESSAGE_MAX]})
        if not sondes:
            ecartees.append({"id": identifiant, "raison": "no usable probe"})
            continue
        vues.add(identifiant)
        gravite = brute.get("gravite_par_defaut")
        retenues.append(
            {
                "id": identifiant,
                "nom": str(brute.get("nom") or identifiant)[:120],
                "but": str(brute.get("but") or "")[:400],
                "gravite_par_defaut": gravite if gravite in GRAVITES else "moyenne",
                "sondes": sondes,
            }
        )
    return retenues, ecartees


async def lire_le_jeu(slug: str = JEU) -> dict[str, Any]:
    """Le jeu (bibliothèque, sinon fichier versé) : ``techniques`` retenues, ``ecartees``, ``mention``."""
    contenu = await _de_la_bibliotheque(slug) or _du_fichier(slug)
    retenues, ecartees = valider(contenu)
    return {"slug": slug, "techniques": retenues, "ecartees": ecartees, "mention": contenu.get("licence") or MENTION_MIT}


async def lire_les_regles() -> list[dict[str, str]]:
    contenu = await _de_la_bibliotheque(REGLES) or _du_fichier(REGLES)
    return [{"id": str(r.get("id")), "texte": str(r.get("texte"))} for r in contenu.get("regles") or [] if isinstance(r, dict)]
