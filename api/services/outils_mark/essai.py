"""[.mark] U3 sexies point 4 : l'essai de tous les types d'outils.

Avant : HTTP seulement. Maintenant : requête HTTP, action d'un logiciel, outil MCP, calculatrice.

Règle d'un outil qui ÉCRIT : il ne s'essaie jamais « pour de vrai » sans un choix de la personne,
* ``simule`` : réponse enregistrée (HTTP) ou validation à blanc des paramètres (action d'un logiciel) ; rien ne part ;
* ``compte_de_test`` : la personne affirme que l'identifiant de l'outil est celui d'un compte de test.
Un outil qui lit s'essaie directement. Un outil MCP est traité comme un outil qui écrit (le serveur ne le dit pas).

« Premier essai validé par une personne » : la route d'essai note le dernier essai (``dernier_essai``) dans la
configuration de l'outil ; seule une personne le valide (``premier_essai``), et seulement après un essai réussi.
Aucun appel à un éditeur dans les tests : les réponses sont enregistrées en fichier.
"""

from __future__ import annotations

import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from api.enums import ToolCategory

MODES = ("direct", "simule", "compte_de_test")
APERCU_MAX = 2000
CHAMPS_DU_SERVEUR = ("premier_essai", "dernier_essai")


class ErreurEssai(Exception):
    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut
        self.message = message


def conserver_les_champs_du_serveur(ancienne: dict[str, Any] | None, nouvelle: dict[str, Any]) -> dict[str, Any]:
    """Une mise à jour de l'outil garde ``premier_essai`` et ``dernier_essai`` : ils sont écrits par le serveur."""
    ancienne_config = ((ancienne or {}).get("config")) or {}
    config = dict(nouvelle.get("config") or {}) if isinstance(nouvelle.get("config"), dict) else None
    if config is None:
        return nouvelle
    for cle in CHAMPS_DU_SERVEUR:
        if ancienne_config.get(cle) is not None:
            config[cle] = ancienne_config[cle]
        else:
            config.pop(cle, None)
    return {**nouvelle, "config": config}


def _config(outil: Any) -> dict[str, Any]:
    return ((getattr(outil, "definition", None) or {}).get("config")) or {}


def categorie_de(outil: Any) -> str:
    return str(getattr(outil.category, "value", outil.category))


def ecrit(outil: Any) -> bool:
    """L'outil écrit-il chez le client ? HTTP : toute méthode autre que GET sauf « sans risque de doublon » ;
    action d'un logiciel : ce que le catalogue en dit ; MCP : oui (inconnu, donc traité comme tel)."""
    categorie = categorie_de(outil)
    config = _config(outil)
    if categorie == ToolCategory.HTTP_API.value:
        return str(config.get("method") or "POST").upper() != "GET" and not config.get("sans_risque_de_doublon")
    if categorie == ToolCategory.INTEGRATION.value:
        from api.services.integrations.connectors.catalogue import trouver

        trouve = trouver(str(config.get("connecteur") or ""), str(config.get("action") or ""))
        return True if trouve is None else bool(trouve[1].ecrit)
    if categorie == ToolCategory.MCP.value:
        return True
    return False


def _apercu(donnees: Any) -> Any:
    texte = str(donnees)
    return donnees if len(texte) <= APERCU_MAX else texte[:APERCU_MAX] + "…"


def _verdict(mode: str, reussi: bool, duree_ms: int, message: str, donnees: Any = None, **plus: Any) -> dict[str, Any]:
    return {
        "reussi": reussi,
        "mode": mode,
        "duree_ms": duree_ms,
        "message": message,
        "donnees": _apercu(donnees) if donnees is not None else None,
        **plus,
    }


async def essayer(outil: Any, organization_id: int, arguments: dict[str, Any], mode: str, *, outil_mcp: str | None = None) -> dict[str, Any]:
    """Essaie l'outil. Lève ``ErreurEssai`` pour un refus normal (type non essayable, écriture sans choix, rien à servir)."""
    if mode not in MODES:
        raise ErreurEssai(422, f"Mode must be one of: {', '.join(MODES)}.")
    categorie = categorie_de(outil)
    ecrit_chez_le_client = ecrit(outil)
    if ecrit_chez_le_client and mode == "direct":
        raise ErreurEssai(
            409,
            "This tool writes at the client's: try it on a simulated answer, or confirm that its credential is a test account.",
        )
    debut = time.perf_counter()
    if categorie == ToolCategory.HTTP_API.value:
        verdict = await _essai_http(outil, organization_id, arguments, mode)
    elif categorie == ToolCategory.INTEGRATION.value:
        verdict = await _essai_logiciel(outil, organization_id, arguments, mode)
    elif categorie == ToolCategory.MCP.value:
        if mode == "simule":
            raise ErreurEssai(422, "An MCP server has no simulated answer: try it on a test account.")
        verdict = await _essai_mcp(outil, organization_id, arguments, outil_mcp)
    elif categorie == ToolCategory.CALCULATOR.value:
        verdict = _essai_calculatrice(arguments)
    else:
        raise ErreurEssai(400, f"A tool of type {categorie} cannot be tried here.")
    verdict["duree_ms"] = verdict.get("duree_ms") or round((time.perf_counter() - debut) * 1000)
    verdict["ecrit"] = ecrit_chez_le_client
    return verdict


async def _essai_http(outil: Any, organization_id: int, arguments: dict[str, Any], mode: str) -> dict[str, Any]:
    from api.services.workflow.tools.custom_tool import execute_http_tool

    config = _config(outil)
    if mode == "simule" and not config.get("reponses_simulees"):
        raise ErreurEssai(422, "This tool has no simulated answer: write one in its Response tab first.")
    fiche: dict[str, Any] = {}
    debut = time.perf_counter()
    reponse = await execute_http_tool(
        outil,
        arguments,
        organization_id=organization_id,
        include_request_headers=True,
        simuler=mode == "simule",
        fiche_cible=fiche,
    )
    duree = round((time.perf_counter() - debut) * 1000)
    reussi = reponse.get("status") == "success"
    return _verdict(
        mode,
        reussi,
        duree,
        "The service answered." if reussi else str(reponse.get("error") or f"HTTP {reponse.get('status_code')}"),
        reponse.get("data"),
        statut_http=reponse.get("status_code"),
        copies=reponse.get("copies_dans_la_fiche") or {},
        simulee=bool(reponse.get("simulee")),
        requete={"methode": str(config.get("method") or "POST").upper(), "adresse": reponse.get("rendered_url") or config.get("url"), "en_tetes": reponse.get("request_headers", {})},
    )


async def _essai_logiciel(outil: Any, organization_id: int, arguments: dict[str, Any], mode: str) -> dict[str, Any]:
    from api.services.integrations.connectors.catalogue import trouver
    from api.services.integrations.connectors.execution import arguments_permis, executer, manquants

    config = _config(outil)
    trouve = trouver(str(config.get("connecteur") or ""), str(config.get("action") or ""))
    if trouve is None:
        raise ErreurEssai(422, "This action is not in the catalogue.")
    _, action = trouve
    args = arguments_permis(action, arguments)
    absents = manquants(action, args)
    if absents:
        return _verdict(mode, False, 0, f"Missing: {', '.join(absents)}.", manquants=absents)
    if mode == "simule":
        return _verdict(mode, True, 0, "Parameters valid. Nothing was sent to the software.", {"parametres": args}, simulee=True)
    resultat = await executer(organization_id, config, args, {})
    reussi = resultat.statut == "ok"
    return _verdict(mode, reussi, resultat.duree_ms, "The software answered." if reussi else (resultat.message or "Failed."), resultat.donnees if reussi else None)


async def appeler_outil_mcp(outil: Any, organization_id: int, nom: str, arguments: dict[str, Any]) -> Any:
    """Une session éphémère sur le serveur, un appel, fermeture. (Point d'insertion des tests : réponses enregistrées.)"""
    from api.services.outils_mark.mcp import entetes_du_serveur
    from api.services.tool_management import fetch_credential
    from api.services.workflow.mcp_tool_session import McpToolSession
    from api.services.workflow.tools.mcp_tool import validate_mcp_definition

    cfg = validate_mcp_definition(outil.definition)
    session = McpToolSession(
        tool_uuid=outil.tool_uuid,
        tool_name=outil.name,
        url=cfg["url"],
        credential=await fetch_credential(cfg.get("credential_uuid"), organization_id),
        tools_filter=[],
        timeout_secs=cfg["timeout_secs"],
        sse_read_timeout_secs=cfg["sse_read_timeout_secs"],
        transport=cfg.get("transport", "streamable_http"),
        extra_headers=await entetes_du_serveur(cfg, organization_id) or None,
    )
    await session.start()
    try:
        if not session.available:
            raise RuntimeError("The MCP server is unreachable.")
        nom_complet = next((n for n, brut in session._name_map.items() if brut == nom), None)  # noqa: SLF001
        if nom_complet is None:
            raise RuntimeError(f"The server has no tool named {nom}.")
        return await session.call(nom_complet, arguments)
    finally:
        await session.close()


async def _essai_mcp(outil: Any, organization_id: int, arguments: dict[str, Any], nom: str | None) -> dict[str, Any]:
    if not nom:
        raise ErreurEssai(422, "Name the MCP tool to try.")
    debut = time.perf_counter()
    try:
        sortie = await appeler_outil_mcp(outil, organization_id, nom, arguments)
    except Exception as erreur:  # noqa: BLE001 -- un essai qui échoue est un verdict, pas une panne
        logger.warning(f"[outils] essai MCP en échec : {type(erreur).__name__}")
        return _verdict("compte_de_test", False, round((time.perf_counter() - debut) * 1000), str(erreur))
    return _verdict("compte_de_test", True, round((time.perf_counter() - debut) * 1000), "The server answered.", sortie)


def _essai_calculatrice(arguments: dict[str, Any]) -> dict[str, Any]:
    from api.services.workflow.tools.calculator import safe_calculator

    expression = str((arguments or {}).get("expression") or "").strip()
    if not expression:
        raise ErreurEssai(422, "Give an expression to calculate.")
    try:
        return _verdict("direct", True, 0, "Calculated.", {"expression": expression, "result": safe_calculator(expression)})
    except Exception as erreur:  # noqa: BLE001
        return _verdict("direct", False, 0, str(erreur))


def noter_le_dernier_essai(definition: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    """La définition avec ``dernier_essai`` à jour. Un nouvel essai réussi n'efface pas un premier essai déjà validé."""
    neuve = deepcopy(definition or {})
    config = neuve.setdefault("config", {})
    if not isinstance(config, dict):
        return neuve
    config["dernier_essai"] = {
        "reussi": bool(verdict.get("reussi")),
        "mode": verdict.get("mode"),
        "le": datetime.now(UTC).isoformat(),
    }
    return neuve


def valider_le_premier_essai(definition: dict[str, Any], valideur: str) -> dict[str, Any]:
    """Une personne valide le premier essai. Refusé sans essai réussi. Un outil sans configuration (calculatrice) n'en a pas."""
    config = (definition or {}).get("config")
    if not isinstance(config, dict):
        raise ErreurEssai(400, "This tool has no first trial to validate.")
    dernier = config.get("dernier_essai") or {}
    if not dernier.get("reussi"):
        raise ErreurEssai(409, "Try the tool successfully first.")
    neuve = deepcopy(definition)
    neuve["config"]["premier_essai"] = {
        "valide_par": valideur,
        "valide_le": datetime.now(UTC).isoformat(),
        "mode": dernier.get("mode"),
    }
    return neuve
