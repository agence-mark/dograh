"""[.mark] Builder : les conversations du chat en tables, en tâche de fond (builder partie 2, U5, D1 et D2 du 03/11).

* Une conversation = une ligne de ``mark_builder_conversations`` (titre, état, coût, jauge, historique du cerveau) ;
  plusieurs par agent, ou aucune pour le chat de l'accueil (le builder crée alors l'agent et la conversation s'y rattache).
* Le travail tourne dans une **tâche de fond** (plus dans la requête) : l'écran peut se recharger, il rejoue les
  événements de la table depuis le dernier reçu (``mark_evenements``).
* **Arrêter** coupe l'appel au cerveau et rend la main (« arretee ») ; **Reprendre** relance depuis le disque (l'historique
  rangé à chaque fin de tour). Au redémarrage du serveur, toute conversation restée « en_cours » passe à « arretee ».

États : ``nouvelle`` · ``en_cours`` · ``terminee`` · ``arretee`` · ``erreur``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.builder import actions, brouillon, contexte, moteur  # noqa: F401 -- ``actions`` inscrit le registre
from api.services.builder.actions.registre import Contexte
from api.services.builder.cerveau.appel import Cerveau
from api.services.builder.cerveau.reglages import ReglagesCerveau
from api.services.mark_evenements import publier

EVENEMENT_OCTETS_MAX = 60_000
TITRE_MAX = 60
MESSAGE_DE_REPRISE = (
    "Reprends là où tu t'es arrêté : relis l'état actuel, dis en une phrase où tu en étais, puis continue sans refaire ce qui est fait."
)
ETAT_DE_FIN = {"fin": "terminee", "tours": "terminee", "plafond": "arretee", "erreur": "erreur", "arret": "arretee"}

# C2 : ce que la conversation garde en plus de l'historique (plan en cases, dépenses annoncées, rapport de fin).
CLES_GARDEES = ("plan", "depenses", "rapport")

_TACHES: dict[int, asyncio.Task] = {}
# Le cerveau et les réglages de chaque conversation en cours : un sous-agent (``deleguer``) s'en sert pour son propre cerveau.
CERVEAUX: dict[int, tuple[Cerveau, ReglagesCerveau]] = {}


class ErreurFil(Exception):
    def __init__(self, message: str, code: str = "refus", statut: int = 409):
        super().__init__(message)
        self.code = code
        self.statut = statut


def canal(fil_id: int) -> str:
    return f"mark:builder:fil:{fil_id}"


def en_cours(fil_id: int) -> bool:
    tache = _TACHES.get(fil_id)
    return tache is not None and not tache.done()


# --- les événements --------------------------------------------------------------------------------------------------


def _borner(evenement: dict[str, Any]) -> dict[str, Any]:
    """Un événement trop gros (résultat d'une action) est raccourci : la table n'est pas un entrepôt de fichiers."""
    brut = json.dumps(evenement, ensure_ascii=False, default=str)
    if len(brut.encode("utf-8")) <= EVENEMENT_OCTETS_MAX:
        return evenement
    return {
        "type": evenement.get("type", "evenement"),
        **{k: evenement[k] for k in ("id", "nom", "ok") if k in evenement},
        "tronque": True,
        "apercu": brut[:2000],
    }


async def noter(fil_id: int, evenement: dict[str, Any]) -> int:
    """Écrit l'événement dans la table (la vérité), puis réveille les lecteurs (Redis ne porte aucune donnée)."""
    evenement = _borner(evenement)
    identifiant = await db_client.ajouter_evenement(fil_id, str(evenement.get("type", "evenement")), evenement)
    await publier(canal(fil_id))
    return identifiant


async def lire_apres(fil_id: int, apres: int) -> list[tuple[int, dict[str, Any]]]:
    return [(int(e.id), dict(e.donnees)) for e in await db_client.evenements_apres(fil_id, apres)]


# --- l'historique du cerveau -----------------------------------------------------------------------------------------


def _conversation_de(fil) -> dict[str, Any]:
    h = dict(fil.historique or {})
    return {
        **contexte.conversation_vide(),
        "resume": h.get("resume", ""),
        "messages": list(h.get("messages", [])),
        "depense": {"jetons": fil.jetons or 0, "cout": fil.cout or 0.0, **dict(h.get("depense") or {})},
        "dernier_message": h.get("dernier_message"),
        **{cle: h[cle] for cle in CLES_GARDEES if cle in h},
    }


def reparer(conv: dict[str, Any]) -> None:
    """Après une coupure : tout appel du dernier tour sans résultat en reçoit un (« interrompu »), pour que le cerveau puisse
    relire l'historique sans appel orphelin."""
    messages = conv["messages"]
    for rang in range(len(messages) - 1, -1, -1):
        if messages[rang]["role"] == "assistant":
            reponses = {m.get("appel_id") for m in messages[rang + 1 :] if m["role"] == "outil"}
            for appel in messages[rang].get("appels") or []:
                if appel["id"] not in reponses:
                    messages.append(
                        {
                            "role": "outil",
                            "appel_id": appel["id"],
                            "nom": appel["nom"],
                            "content": json.dumps({"ok": False, "erreur": "Interrupted before the result: check the state, redo if needed."}),
                        }
                    )
            return


async def _sauver(org: int, fil_id: int, conv: dict[str, Any], reglages: ReglagesCerveau, workflow_id: int | None) -> None:
    changements = 0
    if workflow_id is not None:
        try:
            changements = len((await brouillon.lire_en_attente(org, workflow_id)).get("operations") or [])
        except Exception:  # noqa: BLE001 -- le compteur n'arrête jamais la conversation
            logger.warning(f"[builder] fil {fil_id}: changements en attente illisibles")
    depense = conv["depense"]
    await db_client.modifier_fil(
        org,
        fil_id,
        historique={
            "resume": conv["resume"],
            "messages": conv["messages"],
            "depense": depense,
            "dernier_message": conv.get("dernier_message"),
            **{cle: conv[cle] for cle in CLES_GARDEES if cle in conv},
        },
        jetons=int(depense.get("jetons", 0)),
        cout=float(depense.get("cout", 0.0)),
        jauge=min(1.0, round(contexte.estimer_jetons("", conv["messages"], conv["resume"]) / max(reglages.fenetre, 1), 4)),
        changements=changements,
    )


# --- la vie d'une conversation ---------------------------------------------------------------------------------------


async def creer(user, workflow_id: int | None, titre: str, demarrage: str | None = None):
    """Une conversation neuve. L'agent, s'il y en a un, est contrôlé par l'appelant (route) avec l'organisation."""
    return await db_client.creer_fil(user.selected_organization_id, user.id, workflow_id, titre[:TITRE_MAX] or "Nouvelle conversation", demarrage)


async def lancer(
    user,
    fil,
    message: str,
    cerveau: Cerveau,
    reglages: ReglagesCerveau,
    *,
    evenement_de_message: dict[str, Any] | None = None,
    actions_permises: frozenset[str] | None = None,
    extras: dict[str, Any] | None = None,
) -> None:
    """Pose le message de la personne et démarre la tâche. Rend la main tout de suite."""
    if en_cours(fil.id):
        raise ErreurFil("The builder is already working on this conversation.", "en_cours")
    org = user.selected_organization_id
    conv = _conversation_de(fil)
    conv["dernier_message"] = await noter(fil.id, evenement_de_message or {"type": "message", "role": "user", "texte": message})
    await db_client.modifier_fil(org, fil.id, etat="en_cours")
    ctx = Contexte(user=user, workflow_id=fil.workflow_id, actions_permises=actions_permises)
    conv.update(extras or {})
    conv["fil_id"] = fil.id
    CERVEAUX[fil.id] = (cerveau, reglages)
    _TACHES[fil.id] = asyncio.create_task(_courir(org, fil.id, ctx, message, cerveau, reglages, conv))


async def _courir(org: int, fil_id: int, ctx: Contexte, message: str, cerveau: Cerveau, reglages: ReglagesCerveau, conv: dict[str, Any]) -> None:
    etat = "terminee"

    async def sauver(_org: int, _agent: int | None, courante: dict[str, Any]) -> None:
        await _sauver(org, fil_id, courante, reglages, ctx.workflow_id)

    try:
        agent_au_depart = ctx.workflow_id
        async for evenement in moteur.tours(ctx, message, cerveau, reglages, conv, sauver):
            await noter(fil_id, evenement)
            if evenement.get("type") == "fin":
                etat = ETAT_DE_FIN.get(str(evenement.get("raison")), "terminee")
            if ctx.workflow_id != agent_au_depart:
                agent_au_depart = ctx.workflow_id
                await db_client.modifier_fil(org, fil_id, workflow_id=ctx.workflow_id)
        await _sauver(org, fil_id, conv, reglages, ctx.workflow_id)
    except asyncio.CancelledError:
        reparer(conv)
        try:
            await _sauver(org, fil_id, conv, reglages, ctx.workflow_id)
            await noter(fil_id, {"type": "fin", "raison": "arret"})
            await db_client.modifier_fil(org, fil_id, etat="arretee")
        except Exception:  # noqa: BLE001
            logger.exception(f"[builder] fil {fil_id}: l'arrêt n'a pas pu être enregistré")
        raise
    except Exception as erreur:  # noqa: BLE001 -- une panne ne laisse jamais la conversation « en cours »
        logger.exception(f"[builder] fil {fil_id}: panne du travail de fond")
        reparer(conv)
        try:
            await _sauver(org, fil_id, conv, reglages, ctx.workflow_id)
            await noter(fil_id, {"type": "erreur", "code": "panne", "message": f"The builder stopped: {type(erreur).__name__}."})
            await noter(fil_id, {"type": "fin", "raison": "erreur"})
            await db_client.modifier_fil(org, fil_id, etat="erreur")
        except Exception:  # noqa: BLE001
            logger.exception(f"[builder] fil {fil_id}: la panne n'a pas pu être enregistrée")
    else:
        await db_client.modifier_fil(org, fil_id, etat=etat)
    finally:
        _TACHES.pop(fil_id, None)
        CERVEAUX.pop(fil_id, None)


async def arreter(org: int, fil_id: int) -> str:
    """Coupe le travail en cours. Rend l'état final. Sans tâche vivante (autre processus, redémarrage), la ligne « en_cours » passe
    à « arretee » avec son événement de fin."""
    tache = _TACHES.get(fil_id)
    if tache is not None and not tache.done():
        tache.cancel()
        try:
            await tache
        except asyncio.CancelledError:
            pass
        return "arretee"
    fil = await db_client.lire_fil(org, fil_id)
    if fil is not None and fil.etat == "en_cours":
        await noter(fil_id, {"type": "fin", "raison": "arret"})
        await db_client.modifier_fil(org, fil_id, etat="arretee")
    return "arretee"


async def supprimer(org: int, fil_id: int) -> bool:
    """Coupe d'abord le travail (et celui de ses sous-agents), puis efface la conversation : événements et sous-agents partent avec
    elle par cascade. Rend faux si la conversation n'existe pas dans cette organisation."""
    for enfant in await db_client.lister_les_enfants(org, fil_id):
        await arreter(org, enfant.id)
    await arreter(org, fil_id)
    _TACHES.pop(fil_id, None)
    CERVEAUX.pop(fil_id, None)
    return await db_client.supprimer_fil(org, fil_id)


async def reprendre(user, fil, cerveau: Cerveau, reglages: ReglagesCerveau) -> None:
    if fil.etat not in ("arretee", "erreur") or en_cours(fil.id):
        raise ErreurFil("Only a stopped conversation can be resumed.", "pas_arretee")
    conv = _conversation_de(fil)
    reparer(conv)
    await db_client.modifier_fil(
        user.selected_organization_id, fil.id, historique={**(fil.historique or {}), "messages": conv["messages"]}
    )
    fil.historique = {**(fil.historique or {}), "messages": conv["messages"]}
    await lancer(user, fil, MESSAGE_DE_REPRISE, cerveau, reglages, evenement_de_message={"type": "reprise"})


async def modifier_le_dernier_message(user, fil, message: str, cerveau: Cerveau, reglages: ReglagesCerveau) -> None:
    """Modifier et relancer : le dernier message de la personne et tout ce qui a suivi sont retirés de l'historique du cerveau
    (l'écran les masque grâce à l'événement « retrait ») ; le travail déjà écrit dans l'agent, lui, reste (il est sur le disque)."""
    if en_cours(fil.id):
        raise ErreurFil("Stop the builder before editing your last message.", "en_cours")
    conv = _conversation_de(fil)
    messages = conv["messages"]
    rang = next((i for i in range(len(messages) - 1, -1, -1) if messages[i]["role"] == "user"), None)
    if rang is None:
        raise ErreurFil("There is no message to edit.", "aucun_message", 422)
    depuis = conv.get("dernier_message")
    historique = {**(fil.historique or {}), "messages": messages[:rang]}
    await db_client.modifier_fil(user.selected_organization_id, fil.id, historique=historique)
    fil.historique = historique
    await noter(fil.id, {"type": "retrait", "depuis": depuis})
    await lancer(user, fil, message, cerveau, reglages)


async def attendre(fil_id: int) -> None:
    """Attend la fin du travail de fond (les tests, l'arrêt propre)."""
    tache = _TACHES.get(fil_id)
    if tache is not None:
        try:
            await tache
        except asyncio.CancelledError:
            pass


async def au_demarrage() -> int:
    """À appeler une fois au démarrage du serveur : les conversations restées « en_cours » n'ont plus de tâche. Elles passent à
    « arretee », avec leur événement de fin, et « Reprendre » les relance depuis le disque."""
    touches = await db_client.arreter_les_fils_en_cours()
    for _org, fil_id in touches:
        await noter(fil_id, {"type": "fin", "raison": "redemarrage"})
    if touches:
        logger.info(f"[builder] {len(touches)} conversation(s) arrêtée(s) par le redémarrage")
    return len(touches)
