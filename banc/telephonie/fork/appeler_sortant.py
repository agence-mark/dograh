"""Demande au fork un appel sortant vers le simulateur, par la route de l'écran.

    ./banc.sh appeler-sortant [numéro]

Le fork fait appeler le numéro par Asterisk (gabarit ``PJSIP/{number}@sipp`` de
la configuration du banc) ; SIPp en réception décroche.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("BANC_API_ADRESSE", "http://api:8000") + "/api/v1"
COURRIEL = os.environ["BANC_COMPTE_COURRIEL"]
MOT_DE_PASSE = os.environ["BANC_COMPTE_MOT_DE_PASSE"]
FICHIER_ETAT = Path(os.environ.get("BANC_FICHIER_FORK", "/resultats/fork.json"))


def appeler(chemin: str, corps: dict, jeton: str = "") -> tuple[int, str]:
    requete = urllib.request.Request(
        API + chemin,
        method="POST",
        data=json.dumps(corps).encode(),
        headers={"Content-Type": "application/json"},
    )
    if jeton:
        requete.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(requete, timeout=30) as reponse:
            return reponse.status, reponse.read().decode()
    except urllib.error.HTTPError as erreur:
        return erreur.code, erreur.read().decode()


def principal(numero: str) -> int:
    etat = json.loads(FICHIER_ETAT.read_text())
    code, corps = appeler("/auth/login", {"email": COURRIEL, "password": MOT_DE_PASSE})
    if code != 200:
        print(f"Connexion refusée : {code}", file=sys.stderr)
        return 1
    jeton = json.loads(corps)["token"]
    code, corps = appeler(
        "/telephony/initiate-call",
        {
            "workflow_id": etat["agent"],
            "phone_number": numero,
            "telephony_configuration_id": etat["configuration"],
        },
        jeton,
    )
    print(f"initiate-call -> {code} : {corps[:600]}")
    return 0 if code == 200 else 1


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1] if len(sys.argv) > 1 else "1000"))
