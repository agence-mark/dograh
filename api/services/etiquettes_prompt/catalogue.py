"""[.mark] Lots 8 et 22 : le CATALOGUE des objets citables par une étiquette, et le DIAGNOSTIC des étiquettes d'un brouillon.

Rien n'est stocké : le catalogue est calculé à partir des objets qui existent dans l'organisation (outils, étapes du graphe de
l'agent, agents, sujets de l'équipe, documents de la base de connaissances, phrases du code, blocs de la bibliothèque), comme
celui des variables. Chaque lecture est filtrée PAR ORGANISATION dans la requête (une étiquette ne voit jamais l'objet d'une
autre). Une source illisible est une source vide, notée ``sources_illisibles`` : le diagnostic ne déclare alors pas
« introuvable » une étiquette de cette famille (jamais un faux blocage).

``construire`` et ``diagnostiquer`` sont pures (testées seules) ; ``catalogue_de`` lit les sources.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from loguru import logger

from api.services.etiquettes_prompt import familles as f
from api.services.etiquettes_prompt.resolution import REJETE, BlocLu

ACTIF = "actif"
ARCHIVE = "archive"
BROUILLON = "brouillon"
ILLISIBLE = "illisible"

# Les motifs d'erreur d'une étiquette (bloquants) et le conseil (non bloquant).
INTROUVABLE = "introuvable"
NON_RATTACHE = "non_rattache"
VERSION_DISPARUE = "version_disparue"
BLOC_REJETE = "rejete"
SANS_RECETTE = "sans_recette"
BLOC_DANS_BLOC = "bloc_dans_bloc"
PLUS_RECENT = "plus_recent"  # conseil : un bloc resté sur sa version a une Recette plus récente
CONSEILS = frozenset({PLUS_RECENT})


@dataclass
class ObjetCitable:
    cle: str  # « famille:clé », ce que l'écran insère entre {{ }}
    famille: str
    libelle: str
    statut: str = ACTIF
    resume: str = ""
    rendu: str = ""  # ce que le modèle reçoit (le nom exact de la fonction pour un outil)
    lignes: list[tuple[str, str]] = field(default_factory=list)
    etapes: list[str] = field(default_factory=list)  # outil : les étapes (identifiants) qui le rattachent
    version: int | None = None  # bloc : la dernière Recette
    versions: list[dict[str, Any]] = field(default_factory=list)  # bloc : [{numero, statut}]

    def en_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lignes"] = [list(x) for x in self.lignes]
        return d


@dataclass
class Sources:
    """Ce que ``catalogue_de`` a lu ; ``construire`` en fait le catalogue (pur)."""

    outils: list[Any] = field(default_factory=list)
    agents: list[Any] = field(default_factory=list)
    sujets: list[Any] = field(default_factory=list)
    documents: list[Any] = field(default_factory=list)
    blocs: list[BlocLu] = field(default_factory=list)
    graphe: dict | None = None
    illisibles: set[str] = field(default_factory=set)


def _noeuds(graphe: dict | None) -> list[dict]:
    return [n for n in ((graphe or {}).get("nodes") or []) if isinstance(n, dict)]


def _rattaches(graphe: dict | None) -> dict[str, list[str]]:
    sortie: dict[str, list[str]] = {}
    for n in _noeuds(graphe):
        for u in (n.get("data") or {}).get("tool_uuids") or []:
            if isinstance(u, str):
                sortie.setdefault(u, []).append(str(n.get("id")))
    return sortie


def construire(s: Sources) -> dict[str, ObjetCitable]:
    from api.enums import ToolCategory
    from api.services.phrases.catalogue import MOTIFS
    from api.services.workflow.tools.custom_tool import custom_tool_function_name
    from api.services.workflow.tools.mcp_tool import namespace_function_name

    sortie: dict[str, ObjetCitable] = {}
    rattaches = _rattaches(s.graphe)
    statut_outil = {"active": ACTIF, "archived": ARCHIVE, "draft": BROUILLON}
    for o in s.outils:
        statut = statut_outil.get(str(o.status), ACTIF)
        etapes = rattaches.get(o.tool_uuid, [])
        if o.category == ToolCategory.MCP.value:
            for d in ((o.definition or {}).get("config") or {}).get("discovered_tools") or []:
                if isinstance(d, dict) and d.get("name"):
                    cle = f"{f.OUTIL}:{o.tool_uuid}/{d['name']}"
                    fonction = namespace_function_name(o.name, d["name"], fallback=o.tool_uuid[:8])
                    sortie[cle] = ObjetCitable(cle, f.OUTIL, f"{o.name} › {d['name']}", statut, str(d.get("description") or "")[:300],
                                               fonction, [("Serveur MCP", o.name), ("Nom vu par le modèle", fonction)], etapes)
            continue
        fonction = custom_tool_function_name(o.name)
        cle = f"{f.OUTIL}:{o.tool_uuid}"
        sortie[cle] = ObjetCitable(cle, f.OUTIL, o.name, statut, str(o.description or "")[:300], fonction,
                                   [("Type", str(o.category)), ("Nom vu par le modèle", fonction)], etapes)
    for n in _noeuds(s.graphe):
        donnees = n.get("data") or {}
        nom = donnees.get("name")
        if not isinstance(nom, str) or not nom.strip():
            continue
        cle = f"{f.ETAPE}:{n.get('id')}"
        sortie[cle] = ObjetCitable(cle, f.ETAPE, nom, ACTIF, str(donnees.get("prompt") or "")[:200], nom, [("Type", str(n.get("type")))])
    for a in s.agents:
        cle = f"{f.AGENT}:{a.id}"
        statut = ARCHIVE if str(getattr(a, "status", "active")) == "archived" else ACTIF
        sortie[cle] = ObjetCitable(cle, f.AGENT, a.name, statut, "", a.name)
    for sujet in s.sujets:
        cle = f"{f.EQUIPE}:{sujet.code}"
        sortie[cle] = ObjetCitable(cle, f.EQUIPE, sujet.libelle, ACTIF if sujet.actif else ARCHIVE,
                                   f"Sujet de transfert ({len(sujet.destinataires)} destinataire(s)).", sujet.code,
                                   [("Code", sujet.code)])
    for d in s.documents:
        cle = f"{f.DOCUMENT}:{d.document_uuid}"
        statut = ILLISIBLE if str(getattr(d, "processing_status", "")) == "failed" else ACTIF
        sortie[cle] = ObjetCitable(cle, f.DOCUMENT, d.filename, statut, "Document de la base de connaissances.", d.filename)
    for m in MOTIFS.values():
        cle = f"{f.PHRASE}:{m.id}"
        texte = m.variantes_defaut[0] if m.variantes_defaut else ""
        sortie[cle] = ObjetCitable(cle, f.PHRASE, m.libelle_fr, ACTIF, f"« {texte} »" if texte else "", texte, [("Dite quand", m.quand_fr)])
    for b in s.blocs:
        cle = f"{f.BLOC}:{b.slug}"
        recette = b.derniere_recette
        sortie[cle] = ObjetCitable(
            cle, f.BLOC, b.titre, ACTIF, (recette.texte if recette else "")[:300], (recette.texte if recette else ""),
            [("Famille de la bibliothèque", b.famille)] + ([("Version en Recette", f"v{recette.numero}")] if recette else []),
            version=recette.numero if recette else None,
            versions=[{"numero": v.numero, "statut": v.statut} for v in b.versions],
        )
    return sortie


# --- Le diagnostic d'un brouillon ------------------------------------------------------------------------------------------


@dataclass
class Probleme:
    cle: str  # la clé complète citée (« bloc:x@v2 »)
    famille: str
    motif: str
    message: str
    champ: str
    noeud_id: str | None = None
    etape: str | None = None
    corrections: list[dict[str, Any]] = field(default_factory=list)

    @property
    def bloquant(self) -> bool:
        return self.motif not in CONSEILS

    def en_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bloquant"] = self.bloquant
        return d


def textes_du_brouillon(graphe: dict | None, configurations: dict | None) -> Iterable[tuple[str, str | None, str | None, str, dict]]:
    """(champ, identifiant du nœud, nom de l'étape, texte, données du nœud) de chaque texte qui porte une étiquette."""
    from api.services.variables_agent.citations import _parcourir

    for n in _noeuds(graphe):
        donnees = n.get("data") or {}
        nom = donnees.get("name") if isinstance(donnees.get("name"), str) else None
        for chemin, _etape, texte in _parcourir(donnees, f"nodes[{n.get('id')}]", nom):
            if f.MOTIF.search(texte):
                yield chemin, str(n.get("id")), nom, texte, n
    for chemin, _etape, texte in _parcourir(configurations or {}, "configurations", None):
        if f.MOTIF.search(texte):
            yield chemin, None, None, texte, {}
    for arete in ((graphe or {}).get("edges") or []):
        if isinstance(arete, dict):
            for chemin, _etape, texte in _parcourir(arete.get("data") or {}, f"edges[{arete.get('id')}]", None):
                if f.MOTIF.search(texte):
                    yield chemin, None, None, texte, {}


def _retirer(cle: str, champ: str) -> dict[str, Any]:
    return {"type": "retirer", "cle": cle, "champ": champ, "libelle": "Retirer l'étiquette"}


def _probleme_d_une_etiquette(e: f.Etiquette, catalogue: dict[str, ObjetCitable], noeud: dict, illisibles: set[str]) -> tuple[str, str, list] | None:
    complete = e.complete
    if e.famille == f.BLOC:
        slug, epingle = f.bloc_et_version(e.cle)
        objet = catalogue.get(f"{f.BLOC}:{slug}")
        if objet is None:
            return None if f.BLOC in illisibles else (INTROUVABLE, f"Le bloc « {slug} » n'existe pas dans la bibliothèque.", [])
        numeros = {v["numero"]: v["statut"] for v in objet.versions}
        suivre = {"type": "suivre", "cle": complete, "libelle": "Suivre la dernière version"} if objet.version else None
        if epingle is not None:
            passer = (
                {"type": "passer_version", "cle": complete, "version": objet.version, "libelle": f"Passer à la version {objet.version}"}
                if objet.version and objet.version != epingle
                else None
            )
            if epingle not in numeros:
                return VERSION_DISPARUE, f"La version {epingle} du bloc « {objet.libelle} » n'existe plus.", [c for c in (passer, suivre) if c]
            if numeros[epingle] == REJETE:
                return BLOC_REJETE, f"La version {epingle} du bloc « {objet.libelle} » est rejetée.", [c for c in (passer, suivre) if c]
            if objet.version and objet.version > epingle:
                return PLUS_RECENT, f"Le bloc « {objet.libelle} » a une version {objet.version} en Recette ; cet agent reste sur la {epingle}.", [c for c in (passer, suivre) if c]
            return None
        if objet.version is None:
            return SANS_RECETTE, f"Le bloc « {objet.libelle} » n'a aucune version en Recette : rien à suivre.", []
        if any(x.famille == f.BLOC for x in f.etiquettes_de(objet.rendu)):
            return BLOC_DANS_BLOC, f"Le bloc « {objet.libelle} » cite un autre bloc : un seul niveau est permis.", []
        return None
    if e.famille == f.EQUIPE and f.EQUIPE in illisibles:
        return None
    objet = catalogue.get(complete)
    if objet is None:
        if e.famille in illisibles:
            return None
        return INTROUVABLE, f"« {e.cle} » n'existe pas (ou plus) : l'objet a été supprimé.", []
    if objet.statut == ARCHIVE:
        return ARCHIVE, f"« {objet.libelle} » est archivé : l'agent ne pourrait plus s'en servir.", []
    if objet.statut == BROUILLON:
        return BROUILLON, f"L'outil « {objet.libelle} » est encore en brouillon : il n'est pas proposé au modèle.", []
    if objet.statut == ILLISIBLE:
        return ILLISIBLE, f"Le document « {objet.libelle} » n'a pas pu être lu.", []
    if e.famille == f.OUTIL and noeud and noeud.get("type") != "globalNode":
        uuid = f.outil_et_fonction(e.cle)[0]
        if uuid not in ((noeud.get("data") or {}).get("tool_uuids") or []):
            return (
                NON_RATTACHE,
                f"L'outil « {objet.libelle} » n'est pas rattaché à cette étape : le modèle ne le verrait pas.",
                [{"type": "rattacher", "cle": complete, "noeud_id": str(noeud.get("id")), "libelle": "Rattacher l'outil à l'étape"}],
            )
    return None


def diagnostiquer(graphe: dict | None, configurations: dict | None, catalogue: dict[str, ObjetCitable], illisibles: Iterable[str] = ()) -> list[Probleme]:
    """Pure. Chaque étiquette en erreur (ou à conseiller) de chaque texte, avec ses corrections en un clic."""
    illisibles = set(illisibles)
    sortie: list[Probleme] = []
    vus: set[tuple[str, str]] = set()
    for champ, noeud_id, etape, texte, noeud in textes_du_brouillon(graphe, configurations):
        for e in f.etiquettes_de(texte):
            if (e.complete, champ) in vus:
                continue
            vus.add((e.complete, champ))
            constat = _probleme_d_une_etiquette(e, catalogue, noeud, illisibles)
            if constat is None:
                continue
            motif, message, corrections = constat
            sortie.append(Probleme(e.complete, e.famille, motif, message, champ, noeud_id, etape, [*corrections, _retirer(e.complete, champ)]))
    return sortie


# --- Les lectures ------------------------------------------------------------------------------------------------------------


async def lire_les_blocs() -> list[BlocLu]:
    from api.services.builder.bibliotheque import service
    from api.services.etiquettes_prompt.table import FAMILLES_DE_BLOCS, bloc_depuis_element

    blocs: list[BlocLu] = []
    vus: set[str] = set()
    for famille in FAMILLES_DE_BLOCS:
        for element in await service.elements_de(famille):
            if element.slug not in vus:
                vus.add(element.slug)
                blocs.append(bloc_depuis_element(element))
    return blocs


async def _sujets(organization_id: int) -> list[Any]:
    from api.db.bases_clients.connexion import connecter
    from api.db.bases_clients.equipe import lire_equipe
    from api.services.base_client.rattachement import nom_de_la_base

    base = await nom_de_la_base(organization_id)
    if not base:
        return []
    connexion = await connecter(base)
    try:
        return list((await lire_equipe(connexion)).sujets)
    finally:
        await connexion.close()


async def lire_les_sources(organization_id: int, graphe: dict | None) -> Sources:
    from api.db import db_client

    s = Sources(graphe=graphe)

    async def _lire(famille: str, lecture):
        try:
            return await lecture()
        except Exception as erreur:  # noqa: BLE001 -- une source illisible est une source vide, notée
            logger.warning(f"[.mark] étiquettes : {famille} illisibles pour {organization_id} ({type(erreur).__name__})")
            s.illisibles.add(famille)
            return []

    s.outils = list(await _lire(f.OUTIL, lambda: db_client.get_tools_for_organization(organization_id, status="active,archived,draft")))
    s.agents = list(await _lire(f.AGENT, lambda: db_client.get_workflows_by_organization_light(organization_id)))
    s.sujets = list(await _lire(f.EQUIPE, lambda: _sujets(organization_id)))
    s.documents = list(await _lire(f.DOCUMENT, lambda: db_client.get_documents_for_organization(organization_id, limit=1000)))
    s.blocs = list(await _lire(f.BLOC, lire_les_blocs))
    return s


async def catalogue_de(organization_id: int, graphe: dict | None) -> tuple[dict[str, ObjetCitable], set[str]]:
    sources = await lire_les_sources(organization_id, graphe)
    return construire(sources), sources.illisibles


async def problemes_du_brouillon(organization_id: int, brouillon: Any) -> list[Probleme]:
    """Le diagnostic d'un brouillon (ou d'une version) ; ne lève jamais (une panne = aucun problème déclaré, et un avertissement)."""
    try:
        graphe = getattr(brouillon, "workflow_json", None)
        configurations = getattr(brouillon, "workflow_configurations", None)
        graphe = graphe if isinstance(graphe, dict) else None
        configurations = configurations if isinstance(configurations, dict) else None
        if not any(True for _ in textes_du_brouillon(graphe, configurations)):
            return []
        catalogue, illisibles = await catalogue_de(organization_id, graphe)
        return diagnostiquer(graphe, configurations, catalogue, illisibles)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] étiquettes : diagnostic impossible ({type(erreur).__name__})")
        return []
