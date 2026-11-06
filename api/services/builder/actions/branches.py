"""[.mark] Partie 3, SA-L3d (sous-lot 2, audit 12 § 2 « Builder ») : le builder et les branches d'agent.

Le builder peut créer une branche, y travailler, passer un outil à une autre version et lire la répartition du trafic :

* ``branches_lire`` : les branches de l'agent, leurs versions et brouillons, la part de trafic de chacune (lecture) ;
* ``branche_creer`` : une branche à 0 % du trafic, avec le brouillon de la personne (les appels en cours ne bougent pas) ;
* ``branche_travailler`` : le travail suivant (brouillon, réglages, outils, tests) se fait sur CETTE branche, ou de nouveau sur la
  principale. Valable pour le tour en cours et les suivants de la conversation ; un en-tête de branche de l'écran, s'il en nomme une,
  garde la priorité ;
* ``outils_versions_lire`` / ``outil_passer_a_la_version`` : la version de chaque outil que l'agent joue, et « Passer à la v5 » dans le
  BROUILLON de la branche de travail (décision 21 : jamais une version publiée, jamais seul).

Fusionner, changer la part du trafic et publier une branche sont dans ``gestes.py`` (N1), famille « publication » : la permission
décide (``modes.py``). Aucun appel réel, aucune dépense.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.db import branche_ouverte, db_client
from api.db.branches_client import ErreurDeBranche
from api.db.outils_versions_client import ErreurOutilVersion
from api.services.branches import service
from api.services.builder.actions._commun import agent_de_l_organisation
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer


class _Agent(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent (default: the agent of this conversation).")


class _Creer(_Agent):
    nom: str = Field(min_length=1, max_length=60, description="The branch name, unique for the agent (60 characters at most).")
    depuis_version: int | None = Field(default=None, ge=1, description="The version number to start from (default: the agent's live version).")


class _Travailler(_Agent):
    branche_id: int | None = Field(
        default=None, ge=1, description="The branch to work on from now on; none: work on the main branch again (branches_lire gives the ids)."
    )


class _PasserUnOutil(_Agent):
    outil: str = Field(min_length=1, max_length=255, description="The tool: its exact name or its uuid (outils_versions_lire gives both).")
    version: int = Field(ge=1, le=100000, description="The version number the draft of the working branch should play.")


def _refus_de_branche(erreur: ErreurDeBranche) -> ErreurAction:
    return ErreurAction(str(erreur), erreur.code)


async def _lire(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        vue = await service.vue(contexte.organisation_id, agent, getattr(contexte.user, "id", None))
    except ErreurDeBranche as erreur:
        raise _refus_de_branche(erreur) from None
    ouverte = (await db_client.branche_ouverte_de(agent.id)).branch_id
    return {"ok": True, "branche_de_travail": ouverte, **vue}


async def _creer(contexte: Contexte, p: _Creer) -> dict[str, Any]:
    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        cree = await service.creer(
            contexte.organisation_id,
            agent,
            p.nom,
            depuis_version=p.depuis_version,
            user_id=getattr(contexte.user, "id", None),
            protegee=False,
        )
    except ErreurDeBranche as erreur:
        raise _refus_de_branche(erreur) from None
    from api.services.equipe_mark.acces import journaliser

    await journaliser(contexte.user, "agents.branche_creee", contexte.organisation_id, {"agent": agent.id, "branche": cree["id"], "par": "builder"})
    return {"ok": True, **cree, "part_trafic": 0, "suite": "Use branche_travailler to work on it; merging and publishing are done by a person."}


async def _travailler(contexte: Contexte, p: _Travailler) -> dict[str, Any]:
    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    nom = "Principale"
    if p.branche_id is not None:
        branche = await db_client.obtenir_une_branche(contexte.organisation_id, agent.id, p.branche_id)
        if branche is None or branche.est_principale or branche.statut != "active":
            raise ErreurAction("This branch does not exist, is archived, or is the main branch (use branche_id none for the main branch).", "introuvable")
        nom = branche.nom
    branche_ouverte.ouvrir(p.branche_id, getattr(contexte.user, "id", None))
    if contexte.conversation is not None:
        contexte.conversation["branche"] = p.branche_id  # les tours suivants reprennent cette branche (moteur)
    return {"ok": True, "branche_de_travail": p.branche_id, "nom": nom}


async def _outils(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        vue = await db_client.outils_epingles_de_l_agent(contexte.organisation_id, agent.id)
    except ErreurOutilVersion as erreur:
        raise ErreurAction(str(erreur), erreur.code) from None
    return {"ok": True, **vue}


async def _passer(contexte: Contexte, p: _PasserUnOutil) -> dict[str, Any]:
    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    vue = await db_client.outils_epingles_de_l_agent(contexte.organisation_id, agent.id)
    cherche = p.outil.strip()
    trouves = [o for o in vue["outils"] if o["tool_uuid"] == cherche] or [o for o in vue["outils"] if o["nom"] == cherche]
    if len(trouves) != 1:
        raise ErreurAction("This agent does not use exactly one tool with that name or uuid (outils_versions_lire lists them).", "pas_utilise")
    try:
        fait = await db_client.passer_un_outil_a_la_version(contexte.organisation_id, agent.id, trouves[0]["tool_uuid"], p.version)
    except ErreurOutilVersion as erreur:
        raise ErreurAction(str(erreur), erreur.code) from None
    from api.services.equipe_mark.acces import journaliser

    await journaliser(
        contexte.user,
        "agents.outil_version_changee",
        contexte.organisation_id,
        {"agent": agent.id, "outil": trouves[0]["tool_uuid"], "version": p.version, "par": "builder"},
    )
    return {
        "ok": True,
        **fait,
        "nom": trouves[0]["nom"],
        "suite": "Written into the DRAFT only: the live agent keeps its version. Test it; a person publishes.",
    }


def _enregistrer(nom: str, description: str, parametres: type[BaseModel], fonction, ecriture: bool) -> None:
    enregistrer(
        Action(nom=nom, description=description, parametres=parametres, fonction=fonction, ecriture=ecriture, groupe="branches", extras={"lot": "L3d"})
    )


_enregistrer(
    "branches_lire",
    "Read the agent's branches: each one with its traffic share (the main branch takes the rest), its live version, its versions and "
    "drafts, whether the main branch is protected, and the branch you work on now (branche_de_travail, none = main).",
    _Agent,
    _lire,
    False,
)
_enregistrer(
    "branche_creer",
    "Create a branch of the agent: it starts at 0 % of the traffic (live calls do not move) with a draft copied from the live version "
    "or from depuis_version. Then use branche_travailler. Merging, changing the traffic share and publishing are done by a person.",
    _Creer,
    _creer,
    True,
)
_enregistrer(
    "branche_travailler",
    "Work on a branch from now on: every following draft, settings, tool and test action of this conversation is made on it, not on "
    "the main branch. branche_id none goes back to the main branch.",
    _Travailler,
    _travailler,
    False,
)
_enregistrer(
    "outils_versions_lire",
    "Read the tools of the agent (draft of the working branch, else its live version): for each, the version the agent plays (epinglee), "
    "the latest version (courante), and whether it is frozen. An agent never follows a new tool version on its own.",
    _Agent,
    _outils,
    False,
)
_enregistrer(
    "outil_passer_a_la_version",
    "Move a tool of the agent to another version, in the DRAFT of the working branch only (the live agent keeps its version). Then test; "
    "a person publishes. Give the tool's exact name or uuid (outils_versions_lire).",
    _PasserUnOutil,
    _passer,
    True,
)
