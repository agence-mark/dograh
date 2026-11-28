"""[.mark] Lot 8, 8c-2 (125) : ``derniere_parole_de_la_personne`` (``workflow/passage_sur_la_fiche.py``) est un nom public, lu par ``pipecat/avant_la_requete.py``,
``securite/ecoute.py``, ``securite/urgence.py`` et ``workflow/decideur_de_fin_de_tour.py`` ; plus aucun module ne lit l'ancien nom privé. Et ``avant_la_requete.py``
n'avale plus d'erreur en silence : la pose du hook ``preparer_la_forme`` qui échoue écrit au journal."""

from __future__ import annotations

import ast
from pathlib import Path

from api.outils import inventaire_rustines as INV

RACINE_API = Path(__file__).resolve().parents[3]


def test_aucun_module_ne_lit_le_nom_prive_de_la_derniere_parole():
    lecteurs = []
    for fichier in sorted((RACINE_API / "services").rglob("*.py")):
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Attribute) and noeud.attr == "_derniere_parole_de_la_personne" and fichier.name != "passage_sur_la_fiche.py":
                lecteurs.append(f"{fichier.relative_to(RACINE_API).as_posix()}:{noeud.lineno}")
    assert lecteurs == []


def test_le_nom_public_existe():
    from api.services.workflow import passage_sur_la_fiche as passage

    assert callable(passage.derniere_parole_de_la_personne)


def test_avant_la_requete_n_avale_aucune_erreur():
    source = (RACINE_API / "services/pipecat/avant_la_requete.py").read_text(encoding="utf-8")
    assert INV.compter_les_erreurs_avalees(source) == 0
