"""[.mark] Partie 3, L5b (sous-lot 3) : le builder et les groupes d'agents (un principal et ses spécialisés, les passations).

Le builder lit, crée et règle un groupe par les fonctions qui existent déjà (``services/groupe/``, les mêmes que les routes de l'écran) :

* ``groupes_lister`` : les groupes de l'organisation (le principal de chacun et ses spécialisés) ;
* ``groupe_lire`` : le groupe d'un agent et les réglages de passation de son principal (valeur réglée, ou défaut d'un groupe) ;
* ``groupe_creer`` : le principal d'un nouveau groupe et son sous-dossier (comme la carte « Graphe avec agents spécialisés ») ;
* ``groupe_specialise_creer`` : un spécialisé dans le groupe d'un principal (graphe minimal, clés communes, outil de passation) ;
* ``groupe_regler`` : les réglages de passation du principal (plafond, passation sans résumé, préchauffage, renvoi unique, phrase de
  mise en relation, attente) et le « cerveau propre » d'un spécialisé. Écrits dans le BROUILLON, recopiés dans les spécialisés ;
* ``groupe_completer`` : un nœud de fin pour chaque collègue et une étape de retour pour l'accueil (les prompts restent « à rédiger »).

Publier un groupe et archiver un agent sont dans ``gestes.py`` (N1), familles « publication » et « irréversible » : la permission
décide (``modes.py``). Tout est écrit dans les BROUILLONS ; la principale protégée d'un agent
client en ligne refuse comme pour toute écriture. Aucun appel réel, aucune dépense.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from api.db import db_client
from api.services.builder import reglages_agent
from api.services.builder.actions._commun import agent_de_l_organisation
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer
from api.services.groupe import groupe as service
from api.services.groupe import passations, reglages_passation
from api.services.groupe.passations import CLE_AGENT_PRINCIPAL
from api.services.groupe.reglages import CLE_CERVEAU_PROPRE, CLES_DU_GROUPE

# Les bornes des deux réglages chiffrés : l'écran n'en pose pas (minimum 0) et le serveur n'en avait pas ; elles évitent une faute de frappe.
PLAFOND_MAX = 50
SANS_RESUME_MAX = 500
ATTENTE_MAX_S = 30.0


class _Agent(BaseModel):
    workflow_id: int | None = Field(default=None, description="An agent of the group (default: the agent of this conversation).")


class _Rien(BaseModel):
    pass


class _Creer(BaseModel):
    nom: str = Field(min_length=1, max_length=100, description="The main agent's name (the group's folder takes it).")
    dossier_id: int | None = Field(default=None, ge=1, description="The folder the group's sub-folder goes in (default: top level).")
    recette: str | None = Field(default=None, max_length=120, description="The recipe (library sheet id) to start from; none: the default.")

    @field_validator("nom")
    @classmethod
    def _nettoyer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("The name cannot be empty")
        return v


class _CreerSpecialise(_Agent):
    nom: str = Field(min_length=1, max_length=100, description="The specialist's name.")

    @field_validator("nom")
    @classmethod
    def _nettoyer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("The name cannot be empty")
        return v


class _Attente(BaseModel):
    duree_min_s: float | None = Field(default=None, ge=0, le=ATTENTE_MAX_S, description="Minimum length of the waiting sound, in seconds.")
    passation: bool | None = Field(default=None, description="Play the waiting sound during a hand-over between agents.")
    transfert_humain: bool | None = Field(default=None, description="Play the waiting sound during a transfer to a person.")
    phrase_pont: str | None = Field(default=None, max_length=300, description="The bridge sentence the passing agent says when a hand-over takes long; empty turns it off.")
    delai_phrase_pont_s: float | None = Field(default=None, ge=0, le=ATTENTE_MAX_S, description="Seconds before the bridge sentence is said.")


class _Regler(_Agent):
    plafond_passations: int | None = Field(default=None, ge=0, le=PLAFOND_MAX, description="At most this many successful hand-overs per call (default in a group: 6).")
    passation_sans_resume_jusqua: int | None = Field(
        default=None, ge=0, le=SANS_RESUME_MAX, description="Under this number of messages the called agent gets the history as it is, without a summary (default 40; 0 = always a summary)."
    )
    prechauffage_agents: bool | None = Field(default=None, description="Warm up the colleagues at pick-up (default on in a group).")
    un_seul_renvoi_par_appel: bool | None = Field(default=None, description="After a failed transfer to a person, no other transfer in the call (default on in a group).")
    phrase_mise_en_relation: str | None = Field(default=None, max_length=300, description="The sentence the code says before a transfer to a person; empty turns it off.")
    attente: _Attente | None = Field(default=None, description="The waiting sound and the bridge sentence (only the fields you give change).")
    specialise_id: int | None = Field(default=None, ge=1, description="A specialist of this group, to change its own brain setting.")
    cerveau_propre: bool | None = Field(default=None, description="True: the specialist keeps its own brain; false: it follows the main agent again.")

    @model_validator(mode="after")
    def _au_moins_un(self) -> "_Regler":
        passations_dites = [self.plafond_passations, self.passation_sans_resume_jusqua, self.prechauffage_agents, self.un_seul_renvoi_par_appel, self.phrase_mise_en_relation]
        attente = self.attente is not None and any(v is not None for v in self.attente.model_dump().values())
        if (self.cerveau_propre is None) != (self.specialise_id is None):
            raise ValueError("specialise_id and cerveau_propre go together")
        if self.cerveau_propre is None and not attente and all(v is None for v in passations_dites):
            raise ValueError("Give at least one setting")
        return self


def _refus(erreur: service.GroupeError) -> ErreurAction:
    return ErreurAction(str(erreur), "groupe")


def _reglages_de_passation(reglages: dict[str, Any]) -> dict[str, Any]:
    """Ce que le moteur de l'appel lira : la valeur réglée, ou le défaut d'un groupe (mêmes fonctions que lui)."""
    attente = reglages_passation.attente_de(reglages)
    return {
        "plafond_passations": passations.plafond_de(reglages),
        "passation_sans_resume_jusqua": reglages_passation.limite_sans_resume(reglages),
        "prechauffage_agents": reglages_passation.prechauffage_actif(reglages),
        "un_seul_renvoi_par_appel": reglages_passation.renvoi_unique_actif(reglages),
        "phrase_mise_en_relation": reglages_passation.phrase_de_mise_en_relation(reglages),
        "attente": {
            "duree_min_s": attente.duree_min_s,
            "passation": attente.passation,
            "transfert_humain": attente.transfert_humain,
            "phrase_pont": attente.phrase_pont,
            "delai_phrase_pont_s": attente.delai_phrase_pont_s,
        },
    }


async def _lister(contexte: Contexte, _p: _Rien) -> dict[str, Any]:
    liens = await service.liens_des_groupes(contexte.organisation_id)
    noms = {a.id: a.name for a in await db_client.get_all_workflows_for_listing(organization_id=contexte.organisation_id, status="active")}
    groupes = [
        {
            "principal": {"id": lien["id"], "nom": noms.get(lien["id"], "")},
            "specialises": [{"id": i, "nom": noms.get(i, "")} for i in lien["agents_specialises"]],
        }
        for lien in liens
        if lien["role"] == "principal"
    ]
    return {"ok": True, "groupes": groupes}


async def _lire(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    groupe = await service.lire_groupe(agent.id, contexte.organisation_id)
    if groupe is None or groupe.get("principal") is None:
        return {"ok": True, "groupe": None, "suite": "This agent is alone: groupe_creer makes a group, groupe_specialise_creer adds a specialist to a main agent."}
    principal = await service.lire_agent(groupe["principal"]["id"], contexte.organisation_id)
    return {
        "ok": True,
        "groupe": {
            "principal": groupe["principal"],
            "specialises": [{"id": m["id"], "nom": m["name"], "cerveau_propre": m["cerveau_propre"], "statut": m["status"]} for m in groupe["specialises"]],
        },
        "passations": _reglages_de_passation(principal.reglages if principal else {}),
        "du_brouillon": bool(principal and principal.a_un_brouillon),
    }


async def _creer(contexte: Contexte, p: _Creer) -> dict[str, Any]:
    from api.services.builder import recettes

    try:
        choisie = await recettes.verifier_le_choix(contexte.organisation_id, p.recette)
    except recettes.ErreurRecette as erreur:
        raise ErreurAction(str(erreur), "recette") from None
    try:
        workflow_id, dossier_id = await service.creer_principal(
            nom=p.nom, organization_id=contexte.organisation_id, user_id=contexte.user.id, dossier_parent_id=p.dossier_id
        )
    except service.GroupeError as erreur:
        raise _refus(erreur) from None
    await recettes.poser_a_la_creation(contexte.organisation_id, workflow_id, choisie, getattr(contexte.user, "email", "") or "")
    from api.services.equipe_mark.acces import journaliser

    await journaliser(contexte.user, "agents.groupe_cree", contexte.organisation_id, {"agent": workflow_id, "par": "builder"})
    return {"ok": True, "workflow_id": workflow_id, "dossier_id": dossier_id, "suite": "Add specialists with groupe_specialise_creer; a person publishes."}


async def _creer_specialise(contexte: Contexte, p: _CreerSpecialise) -> dict[str, Any]:
    principal = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        nouveau = await service.creer_specialise(
            principal_id=principal.id, nom=p.nom, organization_id=contexte.organisation_id, user_id=contexte.user.id
        )
    except service.GroupeError as erreur:
        raise _refus(erreur) from None
    from api.services.equipe_mark.acces import journaliser

    await journaliser(contexte.user, "agents.specialise_cree", contexte.organisation_id, {"agent": nouveau, "principal": principal.id, "par": "builder"})
    return {"ok": True, "workflow_id": nouveau, "principal_id": principal.id, "suite": "Written as drafts; groupe_completer adds the hand-over steps; a person publishes."}


async def _regler(contexte: Contexte, p: _Regler) -> dict[str, Any]:
    principal = await agent_de_l_organisation(contexte, p.workflow_id)
    etat = await service.lire_agent(principal.id, contexte.organisation_id)
    if etat is None or not isinstance(etat.reglages.get(passations.CLE_AGENTS_SPECIALISES), list):
        raise ErreurAction("This agent is not the main agent of a group (groupe_lire tells which one is).", "pas_un_principal")
    valeurs: dict[str, Any] = {}
    for nom, valeur in (
        (passations.CLE_PLAFOND, p.plafond_passations),
        (reglages_passation.CLE_SANS_RESUME, p.passation_sans_resume_jusqua),
        (reglages_passation.CLE_PRECHAUFFAGE, p.prechauffage_agents),
        (reglages_passation.CLE_RENVOI_UNIQUE, p.un_seul_renvoi_par_appel),
    ):
        if valeur is not None:
            valeurs[nom] = valeur
    if p.phrase_mise_en_relation is not None:
        existant = etat.reglages.get(reglages_passation.CLE_TRANSFERT_HUMAIN)
        valeurs[reglages_passation.CLE_TRANSFERT_HUMAIN] = {
            **(existant if isinstance(existant, dict) else {}),
            reglages_passation.CLE_PHRASE_MISE_EN_RELATION: p.phrase_mise_en_relation.strip(),
        }
    if p.attente is not None:
        dits = {k: v for k, v in p.attente.model_dump().items() if v is not None}
        if dits:
            existant = etat.reglages.get(reglages_passation.CLE_ATTENTE)
            valeurs[reglages_passation.CLE_ATTENTE] = {**(existant if isinstance(existant, dict) else {}), **dits}
    ecrits: list[str] = []
    try:
        if valeurs:
            ecrits += (await reglages_agent.regler(contexte.organisation_id, principal.id, valeurs, cles_en_plus=frozenset(CLES_DU_GROUPE)))["ecrits"]
        if p.specialise_id is not None:
            specialise = await service.lire_agent(p.specialise_id, contexte.organisation_id)
            if (
                specialise is None
                or p.specialise_id not in service.specialises_de(etat.reglages)
                or specialise.reglages.get(CLE_AGENT_PRINCIPAL) != principal.id
            ):
                raise ErreurAction("This agent is not a specialist of this group (groupe_lire lists them).", "pas_un_specialise")
            await reglages_agent.regler(
                contexte.organisation_id, specialise.id, {CLE_CERVEAU_PROPRE: p.cerveau_propre}, cles_en_plus=frozenset({CLE_CERVEAU_PROPRE})
            )
            # Un cerveau qui se rattache reprend aussitôt celui du principal (la recopie du principal, comme à son enregistrement).
            await service.recopier_dans_les_specialises(principal.id, contexte.organisation_id)
            ecrits.append(f"cerveau_propre:{specialise.id}")
    except reglages_agent.ErreurReglage as erreur:
        raise ErreurAction(str(erreur), "reglage") from None
    from api.services.equipe_mark.acces import journaliser

    await journaliser(contexte.user, "agents.groupe_regle", contexte.organisation_id, {"agent": principal.id, "reglages": sorted(ecrits), "par": "builder"})
    return {"ok": True, "ecrits": sorted(ecrits), "suite": "Written into the DRAFT and copied into the specialists; a person publishes."}


async def _completer(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    principal = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        rendu = await service.completer_le_groupe(principal.id, contexte.organisation_id)
    except service.GroupeError as erreur:
        raise _refus(erreur) from None
    return {"ok": True, "ajouts": {str(agent): ajouts for agent, ajouts in rendu.items()}, "suite": "Drafts only: the prompts marked « À rédiger » are written with the person."}


def _enregistrer(nom: str, description: str, parametres: type[BaseModel], fonction, ecriture: bool) -> None:
    enregistrer(
        Action(nom=nom, description=description, parametres=parametres, fonction=fonction, ecriture=ecriture, groupe="groupes", extras={"lot": "L5b"})
    )


_enregistrer(
    "groupes_lister",
    "List the agent groups of the organization: for each, the main agent and its specialists (id and name).",
    _Rien,
    _lister,
    False,
)
_enregistrer(
    "groupe_lire",
    "Read the group of an agent (main or specialist): the main agent, its specialists (own brain or not) and the hand-over settings of "
    "the main agent as the call will read them (cap, summary threshold, warm-up, single transfer, sentences, waiting sound).",
    _Agent,
    _lire,
    False,
)
_enregistrer(
    "groupe_creer",
    "Create the main agent of a new group and its sub-folder, as the screen does (a new agent, first version). Then add "
    "specialists with groupe_specialise_creer; a person publishes later changes.",
    _Creer,
    _creer,
    True,
)
_enregistrer(
    "groupe_specialise_creer",
    "Add a specialist agent to the group of a main agent: minimal graph, common settings copied, hand-over tool put on the main agent. "
    "Draft only.",
    _CreerSpecialise,
    _creer_specialise,
    True,
)
_enregistrer(
    "groupe_regler",
    "Set the hand-over settings of a main agent (cap per call, summary threshold, warm-up, single transfer, sentence before a transfer, "
    "waiting sound and bridge sentence) and/or the « own brain » setting of one specialist. Written in the DRAFT and copied into the "
    "specialists; a person publishes.",
    _Regler,
    _regler,
    True,
)
_enregistrer(
    "groupe_completer",
    "Complete the group of a main agent: an end node for each colleague and a return step for the front agent. Nothing is removed or "
    "rewritten; the prompts stay « À rédiger » for the person. Drafts only.",
    _Agent,
    _completer,
    True,
)
