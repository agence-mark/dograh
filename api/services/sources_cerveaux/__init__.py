"""[.mark] U12 (E104) : la source de chaque cerveau, brique par brique : Claude Code (l'abonnement de la personne) ou une clé d'API.

Un seul réglage par brique, dans une ligne de ``organization_configurations`` (``MARK_SOURCES``, aucune migration). Cinq briques :
le builder (les sous-agents le suivent), l'appelant simulé, le juge des tests, le juge des vrais appels, l'analyse des appels.
**L'agent garde toujours ses clés** (transcription, modèle, voix) : ce module ne le touche jamais.

* Au départ, tout est sur **Claude Code** (``DEFAUT``) : aucun appel à un fournisseur tant qu'on n'a pas choisi la clé.
* Une brique sur Claude Code ne fait AUCUN appel à un fournisseur : elle attend une session (outils MCP).
* Compatibilité : avant U12, le rôle de l'appelant ou du juge portait sa propre ``source``. La ligne de ce module gagne ; sans ligne,
  un rôle qui dit « claude_code » reste respecté (sinon ``DEFAUT``). Les réglages de l'appelant et du juge relus pour l'écran portent la
  source effective (``surcharger_les_roles``).

⛔ Aucune clé ici : seulement le nom de la source.
"""

from __future__ import annotations

from typing import Any, Literal

from api.services.builder import stock

CLE_SOURCES = "MARK_SOURCES"

Brique = Literal["builder", "appelant", "juge_tests", "juge_appels", "analyse"]
Source = Literal["claude_code", "cle_api"]

BRIQUES: tuple[str, ...] = ("builder", "appelant", "juge_tests", "juge_appels", "analyse")
SOURCES: tuple[str, ...] = ("claude_code", "cle_api")
# E104 : tout sur Claude Code au départ (pas encore de rentrées, un abonnement Claude Max).
DEFAUT: str = "claude_code"
# Les briques qui lisent leurs réglages dans l'organisation du builder (la bibliothèque .mark), les autres dans celle de la personne.
BRIQUES_DU_BUILDER = ("builder",)


class SourceInconnue(ValueError):
    pass


async def _ligne(organisation: int) -> dict[str, str]:
    brut = await stock.lire(organisation, CLE_SOURCES) or {}
    return {b: s for b, s in brut.items() if b in BRIQUES and s in SOURCES}


async def source_de(organisation: int, brique: str, ancienne: str | None = None) -> str:
    """La source effective d'une brique. ``ancienne`` : la ``source`` du rôle d'avant U12 (respectée seulement si c'est Claude Code)."""
    if brique not in BRIQUES:
        raise SourceInconnue(f"Unknown brick: {brique}.")
    ligne = await _ligne(organisation)
    if brique in ligne:
        return ligne[brique]
    return "claude_code" if ancienne == "claude_code" else DEFAUT


async def toutes(organisation_builder: int, organisation: int) -> dict[str, str]:
    """Les cinq sources effectives : le builder dans l'organisation du builder, les autres dans celle de la personne."""
    sorties: dict[str, str] = {}
    for brique in BRIQUES:
        sorties[brique] = await source_de(organisation_builder if brique in BRIQUES_DU_BUILDER else organisation, brique)
    return sorties


async def regler(organisation: int, brique: str, source: str) -> str:
    """Pose la source d'une brique ; refuse un nom inconnu. Rend la source posée."""
    if brique not in BRIQUES:
        raise SourceInconnue(f"Unknown brick: {brique}.")
    if source not in SOURCES:
        raise SourceInconnue(f"Unknown source: {source}.")

    def transformer(ligne: dict[str, Any] | None) -> dict[str, Any]:
        return {**(ligne or {}), brique: source}

    await stock.modifier(organisation, CLE_SOURCES, transformer)
    return source


async def surcharger_les_roles(organisation: int, roles: Any) -> Any:
    """Les réglages de l'appelant et du juge avec la source effective de leur brique (l'appelant ; le juge = celui des tests)."""
    appelant = await source_de(organisation, "appelant", roles.appelant.source)
    juge = await source_de(organisation, "juge_tests", roles.juge.source)
    return roles.model_copy(
        update={
            "appelant": roles.appelant.model_copy(update={"source": appelant}),
            "juge": roles.juge.model_copy(update={"source": juge}),
        }
    )


async def ecrire_depuis_les_roles(organisation: int, roles: Any) -> None:
    """L'enregistrement des réglages de l'appelant et du juge par l'écran (la fenêtre existante) range la source dans LA ligne des
    sources : un seul réglage par brique, jamais deux qui divergent. La brique « juge des vrais appels » suit le juge de la fenêtre
    quand elle n'a jamais été réglée à part."""
    deja = await _ligne(organisation)
    await regler(organisation, "appelant", roles.appelant.source)
    await regler(organisation, "juge_tests", roles.juge.source)
    if "juge_appels" not in deja:
        await regler(organisation, "juge_appels", roles.juge.source)
