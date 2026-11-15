"""[.mark] Module Restauration, lot 12 : les routes des écrans du fork (Entreprise › « + Ajouter un module », Carte, Livraison, Réglages restaurant).

Des routes du FORK seulement : le portail écrit directement dans sa base (contrat portail ↔ fork § 1), il n'utilise pas celles-ci. Elles servent la
session d'un compte de l'équipe : lire = voir les conversations, écrire = ``agents.modifier`` (jamais par clé d'API, aucune ne porte ``pour_cle``).

- ``GET`` et ``PUT /restauration/module`` : le module est-il allumé, le (re)mettre ou le retirer (aucune donnée supprimée) ;
- ``GET /restauration/etablissements/{id}/carte``, ``PUT …/carte/etoile``, ``PUT …/carte/synonymes``, ``POST …/carte/synonymes/relus``, ``POST …/carte/import`` ;
- ``GET …/livraison`` (zones et communes trouvées), ``PUT …/livraison/zones`` ;
- ``GET`` et ``PUT …/reglages``, ``GET …/historique``.

Chaque route relit l'établissement contre la base de l'organisation de la requête (404 sinon, sans dire pourquoi) ; chaque écriture est journalisée
avec son auteur (déclencheurs de la 028) ; un identifiant ou un code inconnu est un 404/422 au format unique, jamais un texte interne.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from api.db.bases_clients import restauration_ecran as ecran
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.db.bases_clients.restauration_synonymes import (
    marquer_relus,
    proposer_les_synonymes,
)
from api.db.models import UserModel
from api.routes.restauration import _connexion_de_l_etablissement, _refus
from api.schemas.restauration_ecran import (
    CarteRendue,
    EtoileDemandee,
    HistoriqueRendu,
    ImportDemande,
    ImportRendu,
    LivraisonRendue,
    ModuleDemande,
    ModuleRendu,
    OkRendu,
    ReglagesChanges,
    ReglagesRendus,
    SynonymesDemandes,
    SynonymesRelus,
    ZonesDemandees,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement
from api.services.restauration import caisse as service_caisse
from api.services.restauration.prises.import_carte import importer_selon_la_portee
from api.services.restauration.prises.prise import (
    ContexteDePrise,
    capacites_de,
    prise_de_l_etablissement,
)
from api.services.restauration.synchro_caisse import importer_la_caisse

router = APIRouter(prefix="/restauration", tags=["restauration"])

TAILLE_MAX_CARTE = 2_000_000  # octets de la carte d'un fichier
RAYON_MAX_KM = 50.0


async def _connexion_de_l_organisation(organization_id: int):
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise _refus(409, "Attach a client database first: the establishments live there.")
    try:
        return await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(503, str(erreur)) from None


async def _module_rendu(connexion) -> ModuleRendu:
    etablissements = [{"id": r["id"], "nom": r["nom"]} for r in await connexion.fetch("SELECT id, nom FROM mark.site ORDER BY nom, id")]
    return ModuleRendu.model_validate({"actif": await ecran.module_allume(connexion), "etablissements": etablissements})


# --------------------------------------------------------------------------- le module


@router.get("/module", response_model=ModuleRendu)
async def get_module(user: UserModel = Depends(get_user_with_selected_organization)) -> ModuleRendu:
    """Is the Restaurant module on for this organization, and its establishments (the selector of the module tabs)."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_organisation(user.selected_organization_id)
    try:
        async with _schema_a_jour(connexion):
            return await _module_rendu(connexion)
    finally:
        await connexion.close()


@router.put("/module", response_model=ModuleRendu)
async def put_module(corps: ModuleDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> ModuleRendu:
    """Add the module (one settings row per establishment) or remove it. Removing deletes nothing: menu, rooms, orders and zones stay."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_organisation(user.selected_organization_id)
    try:
        async with _schema_a_jour(connexion):
            await ecran.poser_le_module(connexion, corps.actif, rattachement.auteur_de(user))
            return await _module_rendu(connexion)
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- la carte


@router.get("/etablissements/{etablissement_id}/carte", response_model=CarteRendue)
async def get_carte(etablissement_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> CarteRendue:
    """The menu of the establishment (exceptions applied, each object with its scope), its out-of-stock list and whether the till carries it."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            carte = await ecran.carte_pour_l_ecran(connexion, etablissement_id)
            fiche = await service_caisse.fiche_de_liaison(connexion, etablissement_id)
            carte["lecture_seule"] = fiche["etat"] == "ok" and fiche["capacites"]["carte"] == "lue"
            carte["prise"] = fiche["prise"]
            return CarteRendue.model_validate(carte)
    finally:
        await connexion.close()


@router.put("/etablissements/{etablissement_id}/carte/etoile", response_model=OkRendu)
async def put_etoile(etablissement_id: int, corps: EtoileDemandee, user: UserModel = Depends(get_user_with_selected_organization)) -> OkRendu:
    """« Most requested » (star) on a product: an overlay, kept when the till re-reads the menu. Always possible."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            if not await ecran.poser_l_etoile(connexion, etablissement_id, corps.ref, corps.etoile, rattachement.auteur_de(user)):
                raise _refus(404, "Product not found in the menu of this establishment.")
    finally:
        await connexion.close()
    return OkRendu(ok=True)


@router.put("/etablissements/{etablissement_id}/carte/synonymes", response_model=OkRendu)
async def put_synonymes(etablissement_id: int, corps: SynonymesDemandes, user: UserModel = Depends(get_user_with_selected_organization)) -> OkRendu:
    """The synonyms of a product (replaced, active at once). An overlay: always possible, whoever keeps the menu."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            if not await ecran.poser_les_synonymes(connexion, etablissement_id, corps.ref, corps.synonymes, rattachement.auteur_de(user)):
                raise _refus(404, "Product not found in the menu of this establishment.")
    finally:
        await connexion.close()
    return OkRendu(ok=True)


@router.post("/etablissements/{etablissement_id}/carte/synonymes/relus", response_model=OkRendu)
async def post_synonymes_relus(etablissement_id: int, corps: SynonymesRelus, user: UserModel = Depends(get_user_with_selected_organization)) -> OkRendu:
    """Approve the synonyms proposed at import for a product (as they are, or corrected): they become active."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            relus = await marquer_relus(connexion, etablissement_id, corps.ref, corps.synonymes, auteur=rattachement.auteur_de(user))
    finally:
        await connexion.close()
    if not relus:
        raise _refus(404, "Nothing to review for this product.")
    return OkRendu(ok=True)


@router.post("/etablissements/{etablissement_id}/carte/import", response_model=ImportRendu)
async def post_import(etablissement_id: int, corps: ImportDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> ImportRendu:
    """Import the menu: from the till (the socket reads it now) or from a file in the common format. Nothing a person wrote is overwritten
    (synonyms, stars, lines kept by hand); the new synonyms come back « to review »."""
    from api.routes.base_client import _schema_a_jour

    if corps.source == "fichier":
        if not corps.carte:
            raise _refus(422, "Invalid value: carte.")
        if len(json.dumps(corps.carte, default=str)) > TAILLE_MAX_CARTE:
            raise _refus(413, "The menu file is too large.")
    organization_id = user.selected_organization_id
    connexion = await _connexion_de_l_etablissement(organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            if corps.source == "caisse":
                fiche = await service_caisse.fiche_de_liaison(connexion, etablissement_id)
                if fiche["etat"] == "aucune" or capacites_de(fiche["prise"]).carte != "lue":
                    raise _refus(409, "No till that can be read is plugged in to this establishment.")
                prise = await prise_de_l_etablissement(ContexteDePrise(connexion, organization_id, etablissement_id, await rattachement.nom_de_la_base(organization_id)))
                bilan = (await importer_la_caisse(prise, connexion, organization_id, etablissement_id)).get("carte")
                if bilan is None:
                    raise _refus(502, "The till did not answer: nothing was imported.")
            else:
                try:
                    bilan = await importer_selon_la_portee(connexion, etablissement_id, corps.carte or {}, "import")
                except (ValueError, KeyError, TypeError):
                    raise _refus(422, "The file is not a menu in the common format. Nothing was imported.") from None
            propose = await proposer_les_synonymes(connexion, etablissement_id, auteur=rattachement.auteur_de(user))
    finally:
        await connexion.close()
    return ImportRendu(
        ajoutes=bilan["ajoutes"], changes=bilan["changes"], retires=bilan["retires"], conserves=bilan["conserves"],
        sans_code_caisse=len(bilan["sans_code_caisse"]), synonymes_proposes=propose["proposes"],
    )


# --------------------------------------------------------------------------- la livraison


@router.get("/etablissements/{etablissement_id}/livraison", response_model=LivraisonRendue)
async def get_livraison(
    etablissement_id: int,
    rayon_km: float = Query(default=12.0, gt=0, le=RAYON_MAX_KM, description="Chercher les communes jusqu'à cette distance."),
    user: UserModel = Depends(get_user_with_selected_organization),
) -> LivraisonRendue:
    """The delivery zones of the establishment and the towns found within ``rayon_km`` (distance, zone, refusal)."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            return LivraisonRendue.model_validate(await ecran.livraison_pour_l_ecran(connexion, etablissement_id, rayon_km))
    finally:
        await connexion.close()


@router.put("/etablissements/{etablissement_id}/livraison/zones", response_model=LivraisonRendue)
async def put_zones(etablissement_id: int, corps: ZonesDemandees, user: UserModel = Depends(get_user_with_selected_organization)) -> LivraisonRendue:
    """Replace the zones of the establishment (five at most, in circle order). Written by the fork, never by the till (the portal stays master of zones)."""
    from api.routes.base_client import _schema_a_jour

    for z in corps.zones:
        if z.cercle_km is None:
            raise _refus(422, "Invalid value: cercle_km.")
    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            try:
                await ecran.ecrire_les_zones(connexion, etablissement_id, [z.model_dump() for z in corps.zones], rattachement.auteur_de(user))
            except ecran.ZoneInconnue:
                raise _refus(404, "Zone not found.") from None
            return LivraisonRendue.model_validate(await ecran.livraison_pour_l_ecran(connexion, etablissement_id, 12.0))
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- les réglages


_OBJETS_ET_CAPACITE = (
    ("carte", lambda c: c.carte == "lue"), ("ruptures", lambda c: c.ruptures == "lues"), ("horaires", lambda c: c.horaires),
    ("remises", lambda c: c.remises_lues), ("clients", lambda c: c.clients_lus),
)


async def _reglages_rendus(connexion, etablissement_id: int) -> ReglagesRendus:
    rendu = await ecran.reglages_pour_l_ecran(connexion, etablissement_id)
    fiche = await service_caisse.fiche_de_liaison(connexion, etablissement_id)
    capacites = capacites_de(fiche["prise"])
    branchee = fiche["etat"] == "ok"
    rendu["sources"] = [{"objet": objet, "prise_sait": bool(sait(capacites)), "mode": "caisse" if branchee and sait(capacites) else "ici"} for objet, sait in _OBJETS_ET_CAPACITE]
    rendu["prise"] = fiche["prise"]
    rendu["caisse_porte_l_etat"] = fiche["etat_caisse"] is not None
    return ReglagesRendus.model_validate(rendu)


@router.get("/etablissements/{etablissement_id}/reglages", response_model=ReglagesRendus)
async def get_reglages(etablissement_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> ReglagesRendus:
    """Everything the « Restaurant settings » tab shows for an establishment: order types, payment, sending, thresholds, sources, hours."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            return await _reglages_rendus(connexion, etablissement_id)
    finally:
        await connexion.close()


@router.put("/etablissements/{etablissement_id}/reglages", response_model=ReglagesRendus)
async def put_reglages(etablissement_id: int, corps: ReglagesChanges, user: UserModel = Depends(get_user_with_selected_organization)) -> ReglagesRendus:
    """Apply what changed (only the fields given). The waiting time and the pause of a type go through the time chip (``PUT …/temps``)."""
    from api.routes.base_client import _schema_a_jour

    changements = corps.model_dump(exclude_unset=True, exclude_none=False)
    if corps.reglage is not None:
        changements["reglage"] = corps.reglage.model_dump(exclude_unset=True)
    if corps.types is not None:
        changements["types"] = [t.model_dump(exclude_unset=True) for t in corps.types]
    if corps.recurrents is not None:
        changements["recurrents"] = [r.model_dump() for r in corps.recurrents]
    for cle in ("envoi_heure_changee", "seuils", "imprimante"):
        sous = getattr(corps, cle)
        if sous is not None:
            changements[cle] = sous.model_dump(exclude_unset=True)
    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            if changements.get("seuils") and await liaison_db.liaison(connexion, etablissement_id) is None:
                raise _refus(409, "No till is plugged in: the thresholds do not apply.")
            if changements.get("imprimante") and await liaison_db.imprimante(connexion, etablissement_id) is None:
                raise _refus(409, "No printer is plugged in to this establishment.")
            try:
                await ecran.ecrire_les_reglages(connexion, etablissement_id, {k: v for k, v in changements.items() if v is not None}, rattachement.auteur_de(user))
            except ecran.ZoneInconnue:
                raise _refus(404, "Row not found.") from None
            return await _reglages_rendus(connexion, etablissement_id)
    finally:
        await connexion.close()


@router.get("/etablissements/{etablissement_id}/historique", response_model=HistoriqueRendu)
async def get_historique(
    etablissement_id: int,
    limite: int = Query(default=30, ge=1, le=100),
    avant: int | None = Query(default=None, ge=1, description="Les changements plus anciens que cet identifiant."),
    user: UserModel = Depends(get_user_with_selected_organization),
) -> HistoriqueRendu:
    """The change log of the establishment (before, after, source, who, when), newest first, paginated."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            lignes = await ecran.historique_des_changements(connexion, etablissement_id, limite + 1, avant)
    finally:
        await connexion.close()
    suite = lignes[limite - 1]["id"] if len(lignes) > limite else None
    return HistoriqueRendu.model_validate({"lignes": lignes[:limite], "suite": suite})

