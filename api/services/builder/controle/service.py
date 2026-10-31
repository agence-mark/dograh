"""[.mark] Builder, lot 5 : le contrôle du prompt d'un agent réel (charge ce qu'il faut, applique les règles pures).

Lit le brouillon de l'agent (sinon sa version publiée), ses outils, les phrases que le code dit (règles réglées + défauts des
motifs actifs + fins figées), ses objets (base du client : injoignable = ``None``, on ne bloque pas dessus) et les variables
que le code pose (lues dans le code, ``objets_agent.noms_poses_par_le_code`` : jamais une liste recopiée ici).

Le résultat sert trois portes : l'action ``prompt_controler`` (builder et MCP), la carte « Contrôle » de l'écran, et la garde
de publication (``publication.py``).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db import db_client
from api.services.builder.controle import regles
from api.services.builder.controle.regles import AVERTISSEMENT, BLOQUANT, Defaut, Entree, ObjetConnu, OutilConnu

# Le tableau de chaque règle : ce qui rend le contrôle lisible par une carte générique (statut, message).
STATUT_ECHEC = "echec"
STATUT_AVERTISSEMENT = "avertissement"


async def graphe_de_travail(workflow: Any) -> dict[str, Any]:
    from api.services.builder.brouillon import source_courante

    graphe, _ = await source_courante(workflow)
    return graphe or {"nodes": [], "edges": []}


def _noeuds(graphe: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in graphe.get("nodes") or [] if isinstance(n, dict)]


async def _outils(graphe: dict[str, Any], organisation_id: int) -> dict[str, OutilConnu]:
    uuids: list[str] = []
    for n in _noeuds(graphe):
        brut = (n.get("data") or {}).get("tool_uuids")
        uuids += [u for u in brut if isinstance(u, str)] if isinstance(brut, list) else []
    if not uuids:
        return {}
    try:
        lignes = await db_client.get_tools_by_uuids(sorted(set(uuids)), organisation_id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[builder] outils non lus pour le contrôle : {type(erreur).__name__}")
        return {}
    sortie: dict[str, OutilConnu] = {}
    for t in lignes:
        config = ((t.definition or {}).get("config") or {}) if isinstance(t.definition, dict) else {}
        sortie[t.tool_uuid] = OutilConnu(
            uuid=t.tool_uuid,
            nom=t.name,
            categorie=str(getattr(t.category, "value", t.category)),
            methode=str(config.get("method", "POST")).upper() if str(getattr(t.category, "value", t.category)) == "http_api" else None,
        )
    return sortie


def phrases_du_code(configurations: dict[str, Any], graphe: dict[str, Any]) -> list[str]:
    """Toutes les phrases que le CODE dit : règles réglées, défauts des motifs actifs, fins figées des étapes."""
    from api.services.phrases.catalogue import MOTIFS
    from api.services.phrases.regles import regles_de

    phrases: list[str] = []
    reglees = regles_de(configurations)
    motifs_reglees = {r.motif for r in reglees}
    for r in reglees:
        if r.active:
            phrases += list(r.variantes)
    for motif in MOTIFS.values():
        if motif.id not in motifs_reglees and motif.actif_par_defaut:
            phrases += list(motif.variantes_defaut)
    for n in _noeuds(graphe):
        for fin in (n.get("data") or {}).get("fins") or []:
            if isinstance(fin, dict) and fin.get("phrase"):
                phrases.append(str(fin["phrase"]))
    return phrases


async def objets_du_client(organisation_id: int) -> list[ObjetConnu] | None:
    """Les objets de l'agent (texte rendu). ``[]`` : pas de base rattachée. ``None`` : la base ne répond pas."""
    from api.db.bases_clients.connexion import connecter
    from api.db.bases_clients.objets import lire_objets
    from api.services.base_client.rattachement import nom_de_la_base
    from api.services.objets_agent.rendu import rendre

    try:
        base = await nom_de_la_base(organisation_id)
        if not base:
            return []
        connexion = await connecter(base)
        try:
            return [ObjetConnu(nom=o.nom, texte=rendre(o)) for o in await lire_objets(connexion)]
        finally:
            await connexion.close()
    except Exception as erreur:  # noqa: BLE001 -- même logique que le moteur : on ne bloque pas
        logger.warning(f"[builder] objets non lus pour le contrôle ({type(erreur).__name__})")
        return None


async def _variables_de_l_agent(organisation_id: int, workflow: Any, graphe: dict[str, Any], configurations: dict[str, Any]) -> frozenset[str]:
    noms: set[str] = set(getattr(workflow, "template_context_variables", None) or {})
    for n in _noeuds(graphe):
        for v in (n.get("data") or {}).get("extraction_variables") or []:
            if isinstance(v, dict) and v.get("name"):
                noms.add(str(v["name"]))
    for champ in configurations.get("fiche_champs") or []:
        nom = champ.get("nom") if isinstance(champ, dict) else getattr(champ, "nom", None)
        if nom:
            noms.add(str(nom))
    try:
        from api.services.etablissements.copie import lire_copie_complete

        copie = await lire_copie_complete(organisation_id)
        noms |= {p.variable for p in copie.phrases.phrases}
        for e in copie.etablissements.etablissements:
            noms |= set((e.phrases or {}).keys())
    except Exception:  # noqa: BLE001
        pass
    return frozenset(noms)


def genre_de_la_voix(configurations: dict[str, Any]) -> str | None:
    """Le genre de la voix choisie, SEULEMENT s'il est relevé dans le catalogue (jamais deviné)."""
    try:
        from api.services.configuration.options.soniox import SONIOX_TTS_VOIX

        voix = ((configurations.get("model_overrides") or {}).get("tts") or {}).get("voice")
        for v in SONIOX_TTS_VOIX:
            if v["id"] == voix and v.get("genre"):
                g = str(v["genre"]).lower()
                return "f" if g.startswith("f") else "m" if g.startswith("m") else None
    except Exception:  # noqa: BLE001
        return None
    return None


async def construire_l_entree(workflow: Any, organisation_id: int, *, graphe: dict[str, Any] | None = None) -> Entree:
    from api.services.modeles_reglages import service as modeles
    from api.services.objets_agent.noms_poses_par_le_code import variables_posees_par_le_code
    from api.services.workflow.signaler_un_probleme import NOM_OUTIL

    graphe = graphe if graphe is not None else await graphe_de_travail(workflow)
    try:
        configurations = (await modeles.configuration_active(workflow.id, organisation_id))["configurations"]
    except Exception:  # noqa: BLE001
        configurations = dict(getattr(workflow, "workflow_configurations", None) or {})
    return Entree(
        graphe=graphe,
        outils=await _outils(graphe, organisation_id),
        noms_d_outils_du_moteur=(NOM_OUTIL,),
        phrases_du_code=phrases_du_code(configurations, graphe),
        objets=await objets_du_client(organisation_id),
        variables_posees_par_le_code=variables_posees_par_le_code(),
        variables_de_l_agent=await _variables_de_l_agent(organisation_id, workflow, graphe, configurations),
        genre_de_la_voix=genre_de_la_voix(configurations),
    )


def rendre_le_resultat(defauts: list[Defaut]) -> dict[str, Any]:
    """La forme rendue par ``prompt_controler`` : ``ok`` (aucun bloquant), les deux listes, et des ``elements`` pour la carte."""
    bloquants = [d for d in defauts if d.gravite == BLOQUANT]
    avertissements = [d for d in defauts if d.gravite == AVERTISSEMENT]
    elements = [
        {
            "statut": STATUT_ECHEC if d.gravite == BLOQUANT else STATUT_AVERTISSEMENT,
            "message": d.message + (f" [{d.etape}]" if d.etape else ""),
            "code": d.code,
            "etape": d.etape,
            "extrait": d.extrait,
        }
        for d in defauts
    ]
    return {
        "ok": not bloquants,
        "bloquants": [d.en_json() for d in bloquants],
        "avertissements": [d.en_json() for d in avertissements],
        "elements": elements,
        "carte": {"type": "controle", "ok": not bloquants, "elements": elements},
    }


async def controler_l_agent(workflow: Any, organisation_id: int, *, graphe: dict[str, Any] | None = None) -> dict[str, Any]:
    entree = await construire_l_entree(workflow, organisation_id, graphe=graphe)
    return rendre_le_resultat(regles.controler(entree))
