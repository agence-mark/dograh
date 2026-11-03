"""[.mark] S2 / D153 / D163 : le canal d'un agent (``telephone`` ou ``site``) et les refus de cohérence.

Le canal est un réglage de l'agent (clé ``canal`` de ses réglages publiés). Absent = ``telephone`` : tout agent
existant garde son comportement. Un agent de site n'a jamais de numéro ni d'outil de transfert d'appel ; un
jeton d'intégration ne se crée pas sur un agent téléphonique. Les spécialisés héritent du canal de leur principal.
Fonctions pures : les routes les appellent avec ce qu'elles ont lu.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from api.enums import ToolCategory

CLE_CANAL = "canal"
TELEPHONE = "telephone"
SITE = "site"
CANAUX = (TELEPHONE, SITE)


def canal_de(configurations: Mapping | None, configurations_principal: Mapping | None = None) -> str:
    """Le canal d'un agent ; un spécialisé (``agent_principal_id`` posé) prend celui de son principal quand on le fournit."""
    source = configurations_principal if configurations_principal is not None else configurations
    propre = (source or {}).get(CLE_CANAL)
    return propre if propre in CANAUX else TELEPHONE


def refus_jeton_sur_agent(canal: str) -> str | None:
    if canal != SITE:
        return "An embed token needs a site agent: set the agent's channel to « site » first."
    return None


def refus_numero_sur_agent(canal: str) -> str | None:
    if canal == SITE:
        return "A site agent cannot be reached by phone: a phone number needs a telephone agent."
    return None


def outils_de_transfert(outils: Iterable[Any]) -> list[str]:
    """Les noms des outils de transfert d'APPEL (téléphone ou personne de l'équipe) parmi des ``ToolModel``."""
    trouves: list[str] = []
    for outil in outils:
        categorie = getattr(outil, "category", None)
        config = ((getattr(outil, "definition", None) or {}).get("config") or {}) if outil else {}
        if categorie == ToolCategory.TRANSFER_CALL.value or (
            categorie == ToolCategory.INTEGRATION.value
            and (config.get("connecteur"), config.get("action")) == ("equipe", "diriger_vers_personne")
        ):
            trouves.append(str(getattr(outil, "name", "") or getattr(outil, "tool_uuid", "")))
    return trouves


def refus_transfert_sur_agent_de_site(canal: str, outils: Iterable[Any]) -> str | None:
    if canal != SITE:
        return None
    noms = outils_de_transfert(outils)
    if noms:
        return "A site agent cannot hold a call-transfer tool (" + ", ".join(noms) + ")."
    return None
