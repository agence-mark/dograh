"""Mutants écrits à la main pour le lot 1 (vidage de la file audio d'Asterisk).

mutmut ne mute que le corps des fonctions : sur ce lot il ne produit qu'un
mutant. Ce script joue ceux qu'il ne produit pas, un par un, dans une COPIE
jetable de ``api/`` : l'arbre de travail n'est jamais modifié.

Pour chaque mutant : le texte est remplacé dans la copie, le test du lot est
joué, le fichier est remis. « tué » : le test échoue. « survivant » : il passe.

    ./banc.sh mutants-lot1
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ORIGINE = Path("/app/api")
COPIE = Path("/tmp/mutants-lot1")
SERIALISEUR = "services/telephony/providers/ari/serializers.py"
TRANSPORT = "services/telephony/providers/ari/transport.py"
ESSAI = "tests/mark/test_coupure_de_parole_vide_la_file_asterisk.py"

DELEGATION = "        return await super().serialize(frame)"


@dataclass(frozen=True)
class Mutant:
    nom: str
    fichier: str
    avant: str
    apres: str


MUTANTS = [
    Mutant(
        "la commande porte un autre nom",
        SERIALISEUR,
        'FLUSH_MEDIA_COMMAND = "FLUSH_MEDIA"',
        'FLUSH_MEDIA_COMMAND = "MEDIA_FLUSH"',
    ),
    Mutant(
        "la condition est inversée",
        SERIALISEUR,
        "if isinstance(frame, InterruptionFrame):",
        "if not isinstance(frame, InterruptionFrame):",
    ),
    Mutant(
        "la commande part pour toute trame",
        SERIALISEUR,
        "if isinstance(frame, InterruptionFrame):",
        "if True:",
    ),
    Mutant(
        "rien ne part à la coupure de parole",
        SERIALISEUR,
        "            return FLUSH_MEDIA_COMMAND",
        "            return None",
    ),
    Mutant(
        "la commande part en trame binaire",
        SERIALISEUR,
        "            return FLUSH_MEDIA_COMMAND",
        "            return FLUSH_MEDIA_COMMAND.encode()",
    ),
    Mutant(
        "les autres trames ne sont plus remises au parent",
        SERIALISEUR,
        DELEGATION,
        "        return None",
    ),
    Mutant(
        "la trame de fin d'appel n'est plus remise au parent",
        SERIALISEUR,
        DELEGATION,
        '        if type(frame).__name__ == "EndFrame":\n            return None\n'
        + DELEGATION,
    ),
    Mutant(
        "la trame d'annulation n'est plus remise au parent",
        SERIALISEUR,
        DELEGATION,
        '        if type(frame).__name__ == "CancelFrame":\n            return None\n'
        + DELEGATION,
    ),
    Mutant(
        "la fabrique construit le sérialiseur de l'amont",
        TRANSPORT,
        "serializer = AsteriskFrameSerializerMark(",
        "serializer = AsteriskFrameSerializer(",
    ),
]


def jouer() -> bool:
    """Rend True si le test du lot passe sur la copie."""
    resultat = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--timeout=120",
            "-q",
            "-x",
            ESSAI,
        ],
        cwd=COPIE / "api",
        env={
            **__import__("os").environ,
            "PYTHONPATH": f"/app/pipecat/src:{COPIE}",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return resultat.returncode == 0


def principal() -> int:
    shutil.rmtree(COPIE, ignore_errors=True)
    shutil.copytree(ORIGINE, COPIE / "api")

    if not jouer():
        print("Le test du lot est rouge sur la copie non mutée : rien n'est mesurable.")
        return 2
    print("Sans mutant : le test passe (témoin).")

    survivants = []
    for mutant in MUTANTS:
        fichier = COPIE / "api" / mutant.fichier
        original = fichier.read_text(encoding="utf-8")
        if original.count(mutant.avant) != 1:
            print(f"NON APPLICABLE  {mutant.nom} (texte attendu absent ou répété)")
            survivants.append(mutant.nom)
            continue
        fichier.write_text(
            original.replace(mutant.avant, mutant.apres), encoding="utf-8"
        )
        try:
            passe = jouer()
        finally:
            fichier.write_text(original, encoding="utf-8")
        print(f"{'SURVIVANT' if passe else 'tué      '}  {mutant.nom}")
        if passe:
            survivants.append(mutant.nom)

    tues = len(MUTANTS) - len(survivants)
    print(f"\n{tues} tués sur {len(MUTANTS)}. Survivants : {survivants or 'aucun'}")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
