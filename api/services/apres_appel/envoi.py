"""[.mark] What is written in the client's database for a call (A2), built from the run.

The run's analysis (``api/services/analyse_run/``, the one the run window shows) gives
the turns, the latency, the conversation and the cost; the record (``extracted_variables``,
``fiche_etat``) gives the fields. Which field holds the name, the reason or the urgency is
the AGENT's setting (``ApresAppelAgent.champs``): no trade word in the code.

``mark.recevoir_appel`` does the rest in the database (contact by number, one request per
call, the hint of another open request, the transcript's expiry date).
"""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Any

from api.schemas.apres_appel import ApresAppelAgent

CANAUX = {
    "smallwebrtc": "navigateur",
    "textchat": "clavier",
    "simulated": "simule",
}


def _texte(valeur: Any) -> str | None:
    if valeur in (None, "", [], {}):
        return None
    if isinstance(valeur, (list, tuple)):
        return ", ".join(str(v) for v in valeur if v not in (None, ""))
    if isinstance(valeur, dict):
        return ", ".join(f"{k}: {v}" for k, v in valeur.items() if v not in (None, ""))
    return str(valeur)


def _sans_accents(texte: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texte.casefold())
        if unicodedata.category(c) != "Mn"
    )


def choisir_sujet(sujets: list[dict], *textes: str | None) -> dict | None:
    """The routing (A4): the first active subject one of whose trigger words, or its code,
    appears in the reason or the request type. None: the default recipients."""
    corpus = _sans_accents(" ".join(t for t in textes if t))
    if not corpus:
        return None
    for sujet in sujets:
        mots = list(sujet.get("mots_declencheurs") or []) + [sujet.get("code") or ""]
        for mot in mots:
            mot = _sans_accents(mot or "").strip()
            if mot and mot in corpus:
                return sujet
    return None


def _jetons(usage: dict) -> tuple[int | None, int | None, int | None]:
    llm = (usage or {}).get("llm") or {}
    if not isinstance(llm, dict) or not llm:
        return None, None, None
    entree = cache = sortie = 0
    for valeur in llm.values():
        if not isinstance(valeur, dict):
            continue
        entree += int(valeur.get("prompt_tokens") or 0)
        sortie += int(valeur.get("completion_tokens") or 0)
        cache += int(valeur.get("cache_read_input_tokens") or 0)
    return entree, cache, sortie


def construire_envoi(
    run,
    analyse: dict,
    agent: ApresAppelAgent,
    sujets: list[dict] | None = None,
    avec_verbatim: bool = True,
) -> dict:
    """The ``envoi`` of ``mark.recevoir_appel`` for this run."""
    initial = run.initial_context or {}
    contexte = run.gathered_context or {}
    fiche = contexte.get("extracted_variables") or {}
    fiche = fiche if isinstance(fiche, dict) else {}
    etat = (
        contexte.get("fiche_etat")
        if isinstance(contexte.get("fiche_etat"), dict)
        else {}
    )
    definition = getattr(run, "definition", None)
    configurations = getattr(definition, "workflow_configurations", None) or {}
    origines = {
        c.get("nom"): c.get("origine")
        for c in configurations.get("fiche_champs") or []
        if isinstance(c, dict)
    }
    runtime = initial.get("runtime_configuration") or {}
    etablissement = (
        (runtime.get("etablissement") or {}).get("id")
        if isinstance(runtime, dict)
        else None
    )

    def valeur(role: str) -> str | None:
        return _texte(fiche.get(agent.champ(role)))

    motif = valeur("motif")
    type_demande = valeur("type_demande")
    sujet = choisir_sujet(sujets or [], motif, type_demande)

    entrant = (getattr(run, "call_type", None) or "inbound") != "outbound"
    appelant = initial.get("caller_number") if entrant else initial.get("called_number")
    appele = initial.get("called_number") if entrant else initial.get("caller_number")
    rappel = valeur("numero_rappel")

    resume = analyse.get("summary") or {}
    latence = analyse.get("latency") or {}
    stats = latence.get("stats") or {}
    cout = resume.get("cost") or {}
    entree, cache, sortie = _jetons(getattr(run, "usage_info", None) or {})

    champs = [
        {
            "nom": nom,
            "valeur": _texte(v),
            "origine": origines.get(nom),
            "sure": (etat.get(nom) or {}).get("sure")
            if isinstance(etat.get(nom), dict)
            else None,
            "source": (etat.get(nom) or {}).get("source")
            if isinstance(etat.get(nom), dict)
            else None,
        }
        for nom, v in fiche.items()
        if _texte(v) is not None
    ]
    tours = [
        {
            "numero": t.get("turn"),
            "etape": t.get("step") or None,
            "locuteur": "agent",
            "silence_s": t.get("silence_secs"),
            "latence_s": t.get("silence_secs"),
        }
        for t in latence.get("turns") or []
        if isinstance(t.get("turn"), int)
    ]
    lignes = (analyse.get("conversation") or {}).get("lines") or []
    verbatim = (
        [
            {
                "tour": l.get("turn"),
                "qui": "agent" if l.get("speaker") == "agent" else "appelant",
                "texte": l.get("text"),
                "debut_s": l.get("start_secs"),
            }
            for l in lignes
            if l.get("text")
        ]
        if avec_verbatim
        else []
    )
    debut = getattr(run, "created_at", None) or datetime.now(UTC)
    # One request per call (A2), when the call carries one: a call where nothing was
    # noted (wrong number, hung up at once) makes no request to call back.
    demande = (
        {
            "type": type_demande,
            "sujet": (sujet or {}).get("code"),
            "priorite": 1 if (sujet or {}).get("urgent") else 2,
            "degre_urgence": valeur("degre_urgence"),
        }
        if champs
        else None
    )
    # [.mark] L7 (PN1): a call lost by an outage always makes its request « to call back »,
    # even with nothing noted, first in the list.
    panne = contexte.get("panne")
    if isinstance(panne, dict) and panne.get("a_rappeler"):
        demande = {
            **(demande or {"type": "autre", "sujet": None, "degre_urgence": None}),
            "priorite": 1,
            "resume": "Appel interrompu par une panne de l'agent : à rappeler.",
            "nee_d_une_panne": True,
        }
    # [.mark] l-agent-collegue, L2 (C8, C10): what the agent did for the team. A request
    # passed on to a person exists even with nothing noted, and is assigned to her. Absent
    # from the record (every agent of before): the envoi is exactly the one of before.
    gestes = contexte.get("equipe_gestes")
    gestes = [g for g in gestes if isinstance(g, dict)] if isinstance(gestes, list) else []
    assignation = contexte.get("equipe_assignation")
    assignation = assignation if isinstance(assignation, str) and assignation else None
    if assignation:
        demande = {
            **(
                demande
                or {
                    "type": type_demande or "autre",
                    "sujet": (sujet or {}).get("code"),
                    "priorite": 1 if (sujet or {}).get("urgent") else 2,
                    "degre_urgence": valeur("degre_urgence"),
                }
            ),
            "assignee": assignation,
        }
    envoi_equipe = {"equipe": {"gestes": gestes, "assignee": assignation}} if (gestes or assignation) else {}
    # [.mark] l-agent-collegue, L4 (H6): the appointments booked during the call, written in the
    # hub after it. A booked appointment always has its request (a rendez_vous belongs to one).
    # Absent from the record (every agent of before): the envoi is exactly the one of before.
    poses = contexte.get("hub_rendez_vous")
    poses = [r for r in poses if isinstance(r, dict)] if isinstance(poses, list) else []
    if poses and demande is None:
        demande = {
            "type": type_demande or "autre",
            "sujet": (sujet or {}).get("code"),
            "priorite": 1 if (sujet or {}).get("urgent") else 2,
            "degre_urgence": valeur("degre_urgence"),
        }
    envoi_hub = {"hub": {"rendez_vous": poses}} if poses else {}
    return {
        **envoi_equipe,
        **envoi_hub,
        "dograh_run_id": run.id,
        "dograh_workflow_id": run.workflow_id,
        "agent_nom": getattr(getattr(run, "workflow", None), "name", None),
        "dograh_definition_id": run.definition_id or 0,
        "numero_version": getattr(definition, "version_number", None),
        "etablissement": etablissement,
        "canal": CANAUX.get(run.mode, "telephone"),
        "sens": "entrant" if entrant else "sortant",
        "numero_appelant": appelant or rappel,
        "numero_appele": appele,
        "debut": debut.isoformat(),
        "duree_s": (
            round(d)
            if isinstance(
                d := (run.usage_info or {}).get("call_duration_seconds"), (int, float)
            )
            else None
        ),
        "issue": contexte.get("mapped_call_disposition")
        or contexte.get("call_disposition")
        or None,
        "motif": motif,
        "degre_urgence": valeur("degre_urgence"),
        "contact": {
            "nom": valeur("nom"),
            "prenom": valeur("prenom"),
            "mail": valeur("mail"),
        },
        "demande": demande,
        "champs": champs,
        "tours": tours,
        "verbatim": verbatim,
        "nb_tours": stats.get("total_turns"),
        "latence_mediane_s": stats.get("median_silence_secs"),
        "pire_silence_s": stats.get("worst_silence_secs"),
        "jetons_entree": entree,
        "jetons_cache": cache,
        "jetons_sortie": sortie,
        "cout_estime": cout.get("total") if cout.get("status") == "ok" else None,
        "cout_tarif_du": (cout.get("rate_dates") or [None])[-1]
        if cout.get("status") == "ok"
        else None,
        "fournisseurs": {
            k: v
            for k, v in (runtime.items() if isinstance(runtime, dict) else [])
            if k.endswith(("_provider", "_model"))
        },
        "mesures": {"analyse_version": analyse.get("version")},
    }
