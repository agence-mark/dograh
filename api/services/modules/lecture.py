"""[.mark] Lot F8 : ce que le portail et la page de l'agent lisent des modules (M4, M6, M8, D118, D121).

- ``lire_modules`` : le registre, avec pour CETTE organisation le traducteur branché sur chaque besoin et
  « utilisé par » (les agents actifs dont la version PUBLIÉE allume le module : ce que lisent les appels) ;
- ``lire_modules_de_l_agent`` : la même chose pour un agent, avec ``actif`` ;
- ``synchroniser_modules`` : écrit le catalogue et « utilisé par » dans la base du client (ce que lit
  ``v_portail_modules``), à l'écran et à chaque publication. ⛔ Ne lève jamais.

Tout est lu sous l'organisation de l'appelant ; un agent d'une autre organisation n'existe pas ici.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.schemas.modules import (
    BesoinModule,
    ModuleDeLAgent,
    ModulesAgent,
    ModulesOrganisation,
    ModuleVue,
    ReglageModule,
    TexteModule,
    TraducteurBranche,
)
from api.schemas.objets_agent import AgentUtilisateur
from api.services.modules.etat import actif_sur
from api.services.modules.registre import MODULES, Module, Texte


def _texte(t: Texte | None) -> TexteModule | None:
    return TexteModule(en=t.en, fr=t.fr) if t else None


def _branche(systeme: str | None) -> TraducteurBranche | None:
    from api.services.hub.traducteurs import traducteur

    trouve = traducteur(systeme)
    return TraducteurBranche(systeme=trouve.systeme, libelle=trouve.libelle) if trouve else None


async def traducteurs_choisis(organization_id: int) -> dict[str, TraducteurBranche | None]:
    """The translator the organization chose for each domain (« Integrations » and « Caller verification »).
    Never raises: unreadable = none."""
    from api.services.hub.choix import lire_choix
    from api.services.verification.reglages import lire_reglages

    choix = await lire_choix(organization_id)
    verification = await lire_reglages(organization_id)
    return {"agenda": _branche(choix.agenda), "dossier": _branche(verification.logiciel)}


def _vue(module: Module, traducteurs: dict[str, TraducteurBranche | None]) -> dict[str, Any]:
    return {
        "code": module.code,
        "libelle": _texte(module.libelle),
        "interrupteur": module.interrupteur,
        "connecteurs": list(module.connecteurs),
        "besoins": [
            BesoinModule(
                code=b.code,
                libelle=_texte(b.libelle),
                domaine=b.domaine,
                source_interne=_texte(b.source_interne),
                traducteur=traducteurs.get(b.domaine) if b.domaine else None,
            )
            for b in module.besoins
        ],
        "reglages_construction": [ReglageModule(cle=r.cle, lieu=r.lieu, bloc=r.bloc, modifiable=r.modifiable) for r in module.construction],
        "reglages_terrain": [ReglageModule(cle=r.cle, lieu=r.lieu, bloc=r.bloc, modifiable=r.modifiable) for r in module.terrain],
    }


async def _agents(organization_id: int):
    """The active agents (published version) and the tools of their steps and background brain."""
    from api.db import db_client
    from api.services.groupe.agents_servis import lire_agents_lus

    agents, uuids = await lire_agents_lus(organization_id)
    outils: dict[str, Any] = {}
    if uuids:
        # Filtered by organization in the query, never afterwards.
        for outil in await db_client.get_tools_by_uuids(uuids, organization_id):
            outils[outil.tool_uuid] = outil
    return [
        (a, [outils[u] for u in [*a.outils, *a.outils_travail] if u in outils]) for a in agents
    ]


def _utilisateurs(module: Module, agents) -> list[AgentUtilisateur]:
    return [AgentUtilisateur(id=a.id, nom=a.nom) for a, outils in agents if actif_sur(module, a.configurations, outils)]


async def lire_modules(organization_id: int) -> ModulesOrganisation:
    traducteurs = await traducteurs_choisis(organization_id)
    agents = await _agents(organization_id)
    return ModulesOrganisation(
        modules=[ModuleVue(**_vue(m, traducteurs), utilise_par=_utilisateurs(m, agents)) for m in MODULES]
    )


async def lire_modules_de_l_agent(organization_id: int, agent_id: int) -> ModulesAgent | None:
    """``None``: no active agent with this identifier in this organization."""
    traducteurs = await traducteurs_choisis(organization_id)
    agents = await _agents(organization_id)
    trouve = next(((a, o) for a, o in agents if a.id == agent_id), None)
    if trouve is None:
        return None
    agent, outils = trouve
    return ModulesAgent(
        agent_id=agent_id,
        modules=[
            ModuleDeLAgent(
                **_vue(m, traducteurs),
                utilise_par=_utilisateurs(m, agents),
                actif=actif_sur(m, agent.configurations, outils),
            )
            for m in MODULES
        ],
    )


def catalogue_pour_la_base() -> list[tuple[str, str, list[dict]]]:
    """What the 020's ``module`` table holds: code, French label, declared terrain settings."""
    return [
        (
            m.code,
            m.libelle.fr,
            [{"cle": r.cle, "lieu": r.lieu, "bloc": r.bloc, "modifiable": r.modifiable} for r in m.terrain],
        )
        for m in MODULES
    ]


async def synchroniser_modules(organization_id: int | None, vue: ModulesOrganisation | None = None) -> bool:
    """Write the catalogue and who uses each module in THIS organization's database. ``True``: written.
    No database, a database before the 020, or one that does not answer: nothing, never an error."""
    if organization_id is None:
        return False
    try:
        from api.db.bases_clients.connexion import connecter
        from api.db.bases_clients.modules import (
            ecrire_agents_des_modules,
            ecrire_catalogue,
        )
        from api.services.base_client.rattachement import nom_de_la_base

        base = await nom_de_la_base(organization_id)
        if not base:
            return False
        vue = vue or await lire_modules(organization_id)
        connexion = await connecter(base)
        try:
            await ecrire_catalogue(connexion, catalogue_pour_la_base())
            await ecrire_agents_des_modules(connexion, {m.code: [a.id for a in m.utilise_par] for m in vue.modules})
        finally:
            await connexion.close()
        return True
    except Exception as erreur:  # noqa: BLE001 -- never a reason to fail a publication or a screen
        logger.warning(
            f"[.mark] Modules of organization {organization_id} not written ({type(erreur).__name__}): {erreur}"
        )
        return False
