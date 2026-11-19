"""Coupures de parole d'un appel du fork : ce que l'appelant entend, et la file d'Asterisk.

    coupures.py <mesure> [dossier des résultats]

Une coupure : l'appelant prend la parole alors que l'agent parle encore. Pour
chacune, trois sources sont croisées, toutes à l'horloge du noyau :

- la capture réseau de SIPp (<mesure>.pcap) : quand l'appelant commence à
  parler, et quand le son de l'agent cesse d'arriver chez lui ;
- le journal des faux fournisseurs (faux.jsonl) : quand la transcription rend
  le premier mot, c'est-à-dire quand le fork apprend que l'appelant parle ;
- les relevés du relais (relais.jsonl) : la commande de vidage envoyée ou non
  par le fork, et la longueur de la file d'Asterisk, lue toutes les 100 ms.

Pour chaque coupure :

- détection : du début de parole de l'appelant au premier mot rendu ;
- son après détection : du premier mot rendu au dernier paquet sonore de
  l'agent reçu par SIPp. C'est ce que la file d'Asterisk joue encore ;
- file avant : dernière lecture de la file avant la prise de parole ;
- file après : médiane basse des lectures entre 300 et 900 ms après la prise
  de parole. L'agent s'est tu, le fork envoie son flux de silence : c'est le
  retard que portera sa prochaine phrase.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

from analyser import PORT_SON_SIPP, SEUIL_SON, lire_paquets_son
from latence import _premier, analyser as analyser_la_latence, prises_de_parole

FENETRE_AGENT_PARLAIT_NS = 100_000_000
TROU_QUI_FINIT_LE_SON_NS = 60_000_000
FENETRE_DE_VIDAGE_NS = (-50_000_000, 500_000_000)
FENETRE_DE_FILE_NS = (300_000_000, 900_000_000)


def fin_du_son(sonores: list[int], depuis_ns: int) -> int | None:
    """Le dernier paquet sonore de la suite en cours à l'instant donné."""
    fin = None
    for instant in sonores:
        if instant < depuis_ns - FENETRE_AGENT_PARLAIT_NS:
            continue
        if fin is not None and instant - fin > TROU_QUI_FINIT_LE_SON_NS:
            break
        fin = instant
    return fin


def lire(fichier: Path, debut_ns: int, fin_ns: int) -> list[dict[str, Any]]:
    if not fichier.exists():
        return []
    lignes = [json.loads(ligne) for ligne in fichier.read_text(encoding="utf-8").splitlines()]
    return [ligne for ligne in lignes if debut_ns <= ligne["t_ns"] <= fin_ns]


def analyser(mesure: str, dossier: Path) -> dict[str, Any]:
    capture = dossier / f"{mesure}.pcap"
    envoyes = lire_paquets_son(capture, port_destination=None, port_source=PORT_SON_SIPP)
    recus = lire_paquets_son(capture, port_destination=PORT_SON_SIPP)
    instants = [p.t_ns for p in envoyes + recus]
    debut, fin = min(instants), max(instants)
    faux = lire(dossier / "faux.jsonl", debut, fin)
    relais = lire(dossier / "relais.jsonl", debut, fin)
    files = [r for r in relais if r["evenement"] == "file" and r["blocs"] is not None]
    vidages = [r for r in relais if r["evenement"] == "fork_dit" and "FLUSH_MEDIA" in r["texte"]]
    sonores = [p.t_ns for p in recus if p.niveau >= SEUIL_SON]
    retours = {
        tour["tour"]: tour.get("retour") for tour in analyser_la_latence(mesure, dossier)["tours"]
    }

    coupures = []
    for rang, parole in enumerate(prises_de_parole(envoyes), start=1):
        agent_parlait = any(
            parole.debut_ns - FENETRE_AGENT_PARLAIT_NS < instant <= parole.debut_ns
            for instant in sonores
        )
        if not agent_parlait:
            continue
        mot = _premier(
            faux, parole.debut_ns - 1, service="transcription", evenement="premier_mot_rendu"
        )
        fin_son = fin_du_son(sonores, parole.debut_ns)
        if mot is None or fin_son is None:
            continue
        vidage = next(
            (
                v
                for v in vidages
                if FENETRE_DE_VIDAGE_NS[0] <= v["t_ns"] - mot["t_ns"] <= FENETRE_DE_VIDAGE_NS[1]
            ),
            None,
        )
        avant = [f["blocs"] for f in files if f["t_ns"] <= parole.debut_ns]
        apres = [
            f["blocs"]
            for f in files
            if FENETRE_DE_FILE_NS[0] <= f["t_ns"] - parole.debut_ns <= FENETRE_DE_FILE_NS[1]
        ]
        coupures.append(
            {
                "coupure": len(coupures) + 1,
                "prise_de_parole": rang,
                "detection_ms": round((mot["t_ns"] - parole.debut_ns) / 1e6, 1),
                "vidage_envoye": vidage is not None,
                "vidage_apres_detection_ms": None
                if vidage is None
                else round((vidage["t_ns"] - mot["t_ns"]) / 1e6, 1),
                "son_apres_detection_ms": round((fin_son - mot["t_ns"]) / 1e6, 1),
                "file_avant_blocs": avant[-1] if avant else None,
                "file_apres_blocs": statistics.median_low(apres) if apres else None,
                "lectures_de_file_apres": apres,
                "retour_de_la_reponse_suivante_ms": retours.get(rang),
            }
        )
    return {
        "mesure": mesure,
        "commandes_de_vidage_du_fork": len(vidages),
        "lectures_de_file": len(files),
        "file_toutes_les_secondes": [f["blocs"] for f in files[::10]],
        "coupures": coupures,
    }


def afficher(resultat: dict[str, Any]) -> None:
    print(
        f"Mesure {resultat['mesure']} : {len(resultat['coupures'])} coupure(s) de parole, "
        f"{resultat['commandes_de_vidage_du_fork']} commande(s) de vidage envoyée(s) par le fork, "
        f"{resultat['lectures_de_file']} lectures de la file"
    )
    colonnes = (
        ("coupure", 7),
        ("detection_ms", 12),
        ("vidage_envoye", 13),
        ("son_apres_detection_ms", 22),
        ("file_avant_blocs", 16),
        ("file_apres_blocs", 16),
        ("retour_de_la_reponse_suivante_ms", 32),
    )
    print("  ".join(f"{nom:>{largeur}}" for nom, largeur in colonnes))
    for coupure in resultat["coupures"]:
        print("  ".join(f"{coupure[nom]!s:>{largeur}}" for nom, largeur in colonnes))
    print("File d'Asterisk, une lecture par seconde (blocs de 20 ms) :")
    print(" ", resultat["file_toutes_les_secondes"])


def principal(arguments: list[str]) -> int:
    if not arguments:
        print(__doc__, file=sys.stderr)
        return 1
    dossier = Path(arguments[1] if len(arguments) > 1 else "/resultats")
    resultat = analyser(arguments[0], dossier)
    (dossier / f"{arguments[0]}.coupures.json").write_text(
        json.dumps(resultat, ensure_ascii=False, indent=1)
    )
    afficher(resultat)
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
