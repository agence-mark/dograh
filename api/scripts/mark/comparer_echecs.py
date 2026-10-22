"""[.mark] Compare deux passages de la suite (branche et base) : qu'est-ce que MON code a cassé ?

Remplace ``tests-vs-base.mjs`` du poste (3 à 4 h) par la CI : voir ``.github/workflows/mark-ci-comparee.yml``.
Chaque passage laisse un dossier de trois fichiers :

* ``junit.xml``           rapport JUnit de pytest (``--junitxml``) ;
* ``code-sortie.txt``     code de sortie de pytest ;
* ``sonde-memoire.json``  état de la sonde (``api/tests/mark/sonde_memoire.py``).

Trois lectures indépendantes du même passage (réflexe R7, « un outil de vérification maison qui
ment ») : le code de sortie, le rapport JUnit et la sonde doivent s'accorder. Si l'une manque, est
tronquée ou contredit les autres, le passage est **incomplet** et le verdict est rouge, jamais un
« 0 échec nouveau » par défaut.

Verdict (code de sortie du programme) :

* ``0`` vert : aucun échec nouveau (les échecs déjà présents sur la base sont listés, pas bloquants) ;
* ``1`` rouge : au moins un échec nouveau, nommé ;
* ``2`` rouge « passage incomplet » : un des deux passages n'a pas fini, avec la raison.

Un test est **nouveau** s'il est rouge dans la branche et pas rouge dans la base. Un test vert seul
mais rouge dans la suite (fuite d'un test à l'autre) l'est donc aussi (D5) : on ne l'exclut jamais
par son nom. Un rouge né d'une dépendance l'est des deux côtés : il est affiché, pas bloquant (R5).

Usage : ``python comparer_echecs.py --branche DOSSIER --base DOSSIER [--mode-base TEXTE] [--resume FICHIER]``
(bibliothèque standard seule : la CI le lance avant d'installer quoi que ce soit).
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

FICHIER_JUNIT = "junit.xml"
FICHIER_CODE = "code-sortie.txt"
FICHIER_SONDE = "sonde-memoire.json"

VERT, ROUGE, INCOMPLET = 0, 1, 2

# Codes de pytest (``pytest.ExitCode``) et ceux que la CI peut rencontrer.
_CODES_COMPLETS = (0, 1)
_SENS_DES_CODES = {
    2: "pytest interrompu (collecte en erreur ou arrêt demandé)",
    3: "erreur interne de pytest",
    4: "mauvais appel de pytest",
    5: "aucun test collecté",
    86: "plafond mémoire dépassé (arrêt net par la sonde)",
    124: "délai dépassé",
    137: "processus tué (SIGKILL : mémoire du runner ou délai)",
    143: "processus arrêté (SIGTERM)",
}

LIMITE_LISTE = 200


@dataclass
class Passage:
    """Ce qu'on a pu relire d'un passage de la suite."""

    nom: str
    ids: set[str] = field(default_factory=set)
    rouges: dict[str, str] = field(
        default_factory=dict
    )  # id -> première ligne du message
    code_sortie: int | None = None
    pic_mo: float | None = None
    raisons: list[str] = field(default_factory=list)  # non vide = passage incomplet

    @property
    def complet(self) -> bool:
        return not self.raisons


@dataclass
class Verdict:
    code: int
    branche: Passage
    base: Passage
    nouveaux: dict[str, str] = field(default_factory=dict)
    deja_presents: dict[str, str] = field(default_factory=dict)
    corriges: list[str] = field(default_factory=list)
    disparus: list[str] = field(default_factory=list)
    mode_base: str = ""


# --------------------------------------------------------------------------- lecture


def _identifiant(testcase: ET.Element) -> str:
    classe = testcase.get("classname") or ""
    nom = testcase.get("name") or ""
    return f"{classe}::{nom}" if classe else nom


def _premiere_ligne(element: ET.Element) -> str:
    texte = element.get("message") or (element.text or "")
    ligne = texte.strip().splitlines()[0] if texte.strip() else ""
    return ligne[:160]


def lire_junit(chemin: Path) -> tuple[set[str], dict[str, str]]:
    """Rend (tous les tests relus, tests rouges). Lève ``ET.ParseError`` ou ``OSError``.

    Rouge = au moins un élément ``failure`` ou ``error`` (pytest émet parfois deux éléments pour un
    même test : l'appel passe, le démontage échoue). ``skipped`` n'est pas rouge.
    """
    racine = ET.parse(chemin).getroot()
    ids: set[str] = set()
    rouges: dict[str, str] = {}
    for cas in racine.iter("testcase"):
        identifiant = _identifiant(cas)
        ids.add(identifiant)
        for enfant in cas:
            if enfant.tag in ("failure", "error") and identifiant not in rouges:
                rouges[identifiant] = _premiere_ligne(enfant)
    return ids, rouges


def lire_passage(nom: str, dossier: Path) -> Passage:
    """Lit les trois fichiers d'un passage ; chaque anomalie devient une raison d'incomplétude."""
    p = Passage(nom=nom)
    if not dossier.is_dir():
        p.raisons.append(f"dossier du passage absent ({dossier})")
        return p

    # 1. Code de sortie de pytest.
    fichier_code = dossier / FICHIER_CODE
    if not fichier_code.is_file():
        p.raisons.append(
            "code de sortie de pytest absent (le passage n'a pas atteint la fin)"
        )
    else:
        try:
            p.code_sortie = int(fichier_code.read_text(encoding="utf-8").strip())
        except ValueError:
            p.raisons.append("code de sortie de pytest illisible")

    # 2. Rapport JUnit.
    fichier_junit = dossier / FICHIER_JUNIT
    junit_lu = False
    if not fichier_junit.is_file():
        p.raisons.append("rapport JUnit absent")
    else:
        try:
            p.ids, p.rouges = lire_junit(fichier_junit)
            junit_lu = True
        except (ET.ParseError, OSError) as erreur:
            p.raisons.append(f"rapport JUnit illisible ou tronqué ({erreur})")

    # 3. Sonde mémoire.
    sonde = None
    fichier_sonde = dossier / FICHIER_SONDE
    if not fichier_sonde.is_file():
        p.raisons.append("état de la sonde mémoire absent")
    else:
        try:
            sonde = json.loads(fichier_sonde.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            p.raisons.append("état de la sonde mémoire illisible")

    if sonde is not None:
        if isinstance(sonde.get("pic_mo"), (int, float)):
            p.pic_mo = float(sonde["pic_mo"])
        test = sonde.get("test_en_cours") or "(hors test : collecte ou fin de session)"
        if sonde.get("plafond_depasse"):
            p.raisons.append(
                f"plafond mémoire de {sonde.get('plafond_mo')} Mo dépassé pendant le test {test}"
            )
        elif not sonde.get("termine"):
            p.raisons.append(f"session pytest non terminée (dernier test : {test})")
        collecte = sonde.get("collecte")
        if collecte is None:
            p.raisons.append(
                "nombre de tests collectés inconnu (la collecte n'a pas fini)"
            )
        elif junit_lu and len(p.ids) < collecte:
            p.raisons.append(
                f"{collecte} tests collectés mais {len(p.ids)} seulement dans le rapport JUnit"
            )

    # Accord entre les lectures.
    if p.code_sortie is not None and p.code_sortie not in _CODES_COMPLETS:
        sens = _SENS_DES_CODES.get(p.code_sortie, "code inattendu")
        p.raisons.append(f"pytest a rendu le code {p.code_sortie} : {sens}")
    elif p.code_sortie is not None and junit_lu:
        if p.code_sortie == 0 and p.rouges:
            p.raisons.append(
                f"pytest annonce un succès (code 0) mais le rapport JUnit compte {len(p.rouges)} échec(s)"
            )
        elif p.code_sortie == 1 and not p.rouges:
            p.raisons.append(
                "pytest annonce des échecs (code 1) mais le rapport JUnit n'en compte aucun"
            )
    return p


# ------------------------------------------------------------------------ comparaison


def comparer(branche: Passage, base: Passage, mode_base: str = "") -> Verdict:
    v = Verdict(code=VERT, branche=branche, base=base, mode_base=mode_base)
    if not (branche.complet and base.complet):
        v.code = INCOMPLET
        return v
    v.nouveaux = {i: m for i, m in branche.rouges.items() if i not in base.rouges}
    v.deja_presents = {i: m for i, m in branche.rouges.items() if i in base.rouges}
    v.corriges = sorted(
        i for i in base.rouges if i in branche.ids and i not in branche.rouges
    )
    v.disparus = sorted(base.ids - branche.ids)
    v.code = ROUGE if v.nouveaux else VERT
    return v


# -------------------------------------------------------------------------- rendu


def _liste(titre: str, entrees: dict[str, str] | list[str]) -> list[str]:
    """Une section de liste ; une liste vide ne s'affiche pas (le titre du verdict le dit déjà)."""
    if not entrees:
        return []
    if isinstance(entrees, dict):
        lignes = [
            f"- `{i}`" + (f" : {m}" if m else "") for i, m in sorted(entrees.items())
        ]
    else:
        lignes = [f"- `{i}`" for i in entrees]
    if len(lignes) > LIMITE_LISTE:
        reste = len(lignes) - LIMITE_LISTE
        lignes = lignes[:LIMITE_LISTE] + [
            f"- … et {reste} autres (voir l'artefact JUnit)"
        ]
    return [f"### {titre} ({len(entrees)})", "", *lignes, ""]


def _cellule_passage(p: Passage) -> tuple[str, str, str]:
    tests = str(len(p.ids)) if p.ids else "?"
    echecs = str(len(p.rouges)) if p.ids else "?"
    pic = f"{p.pic_mo:.0f} Mo" if p.pic_mo is not None else "?"
    return tests, echecs, pic


def rendre(v: Verdict) -> str:
    titres = {
        VERT: "✅ Vert : aucun échec nouveau",
        ROUGE: f"🔴 Rouge : {len(v.nouveaux)} échec(s) nouveau(x)",
        INCOMPLET: "🔴 Rouge : passage incomplet",
    }
    sortie = [f"## CI comparée : {titres[v.code]}", ""]
    if v.mode_base:
        sortie += [f"**Base** : {v.mode_base}", ""]
    t1, e1, m1 = _cellule_passage(v.branche)
    t2, e2, m2 = _cellule_passage(v.base)
    sortie += [
        "| | Branche | Base |",
        "|---|---|---|",
        f"| Tests relus | {t1} | {t2} |",
        f"| Échecs | {e1} | {e2} |",
        f"| Pic de mémoire | {m1} | {m2} |",
        "",
    ]
    if v.code == INCOMPLET:
        for p in (v.branche, v.base):
            if not p.complet:
                sortie += [f"### Passage « {p.nom} » incomplet", ""]
                sortie += [f"- {r}" for r in p.raisons] + [""]
        sortie += [
            (
                "Un passage incomplet ne se lit jamais « aucun échec nouveau » : relancer, ou lire le journal "
                "du passage concerné."
            ),
            "",
        ]
        if v.branche.complet and v.branche.rouges:
            sortie += _liste(
                "Échecs de la branche (non comparés, la base est incomplète)",
                v.branche.rouges,
            )
        return "\n".join(sortie)

    sortie += _liste("Échecs nouveaux, bloquants", v.nouveaux)
    sortie += _liste("Échecs déjà présents sur la base, non bloquants", v.deja_presents)
    sortie += _liste("Rouges sur la base, verts dans la branche", v.corriges)
    sortie += _liste(
        "Présents sur la base, absents de la branche, supprimés ou renommés", v.disparus
    )
    return "\n".join(sortie)


# --------------------------------------------------------------------------- programme


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--branche", required=True, type=Path, help="dossier du passage de la branche"
    )
    ap.add_argument(
        "--base", required=True, type=Path, help="dossier du passage de la base"
    )
    ap.add_argument(
        "--mode-base", default="", help="texte affiché : comment la base a été obtenue"
    )
    ap.add_argument(
        "--resume",
        type=Path,
        help="fichier où ajouter le rapport (GITHUB_STEP_SUMMARY)",
    )
    args = ap.parse_args(argv)

    verdict = comparer(
        lire_passage("branche", args.branche),
        lire_passage("base", args.base),
        mode_base=args.mode_base,
    )
    texte = rendre(verdict)
    print(texte)
    if args.resume:
        with open(args.resume, "a", encoding="utf-8") as f:
            f.write(texte + "\n")
    return verdict.code


if __name__ == "__main__":
    sys.exit(main())
