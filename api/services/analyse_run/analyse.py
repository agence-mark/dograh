"""L'analyse d'un run pour sa fenêtre à l'écran (.mark, chantier langwatch-et-fenetre-du-run, lot 1).

Calculée à la LECTURE depuis les données du run (décision L2) : aucune migration, et les anciens
runs s'affichent aussi. La latence reprend la définition du labo (``mesures.py``, L1) ; ce module
ajoute ce que l'outil du labo ne lit pas (passe par passe, tours non mesurés, fiche, parcours).

⛔ Aucune défaillance silencieuse (R1) : chaque bloc se calcule à part ; un bloc qui échoue rend
``{"status": "unavailable"}`` et un avertissement dans les journaux, jamais un bloc vide. Une
donnée absente du run rend ``"not_captured"`` : l'écran dit « non capté », pas « zéro ».

Les noms des clés sont en anglais (lus par l'écran) ; aucune règle métier ici : les noms des
portes et des champs de la fiche viennent de la définition de l'agent, passés par la route.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from loguru import logger

from api.services.analyse_run.mesures import _ms, mediane_basse, mesurer_run

VERSION = 1

# Le nom de l'outil de prise de notes (``fiche_au_fil_de_leau.NOM_OUTIL``), recopié pour ne pas
# importer le pipeline dans une lecture ; ``test_analyse_run.py`` vérifie qu'ils restent égaux.
OUTIL_DE_NOTE = "noter_information"

# Un tour plus lent que ce seuil est surligné (note de la fenêtre du run, bloc 2).
SEUIL_TOUR_LENT_S = 3.0
SEUIL_TOUR_RAPIDE_S = 0.8

CANAUX = {
    "smallwebrtc": "browser",
    "textchat": "keyboard",
}

OK, NON_CAPTE, INDISPONIBLE = "ok", "not_captured", "unavailable"


def _evenements(run: dict) -> list[dict]:
    return list(((run.get("logs") or {}).get("realtime_feedback_events")) or [])


def _contexte(run: dict) -> dict:
    return run.get("gathered_context") or {}


def _estampille(run: dict) -> dict:
    return (run.get("initial_context") or {}).get("runtime_configuration") or {}


def _nombre_fini(valeur: Any) -> float | None:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    return None if math.isnan(valeur) else float(valeur)


def _tours(run: dict) -> list[tuple[int | None, list[dict]]]:
    """Les événements groupés par tour, tours entiers croissants d'abord."""
    groupes: dict[Any, list[dict]] = {}
    for evenement in _evenements(run):
        groupes.setdefault(evenement.get("turn"), []).append(evenement)
    entiers = sorted(
        t for t in groupes if isinstance(t, int) and not isinstance(t, bool)
    )
    autres = [t for t in groupes if t not in entiers]
    return [(t, groupes[t]) for t in entiers + autres]


def _nature_d_un_outil(nom: str | None, portes: set[str] | None) -> str:
    if nom == OUTIL_DE_NOTE:
        return "note"
    if portes is not None and nom in portes:
        return "transition"
    return "tool" if portes is not None else "tool_or_transition"


# --------------------------------------------------------------------------- blocs


def _latence(run: dict, portes: set[str] | None) -> dict:
    tours = []
    for numero, es in _tours(run):
        details = [
            e.get("payload") or {}
            for e in es
            if e.get("type") == "mark-latency-breakdown"
        ]
        detail = details[-1] if details else None
        ttfb = (detail or {}).get("ttfb") or []
        modele = [
            x for x in ttfb if "LLMService" in str(x.get("processor", "undefined"))
        ]
        voix = [
            _nombre_fini(x.get("duration_secs"))
            for x in ttfb
            if "TTSService" in str(x.get("processor", "undefined"))
        ]
        ecoute = [
            _nombre_fini(x.get("duration_secs"))
            for x in ttfb
            if "STTService" in str(x.get("processor", "undefined"))
        ]
        outils = [
            (e.get("payload") or {}).get("function_name")
            for e in es
            if e.get("type") == "rtf-function-call-start"
        ]
        passes = []
        for i, x in enumerate(modele):
            nature = (
                _nature_d_un_outil(outils[i], portes) if i < len(outils) else "reply"
            )
            passes.append(
                {"secs": _nombre_fini(x.get("duration_secs")), "after": nature}
            )
        fins = [
            e
            for e in es
            if e.get("type") == "rtf-user-transcription"
            and (e.get("payload") or {}).get("final")
        ]
        reponse = next((e for e in es if e.get("type") == "rtf-bot-text"), None)
        silence = None
        if fins and reponse:
            silence = _nombre_fini(
                (
                    _ms((reponse.get("payload") or {}).get("timestamp"))
                    - _ms((fins[-1].get("payload") or {}).get("end_timestamp"))
                )
                / 1000
            )
        if numero == 1:
            raison = "greeting"
        elif detail is None:
            raison = "no_latency_detail"
        elif not modele:
            raison = "no_model_call"
        elif not fins:
            raison = "no_final_transcript"
        elif reponse is None:
            raison = "no_reply"
        elif silence is None:
            raison = "unreadable_timestamps"
        else:
            raison = None
        tours.append(
            {
                "turn": numero,
                "step": (es[0].get("node_name") or "") if es else "",
                "measured": raison is None,
                "not_measured_reason": raison,
                "end_of_turn_wait_secs": _nombre_fini(
                    (detail or {}).get("user_turn_secs")
                ),
                "transcription_secs": max(
                    (v for v in ecoute if v is not None), default=None
                ),
                "passes": passes,
                "voice_secs": max((v for v in voix if v is not None), default=None),
                "silence_secs": silence,
                "slow": silence is not None and silence > SEUIL_TOUR_LENT_S,
                "step_change": any(
                    e.get("type") == "rtf-node-transition"
                    and (e.get("payload") or {}).get("previous_node_id") is not None
                    for e in es
                ),
            }
        )
    if not tours:
        return {"status": NON_CAPTE, "turns": []}
    mesures = [t["silence_secs"] for t in tours if t["measured"]]
    pire = max(
        (t for t in tours if t["measured"]),
        key=lambda t: t["silence_secs"],
        default=None,
    )
    labo = mesurer_run(run)
    return {
        "status": OK,
        "turns": tours,
        "stats": {
            "measured_turns": len(mesures),
            "total_turns": len(tours),
            "median_silence_secs": mediane_basse(mesures),
            "worst_silence_secs": pire["silence_secs"] if pire else None,
            "worst_turn": pire["turn"] if pire else None,
            "share_under_threshold": (
                sum(1 for s in mesures if s <= SEUIL_TOUR_RAPIDE_S) / len(mesures)
                if mesures
                else None
            ),
            "threshold_secs": SEUIL_TOUR_RAPIDE_S,
            "median_passes": mediane_basse(labo["passes"]),
            # Les chiffres de l'outil du labo, à l'identique (L1) : médianes de la parole, de la
            # première réponse, des passes après un outil, et du tour complet.
            "lab": {
                "median_reply_model_secs": mediane_basse(labo["parle"]),
                "median_first_reply_model_secs": mediane_basse(labo["premierTour"]),
                "median_tool_pass_secs": mediane_basse(labo["porte"]),
                "median_turn_secs": mediane_basse(labo["tour"]),
                "median_voice_secs": mediane_basse(labo["voix"]),
            },
        },
    }


def _usage_par_brique(usage: dict, brique: str) -> list[dict]:
    """``"DeepgramFluxSTTService#4|||flux-general-multi": 155.4`` → service, modèle, valeur."""
    lignes = []
    for cle, valeur in (usage.get(brique) or {}).items():
        service, _, modele = str(cle).partition("|||")
        lignes.append(
            {"service": service.split("#")[0], "model": modele or None, "usage": valeur}
        )
    return lignes


def _fournisseurs(run: dict) -> dict:
    estampille = _estampille(run)
    usage = run.get("usage_info") or {}
    if not estampille and not usage:
        return {"status": NON_CAPTE}
    llm = []
    for ligne in _usage_par_brique(usage, "llm"):
        jetons = ligne["usage"] or {}
        llm.append(
            {
                "service": ligne["service"],
                "model": ligne["model"],
                "prompt_tokens": jetons.get("prompt_tokens"),
                "cached_tokens": jetons.get("cache_read_input_tokens"),
                "completion_tokens": jetons.get("completion_tokens"),
            }
        )
    return {
        "status": OK,
        "transcription": {
            "provider": estampille.get("stt_provider"),
            "model": estampille.get("stt_model"),
            "settings": estampille.get("stt_settings"),
            "usage": [
                {**ligne, "seconds": ligne.pop("usage")}
                for ligne in _usage_par_brique(usage, "stt")
            ],
        },
        "model": {
            "provider": estampille.get("llm_provider"),
            "model": estampille.get("llm_model"),
            "sampling": estampille.get("llm_sampling"),
            "note_taking_mode": estampille.get("fiche_mode_de_note"),
            "transitions_in_reply": estampille.get("portes_dans_la_reponse") is True,
            "usage": llm,
        },
        "voice": {
            "provider": estampille.get("tts_provider"),
            "model": estampille.get("tts_model"),
            "settings": estampille.get("tts_settings"),
            "usage": [
                {**ligne, "characters": ligne.pop("usage")}
                for ligne in _usage_par_brique(usage, "tts")
            ],
        },
        "pipeline_settings": estampille.get("pipeline_settings"),
        "call_duration_secs": usage.get("call_duration_seconds"),
    }


# Les traces des modules de lecture : clé du contexte → (module, champ entendu, champ retenu).
MODULES = (
    ("nombres_lus", "numbers", "entendu", "ecrit"),
    ("epellations_lues", "spelling", "entendu", "epele"),
    ("communes_verifiees", "towns", "entendu", "commune_retenue"),
    ("voies_verifiees", "streets", "entendu", "voie_retenue"),
    ("lexique_reconnu", "vocabulary", "entendu", "terme"),
)


def _modules(run: dict) -> dict:
    contexte = _contexte(run)
    elements = []
    presents = []
    for cle, module, entendu, retenu in MODULES:
        traces = contexte.get(cle)
        if not isinstance(traces, list):
            continue
        presents.append(module)
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            propositions = [
                p.get("nom") or p.get("terme")
                for p in (trace.get("propositions") or [])[:3]
                if isinstance(p, dict)
            ]
            elements.append(
                {
                    "module": module,
                    "caller_turn": trace.get("tour"),
                    "step": trace.get("etape"),
                    "heard": trace.get(entendu),
                    "result": trace.get(retenu),
                    "kind": trace.get("type") or trace.get("categorie"),
                    "status": trace.get("statut"),
                    "by_sound": trace.get("par_son"),
                    "proposals": propositions,
                }
            )
    if not presents:
        return {"status": NON_CAPTE, "items": [], "modules": []}
    return {"status": OK, "items": elements, "modules": presents}


def _fiche(run: dict, champs_declares: list[str] | None) -> dict:
    contexte = _contexte(run)
    etat = contexte.get("fiche_etat")
    journal = contexte.get("fiche_journal")
    valeurs = contexte.get("extracted_variables") or {}
    if not isinstance(etat, dict) and not isinstance(journal, list):
        return {"status": NON_CAPTE, "fields": []}
    etat = etat if isinstance(etat, dict) else {}
    journal = [j for j in (journal or []) if isinstance(j, dict)]
    noms = list(champs_declares or [])
    for nom in list(etat) + [j.get("champ") for j in journal]:
        if nom and nom not in noms:
            noms.append(nom)
    champs = []
    for nom in noms:
        historique = [
            {
                "caller_turn": j.get("tour"),
                "status": j.get("statut"),
                "reason": j.get("raison"),
                "source": j.get("source"),
                "sure": j.get("sure"),
                "value": j.get("valeur"),
            }
            for j in journal
            if j.get("champ") == nom
        ]
        ecrits = [h for h in historique if h["status"] == "ecrit"]
        valeur = valeurs.get(nom)
        champs.append(
            {
                "name": nom,
                "value": valeur,
                "empty": valeur in (None, "", [], {}),
                "declared": champs_declares is not None and nom in champs_declares,
                "sure": (etat.get(nom) or {}).get("sure"),
                "source": (etat.get(nom) or {}).get("source"),
                "written_at_caller_turn": ecrits[-1]["caller_turn"] if ecrits else None,
                "history": historique,
            }
        )
    refus = [
        {"field": j.get("champ"), "status": j.get("statut"), "reason": j.get("raison")}
        for j in journal
        if j.get("statut") not in ("ecrit", None)
    ]
    passes_de_notes = {
        "postscript": contexte.get("post_scriptums"),
        "clerk": contexte.get("greffier_passes"),
    }
    return {
        "status": OK,
        "fields": champs,
        "refusals": refus,
        "note_passes": {
            k: v for k, v in passes_de_notes.items() if isinstance(v, list)
        },
    }


def _parcours(run: dict, portes: set[str] | None) -> dict:
    evenements = _evenements(run)
    if not evenements:
        return {"status": NON_CAPTE}
    transitions = [
        {
            "turn": e.get("turn"),
            "from": (e.get("payload") or {}).get("previous_node_name"),
            "to": (e.get("payload") or {}).get("node_name"),
        }
        for e in evenements
        if e.get("type") == "rtf-node-transition"
    ]
    fins = {
        (e.get("payload") or {}).get("tool_call_id"): e
        for e in evenements
        if e.get("type") == "rtf-function-call-end"
    }
    outils = []
    for e in evenements:
        if e.get("type") != "rtf-function-call-start":
            continue
        charge = e.get("payload") or {}
        fin = fins.get(charge.get("tool_call_id"))
        duree = None
        if fin is not None:
            duree = _nombre_fini(
                (_ms(fin.get("timestamp")) - _ms(e.get("timestamp"))) / 1000
            )
        outils.append(
            {
                "turn": e.get("turn"),
                "step": e.get("node_name"),
                "name": charge.get("function_name"),
                "kind": _nature_d_un_outil(charge.get("function_name"), portes),
                "arguments": charge.get("arguments"),
                "result": (fin.get("payload") or {}).get("result") if fin else None,
                "finished": fin is not None,
                "duration_secs": duree,
            }
        )
    contexte = _contexte(run)
    return {
        "status": OK,
        "steps": contexte.get("nodes_visited") or [],
        "transitions": transitions,
        "tools": outils,
        "disposition": contexte.get("call_disposition"),
        "tags": contexte.get("call_tags") or [],
    }


def _conversation(run: dict) -> dict:
    evenements = _evenements(run)
    instants = [
        _ms(e.get("timestamp"))
        for e in evenements
        if not math.isnan(_ms(e.get("timestamp")))
    ]
    if not instants:
        return {"status": NON_CAPTE, "lines": []}
    origine = min(instants)
    lignes = []
    for e in evenements:
        charge = e.get("payload") or {}
        if e.get("type") == "rtf-user-transcription" and charge.get("final"):
            qui = "caller"
        elif e.get("type") == "rtf-bot-text":
            qui = "agent"
        else:
            continue
        debut = _ms(charge.get("timestamp") or e.get("timestamp"))
        fin = _ms(charge.get("end_timestamp"))
        lignes.append(
            {
                "turn": e.get("turn"),
                "speaker": qui,
                "text": charge.get("text"),
                "start_secs": _nombre_fini((debut - origine) / 1000),
                "end_secs": _nombre_fini((fin - origine) / 1000),
            }
        )
    lignes.sort(key=lambda l: (l["start_secs"] is None, l["start_secs"] or 0))
    return {
        "status": OK,
        "lines": lignes,
        # L'origine est le premier événement du run, pas le début de l'enregistrement :
        # l'écran le dit (« approximate »).
        "time_origin": "first_event",
    }


def _incidents(run: dict, latence: dict) -> dict:
    elements = []
    for e in _evenements(run):
        if e.get("type") != "rtf-pipeline-error":
            continue
        charge = e.get("payload") or {}
        limite = (
            str(charge.get("code")) == "1300"
            or "RateLimit" in str(charge.get("exception_type"))
            or "429" in str(charge.get("error"))
        )
        elements.append(
            {
                "turn": e.get("turn"),
                "kind": "model_rate_limited" if limite else "pipeline_error",
                "fatal": bool(charge.get("fatal")),
                "processor": charge.get("processor"),
                "detail": charge.get("exception_type"),
            }
        )
    debuts = [e for e in _evenements(run) if e.get("type") == "rtf-function-call-start"]
    fins = {
        (e.get("payload") or {}).get("tool_call_id")
        for e in _evenements(run)
        if e.get("type") == "rtf-function-call-end"
    }
    for e in debuts:
        if (e.get("payload") or {}).get("tool_call_id") not in fins:
            elements.append(
                {
                    "turn": e.get("turn"),
                    "kind": "tool_never_finished",
                    "fatal": False,
                    "processor": None,
                    "detail": (e.get("payload") or {}).get("function_name"),
                }
            )
    for tour in latence.get("turns") or []:
        if tour.get("slow"):
            elements.append(
                {
                    "turn": tour["turn"],
                    "kind": "slow_turn",
                    "fatal": False,
                    "processor": None,
                    "detail": tour["silence_secs"],
                }
            )
    return {"status": OK, "items": elements}


def _bloc(nom: str, calcul: Callable[[], dict], run_id: Any) -> dict:
    try:
        return calcul()
    except Exception as erreur:  # noqa: BLE001 — R1 : un bloc en échec se VOIT à l'écran
        logger.warning(
            f"[analyse du run {run_id}] bloc {nom} indisponible : {erreur!r}"
        )
        return {"status": INDISPONIBLE, "reason": type(erreur).__name__}


def analyser_run(
    run: dict,
    *,
    portes: set[str] | None = None,
    champs_fiche: list[str] | None = None,
) -> dict:
    """L'analyse complète, bloc par bloc.

    ``portes`` : les noms d'outil des transitions de la définition jouée (``None`` si la
    définition n'a pas pu être lue : les outils autres que la prise de notes restent alors
    « tool_or_transition »). ``champs_fiche`` : les champs déclarés de la fiche, pour montrer
    ceux restés vides.
    """
    identifiant = run.get("id")
    latence = _bloc("latency", lambda: _latence(run, portes), identifiant)
    incidents = _bloc("incidents", lambda: _incidents(run, latence), identifiant)
    contexte = _contexte(run)
    resume = _bloc(
        "summary",
        lambda: {
            "status": OK,
            "agent_id": run.get("workflow_id"),
            "definition_id": run.get("definition_id"),
            "channel": CANAUX.get(run.get("mode"), "phone"),
            "mode": run.get("mode"),
            "duration_secs": (run.get("usage_info") or {}).get("call_duration_seconds"),
            "disposition": contexte.get("call_disposition"),
            "cost": {"status": NON_CAPTE},
            "incident_count": len(incidents.get("items") or []),
        },
        identifiant,
    )
    return {
        "version": VERSION,
        "run_id": identifiant,
        "summary": resume,
        "latency": latence,
        "providers": _bloc("providers", lambda: _fournisseurs(run), identifiant),
        "reading_modules": _bloc("reading_modules", lambda: _modules(run), identifiant),
        "record": _bloc("record", lambda: _fiche(run, champs_fiche), identifiant),
        "path": _bloc("path", lambda: _parcours(run, portes), identifiant),
        "conversation": _bloc("conversation", lambda: _conversation(run), identifiant),
        "incidents": incidents,
    }
