"""[.mark] Plan final Partie 1, lot 1 (R7) : chaque outil du filet est éprouvé sur un cas rouge fabriqué avant de servir.

Les outils (``outils/inventaire_rustines.py``, ``outils/garde_de_lot.py``) sont joués sur des sources et des comptes écrits ici : un outil qui
ne voit plus ce qu'il doit voir fait échouer ces tests, donc la garde ne ment pas.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from api.outils import garde_de_lot as G
from api.outils import inventaire_rustines as I


# --------------------------------------------------------------------------- les comptes d'un fichier

def test_un_drapeau_de_la_liste_est_compte_sous_toutes_ses_formes():
    source = (
        "def f(p):\n"
        "    p['relecture_acceptee'] = True\n"
        "    if p.fin_dite or allergie_donnee_au_tour:\n"
        "        g(question_gardee=1)\n"
        "APRES_C_EST_TOUT = 'x'\n"
    )
    n = I.compter_les_drapeaux(source)
    assert n == {"relecture_acceptee": 1, "fin_dite": 1, "allergie_donnee*": 1, "question_gardee": 1, "APRES_C_EST_TOUT": 1}, n


def test_un_commentaire_ou_une_phrase_qui_cite_un_drapeau_ne_compte_pas():
    source = '"""relecture_acceptee est un drapeau."""\n# fin_dite\nx = "le drapeau fin_dite dit ceci et cela, en plus long que la limite de soixante caracteres"\n'
    assert I.compter_les_drapeaux(source) == {}


def test_une_erreur_avalee_sans_journal_est_comptee_une_erreur_journalisee_ou_relancee_non():
    avalees = "try:\n    a()\nexcept Exception:\n    pass\ntry:\n    a()\nexcept:\n    x = 1\n"
    saines = ("try:\n    a()\nexcept Exception:\n    logger.warning('x')\ntry:\n    a()\nexcept Exception as e:\n    raise ValueError() from e\n"
              "try:\n    a()\nexcept KeyError:\n    pass\n")
    assert I.compter_les_erreurs_avalees(avalees) == 2
    assert I.compter_les_erreurs_avalees(saines) == 0


def test_un_nom_prive_importe_d_un_autre_paquet_est_compte_pas_celui_du_meme_paquet():
    d = "from api.services.commande.moteur import _r, _avec, public\nfrom api.services.commande.panier import _meme_paquet\n"
    assert I.compter_les_noms_prives(d, "services/commande/porte.py") == 2
    relatif = "from .moteur import _r\nfrom . import _x\n"
    assert I.compter_les_noms_prives(relatif, "services/commande/porte.py") == 1
    assert I.compter_les_noms_prives("from os import _exit\n", "services/commande/porte.py") == 0


def test_la_lecture_de_mots_compte_les_expressions_regulieres_et_les_coupes_de_texte():
    source = "import re\ndef f(t, derniere_parole):\n    re.compile('x')\n    t.startswith('a')\n    t.removeprefix('b')\n    return derniere_parole\n"
    assert I.compter_la_lecture_de_mots(source) == 4


def test_une_fonction_de_plus_de_80_lignes_est_vue_avec_sa_longueur_en_lignes():
    longue = "def grosse():\n" + "    x = 1\n" * 90
    courte = "class A:\n    def petite(self):\n        return 1\n"
    assert I.fonctions_longues(longue) == {"grosse": 91}
    assert I.fonctions_longues(courte) == {}
    assert I.fonctions_du_fichier(courte) == {"A.petite": 2}


def test_les_fonctions_touchees_sont_celles_qui_contiennent_une_ligne_ajoutee():
    source = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
    assert I.fonctions_touchees(source, {6}) == ["b"]
    assert I.fonctions_touchees(source, {3}) == []


# --------------------------------------------------------------------------- le cliquet de l'inventaire

def _inv(**ligne):
    base = {"drapeaux": {}, "erreurs_avalees": 0, "noms_prives": 0, "lecture_de_mots": 0, "fonctions_longues": {}}
    return {"fichiers": {"a.py": {**base, **ligne}}}


def test_le_cliquet_refuse_une_hausse_et_accepte_une_baisse_ou_l_egalite():
    base = _inv(erreurs_avalees=2, drapeaux={"fin_dite": 3}, fonctions_longues={"f": 100})
    assert I.comparer(base, base) == []
    assert I.comparer(_inv(erreurs_avalees=1, drapeaux={"fin_dite": 2}, fonctions_longues={"f": 90}), base) == []
    hausse = I.comparer(_inv(erreurs_avalees=3, drapeaux={"fin_dite": 3}, fonctions_longues={"f": 100}), base)
    assert any("erreurs_avalees 2 -> 3" in e for e in hausse), hausse


def test_le_cliquet_refuse_un_drapeau_neuf_une_fonction_longue_neuve_et_une_fonction_qui_grossit():
    base = _inv(fonctions_longues={"f": 100})
    assert any("drapeau fin_dite" in e for e in I.comparer(_inv(drapeaux={"fin_dite": 1}, fonctions_longues={"f": 100}), base))
    assert any("nouvelle" in e for e in I.comparer(_inv(fonctions_longues={"f": 100, "g": 81}), base))
    assert any("grossit" in e for e in I.comparer(_inv(fonctions_longues={"f": 101}), base))


def test_un_fichier_neuf_est_compte_a_zero_dans_la_base():
    base = {"fichiers": {}}
    courant = {"fichiers": {"neuf.py": _inv(noms_prives=1)["fichiers"]["a.py"]}}
    assert any("noms_prives 0 -> 1" in e for e in I.comparer(courant, base))


# --------------------------------------------------------------------------- le cliquet de ruff

BASE_RUFF = {"fichiers": {"a.py": {"C901": 2}, "b.py": {"C901": 1}}, "existants": ["a.py", "b.py"]}


def test_ruff_refuse_une_hausse_dans_un_fichier_qui_existait():
    ecarts = G.ecarts_ruff({"a.py": {"C901": 3}, "b.py": {"C901": 1}}, BASE_RUFF, {"a.py", "b.py"})
    assert any("a.py 2 -> 3" in e for e in ecarts), ecarts


def test_ruff_accepte_le_code_deplace_et_refuse_un_fichier_neuf_qui_fait_monter_le_total():
    deplace = G.ecarts_ruff({"a.py": {"C901": 1}, "neuf.py": {"C901": 1}}, BASE_RUFF, {"a.py", "neuf.py"})
    assert deplace == []
    monte = G.ecarts_ruff({"a.py": {"C901": 2}, "neuf.py": {"C901": 1}}, BASE_RUFF, {"a.py", "neuf.py"})
    assert any("total sur la zone" in e for e in monte), monte


def test_ruff_refuse_un_nom_non_defini_n_importe_ou():
    assert any("F821" in e for e in G.ecarts_ruff({"z.py": {"F821": 1}}, BASE_RUFF, set()))


def test_la_base_de_ruff_connait_les_regles_de_la_garde():
    base = I.charger(G.BASE_RUFF)
    assert tuple(base["regles"]) == G.REGLES_RUFF
    assert not any("F821" in r for r in base["fichiers"].values())


# --------------------------------------------------------------------------- noqa et import-linter

def test_un_noqa_ajoute_est_vu(monkeypatch):
    diff = "+++ b/api/services/x.py\n+x = 1  # noqa: F401\n+y = 2\n-z = 3  # noqa\n"
    monkeypatch.setattr(G, "_git", lambda *a, **k: diff)
    assert G.noqa_ajoutes("abc") == ["x = 1  # noqa: F401"]


def test_le_contrat_d_import_est_pose_et_ses_exceptions_ne_s_allongent_pas():
    texte = Path(I.RACINE_API / ".importlinter").read_text(encoding="utf-8")
    assert "api.services.restauration" in texte and "api.services.gabarits.restauration" in texte
    assert G._compter_les_ignores() <= I.charger(G.BASE_INVENTAIRE)["ignore_imports_max"]


def test_le_contrat_d_import_echoue_sur_un_import_interdit_fabrique(tmp_path):
    """Cas rouge : un petit paquet où le « moteur » importe le « métier » rend lint-imports rouge."""
    for d in ("paquet", "paquet/moteur", "paquet/metier"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
        (tmp_path / d / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "paquet" / "moteur" / "x.py").write_text("from paquet.metier import y\n", encoding="utf-8")
    (tmp_path / "paquet" / "metier" / "y.py").write_text("", encoding="utf-8")
    (tmp_path / ".importlinter").write_text(
        "[importlinter]\nroot_package = paquet\n\n[importlinter:contract:1]\nname = c\ntype = forbidden\n"
        "source_modules =\n    paquet.moteur\nforbidden_modules =\n    paquet.metier\nallow_indirect_imports = True\n", encoding="utf-8")
    exe = Path(sys.executable).parent / ("lint-imports.exe" if sys.platform == "win32" else "lint-imports")
    r = subprocess.run([str(exe), ".importlinter"], cwd=tmp_path, capture_output=True, text=True,
                       env={"PYTHONPATH": str(tmp_path), "SYSTEMROOT": "C:\\Windows"})
    assert r.returncode != 0 and "BROKEN" in r.stdout, r.stdout[-400:]


def test_la_base_d_inventaire_est_ecrite_et_le_perimetre_aussi():
    assert json.loads((I.RACINE_API / "outils" / "base_inventaire.json").read_text(encoding="utf-8"))["fichiers"]
    assert I.charger(I.RACINE_API / "outils" / "perimetre_partie_1.json")["fichiers"]
