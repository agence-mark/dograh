"""[.mark] Builder, lot 5 : l'essai d'un outil avant de le déclarer « branché » (Q11).

Un outil est appelé AVEC DES DONNÉES DE TEST (``donnees_fictives.est_fictive`` : une donnée qui a l'air réelle est refusée),
par le MÊME chemin que l'appel (``execute_http_tool``). « Branché » seulement sur une réponse VALIDE :

* le système a répondu en 2xx, sans délai dépassé ni erreur ;
* la réponse est du JSON non vide, qui ne dit pas elle-même un échec (``error``, ``success: false``, ``status: error``).

Tout le reste est « non branché » : l'étape ne doit rien promettre, elle passe au repli ``demander_un_rappel``. Seuls les outils
HTTP s'essaient ici ; les autres catégories (serveur MCP, connecteur, transfert) sont dites « non essayées » (donc non branchées).

Le résultat est rangé dans ``MARK_BUILDER:<agent>:outils`` pour que le rapport et la carte « Outils » le relisent. Aucune clé,
aucun en-tête n'est renvoyé. ⛔ Zéro vocabulaire métier.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.builder import stock
from api.services.builder.constantes import cle_builder
from api.services.builder.donnees_fictives import est_fictive

REPLI = "demander_un_rappel"
LONGUEUR_MAX_DE_LA_REPONSE = 400


class ErreurEssai(Exception):
    pass


def reponse_valide(resultat: dict[str, Any]) -> tuple[bool, str]:
    """(valide, raison). La réponse brute de ``execute_http_tool``."""
    if resultat.get("status") != "success":
        code = resultat.get("status_code")
        return False, f"The system answered with an error{f' (HTTP {code})' if code else ''}: {str(resultat.get('error') or '')[:120]}".rstrip(": ")
    donnees = resultat.get("data")
    if not isinstance(donnees, (dict, list)) or (isinstance(donnees, dict) and set(donnees) == {"raw_response"}):
        return False, "The answer is not JSON: nothing the agent could read."
    if not donnees:
        return False, "The answer is empty."
    if isinstance(donnees, dict):
        if donnees.get("success") is False or str(donnees.get("status", "")).lower() in ("error", "failed", "failure"):
            return False, "The answer says itself that it failed."
        if donnees.get("error"):
            return False, "The answer carries an error."
    return True, "The system answered with a valid answer."


async def _trouver(organisation_id: int, nom: str):
    for outil in await db_client.get_tools_for_organization(organisation_id):
        if outil.name == nom or outil.tool_uuid == nom:
            return outil
    return None


def methode_de(outil: Any) -> str:
    config = (getattr(outil, "definition", None) or {}).get("config") or {}
    return str(config.get("method") or "POST").upper()


def carte_a_valider(outil: Any, donnees_test: dict[str, Any]) -> dict[str, Any]:
    """Revue R5 : un essai qui ÉCRIT chez le client (toute méthode autre que GET) ne part pas sans un geste humain. Le builder rend
    cette carte ; la personne lance l'essai (route dédiée). Rien n'a été appelé, rien n'est rangé : l'outil n'est pas « branché »."""
    config = (getattr(outil, "definition", None) or {}).get("config") or {}
    methode, adresse = methode_de(outil), str(config.get("url") or "")
    message = f"{methode} {adresse} writes at the client's: a person must run this trial (button « Run the trial »). Nothing was called."
    return {
        "ok": True,
        "a_valider": True,
        "branche": False,
        "outil": outil.name,
        "methode": methode,
        "adresse": adresse,
        "donnees_test": donnees_test,
        "raison": "Waiting for a person to run the trial.",
        "elements": [{"statut": "avertissement", "message": f"{outil.name} : {message}"}],
        "carte": {"type": "essai_a_valider", "outil": outil.name, "methode": methode, "adresse": adresse, "donnees_test": donnees_test},
    }


async def essayer(
    organisation_id: int, workflow_id: int | None, nom: str, donnees_test: dict[str, Any], *, geste_humain: bool = False
) -> dict[str, Any]:
    """Essaie l'outil ``nom`` avec ``donnees_test``. Ne lève que ``ErreurEssai`` (refus normal).

    ``geste_humain`` : l'essai est lancé par une personne (route dédiée). Sans lui, seul un GET part directement ; toute autre
    méthode rend la carte « Essai à valider » (revue R5)."""
    if not est_fictive(donnees_test):
        raise ErreurEssai("The test data looks real (e-mail outside .test, phone outside the reserved ranges): use fictitious data only.")
    outil = await _trouver(organisation_id, nom)
    if outil is None:
        raise ErreurEssai(f"Unknown tool: {nom}.")
    categorie = str(getattr(outil.category, "value", outil.category))
    if categorie == "http_api" and not geste_humain and methode_de(outil) != "GET":
        return carte_a_valider(outil, donnees_test)
    if categorie != "http_api":
        resultat = _verdict(outil.name, False, f"A tool of category « {categorie} » cannot be tried here: it is not connected until a person tries it.", None, 0)
        await _ranger(organisation_id, workflow_id, resultat)
        return resultat
    debut = time.perf_counter()
    try:
        from api.services.workflow.tools.custom_tool import execute_http_tool

        reponse = await execute_http_tool(outil, donnees_test, organization_id=organisation_id)
    except Exception as erreur:  # noqa: BLE001 -- un outil qui plante = non branché, jamais une panne du builder
        logger.warning(f"[builder] essai de l'outil {outil.name} en échec : {type(erreur).__name__}")
        reponse = {"status": "error", "error": f"{type(erreur).__name__}"}
    duree_ms = round((time.perf_counter() - debut) * 1000)
    valide, raison = reponse_valide(reponse)
    resultat = _verdict(outil.name, valide, raison, reponse.get("status_code"), duree_ms, reponse.get("data") if valide else None)
    await _ranger(organisation_id, workflow_id, resultat)
    return resultat


def _verdict(nom: str, branche: bool, raison: str, statut_http: int | None, duree_ms: int, donnees: Any = None) -> dict[str, Any]:
    apercu = None if donnees is None else str(donnees)[:LONGUEUR_MAX_DE_LA_REPONSE]
    message = raison if branche else f"{raison} Not connected: the step must fall back to « {REPLI} » and promise nothing."
    return {
        "ok": True,  # l'action a tourné ; le fait est dans « branche »
        "outil": nom,
        "branche": branche,
        "statut_http": statut_http,
        "duree_ms": duree_ms,
        "raison": raison,
        "repli": None if branche else REPLI,
        "apercu": apercu,
        "elements": [{"statut": "ok" if branche else "echec", "message": f"{nom} : {message}"}],
        "carte": {"type": "outils", "outil": nom, "branche": branche},
    }


async def _ranger(organisation_id: int, workflow_id: int | None, resultat: dict[str, Any]) -> None:
    if workflow_id is None:
        return
    cle = cle_builder(workflow_id, "outils")
    etat = await stock.lire(organisation_id, cle) or {}
    etat[resultat["outil"]] = {
        "branche": resultat["branche"],
        "raison": resultat["raison"],
        "repli": resultat["repli"],
        "le": datetime.now(UTC).isoformat(),
    }
    await stock.ecrire(organisation_id, cle, etat)


async def etat_des_outils(organisation_id: int, workflow_id: int) -> dict[str, Any]:
    """Ce qui a été essayé pour cet agent : outil -> {branche, raison, repli, le}."""
    return await stock.lire(organisation_id, cle_builder(workflow_id, "outils")) or {}
