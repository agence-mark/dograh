"""[.mark] Settings templates: create, apply, export, import (cloture-code-avant-migration, lot 5).

The rules, from the plan ``modeles-de-reglages`` (M1 to M11):

- a template lives in the organization (M1): every read and write below takes the organization's id and
  goes through ``organization_configurations``; nothing here reads another organization's row;
- it holds the BEHAVIOUR settings only (M6, ``classement.py``), and never a key of access nor a reference
  to a key (M3): the keys are removed when it is created and refused when a file brings one;
- applying is a COPY on the DRAFT (M4, M5): the sections ticked replace exactly their settings, a setting
  the template does not set goes back to its default, everything else is kept; the agent keeps its OWN
  keys (carried over by provider), and a brick the agent cannot run for lack of a key is NOT written (an
  incomplete override would stop the calls) -- the answer says so, the rest is applied.

The write of the configuration reaches the database only through ``db_client`` (the layer boundary).
"""

from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any, Mapping

from loguru import logger
from pydantic import ValidationError

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.modeles_reglages import (
    FORMAT_DU_FICHIER,
    MAX_MODELES,
    MAX_OCTETS_DES_VALEURS,
    VERSION_DU_FORMAT,
    FichierDeModele,
    MentionApplication,
    ModeleDeReglages,
    OrigineDuModele,
    ReglageNonApplique,
    ResultatApplication,
    StockModeles,
)
from api.services.modeles_reglages import classement as cl

CLE = OrganizationConfigurationKey.MODELES_REGLAGES.value
VARIABLE_DU_COMMIT = "RAILWAY_GIT_COMMIT_SHA"
_CLE_V2 = "model_configuration_v2_override"
_CLE_PAR_SERVICE = "model_overrides"


class ModeleRefuse(Exception):
    """A template, a file or a gesture refused, with the setting that causes it when there is one."""

    def __init__(self, message: str, cle: str | None = None, statut: int = 422):
        super().__init__(message)
        self.message = message
        self.cle = cle
        self.statut = statut


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #


async def lire_le_stock(organization_id: int) -> StockModeles:
    """The organization's templates. ⛔ Strict: a row that exists and cannot be read raises, so the next
    write never replaces templates the screen could not show."""
    ligne = await db_client.get_configuration(organization_id, CLE)
    if ligne is None or not ligne.value:
        return StockModeles()
    return StockModeles.model_validate(ligne.value)


async def ecrire_le_stock(organization_id: int, stock: StockModeles) -> StockModeles:
    await db_client.upsert_configuration(organization_id, CLE, stock.model_dump(mode="json"))
    return stock


def _nom_pris(stock: StockModeles, nom: str, sauf: str | None = None) -> bool:
    vise = nom.strip().casefold()
    return any(m.nom.strip().casefold() == vise and m.id != sauf for m in stock.modeles)


def _nom_libre(stock: StockModeles, nom: str) -> str:
    """A name no template of the organization carries: the file's name, then « (2) », « (3) »..."""
    if not _nom_pris(stock, nom):
        return nom
    rang = 2
    while _nom_pris(stock, f"{nom} ({rang})"):
        rang += 1
    return f"{nom} ({rang})"


def trouver(stock: StockModeles, modele_id: str) -> ModeleDeReglages:
    for modele in stock.modeles:
        if modele.id == modele_id:
            return modele
    raise ModeleRefuse("Template not found.", statut=404)


# --------------------------------------------------------------------------- #
# What an agent runs with: the active settings (draft if any, else the published version)
# --------------------------------------------------------------------------- #


async def configuration_active(workflow_id: int, organization_id: int) -> dict[str, Any]:
    """The settings the page of the agent shows, with where they come from. 404 for another organization's
    agent (the lookup is scoped)."""
    workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
    if not workflow:
        raise ModeleRefuse("Agent not found.", statut=404)
    brouillon = await db_client.get_draft_version(workflow_id)
    if brouillon is not None:
        definition, statut = brouillon, "draft"
    else:
        definition, statut = getattr(workflow, "released_definition", None), "published"
    configurations = copy.deepcopy(getattr(definition, "workflow_configurations", None) or {})
    return {
        "configurations": configurations,
        "version_number": getattr(definition, "version_number", None),
        "version_status": statut,
        "agent_nom": workflow.name,
    }


# --------------------------------------------------------------------------- #
# Create, rename, delete
# --------------------------------------------------------------------------- #


def valeurs_du_modele(configurations: Mapping[str, Any]) -> dict[str, Any]:
    """The settings of an agent a template can hold, without any key of access (M3, M6)."""
    valeurs: dict[str, Any] = {}
    for cle in cl.cles_du_modele():
        if configurations.get(cle) is None:
            continue
        valeurs[cle] = cl.valeur_pour_le_modele(cle, configurations[cle])
    return valeurs


async def creer_un_modele(organization_id: int, nom: str, workflow_id: int) -> ModeleDeReglages:
    stock = await lire_le_stock(organization_id)
    if len(stock.modeles) >= MAX_MODELES:
        raise ModeleRefuse(f"An organization holds {MAX_MODELES} templates at most.")
    if _nom_pris(stock, nom):
        raise ModeleRefuse("Another template already has this name.", statut=409)
    active = await configuration_active(workflow_id, organization_id)
    valeurs = valeurs_du_modele(active["configurations"])
    modele = ModeleDeReglages(
        id=uuid.uuid4().hex[:12],
        nom=nom,
        cree_le=datetime.now(UTC),
        origine=OrigineDuModele(
            workflow_id=workflow_id,
            agent_nom=active["agent_nom"],
            version_number=active["version_number"],
            version_status=active["version_status"],
        ),
        commit=os.getenv(VARIABLE_DU_COMMIT) or None,
        sections=cl.sections_presentes(valeurs),
        valeurs=valeurs,
    )
    stock.modeles.append(modele)
    await ecrire_le_stock(organization_id, stock)
    return modele


async def renommer_un_modele(organization_id: int, modele_id: str, nom: str) -> ModeleDeReglages:
    stock = await lire_le_stock(organization_id)
    modele = trouver(stock, modele_id)
    if _nom_pris(stock, nom, sauf=modele_id):
        raise ModeleRefuse("Another template already has this name.", statut=409)
    modele.nom = nom
    await ecrire_le_stock(organization_id, stock)
    return modele


async def supprimer_un_modele(organization_id: int, modele_id: str) -> None:
    """M4: no agent already set is touched; the mention they keep carries a copy of the name."""
    stock = await lire_le_stock(organization_id)
    trouver(stock, modele_id)
    stock.modeles = [m for m in stock.modeles if m.id != modele_id]
    await ecrire_le_stock(organization_id, stock)


# --------------------------------------------------------------------------- #
# Export, import
# --------------------------------------------------------------------------- #


def fichier_du_modele(modele: ModeleDeReglages) -> FichierDeModele:
    """The file of a template. The values are read back through the same filter as at creation: a key that
    would have slipped into a stored row is not exported (M3, the test proves it)."""
    valeurs = {c: cl.valeur_pour_le_modele(c, v) for c, v in modele.valeurs.items()}
    return FichierDeModele(
        commit=modele.commit,
        nom=modele.nom,
        cree_le=modele.cree_le,
        origine=modele.origine,
        valeurs=valeurs,
    )


def verifier_le_fichier(fichier: FichierDeModele) -> dict[str, Any]:
    """The values of a file, or a refusal that NAMES the setting (never kept in silence)."""
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

    if fichier.format != FORMAT_DU_FICHIER:
        raise ModeleRefuse(f"Not a settings template file (format « {fichier.format} »).")
    if fichier.version_du_format != VERSION_DU_FORMAT:
        raise ModeleRefuse(f"File format version {fichier.version_du_format} is not read by this server.")
    if len(json.dumps(fichier.valeurs, default=str)) > MAX_OCTETS_DES_VALEURS:
        raise ModeleRefuse("The file is too large to be a settings template.")
    chemin = cl.premiere_cle_trouvee(fichier.valeurs)
    if chemin:
        raise ModeleRefuse(
            f"The file holds a key of access ({chemin}): a template never does. Nothing was kept.", cle=chemin
        )
    admises = set(cl.cles_du_modele())
    for cle, valeur in fichier.valeurs.items():
        if cle not in admises:
            if cle in cl.EXCLUES_DU_MODELE or cle in cl.CLES_PROPRES:
                raison = "it stays with the agent and is never part of a template"
            else:
                raison = "this server does not know it"
            raise ModeleRefuse(f"Setting « {cle} » refused: {raison}.", cle=cle)
        if valeur is None:
            raise ModeleRefuse(f"Setting « {cle} » has no value.", cle=cle)
        if cle in WorkflowConfigurationDefaults.model_fields:
            try:
                WorkflowConfigurationDefaults.model_validate({cle: valeur})
            except ValidationError as erreur:
                premier = erreur.errors()[0]
                raise ModeleRefuse(f"Setting « {cle} » refused: {premier.get('msg', 'invalid value')}.", cle=cle) from None
    return copy.deepcopy(fichier.valeurs)


async def importer_un_fichier(organization_id: int, fichier: FichierDeModele) -> ModeleDeReglages:
    valeurs = verifier_le_fichier(fichier)
    stock = await lire_le_stock(organization_id)
    if len(stock.modeles) >= MAX_MODELES:
        raise ModeleRefuse(f"An organization holds {MAX_MODELES} templates at most.")
    modele = ModeleDeReglages(
        id=uuid.uuid4().hex[:12],
        nom=_nom_libre(stock, fichier.nom),
        cree_le=datetime.now(UTC),
        # The origin of a file is the organization it came from: its agent means nothing here (M1).
        origine=None,
        commit=fichier.commit,
        sections=cl.sections_presentes(valeurs),
        valeurs=valeurs,
    )
    stock.modeles.append(modele)
    await ecrire_le_stock(organization_id, stock)
    return modele


# --------------------------------------------------------------------------- #
# Apply
# --------------------------------------------------------------------------- #


def _valider_les_briques(
    candidat: dict[str, Any], org_effectif: Any | None
) -> None:
    """Raises when the bricks, as they would be written, could not run a call."""
    from api.schemas.ai_model_configuration import (
        EffectiveAIModelConfiguration,
        OrganizationAIModelConfigurationV2,
        compile_ai_model_configuration_v2,
    )
    from api.services.configuration.resolve import resolve_effective_config

    if candidat.get(_CLE_V2):
        compile_ai_model_configuration_v2(OrganizationAIModelConfigurationV2.model_validate(candidat[_CLE_V2]))
    elif candidat.get(_CLE_PAR_SERVICE):
        de_base = org_effectif if org_effectif is not None else EffectiveAIModelConfiguration()
        resolve_effective_config(de_base, copy.deepcopy(candidat[_CLE_PAR_SERVICE]))


def calculer_l_application(
    valeurs: Mapping[str, Any],
    sections: list[str],
    base: Mapping[str, Any],
    *,
    cles_de_l_organisation: Mapping[str, Any] | None = None,
    org_effectif: Any | None = None,
) -> tuple[dict[str, Any], ResultatApplication]:
    """The settings the agent would hold after the template, and what happened to each.

    Pure: ``base`` is the agent's active configuration, ``cles_de_l_organisation`` the organization's
    configuration with its real keys (the same shapes as the agent's: v2 and per-service), only read to
    find a key for a provider the agent has none for. Nothing is mutated."""
    nouveau = copy.deepcopy(dict(base or {}))
    choisies = [s for s in cl.SECTIONS if s in sections]
    posees: list[str] = []
    retirees: list[str] = []
    non_appliquees: list[ReglageNonApplique] = []
    sans_cle: list[str] = []
    vues: set[str] = set()

    for section in choisies:
        for cle in cl.cles_de_la_section(section):
            if cle in vues:
                continue
            groupe = cl.groupe_atomique_de(cle)
            if groupe is not None:
                vues.update(groupe)
                _appliquer_un_groupe(
                    groupe, valeurs, base, nouveau, cles_de_l_organisation, org_effectif,
                    posees, retirees, non_appliquees, sans_cle,
                )
                continue
            vues.add(cle)
            if cle in valeurs:
                recu = cl.valeur_pour_lagent(cle, valeurs[cle], base.get(cle))
                cl.reporter_les_cles(recu, base.get(cle))
                nouveau[cle] = recu
                posees.append(cle)
            elif cle in nouveau:
                del nouveau[cle]
                retirees.append(cle)
    resultat = ResultatApplication(
        ecrit=False,
        sections=choisies,
        posees=posees,
        retirees=retirees,
        non_appliquees=non_appliquees,
        fournisseurs_sans_cle=sans_cle,
    )
    return nouveau, resultat


def _appliquer_un_groupe(
    groupe: tuple[str, ...],
    valeurs: Mapping[str, Any],
    base: Mapping[str, Any],
    nouveau: dict[str, Any],
    cles_org: Mapping[str, Any] | None,
    org_effectif: Any | None,
    posees: list[str],
    retirees: list[str],
    non_appliquees: list[ReglageNonApplique],
    sans_cle: list[str],
) -> None:
    """The bricks go together or not at all: half a pair (a full configuration and per-service overlays
    of another provider) would run a call on something nobody chose."""
    candidat = {c: v for c, v in nouveau.items() if c not in groupe}
    venant_du_modele = [c for c in groupe if c in valeurs]
    for cle in venant_du_modele:
        recu = cl.valeur_pour_lagent(cle, valeurs[cle], base.get(cle))
        cl.reporter_les_cles(recu, base.get(cle))
        if cles_org is not None and cle in (_CLE_V2, _CLE_PAR_SERVICE):
            cl.reporter_les_cles(recu, cles_org.get(cle) if cle in cles_org else None)
        candidat[cle] = recu
    try:
        _valider_les_briques(candidat, org_effectif)
    except Exception as erreur:  # noqa: BLE001 -- anything that stops the bricks from compiling
        manquants = cl.fournisseurs_sans_cle([candidat.get(_CLE_V2), candidat.get(_CLE_PAR_SERVICE)])
        for fournisseur in manquants:
            if fournisseur not in sans_cle:
                sans_cle.append(fournisseur)
        for cle in venant_du_modele or list(groupe[:1]):
            if cle == "mark_per_service_override":
                continue
            non_appliquees.append(
                ReglageNonApplique(
                    cle=cle,
                    raison="cle-manquante" if manquants else "invalide",
                    detail=None if manquants else type(erreur).__name__,
                )
            )
        return
    for cle in groupe:
        if cle in venant_du_modele:
            nouveau[cle] = candidat[cle]
            posees.append(cle)
        elif cle in nouveau:
            del nouveau[cle]
            retirees.append(cle)


async def _cles_de_l_organisation(organization_id: int) -> tuple[dict[str, Any], Any | None]:
    """The organization's model configuration with its real keys, in the shapes the agent's settings take:
    only used to find a key for a provider the agent holds none for (the same fallback the route that
    saves an agent uses). Unreadable: nothing found, the answer then says which providers lack a key."""
    try:
        from api.services.configuration.ai_model_configuration import (
            get_resolved_ai_model_configuration,
        )

        resolue = await get_resolved_ai_model_configuration(organization_id=organization_id)
        cles: dict[str, Any] = {}
        if resolue.organization_configuration is not None:
            cles[_CLE_V2] = resolue.organization_configuration.model_dump(mode="json", exclude_none=True)
        cles[_CLE_PAR_SERVICE] = resolue.effective.model_dump(mode="json", exclude_none=True)
        return cles, resolue.effective
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Model configuration of organization {organization_id} unreadable: {erreur!r}")
        return {}, None


async def appliquer_un_modele(
    organization_id: int,
    modele_id: str,
    workflow_id: int,
    sections: list[str],
    *,
    a_blanc: bool,
    verifier,
) -> ResultatApplication:
    """Apply a template to the DRAFT of an agent of the organization (M4, M5).

    ``verifier(configurations)`` is the route's own check of what would be written (the same validators as
    the save of an agent: a combination the save refuses is refused here, 422, nothing written)."""
    inconnues = [s for s in sections if s not in cl.SECTIONS]
    if inconnues:
        raise ModeleRefuse(f"Unknown section: {inconnues[0]}.")
    if not sections:
        raise ModeleRefuse("Tick at least one section.")
    stock = await lire_le_stock(organization_id)
    modele = trouver(stock, modele_id)
    active = await configuration_active(workflow_id, organization_id)
    cles_org, effectif = await _cles_de_l_organisation(organization_id)
    nouveau, resultat = calculer_l_application(
        modele.valeurs,
        sections,
        active["configurations"],
        cles_de_l_organisation=cles_org,
        org_effectif=effectif,
    )
    verifier(nouveau)
    if a_blanc:
        return resultat
    await db_client.update_workflow(
        workflow_id=workflow_id,
        name=None,
        workflow_definition=None,
        template_context_variables=None,
        workflow_configurations=nouveau,
        organization_id=organization_id,
    )
    # An agent that is the main one of a group hands its common settings to its specialised agents, as
    # every save of the agent does (one gesture, idempotent, never raises).
    from api.services.groupe.groupe import recopier_dans_les_specialises

    await recopier_dans_les_specialises(workflow_id, organization_id)
    stock = await lire_le_stock(organization_id)
    stock.applications[str(workflow_id)] = MentionApplication(
        modele_id=modele.id,
        nom=modele.nom,
        applique_le=datetime.now(UTC),
        sections=resultat.sections,
    )
    await ecrire_le_stock(organization_id, stock)
    return resultat.model_copy(update={"ecrit": True})


async def mention_de_l_agent(organization_id: int, workflow_id: int) -> MentionApplication | None:
    """The mention an agent of the organization keeps (M4). 404 for another organization's agent."""
    workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
    if not workflow:
        raise ModeleRefuse("Agent not found.", statut=404)
    stock = await lire_le_stock(organization_id)
    return stock.applications.get(str(workflow_id))
