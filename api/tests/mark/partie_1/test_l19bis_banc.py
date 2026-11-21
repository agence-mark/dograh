"""[.mark] Chantier Partie 1, lot 19 bis, étape E : le banc A tenu (V6 : ses ``xfail`` sont précis ; V7 : joué exprès, il échoue au lieu de sauter)."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[3]
BANC = API / "tests" / "mark" / "banc_a"


def _xfails() -> list[tuple[str, ast.Call]]:
    appels = []
    for f in sorted(BANC.glob("test_*.py")):
        for noeud in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Call) and getattr(noeud.func, "attr", "") == "xfail":
                appels.append((f"{f.name}:{noeud.lineno}", noeud))
    return appels


def test_l19bis_v6_chaque_xfail_du_banc_a_est_strict_et_dit_pourquoi():
    """V6 : un ``xfail`` du banc A est ``strict`` (il devient rouge le jour où il passe), a une raison écrite, et ne couvre qu'une cause : ``raises`` absent ou
    ``TranscriptionManquante`` (le run n'a pas de fiches écrites : a-trancher), jamais ``Exception`` ni ``AssertionError`` qui avalerait n'importe quel échec."""
    appels = _xfails()
    assert len(appels) >= 5, "le banc A a ses xfail : le test ne lit plus rien"
    fautes = []
    for ou, a in appels:
        mots = {k.arg: k.value for k in a.keywords}
        if not (isinstance(mots.get("strict"), ast.Constant) and mots["strict"].value is True):
            fautes.append(f"{ou} : pas strict")
        if "reason" not in mots:
            fautes.append(f"{ou} : sans raison")
        if "raises" in mots and getattr(mots["raises"], "id", "") != "TranscriptionManquante":
            fautes.append(f"{ou} : raises trop large ({ast.unparse(mots['raises'])})")
    assert fautes == [], fautes


def test_l19bis_v7_le_banc_a_echoue_quand_la_base_manque():
    """V7 : ``-m banc_a`` sans base joignable ÉCHOUE (code de sortie non nul, « prérequis manquant »), il ne saute pas : un vert fait de tests sautés ne prouve rien."""
    env = {**os.environ, "DATABASE_URL": "postgresql+asyncpg://x:y@127.0.0.1:1/test_db", "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/mark/banc_a/test_l00_valeurs_de_pierre.py", "-m", "banc_a", "-q", "-p", "no:cacheprovider", "-x"],
                       cwd=API, env=env, capture_output=True, text=True, timeout=240, encoding="utf-8", errors="replace")
    sortie = r.stdout + r.stderr
    assert r.returncode != 0 and "prérequis manquant" in sortie, sortie[-1500:]
