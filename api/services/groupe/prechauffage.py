"""[.mark] Chantier agents-specialises, lot 6 (A5, A19) : le préchauffage SANS ouvrir la voix.

Décision d'Evan (16/10) : au décroché, pour chaque cible d'un outil ``transfer_agent`` du graphe du
principal (une passe, pas les cibles des cibles), on charge à l'avance ce qui ne coûte AUCUNE
connexion : la définition publiée, le graphe validé, la configuration effective des modèles et les
outils des étapes (ce que ``AgentRuntimeFactory.resolve_destination`` et ``build`` lisent en base, et
ce que ``CustomToolManager`` relit à chaque étape). On NE construit PAS le runtime, on ne démarre
aucun pipeline, on n'ouvre aucune connexion de voix ni de modèle : le runtime se construit à la
passation, plus vite grâce à ce cache.

Le cache est PROPRE À L'APPEL (il vit sur la fabrique d'agents de l'appel) et disparaît avec elle.
Une erreur de préchauffage n'ajoute rien au cache : la passation construit alors normalement, comme
avant. Aucun mot de métier ici.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Mapping

from loguru import logger

from api.enums import ToolCategory

# Au-delà, le préchauffage s'abandonne : il ne doit jamais retarder ni gêner l'appel.
PRECHAUFFAGE_DELAI_S = 15.0


@dataclass
class ChargeAgent:
    """Ce qui est lu à l'avance pour un agent appelé (rien de vivant : pas de service, pas de worker)."""

    workflow: Any
    definition: Any
    user_config: Any
    dto: Any  # le graphe validé (``ReactFlowDTO``) ; le ``WorkflowGraph`` se refait à chaque visite


@dataclass
class Precharge:
    """Le cache d'un appel. Rien n'y entre que par ``prechauffer`` (succès seulement)."""

    organization_id: int | None = None
    agents: dict[int, ChargeAgent] = field(default_factory=dict)
    # Les outils par identifiant, et les identifiants déjà interrogés (un identifiant interrogé et
    # absent = outil inactif ou d'une autre organisation : la base l'omettait aussi).
    _outils_par_uuid: dict[str, Any] = field(default_factory=dict, repr=False)
    _interroges: set[str] = field(default_factory=set, repr=False)
    # Mesures (écrites au journal et lues par les tests).
    duree_s: float | None = None
    echecs: dict[int, str] = field(default_factory=dict)

    async def outils(
        self,
        uuids: Iterable[str],
        organization_id: int,
        lire: Callable[[list[str], int], Awaitable[list]],
    ) -> list:
        """Les outils demandés, lus dans le cache quand tous y sont déjà ; sinon ``lire`` (la base),
        dont le résultat entre dans le cache. Jamais d'outil servi à une autre organisation."""
        demandes = [u for u in dict.fromkeys(uuids) if isinstance(u, str)]
        if not demandes:
            return []
        if self.organization_id is not None and organization_id != self.organization_id:
            return await lire(demandes, organization_id)
        if all(u in self._interroges for u in demandes):
            return [self._outils_par_uuid[u] for u in demandes if u in self._outils_par_uuid]
        trouves = await lire(demandes, organization_id)
        for outil in trouves:
            self._outils_par_uuid[getattr(outil, "tool_uuid", None)] = outil
        self._interroges.update(demandes)
        return list(trouves)


def precharge_de(engine: Any) -> Precharge | None:
    """Le cache de l'appel, ``None`` quand il n'y en a pas (agent seul, clavier, tests). Lecture
    par ``__dict__`` : un moteur simulé ne fabrique pas d'attribut. ⛔ Ne lève jamais."""
    try:
        fabrique = (getattr(engine, "__dict__", None) or {}).get("_agent_factory")
        precharge = (getattr(fabrique, "__dict__", None) or {}).get("precharge")
        return precharge if isinstance(precharge, Precharge) else None
    except Exception:  # noqa: BLE001
        return None


def cibles_de_passation(outils: Iterable[Any]) -> list[int]:
    """Les agents vers qui mènent des outils ``transfer_agent`` (dans l'ordre, sans doublon)."""
    cibles: list[int] = []
    for outil in outils:
        if getattr(outil, "category", None) != ToolCategory.TRANSFER_AGENT.value:
            continue
        vers = (((getattr(outil, "definition", None) or {}).get("config")) or {}).get(
            "workflow_id"
        )
        if isinstance(vers, int) and not isinstance(vers, bool) and vers not in cibles:
            cibles.append(vers)
    return cibles


def uuids_des_outils(graphe: Any) -> list[str]:
    """Les identifiants d'outils posés sur les étapes d'un graphe (``WorkflowGraph`` ou ``ReactFlowDTO``)."""
    vus: list[str] = []
    noeuds = getattr(graphe, "nodes", None) or {}
    for noeud in noeuds.values() if isinstance(noeuds, Mapping) else noeuds:
        donnees = getattr(noeud, "data", noeud)
        for u in getattr(donnees, "tool_uuids", None) or []:
            if isinstance(u, str) and u not in vus:
                vus.append(u)
    return vus


async def prechauffer_les_cibles(
    fabrique: Any,
    graphe_du_principal: Any,
    *,
    ids_a_exclure: Iterable[int] = (),
    lire_outils: Callable[[list[str], int], Awaitable[list]],
) -> Precharge | None:
    """Une passe : les outils de passation du graphe du principal, puis la charge de chaque cible.
    ⛔ Ne lève jamais ; ``None`` quand la fabrique n'a pas de cache (rien à faire)."""
    try:
        precharge = getattr(fabrique, "precharge", None)
        if not isinstance(precharge, Precharge):
            return None
        debut = time.monotonic()
        organisation = fabrique.organization_id
        outils = await precharge.outils(
            uuids_des_outils(graphe_du_principal), organisation, lire_outils
        )
        exclus = set(ids_a_exclure)
        cibles = [c for c in cibles_de_passation(outils) if c not in exclus]
        async with asyncio.timeout(PRECHAUFFAGE_DELAI_S):
            resultats = await asyncio.gather(
                *(fabrique.prechauffer(c, lire_outils=lire_outils) for c in cibles),
                return_exceptions=True,
            )
        for cible, resultat in zip(cibles, resultats):
            if isinstance(resultat, BaseException):
                precharge.echecs[cible] = repr(resultat)
        precharge.duree_s = time.monotonic() - debut
        logger.info(
            f"[prechauffage] {len(precharge.agents)}/{len(cibles)} agents chargés à l'avance "
            f"en {precharge.duree_s:.3f}s (aucune voix ni modèle ouverts)"
        )
        return precharge
    except Exception as e:  # noqa: BLE001 -- un préchauffage ne coûte jamais l'appel
        logger.warning(f"[prechauffage] abandonné, la passation construira normalement : {e!r}")
        return None
