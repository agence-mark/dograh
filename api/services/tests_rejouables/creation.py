"""[.mark] Lot H : créer un test rejouable depuis un run.

Source unique : le journal du run (``logs.realtime_feedback_events``), le même pour un appel et pour une
session clavier. On le coupe juste avant la ``rang``-ième réplique de la personne (le tour fautif, de 1 à N) :

* l'historique = les messages avant ce tour (deux paroles de suite du même côté n'en font qu'une, comme
  l'agrégateur du tour) ; seul le texte est gardé (appels d'outils et prompts ne sont pas rejoués : le
  prompt de l'étape est celui de l'agent rejoué) ;
* l'étape = la dernière transition avant le tour ;
* la fiche = la fiche FINALE du run, remise dans l'état d'avant le tour : chaque champ écrit au journal de
  la fiche est vidé puis réécrit avec les seules écritures des tours précédents (``tour`` < rang) ; les
  traces des modules, le parcours et les clés de fin d'appel sont ramenés à ce moment.

Limite connue : un journal de fiche sans numéro de tour ne peut pas être situé ; ses écritures sont alors
écartées (la fiche restaurée est plus vide que l'originale, jamais plus remplie).
"""

from __future__ import annotations

import copy
from typing import Any

from api.db import db_client
from api.services.groupe.parcours import rendre_le_parcours
from api.services.pipecat.realtime_feedback_events import (
    realtime_feedback_event_sort_key,
)
from api.services.tests_rejouables.modele import (
    ErreurTestRejouable,
    TestRejouable,
    valider_critere,
)

TYPE_USER = "rtf-user-transcription"
TYPE_BOT = "rtf-bot-text"
TYPE_ETAPE = "rtf-node-transition"
# Ce que l'appel écrit à sa fin : n'existe pas encore au tour fautif.
CLES_DE_FIN = ("call_disposition", "mapped_call_disposition", "call_status", "call_tags", "trace_url")
# Traces des modules : listes d'entrées portant le numéro de tour de la personne.
TRACES = (
    "communes_verifiees",
    "communes_ecartees",
    "voies_verifiees",
    "epellations_lues",
    "nombres_lus",
    "lexique_reconnu",
)


def _suite_du_journal(evenements: list[dict[str, Any]]) -> list[tuple]:
    """Messages et étapes dans l'ordre. ('msg', role, texte) | ('etape', id, nom, agent)."""
    suite: list[tuple] = []
    for ev in sorted(evenements or [], key=realtime_feedback_event_sort_key):
        genre = ev.get("type")
        p = ev.get("payload") or {}
        if genre == TYPE_USER:
            texte = str(p.get("text") or "").strip()
            if p.get("final") and texte:
                suite.append(("msg", "user", texte))
        elif genre == TYPE_BOT:
            texte = str(p.get("text") or "").strip()
            if texte:
                suite.append(("msg", "assistant", texte))
        elif genre == TYPE_ETAPE:
            suite.append(
                (
                    "etape",
                    p.get("node_id") or ev.get("node_id"),
                    p.get("node_name") or ev.get("node_name"),
                    p.get("agent"),
                )
            )
    # Deux paroles de suite du même côté n'en font qu'une.
    fusionnee: list[tuple] = []
    for entree in suite:
        if entree[0] == "msg" and fusionnee and fusionnee[-1][0] == "msg" and fusionnee[-1][1] == entree[1]:
            fusionnee[-1] = ("msg", entree[1], f"{fusionnee[-1][2]} {entree[2]}")
            continue
        fusionnee.append(entree)
    return fusionnee


def fiche_avant_le_tour(
    contexte_final: dict[str, Any],
    rang: int,
    etapes_avant: list[tuple],
) -> dict[str, Any]:
    """La fiche du run remise dans l'état d'avant le ``rang``-ième message de la personne."""
    fiche = copy.deepcopy(contexte_final or {})
    for cle in CLES_DE_FIN:
        fiche.pop(cle, None)
    journal = [e for e in fiche.get("fiche_journal") or [] if isinstance(e, dict)]
    champs = {e["champ"] for e in journal if e.get("champ")}
    etat = fiche.get("fiche_etat") if isinstance(fiche.get("fiche_etat"), dict) else {}
    extraites = fiche.get("extracted_variables")
    extraites = extraites if isinstance(extraites, dict) else {}
    for champ in champs:
        fiche.pop(champ, None)
        etat.pop(champ, None)
        extraites.pop(champ, None)
    gardees = [e for e in journal if isinstance(e.get("tour"), int) and e["tour"] < rang]
    for e in gardees:
        if e.get("statut") == "ecrit" and e.get("champ"):
            fiche[e["champ"]] = e.get("valeur")
            extraites[e["champ"]] = e.get("valeur")
            etat[e["champ"]] = {"sure": bool(e.get("sure")), "source": e.get("source")}
    if journal:
        fiche["fiche_journal"] = gardees
    if "fiche_etat" in fiche or etat:
        fiche["fiche_etat"] = etat
    if "extracted_variables" in fiche or extraites:
        fiche["extracted_variables"] = extraites
    for cle in TRACES:
        if isinstance(fiche.get(cle), list):
            fiche[cle] = [
                t
                for t in fiche[cle]
                if not (isinstance(t, dict) and isinstance(t.get("tour"), int) and t["tour"] >= rang)
            ]
    fiche["tour_appelant"] = rang - 1
    # Le parcours : une entrée par étape distincte de suite, comme le moteur les note.
    distinctes: list[tuple] = []
    for e in etapes_avant:
        cle = (e[3], e[2])
        if not distinctes or distinctes[-1][:2] != cle:
            distinctes.append((*cle, e[1]))
    fiche["nodes_visited"] = list(dict.fromkeys(e[1] for e in distinctes if e[1]))
    if isinstance(fiche.get("parcours_etapes"), list):
        fiche["parcours_etapes"] = fiche["parcours_etapes"][: len(distinctes)]
        fiche["parcours"] = rendre_le_parcours(fiche["parcours_etapes"])
    return fiche


def couper_au_tour(
    evenements: list[dict[str, Any]],
    contexte_final: dict[str, Any],
    rang: int,
    nom_de_l_agent: str | None = None,
) -> dict[str, Any]:
    """Historique, étape, fiche et réplique du tour ``rang``. Lève ``ErreurTestRejouable``."""
    if not isinstance(rang, int) or rang < 1:
        raise ErreurTestRejouable("le rang du tour fautif commence à 1")
    suite = _suite_du_journal(evenements)
    vus = 0
    coupe = None
    for i, entree in enumerate(suite):
        if entree[0] == "msg" and entree[1] == "user":
            vus += 1
            if vus == rang:
                coupe = i
                break
    if coupe is None:
        raise ErreurTestRejouable(
            f"le run n'a que {vus} réplique(s) de la personne : le tour {rang} n'existe pas"
        )
    avant = suite[:coupe]
    etapes = [e for e in avant if e[0] == "etape"]
    etape = None
    if etapes:
        _, node_id, node_nom, agent = etapes[-1]
        if agent and nom_de_l_agent and agent != nom_de_l_agent:
            raise ErreurTestRejouable(
                f"à ce tour l'appel est chez l'agent « {agent} » (passation) : seul l'agent du run "
                "peut être rejoué, ce cas n'est pas pris en charge"
            )
        etape = {"id": node_id, "nom": node_nom, "agent": agent}
    return {
        "historique": [{"role": e[1], "texte": e[2]} for e in avant if e[0] == "msg"],
        "etape": etape,
        "fiche": fiche_avant_le_tour(contexte_final, rang, etapes),
        "replique": suite[coupe][2],
    }


async def creer_depuis_un_run(
    run_id: int,
    organisation_id: int,
    rang: int,
    critere: dict[str, Any],
    nom: str,
    description: str = "",
) -> TestRejouable:
    """Lit le run (organisation vérifiée) et rend le test. Ne modifie rien en base."""
    valider_critere(critere)
    run, organisation_du_run = await db_client.get_workflow_run_with_context(run_id)
    # Un run d'une autre organisation est traité comme introuvable (pas de fuite d'existence).
    if run is None or organisation_du_run != organisation_id:
        raise ErreurTestRejouable(
            f"run {run_id} introuvable dans l'organisation {organisation_id}"
        )
    journal = (run.logs or {}).get("realtime_feedback_events") or []
    if not journal:
        raise ErreurTestRejouable(f"run {run_id} : aucun journal de conversation à rejouer")
    nom_agent = getattr(getattr(run, "workflow", None), "name", None)
    coupe = couper_au_tour(journal, run.gathered_context or {}, rang, nom_agent)
    return TestRejouable(
        nom=nom,
        description=description,
        organisation_id=organisation_id,
        source={"run_id": run_id, "rang": rang, "agent_id": run.workflow_id},
        etape=coupe["etape"],
        historique=coupe["historique"],
        fiche=coupe["fiche"],
        replique=coupe["replique"],
        critere=critere,
    )
