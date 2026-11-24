"""[.mark] Lot 5 (n° 143) : écrit le contrat des outils sans carte (``outils.json``) depuis les rendus du banc (``banc/rendus.json``).

    python -m api.outils.generer_le_contrat [--ecrire]     # sans --ecrire : dit seulement si le fichier écrit est égal à la dérivation

Le contrat est une dérivation des rendus que le Labo verse (``verser_textes.py``) : jamais corrigé à la main, et rien d'une carte de test n'y reste.
Les listes fermées construites au décroché (``commande.contrat.LISTES``) perdent leurs valeurs de carte.
"""

from __future__ import annotations

import argparse
import json
import sys

from api.services.commande import contrat as commande
from api.services.gabarits.restauration import textes
from api.services.gabarits.restauration.textes import banc


def le_contrat(version: str = textes.TEMOIN) -> dict:
    return banc.derivation_du_contrat(banc.rendus(version), {"commande": set(commande.LISTES)})


def ecrit(contrat_: dict) -> str:
    return json.dumps(contrat_, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ecrire", action="store_true")
    a = p.parse_args(argv)
    chemin = textes.DOSSIER / textes.TEMOIN / "outils.json"
    voulu = ecrit(le_contrat())
    if a.ecrire:
        chemin.write_text(voulu, encoding="utf-8", newline="\n")
        print(f"écrit : {chemin.name} ({len(voulu)} octets)")
        return 0
    egal = chemin.exists() and chemin.read_text(encoding="utf-8").replace("\r\n", "\n") == voulu
    print("égal à la dérivation" if egal else "DIFFÉRENT de la dérivation")
    return 0 if egal else 1


if __name__ == "__main__":
    sys.exit(main())
