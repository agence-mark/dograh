"""[.mark] Lot 7b-C6, reprise R7 de l'audit (refus 6 : jamais de nom privé importé d'un autre fichier de test) : les tests de C6 prennent leurs gestes dans les modules publics
d'aides (``aides_de_la_commande``, ``aides_de_la_reservation``…), jamais ``from test_x import _y``. On lit les sources."""

from __future__ import annotations

import re
from pathlib import Path

ICI = Path(__file__).parent
IMPORT_PRIVE = re.compile(r"^\s*from\s+(?:api\.tests\.mark\.partie_1\.|\.)test_\w+\s+import\s+(.+)$", re.MULTILINE)


def _noms_prives(texte: str) -> list[str]:
    return [nom.strip() for noms in IMPORT_PRIVE.findall(texte) for nom in noms.strip("()").split(",") if nom.strip().startswith("_")]


def test_aucun_test_de_c6_n_importe_un_nom_prive_d_un_autre_test():
    fautes = {p.name: noms for p in sorted(ICI.glob("test_p1f_lot7c6_*.py")) if (noms := _noms_prives(p.read_text(encoding="utf-8")))}
    assert not fautes, fautes


def test_la_lecture_des_imports_voit_un_nom_prive():
    assert _noms_prives("from api.tests.mark.partie_1.test_x import _jusqu_a, public") == ["_jusqu_a"]
    assert _noms_prives("from .aides_de_la_commande import jusqu_au_numero") == []
