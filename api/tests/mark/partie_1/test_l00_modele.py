"""[.mark] Chantier Partie 1, lot 0 : changer de modèle = un banc, jamais un chantier (D38 ; L00-14 à L00-16, L00-21).

La garde lit le code par son arbre syntaxique (chaînes seulement : ni commentaires ni docstrings) et refuse un nom du modèle de
conversation écrit hors du seul réglage. Lieux permis (constat du 19/11) : le catalogue des modèles, l'embedding (autre famille), le texte
d'aide, les textes versionnés par modèle (D61, point 8) et les tests.
"""

import ast
from pathlib import Path

from api.services.gabarits import banc_de_changement as B
from api.services.gabarits.restauration import textes as T

API = Path(__file__).resolve().parents[3]
MOTIF = "gemma"
PERMIS = (
    "services/configuration/registry.py",
    "services/configuration/aides_fr.py",
    "services/gen_ai/embedding/factory.py",
    "services/builder/banc_embedding.py",
    "services/gabarits/restauration/textes/",
    "tests/",
)


def _chaines(arbre):
    """Les chaînes du code, sans les docstrings."""
    docs = set()
    for n in ast.walk(arbre):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            premier = n.body[0]
            if isinstance(premier, ast.Expr) and isinstance(getattr(premier, "value", None), ast.Constant):
                docs.add(id(premier.value))
    for n in ast.walk(arbre):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            yield n.lineno, n.value


def noms_de_modele_dans_le_code(racine: Path) -> list[str]:
    out = []
    for f in racine.rglob("*.py"):
        rel = f.relative_to(racine).as_posix()
        if any(rel.startswith(p) for p in PERMIS) or "/.venv/" in f.as_posix():
            continue
        try:
            arbre = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        out += [f"{rel}:{l}" for l, s in _chaines(arbre) if MOTIF in s.lower()]
    return out


def test_un_seul_reglage_du_modele():
    assert noms_de_modele_dans_le_code(API) == []


def test_garde_ignore_les_textes_versionnes(tmp_path):
    (tmp_path / "services" / "gabarits" / "restauration" / "textes" / "gemma-4").mkdir(parents=True)
    (tmp_path / "services" / "gabarits" / "restauration" / "textes" / "gemma-4" / "commande.py").write_text('PROMPT = "gemma-4"\n', encoding="utf-8")
    assert noms_de_modele_dans_le_code(tmp_path) == []
    (tmp_path / "services" / "code.py").write_text('"""gemma en docstring"""\nMODELE = "gemma-4-26b-a4b-it"  # gemma en commentaire\n', encoding="utf-8")
    assert noms_de_modele_dans_le_code(tmp_path) == ["services/code.py:2"]


def test_textes_du_contact_a_part():
    assert T.TEMOIN in T.versions()
    assert T.version_pour("gemma-4-26b-a4b-it") == "gemma-4"
    assert T.version_pour("un-modele-sans-version") == T.TEMOIN
    assert T.dossier_des_textes("gemma-4-26b-a4b-it").is_dir()


def test_banc_de_changement_a_vide():
    r = B.jouer("modele-factice", a_vide=True)
    assert r["requetes"] == 0 and r["temoin"] == "gemma-4" and r["textes_du_candidat"] == "gemma-4"
    assert {e["epreuve"] for e in r["epreuves"]} >= {"banc_a", "bon_outil", "conversations_finale", "latence_fiche"}
    assert all(e["candidat"] == "non joué (à vide)" for e in r["epreuves"])
    assert len(r["liste_a_cocher"]) == 4 and not any(x["coche"] for x in r["liste_a_cocher"])
