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
from api.services.apres_appel.rappels import (
    ORIGINE_EQUIPE,
    ORIGINE_PLANIFICATEUR,
    ORIGINE_VERIFICATION,
    origine,
    rappels_de,
    resume_du_rappel,
)

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


def _motifs(brut: Any) -> list[str]:
    """[.mark] Chantier agents-specialises, lot 8 (A8) : les motifs d'un appel. Une liste, ou une
    chaîne dont les valeurs sont séparées par « ; » (le greffier du lot 7 écrit une liste de la
    liste fermée) ; une chaîne sans « ; » est un seul motif, comme avant. Le premier est le
    motif de l'appel ; vides et doublons tombent."""
    if isinstance(brut, (list, tuple)):
        morceaux = [str(v) for v in brut if v not in (None, "")]
    elif isinstance(brut, str):
        morceaux = brut.split(";")
    else:
        texte = _texte(brut)
        morceaux = [texte] if texte else []
    propres: list[str] = []
    for morceau in morceaux:
        morceau = morceau.strip()
        if morceau and morceau not in propres:
            propres.append(morceau)
    return propres


# Ce que l'analyse du run appelle un incident et qui en est un pour le portail (lot 9) : une panne
# ou un repli, pas un silence un peu long ni un tour lent.
INCIDENTS_RETENUS = frozenset(
    {
        "pipeline_error",
        "model_rate_limited",
        "provider_disconnected",
        "provider_error",
        "outage_fallback",
        "model_timeout",
        "tool_never_finished",
    }
)
# Les détails qui portent des chiffres (durées, tentatives) ne servent pas à reconnaître un incident.
_KINDS_SANS_DETAIL = frozenset({"model_timeout"})


def incidents_de(analyse: dict, debut: datetime) -> list[dict]:
    """[.mark] Lot 9 : les incidents de l'appel, tels que ``mark.noter_incident`` les range (une
    brique et une cause ; la même brique et la même cause dans les 30 minutes = le même
    incident, plusieurs appels). Jamais une valeur dite par l'appelant : la brique et le type."""
    elements = ((analyse or {}).get("incidents") or {}).get("items") or []
    sortie: list[dict] = []
    vus: set[tuple] = set()
    for e in elements:
        if not isinstance(e, dict):
            continue
        kind = str(e.get("kind") or "")
        if kind not in INCIDENTS_RETENUS and not e.get("fatal"):
            continue
        brique = str(e.get("processor") or kind)[:100]
        detail = e.get("detail")
        cause = kind
        if kind not in _KINDS_SANS_DETAIL and isinstance(detail, str) and detail.strip():
            cause = f"{kind} : {detail.strip()}"[:200]
        cle = (brique, cause)
        if cle in vus:
            continue
        vus.add(cle)
        sortie.append({"brique": brique, "cause": cause, "debut": debut.isoformat()})
    return sortie


def agents_de_l_appel(run, contexte: dict) -> list[dict]:
    """[.mark] Lot 8 (D83) : les agents de l'appel dans l'ordre -- celui qui a décroché, puis
    chaque agent atteint par une passation (une passation partie : l'agent cible existe). Le nom
    des agents appelés est rempli par l'étape d'écriture (rien dans la trace)."""
    premier = {
        "dograh_workflow_id": run.workflow_id,
        "nom": getattr(getattr(run, "workflow", None), "name", None),
    }
    agents = [premier]
    for passation in (contexte or {}).get("agent_transfers") or []:
        if not isinstance(passation, dict) or passation.get("to_visit_id") is None:
            continue
        vers = passation.get("destination_workflow_id")
        if isinstance(vers, int) and not isinstance(vers, bool):
            agents.append({"dograh_workflow_id": vers, "nom": None})
    return agents


def transferts_de(contexte: dict) -> list[dict]:
    """[.mark] Lot 9 (D82) : les issues des transferts vers un humain et des renvois, telles que la
    fiche les porte (``transferts_humains`` du lot 5, ``transferts`` des renvois). Une entrée :
    ``{le, cible, issue}``."""
    sortie: list[dict] = []
    for cle in ("transferts_humains", "transferts"):
        for e in (contexte or {}).get(cle) or []:
            if isinstance(e, dict) and e.get("issue"):
                sortie.append(
                    {
                        "le": e.get("le"),
                        "cible": e.get("cible"),
                        "issue": str(e.get("issue"))[:40],
                    }
                )
    return sortie


def hors_horaires_de(initial: dict) -> bool | None:
    """[.mark] Lot 9 : l'appel a-t-il été pris hors des horaires ? L'état d'ouverture est calculé une
    fois au décroché (``etat_ouverture`` du contexte initial). Fermé ou en pause = hors horaires ;
    ouvert ou sur rendez-vous = non ; inconnu (aucun horaire réglé) = ``None``, jamais « non »."""
    from api.services.annonce.constantes import FERME, OUVERT, PAUSE, SUR_RENDEZ_VOUS

    etat = (initial or {}).get("etat_ouverture")
    if etat in (FERME, PAUSE):
        return True
    if etat in (OUVERT, SUR_RENDEZ_VOUS):
        return False
    return None


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


def _rappel_permis(origine_du_rappel: str, configurations: dict) -> bool:
    from api.services.equipe import appel as equipe
    from api.services.verification import reglages as verification

    if origine_du_rappel == ORIGINE_EQUIPE:
        return equipe.interrupteur_allume(configurations)
    if origine_du_rappel == ORIGINE_VERIFICATION:
        return verification.interrupteur_allume(configurations)
    return True  # the planner: its tool is on the agent only when the agent was given it


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

    # [.mark] Lot 8 (A8) : un appel peut porter plusieurs motifs ; le premier reste « le motif ».
    motifs = _motifs(fiche.get(agent.champ("motif")))
    motif = motifs[0] if motifs else None
    type_demande = valeur("type_demande")
    sujet = choisir_sujet(sujets or [], " ; ".join(motifs) or None, type_demande)

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
    # [.mark] l-agent-collegue, L5 (P8), R-3, L6 (V6): a call-back decided during the call -- no
    # appointment could be booked, the person did not take the transfer, the caller could not be
    # verified. The request exists, its summary says what is to be done (never a lost caller).
    # The planner's only when nothing was booked; the others always.
    # X2: a call-back of the team or of the verification counts only when the agent's own switch
    # is on; an agent that switched nothing on keeps the mail of before, character for character.
    rappels = [
        r for r in rappels_de(contexte)
        if not (poses and origine(r) == ORIGINE_PLANIFICATEUR)
        and _rappel_permis(origine(r), configurations)
    ]
    if rappels:
        dernier = rappels[-1]
        demande = dict(
            demande
            or {
                "type": type_demande or "autre",
                "sujet": (sujet or {}).get("code"),
                "priorite": 1 if (sujet or {}).get("urgent") else 2,
                "degre_urgence": valeur("degre_urgence"),
            }
        )
        # Every call-back decided in the call says what is to be done (number, object, wish): a
        # summary written by the extraction comes AFTER them, it never replaces them.
        a_faire = list(dict.fromkeys(resume_du_rappel(r) for r in rappels))
        demande["resume"] = " ".join([*a_faire, *([demande["resume"]] if demande.get("resume") else [])])
        if origine(dernier) != ORIGINE_PLANIFICATEUR:
            # R-3, V6: the mail's subject says it is a call-back to make.
            demande["a_rappeler"] = True
    envoi_hub = {"hub": {"rendez_vous": poses}} if poses else {}
    # [.mark] l-agent-collegue, L6 (V6): each verification attempt, never an answer. Absent from
    # the record (every agent of before): the envoi is exactly the one of before.
    verifications = contexte.get("verification_appelant")
    verifications = (
        [v for v in verifications if isinstance(v, dict)] if isinstance(verifications, list) else []
    )
    if verifications:
        envoi_hub = {**envoi_hub, "verifications": verifications}
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
        "motifs": motifs,
        "hors_horaires": hors_horaires_de(initial),
        "agents": agents_de_l_appel(run, contexte),
        "transferts": transferts_de(contexte),
        "incidents": incidents_de(analyse, debut),
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
