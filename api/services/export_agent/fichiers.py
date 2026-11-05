"""[.mark] Partie 3, N3b : l'agent entier en FICHIERS lisibles, et leur import dans le brouillon d'un agent (décision 20, audit 12 § 3).

Distinct de la copie d'un agent d'une organisation à une autre (``ecriture``, « Exporter vers un client ») : ici l'agent devient un
dossier à versionner (chez le client, dans une CI) et revient par un import qui arrive dans un BROUILLON, jamais en ligne.

| Fichier | Contenu |
|---|---|
| ``agent.yaml`` | le nom, la version du format, ce qui ne voyage pas, les secrets retirés (identité de l'export, pas de contenu) |
| ``graphe.yaml`` | les étapes et leurs liaisons ; le prompt de chaque étape est dans son fichier ``prompts/`` |
| ``prompts/<id>-<étape>.md`` | un fichier par étape (et le prompt général, qui est une étape) |
| ``reglages.yaml`` | les réglages du brouillon (phrases du code comprises), sans clé ni secret |
| ``variables.yaml`` | les variables de contexte de l'agent |
| ``outils.yaml`` | chaque outil de l'agent avec la **version exacte épinglée** (décision 21) |
| ``blocs.yaml`` + ``blocs/<slug>.md`` | les blocs cités par les prompts : version suivie et texte (références en LECTURE SEULE : ils vivent dans la bibliothèque) |
| ``tests/<slug>.yaml`` | un fichier par test de l'agent |

Garanties : l'export est **déterministe** (mêmes données = mêmes octets) ; **aucun secret** n'en sort (valeur retirée, la clé reste une
référence ``…credential_uuid`` ; aucun identifiant d'organisation) ; l'import est **idempotent** (le même dossier importé deux fois laisse
le même brouillon, aucun doublon : ``previsualiser`` dit « inchangé » partout) ; aller-retour **sans perte** (exporter, importer dans un
autre agent, exporter donne les mêmes fichiers, hors le nom dans ``agent.yaml``). Un chemin de déclencheur ne voyage pas : l'import garde
celui de l'étape du même identifiant dans l'agent cible, sinon en tire un neuf. Les réglages de rattachement (agents spécialisés, agent
principal, établissement, bruit d'ambiance) ne voyagent pas non plus : l'import laisse ceux de l'agent cible.

⛔ Aucune écriture hors de l'organisation de l'appelant ; l'import ne publie rien et ne supprime aucun test.
"""

from __future__ import annotations

import copy
import difflib
import io
import re
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any

import yaml
from loguru import logger

from api.db import db_client
from api.services.builder import brouillon
from api.services.builder.tests_agent import stockage as stockage_tests
from api.services.export_agent.purge import purger_les_secrets, retirer_les_identifiants
from api.services.groupe.groupe import lire_agent
from api.services.groupe.passations import CLE_AGENT_PRINCIPAL, CLE_AGENTS_SPECIALISES

FORMAT = "agent-mark-fichiers"
VERSION = 1
MARQUE_DECLENCHEUR = "regenere-a-l-import"
CLES_QUI_NE_VOYAGENT_PAS = (CLE_AGENTS_SPECIALISES, CLE_AGENT_PRINCIPAL, "etablissement_id", "ambient_noise_configuration")

FICHIERS_MAX = 400
FICHIER_MAX = 2_000_000
TOTAL_MAX = 8_000_000
CHEMIN_VALIDE = re.compile(r"^(agent|graphe|reglages|variables|outils|blocs)\.yaml$|^(prompts|blocs)/[a-z0-9][a-z0-9._-]*\.md$|^tests/[a-z0-9][a-z0-9._-]*\.yaml$")
_BLOC = re.compile(r"\{\{\s*bloc:([A-Za-z0-9_-]+)(?:@v(\d+))?\s*\}\}")


class ErreurFichiers(Exception):
    """Un refus normal : le message est sûr à montrer, ``statut`` est celui de la route."""

    def __init__(self, message: str, statut: int = 422):
        super().__init__(message)
        self.statut = statut


# --- la forme des fichiers --------------------------------------------------------------------------------------------------


def en_yaml(valeur: Any) -> str:
    """Un YAML déterministe (clés triées, accents lisibles) qui se relit à l'identique (``safe_load``)."""
    return yaml.safe_dump(valeur, allow_unicode=True, sort_keys=True, default_flow_style=False, width=10_000)


def lire_yaml(texte: str, fichier: str) -> Any:
    try:
        return yaml.safe_load(texte)
    except yaml.YAMLError:
        raise ErreurFichiers(f"{fichier}: this file is not valid YAML.") from None


def _ascii(texte: str) -> str:
    plat = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plat.lower()).strip("-")[:40] or "etape"


def _fichier_de_prompt(noeud: dict[str, Any]) -> str:
    donnees = noeud.get("data") or {}
    return f"prompts/{_ascii(str(noeud.get('id') or ''))}-{_ascii(str(donnees.get('name') or ''))}.md"


def _noeuds(graphe: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in (graphe.get("nodes") or []) if isinstance(n, dict)]


def _sortir_les_prompts(graphe: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Le graphe sans le texte des prompts, et ``{fichier: texte}``. Un identifiant d'étape et un nom qui donneraient le même fichier
    prennent un suffixe, dans l'ordre des étapes (donc stable)."""
    neuf = copy.deepcopy(graphe)
    textes: dict[str, str] = {}
    for noeud in _noeuds(neuf):
        donnees = noeud.get("data")
        if not isinstance(donnees, dict):
            continue
        if noeud.get("type") == "trigger" and "trigger_path" in donnees:
            donnees["trigger_path"] = MARQUE_DECLENCHEUR
        prompt = donnees.get("prompt")
        if isinstance(prompt, str) and prompt:
            fichier = _fichier_de_prompt(noeud)
            base, n = fichier, 2
            while fichier in textes:
                fichier = base.replace(".md", f"-{n}.md")
                n += 1
            textes[fichier] = prompt
            donnees.pop("prompt")
            donnees["prompt_fichier"] = fichier
    return neuf, textes


def _remettre_les_prompts(graphe: dict[str, Any], fichiers: dict[str, str]) -> dict[str, Any]:
    neuf = copy.deepcopy(graphe)
    for noeud in _noeuds(neuf):
        donnees = noeud.get("data")
        if isinstance(donnees, dict) and "prompt_fichier" in donnees:
            fichier = donnees.pop("prompt_fichier")
            if fichier not in fichiers:
                raise ErreurFichiers(f"graphe.yaml: the file {fichier} is missing.")
            donnees["prompt"] = fichiers[fichier]
    return neuf


def _uuids_d_outils(graphe: dict[str, Any]) -> list[str]:
    vus: list[str] = []
    for noeud in _noeuds(graphe):
        for u in (noeud.get("data") or {}).get("tool_uuids") or []:
            if isinstance(u, str) and u not in vus:
                vus.append(u)
    return vus


def _blocs_cites(graphe_avec_prompts: dict[str, Any]) -> list[tuple[str, int | None]]:
    """Les blocs cités (slug, version) dans tous les textes du graphe, sans doublon, triés."""
    vus: set[tuple[str, int | None]] = set()

    def marcher(v: Any) -> None:
        if isinstance(v, str):
            for m in _BLOC.finditer(v):
                vus.add((m.group(1), int(m.group(2)) if m.group(2) else None))
        elif isinstance(v, dict):
            for x in v.values():
                marcher(x)
        elif isinstance(v, list):
            for x in v:
                marcher(x)

    marcher(graphe_avec_prompts)
    return sorted(vus, key=lambda c: (c[0], c[1] or 0))


# --- l'export ---------------------------------------------------------------------------------------------------------------


async def _outils_epingles(organisation: int, workflow_id: int) -> list[dict[str, Any]]:
    vue = await db_client.outils_epingles_de_l_agent(organisation, workflow_id)
    return sorted(
        ({"nom": o["nom"], "uuid": o["tool_uuid"], "version": o["epinglee"]} for o in vue["outils"]), key=lambda o: (o["nom"], o["uuid"])
    )


async def _blocs(graphe: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    from api.services.etiquettes_prompt.table import lire_un_bloc

    lignes: list[dict[str, Any]] = []
    textes: dict[str, str] = {}
    for slug, version in _blocs_cites(graphe):
        bloc = await lire_un_bloc(slug)
        ligne: dict[str, Any] = {"slug": slug, "suit": version is None, "version": version}
        if bloc is None:
            ligne["existe"] = False
        else:
            choisie = next((v for v in bloc.versions if v.numero == version), None) if version else (bloc.versions[-1] if bloc.versions else None)
            ligne.update({"existe": True, "famille": bloc.famille, "titre": bloc.titre, "version_lue": choisie.numero if choisie else None})
            if choisie is not None and f"blocs/{slug}.md" not in textes:
                textes[f"blocs/{slug}.md"] = choisie.texte
        lignes.append(ligne)
    return lignes, textes


async def exporter(organisation: int, workflow_id: int) -> dict[str, Any]:
    """Les fichiers de l'agent (``{chemin: texte}``) et le nombre de secrets retirés. ``ErreurFichiers`` (404) si l'agent n'est pas à l'organisation."""
    agent = await lire_agent(workflow_id, organisation)
    if agent is None:
        raise ErreurFichiers("Workflow not found", 404)
    secrets = 0

    def propre(valeur: Any) -> Any:
        nonlocal secrets
        sortie, n = purger_les_secrets(retirer_les_identifiants(valeur))
        secrets += n
        return sortie

    graphe = propre(agent.definition)
    graphe_sans_prompts, prompts = _sortir_les_prompts(graphe)
    reglages = {k: v for k, v in propre(agent.reglages).items() if k not in CLES_QUI_NE_VOYAGENT_PAS}
    variables = propre(agent.variables)
    outils = await _outils_epingles(organisation, workflow_id)
    blocs, textes_de_blocs = await _blocs(graphe)

    fichiers: dict[str, str] = {
        "graphe.yaml": en_yaml(graphe_sans_prompts),
        "reglages.yaml": en_yaml(reglages),
        "variables.yaml": en_yaml(variables),
        "outils.yaml": en_yaml(outils),
        "blocs.yaml": en_yaml(blocs),
        **prompts,
        **textes_de_blocs,
    }
    for test in await stockage_tests.lister(organisation, workflow_id):
        fichiers[f"tests/{test['slug']}.yaml"] = en_yaml(propre(test))
    fichiers["agent.yaml"] = en_yaml(
        {
            "format": FORMAT,
            "version": VERSION,
            "nom": agent.nom,
            "ne_voyage_pas": list(CLES_QUI_NE_VOYAGENT_PAS),
            "blocs": "references en lecture seule : les blocs vivent dans la bibliotheque",
            "secrets_retires": secrets,
        }
    )
    return {"agent_id": workflow_id, "fichiers": dict(sorted(fichiers.items())), "secrets_retires": secrets}


CONTENUS = {
    "graphe": ("graphe.yaml",),
    "prompts": ("prompts/",),
    "reglages": ("reglages.yaml", "variables.yaml"),
    "outils": ("outils.yaml",),
    "blocs": ("blocs.yaml", "blocs/"),
    "tests": ("tests/",),
}


def filtrer(fichiers: dict[str, str], contenus: list[str] | None) -> dict[str, str]:
    """Seulement les contenus demandés (``graphe``, ``prompts``, ``reglages``, ``outils``, ``blocs``, ``tests``) ; ``agent.yaml`` reste toujours.
    ``None`` : tout. Un nom inconnu est refusé (422)."""
    if contenus is None:
        return fichiers
    inconnus = [c for c in contenus if c not in CONTENUS]
    if inconnus:
        raise ErreurFichiers(f"Unknown content: {', '.join(sorted(set(inconnus)))}.")
    gardes = tuple(p for c in contenus for p in CONTENUS[c])
    return {chemin: texte for chemin, texte in fichiers.items() if chemin == "agent.yaml" or chemin.startswith(gardes)}


def en_zip(fichiers: dict[str, str]) -> bytes:
    """Les fichiers dans une archive déterministe (dates fixes, ordre trié) : les mêmes fichiers donnent les mêmes octets."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for chemin in sorted(fichiers):
            info = zipfile.ZipInfo(chemin, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, fichiers[chemin].encode("utf-8"))
    return tampon.getvalue()


# --- l'import ---------------------------------------------------------------------------------------------------------------


@dataclass
class Plan:
    graphe: dict[str, Any]
    reglages: dict[str, Any]
    variables: dict[str, Any]
    epingles: dict[str, int]
    tests: list[dict[str, Any]]
    avertissements: list[dict[str, Any]] = field(default_factory=list)


def verifier_les_fichiers(fichiers: dict[str, str]) -> None:
    if not fichiers or len(fichiers) > FICHIERS_MAX:
        raise ErreurFichiers(f"Between 1 and {FICHIERS_MAX} files are expected.")
    total = 0
    for chemin, texte in fichiers.items():
        if not CHEMIN_VALIDE.match(chemin):
            raise ErreurFichiers(f"{chemin}: this file is not part of an exported agent.")
        taille = len(texte.encode("utf-8"))
        total += taille
        if taille > FICHIER_MAX or total > TOTAL_MAX:
            raise ErreurFichiers("The files are too large.", 413)
    manifeste = lire_yaml(fichiers.get("agent.yaml", ""), "agent.yaml") if "agent.yaml" in fichiers else None
    if not isinstance(manifeste, dict) or manifeste.get("format") != FORMAT:
        raise ErreurFichiers("agent.yaml: this folder is not an exported agent.")
    if manifeste.get("version") != VERSION:
        raise ErreurFichiers("agent.yaml: this version of the format is not known.")
    if "graphe.yaml" not in fichiers:
        raise ErreurFichiers("graphe.yaml is missing.")


def _dict(valeur: Any, fichier: str) -> dict[str, Any]:
    if valeur is None:
        return {}
    if not isinstance(valeur, dict):
        raise ErreurFichiers(f"{fichier}: a mapping is expected.")
    return valeur


async def _correspondance_des_outils(organisation: int, outils: list[dict[str, Any]], avertissements: list[dict[str, Any]]) -> dict[str, str | None]:
    """``uuid de l'export -> uuid de l'outil de CETTE organisation`` : le même identifiant s'il existe ici, sinon l'outil du même nom ; sinon rien."""
    ici = await db_client.get_tools_for_organization(organisation)
    par_uuid = {t.tool_uuid for t in ici}
    par_nom = {t.name: t.tool_uuid for t in ici}
    sortie: dict[str, str | None] = {}
    for o in outils:
        if not isinstance(o, dict) or not isinstance(o.get("uuid"), str):
            continue
        cible = o["uuid"] if o["uuid"] in par_uuid else par_nom.get(str(o.get("nom")))
        sortie[o["uuid"]] = cible
        if cible is None:
            avertissements.append({"code": "outil_absent", "nom": o.get("nom")})
    return sortie


async def construire_le_plan(organisation: int, workflow_id: int, fichiers: dict[str, str]) -> Plan:
    verifier_les_fichiers(fichiers)
    avertissements: list[dict[str, Any]] = []
    graphe = _remettre_les_prompts(_dict(lire_yaml(fichiers["graphe.yaml"], "graphe.yaml"), "graphe.yaml"), fichiers)
    reglages = _dict(lire_yaml(fichiers.get("reglages.yaml", ""), "reglages.yaml"), "reglages.yaml")
    variables = _dict(lire_yaml(fichiers.get("variables.yaml", ""), "variables.yaml"), "variables.yaml")
    outils = lire_yaml(fichiers.get("outils.yaml", ""), "outils.yaml") or []
    if not isinstance(outils, list):
        raise ErreurFichiers("outils.yaml: a list is expected.")
    # Aucun secret ne doit entrer : un dossier modifié à la main ne ramène pas une clé en clair.
    graphe, a = purger_les_secrets(graphe)
    reglages, b = purger_les_secrets(reglages)
    variables, c = purger_les_secrets(variables)
    if a + b + c:
        avertissements.append({"code": "secrets_ignores", "nombre": a + b + c})

    # Les outils : l'identifiant de l'export devient celui de l'outil de cette organisation (sinon l'étape perd la référence, dite).
    correspondance = await _correspondance_des_outils(organisation, outils, avertissements)
    for noeud in _noeuds(graphe):
        donnees = noeud.get("data")
        if isinstance(donnees, dict) and isinstance(donnees.get("tool_uuids"), list):
            donnees["tool_uuids"] = [correspondance.get(u, u) for u in donnees["tool_uuids"] if correspondance.get(u, u)]
    epingles = {
        correspondance[o["uuid"]]: int(o["version"])
        for o in outils
        if isinstance(o, dict) and correspondance.get(o.get("uuid")) and isinstance(o.get("version"), int)
    }

    # Les déclencheurs : le chemin de l'étape du même identifiant dans l'agent cible, sinon un chemin neuf (jamais celui d'un autre agent).
    agent = await lire_agent(workflow_id, organisation)
    existants = {
        str(n.get("id")): (n.get("data") or {}).get("trigger_path")
        for n in _noeuds((agent.definition if agent else None) or {})
        if n.get("type") == "trigger"
    }
    for noeud in _noeuds(graphe):
        donnees = noeud.get("data")
        if noeud.get("type") == "trigger" and isinstance(donnees, dict) and donnees.get("trigger_path") == MARQUE_DECLENCHEUR:
            donnees["trigger_path"] = existants.get(str(noeud.get("id"))) or str(uuid.uuid4())

    # Les réglages de rattachement restent ceux de l'agent cible.
    cible_reglages = agent.reglages if agent else {}
    reglages = {k: v for k, v in reglages.items() if k not in CLES_QUI_NE_VOYAGENT_PAS}
    reglages.update({k: copy.deepcopy(cible_reglages[k]) for k in CLES_QUI_NE_VOYAGENT_PAS if k in cible_reglages})

    # Les blocs : références en lecture seule, un bloc absent de la bibliothèque est dit.
    from api.services.etiquettes_prompt.table import lire_un_bloc

    blocs = lire_yaml(fichiers.get("blocs.yaml", ""), "blocs.yaml") or []
    for b_ in blocs if isinstance(blocs, list) else []:
        if isinstance(b_, dict) and b_.get("existe") is not False:
            if await lire_un_bloc(str(b_.get("slug"))) is None:
                avertissements.append({"code": "bloc_absent", "nom": b_.get("slug")})

    tests: list[dict[str, Any]] = []
    for chemin, texte in sorted(fichiers.items()):
        if chemin.startswith("tests/"):
            test = _dict(lire_yaml(texte, chemin), chemin)
            if test.get("slug") != chemin[len("tests/") : -len(".yaml")]:
                raise ErreurFichiers(f"{chemin}: the test's slug does not match the file name.")
            tests.append(retirer_les_identifiants(purger_les_secrets(test)[0]))
    return Plan(graphe, reglages, variables, epingles, tests, avertissements)


def _effet(avant: str | None, apres: str | None) -> tuple[str, str | None]:
    if avant is None:
        return "ajoute", None
    if apres is None:
        return "retire", None
    if avant == apres:
        return "inchange", None
    changees = sum(1 for ligne in difflib.ndiff(avant.splitlines(), apres.splitlines()) if ligne[:2] in ("+ ", "- "))
    return "modifie", f"{changees} lines"


async def previsualiser(organisation: int, workflow_id: int, fichiers: dict[str, str]) -> list[dict[str, Any]]:
    """Fichier par fichier, ce que l'import changerait dans le brouillon : ``ajoute``, ``modifie``, ``inchange``, ou ``retire`` (présent
    dans l'agent, absent du dossier : l'import ne le supprime pas). ``agent.yaml`` et les blocs (références) ne sont pas comparés."""
    verifier_les_fichiers(fichiers)
    actuel = (await exporter(organisation, workflow_id))["fichiers"]
    lignes = []
    for chemin in sorted({*actuel, *fichiers}):
        if chemin == "agent.yaml" or chemin.startswith("blocs"):
            continue
        effet, detail = _effet(actuel.get(chemin), fichiers.get(chemin))
        lignes.append({"fichier": chemin, "effet": effet, "detail": detail})
    return lignes


async def importer(user: Any, organisation: int, workflow_id: int, fichiers: dict[str, str]) -> dict[str, Any]:
    """Écrit le dossier dans le BROUILLON de l'agent (jamais en ligne). Tout est lu et validé avant la première écriture ; un refus n'écrit rien.
    Rejouable : le même dossier laisse le même brouillon. Ne supprime aucun test."""
    agent = await lire_agent(workflow_id, organisation)
    if agent is None:
        raise ErreurFichiers("Workflow not found", 404)
    plan = await construire_le_plan(organisation, workflow_id, fichiers)
    try:
        erreurs = await brouillon.valider(plan.graphe, organisation)
    except Exception as erreur:  # noqa: BLE001 -- la validation de l'amont peut lever sur un lien vers une étape absente : c'est un graphe invalide
        logger.info(f"export_agent.fichiers: invalid graph ({type(erreur).__name__})")
        erreurs = ["a link points to a step that does not exist, or the graph is malformed"]
    if erreurs:
        raise ErreurFichiers("The graph is not valid: " + "; ".join(erreurs[:3]))
    apercu = await previsualiser(organisation, workflow_id, fichiers)

    await db_client.update_workflow(
        workflow_id=workflow_id,
        name=None,
        workflow_definition=plan.graphe,
        template_context_variables=plan.variables or None,
        workflow_configurations=plan.reglages,
        organization_id=organisation,
    )
    if plan.epingles:
        await db_client.remplacer_les_epingles_du_brouillon(organisation, workflow_id, plan.epingles)
    ecrits = 0
    for test in plan.tests:
        try:
            await stockage_tests.ecrire(organisation, workflow_id, test)
            ecrits += 1
        except stockage_tests.ErreurTest as erreur:
            logger.warning(f"export_agent.fichiers: a test was not written ({erreur})")
            plan.avertissements.append({"code": "test_refuse", "nom": test.get("slug")})
    posees = {o["uuid"]: o["version"] for o in await _outils_epingles(organisation, workflow_id)}
    for uuid_, version in plan.epingles.items():
        if posees.get(uuid_) != version:
            plan.avertissements.append({"code": "version_d_outil_absente", "nom": uuid_, "version": version})
    return {
        "agent_id": workflow_id,
        "applique": True,
        "fichiers": apercu,
        "tests_ecrits": ecrits,
        "outils_epingles": len(plan.epingles),
        "avertissements": plan.avertissements,
    }
