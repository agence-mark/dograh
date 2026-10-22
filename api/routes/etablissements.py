"""[.mark] The establishments of the organization, on screen (chantier l-agent-travaille, L1).

Four routes, all scoped to the user's selected organization:

- ``GET  /organizations/etablissements``          the catalogue (strict reading);
- ``PUT  /organizations/etablissements``          replace it; every bound checked
  BEFORE writing (422, nothing written): hours that parse, a commune at its
  postal code, called numbers that are the organization's own Telephony numbers;
- ``GET  /organizations/etablissements/numeros``  the organization's numbers, for
  the choice list of an establishment;
- ``POST /organizations/etablissements/agent``    what an agent's calls will read,
  establishment by establishment, with the level each value comes from -- the
  same functions as the call (E8: one rule on screen and in the code).

[.mark] Lot F4, writes by element (nothing replaces the catalogue):

- ``PATCH /organizations/etablissements/{id}``      only the fields sent change;
- ``POST  /organizations/etablissements/{id}/etat`` close or reopen one fiche.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from api.db import db_client
from api.db.models import UserModel
from api.schemas.etablissements import (
    CatalogueEtablissements,
    DemandeCopieEtablissement,
    DemandeEtatFiche,
    DemandeReprise,
    Etablissement,
    EtablissementsDeLagent,
    ModificationEtablissement,
    NumeroDeLorganisation,
    ResultatCopieEtablissement,
    ResultatReprise,
)
from api.schemas.agents_servis import DemandeControleHoraires, ResultatControleHoraires
from api.schemas.phrases import CataloguePhrases
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client.rattachement import auteur_de
from api.db.bases_clients.connexion import BaseClientIndisponible
from api.services.communes.adresse import (
    AdresseInvalide,
    texte_adresse,
    valider_adresse_saisie,
)
from api.services.etablissements.appel import etablissements_de_lagent
from api.services.etablissements.stockage import (
    enregistrer_etablissements,
    enregistrer_phrases,
    enregistrer_un_etablissement,
    lire_etablissements_strict,
    lire_phrases_strict,
    verrou_des_fiches,
)

router = APIRouter(prefix="/organizations/etablissements", tags=["organizations"])


def _refus(message: str, loc: list) -> HTTPException:
    return HTTPException(status_code=422, detail=[{"msg": message, "loc": loc}])


def _base_injoignable(erreur: Exception) -> HTTPException:
    """L3: the client's database is the source and does not answer. Nothing was written."""
    return HTTPException(status_code=503, detail=f"{erreur} Nothing was changed.")


@router.get("", response_model=CatalogueEtablissements)
async def get_etablissements(user: UserModel = Depends(get_user_with_selected_organization)):
    """⛔ Strict: shown empty because unreadable, the next save would replace them."""
    try:
        return await lire_etablissements_strict(user.selected_organization_id)
    except BaseClientIndisponible as erreur:
        raise _base_injoignable(erreur) from None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Establishments unreadable for the screen: {erreur!r}")
        raise HTTPException(
            status_code=500,
            detail=(
                "The establishments saved for this organization cannot be read. "
                "Nothing was changed; saving now would replace them."
            ),
        ) from None


async def _numeros_de_lorganisation(organization_id: int) -> list[NumeroDeLorganisation]:
    lignes = await db_client.lister_numeros_de_lorganisation(organization_id)
    return [
        NumeroDeLorganisation(numero=adresse, libelle=libelle, agent=nom)
        for adresse, libelle, _agent, nom, _actif in lignes
    ]


@router.get("/numeros", response_model=list[NumeroDeLorganisation])
async def get_numeros(user: UserModel = Depends(get_user_with_selected_organization)):
    return await _numeros_de_lorganisation(user.selected_organization_id)


async def _controler_etablissements(
    organization_id: int,
    etablissements: list,
    seulement: set[str] | None = None,
    phrases_seules: set[str] | None = None,
) -> list:
    """Every bound of a save, fiche by fiche, BEFORE anything is written (422 otherwise).
    Returns the fiches with their address checked and named officially.

    [.mark] Lot 4: taken out of ``save_etablissements`` unchanged, so the copy of a fiche
    (``/copier``) passes through the very same controls.

    [.mark] Lot F4: for a PARTIAL update, ``seulement`` names the fields the request sent (among
    ``horaires_ouverture``, ``numeros``, ``adresse``) and ``phrases_seules`` the sentences it sent: what was not sent is not re-judged, so a change of name is never refused for
    a number that has left the Telephony since. ``None`` (every other route): everything is checked."""
    from api.services.pipecat.etat_ouverture import (
        HorairesInvalides,
        vers_expression_osm,
    )

    siens = {n.numero for n in await _numeros_de_lorganisation(organization_id)}
    try:
        phrases = await lire_phrases_strict(organization_id)
    except Exception:  # noqa: BLE001 -- unreadable: no establishment sentence can be checked
        phrases = CataloguePhrases()
    au_niveau_etablissement = {p.variable for p in phrases.phrases if p.niveau == "etablissement"}
    verifies = []
    for rang, etablissement in enumerate(etablissements):
        loc = ["body", "etablissements", rang]
        for variable in etablissement.phrases:
            if phrases_seules is not None and variable not in phrases_seules:
                continue
            if variable not in au_niveau_etablissement:
                raise _refus(
                    f"{etablissement.nom}: « {variable} » is not a sentence placed at the establishment's level.",
                    loc + ["phrases", variable],
                )
        if etablissement.horaires_ouverture and (seulement is None or "horaires_ouverture" in seulement):
            try:
                vers_expression_osm(etablissement.horaires_ouverture)
            except HorairesInvalides as erreur:
                raise _refus(f"{etablissement.nom}: {erreur}", loc + ["horaires_ouverture"]) from None
        for numero in etablissement.numeros if seulement is None or "numeros" in seulement else ():
            if numero not in siens:
                # Tenant isolation: a called number must be one of THIS organization's.
                raise _refus(
                    f"{etablissement.nom}: {numero} is not a Telephony number of this organization.",
                    loc + ["numeros"],
                )
        adresse = etablissement.adresse
        if adresse is not None and (seulement is None or "adresse" in seulement):
            try:
                adresse = await valider_adresse_saisie(adresse)
            except AdresseInvalide as erreur:
                raise _refus(f"{etablissement.nom}: {erreur}", loc + ["adresse"]) from None
        verifies.append(etablissement.model_copy(update={"adresse": adresse}))
    return verifies


@router.put("", response_model=CatalogueEtablissements)
async def save_etablissements(
    request: CatalogueEtablissements,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    organization_id = user.selected_organization_id
    verifies = await _controler_etablissements(organization_id, request.etablissements)
    try:
        return await enregistrer_etablissements(
            organization_id, request.model_copy(update={"etablissements": verifies}), auteur_de(user)
        )
    except BaseClientIndisponible as erreur:
        raise _base_injoignable(erreur) from None


@router.post("/controle-horaires", response_model=ResultatControleHoraires)
async def controle_des_horaires(
    request: DemandeControleHoraires,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """[.mark] Lot 9 (C5): the portal sends opening hours as text; Dograh answers « valid » or the
    reason for the refusal, with the SAME function as the screen (``vers_expression_osm``). Writes
    nothing; authenticated like every route here (a key of the organization works)."""
    from api.services.pipecat.etat_ouverture import HorairesInvalides, vers_expression_osm

    try:
        vers_expression_osm(request.texte)
    except HorairesInvalides as erreur:
        return ResultatControleHoraires(valide=False, raison=str(erreur))
    return ResultatControleHoraires(valide=True)


# --------------------------------------------------------------------------- #
# [.mark] Chantier agents-specialises, lot 4 (F2, reprise)
# --------------------------------------------------------------------------- #


async def _catalogue_pour_ecrire(organization_id: int) -> CatalogueEtablissements:
    """Strict, like the screen: a catalogue read empty because unreadable would be replaced."""
    try:
        return await lire_etablissements_strict(organization_id)
    except BaseClientIndisponible as erreur:
        raise _base_injoignable(erreur) from None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Establishments unreadable for a copy or a takeover: {erreur!r}")
        raise HTTPException(
            status_code=500,
            detail="The establishments saved for this organization cannot be read. Nothing was changed.",
        ) from None


@router.post("/copier", response_model=ResultatCopieEtablissement)
async def copier_etablissement(
    request: DemandeCopieEtablissement,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """F2: a new fiche from an existing one. Everything that describes the place is copied
    (and, with a client database, the appointment settings and types); never the numbers
    nor the immediate closure. The new fiche goes through the same controls as a save."""
    from api.services.etablissements.duplication import (
        NON_COPIE,
        IdentifiantPris,
        SourceInconnue,
        dupliquer,
        reglages_dupliques,
    )

    organization_id = user.selected_organization_id
    catalogue = await _catalogue_pour_ecrire(organization_id)
    try:
        nouvelle = dupliquer(catalogue, request.source, request.id, request.nom)
    except SourceInconnue as erreur:
        raise HTTPException(status_code=404, detail=str(erreur)) from None
    except IdentifiantPris as erreur:
        raise _refus(str(erreur), ["body", "id"]) from None
    except ValidationError as erreur:
        raise HTTPException(status_code=422, detail=erreur.errors(include_url=False, include_context=False)) from None
    (verifiee,) = await _controler_etablissements(organization_id, [nouvelle])
    try:
        complet = CatalogueEtablissements(etablissements=[*catalogue.etablissements, verifiee])
    except ValidationError as erreur:
        raise HTTPException(status_code=422, detail=erreur.errors(include_url=False, include_context=False)) from None
    try:
        await enregistrer_etablissements(organization_id, complet, auteur_de(user))
    except BaseClientIndisponible as erreur:
        raise _base_injoignable(erreur) from None
    resultat = ResultatCopieEtablissement(etablissement=verifiee, non_copie=list(NON_COPIE))
    # The appointment settings live in the client's database: copied once the fiche exists there.
    try:
        from api.db.bases_clients.connexion import connecter
        from api.db.bases_clients.planificateur import ecrire_planificateur, lire_planificateur
        from api.services.etablissements.stockage import nom_de_la_base_strict

        nom = await nom_de_la_base_strict(organization_id)
        if nom:
            connexion = await connecter(nom)
            try:
                planificateur = await lire_planificateur(connexion)
                copie, nb_types, reglages = reglages_dupliques(planificateur, request.source, verifiee.id)
                if copie is not planificateur:
                    await ecrire_planificateur(connexion, copie, auteur_de(user))
                resultat.reglages_rendez_vous_copies = reglages
                resultat.types_rendez_vous_copies = nb_types
            finally:
                await connexion.close()
    except Exception as erreur:  # noqa: BLE001 -- the fiche exists; what was not copied is said
        logger.warning(f"[.mark] Appointment settings of fiche {request.source} not copied: {erreur!r}")
        resultat.non_copie.append("reglages_rendez_vous")
    return resultat


@router.post("/reprise", response_model=ResultatReprise)
async def reprise_des_fiches(
    request: DemandeReprise,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """The takeover (C3, R7): writes into each fiche what it used to inherit, and attaches to
    each agent the one fiche its numbers lead to. TRIAL RUN BY DEFAULT: lists what it would
    do and writes nothing; ``ecrire: true`` writes. Replayable: a second run finds nothing to do.
    Values already on a fiche are never replaced; what it cannot decide alone is in ``a_decider``."""
    from api.services.annonce.stockage import lire_annonce_ouverture
    from api.services.etablissements.reprise import (
        ecrire_rattachements,
        lire_agents,
        preparer_reprise,
    )
    from api.services.etablissements.stockage import nom_de_la_base_strict
    from api.services.organization_preferences import get_organization_preferences

    organization_id = user.selected_organization_id
    catalogue = await _catalogue_pour_ecrire(organization_id)
    preferences = await get_organization_preferences(organization_id)
    nom = await nom_de_la_base_strict(organization_id)
    planificateur = None
    if nom:
        from api.db.bases_clients.connexion import connecter
        from api.db.bases_clients.planificateur import lire_planificateur

        try:
            connexion = await connecter(nom)
            try:
                planificateur = await lire_planificateur(connexion)
            finally:
                await connexion.close()
        except Exception as erreur:  # noqa: BLE001
            # Without the planner the takeover would leave the appointment settings behind: nothing is done.
            logger.warning(f"[.mark] Planner unreadable for the takeover: {erreur!r}")
            raise HTTPException(
                status_code=503,
                detail="The appointment settings in the client database cannot be read. Nothing was changed.",
            ) from None
    plan = preparer_reprise(
        catalogue,
        await lire_agents(organization_id),
        getattr(preferences, "adresse_etablissement", None),
        await lire_annonce_ouverture(organization_id),
        planificateur,
    )
    if not request.ecrire:
        return ResultatReprise(ecrit=False, actions=plan.actions, a_decider=plan.a_decider, deja_a_jour=plan.deja_a_jour)

    auteur = auteur_de(user)
    try:
        if plan.fiches:
            modifiees = [
                fiche.model_copy(update=plan.fiches[fiche.id]) if fiche.id in plan.fiches else fiche
                for fiche in catalogue.etablissements
            ]
            controlees = {
                f.id: f
                for f in await _controler_etablissements(organization_id, [f for f in modifiees if f.id in plan.fiches])
            }
            await enregistrer_etablissements(
                organization_id,
                CatalogueEtablissements(etablissements=[controlees.get(f.id, f) for f in modifiees]),
                auteur,
            )
        if plan.reglages and planificateur is not None:
            from api.db.bases_clients.connexion import connecter
            from api.db.bases_clients.planificateur import ecrire_planificateur

            connexion = await connecter(nom)
            try:
                complet = planificateur.model_copy(
                    update={"par_etablissement": {**planificateur.par_etablissement, **plan.reglages}}
                )
                await ecrire_planificateur(connexion, complet, auteur)
            finally:
                await connexion.close()
        if plan.agents:
            await ecrire_rattachements(organization_id, plan.agents)
    except BaseClientIndisponible as erreur:
        raise _base_injoignable(erreur) from None
    return ResultatReprise(ecrit=True, actions=plan.actions, a_decider=plan.a_decider, deja_a_jour=plan.deja_a_jour)


# --------------------------------------------------------------------------- #
# [.mark] Lot F4 : écritures par élément (jamais le catalogue entier)
# --------------------------------------------------------------------------- #


async def _modifier_une_fiche(user: UserModel, identifiant: str, envoye: dict) -> Etablissement:
    """The partial update of ONE fiche: what was sent is laid over the fiche as saved, the whole goes
    through the bounds of a save (422, nothing written), and only that fiche is written. An absent
    field is not touched; nothing here decides WHO may change what (the portal does).

    Constat 28: the read, the overlay and the write happen under ONE lock of the organization, so two
    simultaneous updates of two fields of the same fiche keep both values.

    ``envoye`` holds only the fields the request carried (``exclude_unset``)."""
    try:
        async with verrou_des_fiches(user.selected_organization_id):
            return await _modifier_une_fiche_verrouillee(user, identifiant, envoye)
    except BaseClientIndisponible as erreur:
        raise _base_injoignable(erreur) from None


async def _modifier_une_fiche_verrouillee(user: UserModel, identifiant: str, envoye: dict) -> Etablissement:
    organization_id = user.selected_organization_id
    catalogue = await _catalogue_pour_ecrire(organization_id)
    actuelle = next((e for e in catalogue.etablissements if e.id == identifiant), None)
    if actuelle is None:
        raise HTTPException(status_code=404, detail=f"Establishment « {identifiant} » not found.")
    valeurs = actuelle.model_dump()
    for champ, valeur in envoye.items():
        if champ == "phrases":
            # Sentence by sentence: the others are kept; one sent empty is removed (back to inherited).
            valeurs["phrases"] = {**valeurs["phrases"], **(valeur or {})}
        else:
            valeurs[champ] = valeur
    try:
        nouvelle = Etablissement.model_validate(valeurs)
    except ValidationError as erreur:
        raise HTTPException(status_code=422, detail=erreur.errors(include_url=False, include_context=False, include_input=False)) from None
    # A sentence sent empty is removed: only those that remain are judged (the check of the level).
    (verifiee,) = await _controler_etablissements(
        organization_id,
        [nouvelle],
        seulement=set(envoye),
        phrases_seules=set((envoye.get("phrases") or {}).keys()),
    )
    try:
        # Whole-catalogue rules (one called number leads to one fiche only), as at a save.
        CatalogueEtablissements(
            etablissements=[verifiee if e.id == identifiant else e for e in catalogue.etablissements]
        )
    except ValidationError as erreur:
        raise HTTPException(status_code=422, detail=erreur.errors(include_url=False, include_context=False, include_input=False)) from None
    try:
        await enregistrer_un_etablissement(organization_id, verifiee, auteur_de(user))
    except BaseClientIndisponible as erreur:
        raise _base_injoignable(erreur) from None
    return verifiee


@router.patch("/{identifiant}", response_model=Etablissement)
async def modifier_etablissement(
    identifiant: str,
    request: ModificationEtablissement,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """F4: change some fields of ONE fiche; the fields not sent keep their value (sentences,
    vocabulary, numbers, closure…). Answers with the fiche as saved. 404: unknown fiche of this
    organization."""
    return await _modifier_une_fiche(user, identifiant, request.model_dump(exclude_unset=True))


@router.post("/{identifiant}/etat", response_model=Etablissement)
async def fermer_ou_rouvrir_etablissement(
    identifiant: str,
    request: DemandeEtatFiche,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """F4: close (``etat_force: "FERME"``, with or without an end) or reopen (``etat_force: null``)
    ONE fiche. Nothing else of the fiche is touched."""
    return await _modifier_une_fiche(
        user,
        identifiant,
        {"etat_force": request.etat_force, "etat_force_jusqu_a": request.etat_force_jusqu_a},
    )


class DemandeEtablissementsDeLagent(BaseModel):
    workflow_id: int
    horaires_ouverture: str | None = Field(default=None, description="The agent's own hours, as on its screen.")
    adresse_etablissement: dict | None = Field(default=None, description="The agent's own address, as on its screen.")
    # [.mark] Chantier agents-specialises, lot 1 (F1).
    etablissement_id: str | None = Field(default=None, description="The fiche the agent chose, as on its screen.")


@router.post("/agent", response_model=EtablissementsDeLagent)
async def post_etablissements_de_lagent(
    request: DemandeEtablissementsDeLagent,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    organization_id = user.selected_organization_id
    workflow = await db_client.get_workflow(request.workflow_id, organization_id=organization_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        catalogue = await lire_etablissements_strict(organization_id)
    except BaseClientIndisponible:
        # A summary only: the mirror (last values known good) is enough to show it.
        from api.services.etablissements.stockage import lire_etablissements

        catalogue = await lire_etablissements(organization_id)
    except (ValidationError, ValueError):
        catalogue = CatalogueEtablissements()
    lignes = await db_client.lister_numeros_de_lorganisation(organization_id)
    numeros = [adresse for adresse, _l, agent, _n, _a in lignes if agent == request.workflow_id]

    from api.services.annonce.stockage import lire_annonce_ouverture
    from api.services.organization_preferences import get_organization_preferences

    preferences = await get_organization_preferences(organization_id)
    adresse_org = getattr(preferences, "adresse_etablissement", None)
    return etablissements_de_lagent(
        catalogue,
        numeros,
        {
            "horaires_ouverture": request.horaires_ouverture,
            "adresse_etablissement": request.adresse_etablissement,
            "etablissement_id": request.etablissement_id,
        },
        texte_adresse(adresse_org) if adresse_org else None,
        await lire_annonce_ouverture(organization_id),
    )


# --------------------------------------------------------------------------- #
# The catalogue of sentences (L2, E5): .mark creates, changes and places them here
# --------------------------------------------------------------------------- #

routeur_phrases = APIRouter(prefix="/organizations/phrases", tags=["organizations"])


@routeur_phrases.get("", response_model=CataloguePhrases)
async def get_phrases(user: UserModel = Depends(get_user_with_selected_organization)):
    """⛔ Strict: shown empty because unreadable, the next save would replace them."""
    try:
        return await lire_phrases_strict(user.selected_organization_id)
    except BaseClientIndisponible as erreur:
        raise _base_injoignable(erreur) from None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Sentences unreadable for the screen: {erreur!r}")
        raise HTTPException(
            status_code=500,
            detail="The sentences saved for this organization cannot be read. Nothing was changed; saving now would replace them.",
        ) from None


@routeur_phrases.put("", response_model=CataloguePhrases)
async def save_phrases(
    request: CataloguePhrases,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Replace the catalogue. Bounds and reserved names: 422 before writing."""
    try:
        return await enregistrer_phrases(user.selected_organization_id, request, auteur_de(user))
    except BaseClientIndisponible as erreur:
        raise _base_injoignable(erreur) from None
