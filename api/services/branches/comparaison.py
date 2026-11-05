"""[.mark] Partie 3, SA-L3c (05 § 12, 18) : « Comparer en duel », deux branches ou deux versions face à face.

Un côté se dit ``branche:<id>`` (sa version en ligne, ses appels) ou ``version:<numéro>`` (une version de la principale ou d'une branche).
Les chiffres sont ceux de la page Qualité (``boucle.qualite._resume``, mêmes définitions, mêmes vrais appels, jamais les essais) : AUCUNE
donnée nouvelle. Lecture seule, en parallèle : les appels de la fenêtre, les branches et leurs versions, les deux configurations.

* part du trafic (une branche seulement), appels, résolution, transferts, note du juge, coût par appel, latence médiane ;
* la **meilleure valeur** de chaque ligne qui a un sens (résolution et note : plus haut ; coût et latence : plus bas) ; les appels et
  les transferts n'ont pas de meilleur ;
* un **verdict** d'une ligne (``gagnant`` : gauche, droite, égalité, ou insuffisant sous ``APPELS_MIN`` appels d'un côté) ; le texte
  est dit par l'écran, dans sa langue ;
* la **différence de configuration** champ par champ (les mêmes champs que la fusion), à plat : l'écran la groupe par famille.
"""

from __future__ import annotations

import asyncio
from typing import Any

from api.db import db_client
from api.db.branches_client import ErreurDeBranche
from api.services.branches import champs
from api.services.boucle import qualite

APPELS_MIN = 5
JOURS_MAX = 90

# (clé, plus c'est haut mieux c'est : True, plus c'est bas : False, sans avis : None)
MESURES: tuple[tuple[str, bool | None], ...] = (
    ("part", None),
    ("appels", None),
    ("resolution", True),
    ("transferts", None),
    ("note", True),
    ("cout", False),
    ("latence", False),
)


def _lire_un_cote(brut: str) -> tuple[str, int]:
    genre, _, valeur = (brut or "").partition(":")
    if genre not in ("branche", "version") or not valeur.isdigit() or len(valeur) > 9:
        raise ErreurDeBranche("A side is 'branche:<id>' or 'version:<number>'", "cote")
    return genre, int(valeur)


async def _resoudre(organization_id: int, agent: Any, brut: str, branches, principales, autres) -> dict[str, Any]:
    """Le côté : son nom, les numéros de versions dont on compte les appels, la version dont on lit la configuration, sa part."""
    genre, valeur = _lire_un_cote(brut)
    principale = next(b for b in branches if b.est_principale)
    if genre == "branche":
        branche = next((b for b in branches if b.id == valeur), None)
        if branche is None:
            raise ErreurDeBranche("Branch not found", "introuvable")
        if branche.est_principale:
            tete = principale.head_definition_id or getattr(agent, "released_definition_id", None)
            versions = principales
        else:
            tete = branche.head_definition_id
            versions = [v for v in autres if v["branch_id"] == branche.id]
        if tete is None:
            raise ErreurDeBranche("This branch has no version to compare", "sans_version")
        numeros = {v["version_number"] for v in versions}
        liste = [v for v in versions if v["id"] == tete]
        numero = liste[0]["version_number"] if liste else None
        return {"type": "branche", "id": branche.id, "nom": branche.nom, "version": numero, "definition": tete, "numeros": numeros, "part": branche.part_trafic}
    trouvee = next((v for v in principales if v["version_number"] == valeur), None) or next((v for v in autres if v["version_number"] == valeur), None)
    if trouvee is None:
        raise ErreurDeBranche("Version not found", "introuvable")
    branche = next((b for b in branches if b.id == trouvee.get("branch_id")), principale)
    return {"type": "version", "id": valeur, "nom": branche.nom, "version": valeur, "definition": trouvee["id"], "numeros": {valeur}, "part": None}


def _chiffres(cote: dict[str, Any], lignes: list[dict[str, Any]]) -> dict[str, Any]:
    ses_appels = [ligne for ligne in lignes if ligne.get("version") in cote["numeros"]]
    r = qualite._resume(ses_appels)  # noqa: SLF001 -- les chiffres de la page Qualité, au mot près
    par_appel = round(r["cout"] / r["appels_mesures"], 4) if r["cout"] is not None and r["appels_mesures"] else None
    return {
        "part": cote["part"],
        "appels": r["appels"],
        "resolution": r["part_issue"],
        "transferts": r["part_transferts"],
        "note": r["note"],
        "cout": par_appel,
        "latence": r["reponse_mediane"],
        "_juges": r["juges"],
        "_mesures": r["appels_mesures"],
    }


def _lignes(gauche: dict[str, Any], droite: dict[str, Any]) -> list[dict[str, Any]]:
    sortie = []
    for cle, haut in MESURES:
        g, d = gauche[cle], droite[cle]
        if cle == "part" and g is None and d is None:
            continue
        ecart = round(d - g, 4) if isinstance(g, (int, float)) and isinstance(d, (int, float)) else None
        meilleur = None
        if haut is not None and ecart not in (None, 0):
            meilleur = ("droite" if d > g else "gauche") if haut else ("droite" if d < g else "gauche")
        sortie.append({"cle": cle, "gauche": g, "droite": d, "ecart": ecart, "meilleur": meilleur})
    return sortie


def _verdict(gauche: dict[str, Any], droite: dict[str, Any], lignes: list[dict[str, Any]]) -> dict[str, Any]:
    if gauche["appels"] < APPELS_MIN or droite["appels"] < APPELS_MIN:
        return {"gagnant": "insuffisant", "pour_gauche": [], "pour_droite": []}
    pour_gauche = [ligne["cle"] for ligne in lignes if ligne["meilleur"] == "gauche"]
    pour_droite = [ligne["cle"] for ligne in lignes if ligne["meilleur"] == "droite"]
    gagnant = "egalite" if len(pour_gauche) == len(pour_droite) else ("gauche" if len(pour_gauche) > len(pour_droite) else "droite")
    return {"gagnant": gagnant, "pour_gauche": pour_gauche, "pour_droite": pour_droite}


def _configuration(avant: dict[str, Any], apres: dict[str, Any]) -> list[dict[str, Any]]:
    """La différence de configuration à plat : tout champ qui n'est pas identique des deux côtés (``avant`` = la gauche)."""
    a = champs.Etat(avant["graphe"], avant["reglages"], avant["variables"])
    b = champs.Etat(apres["graphe"], apres["reglages"], apres["variables"])
    return [
        {"cle": ligne["cle"], "famille": ligne["famille"], "libelle": ligne["libelle"], "avant": ligne["cible"], "apres": ligne["source"]}
        for ligne in champs.comparer(a, b, a)
    ]


async def comparer(organization_id: int, agent: Any, gauche: str, droite: str, jours: int) -> dict[str, Any]:
    jours = max(1, min(int(jours), JOURS_MAX))
    # Une lecture par donnée, toutes ensemble : les appels de la fenêtre, les branches, les deux historiques de versions.
    lignes, branches, principales, autres = await asyncio.gather(
        db_client.runs_pour_la_qualite(organization_id, jours=jours, workflow_id=agent.id),
        db_client.lister_les_branches(organization_id, agent.id),
        db_client.get_workflow_version_summaries(agent.id, organization_id),
        db_client.versions_des_branches(organization_id, agent.id),
    )
    principales = [{**v, "branch_id": None} for v in principales]
    g = await _resoudre(organization_id, agent, gauche, branches, principales, autres)
    d = await _resoudre(organization_id, agent, droite, branches, principales, autres)
    contenus = await db_client.contenus_de_definitions(organization_id, agent.id, [g["definition"], d["definition"]])
    if g["definition"] not in contenus or d["definition"] not in contenus:
        raise ErreurDeBranche("Version not found", "introuvable")
    chiffres_g, chiffres_d = _chiffres(g, lignes), _chiffres(d, lignes)
    mesures = _lignes(chiffres_g, chiffres_d)
    cache = lambda cote: {k: v for k, v in cote.items() if k not in ("numeros", "definition")}  # noqa: E731
    return {
        "jours": jours,
        "appels_min": APPELS_MIN,
        "gauche": cache(g),
        "droite": cache(d),
        "mesures": mesures,
        "verdict": _verdict(chiffres_g, chiffres_d, mesures),
        "configuration": _configuration(contenus[g["definition"]], contenus[d["definition"]]),
    }
