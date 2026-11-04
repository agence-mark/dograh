"""[.mark] U10 / S3 : ce que le widget public envoie quand la conversation est finie, ou n'a pas pu commencer.

* ``POST /public/embed/avis/{session_token}`` : l'avis du visiteur (une fois, après la fin de la conversation). Même
  contrôle de session et de domaine que le reste du widget. L'avis entre dans la base du client ; si la conversation
  n'y est pas encore (l'après-appel tourne), il attend sur le run et entre avec elle.
* ``POST /public/embed/rappel/{cle}`` : le plafond du mois est atteint, le visiteur laisse ses coordonnées : une
  demande « à rappeler » entre dans la base du client. Refusée tant que le plafond n'est pas atteint, limitée par
  adresse (l'adresse n'est pas gardée).
* ``POST /public/embed/evenement`` : un compteur anonyme (le rond s'est affiché, s'est ouvert). Ni cookie, ni
  identifiant, ni adresse IP lue.

Ces trois routes n'ont pas de compte : le jeton de session, la clé publique du site et le domaine d'origine font foi,
et le registre des permissions les exempte avec ces limites (voir ``registre_routes.py``).
Les erreurs restent génériques : cette surface est joignable depuis n'importe quelle page.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response
from loguru import logger

from api.db import db_client
from api.routes.public_embed import _allow_embed_origin, get_request_origin
from api.schemas.site_conversations import (
    AvisPublic,
    AvisRecu,
    EvenementPublic,
    RappelPublic,
)
from api.services.site_mark import chemins as lib_chemins
from api.services.site_mark import config_site, plafond
from api.services.site_mark.conversations import (
    avis_deja_donne,
    avis_ecrit,
    avis_sans_donnees_personnelles,
)
from api.services.site_mark.adresse import adresse_du_visiteur
from api.services.site_mark.limite_ip import autoriser_evenement, autoriser_rappel
from api.services.site_mark.reglages import ReglagesMark
from api.services.workflow.embed_session_service import (
    EmbedSessionNotFoundError,
    EmbedSessionValidationError,
    EmbedTokenNotFoundError,
    resolve_embed_session,
    validate_embed_origin,
)
from api.services.workflow.run_creation import published_definition

router = APIRouter(prefix="/public/embed")

# Au-delà, un compteur du jour ne bouge plus : un script qui boucle ne gonfle pas les chiffres sans fin.
PLAFOND_EVENEMENTS_PAR_JOUR = 1_000_000


# --------------------------------------------------------------------------- #
# La base du client : écrire, ou dire proprement qu'on ne peut pas
# --------------------------------------------------------------------------- #


async def _base_rattachee(organization_id: int) -> bool:
    from api.services.base_client.rattachement import nom_de_la_base

    return bool(await nom_de_la_base(organization_id))


async def _ecrire_dans_la_base(organization_id: int, operation):
    """Ouvre la connexion de l'organisation, joue ``operation(connexion)``, ferme. ``None`` si l'organisation n'a pas de
    base rattachée ou si elle ne répond pas (rien n'est levé vers la page publique)."""
    from api.db.bases_clients.connexion import connecter
    from api.services.base_client.rattachement import nom_de_la_base

    nom = await nom_de_la_base(organization_id)
    if not nom:
        return None
    try:
        connexion = await connecter(nom)
    except Exception as erreur:  # noqa: BLE001 -- une base qui ne répond pas ne casse pas la page publique
        logger.warning(f"[.mark] Client database of organization {organization_id} not reached: {type(erreur).__name__}")
        return None
    try:
        return await operation(connexion)
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[.mark] Write to the client database of organization {organization_id} failed: {erreur!r}")
        return None
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# L'avis
# --------------------------------------------------------------------------- #


@router.post("/avis/{session_token}", response_model=AvisRecu)
async def post_avis(session_token: str, corps: AvisPublic, request: Request, response: Response) -> AvisRecu:
    origin = get_request_origin(request)
    try:
        session, jeton = await resolve_embed_session(session_token, origin)
    except (EmbedSessionNotFoundError, EmbedTokenNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except EmbedSessionValidationError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if origin:
        _allow_embed_origin(response, origin)

    if corps.rappel_demande and not (corps.contact and corps.contact.a_de_quoi_rappeler()):
        raise HTTPException(status_code=422, detail="A phone number or a mail is needed to be called back")
    if session.workflow_run_id is None:
        raise HTTPException(status_code=404, detail="No conversation for this session")
    run = await db_client.get_workflow_run(session.workflow_run_id, organization_id=jeton.organization_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No conversation for this session")
    if not run.is_completed:
        raise HTTPException(
            status_code=409, detail={"code": "conversation_not_finished", "message": "The conversation is not over yet."}
        )
    if avis_deja_donne(run):
        raise HTTPException(
            status_code=409, detail={"code": "review_already_given", "message": "A review was already given."}
        )

    # Revue serveur, mineur 3 : la place de l'avis se prend sous verrou ; deux envois simultanés, un seul passe.
    if not await db_client.reserver_avis(run.id, jeton.organization_id):
        raise HTTPException(
            status_code=409, detail={"code": "review_already_given", "message": "A review was already given."}
        )
    try:
        avis = corps.en_dict()
        # Entre dans la base si la conversation y est ; sinon attend sur le run et entre avec elle (recevoir_appel).
        from api.db.bases_clients import apres_appel as sql

        resultat = await _ecrire_dans_la_base(
            jeton.organization_id, lambda connexion: sql.noter_avis(connexion, run.id, avis)
        )
        ecrit = bool(resultat and resultat.get("ecrit"))
        embed = dict((run.annotations or {}).get("embed") or {})
        # Écrit dans la base : plus rien d'autre que le fait qu'il a été donné (aucune coordonnée gardée dans Dograh). En
        # attente de sa conversation : entier, réduit par l'après-appel dès ``recevoir_appel``. Sans base rattachée : ni
        # coordonnées ni texte libre, rien ne les recevra (revue serveur M6).
        if ecrit:
            embed["avis"] = avis_ecrit()
        elif await _base_rattachee(jeton.organization_id):
            embed["avis"] = avis
        else:
            embed["avis"] = avis_sans_donnees_personnelles(avis)
        await db_client.update_workflow_run(run.id, annotations={"embed": embed})
    except Exception:
        await db_client.rendre_avis(run.id, jeton.organization_id)
        raise
    return AvisRecu()


# --------------------------------------------------------------------------- #
# La demande de rappel (plafond atteint)
# --------------------------------------------------------------------------- #


@router.post("/rappel/{cle}", response_model=AvisRecu)
async def post_rappel(cle: str, corps: RappelPublic, request: Request, response: Response) -> AvisRecu:
    origin = get_request_origin(request)
    site = await db_client.lire_site_par_cle(cle)
    if site is None:
        raise HTTPException(status_code=404, detail="Invalid site key")
    if not validate_embed_origin(origin, site.allowed_domains or []):
        raise HTTPException(status_code=403, detail=f"Domain not allowed: {origin}")
    try:
        chemin = lib_chemins.normaliser(corps.chemin)
    except lib_chemins.CheminInvalide:
        raise HTTPException(status_code=400, detail="Invalid path")
    if origin:
        _allow_embed_origin(response, origin)
    if not corps.contact.a_de_quoi_rappeler():
        raise HTTPException(status_code=422, detail="A phone number or a mail is needed to be called back")

    jeton = await config_site.jeton_pour(db_client, site, chemin)
    if jeton is None or jeton.organization_id != site.organization_id:
        raise HTTPException(status_code=404, detail="No agent for this page")
    if not await plafond.est_atteint(jeton.id, ReglagesMark.depuis(jeton.reglages_mark)):
        raise HTTPException(
            status_code=409, detail={"code": "cap_not_reached", "message": "The agent is available: no call-back needed."}
        )
    if not await autoriser_rappel(jeton.id, adresse_du_visiteur(request)):
        raise HTTPException(
            status_code=429,
            detail={"code": "address_rate_limited", "message": "Too many requests from this address."},
        )

    # L'établissement : la fiche de l'agent, ou aucun (jamais « le premier »).
    fiche = None
    workflow = await db_client.get_workflow(jeton.workflow_id, organization_id=jeton.organization_id)
    if workflow is not None:
        definition = published_definition(workflow)
        reglages = getattr(definition, "workflow_configurations", None) or {}
        valeur = reglages.get("etablissement_id") if isinstance(reglages, dict) else None
        fiche = valeur.strip() if isinstance(valeur, str) and valeur.strip() else None

    from api.db.bases_clients import apres_appel as sql

    demande = {
        "etablissement": fiche,
        "chemin": chemin,
        "message": corps.message,
        "contact": corps.contact.model_dump(mode="json", exclude_none=True),
    }
    resultat = await _ecrire_dans_la_base(
        jeton.organization_id, lambda connexion: sql.demander_rappel_site(connexion, demande)
    )
    if resultat is None:
        raise HTTPException(
            status_code=503, detail={"code": "unavailable", "message": "Please try again a little later."}
        )
    return AvisRecu()


# --------------------------------------------------------------------------- #
# L'événement anonyme
# --------------------------------------------------------------------------- #


@router.post("/evenement", response_model=AvisRecu)
async def post_evenement(corps: EvenementPublic, request: Request, response: Response) -> AvisRecu:
    """+1 au compteur du jour de l'agent. Aucune donnée du visiteur n'est gardée : ni adresse (seule son empreinte salée sert à la limite), ni agent utilisateur."""
    origin = get_request_origin(request)
    jeton = None
    domaines: list = []
    if corps.cle:
        site = await db_client.lire_site_par_cle(corps.cle)
        if site is None:
            raise HTTPException(status_code=404, detail="Invalid site key")
        domaines = list(site.allowed_domains or [])
        try:
            jeton = await config_site.jeton_pour(db_client, site, corps.chemin)
        except lib_chemins.CheminInvalide:
            raise HTTPException(status_code=400, detail="Invalid path")
    elif corps.token:
        jeton = await db_client.get_embed_token_by_token(corps.token)
        if jeton is not None and config_site.jeton_valide(jeton):
            domaines = await config_site.domaines_du_jeton(db_client, jeton)
        else:
            jeton = None
    else:
        raise HTTPException(status_code=422, detail="A site key or a token is needed")
    if not validate_embed_origin(origin, domaines):
        raise HTTPException(status_code=403, detail=f"Domain not allowed: {origin}")
    if origin:
        _allow_embed_origin(response, origin)
    if jeton is None:
        raise HTTPException(status_code=404, detail="No agent for this page")
    # [.mark] Revue serveur M7 : au-delà de la limite par jeton et par adresse, refus SILENCIEUX (le compteur ne bouge plus,
    # le widget n'a rien à gérer). L'adresse n'est lue que pour l'empreinte du limiteur, jamais gardée.
    if not await autoriser_evenement(jeton.id, adresse_du_visiteur(request)):
        return AvisRecu()
    await db_client.compter_evenement(
        jeton.id, datetime.now(UTC).date(), corps.evenement, PLAFOND_EVENEMENTS_PAR_JOUR
    )
    return AvisRecu()
