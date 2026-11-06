"""[.mark] Builder : les actions de la fiche client, du document de conception, du contexte et des réglages de l'agent.

* fiche (pivot) : lire ; écrire des lignes SOURCÉES et des trous (le builder ne valide pas) ;
* conception (B36) : lire ; écrire (état « proposé » : l'approbation est un geste humain) ;
* contexte de l'agent (couche 2) ;
* B33 : catalogue des motifs, phrases du code (jamais de nouveau motif), réglages .mark en général, modèles de réglages ;
* B41 : lexique et mots-clés de la reconnaissance vocale depuis la fiche validée.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.services.builder import conception, contexte as contexte_agent, fiche as service_fiche, reglages_agent
from api.services.builder.actions._commun import agent_verifie
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer
from api.services.builder.dossiers import classement, depot


class _Agent(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent; defaults to the conversation's agent.")


# --- fiche -------------------------------------------------------------------------------------------------------


async def _fiche_lire(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    fiche = await service_fiche.lire(contexte.organisation_id, identifiant)
    return {
        "ok": True,
        "fiche": fiche.model_dump(mode="json"),
        "validee": fiche.validee,
        "classements": {n: classement.classement_effectif(n, c.classement, c.valeur) for n, c in fiche.champs.items()},
    }


class _FicheEcrire(BaseModel):
    workflow_id: int | None = None
    champs: dict[str, service_fiche.ChampFiche] = Field(
        default_factory=dict, description="Lines of the sheet: name -> {valeur, source}. A line without a source is refused."
    )
    trous: list[service_fiche.Trou] = Field(default_factory=list, description="Open questions, with a suggested answer if any.")


async def _fiche_ecrire(contexte: Contexte, parametres: _FicheEcrire) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    if not parametres.champs and not parametres.trous:
        raise ErreurAction("Give lines (with their source) or gaps.")
    # Lot 3 : dès que des dossiers sont déposés, une ligne cite l'un d'eux (ou la réponse d'une personne), pas une source inventée.
    depots = await depot.lister(contexte.organisation_id, identifiant)
    if depots:
        for nom, champ in parametres.champs.items():
            if not depot.source_deposee(depots, champ.source):
                raise ErreurAction(
                    f"The source of « {nom} » ({champ.source[:80]!r}) is not a deposited document: cite one of the sources "
                    "given by fiche_tirer_des_documents, or write a gap instead.",
                    "source_inconnue",
                )
    try:
        fiche = await service_fiche.ecrire(contexte.organisation_id, identifiant, parametres.champs, parametres.trous)
    except service_fiche.ErreurFiche as erreur:
        raise ErreurAction(str(erreur)) from None
    return {
        "ok": True,
        "lignes": len(fiche.champs),
        "trous_ouverts": [t.champ for t in fiche.trous],
        "validee": fiche.validee,
        "carte": {
            "type": "fiche",
            "lignes": len(fiche.champs),
            "trous": len(fiche.trous),
            "validee": fiche.validee,
            "classements": {n: classement.classement_effectif(n, c.classement, c.valeur) for n, c in fiche.champs.items()},
        },
        "message": "A person validates the sheet; until then, nothing is built from an unvalidated line.",
    }


# --- conception --------------------------------------------------------------------------------------------------


async def _conception_lire(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    return {"ok": True, "conception": conception.resume(await conception.lire(contexte.organisation_id, identifiant))}


class _ConceptionEcrire(conception.Conception):
    workflow_id: int | None = None


async def _conception_ecrire(contexte: Contexte, parametres: _ConceptionEcrire) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    donnees = parametres.model_dump(exclude={"workflow_id"})
    etat = await conception.ecrire(contexte.organisation_id, identifiant, conception.Conception.model_validate(donnees))
    return {
        "ok": True,
        "revision": etat.revision,
        "etat": etat.etat,
        "carte": {"type": "conception", "revision": etat.revision, "conception": etat.conception.model_dump(mode="json")},
        "message": "Waiting for a person to approve it or send it back with a note. Do not build before.",
    }


# --- contexte de l'agent -----------------------------------------------------------------------------------------


class _Notes(BaseModel):
    workflow_id: int | None = None
    notes: str = Field(max_length=20000, description="What is specific to this agent and its decisions.")


async def _contexte_lire(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    return {"ok": True, **await contexte_agent.lire_contexte_agent(contexte.organisation_id, identifiant)}


async def _contexte_ecrire(contexte: Contexte, parametres: _Notes) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    await contexte_agent.ecrire_notes(contexte.organisation_id, identifiant, parametres.notes)
    return {"ok": True}


# --- réglages ----------------------------------------------------------------------------------------------------


class _Rien(BaseModel):
    pass


async def _phrases_catalogue(contexte: Contexte, parametres: _Rien) -> dict[str, Any]:
    return {"ok": True, **reglages_agent.catalogue_des_motifs()}


class _PhrasesRegler(BaseModel):
    workflow_id: int | None = None
    regles: list[dict[str, Any]] | None = Field(
        default=None,
        description="Rules {motif, portee: groupe|agent|etape, variantes, ...}. The reason MUST be in the catalogue (phrases_catalogue).",
    )
    depuis: str | None = Field(default=None, description="Slug of a 'phrases-du-code' library element to apply instead of rules.")


async def _phrases_regler(contexte: Contexte, parametres: _PhrasesRegler) -> dict[str, Any]:
    if bool(parametres.regles) == bool(parametres.depuis):
        raise ErreurAction("Give either rules or a library element (depuis), not both and not none.")
    if parametres.depuis:
        from api.services.builder.actions.bibliotheque import appliquer_un_element

        return await appliquer_un_element(contexte, "phrases-du-code", parametres.depuis, parametres.workflow_id)
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        return {"ok": True, **await reglages_agent.regler_phrases(contexte.organisation_id, identifiant, parametres.regles or [])}
    except reglages_agent.ErreurReglage as erreur:
        raise ErreurAction(str(erreur), "reglage") from None


class _ReglagesLire(BaseModel):
    workflow_id: int | None = None
    cles: list[str] | None = Field(default=None, description="Setting names; empty returns all the .mark settings.")


async def _reglages_lire(contexte: Contexte, parametres: _ReglagesLire) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        return {"ok": True, "reglages": await reglages_agent.lire_reglages(contexte.organisation_id, identifiant, parametres.cles)}
    except reglages_agent.ErreurReglage as erreur:
        raise ErreurAction(str(erreur), "reglage") from None


class _ReglagesRegler(BaseModel):
    workflow_id: int | None = None
    valeurs: dict[str, Any] = Field(description="Setting name -> value (sheet, modules, scribe, transfers, turn-taking...). Written in the DRAFT.")


async def _reglages_regler(contexte: Contexte, parametres: _ReglagesRegler) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        return {"ok": True, **await reglages_agent.regler(contexte.organisation_id, identifiant, parametres.valeurs)}
    except reglages_agent.ErreurReglage as erreur:
        raise ErreurAction(str(erreur), "reglage") from None


async def _lexique_remplir(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        return {"ok": True, **await reglages_agent.remplir_le_lexique(contexte.organisation_id, identifiant)}
    except reglages_agent.ErreurReglage as erreur:
        raise ErreurAction(str(erreur), "reglage") from None


async def _modeles_lister(contexte: Contexte, parametres: _Rien) -> dict[str, Any]:
    from api.services.modeles_reglages import service as modeles

    stock = await modeles.lire_le_stock(contexte.organisation_id)
    return {"ok": True, "modeles": [{"id": m.id, "nom": m.nom, "sections": m.sections} for m in stock.modeles]}


class _ModeleAppliquer(BaseModel):
    workflow_id: int | None = None
    modele_id: str
    sections: list[str] = Field(min_length=1)
    a_blanc: bool = Field(default=True, description="True: only show what would change.")


async def _modele_appliquer(contexte: Contexte, parametres: _ModeleAppliquer) -> dict[str, Any]:
    from api.services.modeles_reglages import service as modeles

    identifiant = await agent_verifie(contexte, parametres.workflow_id)

    def verifier(configurations: dict) -> None:
        try:
            reglages_agent._verifier(configurations)
        except reglages_agent.ErreurReglage as erreur:
            raise modeles.ModeleRefuse(str(erreur)) from None

    try:
        resultat = await modeles.appliquer_un_modele(
            contexte.organisation_id,
            parametres.modele_id,
            identifiant,
            parametres.sections,
            a_blanc=parametres.a_blanc,
            verifier=verifier,
        )
    except modeles.ModeleRefuse as erreur:
        raise ErreurAction(erreur.message, "modele") from None
    return {"ok": True, **resultat.model_dump(mode="json")}


for _nom, _description, _parametres, _fonction, _ecriture, _groupe in (
    ("fiche_lire", "Read the client sheet (lines with their sources, open gaps, validation).", _Agent, _fiche_lire, False, "fiche"),
    (
        "fiche_ecrire",
        "Write lines of the client sheet, each with its source (document, page), and open gaps as questions. You never validate it.",
        _FicheEcrire,
        _fiche_ecrire,
        True,
        "fiche",
    ),
    ("conception_lire", "Read the design document and its state (proposed, approved, sent back).", _Agent, _conception_lire, False, "conception"),
    (
        "conception_ecrire",
        "Write the design document (goal and success, hypotheses to confirm, data and what to do if absent, tools and their answers including 'system unavailable', example calls). A person approves it before anything is built.",
        _ConceptionEcrire,
        _conception_ecrire,
        True,
        "conception",
    ),
    ("contexte_lire", "Read the agent's context (notes, candidates it uses).", _Agent, _contexte_lire, False, "contexte"),
    ("contexte_ecrire", "Write the agent's context notes (what is specific to this agent).", _Notes, _contexte_ecrire, True, "contexte"),
    ("phrases_catalogue", "Read the catalogue of reasons the code speaks for (never add one: it is code).", _Rien, _phrases_catalogue, False, "reglages"),
    (
        "phrases_regler",
        "Set the sentences the code says (three levels: group, agent, step), from rules or from a library element. Only reasons of the catalogue.",
        _PhrasesRegler,
        _phrases_regler,
        True,
        "reglages",
    ),
    ("reglages_lire", "Read the .mark settings of an agent.", _ReglagesLire, _reglages_lire, False, "reglages"),
    (
        "reglages_regler",
        "Write .mark settings of an agent in its DRAFT (sheet, modules, scribe, transfers...). Validated as the screen's save is.",
        _ReglagesRegler,
        _reglages_regler,
        True,
        "reglages",
    ),
    (
        "lexique_remplir_depuis_fiche",
        "Fill the speech-recognition vocabulary (words to listen for) from the 'lexique' line of the VALIDATED sheet.",
        _Agent,
        _lexique_remplir,
        True,
        "reglages",
    ),
    ("modeles_reglages_lister", "List the settings templates of the organization.", _Rien, _modeles_lister, False, "reglages"),
    (
        "modeles_reglages_appliquer",
        "Apply a settings template to the agent's draft (dry run by default).",
        _ModeleAppliquer,
        _modele_appliquer,
        True,
        "reglages",
    ),
):
    enregistrer(
        Action(nom=_nom, description=_description, parametres=_parametres, fonction=_fonction, ecriture=_ecriture, groupe=_groupe)
    )
