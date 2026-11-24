"""[.mark] Les textes du point de contact du gabarit restauration, une version par modèle (D38, lot 0 élément L00-15).

Prompt de chaque étape, descriptions des cases, lignes de l'état, retours lus par le modèle : tout ce qui dépend du modèle vit ici,
un dossier par version (``gemma-4`` = la version prouvée par le banc B12, le témoin). Le code du métier n'en dépend jamais.
Un modèle sans version propre reprend celle du témoin. Le nom d'un dossier est un nom de modèle par construction : la garde
« aucun nom de modèle dans le code » ignore ce dossier (D61, point 8). Le contrat des outils (``contrats/<n>.json``, sans carte) est lu ici ; les rendus du banc par carte sont la référence des tests (``banc.py``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

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


# --------------------------------------------------------------------------- le contrat des outils (lot 5, n° 143)


def version_courante() -> int:
    """La version du gabarit restauration en vigueur (le fichier ``version`` du gabarit)."""
    return int((DOSSIER.parent / "version").read_text(encoding="utf-8").strip())


def fichier_du_contrat(dossier_du_modele: Path, n: int) -> Path:
    """Le contrat de la version ``n`` du gabarit : son propre fichier, sinon celui de la plus haute version plus ancienne (une version qui ne change pas les outils garde les précédents)."""
    versions_ = sorted(int(p.stem) for p in (dossier_du_modele / "contrats").glob("*.json") if p.stem.isdigit() and int(p.stem) <= n)
    if not versions_:
        raise FileNotFoundError(f"aucun contrat des outils pour la version {n} du gabarit dans {dossier_du_modele.name}")
    return dossier_du_modele / "contrats" / f"{versions_[-1]}.json"


@lru_cache(maxsize=16)
def contrat(version: str = TEMOIN, gabarit_version: int | None = None) -> dict:
    """Le contrat des outils de la version ``gabarit_version`` du gabarit (``contrats/<n>.json``, celle en vigueur par défaut) : déclaré une fois, sans carte de test
    (descriptions, cases, textes d'état). Un agent installé à la version 6 lit le contrat 6 : une version figée n'est jamais réécrite (I-12)."""
    n = gabarit_version if gabarit_version is not None else version_courante()
    return json.loads(fichier_du_contrat(DOSSIER / version, n).read_text(encoding="utf-8"))


def outils_de(etape: str, version: str = TEMOIN, gabarit_version: int | None = None) -> list[dict]:
    """Les outils de l'étape (format OpenAI) dans son état de référence."""
    return contrat(version, gabarit_version)["etapes"][etape]["outils"]


def outil(etape: str, nom: str, version: str = TEMOIN, gabarit_version: int | None = None) -> dict[str, Any]:
    """La fonction d'un outil de l'étape : son nom, sa description, ses cases."""
    return next(o["function"] for o in outils_de(etape, version, gabarit_version) if o["function"]["name"] == nom)


def cases_de_la_fiche(etape: str, version: str = TEMOIN, gabarit_version: int | None = None) -> dict[str, Any]:
    """Toutes les cases de la fiche de l'étape avec leur texte de base ; les textes qui changent avec l'état sont dans ``variantes``."""
    return outil(etape, "fiche", version, gabarit_version)["parameters"]["properties"]


def variantes(version: str = TEMOIN, gabarit_version: int | None = None) -> dict[str, str]:
    """Les textes des cases qui changent avec l'état (proposition en attente, question d'étape, ligne de formule…)."""
    return dict(contrat(version, gabarit_version)["variantes"])


OUTIL_DE_PASSAGE = "passer_a"
OUTIL_RETIRE_DE_L_ACCUEIL = "voir_produit"  # B12, décision 3 : l'accueil ne lit plus la carte


def passage_en_tete(outils: list[dict]) -> list[dict]:
    """B13, point 2 (D62, prouvé 16/16) : l'outil de passage en tête de la liste des outils de l'accueil ; l'ordre des autres est gardé, aucun mot changé."""
    return sorted(outils, key=lambda o: 0 if o["function"]["name"] == OUTIL_DE_PASSAGE else 1)


def outils_de_l_accueil(version: str = TEMOIN, gabarit_version: int | None = None) -> list[dict]:
    """Les outils de l'accueil de la version finale : sans lecture de la carte (B12, décision 3), le passage en tête (B13)."""
    return passage_en_tete([o for o in outils_de("accueil", version, gabarit_version) if o["function"]["name"] != OUTIL_RETIRE_DE_L_ACCUEIL])


# --------------------------------------------------------------------------- les rendus du banc : pour les tests seulement

_DU_BANC = {"outils_verses": "rendus", "rendu": "rendu", "prompt": "prompt", "requetes_types": "requetes_types", "CARTE_TEMOIN": "CARTE_TEMOIN"}


def __getattr__(nom: str):
    """Les rendus du banc par carte (``banc.py``) gardent leurs anciens noms pour les tests ; aucun module du fonctionnement ne les lit
    (règle ``test_p1f_lot5_contrat``)."""
    if nom in _DU_BANC:
        from api.services.gabarits.restauration.textes import banc

        return getattr(banc, _DU_BANC[nom])
    raise AttributeError(nom)
