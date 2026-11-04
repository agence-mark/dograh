"""[.mark] La copie d'un agent (et de son groupe) d'une organisation à une autre : toujours en brouillon, jamais publiée.

Ce que la copie garantit :

* l'original n'est pas touché (lecture seule sous la source) ;
* chaque écriture se fait sous l'organisation de la cible ; chaque référence est remplacée par celle de la cible ou retirée ;
* aucune clé n'est copiée : « relier » désigne une clé de la cible, sinon le champ est vidé ; les valeurs sous un nom de secret sont retirées ;
* aucun identifiant de la source ne reste dans la copie (outils, documents, clés, déclencheurs, agents du groupe, organisation) ;
* rejouée, la copie n'est pas refaite : le journal du Labo (``registre``) rend la copie déjà faite ;
* la fiche d'établissement suit (sans les numéros) vers un client SANS base client ; avec une base, elle ne voyage pas ;
* une copie qui échoue défait ce qu'elle a créé (agents et outils archivés, documents retirés), puis le dit.
"""

from __future__ import annotations

import copy
import posixpath
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from api.db import db_client
from api.db.folder_client import FolderNameConflictError
from api.enums import WorkflowStatus
from api.services.builder import recettes
from api.services.builder.tests_agent import stockage as stockage_tests
from api.services.export_agent import registre
from api.services.export_agent.modeles import AgentCopie, ChoixElement, CompteRendu, ErreurCopie, LigneCompte
from api.services.export_agent.purge import (
    purger_les_secrets,
    regenerer_les_declencheurs,
    remplacer_les_cles,
    retirer_les_identifiants,
)
from api.services.export_agent.releve import (
    RAMENER,
    Plan,
    cible_de_passation,
    charger_le_plan,
    copie_existante,
)
from api.services.groupe.groupe import (
    CLE_AGENT_PRINCIPAL,
    CLE_AGENTS_SPECIALISES,
    _creer_sous_dossier,
    graphe_minimal_du_specialise,
    lire_agent,
    specialises_de,
)
from api.services.groupe.passations import est_un_outil_de_passation
from api.services.workflow.duplicate import _copy_storage_object

DOSSIER_DES_COPIES = "Copies de clients"


@dataclass
class _Journal:
    """Ce que la copie a créé, pour le défaire si elle échoue."""

    agents: list[int] = field(default_factory=list)
    outils: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    enregistrements: list[str] = field(default_factory=list)
    tests: list[tuple[int, str]] = field(default_factory=list)
    etablissements: list[str] = field(default_factory=list)


def _choisir(plan: Plan, demandes: list[ChoixElement]) -> dict[tuple[str, str], tuple[str, str | None]]:
    """Le choix de chaque élément du relevé : (type, ref) -> (action, cible). Un choix hors relevé ou hors des actions permises est refusé."""
    par_element = {(e.type, e.ref): e for e in plan.elements}
    envoyes: dict[tuple[str, str], ChoixElement] = {}
    for d in demandes:
        cle = (d.type, d.ref)
        if cle not in par_element:
            raise ErreurCopie("A choice names an element that this agent does not carry.", 422)
        envoyes[cle] = d
    retenus: dict[tuple[str, str], tuple[str, str | None]] = {}
    for cle, element in par_element.items():
        d = envoyes.get(cle)
        action = d.action if d else element.defaut
        if action not in element.choix:
            raise ErreurCopie(f"“{element.nom}”: this choice is not available.", 422)
        cible = None
        if action == "relier":
            cible = (d.cible if d and d.cible else None) or element.cible_par_defaut
            if cible not in {c.ref for c in element.cibles}:
                raise ErreurCopie(f"“{element.nom}”: the item to link to does not exist in the target.", 422)
        if action == "copier" and element.type == "enregistrement" and element.ref in plan.enregistrements_cible:
            action, cible = "relier", element.ref  # l'identifiant est unique par organisation : on relie
        retenus[cle] = (action, cible)
    return retenus


async def _dossier_des_copies(cible: int) -> int:
    for dossier in await db_client.list_folders(cible):
        if dossier.name == DOSSIER_DES_COPIES and dossier.parent_id is None:
            return dossier.id
    try:
        return (await db_client.create_folder(name=DOSSIER_DES_COPIES, organization_id=cible, parent_id=None)).id
    except FolderNameConflictError:
        for dossier in await db_client.list_folders(cible):
            if dossier.name == DOSSIER_DES_COPIES and dossier.parent_id is None:
                return dossier.id
        raise


async def _dossier_au_choix(plan: Plan, dossier_id: int | None) -> int | None:
    """SE-9 (A-7) : le dossier choisi pour une copie ramenée au Labo doit être un vrai dossier de la cible (422 sinon). Ignoré à l'export."""
    if dossier_id is None or plan.sens != RAMENER:
        return None
    if dossier_id not in {d.id for d in await db_client.list_folders(plan.cible)}:
        raise ErreurCopie("The chosen folder does not exist in the target.", 422)
    return dossier_id


async def _dossier_du_groupe(nom: str, cible: int, parent: int | None) -> int:
    """Un sous-dossier au nom libre (« Accueil », puis « Accueil (2) »…) : les noms pris sont lus d'abord, un conflit ne sert que de filet."""
    pris = {d.name for d in await db_client.list_folders(cible)}
    libre = nom if nom not in pris else next(f"{nom} ({n})" for n in range(2, 1000) if f"{nom} ({n})" not in pris)
    try:
        return (await db_client.create_folder(name=libre, organization_id=cible, parent_id=parent)).id
    except FolderNameConflictError:
        return (await _creer_sous_dossier(nom, cible, parent)).id


def _reecrire_la_definition(
    definition: dict,
    outils: dict[str, str | None],
    documents: dict[str, str | None],
    cles: dict[str, str | None],
    enregistrements: dict[str, str | None],
) -> dict:
    neuve = regenerer_les_declencheurs(definition)
    for noeud in neuve.get("nodes") or []:
        donnees = noeud.get("data") if isinstance(noeud, dict) else None
        if not isinstance(donnees, dict):
            continue
        if "tool_uuids" in donnees:
            donnees["tool_uuids"] = [outils[u] for u in donnees["tool_uuids"] or [] if outils.get(u)]
        if "document_uuids" in donnees:
            donnees["document_uuids"] = [documents[u] for u in donnees["document_uuids"] or [] if documents.get(u)]
        accueil = donnees.get("greeting_recording_id")
        if isinstance(accueil, str) and accueil in enregistrements:
            if enregistrements[accueil]:
                donnees["greeting_recording_id"] = enregistrements[accueil]
            else:
                donnees.pop("greeting_recording_id", None)
        noeud["data"] = remplacer_les_cles(donnees, cles)
    return neuve


async def _copier_les_tests(source: int, cible: int, ancien: int, nouveau: int, journal: _Journal) -> int:
    nombre = 0
    for test in await stockage_tests.lister(source, ancien):
        propre, _ = purger_les_secrets(retirer_les_identifiants(test))
        try:
            await stockage_tests.ecrire(cible, nouveau, propre)
        except stockage_tests.ErreurTest as erreur:
            logger.warning(f"export_agent: a test was not copied ({erreur})")
            continue
        journal.tests.append((nouveau, propre["slug"]))
        nombre += 1
    return nombre


async def _copier_la_fiche(plan: Plan, eid: str, journal: _Journal) -> None:
    """SE-7 (A-8) : écrit chez la cible la fiche d'établissement de la source, sans les numéros (comme ``etablissements/duplication``).
    Les autres fiches de la cible sont gardées ; un identifiant déjà pris chez elle n'est jamais écrasé."""
    from api.schemas.etablissements import CatalogueEtablissements
    from api.services.etablissements.duplication import sans_les_numeros
    from api.services.etablissements.stockage import (
        enregistrer_etablissements,
        lire_etablissements,
        lire_etablissements_strict,
        verrou_des_fiches,
    )

    if eid not in plan.etablissements_copiables:
        raise ErreurCopie(f"“{eid}”: this establishment cannot be copied to the target.", 422)
    origine = next((e for e in (await lire_etablissements(plan.source)).etablissements if e.id == eid), None)
    if origine is None:
        raise ErreurCopie(f"“{eid}”: this establishment cannot be read in the source.", 422)
    async with verrou_des_fiches(plan.cible):
        chez_la_cible = await lire_etablissements_strict(plan.cible)
        if any(e.id == eid for e in chez_la_cible.etablissements):
            raise ErreurCopie(f"“{eid}”: this establishment already exists in the target.", 409)
        neuf = CatalogueEtablissements(etablissements=[*chez_la_cible.etablissements, sans_les_numeros(origine)])
        await enregistrer_etablissements(plan.cible, neuf, "copie", preremplir=False)
    journal.etablissements.append(eid)


async def _retirer_les_fiches_copiees(journal: _Journal, cible: int) -> None:
    from api.schemas.etablissements import CatalogueEtablissements
    from api.services.etablissements.stockage import (
        enregistrer_etablissements,
        lire_etablissements_strict,
        verrou_des_fiches,
    )

    async with verrou_des_fiches(cible):
        reste = await lire_etablissements_strict(cible)
        gardees = [e for e in reste.etablissements if e.id not in journal.etablissements]
        await enregistrer_etablissements(cible, CatalogueEtablissements(etablissements=gardees), "copie", preremplir=False)


async def _defaire(journal: _Journal, cible: int) -> None:
    """Défait au mieux ce que la copie a créé. Ne lève jamais : l'erreur d'origine est celle qu'on rend."""
    for workflow_id, slug in journal.tests:
        try:
            await stockage_tests.supprimer(cible, workflow_id, slug)
        except Exception:  # noqa: BLE001
            logger.exception("export_agent: rollback of a test failed")
    for workflow_id in journal.agents:
        try:
            await db_client.update_workflow_status(
                workflow_id=workflow_id, status=WorkflowStatus.ARCHIVED.value, organization_id=cible
            )
        except Exception:  # noqa: BLE001
            logger.exception("export_agent: rollback of an agent failed")
    for u in journal.outils:
        try:
            await db_client.archive_tool(u, cible)
        except Exception:  # noqa: BLE001
            logger.exception("export_agent: rollback of a tool failed")
    for u in journal.documents:
        try:
            await db_client.delete_document(u, cible)
        except Exception:  # noqa: BLE001
            logger.exception("export_agent: rollback of a document failed")
    for rid in journal.enregistrements:
        try:
            await db_client.delete_recording(rid, cible)
        except Exception:  # noqa: BLE001
            logger.exception("export_agent: rollback of a recording failed")
    if journal.etablissements:
        try:
            await _retirer_les_fiches_copiees(journal, cible)
        except Exception:  # noqa: BLE001
            logger.exception("export_agent: rollback of an establishment failed")


async def copier(
    *,
    user: Any,
    sens: str,
    workflow_id: int,
    source: int,
    cible: int,
    nom_de_la_source: str,
    demandes: list[ChoixElement],
    avec_tests: bool,
    nom: str | None = None,
    dossier_id: int | None = None,
) -> CompteRendu:
    plan = await charger_le_plan(sens, workflow_id, source, cible)
    dossier_id = await _dossier_au_choix(plan, dossier_id)
    nom = (nom or "").strip() or None
    async with registre.verrou(sens, source, plan.racine.id, cible):
        deja = await copie_existante(plan)
        if deja is not None:
            return CompteRendu(
                sens=sens, deja_copie=True, cible_organization_id=cible, agent_id=deja.agent_id,
                agents=[AgentCopie(id=deja.agent_id, nom=deja.nom)], dossier_id=None, lignes=[], tests_copies=0, secrets_retires=0,
            )
        choix = _choisir(plan, demandes)
        journal = _Journal()
        try:
            return await _ecrire(plan, choix, user, nom_de_la_source, avec_tests, journal, nom, dossier_id)
        except ErreurCopie:
            await _defaire(journal, cible)
            raise
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"export_agent: the copy of agent {workflow_id} failed and was undone ({type(erreur).__name__})")
            await _defaire(journal, cible)
            raise ErreurCopie("The copy failed; nothing was kept.", 500) from erreur


async def _ecrire(
    plan: Plan,
    choix: dict[tuple[str, str], tuple[str, str | None]],
    user: Any,
    nom_de_la_source: str,
    avec_tests: bool,
    journal: _Journal,
    nom: str | None = None,
    dossier_choisi: int | None = None,
) -> CompteRendu:
    cible, source = plan.cible, plan.source
    lignes: list[LigneCompte] = []
    secrets = 0
    ramener = plan.sens == RAMENER
    groupe = len(plan.agents) > 1

    def nom_de_la_copie(nom_d_origine: str) -> str:
        if ramener and nom and nom_d_origine == plan.racine.nom:
            return nom  # SE-9 (A-7) : le nom choisi pour l'agent ramené (ses spécialisés gardent le nom d'usage)
        return f"{nom_d_origine} ({nom_de_la_source})" if ramener and nom_de_la_source else nom_d_origine

    # 1. Les dossiers.
    parent = (dossier_choisi or await _dossier_des_copies(cible)) if ramener else None
    dossier_id = parent
    if groupe:
        dossier_id = await _dossier_du_groupe(nom_de_la_copie(plan.racine.nom), cible, parent)

    # 2. Les agents (squelette publié à la création, définition réelle écrite en brouillon : rien n'est publié).
    agents_neufs: dict[int, int] = {}
    for agent in plan.agents:
        neuf = await db_client.create_workflow(nom_de_la_copie(agent.nom), graphe_minimal_du_specialise(), user.id, cible)
        journal.agents.append(neuf.id)
        agents_neufs[agent.id] = neuf.id
        if dossier_id is not None:
            await db_client.move_workflow_to_folder(workflow_id=neuf.id, folder_id=dossier_id, organization_id=cible)
        lignes.append(LigneCompte(type="agent", nom=agent.nom, action="copier"))

    # 3. Les clés : reliées par leur nom à une clé de la cible, ou vides. Jamais copiées.
    cles: dict[str, str | None] = {}
    for u, cle in plan.cles.items():
        action, vers = choix[("cle", u)]
        cles[u] = vers if action == "relier" else None
        lignes.append(LigneCompte(type="cle", nom=cle.name, action=action, code="jamais_copiee"))

    # 4. Les documents.
    documents: dict[str, str | None] = {}
    for u, document in plan.documents.items():
        action, vers = choix[("document", u)]
        if action == "relier":
            documents[u] = vers
        elif action == "copier":
            copie = await db_client.copier_un_document(u, source, cible, user.id)
            if copie is None:
                documents[u] = None
                action = "vide"
            else:
                journal.documents.append(copie.document_uuid)
                documents[u] = copie.document_uuid
        else:
            documents[u] = None
        lignes.append(LigneCompte(type="document", nom=document.filename, action=action))

    # 5. Les enregistrements (le fichier est copié dans le stockage de la cible ; sans lui, l'enregistrement reste vide).
    enregistrements: dict[str, str | None] = {}
    for rid in plan.enregistrements:
        action, vers = choix[("enregistrement", rid)]
        if action == "relier":
            enregistrements[rid] = vers
        elif action == "copier":
            adresse = await db_client.adresse_de_stockage_d_un_enregistrement(rid, source)
            copie = None
            if adresse is not None:
                nouvelle = f"recordings/{cible}/{posixpath.basename(adresse[0])}"
                try:
                    if await _copy_storage_object(adresse[0], nouvelle, adresse[1]):
                        copie = await db_client.copier_un_enregistrement(rid, source, cible, user.id, nouvelle)
                except Exception as erreur:  # noqa: BLE001
                    logger.warning(f"export_agent: a recording file was not copied ({type(erreur).__name__})")
            if copie is None:
                enregistrements[rid] = None
                action = "vide"
            else:
                journal.enregistrements.append(rid)
                enregistrements[rid] = rid
        else:
            enregistrements[rid] = None
        lignes.append(LigneCompte(type="enregistrement", nom=rid, action=action))

    # 6. Les outils (les passations suivent les agents copiés ; les autres : reliés, copiés ou vides).
    outils: dict[str, str | None] = {}
    for u, outil in plan.outils.items():
        action, vers = choix[("outil", u)]
        if est_un_outil_de_passation(outil):
            definition = copy.deepcopy(outil.definition or {})
            config = definition.setdefault("config", {})
            visee = agents_neufs.get(cible_de_passation(outil) or -1)
            if visee is None:
                outils[u] = None
                lignes.append(LigneCompte(type="outil", nom=outil.name, action="vide", code="hors_du_groupe"))
                continue
            config["workflow_id"] = visee
        elif action == "relier":
            outils[u] = vers
            lignes.append(LigneCompte(type="outil", nom=outil.name, action="relier"))
            continue
        elif action == "vide":
            outils[u] = None
            lignes.append(LigneCompte(type="outil", nom=outil.name, action="vide"))
            continue
        else:
            definition = remplacer_les_cles(copy.deepcopy(outil.definition or {}), cles)
        definition, retires = purger_les_secrets(retirer_les_identifiants(definition))
        secrets += retires
        neuf = await db_client.create_tool(
            organization_id=cible, user_id=user.id, name=outil.name, definition=definition, category=outil.category,
            description=outil.description, icon=outil.icon, icon_color=outil.icon_color,
        )
        journal.outils.append(neuf.tool_uuid)
        outils[u] = neuf.tool_uuid
        lignes.append(LigneCompte(type="outil", nom=outil.name, action="copier"))

    # 7. Les établissements : on garde l'identifiant s'il existe chez la cible (« relier ») ; sans base client chez la cible, la fiche
    # suit (« copier », SE-7) sans les numéros ; sinon l'identifiant est retiré.
    etablissements: dict[str, str | None] = {}
    for eid in plan.etablissements:
        action, vers = choix[("etablissement", eid)]
        if action == "copier":
            await _copier_la_fiche(plan, eid, journal)
            etablissements[eid] = eid
        else:
            etablissements[eid] = vers if action == "relier" else None
        lignes.append(LigneCompte(type="etablissement", nom=eid, action=action))

    # 8. La définition et les réglages de chaque agent, écrits en brouillon.
    tests_copies = 0
    for agent in plan.agents:
        neuf = agents_neufs[agent.id]
        definition = _reecrire_la_definition(agent.definition, outils, documents, cles, enregistrements)
        definition, a = purger_les_secrets(retirer_les_identifiants(definition))
        reglages = copy.deepcopy(agent.reglages)
        if CLE_AGENTS_SPECIALISES in reglages:
            reglages[CLE_AGENTS_SPECIALISES] = [agents_neufs[i] for i in reglages[CLE_AGENTS_SPECIALISES] if i in agents_neufs]
        if agent.id == plan.racine.id:
            reglages.pop(CLE_AGENT_PRINCIPAL, None)
        elif CLE_AGENT_PRINCIPAL in reglages:
            reglages[CLE_AGENT_PRINCIPAL] = agents_neufs[plan.racine.id]
        eid = reglages.get("etablissement_id")
        if isinstance(eid, str) and eid in etablissements:
            if etablissements[eid]:
                reglages["etablissement_id"] = etablissements[eid]
            else:
                reglages.pop("etablissement_id", None)
        bruit = reglages.get("ambient_noise_configuration")
        if isinstance(bruit, dict) and bruit.get("storage_key"):
            reglages.pop("ambient_noise_configuration", None)  # un fichier de la source : il ne suit pas
        reglages, b = purger_les_secrets(retirer_les_identifiants(reglages))
        variables, c = purger_les_secrets(retirer_les_identifiants(copy.deepcopy(agent.variables)))
        secrets += a + b + c
        await db_client.update_workflow(
            workflow_id=neuf, name=None, workflow_definition=definition, template_context_variables=variables or None,
            workflow_configurations=reglages, organization_id=cible,
        )
        if avec_tests:
            tests_copies += await _copier_les_tests(source, cible, agent.id, neuf, journal)
        try:
            slug = await recettes.choisie_de_l_agent(source, agent.id)
            recette = await recettes.lire(slug) if slug else None
            await recettes.poser_a_la_creation(cible, neuf, recette, par="copie")
        except Exception as erreur:  # noqa: BLE001 - la recette ne bloque pas la copie ; l'agent prend alors le défaut
            logger.warning(f"export_agent: the recipe of an agent was not carried ({type(erreur).__name__})")

    # 9. Le journal : écrit en dernier, une copie défaite n'y laisse rien.
    await registre.noter(plan.labo, plan.sens, source, plan.racine.id, cible, agents_neufs[plan.racine.id])

    return CompteRendu(
        sens=plan.sens, deja_copie=False, cible_organization_id=cible, agent_id=agents_neufs[plan.racine.id],
        agents=[AgentCopie(id=agents_neufs[a.id], nom=nom_de_la_copie(a.nom)) for a in plan.agents],
        dossier_id=dossier_id, lignes=lignes, tests_copies=tests_copies, secrets_retires=secrets,
    )


async def copier_les_tests_apres_duplication(
    organization_id: int, principal_source: int, principal_copie: int, specialises_copies: list[int]
) -> int:
    """« Dupliquer avec ses tests » (même organisation) : les tests du principal sur sa copie, ceux de chaque spécialisé sur la sienne.

    Les copies de spécialisés sont rendues dans l'ordre des spécialisés d'origine qui existent encore (comme la duplication du groupe)."""
    source = await lire_agent(principal_source, organization_id)
    anciens = [i for i in specialises_de(source.reglages if source else {}) if await lire_agent(i, organization_id) is not None]
    couples = [(principal_source, principal_copie), *zip(anciens, specialises_copies)]
    journal = _Journal()
    total = 0
    for ancien, nouveau in couples:
        total += await _copier_les_tests(organization_id, organization_id, ancien, nouveau, journal)
    return total
