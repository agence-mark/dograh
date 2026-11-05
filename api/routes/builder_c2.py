"""[.mark] Builder partie 2, U5 (lot C2) : la revue des changements, les versions restaurables, l'accord de dépense, les sous-agents,
la visionneuse de fichiers.

- ``GET  /builder/fils/{id}/changements``                       les changements en attente, un par champ ;
- ``POST /builder/fils/{id}/changements/accepter`` · ``refuser``  (``rangs`` vide = tous) ;
- ``GET  /builder/agents/{id}/versions``                         les versions de brouillon restaurables ;
- ``POST /builder/agents/{id}/versions/{n}/restaurer``;
- ``POST /builder/fils/{id}/depenses/{depense}``                 l'accord (ou le refus) d'une dépense annoncée ;
- ``PUT  /builder/fils/{id}/mode``                               le mode du chat (N1 : demander, agent, tout, plan) ;
- ``POST /builder/fils/{id}/autorisations/{demande}``            la réponse à une carte d'autorisation (une fois, pour ce chat, refuser) ;
- ``DELETE /builder/fils/{id}/autorisations/{demande}``          retirer une autorisation « pour ce chat » ;
- ``GET  /builder/fils/{id}/sous-agents`` · ``PUT .../sous-agents/interrupteur`` · ``POST .../sous-agents/arreter``;
- ``GET|PUT /builder/sous-agents/reglages``                      Labo › Builder IA › Sous-agents ;
- ``GET  /builder/fichiers/{uuid}/texte``                        le texte extrait d'un fichier de la base de connaissances (visionneuse).

Tout est lu et écrit AVEC l'organisation de l'utilisateur (R0).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import fil as service_fil
from api.services.builder import modes, revue, sous_agents

router = APIRouter(tags=["builder"])

PAGE_CARACTERES = 4000
PAGE_LIGNES = 200


async def _fil_ou_404(user: UserModel, fil_id: int):
    fil = await db_client.lire_fil(user.selected_organization_id, fil_id)
    if fil is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return fil


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Agent not found")
    return workflow


async def _agent_du_fil(user: UserModel, fil):
    if fil.workflow_id is None:
        raise HTTPException(status_code=409, detail="This conversation has no agent yet.")
    return await _agent_ou_404(user, fil.workflow_id)


# --- la revue des changements ----------------------------------------------------------------------------------------------


@router.get("/fils/{fil_id}/changements")
async def lire_les_changements(fil_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    workflow = await _agent_du_fil(user, await _fil_ou_404(user, fil_id))
    return await revue.lister(user.selected_organization_id, workflow)


class Rangs(BaseModel):
    rangs: list[int] = Field(default_factory=list, max_length=500, description="Vide : tous les changements en attente.")


async def _decider(fil_id: int, demande: Rangs, user: UserModel, accepter: bool) -> dict[str, Any]:
    fil = await _fil_ou_404(user, fil_id)
    if fil.genre == "sous_agent":
        raise HTTPException(status_code=409, detail="A sub-agent never writes.")
    workflow = await _agent_du_fil(user, fil)
    org = user.selected_organization_id
    try:
        if accepter:
            rendu = await revue.accepter(org, workflow, demande.rangs, fil.id)
        else:
            rendu = await revue.refuser(org, workflow, demande.rangs)
    except revue.ErreurRevue as erreur:
        raise HTTPException(status_code=409, detail=str(erreur)) from None
    restants = (await revue.lister(org, workflow))["total"]
    await db_client.modifier_fil(org, fil.id, changements=restants)
    await service_fil.noter(fil.id, {"type": "revue", "decision": "acceptation" if accepter else "refus", "restants": restants, **rendu})
    return {**rendu, "restants": restants}


@router.post("/fils/{fil_id}/changements/accepter")
async def accepter_les_changements(fil_id: int, demande: Rangs, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _decider(fil_id, demande, user, True)


@router.post("/fils/{fil_id}/changements/refuser")
async def refuser_les_changements(fil_id: int, demande: Rangs, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _decider(fil_id, demande, user, False)


class VueVersion(BaseModel):
    numero: int
    cause: str
    date: str
    fil_id: int | None
    version_avant: int | None
    version_apres: int | None
    operations: list[dict[str, Any]]
    # Sous-lot 7 : les familles que cette version sait restaurer (schema, phrases, reglages, vocabulaire, objets).
    familles: list[str] = Field(default_factory=lambda: ["schema"])


class Restauration(BaseModel):
    """Les familles à remettre ; absent ou ``null`` = toutes celles que la version a gardées."""

    familles: list[str] | None = Field(default=None, max_length=5)


@router.get("/agents/{workflow_id}/versions", response_model=list[VueVersion])
async def lister_les_versions(
    workflow_id: int, fil_id: int | None = Query(default=None), user: UserModel = Depends(get_user_with_selected_organization)
):
    await _agent_ou_404(user, workflow_id)
    return await revue.instantanes(user.selected_organization_id, workflow_id, fil_id)


@router.post("/agents/{workflow_id}/versions/{numero}/restaurer")
async def restaurer_une_version(
    workflow_id: int,
    numero: int,
    corps: Restauration | None = None,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    workflow = await _agent_ou_404(user, workflow_id)
    familles = corps.familles if corps is not None else None
    try:
        rendu = await revue.restaurer(user.selected_organization_id, workflow, numero, familles=familles, user=user)
    except revue.ErreurRevue as erreur:
        inconnue = str(erreur).startswith("Unknown version")
        raise HTTPException(status_code=404 if inconnue else 422, detail=str(erreur)) from None
    # Une action sensible est journalisée : qui, quoi (l'agent, la version, les familles), quand, où.
    from api.services.equipe_mark.acces import journaliser

    await journaliser(user, "agents.revenir_avant", user.selected_organization_id, {"agent": workflow_id, "instantane": numero, "familles": rendu["familles"]})
    return rendu


# --- l'accord de dépense ---------------------------------------------------------------------------------------------------


class Accord(BaseModel):
    accord: bool


@router.post("/fils/{fil_id}/depenses/{depense_id}")
async def repondre_a_une_depense(
    fil_id: int, depense_id: str, demande: Accord, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Enregistre l'accord (ou le refus), puis rend la main au builder avec un message : il reprend, ou cherche une autre voie."""
    from api.routes import builder as routes_builder

    fil = await _fil_ou_404(user, fil_id)
    if fil.genre == "sous_agent":
        raise HTTPException(status_code=409, detail="A sub-agent receives no message.")
    if service_fil.en_cours(fil.id):
        raise HTTPException(status_code=409, detail="The builder is still working: wait for it to stop.")
    historique = dict(fil.historique or {})
    depenses = {k: dict(v) for k, v in (historique.get("depenses") or {}).items()}
    depense = depenses.get(depense_id)
    if depense is None:
        raise HTTPException(status_code=404, detail="Unknown cost")
    if depense.get("statut") != "attente":
        raise HTTPException(status_code=409, detail="This cost was already answered.")
    depense["statut"] = "accordee" if demande.accord else "refusee"
    depenses[depense_id] = depense
    historique["depenses"] = depenses
    await db_client.modifier_fil(user.selected_organization_id, fil.id, historique=historique)
    fil.historique = historique
    await service_fil.noter(fil.id, {"type": "depense_reponse", "id": depense_id, "statut": depense["statut"]})
    cerveau, reglages = await routes_builder._cerveau_de(user)
    message = (
        f"Agreed: you may spend for « {depense['motif']} » (up to ${depense['montant_estime']:.2f}). Go ahead."
        if demande.accord
        else f"Refused: do not spend for « {depense['motif']} ». Find a way that costs nothing, or tell me what you cannot check."
    )
    try:
        await service_fil.lancer(user, fil, message, cerveau, reglages)
    except service_fil.ErreurFil as erreur:
        raise HTTPException(status_code=erreur.statut, detail=str(erreur)) from None
    return {"ok": True, "statut": depense["statut"]}


# --- N1 : le mode du chat et les cartes d'autorisation ------------------------------------------------------------------------------


class ModeDemande(BaseModel):
    mode: Literal["demander", "agent", "tout", "plan"]


class ReponseAutorisation(BaseModel):
    decision: Literal["une_fois", "pour_ce_chat", "refuser"]
    raison: str | None = Field(default=None, max_length=500, description="Why it is refused (optional): the builder reads it.")


def _chat_modifiable(fil) -> None:
    if fil.genre in ("sous_agent", "claude_code"):
        raise HTTPException(status_code=409, detail="This conversation has no permission mode.")
    if service_fil.en_cours(fil.id):
        raise HTTPException(status_code=409, detail="The builder is still working: wait for it to stop.")


@router.put("/fils/{fil_id}/mode")
async def regler_le_mode(fil_id: int, demande: ModeDemande, user: UserModel = Depends(get_user_with_selected_organization)):
    """Le mode vaut pour CE chat (un nouveau chat repart sur « demander »). Il ne donne jamais plus que le rôle de la personne : chaque
    action reste vérifiée côté serveur (``modes.decider``). « Tout permettre » est journalisé (qui, quel chat, quand)."""
    fil = await _fil_ou_404(user, fil_id)
    _chat_modifiable(fil)
    await modes.poser(user, fil, demande.mode)
    return {"ok": True, "mode": demande.mode}


def _demande_ou_erreur(historique: dict[str, Any], demande_id: str) -> dict[str, Any]:
    demandes = {k: dict(v) for k, v in (historique.get("autorisations") or {}).items()}
    historique["autorisations"] = demandes
    demande = demandes.get(demande_id)
    if demande is None:
        raise HTTPException(status_code=404, detail="Unknown permission request")
    return demande


def _message_de_reponse(demande: dict[str, Any], decision: str, raison: str | None) -> str:
    nom = demande.get("nom")
    if decision == "une_fois":
        return f"Allowed once: call « {nom} » again with exactly the same arguments, then go on."
    if decision == "pour_ce_chat":
        return f"Allowed for this chat: « {nom} » on {demande.get('objet')}. Call it again, then go on."
    motif = f" Reason given by the person: {raison.strip()}" if raison and raison.strip() else ""
    return f"Refused: do not do « {nom} ». Find another way or tell the person what stays to do.{motif}"


@router.post("/fils/{fil_id}/autorisations/{demande_id}")
async def repondre_a_une_autorisation(
    fil_id: int, demande_id: str, reponse: ReponseAutorisation, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Enregistre la réponse de la personne à une carte, puis rend la main au builder : rien n'est exécuté sans ce clic, et c'est le
    builder qui rappelle l'action (la porte des modes la laisse passer d'après cette réponse)."""
    from api.routes import builder as routes_builder

    fil = await _fil_ou_404(user, fil_id)
    _chat_modifiable(fil)
    historique = dict(fil.historique or {})
    demande = _demande_ou_erreur(historique, demande_id)
    if demande.get("statut") != "attente":
        raise HTTPException(status_code=409, detail="This request was already answered.")
    demande["statut"] = "refusee" if reponse.decision == "refuser" else reponse.decision
    if reponse.decision == "refuser" and reponse.raison:
        demande["raison"] = reponse.raison.strip()[:500]
    historique["autorisations"][demande_id] = demande
    await db_client.modifier_fil(user.selected_organization_id, fil.id, historique=historique)
    fil.historique = historique
    await service_fil.noter(fil.id, {"type": "autorisation_reponse", "id": demande_id, "statut": demande["statut"]})
    if reponse.decision != "refuser":
        from api.services.equipe_mark.acces import journaliser

        await journaliser(
            user,
            "builder.autorisation",
            user.selected_organization_id,
            {"fil": fil.id, "action": demande.get("nom"), "famille": demande.get("famille"), "objet": demande.get("objet"), "decision": reponse.decision},
        )
    cerveau, reglages = await routes_builder._cerveau_de(user)
    try:
        await service_fil.lancer(user, fil, _message_de_reponse(demande, reponse.decision, reponse.raison), cerveau, reglages)
    except service_fil.ErreurFil as erreur:
        raise HTTPException(status_code=erreur.statut, detail=str(erreur)) from None
    return {"ok": True, "statut": demande["statut"]}


@router.delete("/fils/{fil_id}/autorisations/{demande_id}")
async def retirer_une_autorisation(fil_id: int, demande_id: str, user: UserModel = Depends(get_user_with_selected_organization)):
    """Retire une autorisation « pour ce chat » : la prochaine action de ce type sur cet objet redemande."""
    fil = await _fil_ou_404(user, fil_id)
    _chat_modifiable(fil)
    historique = dict(fil.historique or {})
    demande = _demande_ou_erreur(historique, demande_id)
    if demande.get("statut") != "pour_ce_chat":
        raise HTTPException(status_code=409, detail="Only a permission for this chat can be withdrawn.")
    demande["statut"] = "retiree"
    historique["autorisations"][demande_id] = demande
    await db_client.modifier_fil(user.selected_organization_id, fil.id, historique=historique)
    await service_fil.noter(fil.id, {"type": "autorisation_reponse", "id": demande_id, "statut": "retiree"})
    return {"ok": True, "statut": "retiree"}


# --- les sous-agents -------------------------------------------------------------------------------------------------------


class VueSousAgent(BaseModel):
    id: int
    delegation: str | None
    titre: str
    usage: str | None
    etat: str
    modele: str | None
    tache: str | None
    jetons: int
    cout: float
    resume: str | None
    actions: int | None
    en_cours: bool


class VueSousAgents(BaseModel):
    actif: bool
    sous_agents: list[VueSousAgent]


@router.get("/fils/{fil_id}/sous-agents", response_model=VueSousAgents)
async def lister_les_sous_agents(fil_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    fil = await _fil_ou_404(user, fil_id)
    enfants = await db_client.lister_les_enfants(user.selected_organization_id, fil.id)
    return VueSousAgents(
        actif=bool(fil.sous_agents_actifs),
        sous_agents=[
            VueSousAgent(
                id=e.id, delegation=e.delegation_id, titre=e.titre, usage=e.usage, etat=e.etat, modele=e.modele, tache=e.tache,
                jetons=e.jetons or 0, cout=e.cout or 0.0, resume=(e.resultat or {}).get("resume"), actions=(e.resultat or {}).get("actions"),
                en_cours=service_fil.en_cours(e.id),
            )
            for e in enfants
        ],
    )


class Interrupteur(BaseModel):
    actif: bool


@router.put("/fils/{fil_id}/sous-agents/interrupteur", response_model=VueSousAgents)
async def regler_l_interrupteur(
    fil_id: int, demande: Interrupteur, user: UserModel = Depends(get_user_with_selected_organization)
):
    """« Sous-agents dans ce chat » : éteint, le builder ne délègue plus (ceux qui travaillent finissent). Gardé avec la conversation."""
    fil = await _fil_ou_404(user, fil_id)
    if fil.genre == "sous_agent":
        raise HTTPException(status_code=409, detail="Only the main conversation has this switch.")
    await db_client.modifier_fil(user.selected_organization_id, fil.id, sous_agents_actifs=demande.actif)
    return await lister_les_sous_agents(fil_id, user)


@router.post("/fils/{fil_id}/sous-agents/arreter", response_model=VueSousAgents)
async def arreter_tous_les_sous_agents(fil_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    fil = await _fil_ou_404(user, fil_id)
    org = user.selected_organization_id
    for enfant in await db_client.lister_les_enfants(org, fil.id):
        if service_fil.en_cours(enfant.id):
            await service_fil.arreter(org, enfant.id)
    return await lister_les_sous_agents(fil_id, user)


@router.get("/sous-agents/reglages", response_model=sous_agents.ReglagesSousAgents)
async def lire_les_reglages_des_sous_agents(user: UserModel = Depends(get_user_with_selected_organization)):
    return await sous_agents.lire_les_reglages(await sous_agents._organisation_des_reglages(user))


@router.put("/sous-agents/reglages", response_model=sous_agents.ReglagesSousAgents)
async def regler_les_sous_agents(
    demande: sous_agents.ReglagesSousAgents, user: UserModel = Depends(get_user_with_selected_organization)
):
    await sous_agents.ecrire_les_reglages(await sous_agents._organisation_des_reglages(user), demande)
    return demande


# --- la visionneuse de fichiers --------------------------------------------------------------------------------------------


class PageDeTexte(BaseModel):
    nom: str
    type_mime: str | None
    genre: str  # texte | pages | lignes
    page: int
    pages: int
    texte: str


def _decouper(nom: str, brut: str) -> tuple[str, list[str]]:
    """Un tableur se lit en lignes, un PDF page par page (saut de page du texte extrait), le reste par blocs de caractères."""
    bas = nom.lower()
    if bas.endswith((".csv", ".xls", ".xlsx", ".tsv")):
        lignes = brut.splitlines()
        return "lignes", ["\n".join(lignes[i : i + PAGE_LIGNES]) for i in range(0, max(len(lignes), 1), PAGE_LIGNES)]
    if "\f" in brut:
        return "pages", brut.split("\f")
    return "texte", [brut[i : i + PAGE_CARACTERES] for i in range(0, max(len(brut), 1), PAGE_CARACTERES)]


@router.get("/fichiers/{document_uuid}/texte", response_model=PageDeTexte)
async def lire_le_texte_d_un_fichier(
    document_uuid: str, page: int = Query(default=1, ge=1), user: UserModel = Depends(get_user_with_selected_organization)
):
    """Le texte extrait d'un fichier de la base de connaissances (le même que celui des connaissances). Lecture seule."""
    org = user.selected_organization_id
    document = await db_client.get_document_by_uuid(document_uuid=document_uuid, organization_id=org)
    if document is None:
        raise HTTPException(status_code=404, detail="File not found")
    brut = document.full_text
    if not brut:
        morceaux = await db_client.get_chunks_for_document(document.id, org)
        brut = "\n\n".join(m.chunk_text for m in morceaux)
    genre, pages = _decouper(document.filename, brut or "")
    if page > len(pages):
        raise HTTPException(status_code=404, detail="Page not found")
    return PageDeTexte(nom=document.filename, type_mime=document.mime_type, genre=genre, page=page, pages=len(pages), texte=pages[page - 1])
