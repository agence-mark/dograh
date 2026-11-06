"""[.mark] Builder, lot 3 : les actions du contexte client (dossiers déposés, fiche sourcée, faits classés, base de connaissances).

* ``fiche_tirer_des_documents`` : REMPLIT le point d'entrée posé au lot 1 (même nom, même registre, le moteur n'a pas
  bougé). Il lit les dossiers déposés (le texte est extrait à la demande de la personne, sur place) et rend au cerveau
  les pages AVEC leur source ; le cerveau écrit les lignes avec ``fiche_ecrire``, chacune citant l'une de ces sources.
  Un document illisible est signalé, jamais inventé ; ce qui manque devient une question (``champs_sans_ligne``) ;
* ``depot_ajouter_site`` : lit un site (pages publiques seulement, voir ``dossiers/site.py``) ;
* ``fiche_creer_les_objets`` (B48) : les faits de la fiche VALIDÉE classés « objet » deviennent des objets de l'agent ;
* ``base_lister`` · ``base_proposer`` · ``base_rattacher`` (B27) : la base de connaissances. Le builder propose, une
  personne valide (``routes/builder_contexte.py``), seul un document validé est rattaché au brouillon.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from pydantic import BaseModel, Field

from api.services.builder import brouillon
from api.services.builder import fiche as service_fiche
from api.services.builder.actions import construction, objets
from api.services.builder.actions._commun import agent_de_l_organisation, agent_verifie
from api.services.builder.actions.points_d_entree import _Documents
from api.services.builder.actions.registre import (
    REGISTRE,
    Action,
    Contexte,
    ErreurAction,
    enregistrer,
)
from api.services.builder.bibliotheque import droits
from api.services.builder.dossiers import base, classement, depot
from api.services.builder.dossiers.base import ErreurBase

BUDGET_CARACTERES = 24_000

CONSIGNE_DE_LECTURE = (
    "Write the sheet lines with fiche_ecrire. Each line cites EXACTLY one 'source' label given below (or a person's "
    "answer). Put a fact you did not find in 'trous' as a question, with a suggested answer ONLY if the documents hold "
    "it; never fill a gap by guessing. Classify each fact (classement): objet (small, critical, the client will edit it), "
    "base (large, rarely asked), regle (conduct rule). Tell the person about unreadable documents."
)


class _Tirer(_Documents):
    a_partir_de: int = Field(default=0, ge=0, description="Continue after this many pages (use 'suite' of the previous answer).")


async def _tirer(contexte: Contexte, parametres: _Tirer) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    org = contexte.organisation_id
    depots = await depot.lister(org, identifiant)
    if parametres.documents:
        voulus = set(parametres.documents)
        inconnus = sorted(voulus - {d["id"] for d in depots})
        if inconnus:
            raise ErreurAction(f"Unknown deposit(s): {', '.join(inconnus)}. Read the card of deposits first.", "introuvable")
        depots = [d for d in depots if d["id"] in voulus]
    fiche = await service_fiche.lire(org, identifiant)
    illisibles = [{"id": d["id"], "nom": d["nom"], "raison": d.get("raison", "")} for d in depots if d.get("statut") == "illisible"]
    extraits: list[dict[str, Any]] = []
    vus = 0
    utilise = 0
    suite: int | None = None
    for dep in depots:
        if dep.get("statut") != "lu":
            continue
        for page in await depot.pages_de(org, dep):
            vus += 1
            if vus <= parametres.a_partir_de:
                continue
            if utilise and utilise + len(page.texte) > BUDGET_CARACTERES:
                suite = vus - 1
                break
            utilise += len(page.texte)
            extraits.append(
                {"depot": dep["id"], "source": depot.etiquette_de_source(dep, page), "document": dep["nom"], "page": page.numero, "texte": page.texte}
            )
        if suite is not None:
            break
    attendus = sorted(classement.PAR_DEFAUT)
    sans_ligne = [c for c in attendus if c not in fiche.champs and not any(t.champ == c for t in fiche.trous)]
    return {
        "ok": True,
        "documents": [depot.vue(d) for d in depots],
        "illisibles": illisibles,
        "extraits": extraits,
        "suite": {"a_partir_de": suite} if suite is not None else None,
        "champs_standard_sans_ligne": sans_ligne,
        "classement_par_defaut": {c: classement.PAR_DEFAUT[c] for c in attendus},
        "lignes_deja_ecrites": sorted(fiche.champs),
        "consigne": CONSIGNE_DE_LECTURE,
        "carte": {"type": "depot", "documents": [depot.vue(d) for d in depots], "illisibles": illisibles},
    }


class _Site(BaseModel):
    workflow_id: int | None = None
    adresse: str = Field(min_length=3, max_length=2000, description="Address of the client's public site.")


async def _ajouter_un_site(contexte: Contexte, parametres: _Site) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        ajoute = await depot.deposer_site(contexte.organisation_id, identifiant, parametres.adresse, droits.nom_de_l_auteur(contexte.user))
    except depot.ErreurDepot as erreur:
        raise ErreurAction(str(erreur), "depot") from None
    return {"ok": ajoute.get("statut") == "lu", "depot": ajoute, "carte": {"type": "depot", "documents": await _vues(contexte, identifiant)}}


async def _vues(contexte: Contexte, identifiant: int) -> list[dict[str, Any]]:
    return [depot.vue(d) for d in await depot.lister(contexte.organisation_id, identifiant)]


# --- B48 : les faits classés « objet » deviennent des objets de l'agent -------------------------------------------------


class _Agent(BaseModel):
    workflow_id: int | None = None


async def _creer_les_objets(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    fiche = await service_fiche.lire(contexte.organisation_id, identifiant)
    if not fiche.validee:
        raise ErreurAction("The sheet is not validated by a person: no object is created from it yet.", "fiche_non_validee")
    retenus, autres = [], {"base": [], "regle": []}
    for nom, champ in fiche.champs.items():
        place = classement.classement_effectif(nom, champ.classement, champ.valeur)
        if place == "objet":
            retenus.append(objets.ObjetEnvoye.model_validate(classement.en_objet(nom, champ.valeur)))
        else:
            autres[place].append(nom)
    if not retenus:
        return {"ok": True, "objets": [], "ailleurs": autres, "message": "No fact of the sheet is classed as an object."}
    resultats = await objets.ecrire_des_objets(contexte, retenus)
    return {
        "ok": all(r["ok"] for r in resultats),
        "objets": resultats,
        "ailleurs": autres,
        "carte": {"type": "objets", "objets": resultats},
        "message": "Put each object in the « what you know » part of the prompt with its {{name}}, never the fact itself.",
    }


# --- B27 : la base de connaissances ---------------------------------------------------------------------------------------


async def _base_lister(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    documents = await base.lister(contexte.organisation_id, identifiant)
    return {"ok": True, "documents": [d.model_dump(mode="json") for d in documents]}


class _BaseProposer(BaseModel):
    workflow_id: int | None = None
    titre: str = Field(min_length=1, max_length=200)
    contenu: str = Field(min_length=1, max_length=base.CONTENU_MAX, description="The document the agent will consult to answer.")
    sources: list[base.SourceCitee] = Field(
        min_length=1,
        max_length=20,
        description="Passages copied WORD FOR WORD from the deposited documents that hold what the content says.",
    )


async def _base_proposer(contexte: Contexte, parametres: _BaseProposer) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        proposition = await base.proposer(
            contexte.organisation_id,
            identifiant,
            parametres.titre,
            parametres.contenu,
            parametres.sources,
            f"builder pour {droits.nom_de_l_auteur(contexte.user)}",
        )
    except ErreurBase as erreur:
        raise ErreurAction(str(erreur), erreur.code) from None
    return {
        "ok": True,
        "id": proposition.id,
        "etat": proposition.etat,
        "carte": {"type": "base", "documents": [d.model_dump(mode="json") for d in await base.lister(contexte.organisation_id, identifiant)]},
        "message": "Proposed. A person validates it; only then it enters the knowledge base. Never announce it as done before.",
    }


class _BaseRattacher(BaseModel):
    workflow_id: int | None = None
    proposition: str = Field(min_length=1, description="Identifier of a VALIDATED proposal (base_lister).")
    noeud: str = Field(min_length=1, description="Identifier of the node of the draft that will consult the document.")


async def _base_rattacher(contexte: Contexte, parametres: _BaseRattacher) -> dict[str, Any]:
    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    try:
        document = await base.pour_rattacher(contexte.organisation_id, workflow.id, parametres.proposition)
    except ErreurBase as erreur:
        raise ErreurAction(str(erreur), erreur.code) from None
    etat = await brouillon.lire_en_attente(contexte.organisation_id, workflow.id)
    graphe, _version = await brouillon.source_courante(workflow)
    try:
        courant = brouillon.appliquer(graphe, brouillon.operations_de(etat))
        noeud = brouillon._noeud(courant, parametres.noeud)
    except brouillon.ErreurOperation as erreur:
        raise ErreurAction(str(erreur), "operation") from None
    deja = list((noeud.get("data") or {}).get("document_uuids") or [])
    if document.document_uuid not in deja:
        deja.append(document.document_uuid)
    resultat = await construction._operer(
        contexte,
        construction._Operations(
            workflow_id=workflow.id,
            operations=[brouillon.Operation(op="modifier_noeud", id=parametres.noeud, donnees={"document_uuids": deja})],
        ),
    )
    if resultat.get("ok"):
        await base.noter_le_rattachement(contexte.organisation_id, workflow.id, parametres.proposition, parametres.noeud)
    return {**resultat, "rattache": document.titre}


# --- l'inscription -----------------------------------------------------------------------------------------------------


def _remplir_le_point_d_entree() -> None:
    """Le point d'entrée du lot 1 devient disponible : seul ``fonction`` (et son schéma) change, pas le moteur."""
    ancien = REGISTRE["fiche_tirer_des_documents"]
    REGISTRE["fiche_tirer_des_documents"] = dataclasses.replace(
        ancien,
        description=(
            "Read the deposited documents (files and site pages) and give their pages with the source of each. Then write the "
            "sheet lines with fiche_ecrire, citing these sources; a missing fact is a question, never a guess. Unreadable "
            "documents are reported."
        ),
        parametres=_Tirer,
        fonction=_tirer,
        ecriture=False,
        disponible=True,
        groupe="fiche",
        extras={},
    )


_remplir_le_point_d_entree()

for _nom, _description, _parametres, _fonction, _ecriture, _groupe in (
    (
        "depot_ajouter_site",
        "Read the client's public site (public pages only, at most 10) and deposit it as a document with a source per page.",
        _Site,
        _ajouter_un_site,
        True,
        "fiche",
    ),
    (
        "fiche_creer_les_objets",
        "From the VALIDATED sheet, create as objects of the agent the facts classed 'objet' (small, critical, edited by the client). Never writes them in a prompt.",
        _Agent,
        _creer_les_objets,
        True,
        "fiche",
    ),
    ("base_lister", "List the knowledge base documents proposed for this agent with their state.", _Agent, _base_lister, False, "base"),
    (
        "base_proposer",
        "Propose a knowledge base document (large, rarely asked: FAQ, catalogue, conditions) drawn from the deposits. Every passage cited must be word for word in the deposit, and no number or commitment may be absent from them. A person validates it.",
        _BaseProposer,
        _base_proposer,
        True,
        "base",
    ),
    (
        "base_rattacher",
        "Attach a document VALIDATED by a person to a node of the draft, through the existing knowledge base. Refused for a proposal not validated.",
        _BaseRattacher,
        _base_rattacher,
        True,
        "base",
    ),
):
    enregistrer(
        Action(nom=_nom, description=_description, parametres=_parametres, fonction=_fonction, ecriture=_ecriture, groupe=_groupe)
    )
