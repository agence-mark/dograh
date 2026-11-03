"""[.mark] Où vivent les étiquettes (U3, E30) : AUCUNE migration.

La liste des étiquettes de l'organisation et les étiquettes de chaque agent sont une seule valeur JSON de
``organization_configurations``, clé ``MARK_ETIQUETTES`` (donc cloisonnée par organisation par construction) :

    {"etiquettes": ["Recette", "Banc"], "agents": {"12": ["Recette"], "30": ["Banc", "Recette"]}}

* une étiquette se crée pour toute l'organisation ;
* une étiquette qui n'a plus aucun agent reste proposée à la pose (``etiquettes``) mais DISPARAÎT du filtre de la liste
  (``nb_agents`` = 0) ;
* l'identifiant d'un agent supprimé ou archivé ne compte plus (lu à chaque fois contre les agents actifs, jamais
  stocké comme vrai).

Écriture : comparer-puis-écrire (``compare_and_set_configuration``), reprise si deux écritures se croisent : aucune
étiquette n'est perdue par une pose simultanée.
"""

from __future__ import annotations

import re
from typing import Any

from api.db import db_client
from api.enums import OrganizationConfigurationKey

CLE = OrganizationConfigurationKey.MARK_ETIQUETTES.value
NOM_MAX = 40
ETIQUETTES_MAX = 200
PAR_AGENT_MAX = 20
_TENTATIVES = 5


class ErreurEtiquette(ValueError):
    """Une étiquette refusée (nom vide ou trop long, trop d'étiquettes) : le message est rendu tel quel."""


def normaliser(nom: str) -> str:
    """Espaces compactés ; vide ou trop long refusé."""
    propre = re.sub(r"\s+", " ", str(nom or "")).strip()
    if not propre:
        raise ErreurEtiquette("An empty label is not a label.")
    if len(propre) > NOM_MAX:
        raise ErreurEtiquette(f"A label has {NOM_MAX} characters at most.")
    return propre


def _sans_doublon(noms: list[str]) -> list[str]:
    """Sans doublon, sans tenir compte de la casse ; la première écriture garde sa casse."""
    vus: dict[str, str] = {}
    for nom in noms:
        vus.setdefault(nom.casefold(), nom)
    return list(vus.values())


def lire_brut(valeur: Any) -> dict[str, Any]:
    """Une valeur stockée, remise en forme (jamais d'exception sur une valeur abîmée : elle est lue comme vide)."""
    if not isinstance(valeur, dict):
        return {"etiquettes": [], "agents": {}}
    etiquettes = [e for e in valeur.get("etiquettes", []) if isinstance(e, str) and e.strip()]
    agents = {
        str(k): [e for e in v if isinstance(e, str)]
        for k, v in (valeur.get("agents") or {}).items()
        if isinstance(v, list)
    }
    return {"etiquettes": _sans_doublon(etiquettes), "agents": agents}


async def _valeur(organisation_id: int) -> Any:
    ligne = await db_client.get_configuration(organisation_id, CLE)
    return ligne.value if ligne else None


def vue(brut: dict[str, Any], agents_actifs: set[int]) -> dict[str, Any]:
    """Ce que l'écran lit : les étiquettes (avec le nombre d'agents actifs) et celles de chaque agent actif."""
    par_agent = {int(k): v for k, v in brut["agents"].items() if k.isdigit() and int(k) in agents_actifs and v}
    compte: dict[str, int] = {}
    for noms in par_agent.values():
        for nom in noms:
            compte[nom.casefold()] = compte.get(nom.casefold(), 0) + 1
    return {
        "etiquettes": [{"nom": nom, "nb_agents": compte.get(nom.casefold(), 0)} for nom in brut["etiquettes"]],
        "par_agent": par_agent,
    }


async def agents_actifs(organisation_id: int) -> set[int]:
    liste = await db_client.get_all_workflows_for_listing(organization_id=organisation_id, status="active")
    return {w.id for w in liste}


async def lire(organisation_id: int) -> dict[str, Any]:
    return vue(lire_brut(await _valeur(organisation_id)), await agents_actifs(organisation_id))


async def poser(organisation_id: int, workflow_id: int, noms: list[str]) -> dict[str, Any]:
    """Remplace les étiquettes de l'agent (les nouvelles sont créées pour toute l'organisation).

    ``noms`` vide retire toutes les étiquettes de l'agent. L'appelant a déjà contrôlé que l'agent est de l'organisation.
    """
    voulues = _sans_doublon([normaliser(n) for n in noms])
    if len(voulues) > PAR_AGENT_MAX:
        raise ErreurEtiquette(f"An agent has {PAR_AGENT_MAX} labels at most.")
    for _ in range(_TENTATIVES):
        avant = await _valeur(organisation_id)
        brut = lire_brut(avant)
        existantes = {e.casefold(): e for e in brut["etiquettes"]}
        # Une étiquette déjà connue garde sa casse d'origine : « recette » pose « Recette ».
        retenues = [existantes.get(n.casefold(), n) for n in voulues]
        toutes = _sans_doublon([*brut["etiquettes"], *retenues])
        if len(toutes) > ETIQUETTES_MAX:
            raise ErreurEtiquette(f"An organization has {ETIQUETTES_MAX} labels at most.")
        agents = dict(brut["agents"])
        if retenues:
            agents[str(workflow_id)] = retenues
        else:
            agents.pop(str(workflow_id), None)
        apres = {"etiquettes": toutes, "agents": agents}
        if await db_client.compare_and_set_configuration(organisation_id, CLE, avant, apres):
            return await lire(organisation_id)
    raise ErreurEtiquette("The labels are being changed elsewhere. Try again.")
