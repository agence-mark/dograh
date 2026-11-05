"""[.mark] Lots 8 et 22 : le branchement du résolveur dans le moteur d'appel (``PipecatEngine``).

Le moteur ne connaît que deux gestes :

* ``preparer(engine, workflow)`` (asynchrone, une fois par graphe d'agent qui joue : l'agent d'accueil à l'initialisation, un
  spécialiste à son premier passage) lit la ``Table`` des objets cités par ce graphe ;
* ``rendre(engine, texte)`` (synchrone, dans ``_format_prompt``) remplace les étiquettes AVANT ``render_template``.

Rien ici ne lève : une étiquette qu'on ne sait pas lire disparaît (la publication l'a refusée avant).
"""

from __future__ import annotations

from typing import Any, Iterable

from loguru import logger

from api.services.etiquettes_prompt import resolution
from api.services.etiquettes_prompt.familles import MOTIF
from api.services.etiquettes_prompt.table import construire


def _chaines(valeur: Any) -> Iterable[str]:
    if isinstance(valeur, str):
        yield valeur
    elif isinstance(valeur, dict):
        for v in valeur.values():
            yield from _chaines(v)
    elif isinstance(valeur, (list, tuple)):
        for v in valeur:
            yield from _chaines(v)


def textes_du_graphe(workflow: Any) -> list[str]:
    """Les textes d'un ``WorkflowGraph`` qui portent au moins une étiquette."""
    textes: list[str] = []
    for noeud in (getattr(workflow, "nodes", None) or {}).values():
        donnees = getattr(noeud, "data", None)
        brut = donnees.model_dump() if hasattr(donnees, "model_dump") else {}
        textes.extend(t for t in _chaines(brut) if MOTIF.search(t))
    for arete in getattr(workflow, "edges", None) or []:
        donnees = getattr(arete, "data", None)
        brut = donnees.model_dump() if hasattr(donnees, "model_dump") else {}
        textes.extend(t for t in _chaines(brut) if MOTIF.search(t))
    return textes


async def preparer(engine: Any, workflow: Any) -> None:
    """Lit (une fois par graphe) la table des objets cités ; un graphe sans étiquette ne lit rien."""
    tables: dict[int, resolution.Table] = engine.__dict__.setdefault("_tables_etiquettes", {})
    if workflow is None or id(workflow) in tables:
        return
    textes = textes_du_graphe(workflow)
    if not textes:
        tables[id(workflow)] = resolution.Table()
        return
    try:
        organisation = await engine._get_organization_id()
        tables[id(workflow)] = await construire(
            organisation, textes, outils_epingles=getattr(workflow, "outils_epingles", None)
        )
    except Exception as erreur:  # noqa: BLE001 -- jamais une raison de rater un appel
        logger.warning(f"[.mark] étiquettes : table illisible ({type(erreur).__name__})")
        tables[id(workflow)] = resolution.Table()


def _phrase(engine: Any, cle: str) -> str | None:
    from api.services.phrases.catalogue import motif
    from api.services.phrases.regles import resoudre

    if motif(cle) is not None:
        phrase = resoudre(cle, reglages_agent=getattr(engine, "reglages_relances", None) or {})
        variantes = [v for v in (phrase.variantes if phrase else ()) if isinstance(v, str) and v.strip()]
        return variantes[0] if variantes else None
    valeur = (getattr(engine, "_call_context_vars", None) or {}).get(cle)
    return valeur if isinstance(valeur, str) else None


def rendre(engine: Any, texte: str | None) -> str | None:
    if not texte or "{{" not in texte or not MOTIF.search(texte):
        return texte
    agent = getattr(engine, "_active_agent", None)
    workflow = getattr(agent, "workflow", None) or getattr(engine, "workflow", None)
    table = (engine.__dict__.get("_tables_etiquettes") or {}).get(id(workflow))
    etapes = {str(i): n.name for i, n in (getattr(workflow, "nodes", None) or {}).items()}
    return resolution.rendre(texte, table, etapes=etapes, phrase=lambda c: _phrase(engine, c))
