from fastapi import HTTPException
from fastmcp.server.dependencies import get_http_headers
from opentelemetry import trace

from api.db.models import UserModel
from api.services.auth.depends import _handle_api_key_auth


# [.mark] builder-agent-vocal, lot 1 : le moteur du builder appelle les outils de ce serveur COMME DES FONCTIONS
# (« un moteur, deux portes »). Il pose l'utilisateur déjà authentifié par la route ``/builder`` dans
# ``UTILISATEUR_DIRECT`` : seul du code du serveur peut le poser, aucun en-tête de requête ne le peut. Vide (défaut) :
# comportement de l'amont.
from api.services.builder.identite import UTILISATEUR_DIRECT  # noqa: E402


async def authenticate_mcp_request(outil: str | None = None) -> UserModel:
    """Resolve the authenticated Dograh user for an MCP tool invocation.

    Accepts either `X-API-Key: <key>` or `Authorization: Bearer <key>`,
    reusing the API-key flow from `api.services.auth.depends`.

    Tags the currently-active OTel span with the resolved organization
    and user identifiers. `_OrgRoutingExporter` reads `dograh.org_id`
    at export time to dispatch the span to the right Langfuse project;
    the `langfuse.user.id` / `langfuse.session.id` attributes make the
    span filterable in the Langfuse UI.
    """
    direct = UTILISATEUR_DIRECT.get()
    if direct is not None:
        return direct

    # FastMCP strips Authorization by default unless explicitly included.
    # Preserve it here so Bearer API keys work for MCP tool invocations.
    headers = get_http_headers(include={"authorization"})
    api_key = headers.get("x-api-key")
    if not api_key:
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            api_key = auth.split(" ", 1)[1].strip()
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key — send X-API-Key or Authorization: Bearer <key>",
        )
    user = await _handle_api_key_auth(api_key)
    # [.mark] Revue de contrôle, point 3 (B1) : la porte MCP est un accès par clé comme les autres, sans rôle d'équipe.
    # ``par_porte_mcp`` ne sert qu'à l'exemption explicite « clé du Labo » de l'écriture en bibliothèque
    # (``bibliotheque.droits.exiger_l_equipe_au_labo``), en attendant la décision d'Evan (18).
    user.par_cle_api = True
    user.par_porte_mcp = True
    # [.mark] Clôture, É36 : les versions créées par cette porte sont « par la clé » (son nom), jamais par un auteur du corps de la requête.
    from api.db import auteur_de_version

    auteur_de_version.poser_depuis(user)
    # [.mark] Revue SA-9 (2) : une clé à rôle sans aucun droit effectif (créateur retiré, bloqué, espace fermé) n'ouvre aucun outil, lecture comprise.
    from api.services.equipe_mark.droits_effectifs import exiger_une_cle_a_role_vivante

    await exiger_une_cle_a_role_vivante(user)
    if outil is not None:
        # [.mark] Clôture, lot A (D10, D21) : la lecture des agents, outils et du builder est fermée à une clé de client sans rôle.
        from api.services.equipe_mark.droits_mcp import LECTURE_AGENTS, PERMISSION_DES_OUTILS_MCP

        if PERMISSION_DES_OUTILS_MCP.get(outil) == LECTURE_AGENTS:
            from api.services.equipe_mark.droits_effectifs import lecture_fermee_a_la_cle_de_client

            if lecture_fermee_a_la_cle_de_client(user):
                raise HTTPException(status_code=403, detail="Not available to an API key of a client")

    span = trace.get_current_span()
    if span.is_recording():
        org_id = user.selected_organization_id
        # Intentionally NOT `dograh.org_id` — that attribute triggers the
        # per-org Langfuse routing for pipeline spans, and MCP traffic
        # should land in the default (developer-facing) project only.
        # Exposed under `mcp.org_id` for Langfuse UI filtering without
        # affecting the router.
        span.set_attribute("mcp.org_id", str(org_id))
        span.set_attribute("mcp.user_id", str(user.id))
        span.set_attribute("langfuse.user.id", str(user.id))

    return user


async def authenticate_mcp_write(outil: str) -> UserModel:
    """Comme ``authenticate_mcp_request`` pour un outil qui ÉCRIT : la permission de l'outil vient de la table unique (``droits_mcp``).

    Clôture, lot A (D21) : une clé PORTÉE PAR UN RÔLE écrit si ce rôle (borné par son créateur) porte la permission, exactement comme à l'écran.
    Une clé sans rôle garde la règle de la liste fermée (17a) : une clé de client n'écrit jamais ; seule la clé du Labo, créée par un membre de
    l'équipe (Claude Code de .mark), écrit. Le moteur du builder (appel direct, sans clé) n'est pas concerné."""
    from api.services.equipe_mark.droits_mcp import PERMISSION_DES_OUTILS_MCP

    permission = PERMISSION_DES_OUTILS_MCP[outil]
    user = await authenticate_mcp_request()
    if getattr(user, "par_porte_mcp", False):
        if getattr(user, "cle_api_role_id", None) is not None:
            from api.services.equipe_mark.droits_effectifs import permissions_de

            if permission not in await permissions_de(user):
                raise HTTPException(status_code=403, detail=f"Permission required: {permission} (not carried by the role of this API key)")
        else:
            from api.services.builder.bibliotheque import droits
            from api.services.builder.constantes import organisation_bibliotheque

            # SA-9 (3) : bornée par la permission ACTUELLE du créateur pour CET outil (pas seulement son appartenance à l'équipe).
            if not await droits._cle_du_labo_par_mcp(user, organisation_bibliotheque(), permission):
                raise HTTPException(status_code=403, detail="This API key cannot write through MCP: only the Labo key of the .mark team does")
    return user
