"""[.mark] Lots 8 et 22 : ce qu'un appel sait des objets cités, lu UNE fois au départ.

``construire`` ne lit que les objets que les textes citent : une lecture par famille (outils, agents, documents), jamais une
par étiquette ; les blocs viennent de la bibliothèque de .mark. Tout est lu AVEC l'organisation de l'agent : une étiquette ne
résout jamais l'objet d'une autre organisation. Ne lève jamais : une source illisible laisse ses étiquettes vides.
"""

from __future__ import annotations

from typing import Any, Iterable

from loguru import logger

from api.services.etiquettes_prompt import familles as f
from api.services.etiquettes_prompt.resolution import BlocLu, Table, VersionDeBloc

# Les familles de la bibliothèque qui ÉCRIVENT des prompts : leurs éléments sont citables par ``{{bloc:slug}}``. Une famille qui
# n'écrit pas de prompt (tests, réglages, outils…) n'en propose pas.
FAMILLES_DE_BLOCS: tuple[str, ...] = ("prompt-general", "moules-etape", "personas", "conditions-passage")


def texte_d_un_element(contenu: Any) -> str:
    texte = contenu.get("texte") if isinstance(contenu, dict) else None
    return texte if isinstance(texte, str) else ""


def bloc_depuis_element(element: Any) -> BlocLu:
    return BlocLu(
        slug=element.slug,
        titre=element.titre,
        famille=element.famille,
        versions=tuple(
            VersionDeBloc(v.numero, getattr(v.statut, "value", str(v.statut)), texte_d_un_element(v.contenu)) for v in element.versions
        ),
    )


async def lire_un_bloc(slug: str) -> BlocLu | None:
    """Le bloc ``slug`` dans la première famille qui écrit des prompts et le porte ; ``None`` s'il n'existe nulle part."""
    from api.services.builder.bibliotheque import service

    for famille in FAMILLES_DE_BLOCS:
        try:
            element = await service.element_ou_none(famille, slug)
        except Exception as erreur:  # noqa: BLE001 -- bibliothèque illisible = bloc vide
            logger.warning(f"[.mark] étiquettes : bloc {slug} illisible ({type(erreur).__name__})")
            return None
        if element is not None:
            return bloc_depuis_element(element)
    return None


def cles_citees(textes: Iterable[str]) -> dict[str, set[str]]:
    """``{famille: {clés}}`` des étiquettes des textes (un bloc compté par son slug, sans version)."""
    sortie: dict[str, set[str]] = {}
    for texte in textes:
        for e in f.etiquettes_de(texte):
            cle = f.bloc_et_version(e.cle)[0] if e.famille == f.BLOC else e.cle
            sortie.setdefault(e.famille, set()).add(cle)
    return sortie


async def construire(organization_id: int | None, textes: Iterable[str], *, outils_epingles: dict | None = None) -> Table:
    textes = list(textes)
    citees = cles_citees(textes)
    table = Table()
    if not citees or organization_id is None:
        return table
    from api.db import db_client

    # Les blocs d'abord : leurs textes peuvent citer d'autres objets (outils, documents…), lus dans la même passe.
    for slug in sorted(citees.get(f.BLOC, ())):
        bloc = await lire_un_bloc(slug)
        if bloc is not None:
            table.blocs[slug] = bloc
    if table.blocs:
        textes_des_blocs = [v.texte for b in table.blocs.values() for v in b.versions]
        for famille, cles in cles_citees(textes_des_blocs).items():
            if famille != f.BLOC:
                citees.setdefault(famille, set()).update(cles)

    try:
        if citees.get(f.OUTIL):
            from api.enums import ToolCategory
            from api.services.workflow.tools.custom_tool import custom_tool_function_name
            from api.services.workflow.tools.mcp_tool import namespace_function_name

            uuids = sorted({f.outil_et_fonction(c)[0] for c in citees[f.OUTIL]})
            for outil in await db_client.get_tools_by_uuids(uuids, organization_id, versions=outils_epingles):
                if outil.category == ToolCategory.MCP.value:
                    for cle in citees[f.OUTIL]:
                        uuid, fonction = f.outil_et_fonction(cle)
                        if uuid == outil.tool_uuid and fonction:
                            table.outils[cle] = namespace_function_name(outil.name, fonction, fallback=outil.tool_uuid[:8])
                else:
                    table.outils[outil.tool_uuid] = custom_tool_function_name(outil.name)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] étiquettes : outils illisibles ({type(erreur).__name__})")
    try:
        if citees.get(f.AGENT):
            ids = sorted({int(c) for c in citees[f.AGENT] if c.isdigit()})
            for agent in await db_client.get_workflows_by_ids(ids, organization_id) if ids else []:
                table.agents[str(agent.id)] = agent.name
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] étiquettes : agents illisibles ({type(erreur).__name__})")
    try:
        if citees.get(f.DOCUMENT):
            for doc in await db_client.get_documents_by_uuids(sorted(citees[f.DOCUMENT]), organization_id):
                table.documents[str(doc.document_uuid)] = doc.filename
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] étiquettes : documents illisibles ({type(erreur).__name__})")
    return table
