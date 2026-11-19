"""Latence côté appelant, tour par tour, lue sur la capture réseau de SIPp.

    latence.py <mesure> [dossier des résultats]

La mesure : de la fin de parole de l'appelant (dernier paquet sonore envoyé par
SIPp) au premier paquet sonore de l'agent reçu par SIPp. Les deux instants sont
lus dans la même capture, prise dans le conteneur SIPp : une seule horloge, et
rien de ce que le fork dit de lui-même.

Quand le journal des faux fournisseurs est là (faux.jsonl, même horloge), chaque
tour est découpé en sept temps, dont la somme est la latence mesurée :

- aller : du dernier paquet sonore envoyé à sa réception par la transcription
  (Asterisk, puis l'entrée du fork) ;
- fin de tour : la transcription attend le silence et rend la fin de tour ;
- fork avant le modèle : de la fin de tour à la requête reçue par le modèle ;
- modèle : de la requête au premier morceau de la passe qui parle (toutes les
  passes d'un tour à outil comprises) ;
- fork avant la voix : du premier morceau au texte reçu par la voix ;
- voix : du texte au premier son rendu ;
- retour : du premier son rendu à son arrivée chez SIPp (la sortie du fork, puis
  Asterisk).

Quand l'analyse du run est là (<mesure>.analyse.json, relevée par
fork/lire_analyse.py), la mesure M2 du chronomètre du fork est mise à côté.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analyser import PORT_SON_SIPP, SEUIL_SON, Paquet, lire_paquets_son

# Deux prises de parole de l'appelant sont séparées par au moins ce silence.
SILENCE_ENTRE_DEUX_PAROLES_NS = 100_000_000
# L'agent « parlait encore » s'il a envoyé du son dans cette fenêtre avant la
# fin de parole de l'appelant : le tour est alors une coupure de parole, pas une
# réponse, et il n'est pas mesuré.
FENETRE_AGENT_PARLAIT_NS = 100_000_000
TEMPS = (
    "aller",
    "fin_de_tour",
    "fork_avant_modele",
    "modele",
    "fork_avant_voix",
    "voix",
    "retour",
)


@dataclass(frozen=True)
class Parole:
    debut_ns: int
    fin_ns: int


def prises_de_parole(envoyes: list[Paquet]) -> list[Parole]:
    """Les suites de paquets sonores envoyés par l'appelant."""
    paroles: list[Parole] = []
    debut = fin = 0
    for paquet in envoyes:
        if paquet.niveau < SEUIL_SON:
            continue
        if debut and paquet.t_ns - fin > SILENCE_ENTRE_DEUX_PAROLES_NS:
            paroles.append(Parole(debut, fin))
            debut = 0
        if not debut:
            debut = paquet.t_ns
        fin = paquet.t_ns
    if debut:
        paroles.append(Parole(debut, fin))
    return paroles


def mesurer_les_tours(
    envoyes: list[Paquet], recus: list[Paquet]
) -> list[dict[str, Any]]:
    paroles = prises_de_parole(envoyes)
    sonores = [paquet.t_ns for paquet in recus if paquet.niveau >= SEUIL_SON]
    fin_de_capture = max((p.t_ns for p in envoyes + recus), default=0)
    tours = []
    for rang, parole in enumerate(paroles):
        suivante = (
            paroles[rang + 1].debut_ns if rang + 1 < len(paroles) else fin_de_capture
        )
        agent_parlait = any(
            parole.fin_ns - FENETRE_AGENT_PARLAIT_NS < instant <= parole.fin_ns
            for instant in sonores
        )
        reponse = next((t for t in sonores if parole.fin_ns < t < suivante), None)
        tours.append(
            {
                "tour": rang + 1,
                "fin_de_parole_ns": parole.fin_ns,
                "premier_son_ns": reponse,
                "agent_parlait": agent_parlait,
                "latence_ms": None
                if reponse is None or agent_parlait
                else round((reponse - parole.fin_ns) / 1e6, 1),
            }
        )
    return tours


def _premier(
    evenements: list[dict[str, Any]], apres_ns: int, **criteres: Any
) -> dict | None:
    for evenement in evenements:
        if evenement["t_ns"] > apres_ns and all(
            evenement.get(cle) == valeur for cle, valeur in criteres.items()
        ):
            return evenement
    return None


def decouper(tour: dict[str, Any], journal: list[dict[str, Any]]) -> dict[str, Any]:
    """Les sept temps d'un tour, lus dans le journal des faux fournisseurs."""
    fin_de_parole, premier_son = tour["fin_de_parole_ns"], tour["premier_son_ns"]
    # Le silence vu par la transcription pour CE tour : le premier après la fin de parole.
    silence = _premier(journal, fin_de_parole - 1, evenement="premier_silence")
    if silence is None or premier_son is None:
        return {}
    fin_de_tour = _premier(journal, silence["t_ns"] - 1, evenement="fin_de_tour_rendue")
    if fin_de_tour is None:
        return {}
    texte = _premier(
        journal, fin_de_tour["t_ns"], service="voix", evenement="texte_recu"
    )
    if texte is None or texte["t_ns"] > premier_son:
        return {}
    son = _premier(
        journal,
        texte["t_ns"] - 1,
        service="voix",
        evenement="premier_son_rendu",
        connexion=texte["connexion"],
    )
    passes = [
        e
        for e in journal
        if e["service"] == "modele"
        and e["evenement"] == "requete_recue"
        and fin_de_tour["t_ns"] < e["t_ns"] < texte["t_ns"]
    ]
    if son is None or not passes:
        return {}
    morceau = _premier(
        journal,
        passes[-1]["t_ns"] - 1,
        evenement="premier_morceau_rendu",
        numero=passes[-1]["numero"],
    )
    if morceau is None:
        return {}
    bornes = [
        fin_de_parole,
        silence["dernier_son_ns"],
        fin_de_tour["t_ns"],
        passes[0]["t_ns"],
        morceau["t_ns"],
        texte["t_ns"],
        son["t_ns"],
        premier_son,
    ]
    temps = {
        nom: round((bornes[rang + 1] - bornes[rang]) / 1e6, 1)
        for rang, nom in enumerate(TEMPS)
    }
    return {"passes_du_modele": len(passes), **temps}


def lire_journal(fichier: Path, debut_ns: int, fin_ns: int) -> list[dict[str, Any]]:
    if not fichier.exists():
        return []
    evenements = [
        json.loads(ligne) for ligne in fichier.read_text(encoding="utf-8").splitlines()
    ]
    return [e for e in evenements if debut_ns <= e["t_ns"] <= fin_ns]


def chronometre_du_fork(fichier: Path) -> list[dict[str, Any]]:
    """Les tours que le chronomètre du fork a mesurés, dans l'ordre, avec ses
    étapes en millisecondes depuis ce qu'il appelle le dernier mot de l'appelant."""
    if not fichier.exists():
        return []
    analyse = json.loads(fichier.read_text(encoding="utf-8")).get("analyse") or {}
    tours = (analyse.get("chrono") or {}).get("turns") or []
    return [
        {
            nom: None if valeur is None else round(valeur * 1000, 1)
            for nom, valeur in (tour.get("stages") or {}).items()
        }
        for tour in tours
        if tour.get("measured")
    ]


def resume(valeurs: list[float]) -> dict[str, float] | None:
    """Minimum, médiane basse (celle du fork) et maximum."""
    if not valeurs:
        return None
    return {
        "n": len(valeurs),
        "min": min(valeurs),
        "mediane": statistics.median_low(valeurs),
        "max": max(valeurs),
    }


def analyser(mesure: str, dossier: Path) -> dict[str, Any]:
    capture = dossier / f"{mesure}.pcap"
    envoyes = lire_paquets_son(
        capture, port_destination=None, port_source=PORT_SON_SIPP
    )
    recus = lire_paquets_son(capture, port_destination=PORT_SON_SIPP)
    tours = mesurer_les_tours(envoyes, recus)
    instants = [p.t_ns for p in envoyes + recus]
    journal = (
        lire_journal(dossier / "faux.jsonl", min(instants), max(instants))
        if instants
        else []
    )
    chrono = chronometre_du_fork(dossier / f"{mesure}.analyse.json")
    for tour in tours:
        tour.update(decouper(tour, journal) if tour["latence_ms"] is not None else {})
    # Le chronomètre du fork ne compte que les tours qu'il a su mesurer : on ne
    # l'accole aux tours de la capture que si les deux listes ont la même longueur.
    mesures = [tour for tour in tours if tour["latence_ms"] is not None]
    if chrono and len(chrono) == len(mesures):
        for tour, etapes in zip(mesures, chrono, strict=True):
            tour["chronometre_du_fork"] = etapes
            tour["m2_du_fork_ms"] = etapes["first_sound"]
            tour["hors_m2_ms"] = round(tour["latence_ms"] - etapes["first_sound"], 1)
    return {
        "mesure": mesure,
        "paquets_envoyes": len(envoyes),
        "paquets_recus": len(recus),
        "tours": tours,
        "tours_du_chronometre_du_fork": len(chrono),
        "resume": {
            nom: resume([tour[nom] for tour in mesures if tour.get(nom) is not None])
            for nom in ("latence_ms", *TEMPS, "m2_du_fork_ms", "hors_m2_ms")
        },
    }


def afficher(resultat: dict[str, Any]) -> None:
    colonnes = ("latence_ms", *TEMPS, "passes_du_modele", "m2_du_fork_ms", "hors_m2_ms")
    print(f"Mesure {resultat['mesure']} : {len(resultat['tours'])} prise(s) de parole")
    print("tour  " + "  ".join(f"{nom[:17]:>17}" for nom in colonnes))
    for tour in resultat["tours"]:
        if tour["latence_ms"] is None:
            raison = (
                "l'agent parlait encore" if tour["agent_parlait"] else "aucune réponse"
            )
            print(f"{tour['tour']:>4}  non mesuré : {raison}")
            continue
        print(
            f"{tour['tour']:>4}  "
            + "  ".join(f"{tour.get(nom, ''):>17}" for nom in colonnes)
        )
    for nom, valeurs in resultat["resume"].items():
        if valeurs:
            print(
                f"{nom:>20} : n={valeurs['n']}  min {valeurs['min']}  "
                f"médiane {valeurs['mediane']}  max {valeurs['max']}"
            )


def principal(arguments: list[str]) -> int:
    if not arguments:
        print(__doc__, file=sys.stderr)
        return 1
    dossier = Path(arguments[1] if len(arguments) > 1 else "/resultats")
    resultat = analyser(arguments[0], dossier)
    (dossier / f"{arguments[0]}.latence.json").write_text(
        json.dumps(resultat, ensure_ascii=False, indent=1)
    )
    afficher(resultat)
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
