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
