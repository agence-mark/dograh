"""[.mark] Chantier Partie 1, lot 17 : les styles d'un agent (D23, D30), en liste fermée.

Un style est UN paragraphe, qui remplit le trou ``{{style}}`` du gabarit (« Tu vouvoies, {{style}}. »). Il dit comment parler, jamais quoi
proposer ni quand : le code décide de la proposition (ses données, sa question numérotée, une fois par appel), le style décide du ton. Jamais
une prose libre du restaurateur : seuls les styles de cette liste existent, et un style n'y entre qu'avec sa preuve (banc et grille humaine,
``agents/_gabarit/08``), sous le budget de caractères (D29).

Les textes vivent ici (le code les sert à l'installation) et sont versés dans la bibliothèque, famille ``styles-agent`` (``verser``), pour que
l'écran les montre ; la bibliothèque ne les change pas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FAMILLE = "styles-agent"
DOSSIER = Path(__file__).parent / "restauration"
PREUVES = DOSSIER / "styles.json"
PAR_DEFAUT = "chaleureux"


@dataclass(frozen=True)
class Style:
    nom: str
    libelle: str
    texte: str


# Le chaleureux reprend mot pour mot le texte prouvé au banc (finale de B9, § 1 « Qui tu es ») ; sobre et dynamique sont écrits par ce lot.
STYLES: dict[str, Style] = {
    s.nom: s
    for s in (
        Style("chaleureux", "Chaleureux", "avec le ton chaleureux et efficace de la meilleure personne du comptoir"),
        Style("sobre", "Sobre", "avec un ton sobre et posé, en phrases nettes, et une proposition en plus dite une seule fois, sans insister"),
        Style("dynamique", "Dynamique", "avec un ton vif et souriant qui va droit au but, et une proposition en plus dite avec entrain, une seule fois"),
    )
}


class StyleInconnu(ValueError):
    """Un style hors de la liste fermée (D23)."""


def preuves() -> dict[str, dict]:
    """La preuve de chaque style (banc et grille humaine), écrite après le banc du lot 17 ; un style sans preuve verte n'est pas proposé."""
    if not PREUVES.exists():
        return {}
    return json.loads(PREUVES.read_text(encoding="utf-8")).get("styles", {})


def est_prouve(nom: str) -> bool:
    p = preuves().get(nom) or {}
    return bool((p.get("banc") or {}).get("vert")) and bool((p.get("grille_humaine") or {}).get("vert"))


def proposes() -> list[str]:
    """Les styles qu'on peut choisir : ceux de la liste dont la preuve est verte, dans l'ordre de la liste."""
    return [n for n in STYLES if est_prouve(n)]


def valider(nom: str | None) -> str:
    """Le nom du style choisi (le défaut s'il n'est pas dit) ; ``StyleInconnu`` hors de la liste fermée ou sans preuve verte."""
    choisi = nom or PAR_DEFAUT
    if choisi not in STYLES:
        raise StyleInconnu(f"unknown style « {choisi} » (closed list: {', '.join(STYLES)})")
    if not est_prouve(choisi):
        raise StyleInconnu(f"the style « {choisi} » has no green proof yet")
    return choisi


def textes() -> dict[str, str]:
    return {n: s.texte for n, s in STYLES.items()}


async def verser(auteur: str) -> list[str]:
    """Écrit dans la bibliothèque (famille ``styles-agent``) chaque style prouvé qui y manque ; rejouable, rien d'existant n'est réécrit."""
    from api.services.builder.bibliotheque import service as bibliotheque

    verses = []
    for nom in proposes():
        if await bibliotheque.element_ou_none(FAMILLE, nom) is not None:
            continue
        s = STYLES[nom]
        await bibliotheque.creer(
            FAMILLE, nom, s.libelle, {"texte": s.texte, "preuve": preuves().get(nom)}, auteur,
            notes="Style d'agent du gabarit restauration (D23, D30), prouvé au banc et à la grille humaine (lot 17).",
        )
        verses.append(nom)
    return verses
