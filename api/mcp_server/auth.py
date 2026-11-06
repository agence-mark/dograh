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


async def authenticate_mcp_request() -> UserModel:
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


async def authenticate_mcp_write() -> UserModel:
    """Comme ``authenticate_mcp_request`` pour un outil qui ÉCRIT (partie 3, 17a : liste fermée des clés).

    Une clé d'API d'un client n'écrit jamais par la porte MCP : le portail et les scripts d'un client lisent. Seule la clé du Labo, créée
    par un membre de l'équipe (Claude Code de .mark), écrit. Le moteur du builder (appel direct, sans clé) n'est pas concerné."""
    user = await authenticate_mcp_request()
    if getattr(user, "par_porte_mcp", False):
        from api.services.builder.bibliotheque import droits
        from api.services.builder.constantes import organisation_bibliotheque

        if not await droits._cle_du_labo_par_mcp(user, organisation_bibliotheque()):
            raise HTTPException(status_code=403, detail="This API key cannot write through MCP: only the Labo key of the .mark team does")
    return user
