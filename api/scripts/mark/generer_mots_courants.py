"""[.mark] Build the list of common French words the trade vocabulary checks against.

Why: « chauffe », « royal », « cheminée » are real words; a brand must not be
read in them unless a strong cue comes first ("poêle", "marque"...). The
2026-09-16 trial measured 0 false brand on 81 sentences with this guard.

Run from the repository root, with ``wordfreq`` installed BY HAND for the
script only (it is 38 MB in memory and never needed by a call, so it is not in
``requirements.txt``):

    pip install wordfreq
    PYTHONPATH=. python -m api.scripts.mark.generer_mots_courants

Writes ``api/assets/lexique/mots-courants-fr-AAAA-MM.txt``: one word per line,
most frequent first, after a ``#`` header. Then point ``FICHIER_MOTS_COURANTS``
in ``api/services/lexique/analyse.py`` at the new file, run
``api/tests/mark/test_analyse_lexique.py``, and delete the old file in the same
commit.

Source: wordfreq (Robyn Speer), word list « fr », Zipf frequency >= 3.0.
Data licence: CC BY-SA 4.0 (attribution kept in the file header). ⚠️ Decision
L12 of 2026-09-16: the licence is reviewed only if the fork becomes public.

⛔ Never called during a call.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

SEUIL_ZIPF = 3.0
# Wide enough to reach every word above the threshold (about 31 800 in 2026-09).
TAILLE_LISTE = 60000
DOSSIER = Path(__file__).resolve().parents[2] / "assets" / "lexique"


def mots_courants() -> list[str]:
    from wordfreq import top_n_list, zipf_frequency

    return [m for m in top_n_list("fr", TAILLE_LISTE) if zipf_frequency(m, "fr") >= SEUIL_ZIPF]


def main() -> None:
    maintenant = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sortie",
        type=Path,
        default=DOSSIER / f"mots-courants-fr-{maintenant:%Y-%m}.txt",
    )
    arguments = parser.parse_args()

    import importlib.metadata

    mots = mots_courants()
    entete = [
        "# [.mark] Common French words: a brand is not read in them without a strong cue.",
        f"# Source: wordfreq {importlib.metadata.version('wordfreq')} (Robyn Speer), list « fr »,"
        f" Zipf frequency >= {SEUIL_ZIPF}.",
        "# Licence of the data: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/",
        f"# Generated {maintenant:%Y-%m-%d} by api/scripts/mark/generer_mots_courants.py, {len(mots)} words.",
    ]
    arguments.sortie.parent.mkdir(parents=True, exist_ok=True)
    arguments.sortie.write_text("\n".join([*entete, *mots]) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(mots)} words -> {arguments.sortie}")


if __name__ == "__main__":
    main()
