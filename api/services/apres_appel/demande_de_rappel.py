"""[.mark] agent-facon-tala, suite des résultats fermés, lot B1 : l'outil natif « demander un rappel ».

Un agent qui a recueilli une demande n'a, jusqu'ici, aucun acte qui la ferme : « c'est noté » est jugé par le cerveau.
Cet outil est l'acte. Posé par CONFIGURATION sur une étape (outil de catégorie ``native``, ``config.action`` =
``demander_un_rappel``) : un agent qui ne le porte pas ne change pas d'un octet.

- Il lit la fiche de l'appel. Chaque champ de ``config.champs_requis`` doit y être noté (le numéro de l'appel peut le
  remplacer au téléphone, ``repli_appel``). Il en manque : il rend ``il manque : …`` et n'écrit RIEN.
- Rien ne manque : il écrit UNE entrée dans la fiche sous ``CLE_RAPPEL`` (origine ``agent``, la même mécanique que
  le planificateur, l'équipe et le transfert, ``rappels.py``) et rend ``transmise``. Un second appel dans le même appel met
  cette entrée à jour : une demande de rappel par appel.
- Son issue vient de sa configuration (``config.call_disposition``). Elle est posée ICI, à ``transmise``, et à aucun
  autre moment : le classement final ne la voit pas (``issue_reservee.py``), il ne peut pas l'inventer.

Même chemin au téléphone et au clavier (le même moteur monte l'outil). Aucun mot de métier : les champs, leurs libellés
et l'issue viennent de la configuration de l'outil. Agnostique du cerveau : c'est un outil, comme un autre.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger
from pipecat.services.llm_service import FunctionCallParams

from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_AGENT

ACTION = "demander_un_rappel"
CATEGORIE = "native"

STATUT_TRANSMISE = "transmise"
STATUT_IL_MANQUE = "il_manque"


def est_un_outil_de_rappel(outil: Any) -> bool:
    """L'outil est-il l'outil de demande de rappel ? ⛔ Ne lève jamais."""
    try:
        if getattr(outil, "category", None) != CATEGORIE:
            return False
        config = ((getattr(outil, "definition", None) or {}).get("config")) or {}
        return config.get("action") == ACTION
    except Exception:  # noqa: BLE001
        return False


def _config(outil: Any) -> dict:
    return ((getattr(outil, "definition", None) or {}).get("config")) or {}


def issue_de(outil: Any) -> str | None:
    """L'issue réglée sur l'outil, ``None`` s'il n'en a pas."""
    code = _config(outil).get("call_disposition")
    return code.strip() if isinstance(code, str) and code.strip() else None


def _renseigne(valeur: Any) -> bool:
    from api.services.workflow.fiche_au_fil_de_leau import VALEUR_DE_REFUS, _est_vide

    if _est_vide(valeur):
        return False
    return not (isinstance(valeur, str) and valeur.strip().casefold() == VALEUR_DE_REFUS)


def ce_qui_manque(fiche: dict | None, variables: dict | None, config: dict) -> list[str]:
    """Les libellés des champs requis qui ne sont pas notés (ni remplacés par une variable de l'appel)."""
    fiche = fiche or {}
    variables = variables or {}
    manque: list[str] = []
    for requis in config.get("champs_requis") or []:
        if not isinstance(requis, dict) or not requis.get("champ"):
            continue
        if _renseigne(fiche.get(requis["champ"])):
            continue
        repli = requis.get("repli_appel")
        if repli and _renseigne(variables.get(repli)):
            continue
        manque.append(str(requis.get("libelle") or requis["champ"]))
    return manque


def _texte(valeur: Any) -> str | None:
    if isinstance(valeur, str) and valeur.strip():
        return " ".join(valeur.split())
    return None


def ecrire_la_demande(fiche: dict, variables: dict | None, arguments: dict | None, config: dict) -> dict:
    """Écrit (ou met à jour) l'unique entrée ``agent`` de l'appel. Rend l'entrée."""
    arguments = arguments or {}
    variables = variables or {}
    numero = None
    for requis in config.get("champs_requis") or []:
        if isinstance(requis, dict) and requis.get("repli_appel"):
            numero = _texte(fiche.get(requis["champ"])) or _texte(variables.get(requis["repli_appel"]))
            break
    entree = {
        "origine": ORIGINE_AGENT,
        "mode": "rappel",
        "numero": numero,
        "objet": _texte(arguments.get("objet")),
        "souhait": _texte(arguments.get("moment_souhaite")),
        "le": datetime.now(UTC).isoformat(),
    }
    liste = fiche.setdefault(CLE_RAPPEL, [])
    if not isinstance(liste, list):  # une fiche abîmée ne coûte jamais l'appel
        liste = fiche[CLE_RAPPEL] = []
    for i, ancienne in enumerate(liste):
        if isinstance(ancienne, dict) and ancienne.get("origine") == ORIGINE_AGENT:
            liste[i] = entree
            return entree
    liste.append(entree)
    return entree


def traiter(engine: Any, outil: Any, arguments: dict | None) -> dict:
    """Le cœur de l'outil, sans le moteur de l'appel de fonction : rend le résultat à lire par le cerveau."""
    config = _config(outil)
    fiche = getattr(engine, "_gathered_context", None)
    if not isinstance(fiche, dict):
        return {"statut": "erreur"}
    variables = getattr(engine, "_call_context_vars", None) or {}
    manque = ce_qui_manque(fiche, variables, config)
    if manque:
        return {"statut": STATUT_IL_MANQUE, "il_manque": manque, "consigne": "il manque : " + ", ".join(manque)}
    ecrire_la_demande(fiche, variables, arguments, config)
    code = issue_de(outil)
    if code:
        engine.set_call_disposition(code)
    return {"statut": STATUT_TRANSMISE}


def creer_gestionnaire(engine: Any, outil: Any):
    """Le gestionnaire de l'appel de fonction (téléphone et clavier : le même moteur). ⛔ Ne lève jamais."""

    async def demander_un_rappel(params: FunctionCallParams) -> None:
        try:
            resultat = traiter(engine, outil, dict(params.arguments or {}))
        except Exception as erreur:  # noqa: BLE001 -- une demande ratée ne coûte jamais l'appel
            logger.error(f"[rappel] {ACTION} a échoué : {erreur!r}")
            resultat = {"statut": "erreur"}
        await params.result_callback(resultat)

    return demander_un_rappel
