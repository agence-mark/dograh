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
un seul tour de conversation à la fois par agent, et le refus des actions interdites (``registre``). Le cerveau
est injecté : les tests passent un cerveau factice, rien n'est dépensé.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from api.services.builder import actions, contexte, methode  # noqa: F401 -- ``actions`` inscrit le registre
from api.services.builder.actions.registre import Contexte, executer, outils_du_moteur
from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau
from api.services.builder.cerveau.reglages import ReglagesCerveau

DELAI_DU_VERROU_S = 600.0


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


async def _prendre_le_verrou(conversation: dict[str, Any]) -> bool:
    depuis = conversation.get("en_cours_depuis")
    if depuis and time.time() - float(depuis) < DELAI_DU_VERROU_S:
        return False
    conversation["en_cours_depuis"] = time.time()
    return True


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
    conv = await contexte.charger(org, agent)
    if not await _prendre_le_verrou(conv):
        yield {"type": "erreur", "code": "en_cours", "message": "The builder is already working on this agent."}
        return
    # Le verrou est écrit tout de suite : un second appel le verra.
    await contexte.enregistrer(org, agent, conv)
    try:
        async for evenement in _tours(ctx, message, cerveau, reglages, conv):
            yield evenement
    finally:
        conv.pop("en_cours_depuis", None)
        await contexte.enregistrer(org, agent, conv)


async def _tours(
    ctx: Contexte, message: str, cerveau: Cerveau, reglages: ReglagesCerveau, conv: dict[str, Any]
) -> AsyncIterator[dict[str, Any]]:
    org, agent = ctx.organisation_id, ctx.workflow_id
    assert agent is not None
    depense = conv["depense"]
    if (atteint := plafond_atteint(depense, reglages)) is not None:
        yield {"type": "erreur", "code": "plafond", "message": f"The conversation's ceiling is reached ({atteint}): raise it in the builder settings."}
        yield {"type": "fin", "raison": "plafond"}
        return

    systeme = await methode.systeme_complet(getattr(ctx.user, "id", None))
    usage_du_resume = await contexte.compacter_si_besoin(conv, cerveau, systeme, reglages.fenetre)
    if usage_du_resume:
        _ajouter_usage(depense, usage_du_resume["entree"], usage_du_resume["sortie"], reglages)
    etat = await contexte.etat_du_disque(org, agent)
    bloc = (f"[Résumé de la conversation avant ce point]\n{conv['resume']}\n\n" if conv["resume"] else "") + etat

    message_du_jour = {"role": "user", "content": message}
    conv["messages"].append(message_du_jour)
    outils = outils_du_moteur()
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
        for appel in appels:
            if appel.get("illisible"):
                resultat = {"ok": False, "erreur": "The arguments were not valid JSON: send them again."}
            else:
                resultat = await executer(appel["nom"], appel["arguments"], ctx)
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
        await contexte.enregistrer(org, agent, conv)
    logger.info(f"[builder] agent {agent}: tours d'actions épuisés")
    yield {"type": "fin", "raison": "tours"}
