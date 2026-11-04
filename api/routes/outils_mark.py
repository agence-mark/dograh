"""[.mark] U3 sexies (E73 à E75) : les routes nouvelles d'Outils et d'Intégrations.

Chaque route lit l'organisation du compte (jamais celle de la requête). Les permissions viennent du registre des routes
(`/tools` et `/credentials` y ont déjà leur règle de domaine). Ce routeur est monté AVANT ceux de `/tools` et de
`/credentials` : `/tools/statistiques` ne doit pas être lu comme un identifiant d'outil.

Aucun secret n'est renvoyé : ni valeur d'identifiant, ni valeur d'en-tête secret (aperçu masqué).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.enums import ToolCategory
from api.schemas.tool import EnteteDeRequete
from api.services.auth.depends import get_user
from api.services.bibliotheque_cles import fournisseur_de
from api.services.builder.cerveau.marque import est_la_cle_du_cerveau
from api.services.outils_mark import essai as essai_mark
from api.services.outils_mark import identifiants as identifiants_mark
from api.services.outils_mark import mcp as mcp_mark
from api.services.outils_mark import statistiques as statistiques_mark
from api.services.workflow.tools.mcp_tool import namespace_function_name
from api.utils.url_security import refuser_adresse_de_metadonnees, validate_user_configured_service_url

router = APIRouter(tags=["outils-mark"])


def _organisation(user: UserModel) -> int:
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected for the user")
    return user.selected_organization_id


async def _outil(tool_uuid: str, organisation: int):
    outil = await db_client.get_tool_by_uuid(tool_uuid, organisation, include_archived=True)
    if outil is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return outil


# ---- Statistiques (point 5) ------------------------------------------------------------------------------------------


class ResumeOutil(BaseModel):
    executions: int
    reussies: int
    echecs: int
    reussite: int | None
    duree_mediane_ms: int | None
    nb_agents: int
    jours: int


@router.get("/tools/statistiques")
async def statistiques_des_outils(user: UserModel = Depends(get_user)) -> dict[str, ResumeOutil]:
    """Le résumé de chaque outil actif de l'organisation (30 jours), pour le tableau des outils."""
    organisation = _organisation(user)
    outils = await db_client.get_tools_for_organization(organisation)
    return {k: ResumeOutil(**v) for k, v in (await statistiques_mark.pour_les_outils(organisation, outils)).items()}


class ExecutionVue(BaseModel):
    run_id: int
    workflow_id: int
    date: str | None
    outil_mcp: str | None
    reussie: bool
    duree_ms: int | None
    etape: str | None


class AgentVu(BaseModel):
    agent_id: int
    agent: str
    etapes: list[str]


class StatistiquesOutil(BaseModel):
    executions: int
    reussies: int
    echecs: int
    reussite: int | None
    duree_mediane_ms: int | None
    jours: int
    page: int
    par_page: int
    total_executions: int
    dernieres_executions: list[ExecutionVue]
    agents: list[AgentVu]


@router.get("/tools/{tool_uuid}/statistiques")
async def statistiques_d_un_outil(
    tool_uuid: str, page: int = 0, user: UserModel = Depends(get_user)
) -> StatistiquesOutil:
    organisation = _organisation(user)
    outil = await _outil(tool_uuid, organisation)
    return StatistiquesOutil(**await statistiques_mark.pour_un_outil(organisation, outil, page=max(0, page)))


# ---- Essai (point 4) ------------------------------------------------------------------------------------------------


class DemandeEssai(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["direct", "simule", "compte_de_test"] = "direct"
    outil_mcp: str | None = Field(default=None, max_length=200, description="For an MCP server: the tool to try.")


class VerdictEssai(BaseModel):
    reussi: bool
    mode: str
    ecrit: bool
    duree_ms: int
    message: str
    donnees: Any | None = None
    statut_http: int | None = None
    copies: dict[str, Any] = Field(default_factory=dict)
    simulee: bool = False
    requete: dict[str, Any] | None = None
    manquants: list[str] = Field(default_factory=list)


@router.post("/tools/{tool_uuid}/essai")
async def essayer_un_outil(
    tool_uuid: str, demande: DemandeEssai, user: UserModel = Depends(get_user)
) -> VerdictEssai:
    """Essaie un outil de n'importe quel type. Un outil qui écrit exige ``simule`` ou ``compte_de_test``."""
    organisation = _organisation(user)
    outil = await _outil(tool_uuid, organisation)
    try:
        verdict = await essai_mark.essayer(outil, organisation, demande.arguments, demande.mode, outil_mcp=demande.outil_mcp)
    except essai_mark.ErreurEssai as e:
        raise HTTPException(status_code=e.statut, detail=e.message) from e
    if essai_mark.categorie_de(outil) in (ToolCategory.HTTP_API.value, ToolCategory.INTEGRATION.value, ToolCategory.MCP.value):
        await db_client.update_tool(
            tool_uuid=tool_uuid,
            organization_id=organisation,
            definition=essai_mark.noter_le_dernier_essai(outil.definition, verdict),
        )
    return VerdictEssai(**{k: v for k, v in verdict.items() if k in VerdictEssai.model_fields})


class PremierEssai(BaseModel):
    valide_par: str
    valide_le: str
    mode: str | None = None


@router.post("/tools/{tool_uuid}/premier-essai")
async def valider_le_premier_essai(tool_uuid: str, user: UserModel = Depends(get_user)) -> PremierEssai:
    """Une personne valide le premier essai de l'outil (refusé sans essai réussi)."""
    organisation = _organisation(user)
    outil = await _outil(tool_uuid, organisation)
    try:
        definition = essai_mark.valider_le_premier_essai(outil.definition, str(user.provider_id or user.id))
    except essai_mark.ErreurEssai as e:
        raise HTTPException(status_code=e.statut, detail=e.message) from e
    await db_client.update_tool(tool_uuid=tool_uuid, organization_id=organisation, definition=definition)
    return PremierEssai(**definition["config"]["premier_essai"])


# ---- Serveurs MCP (point 6) -----------------------------------------------------------------------------------------


class DemandeTestMcp(BaseModel):
    url: str = Field(max_length=2000)
    transport: Literal["streamable_http", "sse"] = "streamable_http"
    timeout_secs: int = Field(default=30, ge=1, le=120)
    sse_read_timeout_secs: int = Field(default=300, ge=1, le=900)
    credential_uuid: str | None = None
    en_tetes_ext: list[EnteteDeRequete] = Field(default_factory=list, max_length=30)
    # Lot 14 (J-3) : le serveur déjà enregistré qu'on teste ; son état et la date de l'essai sont alors gardés.
    outil_uuid: str | None = Field(default=None, max_length=64)


class OutilDecouvert(BaseModel):
    name: str
    description: str = ""


class ResultatTestMcp(BaseModel):
    ok: bool
    outils: list[OutilDecouvert] = Field(default_factory=list)
    erreur: str | None = None


@router.post("/tools/mcp/tester")
async def tester_la_connexion_mcp(demande: DemandeTestMcp, user: UserModel = Depends(get_user)) -> ResultatTestMcp:
    """« Tester la connexion » : découvre les outils du serveur avant de l'enregistrer. Rien n'est écrit, sauf, pour un
    serveur déjà enregistré (``outil_uuid``), l'état et la date de cet essai (colonnes « État » et « Rafraîchi »)."""
    organisation = _organisation(user)
    serveur = None
    if demande.outil_uuid:
        serveur = await _outil(demande.outil_uuid, organisation)
        if essai_mark.categorie_de(serveur) != ToolCategory.MCP.value:
            raise HTTPException(status_code=422, detail="This tool is not an MCP server")
    if not demande.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="The address must start with http:// or https://")
    # Revue serveur, mineur 1 : le test fait sortir le serveur vers l'adresse donnée ; mêmes garde-fous que les autres adresses de
    # service (hôte interne refusé en hébergé) et, en tout mode, jamais l'adresse de métadonnées du nuage. Message générique.
    try:
        refuser_adresse_de_metadonnees(demande.url, field_name="url")
        validate_user_configured_service_url(demande.url, field_name="url")
    except ValueError:
        raise HTTPException(status_code=422, detail="This address is not allowed") from None
    credential = None
    references = [demande.credential_uuid] if demande.credential_uuid else []
    references += [e.identifiant_uuid for e in demande.en_tetes_ext if e.sorte == "secret" and e.identifiant_uuid]
    for uuid in references:
        trouve = await db_client.get_credential_by_uuid(uuid, organisation)
        if trouve is None:
            raise HTTPException(status_code=404, detail="Credential not found")
        if est_la_cle_du_cerveau(trouve):
            raise HTTPException(status_code=403, detail="This credential is reserved")
        if uuid == demande.credential_uuid:
            credential = trouve
    resultat = await mcp_mark.tester_la_connexion(
        url=demande.url,
        transport=demande.transport,
        timeout_secs=demande.timeout_secs,
        sse_read_timeout_secs=demande.sse_read_timeout_secs,
        credential=credential,
        entrees_en_tetes=[e.model_dump() for e in demande.en_tetes_ext],
        organization_id=organisation,
    )
    if serveur is not None:
        await db_client.update_tool(
            tool_uuid=serveur.tool_uuid,
            organization_id=organisation,
            definition=essai_mark.noter_le_test_de_connexion(serveur.definition, bool(resultat.get("ok"))),
        )
    return ResultatTestMcp(**resultat)


class OutilMcpVu(BaseModel):
    serveur_uuid: str
    serveur: str
    nom: str
    description: str
    fonction: str
    reglage: Literal["autorise", "confirmer", "desactive"]


@router.get("/tools/mcp/decouverts")
async def outils_decouverts_des_serveurs(user: UserModel = Depends(get_user)) -> list[OutilMcpVu]:
    """Les outils découverts de chaque serveur MCP actif, avec leur réglage : ils apparaissent dans Outils, marqués MCP."""
    organisation = _organisation(user)
    sortie: list[OutilMcpVu] = []
    for serveur in await db_client.get_tools_for_organization(organisation, category=ToolCategory.MCP.value):
        config = (serveur.definition or {}).get("config") or {}
        reglages = config.get("reglages_outils") or {}
        for d in config.get("discovered_tools") or []:
            if not isinstance(d, dict) or not d.get("name"):
                continue
            sortie.append(
                OutilMcpVu(
                    serveur_uuid=serveur.tool_uuid,
                    serveur=serveur.name,
                    nom=d["name"],
                    description=str(d.get("description") or ""),
                    fonction=namespace_function_name(serveur.name, d["name"], fallback=serveur.tool_uuid[:8]),
                    reglage=reglages.get(d["name"], "autorise"),
                )
            )
    return sortie


# ---- Identifiants (point 7) -----------------------------------------------------------------------------------------


class UtilisePar(BaseModel):
    tool_uuid: str
    nom: str
    categorie: str


@router.get("/credentials/utilisation")
async def utilisation_des_identifiants(user: UserModel = Depends(get_user)) -> dict[str, list[UtilisePar]]:
    """Pour chaque identifiant utilisé : les outils de l'organisation qui s'y appuient."""
    organisation = _organisation(user)
    return {
        k: [UtilisePar(**o) for o in v] for k, v in (await identifiants_mark.utilisation(organisation)).items()
    }


class NouvelleValeur(BaseModel):
    valeur: str = Field(min_length=1, max_length=4000)


class ValeurRemplacee(BaseModel):
    uuid: str
    remplacee: bool = True


@router.put("/credentials/{credential_uuid}/valeur")
async def remplacer_la_valeur(
    credential_uuid: str, demande: NouvelleValeur, user: UserModel = Depends(get_user)
) -> ValeurRemplacee:
    """Remplace la valeur secrète d'un identifiant sans jamais l'afficher ni la renvoyer."""
    organisation = _organisation(user)
    credential = await db_client.get_credential_by_uuid(credential_uuid, organisation)
    if credential is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    if fournisseur_de(credential) is not None or est_la_cle_du_cerveau(credential):
        raise HTTPException(status_code=409, detail="This key is managed in « Keys »")
    try:
        donnees = identifiants_mark.remplacer_la_valeur(
            str(credential.credential_type), dict(credential.credential_data or {}), demande.valeur
        )
    except identifiants_mark.RemplacementImpossible as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await db_client.update_credential(
        credential_uuid=credential_uuid, organization_id=organisation, credential_data=donnees
    )
    return ValeurRemplacee(uuid=credential_uuid)
