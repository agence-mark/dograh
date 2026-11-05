"""[.mark] Builder : la boucle de conversation (flux de texte, cartes, opérations), côté serveur.

``conversation(...)`` est un générateur d'événements, que la route diffuse en SSE :

* ``{"type": "texte", "texte"}``                           un morceau de la réponse ;
* ``{"type": "action", "id", "nom", "arguments"}``         le cerveau appelle une action ;
* ``{"type": "resultat", "id", "nom", "ok", "resultat"}``  ce que l'action a rendu ;
* ``{"type": "carte", "carte": {...}}``                    une carte pour l'écran (conception, fiche, changements, proposition) ;
* ``{"type": "operation", "operation": {...}}``            une opération de construction, à dessiner sur le graphe ;
* ``{"type": "depense", "jetons", "cout", "plafond_jetons", "plafond_depense"}`` ;
* ``{"type": "erreur", "code", "message"}`` puis ``{"type": "fin", "raison"}``.

Tenu ici : l'historique par agent et son compactage (B45), le plafond de jetons et de dépense par conversation,
un seul tour de conversation à la fois par agent, et l'arrêt sur une carte d'autorisation (N1 : la permission est décidée par
``registre.executer`` et ``modes.py``). Le cerveau
est injecté : les tests passent un cerveau factice, rien n'est dépensé.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from api.db import branche_ouverte
from api.services.builder import actions, contexte, methode, modes, suites  # noqa: F401 -- ``actions`` inscrit le registre
from api.services.builder.actions.registre import Contexte, executer, outils_du_moteur
from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau
from api.services.builder.cerveau.reglages import ReglagesCerveau

DELAI_DU_VERROU_S = 600.0
ETAT_SANS_AGENT = (
    "## État actuel (relu sur le disque, c'est la vérité)\n"
    "Cette conversation n'a pas encore d'agent : "
    "crée-le avec create_workflow quand la demande est claire, ou lis d'abord les fichiers joints."
)


def _cout(entree: int, sortie: int, reglages: ReglagesCerveau) -> float:
    return (entree * reglages.prix_entree_par_million + sortie * reglages.prix_sortie_par_million) / 1_000_000


def plafond_atteint(depense: dict[str, Any], reglages: ReglagesCerveau) -> str | None:
    """Le plafond dépassé (``jetons`` ou ``depense``), ou ``None``."""
    if depense.get("jetons", 0) >= reglages.plafond_jetons:
        return "jetons"
    if reglages.plafond_depense > 0 and depense.get("cout", 0.0) >= reglages.plafond_depense:
        return "depense"
    return None


def _ajouter_usage(depense: dict[str, Any], entree: int, sortie: int, reglages: ReglagesCerveau) -> None:
    depense["jetons"] = int(depense.get("jetons", 0)) + entree + sortie
    depense["cout"] = round(float(depense.get("cout", 0.0)) + _cout(entree, sortie, reglages), 6)


def _evenement_de_depense(depense: dict[str, Any], reglages: ReglagesCerveau) -> dict[str, Any]:
    return {
        "type": "depense",
        "jetons": depense["jetons"],
        "cout": depense["cout"],
        "plafond_jetons": reglages.plafond_jetons,
        "plafond_depense": reglages.plafond_depense,
    }


def _requete(conversation: dict[str, Any], message_du_jour: dict[str, Any], bloc: str) -> list[dict[str, Any]]:
    """Les messages envoyés au cerveau : l'historique, et devant le message du jour le résumé + l'état relu sur le disque.

    Le message du jour est retrouvé par identité : un rangement de l'historique en cours de route ne le déplace pas."""
    messages = []
    for m in conversation["messages"]:
        if bloc and m is message_du_jour:
            messages.append({**m, "content": f"{bloc}\n\n[Message de la personne]\n{m['content']}"})
        else:
            messages.append(dict(m))
    return messages


def _sans_carte(resultat: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in resultat.items() if k != "carte"}


async def conversation(
    ctx: Contexte,
    message: str,
    cerveau: Cerveau,
    reglages: ReglagesCerveau,
) -> AsyncIterator[dict[str, Any]]:
    if ctx.workflow_id is None:
        yield {"type": "erreur", "code": "agent", "message": "A builder conversation belongs to an agent."}
        return
    org, agent = ctx.organisation_id, ctx.workflow_id
    # Le verrou est pris et écrit EN UNE FOIS (revue R6) : deux demandes simultanées, une seule le reçoit.
    conv = await contexte.prendre_le_verrou(org, agent, DELAI_DU_VERROU_S)
    if conv is None:
        yield {"type": "erreur", "code": "en_cours", "message": "The builder is already working on this agent."}
        return
    try:
        async for evenement in _tours(ctx, message, cerveau, reglages, conv):
            yield evenement
    finally:
        conv.pop("en_cours_depuis", None)
        try:
            await contexte.enregistrer(org, agent, conv)
        except contexte.ConflitDeRevision:
            # Le verrou périmé a été repris par une autre demande : on ne piétine pas sa conversation.
            logger.warning(f"[builder] agent {agent}: la conversation a été reprise par une autre demande, rien n'est écrasé")


async def tours(
    ctx: Contexte,
    message: str,
    cerveau: Cerveau,
    reglages: ReglagesCerveau,
    conv: dict[str, Any],
    enregistrer=None,
) -> AsyncIterator[dict[str, Any]]:
    """Les tours de la conversation ``conv``. ``enregistrer(org, agent, conv)`` range l'état à chaque fin de tour : le disque
    par agent (``contexte.enregistrer``) par défaut, la table des conversations (``fil.py``) pour le chat."""
    async for evenement in _tours(ctx, message, cerveau, reglages, conv, enregistrer):
        yield evenement


async def _tours(
    ctx: Contexte, message: str, cerveau: Cerveau, reglages: ReglagesCerveau, conv: dict[str, Any], enregistrer=None
) -> AsyncIterator[dict[str, Any]]:
    org, agent = ctx.organisation_id, ctx.workflow_id
    # [.mark] SA-L3d : la branche sur laquelle le builder a choisi de travailler (``branche_travailler``) reste ouverte aux tours suivants,
    # sauf si la requête en a ouvert une autre (l'en-tête de l'écran garde la priorité).
    if conv.get("branche") and branche_ouverte.courante().branch_id is None:
        branche_ouverte.ouvrir(conv["branche"], getattr(ctx.user, "id", None))
    # Sans agent (chat de l'accueil) : seule une conversation de la table peut tourner ainsi (``tours``), le builder crée l'agent.
    depense = conv["depense"]
    if (atteint := plafond_atteint(depense, reglages)) is not None:
        yield {"type": "erreur", "code": "plafond", "message": f"The conversation's ceiling is reached ({atteint}): raise it in the builder settings."}
        yield {"type": "fin", "raison": "plafond"}
        return

    systeme = await methode.systeme_complet(getattr(ctx.user, "id", None), agent, org)
    usage_du_resume = await contexte.compacter_si_besoin(conv, cerveau, systeme, reglages.fenetre)
    if usage_du_resume:
        _ajouter_usage(depense, usage_du_resume["entree"], usage_du_resume["sortie"], reglages)
    etat = await contexte.etat_du_disque(org, agent) if agent is not None else ETAT_SANS_AGENT
    bloc = (f"[Résumé de la conversation avant ce point]\n{conv['resume']}\n\n" if conv["resume"] else "") + etat
    # N1 : le mode du chat, relu à chaque tour (il vaut pour CE chat ; la porte des modes le vérifie de toute façon côté serveur).
    bloc += "\n\n" + modes.consigne(conv)

    message_du_jour = {"role": "user", "content": message}
    conv["messages"].append(message_du_jour)
    outils = [o for o in outils_du_moteur() if ctx.actions_permises is None or o["name"] in ctx.actions_permises]
    ctx.conversation = conv

    for _tour in range(reglages.tours_outils_max):
        if (atteint := plafond_atteint(depense, reglages)) is not None:
            yield {"type": "erreur", "code": "plafond", "message": f"The conversation's ceiling is reached ({atteint})."}
            yield {"type": "fin", "raison": "plafond"}
            return
        texte, appels = "", []
        try:
            async for evenement in cerveau.tour(
                systeme=systeme, messages=_requete(conv, message_du_jour, bloc), outils=outils
            ):
                genre = evenement["type"]
                if genre == "texte":
                    texte += evenement["texte"]
                    yield evenement
                elif genre == "appel":
                    appels.append(evenement)
                    yield {"type": "action", "id": evenement["id"], "nom": evenement["nom"], "arguments": evenement["arguments"]}
                elif genre == "usage":
                    _ajouter_usage(depense, evenement.get("entree", 0), evenement.get("sortie", 0), reglages)
        except ErreurCerveau as erreur:
            # Ce qui a été rendu avant l'erreur reste dans l'historique ; la personne peut relancer.
            if texte or appels:
                conv["messages"].append({"role": "assistant", "content": texte, "appels": []})
            yield {"type": "erreur", "code": erreur.code, "message": erreur.message}
            yield {"type": "fin", "raison": "erreur"}
            return
        yield _evenement_de_depense(depense, reglages)
        conv["messages"].append(
            {
                "role": "assistant",
                "content": texte,
                "appels": [{"id": a["id"], "nom": a["nom"], "arguments": a["arguments"]} for a in appels],
            }
        )
        if not appels:
            yield {"type": "fin", "raison": "fin"}
            return
        demande_posee = False
        for appel in appels:
            if appel.get("illisible"):
                resultat = {"ok": False, "erreur": "The arguments were not valid JSON: send them again."}
            else:
                resultat = suites.avec_la_suite_de(appel["nom"], await executer(appel["nom"], appel["arguments"], ctx))
                if agent is None and appel["nom"] == "create_workflow" and resultat.get("ok", True):
                    # L'agent vient de naître : la conversation lui est rattachée (tours suivants et table).
                    nouveau = resultat.get("workflow_id") or resultat.get("id")
                    if isinstance(nouveau, int):
                        agent = ctx.workflow_id = nouveau
                        conv["workflow_id"] = nouveau
            demande_posee = demande_posee or resultat.get("code") == modes.CODE_DEMANDE
            for operation in (resultat.get("operations") if isinstance(resultat.get("operations"), list) else []):
                yield {"type": "operation", "operation": operation}
            if resultat.get("carte"):
                yield {"type": "carte", "carte": resultat["carte"]}
            yield {
                "type": "resultat",
                "id": appel["id"],
                "nom": appel["nom"],
                "ok": bool(resultat.get("ok", True)),
                "resultat": _sans_carte(resultat),
            }
            conv["messages"].append(
                {
                    "role": "outil",
                    "appel_id": appel["id"],
                    "nom": appel["nom"],
                    "content": contexte.tronquer(json.dumps(_sans_carte(resultat), ensure_ascii=False, default=str)),
                }
            )
        await (enregistrer or contexte.enregistrer)(org, agent, conv)
        if demande_posee:
            # N1 : une carte d'autorisation attend la personne ; rien ne continue avant son clic (la réponse relance le builder).
            yield {"type": "fin", "raison": "attente"}
            return
    logger.info(f"[builder] agent {agent}: tours d'actions épuisés")
    yield {"type": "fin", "raison": "tours"}
