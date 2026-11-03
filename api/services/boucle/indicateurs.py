"""[.mark] U8 (lot C) : les indicateurs d'un appel, CALCULÉS depuis son journal, rien d'autre n'est stocké pour eux.

Fonction pure : le journal d'événements (``logs['realtime_feedback_events']``), la fiche finale (``gathered_context``), la durée et le
coût. Le résultat est rangé dans ``annotations['boucle']['indicateurs']`` du run par l'après-appel (voir ``ingestion``), pour que la
page Qualité les agrège sans relire un journal.

* ``issue_obtenue`` : un outil a abouti, ou l'appel a été transféré (« rendez-vous, demande, transfert ») ;
* ``outils`` / ``outils_en_echec`` : appels d'outils terminés, et ceux dont le résultat dit une erreur ;
* ``transfert`` : l'appel s'est terminé par un transfert ;
* ``raccroche_avant_la_fin`` : l'appelant a raccroché sans qu'une issue ait été obtenue ;
* ``redemandes`` : l'agent a redemandé ce qu'il avait déjà (relevé commun des redites) ;
* ``impasses`` : les impasses notées par le code ; ``coupures`` : l'appelant parle pendant que l'agent parle ;
* ``latence_mediane`` / ``latence_max`` : par tour de parole, outils compris (``rtf-latency-measured``) ;
* ``tours``, ``duree``, ``cout`` ; ``motif`` : le motif d'appel classé, lu dans la fiche (liste fermée par agent).

⛔ Ne lève jamais : un journal illisible rend des indicateurs vides, jamais une panne de l'après-appel. Zéro vocabulaire métier.
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any

from loguru import logger

DISPOSITIONS_TRANSFERT = ("transfer_call", "call_transferred")
DISPOSITION_RACCROCHE = "user_hangup"
# Les champs de la fiche qui portent le motif classé ; le premier présent gagne (la liste fermée est celle du champ, PB3).
CHAMPS_MOTIF = ("motif_appel", "motif")
ECHEC_DANS_LE_RESULTAT = re.compile(r"\b(error|erreur|failed|failure|echec|échec|exception)\b", re.IGNORECASE)
MOTIF_MAX = 120


def _en_echec(resultat: Any) -> bool:
    return bool(resultat) and bool(ECHEC_DANS_LE_RESULTAT.search(str(resultat)[:200]))


def motif_de_la_fiche(contexte: dict[str, Any]) -> str | None:
    """Le motif d'appel classé : la valeur du champ de motif de la fiche (déjà restreinte à la liste fermée de l'agent)."""
    for champ in CHAMPS_MOTIF:
        valeur = contexte.get(champ)
        if isinstance(valeur, str) and valeur.strip():
            return " ".join(valeur.split())[:MOTIF_MAX]
    return None


def calculer(
    journal: list[dict[str, Any]] | None,
    contexte: dict[str, Any] | None,
    *,
    duree: float | None = None,
    cout: float | None = None,
) -> dict[str, Any]:
    try:
        return _calculer(journal or [], contexte or {}, duree, cout)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] indicateurs non calculés : {type(erreur).__name__}")
        return {}


def _calculer(journal: list[dict[str, Any]], contexte: dict[str, Any], duree: float | None, cout: float | None) -> dict[str, Any]:
    from api.services.builder.tests_agent import verdict as verdict_code
    from api.services.pipecat.realtime_feedback_events import realtime_feedback_event_sort_key

    ordonne = sorted((e for e in journal if isinstance(e, dict)), key=realtime_feedback_event_sort_key)
    latences: list[float] = []
    tours: set[Any] = set()
    outils = echecs = coupures = 0
    agent_parle = False
    for evenement in ordonne:
        genre, charge = evenement.get("type"), evenement.get("payload") or {}
        if genre == "rtf-latency-measured":
            valeur = charge.get("latency_seconds")
            if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
                latences.append(float(valeur))
        elif genre in ("rtf-user-transcription", "rtf-bot-text"):
            tours.add(evenement.get("turn", 0))
            if genre == "rtf-user-transcription" and agent_parle and str(charge.get("text") or "").strip():
                coupures += 1
        elif genre == "rtf-bot-started-speaking":
            agent_parle = True
        elif genre == "rtf-bot-stopped-speaking":
            agent_parle = False
        elif genre == "rtf-function-call-end":
            outils += 1
            if _en_echec(charge.get("result")):
                echecs += 1
    observation = verdict_code.observation_depuis_un_run(ordonne, contexte)
    disposition = str(contexte.get("call_disposition") or "")
    transfert = disposition in DISPOSITIONS_TRANSFERT
    issue_obtenue = (outils - echecs) > 0 or transfert
    impasse = contexte.get("impasse")
    impasses = impasse.get("impasses") if isinstance(impasse, dict) else 0
    return {
        "issue_obtenue": issue_obtenue,
        "outils": outils,
        "outils_en_echec": echecs,
        "transfert": transfert,
        "raccroche_avant_la_fin": disposition == DISPOSITION_RACCROCHE and not issue_obtenue,
        "redemandes": len(verdict_code.releve(observation.lignes)["redites"]),
        "impasses": impasses if isinstance(impasses, int) and not isinstance(impasses, bool) else 0,
        "coupures": coupures,
        "latence_mediane": round(median(latences), 2) if latences else None,
        "latence_max": round(max(latences), 2) if latences else None,
        "tours": len(tours),
        "duree": round(duree, 1) if isinstance(duree, (int, float)) else None,
        "cout": round(cout, 4) if isinstance(cout, (int, float)) else None,
        "motif": motif_de_la_fiche(contexte),
    }
