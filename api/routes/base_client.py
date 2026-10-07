"""[.mark] The client's database on screen (chantier l-agent-travaille, L3, B4 to B6).

All routes are scoped to the user's selected organization; the database is the one
attached to THAT organization, never a name taken from the request but to attach it.

- ``GET  /organizations/base-client``              state: name, reachable, version, last write, retention, refusals
- ``PUT  /organizations/base-client``              attach (or detach) a database by its name
- ``POST /organizations/base-client/creer``        CREATE DATABASE + every migration, then attach
- ``POST /organizations/base-client/mettre-a-niveau`` apply the migrations past its version
- ``POST /organizations/base-client/resynchroniser``  rebuild the copy the calls read (test)
- ``PUT  /organizations/base-client/conservation`` change retention durations (bounded, logged)
- ``GET/PUT /organizations/equipe``                the team and the routing
- ``GET/PUT /organizations/planificateur``         the planner's rules (l-agent-collegue, L5)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.db.bases_clients.connexion import (
    BaseClientIndisponible,
    BaseDejaExistante,
    NomDeBaseInvalide,
    appliquer_migrations,
    assurer_compte_courant,
    connecter,
    connecter_proprietaire,
    creer_base,
    version_de,
)
from api.db.models import UserModel
from api.schemas.base_client import (
    Conservation,
    DemandeRattachement,
    Equipe,
    EtatBaseClient,
)
from api.schemas.planificateur import Planificateur
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement

router = APIRouter(prefix="/organizations/base-client", tags=["organizations"])
routeur_equipe = APIRouter(prefix="/organizations/equipe", tags=["organizations"])


def _refus(message: str, code: int = 422) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


async def _etat(organization_id: int) -> EtatBaseClient:
    from api.services.etablissements.copie import lire_copie_complete

    copie = await lire_copie_complete(organization_id)
    return await rattachement.etat(organization_id, refus=copie.refus)


@router.get("", response_model=EtatBaseClient)
async def get_base_client(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    return await _etat(user.selected_organization_id)


@router.put("", response_model=EtatBaseClient)
async def put_base_client(
    request: DemandeRattachement,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    organization_id = user.selected_organization_id
    if request.nom_base:
        try:
            await rattachement.verifier_libre(organization_id, request.nom_base)
        except rattachement.BaseDejaRattachee as erreur:
            raise _refus(str(erreur), 409) from None
        try:
            # The owner's connection (n° 317): it checks the schema and gives the connection
            # account its rights in this database.
            connexion = await connecter_proprietaire(request.nom_base)
        except (BaseClientIndisponible, NomDeBaseInvalide) as erreur:
            raise _refus(str(erreur)) from None
        try:
            version = await version_de(connexion)
            if not version or version < 3:
                raise _refus(
                    f"« {request.nom_base} » has no .mark schema: create it or upgrade it first."
                )
            try:
                await assurer_compte_courant(connexion, request.nom_base)
            except BaseClientIndisponible as erreur:
                raise _refus(str(erreur)) from None
        finally:
            await connexion.close()
    try:
        await rattachement.rattacher(organization_id, request.nom_base)
    except NomDeBaseInvalide as erreur:
        raise _refus(str(erreur)) from None
    await _apres_changement_de_source(organization_id)
    return await _etat(organization_id)


@router.post("/creer", response_model=EtatBaseClient)
async def post_creer(
    request: DemandeRattachement,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Create the database, apply every migration, attach it, and write into it the
    establishments and sentences already set on screen (the base becomes the source)."""
    organization_id = user.selected_organization_id
    if not request.nom_base:
        raise _refus("Give the database a name.")
    if await rattachement.nom_de_la_base(organization_id):
        raise _refus("A database is already attached: detach it first.")
    try:
        await rattachement.verifier_libre(organization_id, request.nom_base)
        await creer_base(request.nom_base)
    except (rattachement.BaseDejaRattachee, BaseDejaExistante) as erreur:
        raise _refus(str(erreur), 409) from None
    except (BaseClientIndisponible, NomDeBaseInvalide) as erreur:
        raise _refus(str(erreur)) from None
    await _verser_dans_la_base(
        organization_id, request.nom_base, rattachement.auteur_de(user)
    )
    await rattachement.rattacher(organization_id, request.nom_base)
    await _apres_changement_de_source(organization_id)
    return await _etat(organization_id)


@router.post("/mettre-a-niveau", response_model=EtatBaseClient)
async def post_mettre_a_niveau(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    organization_id = user.selected_organization_id
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise _refus("No client database is attached to this organization.")
    try:
        connexion = await connecter_proprietaire(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(str(erreur), 503) from None
    try:
        appliquees = await appliquer_migrations(connexion)
        await assurer_compte_courant(connexion, nom)
    except BaseClientIndisponible as erreur:
        raise _refus(str(erreur), 503) from None
    finally:
        await connexion.close()
    logger.info(
        f"[.mark] Client database of organization {organization_id} upgraded: {appliquees}"
    )
    return await _etat(organization_id)


@router.post("/resynchroniser", response_model=EtatBaseClient)
async def post_resynchroniser(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    from api.services.base_client.synchro import resynchroniser

    await resynchroniser(user.selected_organization_id)
    return await _etat(user.selected_organization_id)


@router.put("/conservation", response_model=EtatBaseClient)
async def put_conservation(
    request: list[Conservation],
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        await rattachement.regler_conservation(
            user.selected_organization_id, request, rattachement.auteur_de(user)
        )
    except BaseClientIndisponible as erreur:
        raise _refus(str(erreur)) from None
    except ValueError as erreur:
        raise _refus(str(erreur)) from None
    return await _etat(user.selected_organization_id)


async def _verser_dans_la_base(organization_id: int, nom: str, auteur: str) -> None:
    """What the organization already set on screen goes into its new database."""
    from api.db.bases_clients.referentiel import (
        ecrire_etablissements,
        ecrire_phrases,
    )
    from api.services.etablissements.stockage import (
        lire_etablissements_strict,
        lire_phrases_strict,
    )

    phrases = await lire_phrases_strict(organization_id)
    etablissements = await lire_etablissements_strict(organization_id)
    connexion = await connecter(nom)
    try:
        await ecrire_phrases(connexion, phrases, auteur)
        await ecrire_etablissements(connexion, etablissements, auteur)
    finally:
        await connexion.close()


async def _apres_changement_de_source(organization_id: int) -> None:
    from api.services.etablissements.copie import publier_copie

    await publier_copie(organization_id)


# --------------------------------------------------------------------------- #
# The team and the routing
# --------------------------------------------------------------------------- #


async def _connexion_de(organization_id: int):
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise _refus("Attach a client database first: the team lives there.", 409)
    try:
        return await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(str(erreur), 503) from None


@routeur_equipe.get("", response_model=Equipe)
async def get_equipe(user: UserModel = Depends(get_user_with_selected_organization)):
    from api.db.bases_clients.equipe import lire_equipe

    connexion = await _connexion_de(user.selected_organization_id)
    try:
        return await lire_equipe(connexion)
    finally:
        await connexion.close()


@routeur_equipe.put("", response_model=Equipe)
async def put_equipe(
    request: Equipe, user: UserModel = Depends(get_user_with_selected_organization)
):
    from api.db.bases_clients.equipe import (
        EtablissementInconnu,
        ecrire_equipe,
        lire_equipe,
    )

    connexion = await _connexion_de(user.selected_organization_id)
    try:
        try:
            await ecrire_equipe(connexion, request, rattachement.auteur_de(user))
        except EtablissementInconnu as erreur:
            raise _refus(str(erreur)) from None
        relue = await lire_equipe(connexion)
    finally:
        await connexion.close()
    # l-agent-collegue, C3: the team is in the copy the calls read; the next pick-up
    # hears this save without waiting for the notification (which follows anyway).
    await _apres_changement_de_source(user.selected_organization_id)
    return relue


# --------------------------------------------------------------------------- #
# l-agent-collegue, L5 (P2, P3): the planner's rules, in the client's database
# --------------------------------------------------------------------------- #

routeur_planificateur = APIRouter(prefix="/organizations/planificateur", tags=["organizations"])


@routeur_planificateur.get("", response_model=Planificateur)
async def get_planificateur(user: UserModel = Depends(get_user_with_selected_organization)):
    from api.db.bases_clients.planificateur import lire_planificateur

    connexion = await _connexion_de(user.selected_organization_id)
    try:
        return await lire_planificateur(connexion)
    finally:
        await connexion.close()


@routeur_planificateur.put("", response_model=Planificateur)
async def put_planificateur(
    request: Planificateur, user: UserModel = Depends(get_user_with_selected_organization)
):
    from api.db.bases_clients.planificateur import (
        ReferenceInconnue,
        ecrire_planificateur,
        lire_planificateur,
    )
    from api.services.pipecat.etat_ouverture import (
        HorairesInvalides,
        vers_expression_osm,
    )

    # The booking ranges are read like the opening hours: refused when SAVED, never at a call.
    for niveau, reglages in [("organization", request.reglages), *request.par_etablissement.items()]:
        if reglages.plages:
            try:
                vers_expression_osm(reglages.plages)
            except HorairesInvalides as erreur:
                raise _refus(f"Booking ranges ({niveau}): {erreur}") from None
    connexion = await _connexion_de(user.selected_organization_id)
    try:
        try:
            await ecrire_planificateur(connexion, request, rattachement.auteur_de(user))
        except ReferenceInconnue as erreur:
            raise _refus(str(erreur)) from None
        return await lire_planificateur(connexion)
    finally:
        await connexion.close()
