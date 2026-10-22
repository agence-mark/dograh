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
from api.services.fiche.demandes import APPEL, DEMANDE, demandes_closes, dernier_specialise
from api.services.groupe.parcours import rendre_le_parcours
from api.services.objets_agent.appel import incidents_des_objets
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


def _blocs_des_demandes(
    closes: list[dict],
    contexte: dict,
    champs_a_plat: list[dict],
    entrees,
    agent: ApresAppelAgent,
    sujets: list[dict],
) -> list[dict]:
    """[.mark] Lot 17 : les demandes de l'appel, une par bloc : les demandes closes, puis la demande
    en cours si elle a un champ « demande » rempli. Chaque bloc porte les champs « appel » (à leur
    valeur de la fin de l'appel) et ses propres champs « demande », chacun marqué de sa portée.
    ``demande`` : le type, le sujet (choisi sur le motif du bloc), la priorité, le degré d'urgence."""
    appel_noms = {nom for bloc in closes for nom in (bloc.get("appel") or [])}
    de_l_appel = [dict(c, portee=APPEL) for c in champs_a_plat if c["nom"] in appel_noms]
    en_cours = [dict(c, portee=DEMANDE) for c in champs_a_plat if c["nom"] not in appel_noms]

    def _demande(champs_du_bloc: dict, motifs: list[str]) -> dict:
        def valeur(role: str) -> str | None:
            return _texte(champs_du_bloc.get(agent.champ(role)))

        sujet = choisir_sujet(sujets, " ; ".join(motifs) or None, valeur("type_demande"))
        return {
            "type": valeur("type_demande"),
            "sujet": (sujet or {}).get("code"),
            "priorite": 1 if (sujet or {}).get("urgent") else 2,
            "degre_urgence": valeur("degre_urgence"),
        }

    blocs: list[dict] = []
    for bloc in closes:
        propres = bloc.get("champs") or {}
        motifs = _motifs(propres.get(agent.champ("motif")))
        blocs.append(
            {
                "ordre": len(blocs) + 1,
                "agent_id": bloc.get("agent_id"),
                "agent": bloc.get("agent"),
                "motif": motifs[0] if motifs else None,
                "motifs": motifs,
                "champs": de_l_appel + [dict(c, portee=DEMANDE) for c in entrees(propres, bloc.get("etat") or {})],
                "demande": _demande(propres, motifs),
            }
        )
    if en_cours:
        valeurs = {c["nom"]: c["valeur"] for c in en_cours}
        motifs = _motifs(valeurs.get(agent.champ("motif")))
        blocs.append(
            {
                "ordre": len(blocs) + 1,
                # Le dernier spécialisé passé par l'appel : celui qui a traité la demande en cours.
                "agent_id": dernier_specialise(contexte, None),
                "agent": None,
                "motif": motifs[0] if motifs else None,
                "motifs": motifs,
                "champs": de_l_appel + en_cours,
                # La demande de l'appel : ses champs sont ceux de la vue à plat (champ_appel).
                "courante": True,
                "demande": _demande(valeurs, motifs),
            }
        )
    return blocs


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


def travaux_de(contexte: dict) -> list[dict]:
    """[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D12), lot F2 de cloture-code-avant-migration :
    ce que le cerveau de fond a fait pendant l'appel, tel que la fiche le porte (``travaux``) : une
    entrée par demande confiée, ``{statut, outils, duree_ms}``. ⛔ Ni le texte de la demande ni
    celui du résultat ne partent : la base du client garde ce que le fond a FAIT (quel outil,
    combien de temps, avec quel statut), jamais ce qui s'est dit (IX.3). Liste vide : aucun travail
    (tout agent de jusqu'ici), et la clé n'entre alors pas dans l'envoi."""
    sortie: list[dict] = []
    for e in (contexte or {}).get("travaux") or []:
        if not isinstance(e, dict) or not e.get("demande"):
            continue
        sortie.append(
            {
                "statut": str(e.get("statut") or "")[:20] or None,
                "outils": [str(o)[:80] for o in (e.get("outils") or []) if o][:40],
                "duree_ms": e.get("duree_ms"),
            }
        )
    return sortie


def parcours_de(contexte: dict) -> list[dict]:
    """[.mark] Lot F2 : les entrées du parcours de l'appel (``parcours_etapes``, écrites dans un
    groupe seulement : une par entrée dans une étape, avec l'agent qui la porte). Vide : un agent
    seul, la clé n'entre pas dans l'envoi."""
    entrees = (contexte or {}).get("parcours_etapes")
    return [e for e in entrees if isinstance(e, dict)] if isinstance(entrees, list) else []


def agent_de_chaque_tour(tours: list[dict], entrees: list[dict]) -> None:
    """[.mark] Lot F2 : pose ``agent_id`` (identifiant Dograh) sur chaque tour qui porte une étape,
    à partir du parcours. Le parcours se lit dans l'ordre : pour chaque tour, on cherche son étape
    à partir de l'entrée où l'on en était ; trouvée, l'agent de cette entrée porte le tour (un
    retour chez un agent plus tard ne se confond pas avec son premier passage) ; introuvable, le
    tour garde l'agent de l'entrée courante. Pas de parcours : rien n'est posé. Modifie ``tours``."""
    if not entrees:
        return
    position = 0
    for tour in tours:
        etape = tour.get("etape")
        if etape:
            for i in range(position, len(entrees)):
                if entrees[i].get("etape") == etape:
                    position = i
                    break
        agent = entrees[position].get("agent_id")
        if isinstance(agent, int) and not isinstance(agent, bool):
            tour["agent_id"] = agent


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

    # [.mark] Lot 17 : les demandes closes d'un appel à plusieurs demandes (liste vide : le
    # chemin d'avant, inchangé). Leurs champs « demande » ne sont plus dans la vue à plat.
    closes = demandes_closes(contexte)
    # [.mark] Lot 8 (A8) : un appel peut porter plusieurs motifs ; le premier reste « le motif ».
    # Lot 17 : ceux des demandes closes d'abord, dans l'ordre des demandes.
    motifs = _motifs(
        [
            m
            for bloc in closes
            for m in _motifs((bloc.get("champs") or {}).get(agent.champ("motif")))
        ]
        + _motifs(fiche.get(agent.champ("motif")))
    )
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

    def _entrees(valeurs: dict, etats: dict) -> list[dict]:
        return [
            {
                "nom": nom,
                "valeur": _texte(v),
                "origine": origines.get(nom),
                "sure": (etats.get(nom) or {}).get("sure")
                if isinstance(etats.get(nom), dict)
                else None,
                "source": (etats.get(nom) or {}).get("source")
                if isinstance(etats.get(nom), dict)
                else None,
            }
            for nom, v in valeurs.items()
            if _texte(v) is not None
        ]

    champs = _entrees(fiche, etat)
    # [.mark] Lot 17 : une demande par bloc, quand l'appel en porte au moins deux (sinon la demande
    # close est reversée à plat et l'envoi est celui d'avant).
    demandes_de_l_appel = (
        _blocs_des_demandes(
            closes, contexte, champs, _entrees, agent, sujets or []
        )
        if closes
        else []
    )
    if closes and len(demandes_de_l_appel) < 2:
        # Un seul bloc : la demande unique de l'appel, comme avant (ses champs reviennent à plat).
        for bloc in closes:
            reverses = {
                nom: v
                for nom, v in (bloc.get("champs") or {}).items()
                if nom not in fiche
            }
            champs = _entrees(reverses, bloc.get("etat") or {}) + champs
        demandes_de_l_appel = []
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
    # [.mark] Lot F2 : l'agent de chaque tour et le parcours rendu (« Agent › étape »), dans un
    # groupe seulement ; un agent seul garde l'envoi d'avant.
    entrees_du_parcours = parcours_de(contexte)
    agent_de_chaque_tour(tours, entrees_du_parcours)
    parcours = rendre_le_parcours(entrees_du_parcours) if entrees_du_parcours else ""
    envoi_parcours = {"parcours": parcours} if parcours else {}
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
    # [.mark] Lot 4 d'orchestrateur-trois-cerveaux (D12) : le travail de fond, additif. Absent de
    # la fiche (tout appel d'avant) : l'envoi est exactement celui d'avant, sans la clé.
    travaux = travaux_de(contexte)
    envoi_travaux = {"travaux": travaux} if travaux else {}
    return {
        **envoi_equipe,
        **envoi_hub,
        **envoi_travaux,
        **envoi_parcours,
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
        # [.mark] cloture-code, F7: a call whose objects could not be read at pick-up notes it.
        "incidents": incidents_de(analyse, debut) + incidents_des_objets(runtime, debut),
        "degre_urgence": valeur("degre_urgence"),
        "contact": {
            "nom": valeur("nom"),
            "prenom": valeur("prenom"),
            "mail": valeur("mail"),
        },
        "demande": demande,
        "champs": champs,
        **({"demandes": demandes_de_l_appel} if demandes_de_l_appel else {}),
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
