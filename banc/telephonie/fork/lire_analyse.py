"""Relève l'analyse d'un run du fork, par la route de sa fenêtre du run.

    lire_analyse.py <mesure> [numéro du run ou 0] [agent, agent_outil ou agent_transfert]

Écrit /resultats/<mesure>.analyse.json : la réponse entière de
GET /workflow/<agent>/runs/<run>/analyse, dont le chronomètre par tour (mesure
M2 du fork). Sans numéro de run : le dernier run de l'agent du banc.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from preparer_donnees import FICHIER_ETAT, appeler, ouvrir_session

DOSSIER = Path("/resultats")
DELAI_DE_CLOTURE_S = 40


def dernier_run(jeton: str, agent: int) -> int:
    reponse = appeler("GET", f"/workflow/{agent}/runs?limit=1&page=1", jeton=jeton)
    runs = reponse.get("runs", []) if isinstance(reponse, dict) else reponse
    if not runs:
        raise SystemExit("Aucun run pour l'agent du banc.")
    return max(int(run["id"]) for run in runs)


def attendre_la_cloture(jeton: str, agent: int, run: int) -> None:
    """Le journal d'un run n'est écrit en base qu'à sa clôture, quelques secondes
    après le raccrochage : relevée avant, l'analyse est vide sans le dire."""
    for _ in range(DELAI_DE_CLOTURE_S):
        etat = appeler("GET", f"/workflow/{agent}/runs/{run}", jeton=jeton)
        if isinstance(etat, dict) and etat.get("is_completed"):
            return
        time.sleep(1)
    print(f"Run {run} toujours ouvert après {DELAI_DE_CLOTURE_S} s.", file=sys.stderr)


def principal(arguments: list[str]) -> int:
    if not arguments:
        print(__doc__, file=sys.stderr)
        return 1
    mesure = arguments[0]
    etat = json.loads(FICHIER_ETAT.read_text())
    agent = int(etat[arguments[2] if len(arguments) > 2 else "agent"])
    jeton = ouvrir_session()
    demande = int(arguments[1]) if len(arguments) > 1 else 0
    run = demande or dernier_run(jeton, agent)
    attendre_la_cloture(jeton, agent, run)
    analyse = appeler("GET", f"/workflow/{agent}/runs/{run}/analyse", jeton=jeton)
    sortie = DOSSIER / f"{mesure}.analyse.json"
    sortie.write_text(
        json.dumps({"run": run, "analyse": analyse}, ensure_ascii=False, indent=1)
    )
    print(f"{sortie} : run {run}")
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
