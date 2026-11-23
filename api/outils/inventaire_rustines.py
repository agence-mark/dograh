"""[.mark] Inventaire des rustines : ce que l'arbre syntaxique sait compter, comparé à une base qui ne monte jamais (plan final Partie 1, lot 1).

Six comptes, tous par fichier :
* ``drapeaux`` : les drapeaux « déjà dit », « question gardée », « accord de relecture »… (liste fermée ``DRAPEAUX``) ;
* ``erreurs_avalees`` : un ``except`` bare, ``Exception`` ou ``BaseException`` qui ne relance pas et n'écrit rien au journal ;
* ``noms_prives`` : ``from X import _nom`` où X est dans un autre paquet que le fichier qui importe ;
* ``lecture_de_mots`` : dans le moteur (commande, actions_communes, reservation), les appels qui lisent le texte (expressions régulières,
  ``startswith``, ``endswith``, ``removeprefix``, ``removesuffix``, noms de la dernière parole). C'est un indicateur : il voit la forme,
  pas l'intention ; il ne voit pas une lecture faite par une autre fonction ;
* ``fonctions_longues`` : les fonctions de plus de ``SEUIL_DE_LONGUEUR`` lignes (lignes réelles, pas instructions) ;
* ``noqa`` : comptés par la garde sur les lignes ajoutées.

Ce que l'outil ne voit pas : un nom privé lu par ``module._nom`` (seul l'import est compté), un ``except`` d'un type plus étroit qui avale
une panne, un drapeau écrit sous un autre nom.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import warnings
from pathlib import Path

RACINE_API = Path(__file__).resolve().parents[1]
RACINE_DEPOT = RACINE_API.parent
SEUIL_DE_LONGUEUR = 80

DRAPEAUX = (
    "relecture_acceptee", "fin_dite", "question_gardee", "APRES_C_EST_TOUT", "allergie_donnee*", "actions_tenues_par",
    "CLE_FAITS_A_DIRE", "QUESTION_DEJA_DONNEE",
)
DOSSIERS_DU_MOTEUR = ("services/commande/", "services/actions_communes/", "services/reservation/")
APPELS_DE_LECTURE = {"startswith", "endswith", "removeprefix", "removesuffix"}
FONCTIONS_RE = {"search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split", "compile"}
NOMS_DE_LA_PAROLE = ("derniere_parole", "paroles_de_la_personne", "texte_de_la_personne")
APPELS_DE_JOURNAL = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log", "opt", "bind"}
EXCLUS = ("tests/", "alembic/", "__pycache__/")


# --------------------------------------------------------------------------- les fichiers

def fichiers_du_code(racine: Path = RACINE_API) -> list[str]:
    """Les fichiers Python de ``api/`` hors tests, en chemins relatifs à ``api/`` (barres obliques)."""
    sortie = []
    for p in sorted(racine.rglob("*.py")):
        rel = p.relative_to(racine).as_posix()
        if not any(rel.startswith(x) or f"/{x}" in rel for x in EXCLUS):
            sortie.append(rel)
    return sortie


def _arbre(source: str):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ast.parse(source)
    except SyntaxError:
        return None


# --------------------------------------------------------------------------- les comptes d'un fichier

def _est_drapeau(nom: str, drapeau: str) -> bool:
    return nom.startswith(drapeau[:-1]) if drapeau.endswith("*") else nom == drapeau


def compter_les_drapeaux(source: str) -> dict[str, int]:
    arbre = _arbre(source)
    n: dict[str, int] = {}
    if arbre is None:
        return n
    for noeud in ast.walk(arbre):
        noms: list[str] = []
        if isinstance(noeud, ast.Name):
            noms = [noeud.id]
        elif isinstance(noeud, ast.Attribute):
            noms = [noeud.attr]
        elif isinstance(noeud, ast.Constant) and isinstance(noeud.value, str) and len(noeud.value) < 60:
            noms = [noeud.value]
        elif isinstance(noeud, ast.keyword) and noeud.arg:
            noms = [noeud.arg]
        elif isinstance(noeud, ast.arg):
            noms = [noeud.arg]
        elif isinstance(noeud, ast.alias):
            noms = [noeud.asname or noeud.name]
        for nom in noms:
            for d in DRAPEAUX:
                if _est_drapeau(nom, d):
                    n[d] = n.get(d, 0) + 1
    return n


def _type_large(type_) -> bool:
    if type_ is None:
        return True
    if isinstance(type_, ast.Name):
        return type_.id in ("Exception", "BaseException")
    if isinstance(type_, ast.Tuple):
        return any(_type_large(t) for t in type_.elts)
    return False


def _journalise_ou_relance(corps: list[ast.stmt]) -> bool:
    for instruction in corps:
        for noeud in ast.walk(instruction):
            if isinstance(noeud, ast.Raise):
                return True
            if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute):
                if noeud.func.attr in APPELS_DE_JOURNAL:
                    return True
                if isinstance(noeud.func.value, ast.Name) and noeud.func.value.id in ("logger", "log", "logging", "journal"):
                    return True
    return False


def compter_les_erreurs_avalees(source: str) -> int:
    arbre = _arbre(source)
    if arbre is None:
        return 0
    return sum(1 for n in ast.walk(arbre)
               if isinstance(n, ast.ExceptHandler) and _type_large(n.type) and not _journalise_ou_relance(n.body))


def _module_du_fichier(chemin: str) -> str:
    parties = chemin[:-3].split("/")
    if parties[-1] == "__init__":
        parties = parties[:-1]
    return ".".join(["api", *parties])


def _paquet_du_module(module: str, racine: Path) -> str:
    """Le paquet d'un module : lui-même si c'est un dossier, sinon son parent."""
    rel = module.split(".")[1:]
    return module if rel and (racine.joinpath(*rel)).is_dir() else module.rpartition(".")[0]


def compter_les_noms_prives(source: str, chemin: str, racine: Path = RACINE_API) -> int:
    arbre = _arbre(source)
    if arbre is None:
        return 0
    module = _module_du_fichier(chemin)
    est_init = chemin.endswith("__init__.py")
    paquet_local = module if est_init else module.rpartition(".")[0]
    n = 0
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.ImportFrom):
            continue
        if noeud.level:
            base = paquet_local.split(".")
            base = base[: len(base) - (noeud.level - 1)]
            cible = ".".join(base + ([noeud.module] if noeud.module else []))
        else:
            cible = noeud.module or ""
        if not cible.startswith("api"):
            continue
        if _paquet_du_module(cible, racine) == paquet_local:
            continue
        n += sum(1 for a in noeud.names if a.name.startswith("_") and not a.name.startswith("__"))
    return n


def compter_la_lecture_de_mots(source: str) -> int:
    arbre = _arbre(source)
    if arbre is None:
        return 0
    n = 0
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute):
            f = noeud.func
            if f.attr in APPELS_DE_LECTURE:
                n += 1
            elif isinstance(f.value, ast.Name) and f.value.id == "re" and f.attr in FONCTIONS_RE:
                n += 1
        if isinstance(noeud, (ast.Name, ast.Attribute)):
            nom = noeud.id if isinstance(noeud, ast.Name) else noeud.attr
            if any(m in nom for m in NOMS_DE_LA_PAROLE):
                n += 1
    return n


def fonctions_du_fichier(source: str) -> dict[str, int]:
    """``{nom qualifié: longueur en lignes}`` de toutes les fonctions (méthodes et fonctions emboîtées comprises)."""
    arbre = _arbre(source)
    sortie: dict[str, int] = {}
    if arbre is None:
        return sortie

    def descendre(noeud, prefixe):
        for enfant in ast.iter_child_nodes(noeud):
            if isinstance(enfant, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nom = f"{prefixe}{enfant.name}"
                if not isinstance(enfant, ast.ClassDef):
                    sortie[nom] = enfant.end_lineno - enfant.lineno + 1
                descendre(enfant, nom + ".")
            else:
                descendre(enfant, prefixe)

    descendre(arbre, "")
    return sortie


def fonctions_longues(source: str, seuil: int = SEUIL_DE_LONGUEUR) -> dict[str, int]:
    return {nom: n for nom, n in fonctions_du_fichier(source).items() if n > seuil}


# --------------------------------------------------------------------------- l'inventaire de l'arbre

def inventaire(fichiers: list[str] | None = None, racine: Path = RACINE_API) -> dict:
    """Les comptes de chaque fichier du code (hors tests) : ``{"fichiers": {chemin: {drapeaux, erreurs_avalees, noms_prives, lecture_de_mots,
    fonctions_longues}}}``. Seuls les fichiers qui ont au moins un compte non nul y figurent."""
    fichiers = fichiers if fichiers is not None else fichiers_du_code(racine)
    sortie: dict[str, dict] = {}
    for chemin in fichiers:
        source = (racine / chemin).read_text(encoding="utf-8")
        ligne = {
            "drapeaux": compter_les_drapeaux(source),
            "erreurs_avalees": compter_les_erreurs_avalees(source),
            "noms_prives": compter_les_noms_prives(source, chemin, racine),
            "lecture_de_mots": compter_la_lecture_de_mots(source) if chemin.startswith(DOSSIERS_DU_MOTEUR) else 0,
            "fonctions_longues": fonctions_longues(source),
        }
        if any(v for v in ligne.values()):
            sortie[chemin] = ligne
    return {"fichiers": sortie}


def totaux(inv: dict) -> dict:
    t = {"drapeaux": {d: 0 for d in DRAPEAUX}, "erreurs_avalees": 0, "noms_prives": 0, "lecture_de_mots": 0, "fonctions_longues": 0}
    for ligne in inv["fichiers"].values():
        for d, n in ligne["drapeaux"].items():
            t["drapeaux"][d] += n
        for cle in ("erreurs_avalees", "noms_prives", "lecture_de_mots"):
            t[cle] += ligne[cle]
        t["fonctions_longues"] += len(ligne["fonctions_longues"])
    return t


def comparer(courant: dict, base: dict, perimetre: dict | None = None) -> list[str]:
    """Les écarts où le courant dépasse la base (liste vide = rien n'a monté). Un fichier absent de la base compte pour zéro."""
    ecarts: list[str] = []
    bf = base["fichiers"]
    for chemin, ligne in courant["fichiers"].items():
        avant = bf.get(chemin, {"drapeaux": {}, "erreurs_avalees": 0, "noms_prives": 0, "lecture_de_mots": 0, "fonctions_longues": {}})
        for d, n in ligne["drapeaux"].items():
            if n > avant["drapeaux"].get(d, 0):
                ecarts.append(f"{chemin} : drapeau {d} {avant['drapeaux'].get(d, 0)} -> {n}")
        for cle in ("erreurs_avalees", "noms_prives", "lecture_de_mots"):
            if ligne[cle] > avant[cle]:
                ecarts.append(f"{chemin} : {cle} {avant[cle]} -> {ligne[cle]}")
        for nom, n in ligne["fonctions_longues"].items():
            ancien = avant["fonctions_longues"].get(nom)
            if ancien is None:
                ecarts.append(f"{chemin} : fonction de plus de {SEUIL_DE_LONGUEUR} lignes nouvelle, {nom} ({n} lignes)")
            elif n > ancien:
                ecarts.append(f"{chemin} : {nom} grossit {ancien} -> {n} lignes")
    tc, tb = totaux(courant), totaux(base)
    for d in DRAPEAUX:
        if tc["drapeaux"][d] > tb["drapeaux"].get(d, 0):
            ecarts.append(f"total : drapeau {d} {tb['drapeaux'].get(d, 0)} -> {tc['drapeaux'][d]}")
    for cle in ("erreurs_avalees", "noms_prives", "lecture_de_mots", "fonctions_longues"):
        if tc[cle] > tb[cle]:
            ecarts.append(f"total : {cle} {tb[cle]} -> {tc[cle]}")
    if perimetre is not None:
        compte_p = fonctions_longues_du_perimetre(courant, perimetre)
        compte_b = fonctions_longues_du_perimetre(base, perimetre)
        if len(compte_p) > len(compte_b):
            ecarts.append(f"périmètre : fonctions de plus de {SEUIL_DE_LONGUEUR} lignes {len(compte_b)} -> {len(compte_p)}")
    return ecarts


def fonctions_longues_du_perimetre(inv: dict, perimetre: dict) -> list[str]:
    """Les fonctions longues qui sont dans ``perimetre["fonctions"]`` (écrites ou grossies par la Partie 1)."""
    sortie = []
    for chemin, ligne in inv["fichiers"].items():
        dans = set(perimetre["fonctions"].get(chemin, ()))
        sortie += [f"{chemin}::{nom}" for nom in ligne["fonctions_longues"] if nom in dans]
    return sorted(sortie)


# --------------------------------------------------------------------------- le périmètre (git blame de la Partie 1)

def lignes_ajoutees(debut: str, fin: str, depot: Path = RACINE_DEPOT) -> dict[str, set[int]]:
    """``{chemin relatif à api/: lignes ajoutées}`` des fichiers Python hors tests entre deux commits (renommages suivis)."""
    texte = subprocess.run(["git", "diff", "-U0", "-M", debut, fin, "--", "api"], cwd=depot, capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout
    sortie: dict[str, set[int]] = {}
    courant = None
    for ligne in texte.splitlines():
        if ligne.startswith("+++ "):
            chemin = ligne[6:] if ligne.startswith("+++ b/") else None
            rel = chemin[4:] if chemin and chemin.startswith("api/") else None
            ok = rel and rel.endswith(".py") and not any(rel.startswith(x) or f"/{x}" in rel for x in EXCLUS)
            courant = rel if ok else None
            if courant:
                sortie.setdefault(courant, set())
        elif ligne.startswith("@@") and courant:
            m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", ligne)
            if m:
                debut_l, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
                sortie[courant].update(range(debut_l, debut_l + n))
    return sortie


def fonctions_touchees(source: str, lignes: set[int]) -> list[str]:
    """Les fonctions dont l'étendue contient au moins une ligne ajoutée."""
    arbre = _arbre(source)
    sortie: list[str] = []
    if arbre is None:
        return sortie

    def descendre(noeud, prefixe):
        for enfant in ast.iter_child_nodes(noeud):
            if isinstance(enfant, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nom = f"{prefixe}{enfant.name}"
                if not isinstance(enfant, ast.ClassDef) and any(enfant.lineno <= l <= enfant.end_lineno for l in lignes):
                    sortie.append(nom)
                descendre(enfant, nom + ".")
            else:
                descendre(enfant, prefixe)

    descendre(arbre, "")
    return sortie


def charger(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))
