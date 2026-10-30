"""[.mark] Builder : le registre des actions, commun aux deux portes (écran et Claude Code).

Une action = un nom, une description, un modèle de paramètres (Pydantic) et UNE fonction. Les deux portes
passent par ``executer`` :

* l'écran : le moteur appelle ``executer(nom, arguments, contexte)`` pour chaque appel du cerveau ;
* Claude Code : ``api/mcp_server/tools/builder.py`` expose chaque action du registre au serveur MCP, et son
  ``run`` appelle ``executer`` avec l'utilisateur de la clé d'API.

Les actions déjà exposées par le serveur MCP de l'amont (lire un agent, créer, enregistrer en brouillon...)
gardent leur fonction d'origine : l'adaptateur de ``construction.py`` appelle CETTE fonction (``mcp=False`` :
pas de seconde inscription).

⛔ Interdits codés (B10, B35) : publier, supprimer, écrire dans la bibliothèque au-delà d'un candidat,
passer en Recette, accepter une proposition. Ils ne sont PAS dans le registre ; un cerveau qui les demande
reçoit un refus explicite (``INTERDITES``), un nom inconnu reçoit une erreur. Ce sont des clics humains.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from pydantic import BaseModel, ValidationError

# Ce que le builder ne fait jamais. Le nom sert au refus explicite ; aucune de ces actions n'existe.
INTERDITES: frozenset[str] = frozenset(
    {
        "publish_workflow",
        "publier",
        "publier_agent",
        "delete_workflow",
        "supprimer",
        "supprimer_agent",
        "supprimer_outil",
        "bibliotheque_ecrire",
        "bibliotheque_supprimer",
        "bibliotheque_marquer_recette",
        "bibliotheque_rejeter",
        "bibliotheque_accepter_proposition",
        "bibliotheque_refuser_proposition",
        "bibliotheque_retour_arriere",
    }
)

PORTE_ECRAN = "ecran"
PORTE_MCP = "mcp"


@dataclass
class Contexte:
    """Qui agit et sur quoi. ``conversation`` est l'état de la conversation du builder (écran) ; vide côté MCP."""

    user: Any
    workflow_id: int | None = None
    conversation: dict[str, Any] | None = None
    porte: str = PORTE_ECRAN

    @property
    def organisation_id(self) -> int:
        return self.user.selected_organization_id


class ErreurAction(Exception):
    """Un refus normal de l'action (rendu au cerveau comme résultat, jamais une panne)."""

    def __init__(self, message: str, code: str = "refus"):
        super().__init__(message)
        self.code = code


Fonction = Callable[[Contexte, Any], Awaitable[dict[str, Any]]]


@dataclass
class Action:
    nom: str
    description: str
    parametres: type[BaseModel]
    fonction: Fonction
    # Écrit quelque chose (agent, bibliothèque, fiche...). Une action de lecture ne l'est pas.
    ecriture: bool = False
    # False : le point d'entrée est posé, un lot suivant le remplit (réponse « pas encore disponible »).
    disponible: bool = True
    # Dit au cerveau qu'elle est faite pour lui (écran) / inscrite au serveur MCP.
    moteur: bool = True
    mcp: bool = True
    # Famille de l'action, pour l'écran (cartes) et la documentation.
    groupe: str = "general"
    extras: dict[str, Any] = field(default_factory=dict)

    def schema(self) -> dict[str, Any]:
        schema = self.parametres.model_json_schema()
        schema.pop("title", None)
        return schema


REGISTRE: dict[str, Action] = {}


def enregistrer(action: Action) -> Action:
    if action.nom in REGISTRE:
        raise ValueError(f"Action already registered: {action.nom}")
    if action.nom in INTERDITES:
        raise ValueError(f"A forbidden action cannot be registered: {action.nom}")
    REGISTRE[action.nom] = action
    return action


def outils_du_moteur() -> list[dict[str, Any]]:
    """La description des actions telle que le cerveau la reçoit (nom, description, paramètres)."""
    return [
        {"name": a.nom, "description": a.description, "parameters": a.schema()}
        for a in REGISTRE.values()
        if a.moteur
    ]


def pas_encore_disponible(nom: str, lot: str) -> dict[str, Any]:
    return {"disponible": False, "message": f"« {nom} » n'est pas encore disponible ({lot}). Ne l'annonce pas comme fait."}


async def executer(nom: str, arguments: dict[str, Any], contexte: Contexte) -> dict[str, Any]:
    """L'unique chemin d'exécution d'une action, pour les deux portes. Ne lève jamais : un refus est un résultat."""
    if nom in INTERDITES:
        return {"ok": False, "interdit": True, "erreur": f"« {nom} » is forbidden to the builder: only a person does it."}
    action = REGISTRE.get(nom)
    if action is None:
        return {"ok": False, "erreur": f"Unknown action: {nom}."}
    if contexte.porte == PORTE_ECRAN and not action.moteur:
        return {"ok": False, "erreur": f"Unknown action: {nom}."}
    try:
        parametres = action.parametres.model_validate(arguments or {})
    except ValidationError as erreur:
        premier = erreur.errors()[0]
        lieu = ".".join(str(p) for p in premier.get("loc", ()))
        return {"ok": False, "erreur": f"Invalid arguments ({lieu}): {premier.get('msg', 'invalid')}."}
    try:
        resultat = await action.fonction(contexte, parametres)
    except ErreurAction as erreur:
        return {"ok": False, "code": erreur.code, "erreur": str(erreur)}
    except Exception as erreur:  # noqa: BLE001 -- une action qui échoue ne fait pas tomber la conversation
        logger.warning(f"[builder] action {nom} en échec : {type(erreur).__name__}")
        return {"ok": False, "erreur": f"The action failed ({type(erreur).__name__}): {str(erreur)[:200]}"}
    return resultat if isinstance(resultat, dict) else {"ok": True, "resultat": resultat}
