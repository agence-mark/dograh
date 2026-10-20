"""La mesure de latence du labo, reprise à l'identique côté serveur (.mark).

Chantier langwatch-et-fenetre-du-run, décision L1 : **une seule définition des mesures**.
Ce module est la traduction ligne à ligne de ``Labo-agent-vocal/agents/outils/mesures-run.mjs``
(la définition du 15/09, enrichie le 17/09, le 03/10 et les 04-05/10). La fenêtre du run et les
outils du labo doivent rendre les MÊMES chiffres : ``test_analyse_run_equivalence.py`` le
vérifie sur un corpus de runs passés, contre ce que l'outil du labo a calculé.

⛔ Ne rien « améliorer » ici : un écart de définition, même juste, casse la comparaison avec
toutes les mesures passées. Les lectures plus fines (passe après une porte, après une prise de
notes, tours non mesurés) vivent dans ``analyse.py``.

Deux subtilités de JavaScript reproduites exprès :
- ``Date.parse`` tronque à la milliseconde : les durées se calculent en millisecondes entières ;
- une date illisible donne ``NaN``, que JSON écrit ``null`` : ici ``float("nan")``.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

_LLM = re.compile(r"LLMService")
_TTS = re.compile(r"TTSService")


def _ms(horodatage: Any) -> float:
    """Millisecondes depuis l'époque, tronquées comme ``Date.parse`` ; ``nan`` si illisible."""
    if not isinstance(horodatage, str):
        return math.nan
    texte = horodatage.strip()
    if texte.endswith("Z"):
        texte = texte[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(texte)
    except ValueError:
        return math.nan
    if moment.tzinfo is None:
        # Date.parse lit une date-heure ISO sans fuseau comme une heure LOCALE ; nos runs
        # portent toujours un fuseau. Sans fuseau, on ne devine pas.
        return math.nan
    secondes = int(moment.timestamp())
    return secondes * 1000 + moment.microsecond // 1000


def _cle_numerique(cle: Any) -> int | None:
    """Une clé de tour comme JavaScript la range dans un objet : entier canonique ou non."""
    if isinstance(cle, bool):
        return None
    if isinstance(cle, int) and cle >= 0:
        return cle
    return None


def _ordre_des_tours(evenements: list[dict]) -> list[tuple[Any, list[dict]]]:
    """``Object.entries`` sur ``tours[e.turn]`` : entiers croissants d'abord, puis le reste
    dans l'ordre d'apparition (c'est l'ordre des clés d'un objet JavaScript)."""
    tours: dict[str, list[dict]] = {}
    cles: dict[str, Any] = {}
    for evenement in evenements:
        cle = evenement.get("turn")
        texte = "undefined" if cle is None else str(cle)
        tours.setdefault(texte, []).append(evenement)
        cles.setdefault(texte, cle)
    entiers = sorted(
        (c for c in tours if _cle_numerique(cles[c]) is not None), key=lambda c: int(c)
    )
    autres = [c for c in tours if _cle_numerique(cles[c]) is None]
    return [(cles[c], tours[c]) for c in entiers + autres]


def _nombre(cle: Any) -> float:
    """``Number(t)`` sur une clé d'objet JavaScript."""
    if cle is None:
        return math.nan
    try:
        return float(cle)
    except (TypeError, ValueError):
        return math.nan


def mesurer_run(run: dict) -> dict:
    """Traduction de ``mesurerRun(run)`` : mêmes clés, mêmes valeurs."""
    entree = 0
    cache = 0
    for usage in ((run.get("usage_info") or {}).get("llm") or {}).values():
        usage = usage or {}
        entree += usage.get("prompt_tokens") or 0
        cache += usage.get("cache_read_input_tokens") or 0

    contexte_initial = run.get("initial_context") or {}
    estampille = contexte_initial.get("runtime_configuration") or {}
    mode = estampille.get("fiche_mode_de_note")
    m: dict[str, Any] = {
        "id": run.get("id"),
        "agent": run.get("workflow_id"),
        "entree": entree,
        "cache": cache,
        "parle": [],
        "porte": [],
        "premierTour": [],
        "tour": [],
        "voix": [],
        "passes": [],
        "detailTours": [],
        "mode": mode,
        "postScriptums": list(
            (run.get("gathered_context") or {}).get("post_scriptums") or []
        ),
        "portesParlees": estampille.get("portes_dans_la_reponse") is True,
        "passesPorte": [],
        "tourPorte": [],
    }

    evenements = ((run.get("logs") or {}).get("realtime_feedback_events")) or []
    for cle, es in _ordre_des_tours(evenements):
        numero = _nombre(cle)
        details = [
            e.get("payload") for e in es if e.get("type") == "mark-latency-breakdown"
        ]
        if not details:
            continue
        detail = details[-1] or {}
        ttfb = detail.get("ttfb") or []
        modele = [
            x.get("duration_secs")
            for x in ttfb
            if _LLM.search(str(x.get("processor", "undefined")))
        ]
        if not modele:
            continue
        voix_du_tour = [
            x.get("duration_secs")
            for x in ttfb
            if _TTS.search(str(x.get("processor", "undefined")))
        ]
        m["voix"].extend(voix_du_tour)
        nb_portes = sum(1 for e in es if e.get("type") == "rtf-function-call-start")
        parle_du_tour: list = []
        for i, duree in enumerate(modele):
            if numero == 2 and i == 0:
                m["premierTour"].append(duree)
                parle_du_tour.append(duree)
            elif i < nb_portes:
                m["porte"].append(duree)
            else:
                m["parle"].append(duree)
                parle_du_tour.append(duree)
        fins = [
            e
            for e in es
            if e.get("type") == "rtf-user-transcription"
            and (e.get("payload") or {}).get("final")
        ]
        fin_parole = fins[-1] if fins else None
        reponse = next((e for e in es if e.get("type") == "rtf-bot-text"), None)
        tour = None
        if fin_parole and reponse:
            tour = (
                _ms((reponse.get("payload") or {}).get("timestamp"))
                - _ms((fin_parole.get("payload") or {}).get("end_timestamp"))
            ) / 1000
            m["tour"].append(tour)
        if numero != 1:
            m["passes"].append(len(modele))
        change_d_etape = any(
            e.get("type") == "rtf-node-transition"
            and (e.get("payload") or {}).get("previous_node_id") is not None
            for e in es
        )
        if change_d_etape and numero != 1:
            m["passesPorte"].append(len(modele))
            if tour is not None:
                m["tourPorte"].append(tour)
        m["detailTours"].append(
            {
                "tour": numero,
                "noeud": (es[0].get("node_name") or "") if es else "",
                "passes": len(modele),
                "outils": nb_portes,
                "modeleParle": parle_du_tour[-1] if parle_du_tour else None,
                "voix": max(voix_du_tour) if voix_du_tour else None,
                "complet": tour,
            }
        )
    return m


def mediane_basse(valeurs: list) -> float | None:
    """La médiane BASSE du 15/09 (élément d'indice ``floor((n-1)/2)``), gardée pour que l'avant
    et l'après se comparent à l'identique."""
    nombres = sorted(
        v for v in valeurs if isinstance(v, (int, float)) and not math.isnan(v)
    )
    if not nombres:
        return None
    return nombres[(len(nombres) - 1) // 2]


# --------------------------------------------------------------------------- #
# Le chronomètre par tour et la mesure M2 (fiabilite-orchestration, lot 9, F8, F11)
# --------------------------------------------------------------------------- #
#
# ⛔ Cette partie est AJOUTÉE à côté de ``mesurer_run`` : ``mesurer_run`` ne change pas d'une
# virgule (l'équivalence du corpus du 05/10 le garde). Sa copie de référence est
# ``chronometreDuRun`` dans ``mesures-run.mjs`` : les deux se changent ENSEMBLE, et
# ``test_chronometre_par_tour.py`` compare leurs chiffres sur le même corpus.
#
# M1 (``mesurer_run``, « tour ») : dernier mot de l'appelant selon Soniox → PREMIER TEXTE de l'agent.
# M2 (ici, ``premierSon``) : dernier mot de l'appelant selon Soniox → PREMIER SON sorti du service
# de voix. M2 compte la voix, que M1 ne compte pas. Ce que M2 ne compte pas encore : le trajet de
# l'audio entre la voix et l'oreille (réseau, mémoire tampon du navigateur) ; la détection de voix
# sur l'enregistrement (``silences.py``) reste le contrôle indépendant.
#
# Les étapes (secondes depuis le dernier mot, tous les instants lus dans le détail de latence du
# tour ; les horodatages de Pipecat sont en secondes depuis l'époque, ceux des événements en ISO) :
#   finDeTour    la première requête du tour part au modèle (le tour de l'appelant est décidé fini)
#   requete      la requête de la passe qui parle part (égale à la précédente sans outil appelé)
#   premierMot   premier mot de cette passe
#   phrase       première phrase complète remise à la voix
#   voix         le texte part à la voix
#   premierSon   premier son sorti de la voix

ETAPES_DU_CHRONOMETRE = (
    "finDeTour",
    "requete",
    "premierMot",
    "phrase",
    "voix",
    "premierSon",
)


def _ms_epoque(secondes: Any) -> float:
    """Secondes depuis l'époque → millisecondes entières, arrondies comme ``Math.floor(x*1000+0.5)``
    (jamais ``round`` de Python, qui arrondit les demis au pair) ; ``nan`` si illisible."""
    if isinstance(secondes, bool) or not isinstance(secondes, (int, float)):
        return math.nan
    if math.isnan(secondes) or math.isinf(secondes):
        return math.nan
    return float(math.floor(secondes * 1000 + 0.5))


def _debut_plus_duree(mesure: dict) -> float:
    """``start_time + duration_secs`` en millisecondes entières ; ``nan`` sans ``start_time``
    (``??`` de JavaScript : un début à 0 reste un début)."""
    debut = mesure.get("start_time")
    if debut is None:
        return math.nan
    duree = mesure.get("duration_secs") or 0
    if isinstance(debut, bool) or not isinstance(debut, (int, float)):
        return math.nan
    return _ms_epoque(debut + duree)


def _en_secondes(fin: float, debut: float) -> float | None:
    """Une durée en secondes entre deux instants en millisecondes entières ; ``None`` si l'un
    des deux est illisible."""
    if math.isnan(fin) or math.isnan(debut):
        return None
    return (fin - debut) / 1000


def chronometre_du_run(run: dict) -> dict:
    """Traduction de ``chronometreDuRun(run)`` : une ligne par tour mesuré par M1 (un tour qui a
    un détail de latence avec un appel au modèle), et la liste des M2."""
    evenements = ((run.get("logs") or {}).get("realtime_feedback_events")) or []
    tours: list[dict] = []
    m2: list[float] = []
    for cle, es in _ordre_des_tours(evenements):
        numero = _nombre(cle)
        details = [
            e.get("payload") for e in es if e.get("type") == "mark-latency-breakdown"
        ]
        if not details:
            continue
        detail = details[-1] or {}
        ttfb = detail.get("ttfb") or []
        modele = [x for x in ttfb if _LLM.search(str(x.get("processor", "undefined")))]
        if not modele:
            continue
        ligne: dict[str, Any] = {
            "tour": numero,
            "noeud": (es[0].get("node_name") or "") if es else "",
            "mesure": False,
            "raison": None,
            "dernierMot": None,
            "passes": len(modele),
        }
        for etape in ETAPES_DU_CHRONOMETRE:
            ligne[etape] = None
        ligne["m2"] = None
        tours.append(ligne)

        fins = [
            e
            for e in es
            if e.get("type") == "rtf-user-transcription"
            and (e.get("payload") or {}).get("final")
        ]
        if not fins:
            ligne["raison"] = "no_final_transcript"
            continue
        dernier_mot = _ms((fins[-1].get("payload") or {}).get("end_timestamp"))
        if math.isnan(dernier_mot):
            ligne["raison"] = "unreadable_timestamps"
            continue
        ligne["dernierMot"] = dernier_mot
        voix = [x for x in ttfb if _TTS.search(str(x.get("processor", "undefined")))]
        if not voix:
            ligne["raison"] = "no_voice"
            continue
        debut_voix = _ms_epoque(voix[0].get("start_time"))
        son = _debut_plus_duree(voix[0])
        # La passe qui parle : la dernière requête partie avant que le texte n'arrive à la voix.
        avant = [
            x
            for x in modele
            if not math.isnan(_ms_epoque(x.get("start_time")))
            and _ms_epoque(x.get("start_time")) <= debut_voix
        ]
        parle = (avant or modele)[-1]
        debut_parle = _ms_epoque(parle.get("start_time"))
        premiere = _ms_epoque(modele[0].get("start_time"))
        agregation = detail.get("text_aggregation") or {}
        phrase = _debut_plus_duree(agregation)
        instants = {
            "finDeTour": premiere,
            "requete": debut_parle,
            "premierMot": _debut_plus_duree(parle),
            "phrase": phrase,
            "voix": debut_voix,
            "premierSon": son,
        }
        for etape, instant in instants.items():
            ligne[etape] = _en_secondes(instant, dernier_mot)
        if ligne["premierSon"] is None:
            ligne["raison"] = "unreadable_timestamps"
            continue
        ligne["mesure"] = True
        ligne["m2"] = ligne["premierSon"]
        m2.append(ligne["premierSon"])
    return {"tours": tours, "m2": m2}


def controle_des_mesures(run: dict, silence_entendu_median: float | None) -> dict:
    """M1, M2 et l'oreille, côte à côte, médianes basses (celle du 15/09). L'écart M2 → oreille
    est ce que le chronomètre ne voit pas encore (la sortie audio jusqu'à l'appelant)."""
    m1 = mediane_basse(mesurer_run(run)["tour"])
    m2 = mediane_basse(chronometre_du_run(run)["m2"])
    ecart = (
        round(silence_entendu_median - m2, 3)
        if isinstance(silence_entendu_median, (int, float)) and m2 is not None
        else None
    )
    return {
        "m1_median_secs": m1,
        "m2_median_secs": m2,
        "heard_median_secs": silence_entendu_median,
        "heard_minus_m2_secs": ecart,
    }
