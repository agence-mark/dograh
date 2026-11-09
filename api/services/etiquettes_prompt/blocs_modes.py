"""[.mark] Clôture, lot B (D17) : un bloc réutilisable se SUIT en direct ou se FIGE à la publication, par agent et par bloc.

Trois écritures, de la plus forte à la plus faible :

1. ``{{bloc:x@vN}}`` dans le graphe : la personne a choisi une version, rien ne la change ;
2. réglage du bloc sur cet agent (``blocs_modes`` = ``{slug: "direct" | "fige"}``) ;
3. réglage de l'agent (``blocs_mode``) ; non posé : « figé » si l'agent est protégé (D5), « direct » sinon.

Pas de migration : les réglages vivent dans ``workflow_configurations`` de l'agent, l'épingle dans ``outils_epingles`` de la version
publiée sous la clé ``bloc:<slug>`` (voir ``db/outils_epingles.py``). Changer un réglage ne touche jamais une version déjà publiée :
il vaut à la publication suivante. Pur, sauf ``epingles_a_la_publication`` (une lecture de la bibliothèque par bloc cité).
"""

from __future__ import annotations

from typing import Any, Iterable

from api.services.etiquettes_prompt import familles as f

CLE_AGENT = "blocs_mode"
CLE_BLOCS = "blocs_modes"
DIRECT = "direct"
FIGE = "fige"
MODES = (DIRECT, FIGE)


def _mode(valeur: Any) -> str | None:
    return valeur if isinstance(valeur, str) and valeur in MODES else None


def mode_de_l_agent(configurations: Any, protegee: bool) -> str:
    """Le mode de l'agent : celui qu'on a posé, sinon figé s'il est protégé, direct sinon."""
    pose = _mode((configurations or {}).get(CLE_AGENT)) if isinstance(configurations, dict) else None
    return pose or (FIGE if protegee else DIRECT)


def mode_effectif(configurations: Any, slug: str, protegee: bool) -> str:
    """Le mode d'un bloc sur cet agent : le réglage du bloc l'emporte sur celui de l'agent."""
    par_bloc = configurations.get(CLE_BLOCS) if isinstance(configurations, dict) else None
    pose = _mode(par_bloc.get(slug)) if isinstance(par_bloc, dict) else None
    return pose or mode_de_l_agent(configurations, protegee)


def valider_les_reglages(mode: Any, par_bloc: Any) -> str | None:
    """Un message d'erreur (liste fermée, slugs bornés) ou ``None`` si les réglages sont valides."""
    if mode is not None and _mode(mode) is None:
        return "blocs_mode must be 'direct' or 'fige'"
    if par_bloc is None:
        return None
    if not isinstance(par_bloc, dict) or len(par_bloc) > 200:
        return "blocs_modes must be an object of at most 200 entries"
    for slug, valeur in par_bloc.items():
        if not isinstance(slug, str) or not slug or len(slug) > 120 or _mode(valeur) is None:
            return "blocs_modes values must be 'direct' or 'fige'"
    return None


def _chaines(valeur: Any) -> Iterable[str]:
    if isinstance(valeur, str):
        yield valeur
    elif isinstance(valeur, dict):
        for v in valeur.values():
            yield from _chaines(v)
    elif isinstance(valeur, (list, tuple)):
        for v in valeur:
            yield from _chaines(v)


def blocs_suivis(graphe: Any) -> list[str]:
    """Les slugs cités SANS version (``{{bloc:x}}``) par le graphe, dans l'ordre, sans doublon. ``@vN`` n'en fait pas partie."""
    vus: list[str] = []
    for texte in _chaines(graphe):
        if "{{" not in texte:
            continue
        for e in f.etiquettes_de(texte):
            if e.famille != f.BLOC:
                continue
            slug, version = f.bloc_et_version(e.cle)
            if version is None and slug not in vus:
                vus.append(slug)
    return vus


async def epingles_a_la_publication(graphe: Any, configurations: Any, protegee: bool) -> dict[str, int]:
    """``{"bloc:<slug>": dernière version en Recette}`` des blocs dont le mode effectif est « figer ». Un bloc sans Recette n'a pas
    d'épingle (le contrôle de publication ``SANS_RECETTE`` le dit déjà). Mode « direct » : aucune épingle."""
    from api.db.outils_epingles import PREFIXE_BLOC
    from api.services.etiquettes_prompt.table import lire_un_bloc

    posees: dict[str, int] = {}
    for slug in blocs_suivis(graphe):
        if mode_effectif(configurations, slug, protegee) != FIGE:
            continue
        bloc = await lire_un_bloc(slug)
        recette = bloc.derniere_recette if bloc is not None else None
        if recette is not None:
            posees[f"{PREFIXE_BLOC}{slug}"] = recette.numero
    return posees
