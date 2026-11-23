"""[.mark] La garde de fin de lot (plan final Partie 1, § 5) : un seul geste, des contrôles écrits dans ``outils/garde/lot-N.json``.

    python -m api.outils.garde_de_lot 1 --poste sa11                 # tous les contrôles, un à un, reprise sur ce qui est déjà vert à ce commit
    python -m api.outils.garde_de_lot 1 --poste sa11 --etape ruff    # un seul contrôle (chaque commande reste sous 10 minutes)
    python -m api.outils.garde_de_lot --figer                        # coordinateur : les bases baissent, jamais ne montent

Depuis la racine du dépôt. Contrôles : ``ruff`` (cliquet par compte, ``outils/base_ruff.json``), ``linter`` (import-linter, ``api/.importlinter``),
``inventaire`` (``outils/base_inventaire.json``), ``noqa`` (aucun ``noqa`` ajouté), ``touches`` (tests qui importent un module modifié),
``combinaisons`` (profondeur 1), ``fusions`` (lots 2, 3, 6, 7 : fusions de deux gestes).
L'arbre doit être propre : le commit testé est HEAD. ``--creer-les-bases`` (lot 1 seulement) écrit les fichiers de base à l'état présent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from api.outils import inventaire_rustines as I

OUTILS = I.RACINE_API / "outils"
BASE_RUFF, BASE_INVENTAIRE, PERIMETRE = OUTILS / "base_ruff.json", OUTILS / "base_inventaire.json", OUTILS / "perimetre_partie_1.json"
EN_COURS = OUTILS / ".garde-en-cours"
SORTIE = OUTILS / "garde"
REGLES_RUFF = ("F821", "F401", "C901", "PLR0912", "PLR0915", "BLE001", "S110")
INTEGRATION = "origin/chantier/agent-qui-travaille-1-menage"
ETAPES = ("ruff", "linter", "inventaire", "noqa", "touches", "combinaisons", "fusions")
PYTHON = Path(sys.executable)
BASE_A_SOI = (I.RACINE_DEPOT.parents[1] / "Labo-agent-vocal" / "plans" / "agent-qui-travaille-partie-1" / "outils" / "base_de_test_a_soi.py")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=I.RACINE_DEPOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def _exe(nom: str) -> str:
    return str(PYTHON.parent / (nom + ".exe")) if os.name == "nt" else nom


# --------------------------------------------------------------------------- ruff

def comptes_ruff() -> dict[str, dict[str, int]]:
    """``{fichier: {règle: n}}`` sur le code de ``api/`` hors tests."""
    r = subprocess.run([_exe("ruff"), "check", "--isolated", "--select", ",".join(REGLES_RUFF), "--exclude", "tests", "--exclude", "alembic",
                        "--output-format", "json", "."], cwd=I.RACINE_API, capture_output=True, text=True, encoding="utf-8")
    sortie: dict[str, dict[str, int]] = {}
    for f in json.loads(r.stdout or "[]"):
        rel = Path(f["filename"]).resolve().relative_to(I.RACINE_API).as_posix()
        sortie.setdefault(rel, {})
        sortie[rel][f["code"]] = sortie[rel].get(f["code"], 0) + 1
    return sortie


def ecarts_ruff(courant: dict, base: dict, zone: set[str]) -> list[str]:
    """Par règle, en total sur la zone du lot (les fichiers qui ont changé), et par fichier pour ceux qui existaient dans la base.
    ``base`` : ``{"fichiers": {fichier: {règle: n}}, "existants": [tous les fichiers connus]}``. Un fichier neuf compte zéro dans la base."""
    ecarts = []
    bf, existants = base["fichiers"], set(base["existants"])
    for regle in REGLES_RUFF:
        total_c = sum(courant.get(f, {}).get(regle, 0) for f in zone)
        total_b = sum(bf.get(f, {}).get(regle, 0) for f in zone)
        if total_c > total_b:
            ecarts.append(f"{regle} : total sur la zone {total_b} -> {total_c}")
        for f in sorted(zone & existants):
            if courant.get(f, {}).get(regle, 0) > bf.get(f, {}).get(regle, 0):
                ecarts.append(f"{regle} : {f} {bf.get(f, {}).get(regle, 0)} -> {courant.get(f, {}).get(regle, 0)}")
    if any(r.get("F821") for r in courant.values()):
        ecarts.append("F821 : un nom non défini quelque part dans api/ (doit être à zéro)")
    return ecarts


# --------------------------------------------------------------------------- git : la zone du lot

def reference(depuis: str | None) -> str:
    ref = depuis or INTEGRATION
    try:
        return _git("merge-base", ref, "HEAD")
    except subprocess.CalledProcessError:
        return _git("rev-parse", ref)


def fichiers_modifies(base: str) -> list[str]:
    sortie = _git("diff", "--name-only", "--diff-filter=ACMR", f"{base}..HEAD", "--", "api").splitlines()
    return [s[4:] for s in sortie if s.startswith("api/")]


def zone_du_lot(base: str) -> set[str]:
    return {f for f in fichiers_modifies(base) if f.endswith(".py") and not f.startswith(("tests/", "alembic/", "outils/garde"))}


def noqa_ajoutes(base: str) -> list[str]:
    texte = _git("diff", "-U0", f"{base}..HEAD", "--", "api", ":!api/tests", ":!api/outils")
    return [l[1:].strip()[:120] for l in texte.splitlines() if l.startswith("+") and not l.startswith("+++") and re.search(r"#\s*noqa", l)]


# --------------------------------------------------------------------------- tests

def commande_de_test(poste: str | None, *args: str) -> list[str]:
    pytest = [str(PYTHON), "-m", "pytest", *args, "-q", "-p", "no:cacheprovider", "--tb=line"]
    return [str(PYTHON), str(BASE_A_SOI), poste, "--", *pytest] if poste else pytest


def jouer(poste: str | None, *args: str) -> tuple[bool, str]:
    r = subprocess.run(commande_de_test(poste, *args), cwd=I.RACINE_API, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONUTF8": "1"}, timeout=590)
    queue = "\n".join((r.stdout or "").strip().splitlines()[-6:])
    return r.returncode == 0, queue


def tests_touches(base: str) -> list[str]:
    """Les fichiers de ``tests/mark`` qui importent directement un module modifié (grimp, imports paresseux compris), plus les tests modifiés."""
    import grimp

    modifies = [f for f in fichiers_modifies(base) if f.endswith(".py")]
    graphe = grimp.build_graph("api.services", "api.tests", "api.db", "api.routes", "api.tasks", "api.utils", include_external_packages=False)
    cibles: set[str] = set()
    for f in modifies:
        module = I._module_du_fichier(f)
        if module in graphe.modules:
            cibles |= {m for m in graphe.find_modules_that_directly_import(module) if m.startswith("api.tests.mark")}
            if f.startswith("tests/mark"):
                cibles.add(module)
    fichiers = sorted("/".join(m.split(".")[1:]) + ".py" for m in cibles)
    return [f for f in fichiers if (I.RACINE_API / f).exists() and Path(f).name.startswith("test_")]


# --------------------------------------------------------------------------- les contrôles

def _compter_les_ignores() -> int:
    chemin = I.RACINE_API / ".importlinter"
    texte = chemin.read_text(encoding="utf-8") if chemin.exists() else ""
    return len(re.findall(r"^\s+api\.\S+ -> api\.\S+\s*$", texte, re.M))


def controle(nom: str, lot: str, poste: str | None, base: str) -> dict:
    if nom == "ruff":
        zone = zone_du_lot(base)
        ecarts = ecarts_ruff(comptes_ruff(), I.charger(BASE_RUFF), zone)
        return {"vert": not ecarts, "ecarts": ecarts, "fichiers_de_la_zone": len(zone)}
    if nom == "linter":
        r = subprocess.run([_exe("lint-imports"), "api/.importlinter"], cwd=I.RACINE_DEPOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env={**os.environ, "PYTHONPATH": str(I.RACINE_DEPOT)})
        ignores, maxi = _compter_les_ignores(), I.charger(BASE_INVENTAIRE)["ignore_imports_max"]
        return {"vert": r.returncode == 0 and ignores <= maxi, "ignore_imports": ignores, "ignore_imports_max": maxi,
                "sortie": r.stdout.strip().splitlines()[-6:]}
    if nom == "inventaire":
        ok, queue = jouer(poste, "tests/mark/partie_1/test_inventaire_rustines.py")
        return {"vert": ok, "sortie": queue}
    if nom == "noqa":
        ajoutes = noqa_ajoutes(base)
        return {"vert": not ajoutes, "ajoutes": ajoutes}
    if nom == "touches":
        fichiers = tests_touches(base)
        if not fichiers:
            return {"vert": True, "fichiers": []}
        ok, queue = jouer(poste, *fichiers, "-m", "not combinaisons_longues")
        return {"vert": ok, "fichiers": fichiers, "sortie": queue}
    if nom == "combinaisons":
        ok, queue = jouer(poste, "tests/mark/partie_1/test_combinaisons.py", "-m", "combinaisons and not combinaisons_longues")
        return {"vert": ok, "sortie": queue}
    if nom == "fusions":
        if lot not in ("2", "3", "6", "7"):
            return {"vert": True, "sans_objet": "fusions demandées aux lots 2, 3, 6 et 7"}
        ok, queue = jouer(poste, "tests/mark/partie_1/test_combinaisons.py", "-m", "combinaisons_longues", "-k", "test_fusions_de_deux")
        return {"vert": ok, "sortie": queue}
    raise SystemExit(f"contrôle inconnu : {nom}")


def lancer(lot: str, poste: str | None, etape: str | None, depuis: str | None) -> int:
    if _git("status", "--porcelain", "--", ".", ":!api/outils/.garde-en-cours", ":!api/outils/garde"):
        print("arbre sale : la garde teste le commit HEAD, commite d'abord")
        return 2
    commit, base = _git("rev-parse", "HEAD"), reference(depuis)
    EN_COURS.mkdir(exist_ok=True)
    fiche = EN_COURS / f"lot-{lot}.json"
    etat = json.loads(fiche.read_text(encoding="utf-8")) if fiche.exists() else {}
    if etat.get("commit_teste") != commit:
        etat = {"commit_teste": commit, "controles": {}}
    for nom in ([etape] if etape else ETAPES):
        if not etape and etat["controles"].get(nom, {}).get("vert"):
            continue
        print(f"-- {nom} ...", flush=True)
        etat["controles"][nom] = controle(nom, lot, poste, base)
        fiche.write_text(json.dumps(etat, indent=1, ensure_ascii=False), encoding="utf-8")
        print("   ", "vert" if etat["controles"][nom]["vert"] else "ROUGE", json.dumps(etat["controles"][nom], ensure_ascii=False)[:900], flush=True)
    if etape:
        return 0
    if all(etat["controles"].get(n, {}).get("vert") for n in ETAPES):
        SORTIE.mkdir(exist_ok=True)
        (SORTIE / f"lot-{lot}.json").write_text(json.dumps(
            {"lot": lot, "commit_teste": commit, "base_de_comparaison": base, "poste": poste, "vert": True, "controles": etat["controles"]},
            indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"garde verte : outils/garde/lot-{lot}.json (commit testé {commit[:8]}) ; à commiter seul")
        return 0
    print("garde ROUGE :", [n for n in ETAPES if not etat["controles"].get(n, {}).get("vert")])
    return 1


# --------------------------------------------------------------------------- les bases

def ecrire_les_bases() -> None:
    courant = comptes_ruff()
    BASE_RUFF.write_text(json.dumps({"regles": list(REGLES_RUFF), "fichiers": courant, "existants": I.fichiers_du_code()}, indent=1,
                                    ensure_ascii=False) + "\n", encoding="utf-8")
    inv = I.inventaire()
    perimetre = I.charger(PERIMETRE)
    BASE_INVENTAIRE.write_text(json.dumps({**inv, "ignore_imports_max": _compter_les_ignores(), "longueurs_d_avant": perimetre["longueurs_d_avant"]},
                                          indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("bases écrites :", len(courant), "fichiers avec ruff,", len(inv["fichiers"]), "fichiers avec inventaire")


def figer() -> int:
    """Coordinateur : réécrit les bases si, et seulement si, rien n'a monté."""
    courant, base = comptes_ruff(), I.charger(BASE_RUFF)
    existants = set(base["existants"])
    hausses = [f"{f} {r}" for f, regles in courant.items() for r, n in regles.items()
               if f in existants and n > base["fichiers"].get(f, {}).get(r, 0)]
    inv, base_i = I.inventaire(), I.charger(BASE_INVENTAIRE)
    hausses += I.comparer(inv, base_i, I.charger(PERIMETRE))
    if hausses:
        print("figer refusé : un compte a monté", hausses[:20])
        return 1
    BASE_RUFF.write_text(json.dumps({**base, "fichiers": courant, "existants": I.fichiers_du_code()}, indent=1, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    BASE_INVENTAIRE.write_text(json.dumps({**base_i, **inv, "ignore_imports_max": min(base_i["ignore_imports_max"], _compter_les_ignores())},
                                          indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("bases figées à l'état présent")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("lot", nargs="?")
    p.add_argument("--poste")
    p.add_argument("--etape", choices=ETAPES)
    p.add_argument("--depuis")
    p.add_argument("--figer", action="store_true")
    p.add_argument("--creer-les-bases", action="store_true")
    a = p.parse_args()
    if a.figer:
        return figer()
    if a.creer_les_bases:
        ecrire_les_bases()
        return 0
    if not a.lot:
        p.error("le numéro de lot est obligatoire")
    return lancer(a.lot, a.poste, a.etape, a.depuis)


if __name__ == "__main__":
    sys.exit(main())
