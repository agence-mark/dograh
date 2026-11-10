"""[.mark] Lots 8 et 22 : « Utilisé dans » et la correction en un clic d'une étiquette, écrite dans le BROUILLON.

Corrections (proposées par ``catalogue.diagnostiquer``, ou le choix « suivre / rester » d'un bloc depuis sa fiche) :

* ``retirer``        : l'étiquette disparaît du champ (ou de tous les champs) ;
* ``rattacher``      : l'outil cité est ajouté aux outils de l'étape ;
* ``suivre``         : ``{{bloc:x@v2}}`` -> ``{{bloc:x}}`` (suit la dernière Recette) ;
* ``passer_version`` : ``{{bloc:x}}`` ou ``{{bloc:x@v2}}`` -> ``{{bloc:x@vN}}`` (reste sur la version N).

Le graphe corrigé passe la validation du moteur avant d'être écrit ; rien n'est publié. ``appliquer`` est pure.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from loguru import logger

from api.services.etiquettes_prompt import familles as f

# Clôture, lot B (D17) : le mode d'un bloc sur CET agent (réglage ``blocs_modes``), posé ou retiré (retour au réglage de l'agent).
MODES_DE_BLOC = {"mode_direct": "direct", "mode_fige": "fige", "mode_defaut": None}
MODES_DE_L_AGENT = {"agent_direct": "direct", "agent_fige": "fige", "agent_defaut": None}  # le réglage ``blocs_mode`` de l'agent
TYPES = ("retirer", "rattacher", "suivre", "passer_version", *MODES_DE_BLOC, *MODES_DE_L_AGENT)


class CorrectionRefusee(Exception):
    pass


def _motif_de(cle: str) -> re.Pattern[str]:
    """La clé citée ; pour un bloc, toutes ses écritures (suivre ou rester)."""
    e = f.decouper(cle)
    if e is not None and e.famille == f.BLOC:
        slug = f.bloc_et_version(e.cle)[0]
        return re.compile(r"\{\{\s*bloc:" + re.escape(slug) + r"(?:@v\d+)?\s*\}\}")
    return re.compile(r"\{\{\s*" + re.escape(cle) + r"\s*\}\}")


def _remplacement(correction: dict[str, Any]) -> str:
    cle = correction["cle"]
    if correction["type"] == "retirer":
        return ""
    slug = f.bloc_et_version((f.decouper(cle) or f.Etiquette(f.BLOC, cle)).cle)[0]
    if correction["type"] == "suivre":
        return "{{bloc:" + slug + "}}"
    version = correction.get("version")
    if not isinstance(version, int) or version < 1:
        raise CorrectionRefusee("A version number is required.")
    return "{{bloc:" + slug + f"@v{version}" + "}}"


def _reecrire(valeur: Any, chemin: str, champ: str | None, motif: re.Pattern[str], neuf: str) -> tuple[Any, int]:
    if isinstance(valeur, str):
        if champ is not None and chemin != champ:
            return valeur, 0
        texte, n = motif.subn(neuf, valeur)
        if n and not neuf:
            texte = re.sub(r"[ \t]{2,}", " ", texte)
        return texte, n
    if isinstance(valeur, dict):
        total = 0
        sortie = {}
        for k, v in valeur.items():
            sortie[k], n = _reecrire(v, f"{chemin}.{k}" if chemin else str(k), champ, motif, neuf)
            total += n
        return sortie, total
    if isinstance(valeur, list):
        total = 0
        sortie_l = []
        for i, v in enumerate(valeur):
            nv, n = _reecrire(v, f"{chemin}[{i}]", champ, motif, neuf)
            sortie_l.append(nv)
            total += n
        return sortie_l, total
    return valeur, 0


def appliquer(graphe: dict, configurations: dict, correction: dict[str, Any]) -> tuple[dict, dict, int]:
    """Pure. Rend (graphe, réglages, nombre de changements). ``correction`` : {type, cle, champ?, noeud_id?, version?}."""
    if correction.get("type") not in TYPES or not f.decouper(str(correction.get("cle") or "")):
        raise CorrectionRefusee("Unknown fix.")
    graphe = copy.deepcopy(graphe or {})
    configurations = copy.deepcopy(configurations or {})
    cle = correction["cle"]
    if correction["type"] in MODES_DE_L_AGENT:
        voulu = MODES_DE_L_AGENT[correction["type"]]
        if voulu is None:
            configurations.pop("blocs_mode", None)
        else:
            configurations["blocs_mode"] = voulu
        return graphe, configurations, 1
    if correction["type"] in MODES_DE_BLOC:
        etiquette = f.decouper(cle)
        if etiquette is None or etiquette.famille != f.BLOC:
            raise CorrectionRefusee("Only a reusable block has a mode.")
        slug = f.bloc_et_version(etiquette.cle)[0]
        modes = dict(configurations.get("blocs_modes") or {})
        voulu = MODES_DE_BLOC[correction["type"]]
        if voulu is None:
            modes.pop(slug, None)
        else:
            modes[slug] = voulu
        if modes:
            configurations["blocs_modes"] = modes
        else:
            configurations.pop("blocs_modes", None)
        return graphe, configurations, 1
    if correction["type"] == "rattacher":
        e = f.decouper(cle)
        if e is None or e.famille != f.OUTIL:
            raise CorrectionRefusee("Only a tool is attached to a step.")
        uuid = f.outil_et_fonction(e.cle)[0]
        for n in graphe.get("nodes") or []:
            if str(n.get("id")) == str(correction.get("noeud_id")):
                outils = list((n.get("data") or {}).get("tool_uuids") or [])
                if uuid in outils:
                    return graphe, configurations, 0
                n.setdefault("data", {})["tool_uuids"] = [*outils, uuid]
                return graphe, configurations, 1
        raise CorrectionRefusee("This step does not exist any more.")
    motif = _motif_de(cle)
    neuf = _remplacement(correction)
    champ = correction.get("champ")
    total = 0
    noeuds = []
    for n in graphe.get("nodes") or []:
        donnees, k = _reecrire(n.get("data") or {}, f"nodes[{n.get('id')}]", champ, motif, neuf)
        noeuds.append({**n, "data": donnees})
        total += k
    if "nodes" in graphe:
        graphe["nodes"] = noeuds
    aretes = []
    for a in graphe.get("edges") or []:
        donnees, k = _reecrire(a.get("data") or {}, f"edges[{a.get('id')}]", champ, motif, neuf)
        aretes.append({**a, "data": donnees})
        total += k
    if "edges" in graphe:
        graphe["edges"] = aretes
    configurations, k = _reecrire(configurations, "configurations", champ, motif, neuf)
    return graphe, configurations, total + k


async def corriger(workflow: Any, organisation_id: int, correction: dict[str, Any]) -> dict[str, Any]:
    """Écrit la correction dans le brouillon de l'agent (créé depuis la version en ligne s'il n'existe pas). Rend le diagnostic."""
    from api.db import db_client
    from api.services.etiquettes_prompt.catalogue import problemes_du_brouillon
    from api.services.workflow.dto import ReactFlowDTO

    brouillon = await db_client.get_draft_version(workflow.id)
    if brouillon is None:
        brouillon = await db_client.save_workflow_draft(workflow.id)
    graphe = getattr(brouillon, "workflow_json", None) or {}
    configurations = getattr(brouillon, "workflow_configurations", None) or {}
    nouveau, configs, n = appliquer(graphe, configurations, correction)
    if n == 0 and correction["type"] != "rattacher":
        raise CorrectionRefusee("This label is not in the draft any more: read the list again.")
    if nouveau != graphe:
        try:
            ReactFlowDTO.model_validate(nouveau)
        except Exception as erreur:  # noqa: BLE001 -- jamais un graphe que le moteur refuse
            raise CorrectionRefusee("The fix would leave the graph invalid.") from erreur
    if nouveau != graphe or configs != configurations:
        await db_client.update_workflow(
            workflow_id=workflow.id,
            name=None,
            workflow_definition=nouveau if nouveau != graphe else None,
            template_context_variables=None,
            workflow_configurations=configs if configs != configurations else None,
            organization_id=organisation_id,
        )
    logger.info(f"[.mark] étiquettes : correction « {correction['type']} » écrite dans le brouillon de l'agent {workflow.id}")
    return {"problemes": [p.en_dict() for p in await problemes_du_brouillon(organisation_id, await db_client.get_draft_version(workflow.id))]}


# --- « Utilisé dans » -----------------------------------------------------------------------------------------------------


def citations_dans(cle: str, agents: list[tuple[int, str, dict | None, dict | None]]) -> list[dict[str, Any]]:
    """Pure. Les champs des agents qui citent ``cle`` (un bloc : toutes ses écritures, avec le choix « suivre / rester »)."""
    from api.services.etiquettes_prompt.catalogue import textes_du_brouillon

    motif = _motif_de(cle)
    sortie: list[dict[str, Any]] = []
    slug_du_bloc = f.bloc_et_version(cle.split(":", 1)[1])[0] if cle.startswith("bloc:") else None
    for identifiant, nom, graphe, configs in agents:
        par_bloc = (configs or {}).get("blocs_modes") if isinstance(configs, dict) else None
        mode_du_bloc = par_bloc.get(slug_du_bloc) if slug_du_bloc and isinstance(par_bloc, dict) else None
        mode_de_l_agent = (configs or {}).get("blocs_mode") if isinstance(configs, dict) else None
        for champ, noeud_id, etape, texte, _n in textes_du_brouillon(graphe, configs):
            for m in motif.finditer(texte):
                cite = m.group(0)[2:-2].strip()
                version = f.bloc_et_version(f.decouper(cite).cle)[1] if cite.startswith("bloc:") else None
                sortie.append(
                    {"agent_id": identifiant, "agent": nom, "noeud_id": noeud_id, "etape": etape, "champ": champ, "cle": cite, "version": version}
                    | ({"mode_du_bloc": mode_du_bloc, "mode_de_l_agent": mode_de_l_agent} if slug_du_bloc else {})
                )
                break
    return sortie


async def utilise_dans(organisation_id: int, cle: str) -> list[dict[str, Any]]:
    """Les prompts des agents de l'organisation qui citent ``cle`` : le brouillon s'il existe, sinon la version en ligne."""
    from api.db import db_client

    agents = []
    for workflow in await db_client.list_workflows_for_model_configuration_migration(organisation_id):
        definitions = list(getattr(workflow, "definitions", None) or [])
        source = next((d for d in definitions if d.status == "draft" and getattr(d, "branch_id", None) is None), None)
        if source is None:
            source = next((d for d in definitions if d.id == getattr(workflow, "released_definition_id", None)), None)
        if source is not None:
            agents.append((workflow.id, workflow.name, source.workflow_json, source.workflow_configurations))
    return citations_dans(cle, agents)
