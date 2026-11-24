"""[.mark] Lot 5 (n° 143) : la dérivation INITIALE du contrat des outils sans carte (``outils.json``) depuis les rendus du banc (``banc/rendus.json``).

    python -m api.outils.generer_le_contrat            # dit si ``outils.json`` est encore égal à la dérivation des rendus
    python -m api.outils.generer_le_contrat --ecrire   # écrit la dérivation ; REFUSÉ si ``outils.json`` existe (il est la source depuis la version 7)

Le contrat est né de cette dérivation (version 6 des rendus du Labo, ``verser_textes.py``). Depuis la version 7, ``outils.json`` est la SOURCE : un texte s'y corrige à la
main (n° 43 : la case ``variante``) et les rendus du banc ne le réécrivent plus ; ``--ecrire`` ne sert qu'à le recréer s'il manque. Rien d'une carte de test n'y reste ;
les listes fermées construites au décroché (``commande.contrat.LISTES``) ont perdu leurs valeurs de carte.
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
        if chemin.exists():
            print("refusé : outils.json existe, il est la source du contrat")
            return 2
        chemin.write_text(voulu, encoding="utf-8", newline="\n")
        print(f"écrit : {chemin.name} ({len(voulu)} octets)")
        return 0
    egal = chemin.exists() and chemin.read_text(encoding="utf-8").replace("\r\n", "\n") == voulu
    print("égal à la dérivation" if egal else "DIFFÉRENT de la dérivation")
    return 0 if egal else 1


if __name__ == "__main__":
    sys.exit(main())
