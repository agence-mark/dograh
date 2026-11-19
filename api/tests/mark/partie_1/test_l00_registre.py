"""[.mark] Chantier Partie 1, lot 0 : le script du registre des lots, éprouvé sur trois cas rouges connus (L00-06, R7).

Le script vit dans le labo (`Labo-agent-vocal/plans/agent-qui-travaille-partie-1/outils/verifier_registre_des_lots.py`) ; hors du poste
qui porte le labo à côté du fork (la CI), ces tests sont sautés.
"""

import subprocess
import sys
from pathlib import Path

import pytest

FORK = Path(__file__).resolve().parents[4]
SCRIPT = FORK.parent.parent / "Labo-agent-vocal" / "plans" / "agent-qui-travaille-partie-1" / "outils" / "verifier_registre_des_lots.py"
pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="le labo n'est pas à côté du fork (CI)")

ENTETE_FICHE = "# lot\n\n## Les éléments du registre\n\n| Id | Élément | Test | Badge | Ce qu'on verrait |\n|---|---|---|---|---|\n"
ENTETE_REG = (
    "## 2. Les rouges attendus\n\n| Id | Rouge | Raison |\n|---|---|---|\n\n"
    "## 5. Les éléments\n\n| Id | Lot | Élément | Preuve | Badge | Ce qu'on verrait |\n|---|---|---|---|---|---|\n"
)


def fabriquer(tmp_path, preuve, badge):
    (tmp_path / "lot-00-x.md").write_text(ENTETE_FICHE + f"| L00-01 | essai | `{preuve}` | {badge} |  |\n", encoding="utf-8")
    (tmp_path / "registre.md").write_text(ENTETE_REG + f"| L00-01 | 0 | essai | `{preuve}` | {badge} |  |\n", encoding="utf-8")


def lancer(tmp_path, lots):
    r = subprocess.run([sys.executable, str(SCRIPT), "--registre", str(tmp_path / "registre.md"), "--fiches", str(tmp_path), "--lots", lots],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def test_script_rouge_sur_lot_vide(tmp_path):
    fabriquer(tmp_path, "cmd:git --version", "sans écran")
    code, sortie = lancer(tmp_path, "1")
    assert code == 1 and "lot 1 : aucun élément" in sortie, sortie


def test_script_rouge_sans_badge(tmp_path):
    fabriquer(tmp_path, "cmd:git --version", "")
    code, sortie = lancer(tmp_path, "0")
    assert code == 1 and "badge" in sortie, sortie


def test_script_rouge_test_absent(tmp_path):
    fabriquer(tmp_path, "pytest:api/tests/mark/partie_1/test_n_existe_pas.py::test_x", "sans écran")
    code, sortie = lancer(tmp_path, "0")
    assert code == 1 and "absent du rapport" in sortie, sortie


def test_script_vert_sur_un_element_juste(tmp_path):
    fabriquer(tmp_path, "cmd:git --version", "sans écran")
    code, sortie = lancer(tmp_path, "0")
    assert code == 0, sortie
