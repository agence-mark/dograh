"""[.mark] Builder partie 2, U5 (lot C2) : le rapport de fin, l'annonce d'une dépense, la lecture et la proposition sur les tests,
et la correction depuis un appel en cinq temps.

* ``rapport_de_fin``      : la carte de fin de travail (ce que fait l'agent, tests, pourquoi un échec, phrases à essayer, points ouverts) ;
* ``depense_annoncer``    : le builder annonce ce que va coûter une étape et ATTEND l'accord de la personne (carte, puis réponse) ;
* ``tests_lister`` / ``tests_lire`` : il voit la suite et les 3 dernières exécutions avant d'en écrire ;
* ``tests_supprimer``     : il PROPOSE (carte), une personne supprime ; rien n'est effacé par le builder ;
* ``agent_proposer_archivage`` : il PROPOSE d'archiver un agent (carte avec un bouton), une personne clique (SE-14, E-1) ; rien n'est archivé par le builder ;
* ``correction_proposer`` : temps 2 de la correction (plan avant / après, objet touché), jamais appliqué par cette action ;
* ``correction_bilan``    : temps 5 (ce que le changement a cassé, comparé à l'exécution précédente) ;
* ``modifications_lister``: toutes les modifications de la conversation, avant et après, depuis les instantanés.

Les cartes sont dessinées par le code ; le modèle ne fait que les remplir.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from api.services.builder.actions._commun import agent_verifie
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer

EXECUTIONS_VUES = 3
OBJETS_DE_CORRECTION = ("prompt_general", "etape", "outil", "retour_outil", "code", "test")


# --- le rapport de fin -----------------------------------------------------------------------------------------------------


class _ResultatDeTest(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    ok: bool
    pourquoi: str = Field(default="", max_length=600, description="Why it fails: the faulty reply and the cause, one sentence.")


class _Rapport(BaseModel):
    resume: str = Field(min_length=1, max_length=2000, description="What the agent does now, in a few sentences.")
    tests: list[_ResultatDeTest] = Field(default_factory=list, max_length=60)
    phrases_a_essayer: list[str] = Field(default_factory=list, max_length=8, description="Sentences the person can say to try the agent.")
    points_ouverts: list[str] = Field(default_factory=list, max_length=12)


async def _rapport(contexte: Contexte, parametres: _Rapport) -> dict[str, Any]:
    carte = {"type": "rapport", **parametres.model_dump()}
    carte["reussis"] = sum(1 for t in parametres.tests if t.ok)
    if contexte.conversation is not None:
        contexte.conversation["rapport"] = carte
    return {"ok": True, "carte": carte}


# --- l'annonce d'une dépense -----------------------------------------------------------------------------------------------


class _Depense(BaseModel):
    motif: str = Field(min_length=1, max_length=400, description="What will cost, in one sentence (e.g. replaying the suite 3 times).")
    montant_estime: float = Field(ge=0, description="Estimated cost in dollars.")


async def _depense(contexte: Contexte, parametres: _Depense) -> dict[str, Any]:
    if contexte.conversation is None:
        raise ErreurAction("A cost can only be announced in a conversation with a person.")
    depenses = contexte.conversation.setdefault("depenses", {})
    identifiant = f"d{len(depenses) + 1}"
    depenses[identifiant] = {"motif": parametres.motif, "montant_estime": parametres.montant_estime, "statut": "attente", "utilisee": False}
    return {
        "ok": True,
        "id": identifiant,
        "attente": "Stop here and wait for the person's agreement: you spend nothing until it is given.",
        "carte": {"type": "depense", "id": identifiant, "motif": parametres.motif, "montant_estime": parametres.montant_estime, "statut": "attente"},
    }


def consommer_un_accord(contexte: Contexte) -> None:
    """Le builder ne dépense rien sans l'accord de la personne : une dépense lancée depuis le chat consomme un accord donné.
    Sans conversation (la personne agit elle-même depuis l'écran), rien n'est exigé."""
    if contexte.conversation is None:
        return
    for depense in (contexte.conversation.get("depenses") or {}).values():
        if depense.get("statut") == "accordee" and not depense.get("utilisee"):
            depense["utilisee"] = True
            return
    raise ErreurAction(
        "This costs money: announce it with depense_annoncer and wait for the person's agreement first.", "accord_requis"
    )


# --- les tests : lire, proposer de supprimer --------------------------------------------------------------------------------


class _Agent(BaseModel):
    workflow_id: int | None = None


class _UnTest(_Agent):
    test: str = Field(min_length=1, max_length=80, description="Slug of the test.")


def _resume_d_une_execution(execution: dict[str, Any]) -> dict[str, Any]:
    return {k: execution.get(k) for k in ("le", "version", "statut", "reussis", "total")}


async def _tests_lister(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    from api.services.builder.tests_agent import creation, stockage

    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    org = contexte.organisation_id
    liste = []
    for test in await stockage.lister(org, identifiant):
        executions = (await stockage.resultats(org, identifiant, test["slug"]))[:EXECUTIONS_VUES]
        liste.append({**creation.en_resume(test), "executions": [_resume_d_une_execution(e) for e in executions]})
    return {"ok": True, "total": len(liste), "tests": liste}


async def _tests_lire(contexte: Contexte, parametres: _UnTest) -> dict[str, Any]:
    from api.services.builder.tests_agent import stockage

    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        test = await stockage.lire(contexte.organisation_id, identifiant, parametres.test)
    except stockage.ErreurTest as erreur:
        raise ErreurAction(str(erreur)) from None
    executions = (await stockage.resultats(contexte.organisation_id, identifiant, parametres.test))[:EXECUTIONS_VUES]
    return {"ok": True, "test": test, "executions": executions}


async def _tests_supprimer(contexte: Contexte, parametres: _UnTest) -> dict[str, Any]:
    """Une suppression est un clic humain : le builder la propose sur une carte, rien n'est effacé ici."""
    from api.services.builder.tests_agent import creation, stockage

    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        test = await stockage.lire(contexte.organisation_id, identifiant, parametres.test)
    except stockage.ErreurTest as erreur:
        raise ErreurAction(str(erreur)) from None
    resume = creation.en_resume(test)
    return {
        "ok": True,
        "propose": True,
        "message": "Proposed, not deleted: a person deletes the test from the Tests tab.",
        "carte": {"type": "proposition_test", "genre": "suppression", "workflow_id": identifiant, "test": resume},
    }


class _Archivage(_Agent):
    raison: str = Field(min_length=1, max_length=400, description="Why this agent should be archived, in one or two sentences.")


async def _agent_proposer_archivage(contexte: Contexte, parametres: _Archivage) -> dict[str, Any]:
    """Archiver est un clic humain : le builder le propose sur une carte, rien n'est archivé ici (SE-14, E-1)."""
    from api.services.builder.actions._commun import agent_de_l_organisation

    agent = await agent_de_l_organisation(contexte, parametres.workflow_id)
    if getattr(agent, "status", "active") != "active":
        raise ErreurAction("This agent is already archived.", "deja_archive")
    return {
        "ok": True,
        "propose": True,
        "message": "Proposed, not archived: a person archives the agent with the button on the card. Say so, and wait.",
        "carte": {"type": "proposition_archivage", "workflow_id": agent.id, "nom": agent.name, "raison": parametres.raison},
    }


# --- corriger depuis un appel -----------------------------------------------------------------------------------------------


class _Correction(_Agent):
    cause: str = Field(min_length=1, max_length=800, description="The cause, named by default, quoted on the faulty reply.")
    replique: str = Field(default="", max_length=600, description="The faulty reply of the call, quoted as it is.")
    objet: Literal["prompt_general", "etape", "outil", "retour_outil", "code", "test"]
    cible: str = Field(min_length=1, max_length=200, description="Which prompt, step, tool, code or test is touched.")
    avant: str = Field(max_length=6000, description="The exact text or code today.")
    apres: str = Field(max_length=6000, description="The exact text or code after the change.")
    recette: str = Field(default="", max_length=60, description="Deprecated: the recipe is read from the agent. Only used when the agent has none set.")
    amelioration_id: int | None = Field(
        default=None,
        description="The number of the problem this conversation was opened from (given in the first message): the proposed fix is then written in that problem.",
    )


async def _correction_proposer(contexte: Contexte, parametres: _Correction) -> dict[str, Any]:
    if parametres.avant == parametres.apres:
        raise ErreurAction("The plan changes nothing: « avant » and « apres » are the same.")
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    # D14 : la règle de descente (la consigne qui échoue descend dans le retour de l'outil) ne vaut que si la recette de l'AGENT
    # en déclare la capacité (lot M : la garde lit la capacité, plus un nom de recette).
    if parametres.objet == "retour_outil":
        from api.services.builder import recettes

        capacites = await recettes.capacites_de_l_agent(contexte.organisation_id, identifiant, parametres.recette)
        if recettes.CAPACITE_REGLE_DE_DESCENTE not in capacites:
            raise ErreurAction("Moving a rule into a tool's return only applies to a recipe that has the descent rule: not on this agent.", "recette")
    if parametres.amelioration_id is not None:
        await _ecrire_dans_le_probleme(contexte, identifiant, parametres)
    carte = {"type": "correction", "workflow_id": identifiant, **parametres.model_dump(exclude={"workflow_id", "amelioration_id"}), "statut": "a_approuver"}
    return {
        "ok": True,
        "attente": "Stop here: the person approves or sends it back with a note. Apply nothing before the approval.",
        "carte": carte,
    }


async def _ecrire_dans_le_probleme(contexte: Contexte, workflow_id: int, parametres: _Correction) -> None:
    """SE-17 (F-1) : la correction proposée sur la carte est aussi écrite dans la fiche du problème d'où vient la conversation. Le problème
    est relu avec l'organisation de l'appelant et doit porter sur CET agent (introuvable sinon). Rien n'est appliqué à l'agent."""
    from api.db import db_client

    probleme = await db_client.lire_une_amelioration(contexte.organisation_id, parametres.amelioration_id)
    if probleme is None or probleme.get("workflow_id") != workflow_id:
        raise ErreurAction(f"Problem {parametres.amelioration_id} not found on this agent.", "introuvable")
    correction = {"etape": probleme.get("etape"), "cible": parametres.cible, "avant": parametres.avant, "apres": parametres.apres}
    await db_client.modifier_une_amelioration(contexte.organisation_id, parametres.amelioration_id, correction=correction)


async def _correction_bilan(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    """Ce que ce changement a cassé : un test qui passait à l'exécution précédente et qui échoue à la dernière."""
    from api.services.builder.tests_agent import stockage

    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    org = contexte.organisation_id
    casses, repares, inchanges = [], [], 0
    for test in await stockage.lister(org, identifiant):
        executions = await stockage.resultats(org, identifiant, test["slug"])
        if len(executions) < 2:
            continue
        derniere, precedente = executions[0], executions[1]
        if precedente.get("statut") == "ok" and derniere.get("statut") != "ok":
            casses.append({"test": test["slug"], "nom": test["nom"], "avant": precedente.get("statut"), "apres": derniere.get("statut")})
        elif precedente.get("statut") != "ok" and derniere.get("statut") == "ok":
            repares.append({"test": test["slug"], "nom": test["nom"]})
        else:
            inchanges += 1
    return {"ok": True, "casses": casses, "repares": repares, "inchanges": inchanges}


async def _modifications_lister(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    from api.services.builder import revue

    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    fil_id = (contexte.conversation or {}).get("fil_id")
    lignes = await revue.instantanes(contexte.organisation_id, identifiant, fil_id, complets=True)
    modifications = []
    for v in reversed(lignes):  # de la plus ancienne à la plus récente
        pour_chaque = revue.eclater(list(v.get("operations") or []))
        modifications.append(
            {
                "numero": v["numero"],
                "cause": v["cause"],
                "date": v["date"],
                "operations": [
                    revue._decrire(v.get("avant") or {"nodes": [], "edges": []}, rang, op) for rang, op in enumerate(pour_chaque)
                ],
            }
        )
    return {"ok": True, "total": len(modifications), "modifications": modifications}


def _inscrire(nom: str, description: str, parametres: type[BaseModel], fonction, *, ecriture: bool, mcp: bool, groupe: str) -> None:
    enregistrer(
        Action(nom=nom, description=description, parametres=parametres, fonction=fonction, ecriture=ecriture, mcp=mcp, groupe=groupe, extras={"lot": "C2"})
    )


_inscrire(
    "rapport_de_fin",
    "End of work: the report card. What the agent does now, each test with why it fails if it does, sentences the person can say to try it, open points.",
    _Rapport,
    _rapport,
    ecriture=False,
    mcp=False,
    groupe="dialogue",
)
_inscrire(
    "depense_annoncer",
    "Before anything that costs money (replaying tests with models, a long run): announce the reason and the estimated cost on a card, then STOP and wait for the person's agreement.",
    _Depense,
    _depense,
    ecriture=False,
    mcp=False,
    groupe="dialogue",
)
_inscrire(
    "tests_lister",
    "List the agent's tests (name, kind, required, criteria count) with their last 3 runs. Read it before writing a test.",
    _Agent,
    _tests_lister,
    ecriture=False,
    mcp=True,
    groupe="tests",
)
_inscrire(
    "tests_lire",
    "Read one test in full (criteria, reply or scenario, character) with its last 3 runs.",
    _UnTest,
    _tests_lire,
    ecriture=False,
    mcp=True,
    groupe="tests",
)
_inscrire(
    "tests_supprimer",
    "Propose deleting a test. Nothing is deleted: a person confirms from the Tests tab.",
    _UnTest,
    _tests_supprimer,
    ecriture=False,
    mcp=True,
    groupe="tests",
)
_inscrire(
    "correction_proposer",
    "Fixing from a call, step 2: the plan before / after on a card (cause quoted on the reply, object touched, exact text before and after). A person approves or sends it back; apply nothing before.",
    _Correction,
    _correction_proposer,
    ecriture=False,
    mcp=False,
    groupe="dialogue",
)
_inscrire(
    "correction_bilan",
    "Fixing from a call, step 5: what this change broke. Compares each test's last run with the one before; lists the tests that passed and now fail.",
    _Agent,
    _correction_bilan,
    ecriture=False,
    mcp=True,
    groupe="tests",
)
_inscrire(
    "modifications_lister",
    "List ALL the changes made to the agent in this conversation, in order, each with the value before and after (from the saved versions).",
    _Agent,
    _modifications_lister,
    ecriture=False,
    mcp=True,
    groupe="construction",
)
_inscrire(
    "agent_proposer_archivage",
    "Propose archiving an agent that is no longer useful, on a card with an Archive button. Nothing is archived by you: only the person's click does it, and it can be undone. Give the reason in one or two sentences.",
    _Archivage,
    _agent_proposer_archivage,
    ecriture=False,
    mcp=False,
    groupe="dialogue",
)
