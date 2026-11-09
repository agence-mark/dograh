"""[.mark] Builder : le registre des actions, commun aux deux portes (écran et Claude Code).

Une action = un nom, une description, un modèle de paramètres (Pydantic) et UNE fonction. Les deux portes
passent par ``executer`` :

* l'écran : le moteur appelle ``executer(nom, arguments, contexte)`` pour chaque appel du cerveau ;
* Claude Code : ``api/mcp_server/tools/builder.py`` expose chaque action du registre au serveur MCP, et son
  ``run`` appelle ``executer`` avec l'utilisateur de la clé d'API.

Les actions déjà exposées par le serveur MCP de l'amont (lire un agent, créer, enregistrer en brouillon...)
gardent leur fonction d'origine : l'adaptateur de ``construction.py`` appelle CETTE fonction (``mcp=False`` :
pas de seconde inscription).

Partie 3, N1 (05, « Le builder peut tout faire ») : plus d'interdit codé. Chaque action déclare sa FAMILLE
(``familles_actions.py``) et la permission décide à chaque appel (``modes.decider`` : rôle de la personne, mode du chat,
carte d'autorisation dans le fil). Publier, archiver, les clics de la bibliothèque sont des actions (``gestes.py``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from pydantic import BaseModel, ValidationError

from api.db.protection_principale import PrincipaleProtegee

PORTE_ECRAN = "ecran"
PORTE_MCP = "mcp"


@dataclass
class Contexte:
    """Qui agit et sur quoi. ``conversation`` est l'état de la conversation du builder (écran) ; vide côté MCP."""

    user: Any
    workflow_id: int | None = None
    conversation: dict[str, Any] | None = None
    porte: str = PORTE_ECRAN
    # C2 (E96) : un sous-agent du builder n'a que ces actions (liste fermée côté serveur) ; ``None`` = toutes celles de la porte.
    actions_permises: frozenset[str] | None = None
    # N1 : les permissions de rôle de la personne, lues une fois par travail (``modes.permissions_de``) ; ``None`` = pas encore lues.
    permissions: frozenset[str] | None = None
    # N1 : une action de la famille « dépense » vient d'être permise par le mode ou une carte (vaut l'accord de ``consommer_un_accord``).
    accord_donne: bool = False
    # N1 (sous-lot 4) : comment la permission a été donnée à l'action en cours (``mode``, ``une_fois``, ``pour_ce_chat``, ``depense``...), posé par ``modes.decider``.
    autorisation: str | None = None
    # N1 (sous-lot 4) : la ligne du journal de la dernière action écrite (``{id, annulable, raison}``), lue par le moteur pour la montrer à l'écran.
    journal: dict[str, Any] | None = None
    # RV2 (M-1, M-2) : les accords que ``modes.decider`` vient de consommer pour CETTE action (accord de dépense, autorisation « une fois »),
    # rendus par ``executer`` si l'action est refusée avant d'être jouée (sauvegarde, étiquettes, journal).
    accords_pris: list[dict[str, Any]] = field(default_factory=list)

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
    # N1 : la famille de permission (``familles_actions.FAMILLES``), posée à l'inscription d'après la table ; ``None`` = la plus fermée.
    famille: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def schema(self) -> dict[str, Any]:
        schema = self.parametres.model_json_schema()
        schema.pop("title", None)
        return schema


REGISTRE: dict[str, Action] = {}


def enregistrer(action: Action) -> Action:
    if action.nom in REGISTRE:
        raise ValueError(f"Action already registered: {action.nom}")
    if action.famille is None:
        from api.services.builder.actions.familles_actions import famille_de

        action.famille = famille_de(action.nom)
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


async def _refus_de_la_cle_mcp(action: Action, contexte: Contexte) -> dict[str, Any] | None:
    """Les droits d'une clé à la porte MCP, lus dans la table unique (clôture, lot A, D10 et D21). ``None`` : la clé passe.

    * clé PORTÉE PAR UN RÔLE : une écriture exige la permission de la famille de l'action, exactement comme à l'écran ;
    * clé sans rôle : une écriture est réservée à la clé du Labo (17a) ; la lecture d'un client lui est fermée (D10)."""
    from api.services.builder.actions import familles_actions
    from api.services.builder.bibliotheque import droits
    from api.services.builder.constantes import organisation_bibliotheque
    from api.services.equipe_mark import droits_effectifs

    user = contexte.user
    if getattr(user, "cle_api_role_id", None) is not None:
        if not action.ecriture:
            return None
        permission = familles_actions.permission_de(action.nom, action.famille or "irreversible")
        if permission is not None and permission not in await droits_effectifs.permissions_de(user):
            return {"ok": False, "code": "droits", "erreur": f"This API key does not carry the permission « {permission} »: the role of the key never does more than it allows."}
        return None
    if action.ecriture and not await droits._cle_du_labo_par_mcp(user, organisation_bibliotheque()):
        return {"ok": False, "code": "cle_sans_ecriture", "erreur": "This API key cannot write through MCP: only the Labo key of the .mark team does."}
    if droits_effectifs.lecture_fermee_a_la_cle_de_client(user):
        return {"ok": False, "code": "cle_de_client", "erreur": "This API key of a client cannot read agents, tools or the builder."}
    return None


async def executer(nom: str, arguments: dict[str, Any], contexte: Contexte) -> dict[str, Any]:
    """L'unique chemin d'exécution d'une action, pour les deux portes. Ne lève jamais : un refus est un résultat."""
    contexte.journal = None
    action = REGISTRE.get(nom)
    if action is None:
        return {"ok": False, "erreur": f"Unknown action: {nom}."}
    if contexte.porte == PORTE_ECRAN and not action.moteur:
        return {"ok": False, "erreur": f"Unknown action: {nom}."}
    if contexte.porte == PORTE_MCP and getattr(contexte.user, "par_porte_mcp", False):
        if (refus := await _refus_de_la_cle_mcp(action, contexte)) is not None:
            return refus
    if contexte.actions_permises is not None and nom not in contexte.actions_permises:
        return {"ok": False, "code": "sous_agent", "erreur": f"« {nom} » is not allowed to a sub-agent: it only reads and tests, it never writes."}
    from api.services.builder import portes

    if (refus := await portes.refus_de_la_porte(contexte)) is not None:
        return {"ok": False, "code": "porte_coupee", "erreur": refus}
    try:
        parametres = action.parametres.model_validate(arguments or {})
    except ValidationError as erreur:
        premier = erreur.errors()[0]
        lieu = ".".join(str(p) for p in premier.get("loc", ()))
        return {"ok": False, "erreur": f"Invalid arguments ({lieu}): {premier.get('msg', 'invalid')}."}
    # N1 (sous-lot 6) : les secrets ne passent jamais, dans aucun mode (le builder les choisit par leur nom, une personne les saisit).
    from api.services.builder import garde_secrets, journal, modes

    if (refus := garde_secrets.refus_d_un_secret(parametres.model_dump(mode="json", exclude_unset=True))) is not None:
        return refus
    # N1 : la permission décide (rôle, mode du chat, carte d'autorisation), côté serveur, avant toute écriture.
    contexte.autorisation = None
    contexte.accords_pris = []
    if (decision := await modes.decider(action, parametres.model_dump(mode="json", exclude_unset=True), contexte)) is not None:
        return decision
    # Les garde-fous qui refusent SANS rien écrire passent avant le journal : un refus n'a ni ligne ni instantané.
    try:
        # [.mark] lot M : sauvegarde avant la première modification d'un agent existant (éteinte par défaut, ``sauvegarde.py``).
        from api.services.builder import sauvegarde

        await sauvegarde.garde(nom, parametres, contexte)
        # [.mark] Lots 8 et 22 : le builder n'écrit jamais une étiquette d'objet hors du catalogue de l'organisation.
        from api.services.builder.actions import etiquettes_prompt as garde_etiquettes

        await garde_etiquettes.garde(nom, arguments, contexte)
    except ErreurAction as erreur:
        contexte.accord_donne = False
        modes.rendre_les_accords(contexte)
        return {"ok": False, "code": erreur.code, "erreur": str(erreur)}
    # N1 (sous-lot 4) : toute écriture a sa ligne de journal AVANT d'être jouée ; sans ligne, rien n'est fait (même en « Tout permettre »).
    try:
        entree = await journal.ouvrir(action, parametres.model_dump(mode="json", exclude_unset=True), contexte)
    except journal.ErreurJournal:
        contexte.accord_donne = False
        modes.rendre_les_accords(contexte)
        return {"ok": False, "code": "journal", "erreur": "Nothing was done: the journal of the builder cannot be written. Tell the person."}
    ok = False
    try:
        resultat = await action.fonction(contexte, parametres)
        if nom == "create_workflow" and isinstance(resultat, dict) and resultat.get("ok", True):
            from api.services.builder import sauvegarde

            await sauvegarde.apres_creation(contexte, resultat)
        ok = not (isinstance(resultat, dict) and resultat.get("ok", True) is False)
    except ErreurAction as erreur:
        resultat = {"ok": False, "code": erreur.code, "erreur": str(erreur)}
    except PrincipaleProtegee as erreur:
        # SA-L3c : la principale d'un agent client en ligne n'a plus de brouillon à écrire ; le cerveau passe par une branche.
        resultat = {"ok": False, "code": erreur.code, "erreur": f"{erreur} Tell the person: the change goes on a branch, merged after a review."}
    except Exception as erreur:  # noqa: BLE001 -- une action qui échoue ne fait pas tomber la conversation
        logger.warning(f"[builder] action {nom} en échec : {type(erreur).__name__}")
        resultat = {"ok": False, "erreur": f"The action failed ({type(erreur).__name__}): {str(erreur)[:200]}"}
    finally:
        contexte.accord_donne = False  # N1 : l'accord donné par la permission vaut pour CETTE action seulement
    resultat = resultat if isinstance(resultat, dict) else {"ok": True, "resultat": resultat}
    # N1 (sous-lot 6) : rien de ce que l'action rend ne montre un secret au builder, quel que soit le mode.
    resultat = garde_secrets.masquer(resultat)
    if entree is not None:
        contexte.journal = await journal.clore(entree, resultat, ok)  # l'écran le lit (carte « Annuler ») ; le résultat du builder ne change pas
    if action.ecriture and ok:
        await _publier_la_modification(action, arguments or {}, contexte, resultat)
    return resultat


async def _publier_la_modification(action: Action, arguments: dict[str, Any], contexte: Contexte, resultat: dict[str, Any]) -> None:
    """U12 : toute écriture réussie, par l'écran ou par Claude Code, publie une modification (l'écran ouvert se rafraîchit seul).
    Ne lève jamais : l'écriture est faite, son affichage en direct est un plus."""
    try:
        from api.services import modifications_live as live

        cree = resultat.get("workflow_id") if isinstance(resultat.get("workflow_id"), int) else None
        objet = live.objet_d_une_action(action.nom, action.groupe, arguments, contexte.workflow_id or cree)
        source = "claude_code" if contexte.porte == PORTE_MCP else "ecran"
        await live.noter(contexte.organisation_id, objet, action.nom, source=source, auteur=live.auteur_de(contexte.user))
    except Exception:  # noqa: BLE001
        logger.debug(f"[builder] modification de {action.nom} non publiée")
