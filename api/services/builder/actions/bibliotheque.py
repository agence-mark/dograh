"""[.mark] Builder : les actions de la bibliothèque (lecture, application par famille, candidats, propositions).

Le builder LIT tout, applique, crée ou modifie des **candidats** (B35) et **propose** (B9). Il ne passe rien en
Recette, ne rejette pas, n'accepte pas de proposition, ne revient pas en arrière : ces gestes sont humains
(``routes/builder_bibliotheque.py``). Ce qu'il écrit demande d'être de l'équipe .mark (``droits``).

Une action par FAMILLE d'application (``familles.py``, mode ``applique``) : phrases du code, modèles de
réglages, lexiques écrivent dans l'agent ; les autres rendent le contenu pour que le builder l'écrive avec les
actions de construction. Toute application note l'usage (« utilisée par N agents ») et, si l'élément est un
candidat, la mention « contient des candidats » de l'agent.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from api.services.builder import contexte as contexte_agent
from api.services.builder import reglages_agent
from api.services.builder.actions._commun import agent_verifie
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer
from api.services.builder.bibliotheque import droits, familles_libres, fiches, propositions, rangement, service
from api.services.builder.bibliotheque.familles import MODE_APPLIQUE
from api.services.builder.bibliotheque.modele import Banc, Statut
from api.services.builder.bibliotheque.service import ErreurBibliotheque


def _auteur_builder(contexte: Contexte) -> str:
    return f"builder pour {droits.nom_de_l_auteur(contexte.user)}"


def _refus(erreur: ErreurBibliotheque) -> ErreurAction:
    return ErreurAction(str(erreur), f"bibliotheque_{erreur.statut}")


class _Lister(BaseModel):
    famille: str | None = Field(default=None, description="A family slug; empty lists the families.")
    statut: Literal["candidat", "recette", "rejete"] | None = None


async def _lister(contexte: Contexte, parametres: _Lister) -> dict[str, Any]:
    if parametres.famille is None:
        les_fiches = await fiches.toutes()
        return {
            "ok": True,
            "familles": [
                {
                    "slug": f.slug,
                    "libelle": f.libelle,
                    "groupe": f.groupe,
                    "cible": f.cible,
                    "mode": f.mode,
                    "fiche": les_fiches.get(f.slug, fiches.Fiche()).model_dump(),
                }
                for f in (await familles_libres.toutes()).values()
            ],
            "etiquettes": [e["nom"] for e in await rangement.etiquettes()],
        }
    try:
        elements = await service.lister(parametres.famille, Statut(parametres.statut) if parametres.statut else None)
        sous_dossiers = await rangement.dossiers_de(parametres.famille)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return {
        "ok": True,
        "fiche": (await fiches.lire(parametres.famille)).model_dump(),
        "dossiers": sous_dossiers,
        "elements": [e.model_dump(mode="json") for e in elements],
    }


class _Chercher(BaseModel):
    recherche: str = Field(default="", max_length=200, description="Words searched in titles, labels and content of the whole library.")
    famille: str | None = None
    statut: Literal["candidat", "recette", "rejete"] | None = None
    dossier: str | None = Field(default=None, description="A sub-folder of the family (its descendants are included).")
    etiquettes: list[str] = Field(default_factory=list, description="Labels the element must all carry.")
    decalage: int = Field(default=0, ge=0)


async def _chercher(contexte: Contexte, parametres: _Chercher) -> dict[str, Any]:
    try:
        total, page = await service.parcourir(
            parametres.famille,
            Statut(parametres.statut) if parametres.statut else None,
            dossier=parametres.dossier,
            etiquettes=parametres.etiquettes,
            recherche=parametres.recherche,
            limite=25,
            decalage=parametres.decalage,
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return {"ok": True, "total": total, "elements": [e.model_dump(mode="json") for e in page]}


class _Ranger(BaseModel):
    famille: str
    slug: str
    dossier: str | None = Field(default=None, description="The sub-folder of the family; empty takes it out of its folder.")
    etiquettes: list[str] | None = Field(default=None, max_length=12, description="The labels of the element (unknown ones are created).")


async def _ranger(contexte: Contexte, parametres: _Ranger) -> dict[str, Any]:
    try:
        await droits.exiger_l_equipe(contexte.user)
        element = await rangement.ranger(
            parametres.famille, parametres.slug, dossier=parametres.dossier, etiquettes_posees=parametres.etiquettes
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return {"ok": True, "dossier": element.dossier, "etiquettes": element.etiquettes}


class _Lire(BaseModel):
    famille: str
    slug: str


def _avertissement(statut: Statut) -> str | None:
    if statut is Statut.CANDIDAT:
        return "Candidate: not proven on a bench. Say so to the person."
    if statut is Statut.REJETE:
        return "Rejected: kept with its reason, do not use it."
    return None


async def _lire(contexte: Contexte, parametres: _Lire) -> dict[str, Any]:
    try:
        element = await service.lire_element(parametres.famille, parametres.slug)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    courante = element.courante
    return {
        "ok": True,
        "famille": element.famille,
        "slug": element.slug,
        "titre": element.titre,
        "statut": courante.statut.value,
        "version": courante.numero,
        "banc": courante.banc.model_dump(mode="json") if courante.banc else None,
        "origine": courante.origine.model_dump(mode="json") if courante.origine else None,
        "raison_rejet": courante.raison_rejet,
        "contenu": courante.contenu,
        "fiche_de_la_famille": (await fiches.lire(element.famille)).model_dump(),
        "dossier": element.dossier,
        "etiquettes": element.etiquettes,
        "avertissement": _avertissement(courante.statut),
        "utilisee_par": await service.nombre_d_agents(element.famille, element.slug),
    }


class _Appliquer(BaseModel):
    famille: str
    slug: str
    workflow_id: int | None = None


async def appliquer_un_element(contexte: Contexte, famille: str, slug: str, workflow_id: int | None) -> dict[str, Any]:
    """L'application d'une famille à un agent. Partagée avec ``phrases_regler(depuis=...)``."""
    identifiant = await agent_verifie(contexte, workflow_id)
    try:
        element = await service.lire_element(famille, slug)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    courante = element.courante
    definition = await familles_libres.trouver(famille)
    if courante.statut is Statut.REJETE:
        raise ErreurAction(f"« {famille}/{slug} » is rejected ({courante.raison_rejet or 'no reason kept'}): it is not applied.", "rejete")
    org = contexte.organisation_id
    contenu = courante.contenu
    ecrit: dict[str, Any] = {}
    try:
        if famille == "phrases-du-code":
            ecrit = await reglages_agent.regler_phrases(org, identifiant, list(contenu.get("regles") or []))
        elif famille == "modeles-reglages":
            ecrit = await reglages_agent.regler(org, identifiant, dict(contenu.get("valeurs") or {}))
        elif famille == "lexiques":
            ecrit = await _appliquer_lexique(org, contenu)
    except reglages_agent.ErreurReglage as erreur:
        raise ErreurAction(str(erreur), "reglage") from None
    await service.enregistrer_utilisation(famille, slug, courante.numero, org, identifiant)
    if courante.statut is Statut.CANDIDAT:
        await contexte_agent.noter_un_candidat(org, identifiant, famille, slug, courante.numero)
    return {
        "ok": True,
        "mode": definition.mode,
        "applique": definition.mode == MODE_APPLIQUE,
        "ecrit": ecrit,
        "version": courante.numero,
        "statut": courante.statut.value,
        "avertissement": _avertissement(courante.statut),
        # Les familles qui se construisent : le builder reçoit le contenu et l'écrit lui-même.
        **({} if definition.mode == MODE_APPLIQUE else {"contenu": contenu}),
    }


async def _appliquer_lexique(organization_id: int, contenu: dict[str, Any]) -> dict[str, Any]:
    from pydantic import ValidationError

    from api.schemas.lexique_metier import LexiqueMetier
    from api.services.lexique.stockage import enregistrer_lexique, fusionner_import, lire_lexique_strict

    try:
        importe = LexiqueMetier.model_validate({"termes": contenu.get("termes") or []})
        fusion, ajoutes, deja = fusionner_import(await lire_lexique_strict(organization_id), importe)
    except (ValidationError, ValueError) as erreur:
        raise reglages_agent.ErreurReglage(f"The lexicon would not be accepted: {str(erreur)[:200]}") from None
    await enregistrer_lexique(organization_id, fusion)
    return {"ajoutes": ajoutes, "deja_presents": deja}


async def _appliquer(contexte: Contexte, parametres: _Appliquer) -> dict[str, Any]:
    return await appliquer_un_element(contexte, parametres.famille, parametres.slug, parametres.workflow_id)


class _Candidat(BaseModel):
    famille: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    titre: str = Field(min_length=1, max_length=200)
    contenu: dict[str, Any]
    notes: str = Field(default="", max_length=2000)


async def _ecrire_candidat(contexte: Contexte, parametres: _Candidat) -> dict[str, Any]:
    try:
        await droits.exiger_l_equipe(contexte.user)
        element = await service.ecrire_candidat(
            parametres.famille,
            parametres.slug,
            parametres.titre,
            parametres.contenu,
            _auteur_builder(contexte),
            notes=parametres.notes,
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return {"ok": True, "version": element.version_courante, "statut": element.statut.value}


class _Proposer(BaseModel):
    type: Literal["version", "passage_recette", "rejet", "fiche", "famille"]
    famille: str
    slug: str
    justification: str = Field(min_length=1, max_length=2000)
    titre: str = ""
    contenu: dict[str, Any] | None = Field(
        default=None,
        description="The proposed content. For type « fiche »: description, quand, comment (slug = the family). For type « famille »: libelle, groupe, cible (slug = the new family).",
    )
    version: int | None = None
    banc: str | None = Field(default=None, max_length=500, description="What proves it (for a passage to recipe).")


async def _proposer(contexte: Contexte, parametres: _Proposer) -> dict[str, Any]:
    try:
        await droits.exiger_l_equipe(contexte.user)
        proposition = await propositions.creer(
            parametres.type,
            parametres.famille,
            parametres.slug,
            parametres.justification,
            _auteur_builder(contexte),
            titre=parametres.titre,
            contenu=parametres.contenu,
            version=parametres.version,
            banc=Banc(description=parametres.banc) if parametres.banc else None,
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return {
        "ok": True,
        "proposition": proposition.id,
        "carte": {"type": "proposition", "id": proposition.id, "proposition_type": proposition.type, "famille": proposition.famille, "slug": proposition.slug},
        "message": "Proposal queued: a person accepts or refuses it.",
    }


for _nom, _description, _parametres, _fonction, _ecriture in (
    (
        "bibliotheque_chercher",
        "Search the whole library (titles, labels, content), optionally by family, status, sub-folder and labels. 25 per page.",
        _Chercher,
        _chercher,
        False,
    ),
    (
        "bibliotheque_ranger",
        "Put an element in a sub-folder of its family and/or set its labels. Does not change its content or its status. Team members only.",
        _Ranger,
        _ranger,
        True,
    ),
    ("bibliotheque_lister", "List the library: without a family, the families; with one, its elements (status, version, bench).", _Lister, _lister, False),
    ("bibliotheque_lire", "Read a library element (current version, status, proof, origin). A candidate is not proven: say so.", _Lire, _lire, False),
    (
        "bibliotheque_appliquer",
        "Apply a library element to the agent: sentences of the code, settings templates and lexicons are written in the agent; other families return their content for you to build with.",
        _Appliquer,
        _appliquer,
        True,
    ),
    (
        "bibliotheque_ecrire_candidat",
        "Create or edit a CANDIDATE element of the library (never a recipe). Team members only.",
        _Candidat,
        _ecrire_candidat,
        True,
    ),
    (
        "bibliotheque_proposer",
        "Propose a new version, a passage to recipe (with its bench), a rejection, a change to the SHEET of a family (type fiche) or a new family (type famille). A person decides. Team members only.",
        _Proposer,
        _proposer,
        True,
    ),
):
    enregistrer(
        Action(nom=_nom, description=_description, parametres=_parametres, fonction=_fonction, ecriture=_ecriture, groupe="bibliotheque")
    )
