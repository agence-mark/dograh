"""[.mark] Le relevé d'une copie : tout ce que l'agent (et son groupe) référence, une ligne par élément, et ce que la cible propose.

Lecture seule. Les mêmes lectures servent à la copie (``ecriture``) : les choix envoyés par l'écran sont revalidés contre ce relevé,
jamais crus sur parole (un identifiant qui n'est pas dans le relevé n'existe pas).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from api.db import db_client
from api.services.builder.constantes import organisation_bibliotheque
from api.services.builder.tests_agent import stockage as stockage_tests
from api.services.export_agent import registre
from api.services.export_agent.modeles import Cible, DejaCopie, DossierPropose, ElementReleve, ErreurCopie, Releve
from api.services.export_agent.purge import reperer_les_cles
from api.services.groupe.groupe import AgentDeTravail, _entier, lire_agent, specialises_de
from api.services.groupe.passations import CLE_AGENT_PRINCIPAL, est_un_outil_de_passation

EXPORTER = "exporter"
RAMENER = "ramener"
DOCUMENTS_MAX = 500


@dataclass
class Plan:
    sens: str
    source: int
    cible: int
    labo: int
    racine: AgentDeTravail
    agents: list[AgentDeTravail]
    outils: dict[str, Any] = field(default_factory=dict)
    documents: dict[str, Any] = field(default_factory=dict)
    cles: dict[str, Any] = field(default_factory=dict)
    enregistrements: dict[str, Any] = field(default_factory=dict)
    etablissements: list[str] = field(default_factory=list)
    elements: list[ElementReleve] = field(default_factory=list)
    # Ce que la cible propose (pour valider « relier »).
    outils_cible: dict[str, Any] = field(default_factory=dict)
    documents_cible: dict[str, Any] = field(default_factory=dict)
    cles_cible: dict[str, Any] = field(default_factory=dict)
    enregistrements_cible: dict[str, Any] = field(default_factory=dict)
    etablissements_cible: set[str] = field(default_factory=set)
    # SE-7 (A-8) : les fiches que la copie peut écrire chez la cible (cible sans base client, identifiant libre, fiche lisible à la source).
    etablissements_copiables: set[str] = field(default_factory=set)


def verifier_le_sens(sens: str, source: int, cible: int) -> int:
    """Le Labo, ou ``ErreurCopie`` : on n'exporte que du Labo vers un client, on ne ramène que d'un client vers le Labo."""
    labo = organisation_bibliotheque()
    if labo is None:
        raise ErreurCopie("No Labo is set: mark one organization as the Labo first.", 409)
    if source == cible:
        raise ErreurCopie("The source and the target are the same organization (use Duplicate).", 422)
    if sens == EXPORTER and not (source == labo and cible != labo):
        raise ErreurCopie("Only an agent of the Labo can be exported, to a client.", 422)
    if sens == RAMENER and not (source != labo and cible == labo):
        raise ErreurCopie("Only an agent of a client can be brought back, to the Labo.", 422)
    return labo


def donnees_des_noeuds(agent: AgentDeTravail):
    for noeud in (agent.definition or {}).get("nodes") or []:
        if isinstance(noeud, dict) and isinstance(noeud.get("data"), dict):
            yield noeud["data"]


def _liste_de_textes(valeur: Any) -> list[str]:
    return [v for v in valeur if isinstance(v, str) and v] if isinstance(valeur, list) else []


def cible_de_passation(outil: Any) -> int | None:
    config = ((getattr(outil, "definition", None) or {}).get("config")) or {}
    return _entier(config.get("workflow_id"))


async def charger_le_plan(sens: str, workflow_id: int, source: int, cible: int) -> Plan:
    labo = verifier_le_sens(sens, source, cible)
    racine = await lire_agent(workflow_id, source)
    if racine is None or racine.statut != "active":
        raise ErreurCopie(f"Workflow with id {workflow_id} not found", 404)
    if _entier(racine.reglages.get(CLE_AGENT_PRINCIPAL)) is not None:
        raise ErreurCopie("This agent belongs to a group: copy the group from its main agent.", 409)

    agents = [racine]
    for sid in specialises_de(racine.reglages):
        autre = await lire_agent(sid, source)
        if autre is not None and autre.statut == "active" and _entier(autre.reglages.get(CLE_AGENT_PRINCIPAL)) == racine.id:
            agents.append(autre)

    plan = Plan(sens=sens, source=source, cible=cible, labo=labo, racine=racine, agents=agents)

    uuids_outils: set[str] = set()
    uuids_documents: set[str] = set()
    for agent in agents:
        for donnees in donnees_des_noeuds(agent):
            uuids_outils.update(_liste_de_textes(donnees.get("tool_uuids")))
            uuids_documents.update(_liste_de_textes(donnees.get("document_uuids")))
        etablissement = agent.reglages.get("etablissement_id")
        if isinstance(etablissement, str) and etablissement.strip() and etablissement not in plan.etablissements:
            plan.etablissements.append(etablissement)

    for outil in await db_client.get_tools_by_uuids(sorted(uuids_outils), source):
        plan.outils[outil.tool_uuid] = outil
    for u in sorted(uuids_documents):
        document = await db_client.get_document_by_uuid(u, source)
        if document is not None:
            plan.documents[u] = document

    uuids_cles: set[str] = set()
    for agent in agents:
        uuids_cles.update(reperer_les_cles(list(donnees_des_noeuds(agent))))
    for outil in plan.outils.values():
        uuids_cles.update(reperer_les_cles(outil.definition or {}))
    for u in sorted(uuids_cles):
        cle = await db_client.get_credential_by_uuid(u, source)
        if cle is not None:
            plan.cles[u] = cle

    # Les enregistrements : ceux de la source dont l'identifiant est écrit dans la définition (message d'accueil ou texte d'étape).
    ecrit = " ".join(json.dumps(a.definition, ensure_ascii=False) for a in agents)
    for enregistrement in await db_client.get_recordings(source):
        rid = enregistrement.recording_id
        if rid and re.search(r"(?<![\w-])" + re.escape(rid) + r"(?![\w-])", ecrit):
            plan.enregistrements[rid] = enregistrement

    # Ce que la cible propose.
    plan.outils_cible = {o.tool_uuid: o for o in await db_client.get_tools_for_organization(cible)}
    plan.documents_cible = {
        d.document_uuid: d for d in await db_client.get_documents_for_organization(cible, limit=DOCUMENTS_MAX)
    }
    plan.cles_cible = {c.credential_uuid: c for c in await db_client.get_credentials_for_organization(cible)}
    plan.enregistrements_cible = {r.recording_id: r for r in await db_client.get_recordings(cible)}
    from api.services.etablissements.stockage import lire_etablissements

    plan.etablissements_cible = {e.id for e in (await lire_etablissements(cible)).etablissements}
    plan.etablissements_copiables = await _fiches_copiables(plan, source, cible)

    plan.elements = _elements(plan)
    return plan


async def _fiches_copiables(plan: Plan, source: int, cible: int) -> set[str]:
    """SE-7 (A-8) : sans base client chez la cible, la fiche d'établissement suit (sans les numéros). Avec une base, ou si le
    rattachement est illisible, elle ne suit pas : le cas reste « relier » ou « vide »."""
    if not plan.etablissements:
        return set()
    from api.services.etablissements.stockage import lire_etablissements, nom_de_la_base_strict

    try:
        if await nom_de_la_base_strict(cible):
            return set()
    except Exception:  # noqa: BLE001 -- rattachement illisible : rien n'est écrit chez la cible
        return set()
    chez_la_source = {e.id for e in (await lire_etablissements(source)).etablissements}
    return {eid for eid in plan.etablissements if eid in chez_la_source and eid not in plan.etablissements_cible}


def _elements(plan: Plan) -> list[ElementReleve]:
    exporter = plan.sens == EXPORTER
    ids_du_groupe = {a.id for a in plan.agents}
    sortie: list[ElementReleve] = []

    for agent in plan.agents:
        sortie.append(
            ElementReleve(
                type="agent", ref=str(agent.id), nom=agent.nom, choix=["copier"], defaut="copier",
                code="principal" if agent.id == plan.racine.id else "specialise",
            )
        )

    for u, outil in plan.outils.items():
        if est_un_outil_de_passation(outil):
            if cible_de_passation(outil) in ids_du_groupe:
                sortie.append(ElementReleve(type="outil", ref=u, nom=outil.name, choix=["copier"], defaut="copier", code="suit_l_agent"))
            else:
                sortie.append(ElementReleve(type="outil", ref=u, nom=outil.name, choix=["vide"], defaut="vide", code="hors_du_groupe"))
            continue
        equivalents = [
            Cible(ref=c.tool_uuid, nom=c.name) for c in plan.outils_cible.values() if c.name == outil.name and c.category == outil.category
        ]
        choix = (["relier"] if equivalents else []) + ["copier", "vide"]
        defaut = "relier" if equivalents else ("copier" if exporter else "vide")
        sortie.append(
            ElementReleve(
                type="outil", ref=u, nom=outil.name, detail=str(outil.category), choix=choix, defaut=defaut,
                cibles=equivalents, cible_par_defaut=equivalents[0].ref if equivalents else None,
                code="avec_cle" if list(reperer_les_cles(outil.definition or {})) else None,
            )
        )

    for u, document in plan.documents.items():
        equivalents = [Cible(ref=c.document_uuid, nom=c.filename) for c in plan.documents_cible.values() if c.filename == document.filename]
        copiable = document.processing_status == "completed"
        choix = (["relier"] if equivalents else []) + (["copier"] if copiable else []) + ["vide"]
        defaut = "relier" if equivalents else ("copier" if exporter and copiable else "vide")
        sortie.append(
            ElementReleve(
                type="document", ref=u, nom=document.filename, choix=choix, defaut=defaut,
                cibles=equivalents, cible_par_defaut=equivalents[0].ref if equivalents else None,
                code=None if copiable else "pas_pret",
            )
        )

    for u, cle in plan.cles.items():
        propositions = [Cible(ref=c.credential_uuid, nom=c.name) for c in plan.cles_cible.values()]
        meme_nom = next((c.ref for c in propositions if c.nom == cle.name), None)
        sortie.append(
            ElementReleve(
                type="cle", ref=u, nom=cle.name, choix=(["relier"] if propositions else []) + ["vide"],
                defaut="relier" if meme_nom else "vide", cibles=propositions, cible_par_defaut=meme_nom, code="jamais_copiee",
            )
        )

    for rid, enregistrement in plan.enregistrements.items():
        existe = rid in plan.enregistrements_cible
        sortie.append(
            ElementReleve(
                type="enregistrement", ref=rid, nom=rid, detail=(enregistrement.transcript or "")[:120] or None,
                choix=(["relier"] if existe else []) + ["copier", "vide"], defaut="relier" if existe else "vide",
                cibles=[Cible(ref=rid, nom=rid)] if existe else [], cible_par_defaut=rid if existe else None,
            )
        )

    for eid in plan.etablissements:
        existe = eid in plan.etablissements_cible
        copiable = eid in plan.etablissements_copiables
        sortie.append(
            ElementReleve(
                type="etablissement", ref=eid, nom=eid, choix=(["relier"] if existe else []) + (["copier"] if copiable else []) + ["vide"],
                defaut="relier" if existe else ("copier" if copiable else "vide"), cibles=[Cible(ref=eid, nom=eid)] if existe else [],
                cible_par_defaut=eid if existe else None, code="sans_numeros" if copiable else None,
            )
        )
    return sortie


async def copie_deja_faite(sens: str, labo: int, source: int, agent_id: int, cible: int) -> DejaCopie | None:
    """La copie déjà faite de cet agent vers cette cible, si elle existe encore (non archivée). Lecture légère : pas de relevé."""
    ligne = await registre.lire(labo, sens, source, agent_id, cible)
    copie_id = _entier((ligne or {}).get("agent_id"))
    if copie_id is None:
        return None
    existant = await lire_agent(copie_id, cible)
    if existant is None or existant.statut != "active":
        return None
    return DejaCopie(agent_id=existant.id, nom=existant.nom)


async def copie_existante(plan: Plan) -> DejaCopie | None:
    return await copie_deja_faite(plan.sens, plan.labo, plan.source, plan.racine.id, plan.cible)


async def construire_le_releve(sens: str, workflow_id: int, source: int, cible: int) -> Releve:
    plan = await charger_le_plan(sens, workflow_id, source, cible)
    nb_tests = 0
    for agent in plan.agents:
        nb_tests += len(await stockage_tests.lister(source, agent.id))
    dossiers = []
    if sens == RAMENER:
        dossiers = [DossierPropose(id=d.id, nom=d.name) for d in await db_client.list_folders(cible)]
    return Releve(
        sens=sens, source_organization_id=source, cible_organization_id=cible, agent_id=plan.racine.id,
        agent_nom=plan.racine.nom, elements=plan.elements, nb_tests=nb_tests, deja_copie=await copie_existante(plan),
        dossiers=dossiers,
    )
