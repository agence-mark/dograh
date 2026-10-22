"""[.mark] Seuil de gravité sur les rapports JSON d'``osv-scanner`` : bloquant à partir de « élevée ».

``osv-scanner`` rend 1 dès qu'il trouve une faille, quelle que soit sa gravité, et n'a pas de seuil.
Ce programme lit ses rapports (``--format json``) et ne rend rouge que pour les failles **critiques
ou élevées** (note CVSS ≥ 7,0 par défaut) des dépendances **de production** :

* un paquet dont le seul groupe est ``dev`` (lockfile npm) est ignoré ;
* une faille sans note est listée à part, non bloquante (rien ne la classe) ;
* un rapport illisible, sans clé ``results``, ou une liste vide de rapports = rouge « scan incomplet »
  (réflexe R7 : ne jamais rendre vert un scan qui n'a rien lu).

Usage : ``python verifier_osv.py [--seuil 7.0] [--resume FICHIER] rapport.json [rapport.json …]``
Sortie 0 : aucune faille au seuil ; 1 : au moins une ; 2 : scan incomplet.
Bibliothèque standard seule. Lancé par ``.github/workflows/mark-securite.yml``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SEUIL_PAR_DEFAUT = 7.0
GROUPES_IGNORES = {"dev"}


def _versions_corrigees(paquet: dict, ids: set[str]) -> list[str]:
    corrigees: set[str] = set()
    nom = paquet["package"]["name"]
    for vuln in paquet.get("vulnerabilities", []):
        if vuln.get("id") not in ids and not (ids & set(vuln.get("aliases", []))):
            continue
        for affecte in vuln.get("affected", []):
            if affecte.get("package", {}).get("name", nom).lower() != nom.lower():
                continue
            for plage in affecte.get("ranges", []):
                for evenement in plage.get("events", []):
                    if "fixed" in evenement:
                        corrigees.add(str(evenement["fixed"]))
    return sorted(corrigees)


def lire(rapport: Path) -> tuple[list[dict], list[str]]:
    """Rend (failles de production, raisons d'incomplétude). Une faille = un groupe d'avis d'un paquet."""
    try:
        donnees = json.loads(rapport.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        return [], [f"{rapport.name} : rapport illisible ({erreur})"]
    failles: list[dict] = []
    for resultat in donnees.get("results", []):
        source = Path(resultat.get("source", {}).get("path", "?")).name
        for paquet in resultat.get("packages", []):
            groupes_du_paquet = set(paquet.get("dependency_groups") or [])
            if groupes_du_paquet and groupes_du_paquet <= GROUPES_IGNORES:
                continue
            for groupe in paquet.get("groups", []):
                note = groupe.get("max_severity") or ""
                ids = set(groupe.get("ids", []))
                failles.append(
                    {
                        "paquet": paquet["package"]["name"],
                        "version": paquet["package"]["version"],
                        "avis": ", ".join(groupe.get("ids", [])[:2]),
                        "note": float(note) if note else None,
                        "corrige": _versions_corrigees(paquet, ids),
                        "source": source,
                    }
                )
    # osv-scanner n'écrit ``packages`` que pour les paquets AVEC faille : un rapport sans paquet est
    # normal pour un projet sain. On exige seulement un JSON bien formé avec la clé ``results``.
    if "results" not in donnees:
        return [], [f"{rapport.name} : pas de clé « results » (scan non abouti)"]
    return failles, []


def verifier(rapports: list[Path], seuil: float) -> tuple[int, str]:
    if not rapports:
        return (
            2,
            "## Dépendances (osv-scanner) : 🔴 scan incomplet\n\nAucun rapport à lire.\n",
        )
    failles: list[dict] = []
    raisons: list[str] = []
    for rapport in rapports:
        f, r = lire(rapport)
        failles += f
        raisons += r
    if raisons:
        return 2, "## Dépendances (osv-scanner) : 🔴 scan incomplet\n\n" + "\n".join(
            f"- {r}" for r in raisons
        ) + "\n"

    bloquantes = sorted(
        (f for f in failles if f["note"] is not None and f["note"] >= seuil),
        key=lambda f: (-f["note"], f["paquet"]),
    )
    sans_note = [f for f in failles if f["note"] is None]
    sous_seuil = len(failles) - len(bloquantes) - len(sans_note)

    titre = (
        f"🔴 {len(bloquantes)} faille(s) à {seuil:g} ou plus"
        if bloquantes
        else f"✅ aucune faille à {seuil:g} ou plus"
    )
    texte = [f"## Dépendances (osv-scanner) : {titre}", ""]
    if bloquantes:
        texte += [
            "| Note | Paquet | Version | Avis | Corrigé en | Fichier |",
            "|---|---|---|---|---|---|",
        ]
        for f in bloquantes:
            corrige = ", ".join(f["corrige"][:3]) or "?"
            texte.append(
                f"| {f['note']:g} | {f['paquet']} | {f['version']} | {f['avis']} | {corrige} | {f['source']} |"
            )
        texte.append("")
    if sans_note:
        texte += [
            f"Sans note, non bloquantes ({len(sans_note)}) : "
            + ", ".join(sorted({f"{f['paquet']} {f['version']}" for f in sans_note})),
            "",
        ]
    texte.append(
        f"Sous le seuil, non bloquantes : {sous_seuil}. Dépendances de développement seules : ignorées."
    )
    texte.append("")
    return (1 if bloquantes else 0), "\n".join(texte)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("rapports", nargs="*", type=Path)
    ap.add_argument("--seuil", type=float, default=SEUIL_PAR_DEFAUT)
    ap.add_argument(
        "--resume",
        type=Path,
        help="fichier où ajouter le rapport (GITHUB_STEP_SUMMARY)",
    )
    args = ap.parse_args(argv)
    code, texte = verifier(args.rapports, args.seuil)
    print(texte)
    if args.resume:
        with open(args.resume, "a", encoding="utf-8") as f:
            f.write(texte + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
