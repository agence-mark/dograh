"""[.mark] Builder partie 3, N1 (sous-lot 5) : tout ce que l'écran permet pour l'ENTREPRISE, le builder le permet (05 § 4, 03 § 2).

Établissements, phrases de l'organisation, annonce d'ouverture, listes de valeurs, vocabulaire, équipe, campagnes, téléphonie. Chaque action
rejoue EXACTEMENT le geste de l'écran : elle appelle la fonction de la route (mêmes contrôles, mêmes bornes, même auteur dans le journal de
la base du client) avec la personne du chat. Rien n'est recopié. La permission décide (``modes.py``) : ces actions sont rangées dans leur
famille (``familles_actions.py``) ; ce qui touche toute l'organisation exige « Tout permettre » ou une carte ; ce qui appelle de vrais gens
est dans la famille « appels réels ».

* **Les secrets ne passent jamais** (garde des secrets, ``garde_secrets.py``) : la téléphonie se lit par le NOM de chaque compte (jamais ses
  identifiants), une campagne ou un appel de test choisit un compte par son identifiant ; les identifiants d'un compte se saisissent à l'écran.
* **Annuler** : les réécritures d'un objet entier (établissement, phrases, annonce, vocabulaire) rangent l'état d'avant dans la ligne du
  journal et savent le remettre (``extras["avant"]`` / ``["defaire"]``, voir ``journal.py``) ; le reste dit pourquoi il ne se défait pas.
* Écran seulement (``mcp=False``) : Claude Code n'a pas de mode de chat, donc pas ces gestes.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer


def _detail(erreur: HTTPException) -> str:
    detail = erreur.detail
    if isinstance(detail, dict):
        detail = detail.get("message") or detail
    return str(detail)[:600]


async def _ecran(appel) -> Any:
    """Le geste de l'écran, ou son refus en une phrase pour le cerveau (jamais une pile)."""
    try:
        rendu = await appel
    except HTTPException as erreur:
        raise ErreurAction(f"Refused by the screen's checks: {_detail(erreur)}", "refus_ecran") from None
    return rendu.model_dump(mode="json") if hasattr(rendu, "model_dump") else rendu


# --- paramètres ------------------------------------------------------------------------------------------------------------------------


class _Rien(BaseModel):
    pass


class _Page(BaseModel):
    limite: int = Field(default=25, ge=1, le=100)
    decalage: int = Field(default=0, ge=0)


def _modeles():
    from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture
    from api.schemas.etablissements import CatalogueEtablissements, ModificationEtablissement
    from api.schemas.etablissements import DemandeEtatFiche
    from api.schemas.lexique_metier import LexiqueMetier
    from api.schemas.phrases import CataloguePhrases

    return CatalogueEtablissements, ModificationEtablissement, DemandeEtatFiche, LexiqueMetier, CataloguePhrases, ReglagesAnnonceOuverture


# --- établissements --------------------------------------------------------------------------------------------------------------------


async def _etablissements_lire(contexte: Contexte, p: _Rien) -> dict[str, Any]:
    from api.routes.etablissements import get_etablissements

    return {"ok": True, **await _ecran(get_etablissements(contexte.user))}


async def _catalogue_actuel(contexte: Contexte) -> dict[str, Any]:
    from api.routes.etablissements import get_etablissements

    return await _ecran(get_etablissements(contexte.user))


async def _etablissements_remplacer(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.etablissements import save_etablissements

    return {"ok": True, **await _ecran(save_etablissements(p, contexte.user))}


async def _etablissements_remettre(contexte: Contexte, avant: dict[str, Any]) -> None:
    from api.routes.etablissements import save_etablissements
    from api.schemas.etablissements import CatalogueEtablissements

    await _ecran(save_etablissements(CatalogueEtablissements.model_validate(avant), contexte.user))


class _Fiche(BaseModel):
    identifiant: str = Field(min_length=1, max_length=64, description="The establishment id (etablissements_lire gives it).")


def _fiche_modifier_params():
    from api.schemas.etablissements import ModificationEtablissement

    class FicheModifier(_Fiche):
        modifications: ModificationEtablissement = Field(description="Only the fields to change; the others keep their value.")

    return FicheModifier


async def _fiche_avant(contexte: Contexte, arguments: dict[str, Any]) -> dict[str, Any]:
    catalogue = await _catalogue_actuel(contexte)
    fiche = next((f for f in catalogue.get("etablissements", []) if f.get("id") == arguments.get("identifiant")), None)
    if fiche is None:
        raise ErreurAction("Unknown establishment.", "introuvable")
    return {"identifiant": arguments["identifiant"], "valeurs": {cle: fiche.get(cle) for cle in (arguments.get("modifications") or {})}}


async def _fiche_modifier(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.etablissements import modifier_etablissement

    return {"ok": True, "etablissement": await _ecran(modifier_etablissement(p.identifiant, p.modifications, contexte.user))}


async def _fiche_remettre(contexte: Contexte, avant: dict[str, Any]) -> None:
    from api.routes.etablissements import _modifier_une_fiche

    await _modifier_une_fiche(contexte.user, avant["identifiant"], avant["valeurs"])


def _fiche_etat_params():
    from api.schemas.etablissements import DemandeEtatFiche

    class FicheEtat(_Fiche):
        etat: DemandeEtatFiche = Field(description='Close ({"etat_force": "FERME"}, with or without an end date) or reopen ({"etat_force": null}).')

    return FicheEtat


async def _fiche_etat(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.etablissements import fermer_ou_rouvrir_etablissement

    return {"ok": True, "etablissement": await _ecran(fermer_ou_rouvrir_etablissement(p.identifiant, p.etat, contexte.user))}


async def _etat_avant(contexte: Contexte, arguments: dict[str, Any]) -> dict[str, Any]:
    catalogue = await _catalogue_actuel(contexte)
    fiche = next((f for f in catalogue.get("etablissements", []) if f.get("id") == arguments.get("identifiant")), None)
    if fiche is None:
        raise ErreurAction("Unknown establishment.", "introuvable")
    return {"identifiant": arguments["identifiant"], "valeurs": {"etat_force": fiche.get("etat_force"), "etat_force_jusqu_a": fiche.get("etat_force_jusqu_a")}}


# --- phrases de l'organisation, annonce, vocabulaire, listes ----------------------------------------------------------------------------


async def _phrases_lire(contexte: Contexte, p: _Rien) -> dict[str, Any]:
    from api.routes.etablissements import get_phrases

    return {"ok": True, **await _ecran(get_phrases(contexte.user))}


async def _phrases_avant(contexte: Contexte, arguments: dict[str, Any]) -> dict[str, Any]:
    from api.routes.etablissements import get_phrases

    return await _ecran(get_phrases(contexte.user))


async def _phrases_ecrire(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.etablissements import save_phrases

    return {"ok": True, **await _ecran(save_phrases(p, contexte.user))}


async def _phrases_remettre(contexte: Contexte, avant: dict[str, Any]) -> None:
    from api.routes.etablissements import save_phrases
    from api.schemas.phrases import CataloguePhrases

    await _ecran(save_phrases(CataloguePhrases.model_validate(avant), contexte.user))


async def _annonce_lire(contexte: Contexte, p: _Rien) -> dict[str, Any]:
    from api.routes.organization import get_annonce_ouverture

    return {"ok": True, **await _ecran(get_annonce_ouverture(contexte.user))}


async def _annonce_avant(contexte: Contexte, arguments: dict[str, Any]) -> dict[str, Any]:
    from api.routes.organization import get_annonce_ouverture

    return await _ecran(get_annonce_ouverture(contexte.user))


async def _annonce_regler(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.organization import save_annonce_ouverture

    return {"ok": True, **await _ecran(save_annonce_ouverture(p, contexte.user))}


async def _annonce_remettre(contexte: Contexte, avant: dict[str, Any]) -> None:
    from api.routes.organization import save_annonce_ouverture
    from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture

    await _ecran(save_annonce_ouverture(ReglagesAnnonceOuverture.model_validate(avant), contexte.user))


async def _lexique_lire(contexte: Contexte, p: _Rien) -> dict[str, Any]:
    from api.routes.organization import get_lexique

    return {"ok": True, **await _ecran(get_lexique(contexte.user))}


async def _lexique_avant(contexte: Contexte, arguments: dict[str, Any]) -> dict[str, Any]:
    from api.routes.organization import get_lexique

    return await _ecran(get_lexique(contexte.user))


async def _lexique_ecrire(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.organization import save_lexique

    return {"ok": True, **await _ecran(save_lexique(p, contexte.user))}


async def _lexique_remettre(contexte: Contexte, avant: dict[str, Any]) -> None:
    from api.routes.organization import save_lexique
    from api.schemas.lexique_metier import LexiqueMetier

    await _ecran(save_lexique(LexiqueMetier.model_validate(avant), contexte.user))


async def _listes_lire(contexte: Contexte, p: _Rien) -> dict[str, Any]:
    from api.routes.listes_valeurs import get_listes_valeurs

    return {"ok": True, **await _ecran(get_listes_valeurs(contexte.user))}


async def _listes_cocher(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.listes_valeurs import put_listes_valeurs

    return {"ok": True, **await _ecran(put_listes_valeurs(p, contexte.user))}


# --- équipe ----------------------------------------------------------------------------------------------------------------------------


async def _equipe_lister(contexte: Contexte, p: _Page) -> dict[str, Any]:
    from api.routes.equipe_mark import lister_les_invitations, lister_les_membres

    membres = await _ecran(lister_les_membres(p.limite, p.decalage, contexte.user))
    invitations = await _ecran(lister_les_invitations(p.limite, p.decalage, contexte.user))
    return {"ok": True, "membres": membres, "invitations": invitations}


def _inviter_params():
    from api.routes.equipe_mark import InvitationRequest

    return InvitationRequest


async def _equipe_inviter(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.equipe_mark import inviter

    rendu = await _ecran(inviter(p, contexte.user))
    rendu.pop("lien", None)  # le lien d'invitation est un jeton à usage unique : la personne le lit à l'écran, jamais le builder
    return {"ok": True, "invitation": rendu}


# --- campagnes -------------------------------------------------------------------------------------------------------------------------


class _Campagne(BaseModel):
    campagne_id: int = Field(ge=1, description="The campaign (campagnes_lister gives the ids).")


async def _campagnes_lister(contexte: Contexte, p: _Rien) -> dict[str, Any]:
    from api.routes.campaign import get_campaigns

    return {"ok": True, **await _ecran(get_campaigns(contexte.user))}


async def _campagne_lire(contexte: Contexte, p: _Campagne) -> dict[str, Any]:
    from api.routes.campaign import get_campaign

    return {"ok": True, "campagne": await _ecran(get_campaign(p.campagne_id, contexte.user))}


def _campagne_creer_params():
    from api.routes.campaign import CreateCampaignRequest

    return CreateCampaignRequest


async def _campagne_creer(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.campaign import create_campaign

    return {"ok": True, "campagne": await _ecran(create_campaign(p, contexte.user))}


def _campagne_modifier_params():
    from api.routes.campaign import UpdateCampaignRequest

    class CampagneModifier(_Campagne):
        modifications: UpdateCampaignRequest = Field(description="Only the settings to change.")

    return CampagneModifier


async def _campagne_modifier(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.campaign import update_campaign

    return {"ok": True, "campagne": await _ecran(update_campaign(p.campagne_id, p.modifications, contexte.user))}


async def _campagne_pause(contexte: Contexte, p: _Campagne) -> dict[str, Any]:
    from api.routes.campaign import pause_campaign

    return {"ok": True, "campagne": await _ecran(pause_campaign(p.campagne_id, contexte.user))}


async def _campagne_demarrer(contexte: Contexte, p: _Campagne) -> dict[str, Any]:
    from api.routes.campaign import start_campaign

    return {"ok": True, "campagne": await _ecran(start_campaign(p.campagne_id, contexte.user))}


async def _campagne_reprendre(contexte: Contexte, p: _Campagne) -> dict[str, Any]:
    from api.routes.campaign import resume_campaign

    return {"ok": True, "campagne": await _ecran(resume_campaign(p.campagne_id, contexte.user))}


# --- téléphonie ------------------------------------------------------------------------------------------------------------------------


async def _telephonie_lister(contexte: Contexte, p: _Rien) -> dict[str, Any]:
    """Les comptes de téléphonie par leur NOM : jamais leurs identifiants (une personne les saisit à l'écran)."""
    from api.db import db_client

    comptes = await db_client.list_telephony_configurations(contexte.organisation_id)
    return {
        "ok": True,
        "comptes": [
            {"id": c.id, "nom": c.name, "fournisseur": c.provider, "par_defaut_sortant": bool(c.is_default_outbound), "inactif": bool(c.inactive)} for c in comptes
        ],
    }


def _appel_test_params():
    from api.routes.telephony import InitiateCallRequest

    return InitiateCallRequest


async def _appel_test(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.telephony import initiate_call

    # Le brouillon de l'agent doit être celui de l'organisation (relu avec l'organisation, 404 sinon).
    from api.services.builder.actions._commun import agent_de_l_organisation

    await agent_de_l_organisation(contexte, p.workflow_id)
    return {"ok": True, "appel": await _ecran(initiate_call(p, contexte.user))}


# --- N2 : les restes de l'écran (copier, reprise, recopier, horaires, import, rappel, annuler une invitation) ------------------------------


def _copier_params():
    from api.schemas.etablissements import DemandeCopieEtablissement

    return DemandeCopieEtablissement


async def _fiche_copier(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.etablissements import copier_etablissement

    return {"ok": True, **await _ecran(copier_etablissement(p, contexte.user))}


async def _reprise_essayer(contexte: Contexte, p: _Rien) -> dict[str, Any]:
    """L'essai de la reprise : liste ce qui serait écrit, n'écrit rien (``ecrire`` reste faux, comme l'écran)."""
    from api.routes.etablissements import reprise_des_fiches
    from api.schemas.etablissements import DemandeReprise

    return {"ok": True, **await _ecran(reprise_des_fiches(DemandeReprise(ecrire=False), contexte.user))}


async def _reprise_ecrire(contexte: Contexte, p: _Rien) -> dict[str, Any]:
    from api.routes.etablissements import reprise_des_fiches
    from api.schemas.etablissements import DemandeReprise

    return {"ok": True, **await _ecran(reprise_des_fiches(DemandeReprise(ecrire=True), contexte.user))}


def _appliquer_a_tous_params():
    from api.schemas.appliquer_a_tous import DemandeAppliquerATous

    class AppliquerATous(_Fiche, DemandeAppliquerATous):
        pass

    return AppliquerATous


async def _appliquer_a_tous(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.etablissements import appliquer_a_tous_les_etablissements
    from api.schemas.appliquer_a_tous import DemandeAppliquerATous

    corps = DemandeAppliquerATous(reglage=p.reglage, cle=p.cle)
    return {"ok": True, **await _ecran(appliquer_a_tous_les_etablissements(p.identifiant, corps, contexte.user))}


def _horaires_params():
    from api.schemas.agents_servis import DemandeControleHoraires

    return DemandeControleHoraires


async def _horaires_controler(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.etablissements import controle_des_horaires

    return {"ok": True, **await _ecran(controle_des_horaires(p, contexte.user))}


def _etablissements_de_l_agent_params():
    from api.routes.etablissements import DemandeEtablissementsDeLagent

    return DemandeEtablissementsDeLagent


async def _etablissements_de_l_agent(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.etablissements import post_etablissements_de_lagent
    from api.services.builder.actions._commun import agent_de_l_organisation

    await agent_de_l_organisation(contexte, p.workflow_id)
    return {"ok": True, **await _ecran(post_etablissements_de_lagent(p, contexte.user))}


class _Vocabulaire(BaseModel):
    vocabulaire: Any = Field(description="The vocabulary to measure (the draft), as lexique_lire gives it.")


def _lexique_corps(valeur: Any):
    from pydantic import ValidationError

    from api.schemas.lexique_metier import LexiqueMetier

    try:
        return LexiqueMetier.model_validate(valeur)
    except ValidationError as erreur:
        raise ErreurAction(f"The vocabulary is not valid: {str(erreur.errors()[0].get('msg'))[:200]}", "refus_ecran") from None


async def _lexique_budget(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.organization import budget_lexique

    return {"ok": True, **await _ecran(budget_lexique(_lexique_corps(p.vocabulaire), contexte.user))}


class _Modele(BaseModel):
    modele: Any = Field(description="A template's terms (same shape as the vocabulary): the terms ABSENT are added, a term already there never changes.")


async def _lexique_importer(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.organization import import_lexique

    return {"ok": True, **await _ecran(import_lexique(_lexique_corps(p.modele), contexte.user))}


class _Invitation(BaseModel):
    invitation_id: int = Field(ge=1, description="The open invitation (equipe_lister gives the ids).")


async def _equipe_annuler_invitation(contexte: Contexte, p: _Invitation) -> dict[str, Any]:
    from api.routes.equipe_mark import annuler_une_invitation

    await _ecran(annuler_une_invitation(p.invitation_id, contexte.user))
    return {"ok": True, "annulee": p.invitation_id}


def _rappeler_params():
    from api.routes.campaign import RedialCampaignRequest

    class CampagneRappeler(_Campagne):
        modalites: RedialCampaignRequest = Field(default_factory=RedialCampaignRequest, description="Which failed calls to redial (voicemail, no answer, busy) and the retry settings.")

    return CampagneRappeler


async def _campagne_rappeler(contexte: Contexte, p) -> dict[str, Any]:
    from api.routes.campaign import redial_campaign

    return {"ok": True, "campagne": await _ecran(redial_campaign(p.campagne_id, p.modalites, contexte.user))}


# --- inscription -----------------------------------------------------------------------------------------------------------------------


def _inscrire(nom: str, description: str, parametres, fonction, *, ecriture: bool, groupe: str = "entreprise", avant=None, defaire=None) -> None:
    extras = {"avant": avant, "defaire": defaire} if avant and defaire else {}
    enregistrer(Action(nom=nom, description=description, parametres=parametres, fonction=fonction, ecriture=ecriture, mcp=False, groupe=groupe, extras=extras))


def _inscrire_tout() -> None:
    CatalogueEtablissements, _Mod, _Etat, LexiqueMetier, CataloguePhrases, ReglagesAnnonceOuverture = _modeles()

    class _Etablissements(BaseModel):
        catalogue: CatalogueEtablissements = Field(description="The WHOLE catalogue (every establishment): read it first, change it, send it back.")

    class _Phrases(BaseModel):
        catalogue: CataloguePhrases = Field(description="The WHOLE catalogue of sentences: read it first, change it, send it back.")

    class _Annonce(BaseModel):
        reglages: ReglagesAnnonceOuverture

    class _Lexique(BaseModel):
        vocabulaire: LexiqueMetier = Field(description="The WHOLE trade vocabulary: read it first, change it, send it back.")

    from api.schemas.listes_valeurs import ModificationListesValeurs

    class _Listes(BaseModel):
        modification: ModificationListesValeurs

    async def remplacer(contexte, p):
        return await _etablissements_remplacer(contexte, p.catalogue)

    async def phrases(contexte, p):
        return await _phrases_ecrire(contexte, p.catalogue)

    async def annonce(contexte, p):
        return await _annonce_regler(contexte, p.reglages)

    async def lexique(contexte, p):
        return await _lexique_ecrire(contexte, p.vocabulaire)

    async def listes(contexte, p):
        return await _listes_cocher(contexte, p.modification)

    async def avant_catalogue(contexte, arguments):
        return await _catalogue_actuel(contexte)

    FicheModifier, FicheEtat = _fiche_modifier_params(), _fiche_etat_params()
    _inscrire("etablissements_lire", "Read the establishments of the organisation (the whole catalogue).", _Rien, _etablissements_lire, ecriture=False)
    _inscrire("etablissements_remplacer", "Replace the catalogue of establishments (read it first; the whole catalogue goes back, as the screen's Save).", _Etablissements, remplacer, ecriture=True, avant=avant_catalogue, defaire=_etablissements_remettre)
    _inscrire("etablissement_modifier", "Change some fields of ONE establishment; the fields not sent keep their value.", FicheModifier, _fiche_modifier, ecriture=True, avant=_fiche_avant, defaire=_fiche_remettre)
    _inscrire("etablissement_fermer_ou_rouvrir", "Close (with or without an end date) or reopen ONE establishment.", FicheEtat, _fiche_etat, ecriture=True, avant=_etat_avant, defaire=_fiche_remettre)
    _inscrire("phrases_organisation_lire", "Read the catalogue of sentences of the organisation.", _Rien, _phrases_lire, ecriture=False)
    _inscrire("phrases_organisation_ecrire", "Replace the catalogue of sentences of the organisation (read it first).", _Phrases, phrases, ecriture=True, avant=_phrases_avant, defaire=_phrases_remettre)
    _inscrire("annonce_lire", "Read what the agents say at pick-up when the business is closed.", _Rien, _annonce_lire, ecriture=False)
    _inscrire("annonce_regler", "Set what the agents say at pick-up when the business is closed.", _Annonce, annonce, ecriture=True, avant=_annonce_avant, defaire=_annonce_remettre)
    _inscrire("lexique_lire", "Read the trade vocabulary of the organisation.", _Rien, _lexique_lire, ecriture=False)
    _inscrire("lexique_ecrire", "Replace the trade vocabulary of the organisation (read it first).", _Lexique, lexique, ecriture=True, avant=_lexique_avant, defaire=_lexique_remettre)
    _inscrire("listes_valeurs_lire", "Read the lists of values of the client's database (boxes ticked or not).", _Rien, _listes_lire, ecriture=False)
    _inscrire("listes_valeurs_cocher", "Tick or untick boxes of the lists of values; the others keep their state.", _Listes, listes, ecriture=True)
    _inscrire("equipe_lister", "List the .mark team members and the open invitations (read only).", _Page, _equipe_lister, ecriture=False)
    _inscrire("equipe_inviter", "Invite someone to the .mark team with a role (the invitation link is shown to the person on the screen, never to you).", _inviter_params(), _equipe_inviter, ecriture=True)
    _inscrire("campagnes_lister", "List the calling campaigns of the organisation.", _Rien, _campagnes_lister, ecriture=False)
    _inscrire("campagne_lire", "Read one calling campaign.", _Campagne, _campagne_lire, ecriture=False)
    _inscrire("campagne_creer", "Create a calling campaign (it does not start: starting calls real people).", _campagne_creer_params(), _campagne_creer, ecriture=True)
    _inscrire("campagne_modifier", "Change the settings of a campaign (name, retries, concurrency, schedule).", _campagne_modifier_params(), _campagne_modifier, ecriture=True)
    _inscrire("campagne_pause", "Pause a running campaign (the calls stop).", _Campagne, _campagne_pause, ecriture=True)
    _inscrire("campagne_demarrer", "Start a campaign: REAL PEOPLE ARE CALLED.", _Campagne, _campagne_demarrer, ecriture=True, groupe="appels_reels")
    _inscrire("campagne_reprendre", "Resume a paused campaign: REAL PEOPLE ARE CALLED.", _Campagne, _campagne_reprendre, ecriture=True, groupe="appels_reels")
    _inscrire("etablissement_copier", "Make a NEW establishment from an existing one (everything that describes the place; never its numbers nor an immediate closure).", _copier_params(), _fiche_copier, ecriture=True)
    _inscrire("etablissements_reprise_essayer", "Trial run of the takeover of the fiches and agents: lists what would be written, writes nothing.", _Rien, _reprise_essayer, ecriture=False)
    _inscrire("etablissements_reprise_ecrire", "Run the takeover of the fiches and agents FOR REAL (do the trial run first; values already on a fiche are never replaced).", _Rien, _reprise_ecrire, ecriture=True)
    _inscrire("etablissement_appliquer_a_tous", "Copy ONE setting of an establishment into ALL the other establishments (all or none).", _appliquer_a_tous_params(), _appliquer_a_tous, ecriture=True)
    _inscrire("horaires_controler", "Check opening hours written as text: valid, or the reason for the refusal (writes nothing).", _horaires_params(), _horaires_controler, ecriture=False)
    _inscrire("etablissements_de_l_agent_lire", "Read the establishments one agent serves (a read, with the agent's own hours and address if given).", _etablissements_de_l_agent_params(), _etablissements_de_l_agent, ecriture=False)
    _inscrire("lexique_budget_lire", "Measure what the transcription would receive from a vocabulary draft against the provider's ceiling (writes nothing).", _Vocabulaire, _lexique_budget, ecriture=False)
    _inscrire("lexique_importer", "Add a template's trade terms that are absent from the vocabulary; a term already there never changes.", _Modele, _lexique_importer, ecriture=True, avant=_lexique_avant, defaire=_lexique_remettre)
    _inscrire("equipe_annuler_invitation", "Cancel an open invitation to the .mark team.", _Invitation, _equipe_annuler_invitation, ecriture=True)
    _inscrire("campagne_rappeler", "Redial the failed calls of a completed campaign (voicemail, no answer, busy): REAL PEOPLE ARE CALLED.", _rappeler_params(), _campagne_rappeler, ecriture=True, groupe="appels_reels")
    _inscrire("telephonie_lister", "List the telephony accounts by NAME (never their credentials: a person types those on the screen).", _Rien, _telephonie_lister, ecriture=False)
    _inscrire("appel_de_test_lancer", "Place a test call of the agent's draft to a phone number: A REAL CALL.", _appel_test_params(), _appel_test, ecriture=True, groupe="appels_reels")


_inscrire_tout()
