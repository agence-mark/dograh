"""[.mark] Chantier agents-specialises, lot 10 (A9, A10) : gérer un groupe d'agents.

Un groupe = un agent principal + ses agents spécialisés, rangés dans un sous-dossier. Le lien
est porté **des deux côtés** dans les réglages JSON (``agents_specialises`` sur le principal,
``agent_principal_id`` sur chaque spécialisé) : le sous-dossier est l'affichage, le JSON est la
vérité. Ce module orchestre : créer un principal, créer un spécialisé, le retirer ou l'archiver,
recopier les réglages communs, dupliquer un groupe.

Règles :

- tout est lu et écrit **sous l'organisation de l'appelant** (``organization_id`` à chaque
  accès) : un identifiant d'agent écrit dans des réglages mais pas de cette organisation
  n'existe pas ici ;
- une modification d'agent se range en **brouillon** (comme un enregistrement de l'écran) ; la
  publication du groupe est un geste à part ;
- aucun mot de métier : des noms génériques, des phrases neutres (les prompts réels sont
  réglés à l'écran).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from loguru import logger

from api.db import db_client
from api.db.folder_client import FolderNameConflictError
from api.enums import ToolCategory
from api.services.groupe.passations import (
    CLE_AGENT_PRINCIPAL,
    CLE_AGENTS_SPECIALISES,
    CLE_PLAFOND,
    MARQUEUR_RETOUR,
    PLAFOND_DEFAUT,
)
from api.services.groupe.reglages import CLE_CERVEAU_PROPRE, recopier
from api.services.workflow.tools.custom_tool import custom_tool_function_name


class GroupeError(ValueError):
    """Erreur de gestion de groupe, avec un code HTTP adapté."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class AgentDeTravail:
    """Un agent tel qu'on le travaille : le brouillon s'il existe, sinon la version publiée."""

    id: int
    nom: str
    folder_id: int | None
    definition: dict
    reglages: dict
    variables: dict
    a_un_brouillon: bool = False
    statut: str = "active"
    outils: list[str] = field(default_factory=list)


def _entier(valeur: Any) -> int | None:
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        return valeur
    if isinstance(valeur, str) and valeur.strip().isdigit():
        return int(valeur.strip())
    return None


def _liste_d_entiers(valeur: Any) -> list[int]:
    if not isinstance(valeur, list):
        return []
    sortie: list[int] = []
    for element in valeur:
        n = _entier(element)
        if n is not None and n not in sortie:
            sortie.append(n)
    return sortie


async def lire_agent(workflow_id: int, organization_id: int) -> AgentDeTravail | None:
    """L'agent (brouillon d'abord) sous cette organisation, ``None`` s'il n'y est pas."""
    workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
    if workflow is None:
        return None
    brouillon = await db_client.get_draft_version(workflow_id)
    base = brouillon or workflow.released_definition
    definition = copy.deepcopy((base.workflow_json if base else None) or {})
    return AgentDeTravail(
        id=workflow.id,
        nom=workflow.name,
        folder_id=workflow.folder_id,
        definition=definition,
        reglages=copy.deepcopy((base.workflow_configurations if base else None) or {}),
        variables=copy.deepcopy((base.template_context_variables if base else None) or {}),
        a_un_brouillon=brouillon is not None,
        statut=workflow.status,
    )


def specialises_de(reglages: Mapping[str, Any] | None) -> list[int]:
    return _liste_d_entiers((reglages or {}).get(CLE_AGENTS_SPECIALISES))


# ---------------------------------------------------------------------------
# Graphes de départ (génériques : les prompts réels se règlent à l'écran)
# ---------------------------------------------------------------------------


def graphe_minimal_du_specialise() -> dict:
    """Qualification › coordonnées › retour au principal (A1) : trois étapes, la dernière
    marquée ``retour_au_principal``, sans prompt global, sans outil, **sans nœud de fin**."""
    return {
        "nodes": [
            {
                "id": "1",
                "type": "startCall",
                "position": {"x": 175, "y": 60},
                "data": {
                    "name": "Qualification",
                    "prompt": "Qualifie la demande de l'appelant dans ce domaine, puis passe à l'étape suivante.",
                    "is_start": True,
                    "allow_interrupt": False,
                    "add_global_prompt": True,
                },
            },
            {
                "id": "2",
                "type": "agentNode",
                "position": {"x": 175, "y": 260},
                "data": {
                    "name": "Coordonnées",
                    "prompt": "Recueille les coordonnées nécessaires, puis demande si l'appelant a besoin d'autre chose.",
                    "allow_interrupt": False,
                    "add_global_prompt": True,
                },
            },
            {
                "id": "3",
                "type": "agentNode",
                "position": {"x": 175, "y": 460},
                "data": {
                    "name": "Retour au principal",
                    "prompt": "L'appel revient à l'agent principal.",
                    "allow_interrupt": False,
                    "add_global_prompt": False,
                    MARQUEUR_RETOUR: True,
                },
            },
        ],
        "edges": [
            {
                "id": "1-2",
                "source": "1",
                "target": "2",
                "data": {
                    "label": "Coordonnées",
                    "condition": "Quand la demande est qualifiée, passer aux coordonnées.",
                },
            },
            {
                "id": "2-3",
                "source": "2",
                "target": "3",
                "data": {
                    "label": "Retour au principal",
                    "condition": "Quand les coordonnées sont recueillies et que la dernière question a été posée, rendre la main.",
                },
            },
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 0.75},
    }


def graphe_minimal_du_principal() -> dict:
    """Une étape de qualification (qui portera les outils de passation) et un nœud de fin."""
    return {
        "nodes": [
            {
                "id": "1",
                "type": "startCall",
                "position": {"x": 175, "y": 60},
                "data": {
                    "name": "Qualification",
                    "prompt": "Accueille l'appelant, qualifie sa demande et passe la main à l'agent spécialisé qui convient.",
                    "is_start": True,
                    "allow_interrupt": False,
                    "add_global_prompt": True,
                },
            },
            {
                "id": "2",
                "type": "endCall",
                "position": {"x": 175, "y": 280},
                "data": {
                    "name": "Fin",
                    "prompt": "Remercie l'appelant et termine l'appel.",
                    "is_end": True,
                    "allow_interrupt": False,
                    "add_global_prompt": False,
                },
            },
        ],
        "edges": [
            {
                "id": "1-2",
                "source": "1",
                "target": "2",
                "data": {
                    "label": "Fin",
                    "condition": "Quand l'appelant n'a plus rien à demander, terminer l'appel.",
                },
            }
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 0.75},
    }


# ---------------------------------------------------------------------------
# Dossiers
# ---------------------------------------------------------------------------


async def _creer_sous_dossier(
    nom: str, organization_id: int, parent_id: int | None
):
    """Crée le sous-dossier du groupe ; un nom déjà pris reçoit un numéro (nom unique par
    organisation)."""
    candidat = nom.strip() or "Groupe"
    for n in range(1, 50):
        essai = candidat if n == 1 else f"{candidat} ({n})"
        try:
            return await db_client.create_folder(
                name=essai, organization_id=organization_id, parent_id=parent_id
            )
        except FolderNameConflictError:
            continue
    raise GroupeError("Impossible de nommer le sous-dossier du groupe.", status_code=409)


# ---------------------------------------------------------------------------
# Outils de passation
# ---------------------------------------------------------------------------


def _nom_d_outil_de_passation(nom_cible: str, deja_pris: set[str]) -> str:
    base = f"Passer à {nom_cible.strip() or 'agent'}"
    nom = base
    n = 2
    while custom_tool_function_name(nom) in deja_pris or not custom_tool_function_name(nom):
        nom = f"{base} {n}"
        n += 1
    return nom


async def _noms_de_fonctions_du_noeud(donnees: Mapping, organization_id: int) -> set[str]:
    uuids = [u for u in (donnees.get("tool_uuids") or []) if isinstance(u, str)]
    outils = await db_client.get_tools_by_uuids(uuids, organization_id)
    return {custom_tool_function_name(o.name) for o in outils}


async def creer_outil_de_passation(
    *, organization_id: int, user_id: int, cible_id: int, cible_nom: str, deja_pris: set[str]
):
    """L'outil ``transfer_agent`` qui mène à ``cible_id`` : sans annonce et sans accueil
    (une seule voix pour l'appelant, A21). Un outil, une destination."""
    return await db_client.create_tool(
        organization_id=organization_id,
        user_id=user_id,
        name=_nom_d_outil_de_passation(cible_nom, deja_pris),
        description=(
            f"Passe l'appel à l'agent « {cible_nom} ». À utiliser quand la demande de l'appelant "
            "relève de cet agent : décris ici dans quel cas."
        ),
        category=ToolCategory.TRANSFER_AGENT.value,
        definition={
            "schema_version": 1,
            "type": ToolCategory.TRANSFER_AGENT.value,
            "config": {
                "workflow_id": cible_id,
                "message": "",
                "play_greeting": False,
            },
        },
    )


async def etape_de_qualification(definition: Mapping, organization_id: int) -> dict | None:
    """L'étape du principal qui porte les outils de passation : celle qui en porte déjà, sinon
    l'étape de départ. ``None`` si le graphe n'a rien de tel."""
    noeuds = [n for n in (definition or {}).get("nodes") or [] if isinstance(n, dict)]
    tous = [
        u
        for n in noeuds
        for u in ((n.get("data") or {}).get("tool_uuids") or [])
        if isinstance(u, str)
    ]
    passations: set[str] = set()
    if tous:
        for outil in await db_client.get_tools_by_uuids(sorted(set(tous)), organization_id):
            if outil.category == ToolCategory.TRANSFER_AGENT.value:
                passations.add(outil.tool_uuid)
    for noeud in noeuds:
        uuids = (noeud.get("data") or {}).get("tool_uuids") or []
        if any(u in passations for u in uuids):
            return noeud
    for noeud in noeuds:
        if noeud.get("type") == "startCall":
            return noeud
    return None


async def _outils_de_passation_vers(
    definition: Mapping, cible_id: int, organization_id: int
) -> set[str]:
    """Les uuid des outils de passation du graphe qui mènent à ``cible_id``."""
    tous = sorted(
        {
            u
            for n in (definition or {}).get("nodes") or []
            if isinstance(n, dict)
            for u in ((n.get("data") or {}).get("tool_uuids") or [])
            if isinstance(u, str)
        }
    )
    visees: set[str] = set()
    for outil in await db_client.get_tools_by_uuids(tous, organization_id):
        if outil.category != ToolCategory.TRANSFER_AGENT.value:
            continue
        vers = _entier((((outil.definition or {}).get("config")) or {}).get("workflow_id"))
        if vers == cible_id:
            visees.add(outil.tool_uuid)
    return visees


def _retirer_outils(definition: dict, uuids: set[str]) -> int:
    """Retire ces outils de toutes les étapes ; rend combien de pose ont été retirées."""
    retires = 0
    for noeud in definition.get("nodes") or []:
        donnees = (noeud or {}).get("data") or {}
        actuels = donnees.get("tool_uuids")
        if not isinstance(actuels, list):
            continue
        reste = [u for u in actuels if u not in uuids]
        retires += len(actuels) - len(reste)
        if reste:
            donnees["tool_uuids"] = reste
        else:
            donnees.pop("tool_uuids", None)
    return retires


async def _enregistrer(
    agent: AgentDeTravail,
    organization_id: int,
    *,
    definition: dict | None = None,
    reglages: dict | None = None,
) -> None:
    """Range une modification d'agent en brouillon (comme l'enregistrement de l'écran)."""
    await db_client.update_workflow(
        workflow_id=agent.id,
        name=None,
        workflow_definition=definition,
        template_context_variables=None,
        workflow_configurations=reglages,
        organization_id=organization_id,
    )


# ---------------------------------------------------------------------------
# Créer
# ---------------------------------------------------------------------------


async def creer_principal(
    *, nom: str, organization_id: int, user_id: int, dossier_parent_id: int | None
) -> tuple[int, int]:
    """Le principal d'un nouveau groupe, son sous-dossier, rangés ensemble. Rend
    ``(id de l'agent, id du sous-dossier)``."""
    if dossier_parent_id is not None:
        parent = await db_client.get_folder(dossier_parent_id, organization_id=organization_id)
        if parent is None:
            raise GroupeError(f"Folder with id {dossier_parent_id} not found", status_code=404)
    dossier = await _creer_sous_dossier(nom, organization_id, dossier_parent_id)
    workflow = await db_client.create_workflow(
        nom, graphe_minimal_du_principal(), user_id, organization_id
    )
    await db_client.move_workflow_to_folder(
        workflow_id=workflow.id, folder_id=dossier.id, organization_id=organization_id
    )
    await db_client.update_workflow(
        workflow_id=workflow.id,
        name=None,
        workflow_definition=None,
        template_context_variables=None,
        workflow_configurations={
            CLE_AGENTS_SPECIALISES: [],
            CLE_PLAFOND: PLAFOND_DEFAUT,
        },
        organization_id=organization_id,
    )
    return workflow.id, dossier.id


async def _dossier_du_groupe(principal: AgentDeTravail, organization_id: int) -> int | None:
    """Le sous-dossier du groupe : celui du principal quand il est déjà l'entête d'un groupe
    (la clé ``agents_specialises`` existe, même vide : posée par ``creer_principal`` ou par
    une création précédente), sinon un nouveau sous-dossier du dossier du principal, où le
    principal rejoint son premier spécialisé."""
    if principal.folder_id is not None and CLE_AGENTS_SPECIALISES in principal.reglages:
        return principal.folder_id
    dossier = await _creer_sous_dossier(principal.nom, organization_id, principal.folder_id)
    await db_client.move_workflow_to_folder(
        workflow_id=principal.id, folder_id=dossier.id, organization_id=organization_id
    )
    return dossier.id


async def creer_specialise(
    *, principal_id: int, nom: str, organization_id: int, user_id: int
) -> int:
    """Crée un spécialisé : graphe minimal, clés communes copiées, rangé dans le sous-dossier
    du groupe, inscrit des deux côtés, et l'outil de passation vers lui posé sur l'étape de
    qualification du principal. Rend l'id du nouvel agent."""
    principal = await lire_agent(principal_id, organization_id)
    if principal is None:
        raise GroupeError(f"Workflow with id {principal_id} not found", status_code=404)
    if _entier(principal.reglages.get(CLE_AGENT_PRINCIPAL)) is not None:
        raise GroupeError(
            "Un agent spécialisé ne peut pas être le principal d'un groupe.", status_code=409
        )
    nom = (nom or "").strip()
    if not nom:
        raise GroupeError("Le nom du spécialisé est vide.", status_code=422)

    dossier_id = await _dossier_du_groupe(principal, organization_id)
    nouveau = await db_client.create_workflow(
        nom, graphe_minimal_du_specialise(), user_id, organization_id
    )
    if dossier_id is not None:
        await db_client.move_workflow_to_folder(
            workflow_id=nouveau.id, folder_id=dossier_id, organization_id=organization_id
        )

    reglages = recopier(principal.reglages, {CLE_AGENT_PRINCIPAL: principal.id})
    await db_client.update_workflow(
        workflow_id=nouveau.id,
        name=None,
        workflow_definition=None,
        template_context_variables=copy.deepcopy(principal.variables) or None,
        workflow_configurations=reglages,
        organization_id=organization_id,
    )

    # Côté principal : le lien, et l'outil de passation sur l'étape de qualification.
    definition = principal.definition
    etape = await etape_de_qualification(definition, organization_id)
    reglages_principal = dict(principal.reglages)
    reglages_principal[CLE_AGENTS_SPECIALISES] = [
        *specialises_de(principal.reglages),
        nouveau.id,
    ]
    reglages_principal.setdefault(CLE_PLAFOND, PLAFOND_DEFAUT)
    definition_modifiee: dict | None = None
    if etape is not None:
        donnees = etape.setdefault("data", {})
        outil = await creer_outil_de_passation(
            organization_id=organization_id,
            user_id=user_id,
            cible_id=nouveau.id,
            cible_nom=nom,
            deja_pris=await _noms_de_fonctions_du_noeud(donnees, organization_id),
        )
        donnees["tool_uuids"] = [*(donnees.get("tool_uuids") or []), outil.tool_uuid]
        definition_modifiee = definition
    else:
        logger.warning(
            "groupe : le principal {} n'a pas d'étape de qualification, outil de passation non posé",
            principal.id,
        )
    await _enregistrer(
        principal, organization_id, definition=definition_modifiee, reglages=reglages_principal
    )
    return nouveau.id


# ---------------------------------------------------------------------------
# Recopier
# ---------------------------------------------------------------------------


async def recopier_dans_les_specialises(
    principal_id: int, organization_id: int
) -> list[int]:
    """L'enregistrement du principal recopie les clés communes dans ses spécialisés (un seul
    geste, idempotent : un spécialisé déjà à jour n'est pas réécrit). Rend les agents
    réécrits. Ne lève jamais : un échec ne coûte pas l'enregistrement du principal."""
    ecrits: list[int] = []
    try:
        principal = await lire_agent(principal_id, organization_id)
        if principal is None:
            return ecrits
        for sid in specialises_de(principal.reglages):
            specialise = await lire_agent(sid, organization_id)
            if specialise is None:
                continue
            if _entier(specialise.reglages.get(CLE_AGENT_PRINCIPAL)) != principal.id:
                continue  # lien à sens unique : ce n'est pas un spécialisé de ce principal
            neuf = recopier(principal.reglages, specialise.reglages)
            if neuf == specialise.reglages:
                continue
            await _enregistrer(specialise, organization_id, reglages=neuf)
            ecrits.append(sid)
    except Exception as erreur:  # noqa: BLE001
        logger.warning("groupe : recopie des réglages du principal {} : {}", principal_id, erreur)
    return ecrits


# ---------------------------------------------------------------------------
# Retirer, archiver
# ---------------------------------------------------------------------------


async def _retirer_du_principal(
    principal: AgentDeTravail, specialise_id: int, organization_id: int
) -> None:
    """Côté principal : ôte le spécialisé de la liste et l'outil de passation qui le vise."""
    reglages = dict(principal.reglages)
    reglages[CLE_AGENTS_SPECIALISES] = [
        i for i in specialises_de(principal.reglages) if i != specialise_id
    ]
    definition = copy.deepcopy(principal.definition)
    visees = await _outils_de_passation_vers(definition, specialise_id, organization_id)
    changee = _retirer_outils(definition, visees) > 0
    await _enregistrer(
        principal,
        organization_id,
        definition=definition if changee else None,
        reglages=reglages,
    )


async def retirer_du_groupe(*, specialise_id: int, organization_id: int) -> None:
    """Un spécialisé retiré du groupe redevient un agent seul : plus de lien, plus d'outil de
    passation chez le principal, son graphe et ses réglages gardés. Il sort du sous-dossier
    du groupe vers le dossier parent."""
    specialise = await lire_agent(specialise_id, organization_id)
    if specialise is None:
        raise GroupeError(f"Workflow with id {specialise_id} not found", status_code=404)
    principal_id = _entier(specialise.reglages.get(CLE_AGENT_PRINCIPAL))
    if principal_id is None:
        raise GroupeError("Cet agent n'est pas un spécialisé.", status_code=409)

    principal = await lire_agent(principal_id, organization_id)
    if principal is not None:
        await _retirer_du_principal(principal, specialise_id, organization_id)
    reglages = dict(specialise.reglages)
    reglages.pop(CLE_AGENT_PRINCIPAL, None)
    reglages.pop(CLE_CERVEAU_PROPRE, None)
    await _enregistrer(specialise, organization_id, reglages=reglages)

    if specialise.folder_id is not None:
        dossier = await db_client.get_folder(specialise.folder_id, organization_id=organization_id)
        await db_client.move_workflow_to_folder(
            workflow_id=specialise_id,
            folder_id=dossier.parent_id if dossier is not None else None,
            organization_id=organization_id,
        )


async def archiver_specialise(*, specialise_id: int, organization_id: int) -> None:
    """Supprimer (archiver) un spécialisé retire d'abord l'outil de passation qui le vise chez
    le principal : sans cela, le principal passerait la main à un agent disparu."""
    specialise = await lire_agent(specialise_id, organization_id)
    if specialise is None:
        raise GroupeError(f"Workflow with id {specialise_id} not found", status_code=404)
    principal_id = _entier(specialise.reglages.get(CLE_AGENT_PRINCIPAL))
    if principal_id is not None:
        principal = await lire_agent(principal_id, organization_id)
        if principal is not None:
            await _retirer_du_principal(principal, specialise_id, organization_id)
    await db_client.update_workflow_status(
        workflow_id=specialise_id, status="archived", organization_id=organization_id
    )


async def archiver_principal(
    *, principal_id: int, organization_id: int, specialises: str
) -> list[int]:
    """Supprimer (archiver) un principal : ses spécialisés sont gardés comme agents seuls
    (``specialises="garder"``) ou archivés avec lui (``"archiver"``). Rend les ids touchés."""
    if specialises not in ("garder", "archiver"):
        raise GroupeError("specialises : « garder » ou « archiver ».", status_code=422)
    principal = await lire_agent(principal_id, organization_id)
    if principal is None:
        raise GroupeError(f"Workflow with id {principal_id} not found", status_code=404)
    touches: list[int] = []
    for sid in specialises_de(principal.reglages):
        specialise = await lire_agent(sid, organization_id)
        if specialise is None:
            continue
        if specialises == "archiver":
            await db_client.update_workflow_status(
                workflow_id=sid, status="archived", organization_id=organization_id
            )
        else:
            reglages = dict(specialise.reglages)
            reglages.pop(CLE_AGENT_PRINCIPAL, None)
            reglages.pop(CLE_CERVEAU_PROPRE, None)
            await _enregistrer(specialise, organization_id, reglages=reglages)
        touches.append(sid)
    await db_client.update_workflow_status(
        workflow_id=principal_id, status="archived", organization_id=organization_id
    )
    return touches


# ---------------------------------------------------------------------------
# Lire le groupe (pour l'écran)
# ---------------------------------------------------------------------------


async def lire_groupe(workflow_id: int, organization_id: int) -> dict | None:
    """Le groupe d'un agent : son principal et ses spécialisés (id, nom, cerveau propre).
    ``None`` pour un agent seul."""
    agent = await lire_agent(workflow_id, organization_id)
    if agent is None:
        return None
    principal_id = _entier(agent.reglages.get(CLE_AGENT_PRINCIPAL))
    principal = agent
    if principal_id is not None:
        principal = await lire_agent(principal_id, organization_id)
        if principal is None:
            return {
                "principal": None,
                "agent_principal_id": principal_id,
                "specialises": [],
            }
    ids = specialises_de(principal.reglages)
    if principal_id is None and CLE_AGENTS_SPECIALISES not in principal.reglages:
        return None
    membres = []
    for sid in ids:
        s = await lire_agent(sid, organization_id)
        if s is None:
            continue
        membres.append(
            {
                "id": s.id,
                "name": s.nom,
                "cerveau_propre": s.reglages.get(CLE_CERVEAU_PROPRE) is True,
                "folder_id": s.folder_id,
                "status": s.statut,
            }
        )
    return {
        "principal": {"id": principal.id, "name": principal.nom, "folder_id": principal.folder_id},
        "agent_principal_id": principal.id,
        "specialises": membres,
    }


# ---------------------------------------------------------------------------
# Dupliquer un groupe
# ---------------------------------------------------------------------------


async def dupliquer_les_specialises(
    *, source_principal_id: int, copie_principal_id: int, organization_id: int, user_id: int
) -> list[int]:
    """Après la duplication d'un principal : duplique chacun de ses spécialisés, les range dans
    un nouveau sous-dossier avec la copie du principal, les relie dans les deux sens et
    repointe les outils de passation de la copie vers les copies. Rend les ids des copies.
    Un agent seul n'est pas concerné (rend une liste vide)."""
    from api.services.workflow.duplicate import duplicate_workflow

    source = await lire_agent(source_principal_id, organization_id)
    copie = await lire_agent(copie_principal_id, organization_id)
    if source is None or copie is None:
        return []
    if _entier(source.reglages.get(CLE_AGENT_PRINCIPAL)) is not None:
        # La copie d'un spécialisé est un agent seul : elle n'est dans la liste de personne,
        # elle ne se dit pas spécialisée (graphe et réglages gardés).
        reglages = dict(copie.reglages)
        reglages.pop(CLE_AGENT_PRINCIPAL, None)
        reglages.pop(CLE_CERVEAU_PROPRE, None)
        await _enregistrer(copie, organization_id, reglages=reglages)
        return []
    anciens = [
        i for i in specialises_de(source.reglages)
        if (await lire_agent(i, organization_id)) is not None
    ]
    if not anciens and CLE_AGENTS_SPECIALISES not in source.reglages:
        return []

    source_wf = await db_client.get_workflow(source.id, organization_id=organization_id)
    parent_du_groupe = None
    if source_wf is not None and source_wf.folder_id is not None:
        dossier_source = await db_client.get_folder(
            source_wf.folder_id, organization_id=organization_id
        )
        parent_du_groupe = dossier_source.parent_id if dossier_source else None
    dossier = await _creer_sous_dossier(f"{copie.nom}", organization_id, parent_du_groupe)
    await db_client.move_workflow_to_folder(
        workflow_id=copie.id, folder_id=dossier.id, organization_id=organization_id
    )

    correspondance: dict[int, int] = {}
    for ancien in anciens:
        nouveau = await duplicate_workflow(
            workflow_id=ancien, organization_id=organization_id, user_id=user_id
        )
        correspondance[ancien] = nouveau.id
        await db_client.move_workflow_to_folder(
            workflow_id=nouveau.id, folder_id=dossier.id, organization_id=organization_id
        )

    # Les liens, des deux côtés, vers les copies.
    for nouveau_id in correspondance.values():
        specialise = await lire_agent(nouveau_id, organization_id)
        if specialise is None:
            continue
        reglages = dict(specialise.reglages)
        reglages[CLE_AGENT_PRINCIPAL] = copie.id
        await _enregistrer(specialise, organization_id, reglages=reglages)

    reglages_copie = dict(copie.reglages)
    reglages_copie[CLE_AGENTS_SPECIALISES] = list(correspondance.values())
    definition = copy.deepcopy(copie.definition)
    for ancien, nouveau_id in correspondance.items():
        visees = await _outils_de_passation_vers(definition, ancien, organization_id)
        for uuid in visees:
            outil = (await db_client.get_tools_by_uuids([uuid], organization_id) or [None])[0]
            if outil is None:
                continue
            definition_outil = copy.deepcopy(outil.definition or {})
            definition_outil.setdefault("config", {})["workflow_id"] = nouveau_id
            nouvel_outil = await db_client.create_tool(
                organization_id=organization_id,
                user_id=user_id,
                name=outil.name,
                description=outil.description,
                category=outil.category,
                icon=outil.icon,
                icon_color=outil.icon_color,
                definition=definition_outil,
            )
            for noeud in definition.get("nodes") or []:
                donnees = (noeud or {}).get("data") or {}
                if isinstance(donnees.get("tool_uuids"), list):
                    donnees["tool_uuids"] = [
                        nouvel_outil.tool_uuid if u == uuid else u for u in donnees["tool_uuids"]
                    ]
    await _enregistrer(copie, organization_id, definition=definition, reglages=reglages_copie)
    return list(correspondance.values())


async def preparer_l_archivage(workflow_id: int, organization_id: int) -> None:
    """Avant d'archiver un agent (route d'état) : un spécialisé disparaît de son principal
    (liste et outil de passation) ; les spécialisés d'un principal archivé deviennent des
    agents seuls. Ne lève jamais : l'archivage d'un agent reste possible quoi qu'il arrive."""
    try:
        agent = await lire_agent(workflow_id, organization_id)
        if agent is None:
            return
        principal_id = _entier(agent.reglages.get(CLE_AGENT_PRINCIPAL))
        if principal_id is not None:
            principal = await lire_agent(principal_id, organization_id)
            if principal is not None:
                await _retirer_du_principal(principal, workflow_id, organization_id)
            return
        for sid in specialises_de(agent.reglages):
            specialise = await lire_agent(sid, organization_id)
            if specialise is None:
                continue
            reglages = dict(specialise.reglages)
            reglages.pop(CLE_AGENT_PRINCIPAL, None)
            reglages.pop(CLE_CERVEAU_PROPRE, None)
            await _enregistrer(specialise, organization_id, reglages=reglages)
    except Exception as erreur:  # noqa: BLE001
        logger.warning("groupe : préparation de l'archivage de {} : {}", workflow_id, erreur)


async def liens_des_groupes(organization_id: int) -> list[dict]:
    """Les agents actifs qui sont dans un groupe, avec leur rôle (``principal`` ou
    ``specialise``) : pour la liste d'agents. Un lien écrit mais qui ne mène à aucun agent
    actif de l'organisation n'est pas rendu (un spécialisé sans principal retrouvé n'est
    plus spécialisé pour l'écran)."""
    agents = dict(await db_client.list_agent_configurations(organization_id))
    sortie: list[dict] = []
    for agent_id, reglages in agents.items():
        principal_id = _entier(reglages.get(CLE_AGENT_PRINCIPAL))
        if principal_id is not None and principal_id in agents and principal_id != agent_id:
            sortie.append(
                {
                    "id": agent_id,
                    "role": "specialise",
                    "agent_principal_id": principal_id,
                    "agents_specialises": [],
                    "cerveau_propre": reglages.get(CLE_CERVEAU_PROPRE) is True,
                }
            )
        elif CLE_AGENTS_SPECIALISES in reglages:
            sortie.append(
                {
                    "id": agent_id,
                    "role": "principal",
                    "agent_principal_id": None,
                    "agents_specialises": [
                        i
                        for i in specialises_de(reglages)
                        if i in agents
                        and _entier(agents[i].get(CLE_AGENT_PRINCIPAL)) == agent_id
                    ],
                    "cerveau_propre": False,
                }
            )
    return sortie
