"""[.mark] Chantier agents-specialises, lot 9 (M9, M10, D89, D90, A13) : lire les agents de l'organisation
pour le portail.

Pour chaque agent actif : son nom, sa version publiée, ses numéros, sa fiche, les agents qu'il peut appeler
et ceux qui l'appellent (lus dans ses outils de transfert vers un agent), et ses capacités, déduites de sa
définition publiée, jamais saisies. Pour chaque groupe (un principal et ses spécialisés, lien porté des deux
côtés dans les réglages) : qui appelle qui, et les capacités de l'ENSEMBLE.

Tout est lu sous l'organisation de l'appelant (``organization_id`` à la requête) : un identifiant d'agent
écrit dans des réglages mais qui n'est pas de cette organisation n'existe pas ici.

Aucun mot de métier : des noms d'outils du catalogue, des clés de réglages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from loguru import logger

from api.enums import ToolCategory
from api.schemas.agents_servis import (
    AgentServi,
    AgentsServis,
    CapacitesAgent,
    GroupeServi,
    LienDePassation,
)
from api.services.etablissements.appel import CLE_FICHE_DE_LAGENT
from api.services.groupe.passations import CLE_AGENTS_SPECIALISES, agent_principal_de

# Les outils internes du catalogue des connecteurs qui disent une capacité.
OUTIL_DIRIGER = ("equipe", "diriger_vers_personne")
OUTILS_PLANIFICATEUR = (
    ("planificateur", "proposer_creneaux"),
    ("planificateur", "poser_rendez_vous"),
)


@dataclass
class AgentLu:
    """Un agent de l'organisation tel que la lecture le voit (rien d'autre n'est lu)."""

    id: int
    nom: str
    version_publiee: int | None = None
    numeros: list[str] = field(default_factory=list)
    configurations: dict = field(default_factory=dict)  # la version publiée
    outils: list[str] = field(
        default_factory=list
    )  # les uuid d'outils posés sur les étapes publiées
    outils_travail: list[str] = field(
        default_factory=list
    )  # les uuid du cerveau de fond (travail_outils), vides quand le travail est éteint


def _entier(valeur: Any) -> int | None:
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        return valeur
    if isinstance(valeur, str) and valeur.strip().isdigit():
        return int(valeur.strip())
    return None


def outils_des_etapes(workflow_json: Mapping | None) -> list[str]:
    """Les uuid des outils posés sur les étapes d'un graphe (toutes, la globale comprise)."""
    vus: list[str] = []
    for noeud in (workflow_json or {}).get("nodes") or []:
        donnees = (noeud or {}).get("data") or {}
        for uuid in donnees.get("tool_uuids") or []:
            if isinstance(uuid, str) and uuid not in vus:
                vus.append(uuid)
    return vus


def _capacites_des_outils(c: CapacitesAgent, outils: Iterable[Any]) -> None:
    """Range dans ``c`` ce que disent des outils (les mêmes règles pour ceux de l'étape et ceux du fond)."""
    for outil in outils:
        categorie = getattr(outil, "category", None)
        config = (
            ((getattr(outil, "definition", None) or {}).get("config") or {})
            if outil
            else {}
        )
        if categorie == ToolCategory.TRANSFER_CALL.value:
            c.transfert = True
        elif categorie == ToolCategory.INTEGRATION.value:
            cible = (config.get("connecteur"), config.get("action"))
            if cible == OUTIL_DIRIGER:
                # Il peut transférer l'appel ou passer la demande à une personne de l'équipe.
                c.transfert = True
                c.demande_transmise = True
            elif cible in OUTILS_PLANIFICATEUR:
                c.rendez_vous = True


def capacites_de(
    configurations: Mapping | None,
    outils: Iterable[Any],
    outils_travail: Iterable[Any] = (),
) -> CapacitesAgent:
    """Ce que sait faire un agent : ses outils (``outils`` : les ``ToolModel`` posés sur ses étapes), les
    outils de son cerveau de fond (``outils_travail`` : ceux de ``travail_outils``, comptés seulement quand le
    travail est allumé, et sans ce que le fond ne reçoit jamais : transfert, passation, fin d'appel) et ses
    réglages. Pure : ni base ni réseau. Un réglage illisible vaut « éteint », jamais une erreur."""
    from api.services.travail.outils import outil_permis_au_fond
    from api.services.travail.reglages import ReglagesTravail

    c = CapacitesAgent()
    _capacites_des_outils(c, outils)
    if ReglagesTravail.depuis(dict(configurations or {})).actif:
        _capacites_des_outils(
            c, [o for o in outils_travail if outil_permis_au_fond(o)]
        )
    from api.services.apres_appel.reglages import reglages_de_lagent

    apres = reglages_de_lagent(dict(configurations or {}))
    if apres.actif and apres.mail:
        c.mail = True
    if apres.actif and (apres.sms.appelant.actif or apres.sms.equipe.actif):
        c.sms = True
    if bool((configurations or {}).get("verification_appelant")):
        c.verification = True
    return c


def destinations_de_passation(outils: Iterable[Any]) -> list[int]:
    """Les agents vers qui les outils de passation d'un agent mènent (``transfer_agent``)."""
    sortie: list[int] = []
    for outil in outils:
        if getattr(outil, "category", None) != ToolCategory.TRANSFER_AGENT.value:
            continue
        vers = _entier(
            (((getattr(outil, "definition", None) or {}).get("config")) or {}).get(
                "workflow_id"
            )
        )
        if vers is not None and vers not in sortie:
            sortie.append(vers)
    return sortie


def assembler(
    agents: list[AgentLu],
    outils_par_uuid: Mapping[str, Any],
    rattaches: set[int],
) -> AgentsServis:
    """Pure : de ce que Dograh dit, les agents et leurs groupes. Un lien qui désigne un agent hors de la
    liste (une autre organisation, un agent supprimé) n'existe pas."""
    ids = {a.id for a in agents}
    outils_de = {
        a.id: [outils_par_uuid[u] for u in a.outils if u in outils_par_uuid]
        for a in agents
    }
    outils_travail_de = {
        a.id: [outils_par_uuid[u] for u in a.outils_travail if u in outils_par_uuid]
        for a in agents
    }
    appelle = {
        a.id: [
            v
            for v in destinations_de_passation(outils_de[a.id])
            if v in ids and v != a.id
        ]
        for a in agents
    }
    appele_par: dict[int, list[int]] = {a.id: [] for a in agents}
    for de, cibles in appelle.items():
        for vers in cibles:
            appele_par[vers].append(de)

    # Les groupes : le lien est porté des deux côtés ; l'union des deux dit les membres. Un spécialisé
    # n'a qu'un principal (le premier qui le déclare, dans l'ordre des identifiants) ; un principal
    # n'est jamais le spécialisé d'un autre (pas de chaîne).
    reglages = {a.id: a.configurations for a in agents}
    tetes = {
        a.id
        for a in agents
        if isinstance(reglages[a.id].get(CLE_AGENTS_SPECIALISES), list)
    }
    principal_de: dict[int, int] = {}
    for a in sorted(agents, key=lambda x: x.id):
        if a.id not in tetes:
            continue
        for membre in (_entier(v) for v in reglages[a.id][CLE_AGENTS_SPECIALISES]):
            if (
                membre is not None
                and membre in ids
                and membre != a.id
                and membre not in tetes
                and membre not in principal_de
            ):
                principal_de[membre] = a.id
    for a in sorted(agents, key=lambda x: x.id):
        p = agent_principal_de(reglages[a.id])
        if (
            p is not None
            and p in ids
            and p != a.id
            and a.id not in tetes
            and a.id not in principal_de
            and p not in principal_de
        ):
            principal_de[a.id] = p
    principaux: dict[int, list[int]] = {t: [] for t in tetes}
    for membre, principal in principal_de.items():
        principaux.setdefault(principal, []).append(membre)

    lus: list[AgentServi] = []
    capacites: dict[int, CapacitesAgent] = {}
    for a in sorted(agents, key=lambda x: x.id):
        capacites[a.id] = (
            capacites_de(a.configurations, outils_de[a.id], outils_travail_de[a.id])
            if a.version_publiee is not None
            else CapacitesAgent()
        )
        if a.id in principaux:
            role, principal = "principal", None
        elif a.id in principal_de:
            role, principal = "specialise", principal_de[a.id]
        else:
            role, principal = "seul", None
        lus.append(
            AgentServi(
                id=a.id,
                nom=a.nom,
                version_publiee=a.version_publiee,
                numeros=list(a.numeros),
                etablissement_id=(a.configurations.get(CLE_FICHE_DE_LAGENT) or None),
                role=role,
                agent_principal_id=principal,
                agents_specialises=sorted(principaux.get(a.id, [])),
                appelle=sorted(appelle[a.id]),
                appele_par=sorted(appele_par[a.id]),
                capacites=capacites[a.id],
                rattache=a.id in rattaches,
            )
        )

    groupes: list[GroupeServi] = []
    for principal in sorted(principaux):
        membres = sorted(principaux[principal])
        ensemble = capacites[principal]
        for m in membres:
            ensemble = ensemble.ou(capacites[m])
        liens = [
            LienDePassation(de=de, vers=vers, par="outil")
            for de in [principal, *membres]
            for vers in sorted(appelle[de])
            if vers in membres or vers == principal
        ]
        liens += [LienDePassation(de=m, vers=principal, par="retour") for m in membres]
        groupes.append(
            GroupeServi(
                principal_id=principal,
                specialises=membres,
                capacites=ensemble,
                passations=liens,
                rattache=principal in rattaches,
            )
        )
    return AgentsServis(agents=lus, groupes=groupes)


def _statut(valeur) -> str:
    return str(getattr(valeur, "value", valeur))


def _version_publiee(workflow):
    """La version que les appels lisent : celle que l'agent désigne comme publiée (``released_definition_id``,
    posée par la publication), sinon la plus récente des versions publiées. ``None`` : jamais publié."""
    versions = list(workflow.definitions)
    pointee = getattr(workflow, "released_definition_id", None)
    trouvee = next((d for d in versions if d.id == pointee), None) if pointee else None
    if trouvee is not None and _statut(trouvee.status) == "published":
        return trouvee
    publiees = [d for d in versions if _statut(d.status) == "published"]
    return max(publiees, key=lambda d: d.version_number or 0) if publiees else None


async def lire_agents_lus(organization_id: int) -> tuple[list[AgentLu], list[str]]:
    """Les agents ACTIFS de l'organisation avec leur version publiée, leurs numéros actifs et les uuid
    d'outils de leurs étapes publiées. Le second rendu : les uuid d'outils de tous."""
    from api.db import db_client
    from api.services.etablissements.appel import _normaliser
    from api.services.travail.reglages import ReglagesTravail

    numeros: dict[int, list[str]] = {}
    for (
        adresse,
        _libelle,
        agent,
        _nom,
        actif,
    ) in await db_client.lister_numeros_de_lorganisation(organization_id):
        canonique = _normaliser(adresse)
        if agent is not None and actif and canonique:
            numeros.setdefault(agent, []).append(canonique)
    lus: list[AgentLu] = []
    for workflow in await db_client.list_workflows_for_model_configuration_migration(
        organization_id
    ):
        if _statut(workflow.status) != "active":
            continue
        publiee = _version_publiee(workflow)
        configurations = dict((publiee.workflow_configurations if publiee else None) or {})
        lus.append(
            AgentLu(
                id=workflow.id,
                nom=workflow.name,
                version_publiee=getattr(publiee, "version_number", None)
                if publiee
                else None,
                numeros=numeros.get(workflow.id, []),
                configurations=configurations,
                outils=outils_des_etapes(publiee.workflow_json) if publiee else [],
                # Les outils du cerveau de fond ; ``depuis`` rend une liste vide quand il est éteint.
                outils_travail=list(ReglagesTravail.depuis(configurations).outils),
            )
        )
    toutes = sorted({u for a in lus for u in [*a.outils, *a.outils_travail]})
    return lus, toutes


async def lire_agents_servis(
    organization_id: int, rattaches: set[int] | None = None
) -> AgentsServis:
    """``GET /organizations/agents-servis`` : ce que l'organisation sert, groupes compris."""
    from api.db import db_client

    agents, uuids = await lire_agents_lus(organization_id)
    outils_par_uuid: dict[str, Any] = {}
    if uuids:
        # Filtré par organisation au niveau de la requête, jamais après coup.
        for outil in await db_client.get_tools_by_uuids(uuids, organization_id):
            outils_par_uuid[outil.tool_uuid] = outil
    try:
        return assembler(agents, outils_par_uuid, rattaches or set())
    except Exception as erreur:  # noqa: BLE001 -- une lecture n'écrit rien : on dit ce qu'on sait
        logger.error(
            f"[.mark] Agents served of organization {organization_id} unreadable: {erreur!r}"
        )
        raise


def membres_a_rattacher(servis: AgentsServis, ids: Iterable[int]) -> list[int]:
    """Les agents qu'un rattachement concerne : les agents nommés ET, pour un principal, ses spécialisés
    (A13). Un identifiant qui n'est pas de l'organisation n'y figure pas (la route le refuse avant)."""
    par_id = {a.id: a for a in servis.agents}
    voulus: list[int] = []
    for i in ids:
        if i not in par_id:
            continue
        for x in [i, *par_id[i].agents_specialises]:
            if x not in voulus:
                voulus.append(x)
    return voulus
