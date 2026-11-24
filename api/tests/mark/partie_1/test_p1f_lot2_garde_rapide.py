"""[.mark] Lot 2 (décision d'Evan, 24/11) : la garde de fin de lot est rapide ; le contrôle complet se joue une seule fois, en fin de chantier."""

from __future__ import annotations

from api.outils import garde_de_lot as G


def test_le_mode_rapide_ne_joue_ni_les_touches_ni_les_combinaisons_ni_les_fusions():
    assert G.etapes_du_mode(True) == ("ruff", "linter", "inventaire", "noqa", "donnes")
    assert not {"touches", "combinaisons", "fusions"} & set(G.etapes_du_mode(True))
    assert G.etapes_du_mode(False) == G.ETAPES


def test_le_mode_rapide_exige_les_tests_cibles_du_lot(capsys):
    assert G.lancer("2", None, None, None, rapide=True, tests=()) == 2
    assert "--tests" in capsys.readouterr().out
