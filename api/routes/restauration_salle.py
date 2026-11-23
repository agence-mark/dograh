"""[.mark] Module Restauration, lot 13 : les routes des écrans du fork Salle, Remises et Envois (F6, F7, M7).

Des routes du FORK seulement : le portail écrit directement dans sa base (contrat portail ↔ fork § 1). Elles servent la session d'un compte de l'équipe :
lire = voir les conversations, écrire = ``agents.modifier`` (jamais par clé d'API). Les réservations elles-mêmes (créer, changer, annuler) passent par les routes
du lot 8, qui revérifient la place ; ici : le plan, les créneaux, les durées, les règles et le statut « arrivée ».

- ``GET …/salle`` : le plan, les créneaux, les durées, les règles et les réservations d'aujourd'hui à ``jours`` jours ;
- ``PUT …/salle/plan`` · ``PUT …/salle/creneaux`` · ``POST …/reservations/{id}/statut`` ;
- ``GET`` et ``POST …/remises``, ``PUT`` et ``DELETE …/remises/{id}``, ``POST …/remises/{id}/etat`` ;
- ``GET`` et ``PUT …/envois`` : les SMS après une action, éteints par défaut.

Chaque route relit l'établissement contre la base de l'organisation de la requête (404 sinon, sans dire pourquoi) ; chaque écriture est journalisée avec son auteur.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Query

from api.db.bases_clients import restauration_remise_ecran as remises_db
from api.db.bases_clients import restauration_salle_ecran as salle_db
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_reglage import reglages_du_module
from api.db.models import UserModel
from api.routes.restauration import _connexion_de_l_etablissement, _refus
from api.schemas.restauration_salle import (
    CommandesRecentes,
    CreneauxDemandes,
    EnvoisChanges,
    EnvoisRendus,
    EtatRemiseDemande,
    OkSalle,
    PlanDemande,
    RemiseDemandee,
    RemisesRendues,
    SalleRendue,
    StatutDemande,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.caisse.prises.prise import capacites_de

router = APIRouter(prefix="/restauration", tags=["restauration"])

_CHEMIN = "/etablissements/{etablissement_id}"
_REFUS_DE_REMISE = {"introuvable": (404, "Row not found."), "lecture_seule": (409, "This discount is kept in the till: change it there."),
                    "transition": (409, "This change of state is not possible."), "trop_nombreuses": (409, "Too many discounts.")}


async def _avec_la_base(user: UserModel, etablissement_id: int, geste):
    """Ouvre la base de CETTE organisation (schéma à jour), relit l'établissement, joue ``geste(connexion, auteur)`` et ferme."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            return await geste(connexion, rattachement.auteur_de(user))
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- la salle


@router.get(_CHEMIN + "/salle", response_model=SalleRendue)
async def get_salle(
    etablissement_id: int = Path(ge=1, le=10**12), jours: int = Query(default=30, ge=1, le=120), user: UserModel = Depends(get_user_with_selected_organization)
) -> SalleRendue:
    """The floor plan, bookable slots, meal lengths, rules and the bookings from today on (``jours`` days) of the establishment."""

    async def geste(connexion, _auteur):
        return SalleRendue.model_validate(await salle_db.salle_pour_l_ecran(connexion, etablissement_id, jours))

    return await _avec_la_base(user, etablissement_id, geste)


@router.put(_CHEMIN + "/salle/plan", response_model=SalleRendue)
async def put_plan(corps: PlanDemande, etablissement_id: int = Path(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)) -> SalleRendue:
    """Replace the floor plan (rooms and tables). A table held by a booking to come is refused (409), nothing is written."""

    async def geste(connexion, auteur):
        try:
            await salle_db.ecrire_le_plan(connexion, etablissement_id, [s.model_dump() for s in corps.salles], auteur)
        except salle_db.PlanRefuse as refus:
            if refus.code == "table_reservee":
                raise _refus(409, "A table of the plan is held by a booking to come: move the booking first.") from None
            raise _refus(404, "Row not found.") from None
        return SalleRendue.model_validate(await salle_db.salle_pour_l_ecran(connexion, etablissement_id, 30))

    return await _avec_la_base(user, etablissement_id, geste)


@router.put(_CHEMIN + "/salle/creneaux", response_model=SalleRendue)
async def put_creneaux(corps: CreneauxDemandes, etablissement_id: int = Path(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)) -> SalleRendue:
    """Replace the bookable slots and the meal lengths (when given) and change the booking rules (only the fields given)."""
    changements = corps.model_dump(exclude_unset=True)
    if not changements:
        raise _refus(422, "Invalid value: nothing to change.")
    if corps.regles is not None:
        changements["regles"] = corps.regles.model_dump(exclude_unset=True)

    async def geste(connexion, auteur):
        await salle_db.ecrire_les_creneaux(connexion, etablissement_id, changements, auteur)
        return SalleRendue.model_validate(await salle_db.salle_pour_l_ecran(connexion, etablissement_id, 30))

    return await _avec_la_base(user, etablissement_id, geste)


@router.post(_CHEMIN + "/reservations/{reservation_id}/statut", response_model=OkSalle)
async def post_statut(
    corps: StatutDemande, etablissement_id: int = Path(ge=1, le=10**12), reservation_id: uuid.UUID = Path(), user: UserModel = Depends(get_user_with_selected_organization)
) -> OkSalle:
    """Mark a booking arrived (``honoree``), absent, or confirmed again. A cancelled booking no longer changes (404)."""

    async def geste(connexion, auteur):
        return await salle_db.poser_le_statut(connexion, etablissement_id, str(reservation_id), corps.statut, auteur)

    if not await _avec_la_base(user, etablissement_id, geste):
        raise _refus(404, "Row not found.")
    await flux.emettre(user.selected_organization_id, etablissement_id, "reservation.changee", {"reservation_id": str(reservation_id)})
    return OkSalle(ok=True)


@router.get(_CHEMIN + "/commandes-recentes", response_model=CommandesRecentes)
async def get_commandes_recentes(
    etablissement_id: int = Path(ge=1, le=10**12), limite: int = Query(default=10, ge=1, le=50), user: UserModel = Depends(get_user_with_selected_organization)
) -> CommandesRecentes:
    """The latest orders of the establishment (the till sheet shows them: number, time, total, status, reference at the till)."""

    async def geste(connexion, _auteur):
        return CommandesRecentes.model_validate({"commandes": await salle_db.dernieres_commandes(connexion, etablissement_id, limite)})

    return await _avec_la_base(user, etablissement_id, geste)


# --------------------------------------------------------------------------- les remises


async def _lecture_seule(connexion, etablissement_id: int) -> tuple[bool, str]:
    liaison = await liaison_db.liaison(connexion, etablissement_id)
    if liaison is None:
        return False, "portail"
    ici = (await reglages_du_module(connexion, etablissement_id))["sources"].get("remises") == "ici"
    return capacites_de(liaison["prise"]).remises_lues and not ici, liaison["prise"]


async def _remises_rendues(connexion, etablissement_id: int) -> RemisesRendues:
    seule, prise = await _lecture_seule(connexion, etablissement_id)
    return RemisesRendues.model_validate({"remises": await remises_db.remises_pour_l_ecran(connexion, etablissement_id), "lecture_seule": seule, "prise": prise})


@router.get(_CHEMIN + "/remises", response_model=RemisesRendues)
async def get_remises(etablissement_id: int = Path(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)) -> RemisesRendues:
    """The discounts of the establishment with what each did on the kept orders; read-only when the till carries them."""

    async def geste(connexion, _auteur):
        return await _remises_rendues(connexion, etablissement_id)

    return await _avec_la_base(user, etablissement_id, geste)


async def _ecrire_remise(user: UserModel, etablissement_id: int, corps: RemiseDemandee, remise_id: int | None) -> RemisesRendues:
    champs = corps.model_dump()

    async def geste(connexion, auteur):
        seule, _ = await _lecture_seule(connexion, etablissement_id)
        if seule:
            raise _refus(409, _REFUS_DE_REMISE["lecture_seule"][1])
        try:
            await remises_db.ecrire_une_remise(connexion, etablissement_id, champs, auteur, remise_id)
        except remises_db.RemiseRefusee as refus:
            raise _refus(*_REFUS_DE_REMISE[refus.code]) from None
        return await _remises_rendues(connexion, etablissement_id)

    return await _avec_la_base(user, etablissement_id, geste)


@router.post(_CHEMIN + "/remises", response_model=RemisesRendues, status_code=201)
async def post_remise(corps: RemiseDemandee, etablissement_id: int = Path(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)) -> RemisesRendues:
    """Create a discount (draft or active). The exact effect is computed by the counter when an order is taken."""
    return await _ecrire_remise(user, etablissement_id, corps, None)


@router.put(_CHEMIN + "/remises/{remise_id}", response_model=RemisesRendues)
async def put_remise(
    corps: RemiseDemandee, etablissement_id: int = Path(ge=1, le=10**12), remise_id: int = Path(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)
) -> RemisesRendues:
    """Change a discount of the screen (not one kept in the till; not an ended one)."""
    return await _ecrire_remise(user, etablissement_id, corps, remise_id)


@router.post(_CHEMIN + "/remises/{remise_id}/etat", response_model=RemisesRendues)
async def post_etat_remise(
    corps: EtatRemiseDemande, etablissement_id: int = Path(ge=1, le=10**12), remise_id: int = Path(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)
) -> RemisesRendues:
    """Switch on, pause, resume or end a discount (draft > active > paused or ended; an ended one never comes back)."""

    async def geste(connexion, auteur):
        try:
            await remises_db.changer_l_etat(connexion, etablissement_id, remise_id, corps.etat, auteur)
        except remises_db.RemiseRefusee as refus:
            raise _refus(*_REFUS_DE_REMISE[refus.code]) from None
        return await _remises_rendues(connexion, etablissement_id)

    return await _avec_la_base(user, etablissement_id, geste)


@router.delete(_CHEMIN + "/remises/{remise_id}", response_model=RemisesRendues)
async def delete_remise(
    etablissement_id: int = Path(ge=1, le=10**12), remise_id: int = Path(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)
) -> RemisesRendues:
    """Delete a discount of the screen; the change history keeps it and the orders already taken keep their discount."""

    async def geste(connexion, auteur):
        try:
            await remises_db.supprimer_une_remise(connexion, etablissement_id, remise_id, auteur)
        except remises_db.RemiseRefusee as refus:
            raise _refus(*_REFUS_DE_REMISE[refus.code]) from None
        return await _remises_rendues(connexion, etablissement_id)

    return await _avec_la_base(user, etablissement_id, geste)


# --------------------------------------------------------------------------- les envois


@router.get(_CHEMIN + "/envois", response_model=EnvoisRendus)
async def get_envois(etablissement_id: int = Path(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)) -> EnvoisRendus:
    """The text messages sent after an action (order, booking, menu, review): switched off by default, one place to set them."""

    async def geste(connexion, _auteur):
        return EnvoisRendus.model_validate({"envois": await remises_db.envois_pour_l_ecran(connexion, etablissement_id)})

    return await _avec_la_base(user, etablissement_id, geste)


@router.put(_CHEMIN + "/envois", response_model=EnvoisRendus)
async def put_envois(corps: EnvoisChanges, etablissement_id: int = Path(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)) -> EnvoisRendus:
    """Set the text and the switch of each message given (only those)."""

    async def geste(connexion, auteur):
        await remises_db.ecrire_les_envois(connexion, etablissement_id, [e.model_dump(exclude_unset=True) for e in corps.envois], auteur)
        return EnvoisRendus.model_validate({"envois": await remises_db.envois_pour_l_ecran(connexion, etablissement_id)})

    return await _avec_la_base(user, etablissement_id, geste)


# --------------------------------------------------------------------------- le modèle de réglages Restauration (F14)

# Ce que « Partir du modèle Restauration » pose sur un agent neuf (lot 13, M8) : la conversion des nombres dictés, la commande sur catalogue explicite, et les
# garde-fous des outils du lot 24, éteints partout ailleurs. Une seule source : l'écran lit cette liste, il n'en recopie aucune valeur.
REGLAGES_RESTAURATION: dict[str, object] = {
    "conversion_nombres_transcription": True,
    "recherche_dans_une_liste": True,
    "commande_sur_catalogue": True,
    "commande_ordre_impose": True,
    "commande_relecture_deux_temps": True,
    "commande_vente_en_plus": True,
    "commande_notes_libres": True,
    "garde_arguments_controles": True,
    "garde_echec_repete": True,
    "garde_nom_d_outil": True,
    "garde_une_nouvelle_tentative": True,
    "garde_ecritures_en_file": True,
    "garde_chiffre_sans_source": True,
    "garde_fait_avant_outil": True,
    "garde_confirmation_apres_reponse": True,
}
# Les kits d'outils que le modèle reçoit avec lui (lot 11), par leur nom ; un kit absent de l'organisation est simplement ignoré par l'écran.
KITS_RESTAURATION: tuple[str, ...] = ("Commande", "Réservation", "Envois")


@router.get("/modele-reglages")
async def get_modele_reglages(user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, object]:
    """The settings model « Restaurant » for a new agent: the keys to set and the tool kits it brings. Read-only, the same for everyone."""
    return {"reglages": REGLAGES_RESTAURATION, "kits": list(KITS_RESTAURATION)}
