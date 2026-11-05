"""[.mark] Builder partie 3, N1 (sous-lot 1) : les gestes de personne entrés au registre (05, « Le builder peut tout faire »).

Jusqu'ici interdits codés (``INTERDITES``), ils existent désormais ; c'est la PERMISSION qui décide (``modes.py`` : famille, mode du chat,
rôle de la personne, carte d'autorisation). Chaque action rejoue EXACTEMENT le geste de l'écran (même fonction, mêmes contrôles, même
journal) au nom de la personne du chat :

* ``agent_publier``       : publier le brouillon de l'agent (``publier_un_agent`` : contrôles bloquants compris, jamais forcé) ;
* ``groupe_publier``      : publier un groupe, spécialisés d'abord, arrêt au premier refus (route du groupe) ;
* ``branche_publier``     : publier le brouillon d'une branche ;
* ``branche_fusionner``   : fusionner une branche dans la principale (relue d'après l'aperçu lu ici ; une principale protégée exige la
  relecture d'une personne à l'écran : refusée ici) ;
* ``repartition_regler``  : la répartition du trafic entre branches ;
* ``agent_archiver``      : archiver un agent (irréversible pour le builder : une personne le restaure) ;
* ``outil_supprimer``     : archiver un outil (suppression douce, comme l'écran) ;
* ``bibliotheque_marquer`` · ``bibliotheque_accepter_proposition`` · ``bibliotheque_refuser_proposition`` · ``bibliotheque_retour_arriere`` :
  les clics de la bibliothèque (équipe .mark depuis le Labo, comme l'écran).

Écran seulement (``mcp=False``) : la porte Claude Code n'a pas encore de mode de chat ; elle n'a donc aucun de ces gestes. Aucun appel réel.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from api.db.branches_client import ErreurDeBranche
from api.services.builder.actions._commun import agent_de_l_organisation
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer


def _detail(erreur: HTTPException) -> str:
    """Le refus de l'écran, lisible par le cerveau (jamais une pile) ; borné."""
    detail = erreur.detail
    if isinstance(detail, dict):
        messages = [str(e.get("message", e)) for e in (detail.get("errors") or []) if isinstance(e, dict)]
        texte = "; ".join(messages) or str(detail.get("message") or detail)
    else:
        texte = str(detail)
    return texte[:600]


def _refus_http(erreur: HTTPException) -> ErreurAction:
    return ErreurAction(f"Refused by the screen's checks: {_detail(erreur)}", "refus_ecran")


async def _journaliser(contexte: Contexte, quoi: str, detail: dict[str, Any]) -> None:
    from api.services.equipe_mark.acces import journaliser

    await journaliser(contexte.user, quoi, contexte.organisation_id, {**detail, "par": "builder"})


class _Agent(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent (default: the agent of this conversation).")


class _Groupe(_Agent):
    specialises: list[int] | None = Field(default=None, max_length=50, description="Only these specialised agents; omitted: all of them.")
    avec_le_principal: bool = Field(default=True, description="Publish the main agent of the group last.")


class _Branche(_Agent):
    branche_id: int = Field(ge=1, description="The branch (branches_lire gives the ids).")


class _Fusion(_Branche):
    choix: dict[str, str] = Field(default_factory=dict, description="Field key -> 'source' or 'cible'; one per conflict of the preview.")


class _Repartition(_Agent):
    parts: dict[int, int] = Field(description="Branch id -> share of the calls, whole numbers adding up to 100 (every active branch).")


class _Outil(BaseModel):
    outil: str = Field(min_length=1, max_length=64, description="The tool uuid (list_tools gives it).")


class _Marquer(BaseModel):
    famille: str = Field(min_length=1, max_length=64)
    slug: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=1)
    statut: Literal["recette", "rejete", "candidat"]
    raison: str | None = Field(default=None, max_length=1000, description="Why it is rejected (kept with the element).")


class _Proposition(BaseModel):
    identifiant: str = Field(min_length=1, max_length=64, description="The proposal id.")
    motif: str | None = Field(default=None, max_length=1000, description="Why (required to refuse).")


class _Retour(BaseModel):
    famille: str = Field(min_length=1, max_length=64)
    slug: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=1, description="The version to go back to.")


# --- publier ---------------------------------------------------------------------------------------------------------------------------


async def _agent_publier(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    from api.routes.workflow import publier_un_agent

    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        publie = await publier_un_agent(agent.id, contexte.user)
    except HTTPException as erreur:
        raise _refus_http(erreur) from None
    await _journaliser(contexte, "agents.publier", {"agent": agent.id, "version": publie.get("version_number")})
    return {"ok": True, "workflow_id": agent.id, "version": publie.get("version_number"), "statut": publie.get("status")}


async def _groupe_publier(contexte: Contexte, p: _Groupe) -> dict[str, Any]:
    from api.routes.groupe import PublierGroupeRequest, publier_le_groupe

    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        rendu = await publier_le_groupe(agent.id, PublierGroupeRequest(specialises=p.specialises, avec_le_principal=p.avec_le_principal), contexte.user)
    except HTTPException as erreur:
        raise _refus_http(erreur) from None
    vue = rendu.model_dump() if hasattr(rendu, "model_dump") else dict(rendu)
    await _journaliser(contexte, "agents.groupe_publie", {"agent": agent.id, "publies": [a["id"] for a in vue.get("publies", [])]})
    return {"ok": vue.get("refus") is None, **vue}


async def _branche_publier(contexte: Contexte, p: _Branche) -> dict[str, Any]:
    from api.services.branches import service

    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        version = await service.publier(contexte.organisation_id, agent, p.branche_id, getattr(contexte.user, "id", None))
    except ErreurDeBranche as erreur:
        raise ErreurAction(str(erreur), erreur.code) from None
    await _journaliser(contexte, "agents.branche_publiee", {"agent": agent.id, "branche": p.branche_id, "version": version.get("version_number")})
    return {"ok": True, **version}


async def _branche_fusionner(contexte: Contexte, p: _Fusion) -> dict[str, Any]:
    from api.services.branches import fusion

    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        apercu = await fusion.apercu_de_la_fusion(contexte.organisation_id, agent, p.branche_id)
        if apercu["protegee"]:
            raise ErreurAction(
                "The main branch is protected: a person reviews the merge field by field in the screen (Branches > Merge).", "relecture"
            )
        resultat = await fusion.fusionner(
            contexte.organisation_id,
            agent,
            p.branche_id,
            choix=p.choix,
            relue=False,
            version_branche=apercu["branche"]["id_version"],
            version_cible=apercu["cible"]["id_version"],
            user=contexte.user,
        )
    except ErreurDeBranche as erreur:
        raise ErreurAction(str(erreur), erreur.code) from None
    await _journaliser(contexte, "agents.branche_fusionnee", {"agent": agent.id, "branche": p.branche_id, "version": resultat.get("version")})
    return {"ok": True, **resultat}


async def _repartition_regler(contexte: Contexte, p: _Repartition) -> dict[str, Any]:
    from api.services.branches import service

    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        resultat = await service.regler_la_repartition(contexte.organisation_id, agent, p.parts)
    except ErreurDeBranche as erreur:
        raise ErreurAction(str(erreur), erreur.code) from None
    await _journaliser(contexte, "agents.repartition_du_trafic", {"agent": agent.id, "parts": resultat.get("parts")})
    return {"ok": True, **resultat}


# --- archiver, supprimer -------------------------------------------------------------------------------------------------------------


async def _agent_archiver(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    from api.db import db_client
    from api.services.groupe.groupe import preparer_l_archivage

    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    await preparer_l_archivage(agent.id, contexte.organisation_id)
    await db_client.update_workflow_status(workflow_id=agent.id, status="archived", organization_id=contexte.organisation_id)
    await _journaliser(contexte, "agents.archiver", {"agent": agent.id})
    return {"ok": True, "workflow_id": agent.id, "statut": "archived"}


async def _outil_supprimer(contexte: Contexte, p: _Outil) -> dict[str, Any]:
    from api.db import db_client

    if not await db_client.archive_tool(p.outil, contexte.organisation_id):
        raise ErreurAction(f"Tool {p.outil} not found.", "introuvable")
    await _journaliser(contexte, "outils.supprimer", {"outil": p.outil})
    return {"ok": True, "outil": p.outil, "statut": "archived"}


# --- la bibliothèque -----------------------------------------------------------------------------------------------------------------


async def _bibliotheque(appel) -> dict[str, Any]:
    try:
        rendu = await appel
    except HTTPException as erreur:
        raise _refus_http(erreur) from None
    return {"ok": True, "element": rendu.model_dump(mode="json") if hasattr(rendu, "model_dump") else rendu}


async def _marquer(contexte: Contexte, p: _Marquer) -> dict[str, Any]:
    from api.routes.builder_bibliotheque import ChangementDeStatut, changer_le_statut

    return await _bibliotheque(
        changer_le_statut(p.famille, p.slug, ChangementDeStatut(version=p.version, statut=p.statut, raison=p.raison), contexte.user)
    )


async def _accepter(contexte: Contexte, p: _Proposition) -> dict[str, Any]:
    from api.routes.builder_bibliotheque import Acceptation, accepter

    return await _bibliotheque(accepter(p.identifiant, Acceptation(motif=p.motif), contexte.user))


async def _refuser(contexte: Contexte, p: _Proposition) -> dict[str, Any]:
    from api.routes.builder_bibliotheque import Refus, refuser

    if not (p.motif or "").strip():
        raise ErreurAction("Say why the proposal is refused (motif).")
    return await _bibliotheque(refuser(p.identifiant, Refus(motif=p.motif), contexte.user))


async def _retour(contexte: Contexte, p: _Retour) -> dict[str, Any]:
    from api.routes.builder_bibliotheque import RetourArriere, revenir_en_arriere

    return await _bibliotheque(revenir_en_arriere(p.famille, p.slug, RetourArriere(version=p.version), contexte.user))


_GESTES: tuple[tuple[str, str, type[BaseModel], Any, str], ...] = (
    ("agent_publier", "Publish the agent's draft (same checks as the screen; a blocking check refuses, never forced).", _Agent, _agent_publier, "publication"),
    ("groupe_publier", "Publish a group of agents: specialised agents first, the main agent last; stops at the first refusal.", _Groupe, _groupe_publier, "publication"),
    ("branche_publier", "Publish the draft of a branch of the agent (the live version of the main branch does not move).", _Branche, _branche_publier, "publication"),
    ("branche_fusionner", "Merge a branch into the main branch (one choice per conflict of the preview). A protected main branch is merged by a person.", _Fusion, _branche_fusionner, "publication"),
    ("repartition_regler", "Set the share of the calls between the agent's branches (whole numbers adding up to 100).", _Repartition, _repartition_regler, "publication"),
    ("agent_archiver", "Archive an agent (a person restores it from the Archived list).", _Agent, _agent_archiver, "irreversible"),
    ("outil_supprimer", "Delete (archive) a tool of the organisation.", _Outil, _outil_supprimer, "irreversible"),
    ("bibliotheque_marquer", "Mark a library version as Recette, Rejeté (with the reason) or back to Candidat (the .mark team, from the Lab).", _Marquer, _marquer, "bibliotheque"),
    ("bibliotheque_accepter_proposition", "Accept a library proposal (the .mark team, from the Lab).", _Proposition, _accepter, "bibliotheque"),
    ("bibliotheque_refuser_proposition", "Refuse a library proposal, with the reason (the .mark team, from the Lab).", _Proposition, _refuser, "bibliotheque"),
    ("bibliotheque_retour_arriere", "Make an earlier version of a library element the current one (the .mark team, from the Lab).", _Retour, _retour, "bibliotheque"),
)

for _nom, _description, _parametres, _fonction, _groupe in _GESTES:
    enregistrer(
        Action(
            nom=_nom,
            description=_description,
            parametres=_parametres,
            fonction=_fonction,
            ecriture=True,
            mcp=False,
            groupe=_groupe,
        )
    )
