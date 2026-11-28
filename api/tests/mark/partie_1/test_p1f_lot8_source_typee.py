"""[.mark] Lot 8, 8c-1 (84) : la ``Source`` dit tout ce que le métier et le moteur lui demandent. Chaque nom lu par ``getattr(source, "…")`` dans
``services/commande`` et ``services/restauration/carte_et_allergenes`` est un membre du ``Protocol`` ; la source du restaurant, et celle qui retient
au passage, en sont une (``isinstance``). ``commande/porte.py`` est hors de ce test (ses deux lectures passent en 8c-2)."""

from __future__ import annotations

import ast
import typing
from pathlib import Path

from api.services.commande.etat_pour_le_modele import SourceQuiRetient
from api.services.commande.source import Source
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.source_commande import SourceClasseur

RACINE_API = Path(__file__).resolve().parents[3]
DOSSIERS = ("services/commande", "services/restauration/carte_et_allergenes")
HORS_DU_TEST = {"services/commande/porte.py"}


def _nom_de_la_source(noeud: ast.expr) -> bool:
    return (isinstance(noeud, ast.Name) and noeud.id == "source") or (isinstance(noeud, ast.Attribute) and noeud.attr == "_source")


def _noms_lus_par_getattr() -> dict[str, list[str]]:
    lus: dict[str, list[str]] = {}
    for dossier in DOSSIERS:
        for fichier in sorted((RACINE_API / dossier).rglob("*.py")):
            chemin = fichier.relative_to(RACINE_API).as_posix()
            if chemin in HORS_DU_TEST:
                continue
            for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
                if (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) and noeud.func.id == "getattr" and len(noeud.args) >= 2
                        and _nom_de_la_source(noeud.args[0]) and isinstance(noeud.args[1], ast.Constant) and isinstance(noeud.args[1].value, str)):
                    lus.setdefault(noeud.args[1].value, []).append(f"{chemin}:{noeud.lineno}")
    return lus


def test_chaque_nom_lu_par_getattr_est_un_membre_de_la_source():
    membres = set(typing.get_protocol_members(Source))
    manquants = {nom: ou for nom, ou in _noms_lus_par_getattr().items() if nom not in membres}
    assert manquants == {}


def test_la_source_du_restaurant_est_une_source():
    source = SourceClasseur(None, Lieu("base", 1, 1), nom_prise="test")
    assert isinstance(source, Source)
    assert isinstance(SourceQuiRetient(source), Source)
