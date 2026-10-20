"""[.mark] Chantier fiabilite-orchestration, lot 4 ter (F16, F24) : la carte des phrases dites par le code.

La carte répond, pour un agent (et, vue depuis le principal, pour tout son groupe) : **quand** le code
parle de lui-même, **où**, avec **quel texte** en vigueur, **d'où** il vient (étape, agent, principal,
défaut), **quel délai**, **allumée ou non**, et **la dernière fois** qu'il l'a dite (lue dans la trace
``phrases_du_code`` des derniers appels). Les phrases écrites dans le graphe (accueil, phrases des
portes, fins figées) sont montrées **en lecture** : elles se règlent dans le graphe.

``INVENTAIRE_DU_CODE`` recense **chaque endroit** du code qui fait parler la voix sans le modèle ;
``test_carte_des_phrases.py`` le compare au code lui-même : une phrase ajoutée sans passer par la carte
fait échouer le test. ⛔ Ne lève jamais ; aucun mot de métier.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from api.services.phrases.catalogue import MOTIFS
from api.services.phrases.regles import regles_de, resoudre

NATURE_MOTIF = "motif"  # par le diseur : une règle du thème Phrases
NATURE_GRAPHE = "graphe"  # écrite dans le graphe (accueil, porte, fin figée, messagerie)
NATURE_ACTION = "action"  # écrite sur une action (outil, connecteur, équipe) : dite quand elle s'exécute
NATURE_SOCLE = "socle"  # la mécanique de la parole elle-même (aucun texte propre)
NATURE_HORS = "hors"  # voix temps réel : hors de ce mécanisme

# Chemin (sous ``api/services``) -> les endroits où la voix parle sans le modèle, dans l'ordre du fichier.
INVENTAIRE_DU_CODE: dict[str, list[tuple[str, str]]] = {
    "equipe/diriger.py": [(NATURE_ACTION, "Phrase d'une action d'équipe (diriger vers une personne)")],
    "integrations/connectors/champs_requis.py": [
        (NATURE_ACTION, "Phrase de patience d'un connecteur qui collecte ses champs")
    ],
    "integrations/connectors/outil.py": [
        (NATURE_ACTION, "Phrase rendue par une action interne (planificateur, vérification)")
    ],
    "pipecat/post_scriptum.py": [(NATURE_GRAPHE, "Phrase d'une porte, mode Post-scriptum")],
    "pipecat/realtime/openai_live.py": [
        (NATURE_HORS, "Voix temps réel : accueil"),
        (NATURE_HORS, "Voix temps réel : message de fin"),
    ],
    "travail/outils.py": [(NATURE_SOCLE, "Cerveau de fond au clavier : rien n'est dit")],
    "workflow/agent_runtime.py": [(NATURE_SOCLE, "Parole d'un agent (``speak``)")],
    "workflow/agent_transfer.py": [(NATURE_ACTION, "Annonce d'une passation, réglée sur l'outil")],
    "workflow/answer_handling.py": [
        (NATURE_GRAPHE, "Messagerie : message déposé"),
        (NATURE_GRAPHE, "Messagerie : message déposé (lecture)"),
        (NATURE_GRAPHE, "Messagerie : message configuré"),
    ],
    "workflow/pipecat_engine.py": [
        (NATURE_GRAPHE, "Phrase d'une porte (son enregistré)"),
        (NATURE_GRAPHE, "Phrase d'une porte (texte)"),
        (NATURE_GRAPHE, "Phrase d'une porte lue dans la réponse (son)"),
        (NATURE_GRAPHE, "Phrase d'une porte lue dans la réponse (texte)"),
        (NATURE_GRAPHE, "Fin figée"),
        (NATURE_GRAPHE, "Accueil (son enregistré)"),
        (NATURE_GRAPHE, "Accueil (voix temps réel)"),
        (NATURE_GRAPHE, "Accueil (texte)"),
        (NATURE_SOCLE, "File de parole (``queue_speech``)"),
        (NATURE_SOCLE, "Message sans attente (``queue_text_message``)"),
    ],
    "workflow/pipecat_engine_custom_tools.py": [
        (NATURE_ACTION, "Message d'un outil (son enregistré)"),
        (NATURE_ACTION, "Message d'un outil (texte)"),
        (NATURE_ACTION, "Message avant un outil HTTP (son enregistré)"),
        (NATURE_ACTION, "Message avant un outil HTTP (texte)"),
        (NATURE_ACTION, "Message d'attente d'un transfert dynamique"),
        (NATURE_ACTION, "Message d'un transfert d'appel"),
        (NATURE_ACTION, "Message d'un transfert d'appel, au clavier"),
    ],
}
# Les endroits où le diseur des phrases du code parle (``services/phrases/``), un par motif.
INVENTAIRE_DU_DISEUR = tuple(MOTIFS)


@dataclass
class AgentDeLaCarte:
    id: int
    nom: str
    reglages: Mapping[str, Any] | None
    graphe: Mapping[str, Any] | None = None
    est_principal: bool = False
    etapes: list[str] = field(default_factory=list)


def _texte(libelle_fr: str, libelle_en: str) -> dict[str, str]:
    return {"fr": libelle_fr, "en": libelle_en}


def lecture_du_graphe(graphe: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Les phrases écrites dans le graphe : accueil, phrases des portes, fins figées."""
    lignes: list[dict[str, Any]] = []
    try:
        noeuds = {n.get("id"): n for n in (graphe or {}).get("nodes") or [] if isinstance(n, dict)}
        for noeud in noeuds.values():
            data = noeud.get("data") or {}
            nom = data.get("name") or noeud.get("id")
            accueil = data.get("greeting")
            if isinstance(accueil, str) and accueil.strip():
                lignes.append({"nature": "accueil", "endroit": nom, "texte": accueil.strip()})
            for fin in data.get("fins") or []:
                phrase = (fin or {}).get("phrase") if isinstance(fin, dict) else None
                if isinstance(phrase, str) and phrase.strip():
                    lignes.append({"nature": "fin_figee", "endroit": nom, "texte": phrase.strip()})
        for arete in (graphe or {}).get("edges") or []:
            if not isinstance(arete, dict):
                continue
            data = arete.get("data") or {}
            phrase = data.get("transition_speech")
            if isinstance(phrase, str) and phrase.strip():
                source = (noeuds.get(arete.get("source")) or {}).get("data", {}).get("name")
                cible = (noeuds.get(arete.get("target")) or {}).get("data", {}).get("name")
                lignes.append(
                    {"nature": "porte", "endroit": f"{source} → {cible}", "texte": phrase.strip()}
                )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] graphe illisible pour la carte : {erreur!r}")
    return lignes


def derniers_declenchements(traces: Iterable[tuple[Any, Any, list[dict]]]) -> dict[tuple, dict]:
    """``traces`` : (run, moment du run, entrées ``phrases_du_code``), du plus récent au plus ancien.
    Rend la dernière entrée par (motif, agent, étape) et par (motif, agent)."""
    derniers: dict[tuple, dict] = {}
    for run_id, moment, entrees in traces:
        for entree in reversed(entrees or []):
            if not isinstance(entree, dict):
                continue
            ligne = {
                "run": run_id,
                "moment": moment,
                "texte": entree.get("texte"),
                "etape": entree.get("etape"),
                "niveau": entree.get("niveau"),
            }
            for cle in (
                (entree.get("motif"), entree.get("agent"), entree.get("etape")),
                (entree.get("motif"), entree.get("agent")),
            ):
                derniers.setdefault(cle, ligne)
    return derniers


def construire_la_carte(
    agents: list[AgentDeLaCarte],
    reglages_principal: Mapping[str, Any] | None,
    derniers: dict[tuple, dict] | None = None,
) -> dict[str, Any]:
    """La carte de ``agents`` (le premier est celui de l'écran). ⛔ Ne lève jamais."""
    derniers = derniers or {}
    carte: dict[str, Any] = {"agents": [], "actions": []}
    for agent in agents:
        try:
            principal = reglages_principal if not agent.est_principal else agent.reglages
            motifs = []
            regles = regles_de(agent.reglages)
            for motif in MOTIFS.values():
                phrase = resoudre(
                    motif.id, reglages_agent=agent.reglages, reglages_principal=principal
                )
                etapes = [
                    {
                        "etape": r.etape,
                        "variantes": list(r.variantes),
                        "delai_s": r.delai_s if motif.a_un_delai else None,
                        "active": r.active,
                        "dernier": derniers.get((motif.id, agent.id, r.etape)),
                    }
                    for r in regles
                    if r.motif == motif.id and r.portee == "etape"
                ]
                motifs.append(
                    {
                        "motif": motif.id,
                        "famille": motif.famille,
                        "libelle": _texte(motif.libelle_fr, motif.libelle_en),
                        "quand": _texte(motif.quand_fr, motif.quand_en),
                        "eteinte": _texte(motif.eteinte_fr, motif.eteinte_en),
                        "a_un_delai": motif.a_un_delai,
                        "variantes": list(phrase.variantes) if phrase else [],
                        "delai_s": phrase.delai_s if phrase else None,
                        "active": bool(phrase and phrase.dite),
                        "niveau": phrase.niveau if phrase else None,
                        "etapes": etapes,
                        "dernier": derniers.get((motif.id, agent.id)),
                    }
                )
            carte["agents"].append(
                {
                    "id": agent.id,
                    "nom": agent.nom,
                    "est_principal": agent.est_principal,
                    "motifs": motifs,
                    "lecture": lecture_du_graphe(agent.graphe),
                }
            )
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[phrases] carte de l'agent {agent.id} illisible : {erreur!r}")
    carte["actions"] = [
        {"fichier": fichier, "description": description}
        for fichier, endroits in INVENTAIRE_DU_CODE.items()
        for nature, description in endroits
        if nature == NATURE_ACTION
    ]
    return carte


async def carte_de_l_agent(workflow_id: int, organization_id: int, *, runs: int = 20) -> dict | None:
    """La carte vue depuis ``workflow_id`` : lui seul, ou tout le groupe s'il en est le principal ;
    les derniers déclenchements lus dans ses ``runs`` derniers appels. ``None`` : agent introuvable
    dans l'organisation."""
    from api.db import db_client

    workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
    if workflow is None:
        return None

    def agent_de(w: Any, *, est_principal: bool) -> AgentDeLaCarte:
        definition = getattr(w, "current_definition", None)
        return AgentDeLaCarte(
            id=w.id,
            nom=w.name,
            reglages=getattr(definition, "workflow_configurations", None) or {},
            graphe=getattr(definition, "workflow_json", None) or {},
            est_principal=est_principal,
        )

    premier = agent_de(workflow, est_principal=False)
    reglages = premier.reglages or {}
    agents = [premier]
    principal = reglages
    # Les appels d'un groupe sont enregistrés sous le principal : c'est là que la trace se lit.
    runs_de = workflow_id
    membres = reglages.get("agents_specialises")
    if isinstance(membres, list):
        premier.est_principal = True
        for membre_id in membres:
            try:
                membre = await db_client.get_workflow(int(membre_id), organization_id=organization_id)
            except Exception:  # noqa: BLE001
                membre = None
            if membre is not None:
                agents.append(agent_de(membre, est_principal=False))
    elif reglages.get("agent_principal_id"):
        try:
            chef = await db_client.get_workflow(
                int(reglages["agent_principal_id"]), organization_id=organization_id
            )
        except Exception:  # noqa: BLE001 -- un identifiant illisible : la carte de l'agent seul
            chef = None
        if chef is not None:
            principal = getattr(chef.current_definition, "workflow_configurations", None) or {}
            runs_de = chef.id

    traces = []
    try:
        lus, _total = await db_client.get_workflow_runs_by_workflow_id(
            runs_de, organization_id=organization_id, limit=runs
        )
        for run in lus:
            contexte = getattr(run, "gathered_context", None) or {}
            traces.append(
                (
                    getattr(run, "id", None),
                    str(getattr(run, "created_at", "") or ""),
                    contexte.get("phrases_du_code") or [],
                )
            )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] runs illisibles pour la carte : {erreur!r}")
    return construire_la_carte(agents, principal, derniers_declenchements(traces))
