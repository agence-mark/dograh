"""[.mark] U10 / S2 : les sites intégrés et les agents de site, pour le portail et l'écran de Dograh.

* ``/organizations/sites`` : créer, lister, régler un site (sa clé publique, ses domaines) ; le script est unique par site.
* ``/organizations/agents-site/{id}`` : l'emplacement d'un agent (site, chemins), son canal, son apparence (schéma),
  ses réglages .mark (domaines, plafonds, durée, limite par adresse), « Couleur de mon site ».

Toutes les routes lisent et écrivent DANS l'organisation de l'utilisateur ou de la clé d'API : l'agent, le site ou le
jeton d'une autre organisation répond comme s'il n'existait pas (404). Les écritures exigent ``agents.modifier`` (registre
des routes) ; le portail décide lui-même qui, chez le client, a le droit de personnaliser (règle du 22/10).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from loguru import logger

from api.constants import BACKEND_API_ENDPOINT, ENVIRONMENT, UI_APP_URL
from api.db import db_client
from api.db.models import UserModel
from api.db.site_client import CheminDejaPris, mois_de
from api.schemas.apparence_widget import ApparenceWidget
from api.schemas.site_conversations import EvenementJour
from api.schemas.site_widget import (
    ApparenceLue,
    CouleurDuSite,
    DemandeAffichage,
    DemandeCanal,
    DemandeEmplacement,
    DemandeLireSite,
    DemandeReglageSite,
    DemandeReglagesMark,
    DemandeSite,
    EmplacementLu,
    ReglagesMarkLus,
    SiteLu,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.call_concurrency.rate_limiter import rate_limiter
from api.services.site_mark import canal as lib_canal
from api.services.site_mark import chemins as lib_chemins
from api.services.site_mark import config_site, lecture_site
from api.services.site_mark.reglages import ReglagesMark
from api.services.workflow.run_creation import published_definition

router = APIRouter(prefix="/organizations", tags=["organizations"])


# ---------------------------------------------------------------------- aides
def _script(site) -> str:
    base = str(UI_APP_URL).rstrip("/")
    return (
        "<!-- Widget .mark : un seul script pour tout le site -->\n"
        f'<script async src="{base}/embed/dograh-widget.js?site={site.cle}'
        f'&environment={ENVIRONMENT}&apiEndpoint={BACKEND_API_ENDPOINT}"></script>'
    )


def _site_lu(site) -> SiteLu:
    return SiteLu(
        id=site.id,
        cle=site.cle,
        nom=site.nom or "",
        allowed_domains=list(site.allowed_domains or []),
        dernier_chargement=site.dernier_chargement.isoformat() if site.dernier_chargement else None,
        script=_script(site),
    )


def _domaines_propres(domaines: list[str]) -> list[str]:
    """Les domaines nettoyés. Revue serveur, mineur 4 : au moins un domaine, jamais une liste vide (un site sans domaine
    s'ouvrirait à toute origine)."""
    propres = []
    for d in domaines:
        d = str(d).strip().lower()
        if not d or len(d) > 255 or any(c in d for c in " \t\r\n<>\"'"):
            raise HTTPException(status_code=422, detail=f"Invalid domain: {d[:60]!r}")
        if d not in propres:
            propres.append(d)
    if not propres:
        raise HTTPException(status_code=422, detail="At least one domain is needed")
    return propres


async def _agent(workflow_id: int, user: UserModel):
    """L'agent, sous l'organisation de l'appelant ; l'agent d'une autre organisation n'existe pas."""
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return workflow


def _configurations_publiees(workflow) -> dict:
    definition = published_definition(workflow)
    return dict(getattr(definition, "workflow_configurations", None) or {})


async def _canal_de_lagent(workflow, organization_id: int, *, brouillon: bool = False) -> str:
    """Le canal d'un agent : celui de sa version publiée ; avec ``brouillon``, celui que le brouillon pose déjà (l'intention
    en cours : on règle le canal AVANT de publier). Un spécialisé prend celui de son principal."""

    async def configurations(w) -> dict:
        configs = _configurations_publiees(w)
        if brouillon:
            ebauche = await db_client.get_draft_version(w.id)
            if ebauche is not None and lib_canal.CLE_CANAL in (ebauche.workflow_configurations or {}):
                configs = {**configs, lib_canal.CLE_CANAL: ebauche.workflow_configurations[lib_canal.CLE_CANAL]}
        return configs

    configs = await configurations(workflow)
    principal_id = configs.get("agent_principal_id")
    principal_configs = None
    if isinstance(principal_id, int) and not isinstance(principal_id, bool):
        principal = await db_client.get_workflow(principal_id, organization_id=organization_id)
        if principal is not None:
            principal_configs = await configurations(principal)
    return lib_canal.canal_de(configs, principal_configs)


async def _jeton(workflow_id: int, organization_id: int):
    jetons = await db_client.get_embed_tokens_by_workflow(workflow_id, organization_id, active_only=False)
    return jetons[0] if jetons else None


async def _jeton_ou_404(workflow_id: int, user: UserModel):
    await _agent(workflow_id, user)
    jeton = await _jeton(workflow_id, user.selected_organization_id)
    if jeton is None:
        raise HTTPException(status_code=404, detail="This agent has no widget yet")
    return jeton


async def _outils_du_brouillon_ou_publie(workflow, organization_id: int) -> list:
    from api.services.groupe.agents_servis import outils_des_etapes

    brouillon = await db_client.get_draft_version(workflow.id)
    graphe = brouillon.workflow_json if brouillon else getattr(published_definition(workflow), "workflow_json", None)
    uuids = outils_des_etapes(graphe)
    if not uuids:
        return []
    return list(await db_client.get_tools_by_uuids(uuids, organization_id))


# ---------------------------------------------------------------------- sites
@router.post("/sites", response_model=SiteLu)
async def creer_un_site(demande: DemandeSite, user: UserModel = Depends(get_user_with_selected_organization)):
    site = await db_client.creer_site(
        user.selected_organization_id, demande.nom.strip(), _domaines_propres(demande.allowed_domains)
    )
    return _site_lu(site)


@router.get("/sites", response_model=list[SiteLu])
async def lister_les_sites(user: UserModel = Depends(get_user_with_selected_organization)):
    return [_site_lu(s) for s in await db_client.lister_sites(user.selected_organization_id)]


@router.put("/sites/{site_id}", response_model=SiteLu)
async def regler_un_site(
    site_id: int, demande: DemandeReglageSite, user: UserModel = Depends(get_user_with_selected_organization)
):
    site = await db_client.regler_site(
        site_id,
        user.selected_organization_id,
        nom=demande.nom.strip() if demande.nom is not None else None,
        allowed_domains=_domaines_propres(demande.allowed_domains) if demande.allowed_domains is not None else None,
    )
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    config_site.vider_le_cache(site.cle)
    return _site_lu(site)


@router.post("/sites/{site_id}/regenerer-cle", response_model=SiteLu)
async def regenerer_la_cle_du_site(site_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """Nouvelle clé pour le site (V5, « Régénérer le jeton ») : l'ancien script est refusé, le nouveau est rendu."""
    ancien = await db_client.lire_site(site_id, user.selected_organization_id)
    if ancien is None:
        raise HTTPException(status_code=404, detail="Site not found")
    ancienne_cle = ancien.cle
    site = await db_client.regenerer_cle_du_site(site_id, user.selected_organization_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    config_site.vider_le_cache(ancienne_cle)
    config_site.vider_le_cache(site.cle)
    logger.info(f"site {site_id} (organisation {user.selected_organization_id}) : clé régénérée")
    return _site_lu(site)


# ---------------------------------------------------------------------- canal et emplacement
async def _emplacement_lu(workflow, organization_id: int) -> EmplacementLu:
    jeton = await _jeton(workflow.id, organization_id)
    canal = await _canal_de_lagent(workflow, organization_id, brouillon=True)
    definition = published_definition(workflow)
    lu = EmplacementLu(
        workflow_id=workflow.id,
        canal=canal,
        agent_nom=workflow.name or "",
        version_publiee=getattr(definition, "version_number", None),
    )
    if jeton is None:
        return lu
    lu.embed_token_id = jeton.id
    lu.widget_actif = bool(jeton.is_active)
    lignes = (await db_client.lire_emplacements(organization_id, [workflow.id])).get(workflow.id)
    if lignes:
        lu.site_id, lu.site_cle = lignes["site_id"], lignes["site_cle"]
        lu.chemins, lu.dernier_chargement = lignes["chemins"], lignes["dernier_chargement"]
    return lu


@router.get("/agents-site/evenements", response_model=list[EvenementJour])
async def get_evenements_des_agents_de_site(
    du: date | None = None,
    au: date | None = None,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """[.mark] S3 : les compteurs anonymes (rond affiché, rond ouvert) par jour et par agent de site, des agents de
    CETTE organisation seulement. Par défaut les 30 derniers jours ; au plus 366 jours demandés d'un coup."""
    fin = au or datetime.now(UTC).date()
    debut = du or fin - timedelta(days=29)
    if debut > fin or (fin - debut).days > 366:
        raise HTTPException(status_code=422, detail="Invalid period")
    lignes = await db_client.lire_evenements(user.selected_organization_id, debut, fin)
    return [
        EvenementJour(workflow_id=l["workflow_id"], jour=l["jour"].isoformat(), affiche=l["affiche"], ouvert=l["ouvert"])
        for l in lignes
    ]


@router.get("/agents-site/{workflow_id}", response_model=EmplacementLu)
async def lire_l_emplacement(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    workflow = await _agent(workflow_id, user)
    return await _emplacement_lu(workflow, user.selected_organization_id)


@router.put("/agents-site/{workflow_id}/canal", response_model=EmplacementLu)
async def regler_le_canal(
    workflow_id: int, demande: DemandeCanal, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Pose le canal de l'agent dans son brouillon (D153). Un agent de site n'a ni numéro ni outil de transfert d'appel."""
    workflow = await _agent(workflow_id, user)
    organisation = user.selected_organization_id
    if demande.canal == lib_canal.SITE:
        refus = lib_canal.refus_transfert_sur_agent_de_site(
            lib_canal.SITE, await _outils_du_brouillon_ou_publie(workflow, organisation)
        )
        if refus:
            raise HTTPException(status_code=409, detail=refus)
        numeros = [
            n
            for n in await db_client.lister_numeros_de_lorganisation(organisation)
            if n[2] == workflow_id and n[4]
        ]
        if numeros and lib_canal.refus_numero_sur_agent(lib_canal.SITE):
            raise HTTPException(
                status_code=409,
                detail="This agent still answers a phone number: detach the number before making it a site agent.",
            )
    else:
        jeton = await _jeton(workflow_id, organisation)
        if jeton is not None and jeton.is_active:
            raise HTTPException(
                status_code=409, detail="This agent still has an active widget: deactivate it first."
            )
    brouillon = await db_client.get_draft_version(workflow_id)
    base = dict(
        (brouillon.workflow_configurations if brouillon else None)
        or _configurations_publiees(workflow)
        or {}
    )
    base[lib_canal.CLE_CANAL] = demande.canal
    await db_client.update_workflow(
        workflow_id, None, None, None, base, user_id=user.id, organization_id=organisation
    )
    return await _emplacement_lu(await _agent(workflow_id, user), organisation)


@router.put("/agents-site/{workflow_id}/emplacement", response_model=EmplacementLu)
async def poser_l_emplacement(
    workflow_id: int, demande: DemandeEmplacement, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Pose l'agent sur un site et des chemins. Deux agents sur le même chemin du site : refusé (D175)."""
    workflow = await _agent(workflow_id, user)
    organisation = user.selected_organization_id
    refus = lib_canal.refus_jeton_sur_agent(await _canal_de_lagent(workflow, organisation, brouillon=True))
    jeton = await _jeton(workflow_id, organisation)
    # Zéro perte : un agent qui a déjà son jeton le garde ; on n'en crée pas pour un agent téléphonique.
    if jeton is None and refus:
        raise HTTPException(status_code=409, detail=refus)
    try:
        propres = [lib_chemins.normaliser(c) for c in demande.chemins]
    except lib_chemins.CheminInvalide as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    if await db_client.lire_site(demande.site_id, organisation) is None:
        raise HTTPException(status_code=404, detail="Site not found")
    if jeton is None:
        jeton = await db_client.create_embed_token(
            workflow_id=workflow_id,
            organization_id=organisation,
            created_by=user.id,
            allowed_domains=None,
            settings={},
            usage_limit=None,
            expires_at=None,
        )
    try:
        await db_client.poser_emplacement(organisation, jeton.id, demande.site_id, propres)
    except CheminDejaPris as erreur:
        raise HTTPException(
            status_code=409, detail=f"The path « {erreur.chemin} » is already served by another agent of this site."
        ) from None
    except LookupError:
        raise HTTPException(status_code=404, detail="Site not found") from None
    site = await db_client.lire_site(demande.site_id, organisation)
    if site is not None:
        config_site.vider_le_cache(site.cle)
    return await _emplacement_lu(workflow, organisation)


@router.put("/agents-site/{workflow_id}/affichage", response_model=EmplacementLu)
async def regler_l_affichage(
    workflow_id: int, demande: DemandeAffichage, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Affiché ou coupé sur le site (V5) : coupé, le widget disparaît au prochain chargement de page, le script reste."""
    workflow = await _agent(workflow_id, user)
    organisation = user.selected_organization_id
    jeton = await _jeton_ou_404(workflow_id, user)
    maj = await db_client.regler_jeton_mark(jeton.id, organisation, is_active=demande.actif)
    if maj is None:
        raise HTTPException(status_code=404, detail="This agent has no widget yet")
    if jeton.site_id:
        site = await db_client.lire_site(jeton.site_id, organisation)
        if site is not None:
            config_site.vider_le_cache(site.cle)
    return await _emplacement_lu(workflow, organisation)


# ---------------------------------------------------------------------- apparence
@router.get("/agents-site/{workflow_id}/apparence", response_model=ApparenceLue)
async def lire_l_apparence(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    jeton = await _jeton_ou_404(workflow_id, user)
    apparence = config_site.apparence_du_jeton(jeton)
    return ApparenceLue(apparence=apparence, couleurs=apparence.couleurs_resolues())


@router.put("/agents-site/{workflow_id}/apparence", response_model=ApparenceLue)
async def regler_l_apparence(
    workflow_id: int, apparence: ApparenceWidget, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Remplace l'apparence (D160). Un corps vide revient au bleu .mark. Les autres réglages du jeton ne bougent pas."""
    jeton = await _jeton_ou_404(workflow_id, user)
    reglages = {**(jeton.settings or {}), "apparence": apparence.model_dump(mode="json")}
    await db_client.update_embed_token(jeton.id, user.selected_organization_id, settings=reglages)
    if jeton.site_id:
        site = await db_client.lire_site(jeton.site_id, user.selected_organization_id)
        if site is not None:
            config_site.vider_le_cache(site.cle)
    return ApparenceLue(apparence=apparence, couleurs=apparence.couleurs_resolues())


# ---------------------------------------------------------------------- réglages .mark
async def _reglages_lus(jeton) -> ReglagesMarkLus:
    reglages = ReglagesMark.depuis(jeton.reglages_mark)
    usage = await db_client.lire_usage_mensuel(jeton.id, mois_de())
    return ReglagesMarkLus(
        **reglages.en_json(),
        # Les domaines du jeton, sinon ceux de son site : ce que le script du site vérifie vraiment (V5).
        allowed_domains=[str(d) for d in await config_site.domaines_du_jeton(db_client, jeton)],
        conversations_ce_mois=usage.conversations if usage else 0,
        minutes_ce_mois=(usage.secondes // 60) if usage else 0,
        jeton_expire_le=jeton.expires_at.date().isoformat() if jeton.expires_at else None,
    )


@router.get("/agents-site/{workflow_id}/reglages", response_model=ReglagesMarkLus)
async def lire_les_reglages(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _reglages_lus(await _jeton_ou_404(workflow_id, user))


@router.put("/agents-site/{workflow_id}/reglages", response_model=ReglagesMarkLus)
async def regler_les_reglages(
    workflow_id: int, demande: DemandeReglagesMark, user: UserModel = Depends(get_user_with_selected_organization)
):
    jeton = await _jeton_ou_404(workflow_id, user)
    champs = demande.model_dump(exclude_none=True)
    domaines = champs.pop("allowed_domains", None)
    expire = champs.pop("jeton_expire_le", None)
    valeurs = {**ReglagesMark.depuis(jeton.reglages_mark).en_json(), **champs}
    modifs: dict = {"reglages_mark": ReglagesMark.depuis(valeurs).en_json()}
    if domaines is not None:
        modifs["allowed_domains"] = _domaines_propres(domaines)
    if expire is not None:
        if expire.strip() == "":
            modifs["sans_expiration"] = True
        else:
            try:
                fin = date.fromisoformat(expire.strip())
            except ValueError:
                raise HTTPException(status_code=422, detail="The end date is written YYYY-MM-DD") from None
            if fin < datetime.now(UTC).date():
                raise HTTPException(status_code=422, detail="The end date cannot be in the past")
            modifs["expires_at"] = datetime(fin.year, fin.month, fin.day, 23, 59, 59, tzinfo=UTC)
    maj = await db_client.regler_jeton_mark(jeton.id, user.selected_organization_id, **modifs)
    if maj is None:
        raise HTTPException(status_code=404, detail="This agent has no widget yet")
    return await _reglages_lus(maj)


# ---------------------------------------------------------------------- « Couleur de mon site » (D203)
@router.post("/agents-site/{workflow_id}/lire-site", response_model=CouleurDuSite)
async def lire_la_couleur_du_site(
    workflow_id: int, demande: DemandeLireSite, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Lit la page d'accueil du client (domaines déjà autorisés seulement) : sa couleur et son logo. Rien n'est gardé."""
    jeton = await _jeton_ou_404(workflow_id, user)
    domaines = await config_site.domaines_du_jeton(db_client, jeton)
    reels = [d for d in domaines if str(d).strip() not in ("", "*")]
    adresse = (demande.adresse or "").strip()
    if not adresse:
        if not reels:
            raise HTTPException(status_code=422, detail="Add an allowed domain first: the site is read there only.")
        hote = reels[0].lstrip("*.")
        adresse = f"https://{hote}/"
    if not await rate_limiter.acquire_token(
        user.selected_organization_id,
        lecture_site.LECTURES_PAR_HEURE,
        scope_key=f"lire_site:{user.selected_organization_id}",
        window_seconds=3600.0,
    ):
        raise HTTPException(status_code=429, detail="Ten site readings per hour at most.")
    try:
        lue = await lecture_site.lire_couleur_du_site(
            adresse, reels, resoudre=lecture_site.resoudre_dns, ouvrir=lecture_site.ouvrir_httpx
        )
    except lecture_site.LectureRefusee as refus:
        raise HTTPException(status_code=422, detail={"code": refus.code, "message": str(refus)}) from None
    return CouleurDuSite(couleur=lue.couleur, logo_url=lue.logo_url, sources=lue.sources)
