"""[.mark] Plan final Partie 1, lot 9 : le test « aucun nom d'article » couvre aussi les styles et les phrases des réglages.

Le lot 5 vérifiait le contrat 7, les textes à trous et le gabarit. Les styles de l'agent (``styles.py``, ``styles.json``) et les phrases de ``reglages.json`` sont servis à TOUS les métiers : le nom
d'un produit ou d'une catégorie des cartes du banc n'y figure pas.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from api.services.gabarits import gabarit as G
from api.services.gabarits import styles

CARTES = Path(__file__).resolve().parents[1] / "banc_a" / "cartes"
RACINE = Path(G.__file__).resolve().parent


def _noms_des_cartes() -> set[str]:
    noms: set[str] = set()
    for f in CARTES.glob("*.json"):
        carte = json.loads(f.read_text(encoding="utf-8"))["carte"]
        for cle in ("produits", "categories"):
            noms |= {x["nom"].strip().lower() for x in carte.get(cle, []) if len(x.get("nom", "").strip()) >= 4}
    return noms


def _trouves(textes: dict[str, str]) -> list[tuple[str, str]]:
    noms = _noms_des_cartes()
    return sorted((origine, n) for origine, t in textes.items() for n in noms if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", t.lower()))


def test_les_cartes_du_banc_donnent_des_noms_a_chercher():
    assert len(_noms_des_cartes()) > 50  # sans noms, le test des deux autres ne prouverait rien


def test_aucun_nom_d_article_dans_les_styles():
    textes = {f"styles.py::{n}": t for n, t in styles.textes().items()}
    textes["styles.py"] = (RACINE / "styles.py").read_text(encoding="utf-8")
    textes["styles.json"] = (RACINE / "restauration" / "styles.json").read_text(encoding="utf-8")
    assert not _trouves(textes), _trouves(textes)


def test_aucun_nom_d_article_dans_les_phrases_des_reglages():
    textes = {"reglages.json": (RACINE / "restauration" / "reglages.json").read_text(encoding="utf-8")}
    assert not _trouves(textes), _trouves(textes)
