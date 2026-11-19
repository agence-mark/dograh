"""Joue des mutants écrits à la main, décrits dans un fichier, sur les lignes d'un lot.

mutmut mute des fonctions entières : pour un lot qui touche quelques lignes d'un
long fichier, il noie les mutants des lignes touchées parmi ceux du reste. Ce
script joue ceux qu'on a choisis, un par un, dans une COPIE jetable de ``api/`` :
l'arbre de travail n'est jamais modifié.

    mutants.py <fichier.json>

Le fichier donne les tests du lot et la liste des mutants :

    {"essais": ["tests/mark/test_x.py"],
     "mutants": [{"nom": "...", "fichier": "services/x.py", "avant": "...", "apres": "..."}]}

Pour chaque mutant : le texte « avant » (qui doit apparaître une seule fois) est
remplacé par « apres » dans la copie, les tests sont joués, le fichier est remis.
« tué » : un test échoue. « survivant » : tous passent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ORIGINE = Path("/app/api")
COPIE = Path("/tmp/mutants")


def jouer(essais: list[str]) -> bool:
    """Rend True si les tests du lot passent sur la copie."""
    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--timeout=120", "-q", "-x", *essais],
        cwd=COPIE / "api",
        env={**os.environ, "PYTHONPATH": f"/app/pipecat/src:{COPIE}"},
        capture_output=True,
        text=True,
        check=False,
    )
    return resultat.returncode == 0


def principal(arguments: list[str]) -> int:
    if len(arguments) != 1:
        print(__doc__, file=sys.stderr)
        return 1
    lot = json.loads(Path(arguments[0]).read_text(encoding="utf-8"))
    essais: list[str] = lot["essais"]
    mutants: list[dict[str, str]] = lot["mutants"]

    shutil.rmtree(COPIE, ignore_errors=True)
    shutil.copytree(ORIGINE, COPIE / "api")
    if not jouer(essais):
        print("Les tests du lot sont rouges sur la copie non mutée : rien n'est mesurable.")
        return 2
    print("Sans mutant : les tests passent (témoin).")

    survivants = []
    for mutant in mutants:
        fichier = COPIE / "api" / mutant["fichier"]
        original = fichier.read_text(encoding="utf-8")
        if original.count(mutant["avant"]) != 1:
            print(f"NON APPLICABLE  {mutant['nom']} (texte attendu absent ou répété)")
            survivants.append(mutant["nom"])
            continue
        fichier.write_text(original.replace(mutant["avant"], mutant["apres"]), encoding="utf-8")
        try:
            passe = jouer(essais)
        finally:
            fichier.write_text(original, encoding="utf-8")
        print(f"{'SURVIVANT' if passe else 'tué      '}  {mutant['nom']}")
        if passe:
            survivants.append(mutant["nom"])

    print(f"\n{len(mutants) - len(survivants)} tués sur {len(mutants)}. Survivants : {survivants or 'aucun'}")
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
