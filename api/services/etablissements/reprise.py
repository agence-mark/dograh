"""[.mark] Chantier agents-specialises, lot 4 (F2, C3, R7): la reprise des fiches et des agents.

Avant la fiche sans héritage, un champ vide d'une fiche était « hérité » : l'adresse de
l'organisation, les annonces de l'organisation, les horaires et l'adresse de l'agent qui la
servait, les réglages de rendez-vous de l'organisation. Une fiche n'hérite plus de rien
(C3) : la reprise ÉCRIT EN DUR ce qu'elle héritait, pour que ce que l'agent dit après soit
exactement ce qu'il disait avant (zéro perte).

Deux gestes, jamais plus :

1. pour chaque fiche, remplir ses champs vides avec ce qu'ils héritaient ;
2. pour chaque agent dont TOUS les numéros mènent à la MÊME fiche, écrire son
   ``etablissement_id`` (un agent déjà rattaché n'est pas retouché).

Ce que la reprise ne décide pas seule (signalé dans ``a_decider``, rien n'est écrit pour
cela) : un agent dont les numéros mènent à plusieurs fiches, ou à une fiche et à aucune ;
des horaires ou une adresse que l'agent dit autrement que la fiche, ou que deux agents de
la même fiche disent différemment. Une valeur déjà écrite sur une fiche n'est JAMAIS
remplacée.

Pure : ce module planifie, la route lit et écrit. Idempotente (rejouée, elle ne trouve plus
rien à faire). Aucun mot de métier : des noms de champs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture
from api.schemas.etablissements import (
    ActionReprise,
    CatalogueEtablissements,
    Etablissement,
)
from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.planificateur import Planificateur, ReglagesPlanificateur
from api.services.communes.adresse import _adresse_de, texte_adresse
from api.services.etablissements.appel import (
    CLE_ADRESSE,
    CLE_FICHE_DE_LAGENT,
    CLE_HORAIRES,
    par_numero_appele,
)

CHAMPS_ANNONCE = ("annonce_fermeture", "annonce_pause")


@dataclass
class AgentVu:
    """Un agent de l'organisation tel que la reprise le voit."""

    id: int
    nom: str
    numeros: list[str] = field(default_factory=list)  # numéros ACTIFS, forme canonique
    configurations: dict = field(default_factory=dict)  # la version publiée


@dataclass
class PlanReprise:
    """Ce que la reprise écrirait."""

    actions: list[ActionReprise] = field(default_factory=list)
    fiches: dict[str, dict] = field(default_factory=dict)  # id de fiche -> champs à écrire
    reglages: dict[str, ReglagesPlanificateur] = field(default_factory=dict)  # fiche -> réglages complétés
    agents: dict[int, str] = field(default_factory=dict)  # id d'agent -> id de fiche
    a_decider: list[str] = field(default_factory=list)
    deja_a_jour: int = 0


def _vide(valeur) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def _forme(texte: str) -> str:
    return " ".join(str(texte).split())


def _agents_de(fiche: Etablissement, agents: list[AgentVu], catalogue: CatalogueEtablissements) -> list[AgentVu]:
    """Les agents qui servent cette fiche par au moins un de leurs numéros."""
    servants = []
    for agent in agents:
        for numero in agent.numeros:
            trouvee = par_numero_appele(catalogue, numero)
            if trouvee is not None and trouvee.id == fiche.id:
                servants.append(agent)
                break
    return servants


def _horaires(plan: PlanReprise, fiche: Etablissement, servants: list[AgentVu], ecrits: dict) -> None:
    dits = {
        _forme(a.configurations[CLE_HORAIRES]): a
        for a in servants
        if not _vide(a.configurations.get(CLE_HORAIRES))
    }
    if _vide(fiche.horaires_ouverture):
        if len(dits) == 1:
            (agent,) = dits.values()
            ecrits["horaires_ouverture"] = agent.configurations[CLE_HORAIRES].strip()
            plan.actions.append(
                ActionReprise(
                    sujet="fiche", cible=fiche.id, champ="horaires_ouverture", avant=None, apres=ecrits["horaires_ouverture"]
                )
            )
        elif len(dits) > 1:
            plan.a_decider.append(
                f"Fiche « {fiche.id} » : ses agents ({', '.join(a.nom for a in servants)}) disent des horaires "
                "différents ; la fiche n'en a pas. Rien n'est écrit : choisir les horaires de la fiche."
            )
    elif any(forme != _forme(fiche.horaires_ouverture) for forme in dits):
        plan.a_decider.append(
            f"Fiche « {fiche.id} » : un agent qui la sert dit d'autres horaires que ceux de la fiche "
            "(avant la fiche sans héritage, l'agent passait devant). La fiche n'est pas modifiée."
        )
    else:
        plan.deja_a_jour += 1


def _adresse(
    plan: PlanReprise,
    fiche: Etablissement,
    servants: list[AgentVu],
    adresse_organisation: AdresseEtablissement | None,
    ecrits: dict,
) -> None:
    dites: dict[str, AdresseEtablissement] = {}
    for agent in servants:
        vue = _adresse_de(agent.configurations.get(CLE_ADRESSE), "Agent")
        if vue is not None:
            dites[texte_adresse(vue)] = vue
    if fiche.adresse is None:
        if len(dites) == 1:
            (ecrits["adresse"],) = dites.values()
        elif len(dites) > 1:
            plan.a_decider.append(
                f"Fiche « {fiche.id} » : ses agents disent des adresses différentes ; la fiche n'en a pas. "
                "Rien n'est écrit : choisir l'adresse de la fiche."
            )
        elif adresse_organisation is not None:
            ecrits["adresse"] = adresse_organisation
        if "adresse" in ecrits:
            plan.actions.append(
                ActionReprise(
                    sujet="fiche", cible=fiche.id, champ="adresse", avant=None, apres=texte_adresse(ecrits["adresse"])
                )
            )
    elif any(texte != texte_adresse(fiche.adresse) for texte in dites):
        plan.a_decider.append(
            f"Fiche « {fiche.id} » : un agent qui la sert dit une autre adresse que celle de la fiche. "
            "La fiche n'est pas modifiée."
        )
    else:
        plan.deja_a_jour += 1


def preparer_reprise(
    catalogue: CatalogueEtablissements,
    agents: list[AgentVu],
    adresse_organisation: AdresseEtablissement | None,
    annonce_organisation: ReglagesAnnonceOuverture | None,
    planificateur: Planificateur | None,
) -> PlanReprise:
    """Le plan de la reprise, sans rien écrire."""
    plan = PlanReprise()
    for fiche in catalogue.etablissements:
        servants = _agents_de(fiche, agents, catalogue)
        ecrits: dict = {}
        _horaires(plan, fiche, servants, ecrits)
        _adresse(plan, fiche, servants, adresse_organisation, ecrits)

        # Annonces : celles de l'organisation (avec leurs valeurs par défaut).
        for champ in CHAMPS_ANNONCE:
            if getattr(fiche, champ) is not None:
                plan.deja_a_jour += 1
                continue
            voulue = getattr(annonce_organisation, champ, None) if annonce_organisation is not None else None
            if _vide(voulue):
                continue  # l'organisation n'annonçait rien : la fiche vide n'annonce rien non plus
            ecrits[champ] = voulue
            plan.actions.append(ActionReprise(sujet="fiche", cible=fiche.id, champ=champ, avant=None, apres=voulue))
        if ecrits:
            plan.fiches[fiche.id] = ecrits

        # Rendez-vous : ce que l'organisation réglait et que la fiche ne dit pas.
        if planificateur is not None:
            propres = (planificateur.par_etablissement.get(fiche.id) or ReglagesPlanificateur()).model_dump()
            completes = dict(propres)
            for cle, valeur in planificateur.reglages.model_dump().items():
                if completes.get(cle) is None and valeur is not None:
                    completes[cle] = valeur
                    plan.actions.append(
                        ActionReprise(sujet="rendez_vous", cible=fiche.id, champ=cle, avant=None, apres=str(valeur))
                    )
            if completes != propres:
                plan.reglages[fiche.id] = ReglagesPlanificateur.model_validate(completes)

    # Agents : tous leurs numéros mènent à la même fiche.
    for agent in agents:
        if not agent.numeros:
            continue
        if not _vide(agent.configurations.get(CLE_FICHE_DE_LAGENT)):
            plan.deja_a_jour += 1
            continue
        mene_a: list[str | None] = []
        for numero in agent.numeros:
            trouvee = par_numero_appele(catalogue, numero)
            mene_a.append(trouvee.id if trouvee else None)
        fiches = {f for f in mene_a if f is not None}
        if not fiches:
            continue  # aucun de ses numéros ne mène à une fiche : l'agent n'est pas concerné
        if len(fiches) == 1 and None not in mene_a:
            (cible,) = fiches
            plan.agents[agent.id] = cible
            plan.actions.append(
                ActionReprise(
                    sujet="agent", cible=f"{agent.nom} ({agent.id})", champ=CLE_FICHE_DE_LAGENT, avant=None, apres=cible
                )
            )
        else:
            plan.a_decider.append(
                f"Agent « {agent.nom} » ({agent.id}) : ses numéros mènent à "
                + ("plusieurs fiches" if len(fiches) > 1 else "une fiche et à aucune autre")
                + ". Rien n'est écrit : choisir sa fiche à la main."
            )
    return plan


# --------------------------------------------------------------------------- #
# Lecture des agents et écriture du rattachement (la base de Dograh)
# --------------------------------------------------------------------------- #

VERSIONS_VIVANTES = ("draft", "published")


def _statut(valeur) -> str:
    return str(getattr(valeur, "value", valeur))


async def lire_agents(organization_id: int) -> list[AgentVu]:
    """Les agents actifs de l'organisation, avec leurs numéros actifs et leur configuration
    PUBLIÉE (celle que les appels lisent). Un agent jamais publié : sa configuration courante."""
    from api.db import db_client
    from api.services.etablissements.appel import _normaliser

    lignes = await db_client.lister_numeros_de_lorganisation(organization_id)
    numeros: dict[int, list[str]] = {}
    for adresse, _libelle, agent, _nom, actif in lignes:
        canonique = _normaliser(adresse)
        if agent is not None and actif and canonique:
            numeros.setdefault(agent, []).append(canonique)
    vus = []
    for workflow in await db_client.list_workflows_for_model_configuration_migration(organization_id):
        if _statut(workflow.status) != "active":
            continue
        publiee = next((d for d in workflow.definitions if d.status == "published"), None)
        configurations = (publiee.workflow_configurations if publiee else workflow.workflow_configurations) or {}
        vus.append(
            AgentVu(
                id=workflow.id,
                nom=workflow.name,
                numeros=numeros.get(workflow.id, []),
                configurations=dict(configurations),
            )
        )
    return vus


async def ecrire_rattachements(organization_id: int, agents: dict[int, str]) -> None:
    """``etablissement_id`` sur chaque agent nommé, dans la version publiée ET dans le
    brouillon s'il y en a un (rien d'un brouillon n'est publié par ce geste), et dans la
    colonne courante de l'agent. Une valeur déjà posée n'est jamais remplacée."""
    if not agents:
        return
    from api.db import db_client

    workflow_updates: list[tuple[int, dict]] = []
    definition_updates: list[tuple[int, dict]] = []
    for workflow in await db_client.list_workflows_for_model_configuration_migration(organization_id):
        fiche = agents.get(workflow.id)
        if fiche is None:
            continue
        courante = dict(workflow.workflow_configurations or {})
        if _vide(courante.get(CLE_FICHE_DE_LAGENT)):
            workflow_updates.append((workflow.id, {**courante, CLE_FICHE_DE_LAGENT: fiche}))
        for definition in workflow.definitions:
            if definition.status not in VERSIONS_VIVANTES:
                continue
            propres = dict(definition.workflow_configurations or {})
            if _vide(propres.get(CLE_FICHE_DE_LAGENT)):
                definition_updates.append((definition.id, {**propres, CLE_FICHE_DE_LAGENT: fiche}))
    await db_client.bulk_update_workflow_model_configurations(
        organization_id=organization_id,
        workflow_updates=workflow_updates,
        definition_updates=definition_updates,
    )
    # [.mark] Lot 8 : la base du client apprend la fiche de chaque agent repris (agent_site).
    from api.services.base_client.agents import synchroniser_agent_site

    for workflow_id, fiche in agents.items():
        await synchroniser_agent_site(organization_id, workflow_id, None, fiche)
