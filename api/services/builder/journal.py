"""[.mark] Builder partie 3, N1 (sous-lot 4) : le journal de ce que le builder ÉCRIT, et « Annuler » sur l'action faite.

Un seul point : ``registre.executer`` ouvre une ligne AVANT toute action qui n'est pas une lecture (``ouvrir``), puis la clôt avec le résultat
(``clore``). Chaque ligne dit qui (compte), quoi (action, famille, arguments sans secret), quand, quelle porte (écran ou Claude Code), quel
mode du chat, quelle autorisation (le mode, « une fois », « pour ce chat », l'accord d'une dépense, la personne elle-même hors chat),
l'état avant et après. **La garde tient dans tous les modes** : si la ligne ne peut pas être écrite, l'action n'est pas jouée.

« Annuler » (``annuler``) réutilise ce qui existe au lieu d'un second mécanisme :

* les actions qui écrivent le **brouillon** d'un agent (graphe, phrases, réglages, vocabulaire, version d'outil) rangent juste avant un
  **instantané** de « Revenir avant » (``revue._ranger``, ``instantane.capturer``) ; « Annuler » restaure CET instantané, seulement pour
  les familles que l'action a touchées. Refusé si une écriture plus récente de l'agent est encore en place (défaire l'ancienne emporterait
  la récente : on annule dans l'ordre) ;
* les actions de l'entreprise qui réécrivent un objet entier (annonce, listes, établissements) déclarent comment lire l'état d'avant
  et comment le remettre (``Action.extras["avant"]`` / ``["defaire"]``) ; l'état d'avant est gardé dans la ligne ;
* tout le reste dit pourquoi il ne se défait pas (``non_annulable``) : publié, supprimé, dépensé, appel réel, en attente de revue, création.

Pourquoi une table à part (``mark_builder_journal``) et pas le journal d'équipe (``mark_journal``) : celui-ci écrit un geste d'équipe en une
ligne, sans état avant / après ni annulation, et se lit à travers les clients. Celui-là se lit par organisation, porte l'état d'annulation
et l'instantané à restaurer. L'auteur reprend le même identifiant de compte (``auteur_du_journal``), jamais une adresse.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.builder import garde_secrets

TAILLE_MAX = 6000  # caractères gardés par état (arguments, avant, après) : au-delà, un aperçu seulement

# Les actions qui écrivent le brouillon d'un agent, et les familles d'instantané que « Annuler » restaure pour chacune.
ACTIONS_A_INSTANTANE: dict[str, tuple[str, ...]] = {
    "save_workflow": ("schema",),
    "brouillon_enregistrer": ("schema",),
    "bloc_poser": ("schema",),
    "bloc_retirer": ("schema",),
    "bibliotheque_appliquer": ("schema",),
    "outil_passer_a_la_version": ("schema",),
    "phrases_regler": ("phrases",),
    "reglages_regler": ("reglages",),
    "modeles_reglages_appliquer": ("reglages",),
    "publication_corriger_la_liste_vocale": ("reglages",),
    "lexique_remplir_depuis_fiche": ("vocabulaire",),
}

# Pourquoi une action ne se défait pas d'un clic (le code est traduit à l'écran).
RAISON_DE_LA_FAMILLE = {
    "publication": "publication",
    "irreversible": "irreversible",
    "depense": "depense",
    "appels_reels": "appels_reels",
}
CREATIONS = ("create_workflow", "groupe_creer", "groupe_specialise_creer")


class ErreurJournal(Exception):
    """Le journal n'a pas pu être écrit : l'action n'est pas jouée."""


class ErreurAnnulation(Exception):
    def __init__(self, message: str, statut: int = 409, code: str = "refus"):
        super().__init__(message)
        self.statut = statut
        self.code = code


@dataclass
class Entree:
    """Une ligne ouverte, en attente de sa clôture."""

    id: int
    organisation: int
    annulation: dict[str, Any] | None = None
    non_annulable: str | None = None
    famille: str = "irreversible"
    extras: dict[str, Any] = field(default_factory=dict)


def borne(valeur: Any) -> Any:
    """L'état tel que le journal le garde : sans secret, et borné (un aperçu au-delà de ``TAILLE_MAX``)."""
    propre = garde_secrets.masquer(valeur)
    brut = json.dumps(propre, ensure_ascii=False, default=str)
    if len(brut) <= TAILLE_MAX:
        return json.loads(brut)
    return {"apercu": brut[:TAILLE_MAX] + "…", "tronque": True}


def _auteur(user: Any) -> str:
    from api.services.equipe_mark.acces import auteur_du_journal

    return auteur_du_journal(user)


async def _instantane_avant(nom: str, cible: int, contexte: Any) -> dict[str, Any] | None:
    """Range l'état de l'agent juste avant l'action (le même rangement que « Revenir avant »). ``None`` : pas d'agent ou rangement impossible."""
    from api.services.builder import brouillon, instantane, revue

    try:
        workflow = await db_client.get_workflow(cible, organization_id=contexte.organisation_id)
        if not workflow:
            return None
        graphe, version = await brouillon.source_courante(workflow)
        graphe = graphe or {"nodes": [], "edges": []}
        branche = await revue._branche_ouverte(cible)  # noqa: SLF001
        numero = await revue._ranger(  # noqa: SLF001 -- le même rangement que la revue et la sauvegarde : « Revenir avant » le montre
            contexte.organisation_id,
            cible,
            cause=f"avant {nom} (builder)",
            avant=graphe,
            apres=graphe,
            version_avant=version,
            version_apres=version,
            fil_id=(contexte.conversation or {}).get("fil_id"),
            operations=[],
            complement=await instantane.capturer(contexte.organisation_id, workflow, user=contexte.user),
        )
        return {"genre": "instantane", "numero": numero, "familles": list(ACTIONS_A_INSTANTANE[nom]), "branche": branche}
    except Exception as erreur:  # noqa: BLE001 -- un instantané manqué ne bloque pas l'action : elle dira « sans version »
        logger.warning(f"[builder] instantané avant {nom} non rangé : {type(erreur).__name__}")
        return None


async def _preparer_l_annulation(action: Any, arguments: dict[str, Any], contexte: Any, cible: Any) -> tuple[dict[str, Any] | None, str | None, Any]:
    """(comment défaire, pourquoi on ne peut pas, état d'avant gardé)."""
    raison = RAISON_DE_LA_FAMILLE.get(action.famille or "irreversible")
    if raison is not None:
        return None, raison, None
    if action.nom in ACTIONS_A_INSTANTANE and isinstance(cible, int):
        plan = await _instantane_avant(action.nom, cible, contexte)
        if plan is None:
            return None, "sans_version", None
        return plan, None, {"instantane": plan["numero"], "familles": plan["familles"]}
    if action.extras.get("avant") and action.extras.get("defaire"):
        try:
            lu = await action.extras["avant"](contexte, arguments)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[builder] état d'avant de {action.nom} illisible : {type(erreur).__name__}")
            return None, "illisible", None
        # Un état qui porte un secret ou qui est trop gros ne se range pas en entier : on ne le remettrait pas à l'identique.
        if garde_secrets.masquer(lu) != lu or len(json.dumps(lu, ensure_ascii=False, default=str)) > TAILLE_MAX:
            return None, "illisible", None
        return {"genre": "inverse"}, None, lu
    if action.nom == "brouillon_operation":
        return None, "revue", None
    return None, ("creation" if action.nom in CREATIONS else "autre"), None


async def ouvrir(action: Any, arguments: dict[str, Any], contexte: Any) -> Entree | None:
    """Ouvre la ligne du journal d'une action qui n'est pas une lecture. ``None`` pour une lecture (rien à journaliser).
    Lève ``ErreurJournal`` si la ligne ne peut pas s'écrire : l'appelant ne joue pas l'action."""
    from api.services.builder import modes
    from api.services.builder.actions.registre import PORTE_MCP

    if (action.famille or "irreversible") == "lecture":
        return None
    cible = modes.cible_agent(arguments, contexte)
    annulation, non_annulable, avant = await _preparer_l_annulation(action, arguments, contexte, cible)
    conversation = contexte.conversation
    porte = "mcp" if contexte.porte == PORTE_MCP else "ecran"
    try:
        identifiant = await db_client.ecrire_journal_builder(
            contexte.organisation_id,
            workflow_id=cible if isinstance(cible, int) else None,
            fil_id=(conversation or {}).get("fil_id"),
            user_id=getattr(contexte.user, "id", None),
            auteur=_auteur(contexte.user),
            porte=porte,
            action=action.nom,
            famille=action.famille or "irreversible",
            mode=modes.mode_de(conversation) if conversation is not None else None,
            autorisation=contexte.autorisation or ("claude_code" if porte == "mcp" else "personne"),
            statut="en_cours",
            arguments=borne(arguments),
            avant=borne(avant) if avant is not None else None,
            annulation=annulation,
            non_annulable=non_annulable,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[builder] journal illisible pour {action.nom} : {type(erreur).__name__}")
        raise ErreurJournal("The journal cannot be written.") from None
    return Entree(identifiant, contexte.organisation_id, annulation, non_annulable, action.famille or "irreversible", action.extras)


async def clore(entree: Entree, resultat: Any, ok: bool) -> dict[str, Any]:
    """Clôt la ligne avec ce que l'action a rendu. Rend ce que la ligne d'action montre : ``{id, annulable, raison}``. Ne lève jamais."""
    annulable = ok and entree.annulation is not None
    raison = None if annulable else (entree.non_annulable if ok and entree.non_annulable else "echec")
    champs: dict[str, Any] = {"statut": "fait" if ok else "echec", "apres": borne(resultat if isinstance(resultat, dict) else {"resultat": resultat})}
    if not annulable:
        champs["annulation"] = None
        champs["non_annulable"] = raison
    try:
        await db_client.clore_journal_builder(entree.organisation, entree.id, **champs)
    except Exception as erreur:  # noqa: BLE001 -- l'action est faite ; la ligne reste « en cours », elle est lisible
        logger.error(f"[builder] journal non clos : {type(erreur).__name__}")
    return {"id": entree.id, "annulable": annulable, "raison": raison}


# --- Annuler -------------------------------------------------------------------------------------------------------------------


async def annuler(user: Any, ligne_id: int) -> dict[str, Any]:
    """Défait une action du builder. ``ErreurAnnulation`` : 404 (autre organisation ou inconnue), 403 (le rôle ne le permet pas), 409 (déjà
    annulée, ne se défait pas, une écriture plus récente est en place, version disparue). Journalise elle-même l'annulation."""
    from api.services.builder import modes
    from api.services.builder.actions import familles_actions
    from api.services.builder.actions.registre import REGISTRE, Contexte

    organisation = user.selected_organization_id
    ligne = await db_client.lire_journal_builder(organisation, ligne_id)  # filtré par organisation dans la requête
    if ligne is None:
        raise ErreurAnnulation("Unknown entry.", 404, "inconnue")
    if ligne["annule_le"] is not None:
        raise ErreurAnnulation("This action was already undone.", 409, "deja_annulee")
    if ligne["statut"] != "fait" or ligne["non_annulable"] or not isinstance(ligne["annulation"], dict):
        raise ErreurAnnulation("This action cannot be undone.", 409, ligne["non_annulable"] or "autre")
    # Le rôle borne : défaire une action demande la permission de la faire.
    permission = familles_actions.permission_de(ligne["action"], ligne["famille"])
    if permission is not None and permission not in await modes.permissions_de(user):
        raise ErreurAnnulation(f"Permission required: {permission}", 403, "droits")
    genre = ligne["annulation"].get("genre")
    if genre == "instantane":
        await _restaurer(user, ligne, organisation)
    elif genre == "inverse":
        action = REGISTRE.get(ligne["action"])
        if action is None or not action.extras.get("defaire"):
            raise ErreurAnnulation("This action cannot be undone.", 409, "autre")
        try:
            await action.extras["defaire"](Contexte(user=user, workflow_id=ligne["workflow_id"]), ligne["avant"])
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[builder] annulation de {ligne['action']} en échec : {type(erreur).__name__}")
            raise ErreurAnnulation("The previous state could not be put back: do it on the screen.", 409, "echec") from None
    else:
        raise ErreurAnnulation("This action cannot be undone.", 409, "autre")
    if not await db_client.marquer_annule_journal_builder(organisation, ligne_id, _auteur(user)):
        raise ErreurAnnulation("This action was already undone.", 409, "deja_annulee")
    # L'annulation est elle-même une écriture : elle a sa ligne (qui l'a défaite, sur quelle ligne).
    await db_client.ecrire_journal_builder(
        organisation,
        workflow_id=ligne["workflow_id"],
        fil_id=ligne["fil_id"],
        user_id=getattr(user, "id", None),
        auteur=_auteur(user),
        porte="ecran",
        action="annuler",
        famille=ligne["famille"],
        mode=None,
        autorisation="personne",
        statut="fait",
        arguments={"ligne": ligne_id, "action": ligne["action"]},
        non_annulable="annulation",
    )
    return {"ok": True, "id": ligne_id, "action": ligne["action"], "fil_id": ligne["fil_id"]}


async def _restaurer(user: Any, ligne: dict[str, Any], organisation: int) -> None:
    from api.db import branche_ouverte
    from api.db.protection_principale import PrincipaleProtegee
    from api.services.builder import revue

    cible = ligne["workflow_id"]
    if cible is None:
        raise ErreurAnnulation("This action cannot be undone.", 409, "autre")
    if await db_client.une_ecriture_plus_recente_du_journal(organisation, cible, ligne["id"]):
        raise ErreurAnnulation("A more recent change of this agent is still in place: undo it first.", 409, "ordre")
    workflow = await db_client.get_workflow(cible, organization_id=organisation)
    if not workflow:
        raise ErreurAnnulation("Unknown agent.", 404, "inconnue")
    plan = ligne["annulation"]
    branche_ouverte.ouvrir(plan.get("branche"), getattr(user, "id", None))  # l'instantané appartient à la branche où il a été pris
    try:
        await revue.restaurer(organisation, workflow, int(plan["numero"]), ligne["fil_id"], familles=list(plan.get("familles") or []), user=user)
    except revue.ErreurRevue:
        raise ErreurAnnulation("The version kept before this action is gone: use « Revert » to pick another one.", 409, "sans_version") from None
    except PrincipaleProtegee:
        raise ErreurAnnulation("This agent's main version is protected: the change goes on a branch.", 409, "protegee") from None
