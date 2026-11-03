"""[.mark] Builder partie 2, U5 (E96) : les sous-agents du builder, en tables.

Le builder confie une tâche précise à une copie de lui-même. Chaque sous-agent est une **conversation enfant** de la table
(``parent_id``, ``genre = sous_agent``, ``delegation_id``, ``usage``, ``tache``, ``modele``, ``resultat``) :
son propre contexte, ses événements rejouables, son coût. Il n'a que des actions de **lecture et de test** (liste fermée
côté serveur : une écriture demandée est refusée avec la raison) et ne reçoit jamais de message d'une personne.

``deleguer`` attend la fin du groupe et rend les résumés bornés au builder, qui les rassemble dans un message. Au plus N sous-agents
tournent en même temps (réglage, 3 par défaut), les suivants attendent en file. Un plafond de dépense par délégation, compté aussi
dans le plafond de la conversation. Arrêter la conversation arrête ses sous-agents.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from api.db import db_client
from api.services.builder import stock
from api.services.builder.actions.registre import REGISTRE, Action, Contexte, ErreurAction, enregistrer
from api.services.builder.cerveau.reglages import ReglagesCerveau

CLE_REGLAGES = "MARK_BUILDER_SOUS_AGENTS"
USAGES = ("analyser", "tester", "attaquer", "comparer", "controler")
USAGES_QUI_DEPENSENT = ("tester", "attaquer", "comparer")
MODELE_PAR_DEFAUT = "claude-sonnet-5-5"
RESUME_MAX = 2000
ACCORDS_PAR_SOUS_AGENT = 5
# Ce que le sous-agent ne peut pas faire même en lecture : les cartes de dialogue avec la personne, la délégation elle-même.
EXCLUES = frozenset(
    {"plan_mettre_a_jour", "question_poser", "rapport_de_fin", "depense_annoncer", "correction_proposer", "tests_supprimer", "deleguer"}
)


class ReglagesSousAgents(BaseModel):
    """Réglages du Labo › Builder IA › Sous-agents."""

    actif: bool = True
    usages: list[Literal["analyser", "tester", "attaquer", "comparer", "controler"]] = Field(default_factory=lambda: list(USAGES))
    modele: str = Field(default=MODELE_PAR_DEFAUT, max_length=120)
    en_meme_temps: int = Field(default=3, ge=1, le=10)
    plafond_delegation: float = Field(default=1.0, ge=0, description="Dollars par délégation (0 = sans plafond de dépense).")


def actions_permises() -> frozenset[str]:
    """Liste fermée, calculée sur le registre : les actions qui n'écrivent rien (hors cartes), plus le rejeu des tests."""
    return frozenset(nom for nom, a in REGISTRE.items() if a.moteur and not a.ecriture and nom not in EXCLUES) | {"tests_rejouer"}


async def lire_les_reglages(organisation: int) -> ReglagesSousAgents:
    brut = await stock.lire(organisation, CLE_REGLAGES)
    try:
        return ReglagesSousAgents.model_validate(brut or {})
    except Exception:  # noqa: BLE001 -- une ligne abîmée ne bloque jamais le builder : les valeurs par défaut
        return ReglagesSousAgents()


async def ecrire_les_reglages(organisation: int, reglages: ReglagesSousAgents) -> None:
    await stock.ecrire(organisation, CLE_REGLAGES, reglages.model_dump())


async def _organisation_des_reglages(user) -> int:
    from api.services.builder.cerveau import reglages as reglages_cerveau

    return await reglages_cerveau.organisation_des_reglages(user)


# --- la délégation ----------------------------------------------------------------------------------------------------------


class _Tache(BaseModel):
    titre: str = Field(min_length=1, max_length=120)
    consigne: str = Field(min_length=1, max_length=4000, description="The task, written for the sub-agent: it knows nothing else.")


class _Deleguer(BaseModel):
    usage: Literal["analyser", "tester", "attaquer", "comparer", "controler"]
    taches: list[_Tache] = Field(min_length=1, max_length=12)
    modele: str | None = Field(default=None, max_length=120, description="Model of the sub-agents (default: the one set in the Labo).")


def _resume_de(historique: dict[str, Any] | None) -> tuple[str, int]:
    messages = (historique or {}).get("messages") or []
    appels = sum(len(m.get("appels") or []) for m in messages if m.get("role") == "assistant")
    for m in reversed(messages):
        if m.get("role") == "assistant" and (m.get("content") or "").strip():
            return m["content"].strip()[:RESUME_MAX], appels
    return "", appels


async def _cerveau_de_l_enfant(user, parent_cerveau, parent_reglages: ReglagesCerveau, modele: str):
    """Le cerveau d'un sous-agent : le modèle voulu avec la clé du builder ; sinon (autre fournisseur, clé absente) celui du parent."""
    if not modele or modele == parent_reglages.modele:
        return parent_cerveau, parent_reglages, parent_reglages.modele
    try:
        from api.routes.builder import fabriquer_le_cerveau
        from api.services.builder.cerveau import reglages as reglages_cerveau

        organisation = await reglages_cerveau.organisation_des_reglages(user)
        base = await reglages_cerveau.lire(organisation)
        cle = await reglages_cerveau.lire_la_cle(organisation, base)
        voulus = parent_reglages.model_copy(update={"modele": modele})
        if cle:
            return fabriquer_le_cerveau(voulus, cle), voulus, modele
    except Exception:  # noqa: BLE001 -- le repli est dit dans le rendu, jamais silencieux
        logger.warning("[builder] sous-agent: le modèle voulu n'a pas pu être monté, le cerveau du builder sert")
    return parent_cerveau, parent_reglages, parent_reglages.modele


async def _groupe(org: int, parent_id: int, delegation: str) -> list[Any]:
    return [e for e in await db_client.lister_les_enfants(org, parent_id) if e.delegation_id == delegation]


async def _deleguer(contexte: Contexte, parametres: _Deleguer) -> dict[str, Any]:
    from api.services.builder import fil as service_fil  # ici et pas en tête : ``fil`` importe le registre des actions

    conv = contexte.conversation
    fil_id = (conv or {}).get("fil_id")
    if fil_id is None or fil_id not in service_fil.CERVEAUX:
        raise ErreurAction("Sub-agents only work inside a builder conversation.")
    org = contexte.organisation_id
    parent = await db_client.lire_fil(org, fil_id)
    if parent is None or parent.genre == "sous_agent":
        raise ErreurAction("A sub-agent cannot delegate.")
    if not parent.sous_agents_actifs:
        raise ErreurAction("Sub-agents are off in this chat: do the work yourself, one task after the other.", "sous_agents_eteints")
    reglages = await lire_les_reglages(await _organisation_des_reglages(contexte.user))
    if not reglages.actif or parametres.usage not in reglages.usages:
        raise ErreurAction(f"Sub-agents are not enabled for « {parametres.usage} »: do it yourself.", "sous_agents_eteints")
    if parametres.usage in USAGES_QUI_DEPENSENT:
        from api.services.builder.actions.rapport_et_tests import consommer_un_accord

        consommer_un_accord(contexte)  # des modèles vont tourner : l'accord de la personne d'abord

    cerveau, reglages_cerveau, modele = await _cerveau_de_l_enfant(
        contexte.user, *service_fil.CERVEAUX[fil_id], parametres.modele or reglages.modele
    )
    delegation = uuid.uuid4().hex[:8]
    enfants = []
    for tache in parametres.taches:
        enfants.append(
            await db_client.creer_fil(
                org, getattr(contexte.user, "id", None), parent.workflow_id, tache.titre, None, parent_id=fil_id,
                genre="sous_agent", delegation_id=delegation, usage=parametres.usage, tache=tache.consigne, modele=modele,
                sous_agents_actifs=False,
            )
        )
    await service_fil.noter(fil_id, {"type": "delegation", "id": delegation, "usage": parametres.usage, "total": len(enfants), "modele": modele})

    accords = (
        {f"d{i}": {"motif": "delegation", "montant_estime": 0, "statut": "accordee", "utilisee": False} for i in range(ACCORDS_PAR_SOUS_AGENT)}
        if parametres.usage in USAGES_QUI_DEPENSENT
        else {}
    )
    file = asyncio.Semaphore(reglages.en_meme_temps)
    arret_du_groupe = asyncio.Event()

    async def un_sous_agent(enfant) -> None:
        async with file:
            if arret_du_groupe.is_set():
                await db_client.modifier_fil(org, enfant.id, etat="arretee", resultat={"resume": "", "actions": 0, "raison": "plafond"})
                return
            message = (
                f"[Delegated task: {parametres.usage}]\n{enfant.tache}\n\n"
                "You are a sub-agent of the builder: you only read and test, you never write. "
                "End with a short result (a few lines) for the builder."
            )
            extras = {"depenses": {k: dict(v) for k, v in accords.items()}}
            await service_fil.lancer(
                contexte.user, enfant, message, cerveau, reglages_cerveau, actions_permises=actions_permises(), extras=extras
            )
            await service_fil.attendre(enfant.id)
            fini = await db_client.lire_fil(org, enfant.id)
            resume, appels = _resume_de(fini.historique if fini else None)
            await db_client.modifier_fil(
                org, enfant.id, resultat={"resume": resume, "actions": appels, **({"raison": "plafond"} if arret_du_groupe.is_set() else {})}
            )

    async def surveiller() -> None:
        if reglages.plafond_delegation <= 0:
            return
        while True:
            await asyncio.sleep(0.2)
            groupe = await _groupe(org, fil_id, delegation)
            if sum(e.cout or 0.0 for e in groupe) >= reglages.plafond_delegation and not arret_du_groupe.is_set():
                arret_du_groupe.set()
                await service_fil.noter(
                    fil_id, {"type": "erreur", "code": "plafond_delegation", "message": "The delegation's ceiling is reached: the sub-agents are stopped."}
                )
                for e in groupe:
                    if service_fil.en_cours(e.id):
                        await service_fil.arreter(org, e.id)
                return

    veille = asyncio.create_task(surveiller())
    try:
        await asyncio.gather(*(un_sous_agent(e) for e in enfants), return_exceptions=True)
    finally:
        veille.cancel()
        for e in enfants:  # « Arrêter » la conversation (ou une panne) arrête ses sous-agents
            if service_fil.en_cours(e.id):
                await service_fil.arreter(org, e.id)
    groupe = await _groupe(org, fil_id, delegation)
    cout, jetons = sum(e.cout or 0.0 for e in groupe), sum(e.jetons or 0 for e in groupe)
    if conv is not None:  # compté aussi dans le plafond de la conversation
        depense = conv.setdefault("depense", {"jetons": 0, "cout": 0.0})
        depense["jetons"] = int(depense.get("jetons", 0)) + jetons
        depense["cout"] = round(float(depense.get("cout", 0.0)) + cout, 6)
    await service_fil.noter(fil_id, {"type": "delegation_fin", "id": delegation, "cout": round(cout, 6)})
    return {
        "ok": True,
        "delegation": delegation,
        "modele": modele,
        "arretee_par_plafond": arret_du_groupe.is_set(),
        "cout": round(cout, 6),
        "resultats": [
            {"id": e.id, "titre": e.titre, "etat": e.etat, "cout": e.cout or 0.0, **{k: (e.resultat or {}).get(k) for k in ("resume", "actions")}}
            for e in groupe
        ],
    }


enregistrer(
    Action(
        nom="deleguer",
        description=(
            "Hand precise tasks to copies of yourself (sub-agents), then gather their short results. Usage: analyser (real calls, one "
            "sub-agent per batch), tester / attaquer (tests or attacks in parallel), comparer (two versions or models), controler "
            "(check the agent step by step before publication). They only read and test, never write. Write each task so it stands alone. "
            "tester / attaquer / comparer cost money: announce it with depense_annoncer first. Blocks until the group is done."
        ),
        parametres=_Deleguer,
        fonction=_deleguer,
        ecriture=False,
        mcp=False,
        groupe="dialogue",
        extras={"lot": "C2"},
    )
)
