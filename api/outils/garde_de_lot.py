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


ROUGES_DE_DEPART = OUTILS / "rouges_de_depart.json"


def rouges_connus() -> set[str]:
    """Les tests déjà rouges à la base du chantier (7bdfd515), vus rouges là-bas : ils ne rendent pas la garde rouge, mais n'en cachent aucun autre."""
    return set(I.charger(ROUGES_DE_DEPART)["tests"]) if ROUGES_DE_DEPART.exists() else set()


def echecs_de(sortie: str) -> set[str]:
    return {m.group(1).strip() for m in re.finditer(r"^(?:FAILED|ERROR) (\S+)", sortie, re.M)}


def jouer(poste: str | None, *args: str) -> tuple[bool, str]:
    r = subprocess.run(commande_de_test(poste, *args, "-rfEp"), cwd=I.RACINE_API, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONUTF8": "1"}, timeout=590)
    plein = r.stdout or ""
    perimes = sorted(rouges_connus() & {m.group(1).strip() for m in re.finditer(r"^PASSED (\S+)", plein, re.M)})
    if perimes:
        return False, f"entrée périmée de rouges_de_depart.json (le test repasse au vert : la retirer) : {perimes}"
    queue = "\n".join(plein.strip().splitlines()[-6:])
    if r.returncode == 0:
        return True, queue
    echecs = echecs_de(plein)
    inconnus = sorted(e for e in echecs if e not in rouges_connus())
    if echecs and not inconnus:
        return True, queue + f"\n[rouges de départ seuls : {sorted(echecs)}]"
    return False, queue + (f"\n[rouges nouveaux : {inconnus}]" if inconnus else "")


def _modules_importes(source: str, module_du_test: str) -> set[str]:
    """Les noms de modules qu'un fichier importe (imports paresseux compris) : ``from a.b import c`` donne ``a.b`` et ``a.b.c``."""
    import ast

    try:
        arbre = ast.parse(source)
    except SyntaxError:
        return set()
    paquet = module_du_test.rpartition(".")[0]
    sortie: set[str] = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            sortie |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = paquet.split(".")
                base = base[: len(base) - (n.level - 1)]
                cible = ".".join(base + ([n.module] if n.module else []))
            else:
                cible = n.module or ""
            sortie.add(cible)
            sortie |= {f"{cible}.{a.name}" for a in n.names}
    return sortie


def tests_touches(base: str) -> list[str]:
    """Les fichiers de ``tests/mark`` qui importent directement un module modifié, plus les tests modifiés ; lus à l'arbre syntaxique (``grimp`` ne voit pas
    le paquet ``api.services``, un espace de noms)."""
    modifies = [f for f in fichiers_modifies(base) if f.endswith(".py")]
    cibles = {I._module_du_fichier(f) for f in modifies}
    sortie = []
    for p in sorted((I.RACINE_API / "tests" / "mark").rglob("test_*.py")):
        rel = p.relative_to(I.RACINE_API).as_posix()
        if rel in modifies or _modules_importes(p.read_text(encoding="utf-8"), I._module_du_fichier(rel)) & cibles:
            sortie.append(rel)
    return sortie


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
        fichiers = [f for f in tests_touches(base) if not f.endswith(("test_combinaisons.py", "test_l05_latence.py"))]  # la profondeur 1 et la latence ont leur place à part
        if not fichiers:
            return {"vert": True, "fichiers": []}
        n = max(1, int(os.environ.get("GARDE_MORCEAUX", "6")))
        morceaux = [fichiers[i::n] for i in range(n)]
        return {"morceaux": n, "fichiers": fichiers, "_jouer": morceaux}
    if nom == "combinaisons":
        ok, queue = jouer(poste, "tests/mark/partie_1/test_combinaisons.py", "-m", "combinaisons and not combinaisons_longues")
        return {"vert": ok, "sortie": queue}
    if nom == "fusions":
        if lot not in ("2", "3", "6", "7"):
            return {"vert": True, "sans_objet": "fusions demandées aux lots 2, 3, 6 et 7"}
        from api.tests.mark.partie_1 import combinaisons as C

        ids = [f"tests/mark/partie_1/test_combinaisons.py::test_fusions_de_deux[{etat}]" for etat in C.ETATS]
        return {"morceaux": len(ids), "fichiers": ids, "_jouer": [[i] for i in ids], "_marqueur": "combinaisons_longues"}
    raise SystemExit(f"contrôle inconnu : {nom}")


def _controle_en_morceaux(nom: str, lot: str, poste: str | None, base: str, deja: dict | None, partie: int | None) -> dict:
    """``touches`` se joue par morceaux (chaque commande reste sous 10 minutes) : ``--partie k`` en joue un, sans ``--partie`` le premier non joué."""
    r = controle(nom, lot, poste, base)
    morceaux = r.pop("_jouer", None)
    marqueur = r.pop("_marqueur", None)
    if morceaux is None:
        return r
    faits = dict((deja or {}).get("faits") or {}) if (deja or {}).get("fichiers") == r["fichiers"] else {}
    a_jouer = [partie] if partie is not None else [k for k in range(len(morceaux)) if not faits.get(str(k), {}).get("vert")][:1]
    for k in a_jouer:
        ok, queue = jouer(poste, *morceaux[k], "-m", marqueur or "not combinaisons_longues and not latence")
        faits[str(k)] = {"vert": ok, "fichiers": len(morceaux[k]), "sortie": queue}
    r["faits"] = faits
    r["vert"] = len(faits) == len(morceaux) and all(f["vert"] for f in faits.values())
    r["reste"] = [k for k in range(len(morceaux)) if not faits.get(str(k), {}).get("vert")]
    return r


def lancer(lot: str, poste: str | None, etape: str | None, depuis: str | None, partie: int | None = None) -> int:
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
        etat["controles"][nom] = _controle_en_morceaux(nom, lot, poste, base, etat["controles"].get(nom), partie)
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
    p.add_argument("--partie", type=int, help="touches : le morceau à jouer (0 à GARDE_MORCEAUX-1)")
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
    return lancer(a.lot, a.poste, a.etape, a.depuis, a.partie)


if __name__ == "__main__":
    sys.exit(main())
