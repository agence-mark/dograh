"""[.mark] Les textes du point de contact du gabarit restauration, une version par modèle (D38, lot 0 élément L00-15).

Prompt de chaque étape, descriptions des cases, lignes de l'état, retours lus par le modèle : tout ce qui dépend du modèle vit ici,
un dossier par version (``gemma-4`` = la version prouvée par le banc B12, le témoin). Le code du métier n'en dépend jamais.
Un modèle sans version propre reprend celle du témoin. Le nom d'un dossier est un nom de modèle par construction : la garde
« aucun nom de modèle dans le code » ignore ce dossier (D61, point 8). Les textes eux-mêmes sont versés au lot 2.
"""

from __future__ import annotations

from pathlib import Path

DOSSIER = Path(__file__).parent
TEMOIN = "gemma-4"


def versions() -> list[str]:
    """Les versions présentes : un sous-dossier par modèle."""
    return sorted(p.name for p in DOSSIER.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))


def version_pour(modele: str) -> str:
    """La version des textes d'un modèle : la plus longue version dont le nom commence l'identifiant du modèle, sinon le témoin."""
    m = (modele or "").strip().lower()
    candidats = [v for v in versions() if m.startswith(v)]
    return max(candidats, key=len) if candidats else TEMOIN


def dossier_des_textes(modele: str) -> Path:
    return DOSSIER / version_pour(modele)


# --------------------------------------------------------------------------- les textes versés (lot 2, étape 9)

import json  # noqa: E402
from functools import lru_cache  # noqa: E402

CARTE_TEMOIN = "300"  # Casa Italia, la carte du témoin
ETAPES_DE_REQUETE = {"accueil": ("accueil", "accueil"), "commande": ("commande", "vide"), "reservation": ("reservation", "vide"), "service": ("service", "service")}


@lru_cache(maxsize=8)
def outils_verses(version: str = TEMOIN) -> dict:
    """``outils.json`` de la version : les rendus de la version finale par carte et par état, les variantes, les empreintes des sources."""
    return json.loads((DOSSIER / version / "outils.json").read_text(encoding="utf-8"))


def prompt(etape: str, carte: str = CARTE_TEMOIN, version: str = TEMOIN) -> str:
    """Le prompt système de l'étape tel que versé, l'état remplacé par le trou ``{{etat}}``."""
    return (DOSSIER / version / "prompts" / f"{etape}-{carte}.txt").read_text(encoding="utf-8")


def rendu(etape: str, etat: str, carte: str = CARTE_TEMOIN, version: str = TEMOIN) -> list[dict]:
    """Les outils envoyés au modèle par la version finale dans cet état (format OpenAI)."""
    for e in outils_verses(version)["cartes"][carte]:
        if e["etape"] == etape and e["etat"] == etat:
            return e["outils"]
    raise KeyError(f"aucun rendu {etape}/{etat} sur la carte {carte}")


def variantes(version: str = TEMOIN) -> dict[str, str]:
    """Les textes des cases qui changent avec l'état (proposition en attente, question d'étape, ligne de formule…)."""
    return dict(outils_verses(version)["variantes"])


def requetes_types(version: str = TEMOIN):
    """(étape, prompt système, outils en JSON) des requêtes types de la carte du témoin, pour le budget de caractères (L00-08)."""
    for etape, (fichier, etat) in ETAPES_DE_REQUETE.items():
        yield etape, prompt(fichier, version=version), json.dumps(rendu(etape, etat, version=version), ensure_ascii=False)


OUTIL_DE_PASSAGE = "passer_a"
OUTIL_RETIRE_DE_L_ACCUEIL = "voir_produit"  # B12, décision 3 : l'accueil ne lit plus la carte


def passage_en_tete(outils: list[dict]) -> list[dict]:
    """B13, point 2 (D62, prouvé 16/16) : l'outil de passage en tête de la liste des outils de l'accueil ; l'ordre des autres est gardé, aucun mot changé."""
    return sorted(outils, key=lambda o: 0 if o["function"]["name"] == OUTIL_DE_PASSAGE else 1)


def outils_de_l_accueil(carte: str = CARTE_TEMOIN, version: str = TEMOIN) -> list[dict]:
    """Les outils de l'accueil de la version finale : sans lecture de la carte (B12, décision 3), le passage en tête (B13)."""
    return passage_en_tete([o for o in rendu("accueil", "accueil", carte, version) if o["function"]["name"] != OUTIL_RETIRE_DE_L_ACCUEIL])
