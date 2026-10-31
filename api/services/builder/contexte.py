"""[.mark] Builder : le contexte permanent en trois couches (Q10) et la gestion du contexte de la conversation (B45).

Couches :
1. **conventions .mark** : l'élément ``conventions-mark/conventions`` de la bibliothèque (pour tous) ;
2. **contexte de l'agent** : ``MARK_BUILDER:<agent>:contexte`` (notes, candidats utilisés) ;
3. **préférences de la personne** : ``user_configurations``, clé ``MARK_BUILDER_PREFERENCES``.

Conversation : ``MARK_BUILDER:<agent>:conversation`` = un résumé + les 200 derniers messages (≤ 1 Mo). Quand
elle approche la limite du cerveau (70 % de la fenêtre), les vieux tours sont RÉSUMÉS et l'**état actuel est relu
sur le disque** (fiche, document de conception, changements en attente, derniers résultats de tests) pour être
réinjecté : ce que le résumé aurait perdu n'est jamais la seule trace. Les consignes et la description des outils
sont mises en cache chez le fournisseur qui le permet (``cerveau/appel.py``).
"""

from __future__ import annotations

import json
import time
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.builder import brouillon, conception, stock
from api.services.builder import fiche as service_fiche
from api.services.builder.bibliotheque import service as service_bibliotheque
from api.services.builder.bibliotheque.familles import FAMILLE_CONVENTIONS
from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau
from api.services.builder.constantes import (
    CLE_PREFERENCES,
    CONVERSATION_MESSAGES_MAX,
    CONVERSATION_OCTETS_MAX,
    MESSAGE_OCTETS_MAX,
    cle_builder,
)

CONVENTIONS_SLUG = "conventions"
SEUIL_DE_COMPACTAGE = 0.7
MESSAGES_GARDES = 6
RESUME_MAX = 6000
RESULTAT_OUTIL_MAX = 8000
OCTETS_PAR_JETON = 3.5

CONSIGNE_DE_RESUME = (
    "Tu résumes le début d'une conversation de construction d'agent vocal pour la reprendre plus tard. "
    "Garde : ce que la personne a demandé et décidé, ce qui a été fait (actions et leur résultat), ce qui reste "
    "à faire, les questions ouvertes. N'invente rien. Réponds par un résumé court en français."
)


# --- couche 2 : le contexte de l'agent ---------------------------------------------------------------------------


async def lire_contexte_agent(organization_id: int, workflow_id: int) -> dict[str, Any]:
    return await stock.lire(organization_id, cle_builder(workflow_id, "contexte")) or {"notes": "", "candidats": []}


async def ecrire_notes(organization_id: int, workflow_id: int, notes: str) -> None:
    await stock.modifier(
        organization_id,
        cle_builder(workflow_id, "contexte"),
        lambda ligne: {**(ligne or {"notes": "", "candidats": []}), "notes": notes[:20000]},
    )


async def noter_un_candidat(organization_id: int, workflow_id: int, famille: str, slug: str, version: int) -> None:
    """La mention « contient des candidats » de l'agent (B35) : ce qu'il utilise de non prouvé."""

    def transformer(brut):
        ligne = brut or {"notes": "", "candidats": []}
        candidats = [c for c in ligne.get("candidats") or [] if (c.get("famille"), c.get("slug")) != (famille, slug)]
        candidats.append({"famille": famille, "slug": slug, "version": version})
        return {**ligne, "candidats": candidats}

    await stock.modifier(organization_id, cle_builder(workflow_id, "contexte"), transformer)


# --- couches 1 et 3 ----------------------------------------------------------------------------------------------


async def conventions() -> str:
    try:
        element = await service_bibliotheque.element_ou_none(FAMILLE_CONVENTIONS, CONVENTIONS_SLUG)
    except Exception:  # noqa: BLE001 -- une bibliothèque illisible ne coupe pas le builder
        return ""
    return str(element.courante.contenu.get("texte") or "") if element else ""


async def preferences(user_id: int | None) -> str:
    if user_id is None:
        return ""
    valeur = await db_client.get_user_configuration_value(user_id, CLE_PREFERENCES)
    return str((valeur or {}).get("texte") or "")


async def ecrire_preferences(user_id: int, texte: str) -> None:
    await db_client.upsert_user_configuration_value(user_id, CLE_PREFERENCES, {"texte": texte[:5000]})


# --- la conversation ---------------------------------------------------------------------------------------------


def conversation_vide() -> dict[str, Any]:
    return {"resume": "", "messages": [], "depense": {"jetons": 0, "cout": 0.0}, "revision": 0}


async def charger(organization_id: int, workflow_id: int) -> dict[str, Any]:
    brut = await stock.lire(organization_id, cle_builder(workflow_id, "conversation"))
    if not brut:
        return conversation_vide()
    return {**conversation_vide(), **brut}


class ConflitDeRevision(Exception):
    """La conversation a été écrite par un autre depuis qu'on l'a lue : cette écriture est refusée (rien n'est écrasé)."""


def _octets(conversation: dict[str, Any]) -> int:
    return len(json.dumps(conversation, ensure_ascii=False, default=str).encode("utf-8"))


def borner(conversation: dict[str, Any]) -> None:
    """Le plafond de la conversation enregistrée : ``CONVERSATION_MESSAGES_MAX`` lignes ET ``CONVERSATION_OCTETS_MAX`` octets (revue N4).
    Les plus vieux messages passent au résumé, à une frontière de message utilisateur ; un message seul plus gros que le plafond
    est raccourci. Modifie ``conversation`` en place."""
    messages = conversation["messages"]
    if len(messages) > CONVERSATION_MESSAGES_MAX:
        # Au-delà du plafond de lignes : les plus vieux passent au résumé, à une frontière de message utilisateur.
        coupure = _coupure(messages, len(messages) - CONVERSATION_MESSAGES_MAX)
        conversation["resume"] = _fusionner(conversation["resume"], _resume_sec(messages[:coupure]))
        conversation["messages"] = messages[coupure:]
    while _octets(conversation) > CONVERSATION_OCTETS_MAX:
        messages = conversation["messages"]
        coupure = _coupure(messages, 1)
        if coupure == 0:  # plus de tour entier à résumer : on raccourcit ce qui reste
            for m in messages:
                if isinstance(m.get("content"), str) and len(m["content"]) > MESSAGE_OCTETS_MAX:
                    m["content"] = m["content"][:MESSAGE_OCTETS_MAX] + "\n[... truncated]"
            break
        conversation["resume"] = _fusionner(conversation["resume"], _resume_sec(messages[:coupure]))
        conversation["messages"] = messages[coupure:]


async def enregistrer(organization_id: int, workflow_id: int, conversation: dict[str, Any]) -> None:
    """Écrit la conversation si personne ne l'a écrite depuis qu'on l'a lue (condition sur ``revision``, revue R6)."""
    borner(conversation)
    lue = int(conversation.get("revision", 0))

    def ecrire(courant: dict[str, Any] | None) -> dict[str, Any]:
        if courant is not None and int(courant.get("revision", 0)) != lue:
            raise ConflitDeRevision("The conversation was written by someone else in the meantime.")
        return {**conversation, "revision": lue + 1}

    ecrite = await stock.modifier(organization_id, cle_builder(workflow_id, "conversation"), ecrire)
    conversation["revision"] = int((ecrite or {}).get("revision", lue + 1))


async def prendre_le_verrou(organization_id: int, workflow_id: int, delai_s: float, maintenant: float | None = None) -> dict[str, Any] | None:
    """Prend le verrou de la conversation EN UNE ÉCRITURE ATOMIQUE (revue R6) : la conversation à jour avec ``en_cours_depuis``, ou ``None``
    si une autre tourne déjà (verrou plus récent que ``delai_s``). Deux demandes simultanées : une seule l'obtient."""
    instant = time.time() if maintenant is None else maintenant
    prise: dict[str, Any] = {}

    def prendre(courant: dict[str, Any] | None) -> dict[str, Any] | None:
        conversation = {**conversation_vide(), **(courant or {})}
        depuis = conversation.get("en_cours_depuis")
        if depuis and instant - float(depuis) < delai_s:
            prise["conversation"] = None
            return None
        conversation["en_cours_depuis"] = instant
        conversation["revision"] = int(conversation.get("revision", 0)) + 1
        prise["conversation"] = conversation
        return conversation

    await stock.modifier(organization_id, cle_builder(workflow_id, "conversation"), prendre)
    return prise["conversation"]


def tronquer(contenu: str) -> str:
    if len(contenu) <= RESULTAT_OUTIL_MAX:
        return contenu
    return contenu[:RESULTAT_OUTIL_MAX] + f"\n[... truncated, {len(contenu) - RESULTAT_OUTIL_MAX} characters left out]"


def estimer_jetons(systeme: str, messages: list[dict[str, Any]], resume: str = "") -> int:
    taille = len(systeme) + len(resume) + sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
    return int(taille / OCTETS_PAR_JETON)


def _coupure(messages: list[dict[str, Any]], minimum: int) -> int:
    """Premier rang >= minimum où un message utilisateur commence : on ne coupe jamais entre un appel et son résultat."""
    for rang in range(max(minimum, 0), len(messages)):
        if messages[rang]["role"] == "user":
            return rang
    return 0


def _resume_sec(messages: list[dict[str, Any]]) -> str:
    """Résumé sans cerveau (repli) : les demandes de la personne et les actions faites."""
    lignes: list[str] = []
    for m in messages:
        if m["role"] == "user":
            lignes.append(f"- Demande : {str(m['content'])[:200]}")
        elif m["role"] == "assistant" and m.get("appels"):
            lignes.append("- Actions : " + ", ".join(a["nom"] for a in m["appels"]))
    return "\n".join(lignes)


def _fusionner(ancien: str, nouveau: str) -> str:
    texte = f"{ancien}\n{nouveau}".strip()
    return texte[-RESUME_MAX:]


async def compacter_si_besoin(
    conversation: dict[str, Any], cerveau: Cerveau, systeme: str, fenetre: int
) -> dict[str, int] | None:
    """Résume les vieux tours quand la conversation dépasse 70 % de la fenêtre. Rend l'usage du résumé (ou ``None``).

    Les ``MESSAGES_GARDES`` derniers messages restent tels quels (coupés à une frontière utilisateur)."""
    messages = conversation["messages"]
    if estimer_jetons(systeme, messages, conversation["resume"]) < SEUIL_DE_COMPACTAGE * fenetre:
        return None
    coupure = _coupure(messages, len(messages) - MESSAGES_GARDES)
    if coupure <= 0:
        return None
    anciens = messages[:coupure]
    usage = {"entree": 0, "sortie": 0}
    resume = ""
    try:
        transcription = conversation["resume"] + "\n" + json.dumps(anciens, ensure_ascii=False)[:60000]
        async for evenement in cerveau.tour(
            systeme=CONSIGNE_DE_RESUME, messages=[{"role": "user", "content": transcription}], outils=[]
        ):
            if evenement["type"] == "texte":
                resume += evenement["texte"]
            elif evenement["type"] == "usage":
                usage = {"entree": evenement.get("entree", 0), "sortie": evenement.get("sortie", 0)}
    except ErreurCerveau as erreur:
        logger.warning(f"[builder] résumé par le cerveau impossible ({erreur.code}), repli sans cerveau")
        resume = ""
    if not resume.strip():
        resume = _resume_sec(anciens)
    conversation["resume"] = _fusionner(conversation["resume"], resume.strip())
    conversation["messages"] = messages[coupure:]
    return usage


# --- l'état relu sur le disque (B45) -----------------------------------------------------------------------------


def _borner(texte: str, limite: int) -> str:
    return texte if len(texte) <= limite else texte[:limite] + "…"


async def etat_du_disque(organization_id: int, workflow_id: int) -> str:
    """Ce qui est vrai MAINTENANT, relu sur le disque : fiche, conception, changements en attente, derniers tests."""
    fiche = await service_fiche.lire(organization_id, workflow_id)
    etat_conception = await conception.lire(organization_id, workflow_id)
    en_attente = await brouillon.lire_en_attente(organization_id, workflow_id)
    contexte = await lire_contexte_agent(organization_id, workflow_id)
    parties = ["## État actuel (relu sur le disque, c'est la vérité)"]
    if fiche.champs or fiche.trous:
        statut = f"validée par {fiche.valide_par}" if fiche.validee else "NON validée"
        parties.append(
            f"Fiche client ({statut}, {len(fiche.champs)} lignes, {len(fiche.trous)} trou(s) ouvert(s)) :\n"
            + _borner(json.dumps(fiche.model_dump(mode="json", exclude={"valide_le"}), ensure_ascii=False), 6000)
        )
    else:
        parties.append("Fiche client : vide.")
    if etat_conception is not None:
        parties.append(
            f"Document de conception ({etat_conception.etat}, révision {etat_conception.revision}"
            + (f", note : {etat_conception.note}" if etat_conception.note else "")
            + ") :\n"
            + _borner(json.dumps(etat_conception.conception.model_dump(mode="json"), ensure_ascii=False), 4000)
        )
    else:
        parties.append("Document de conception : aucun (rien ne se construit avant son approbation).")
    parties.append(f"Changements en attente : {len(en_attente.get('operations') or [])} opération(s).")
    if contexte.get("candidats"):
        parties.append(
            "Cet agent contient des candidats (non prouvés) : "
            + ", ".join(f"{c['famille']}/{c['slug']} v{c['version']}" for c in contexte["candidats"])
        )
    if contexte.get("notes"):
        parties.append("Contexte de l'agent :\n" + _borner(str(contexte["notes"]), 3000))
    resultats = await _derniers_resultats_de_tests(organization_id, workflow_id)
    parties.append(resultats or "Derniers résultats de tests : aucun.")
    return "\n\n".join(parties)


async def _derniers_resultats_de_tests(organization_id: int, workflow_id: int) -> str:
    """Lit ce que les lots de tests rangent (``MARK_TESTS_RESULTATS:<agent>:*``) ; rien tant qu'ils n'existent pas."""
    lignes = await stock.lister(organization_id, f"MARK_TESTS_RESULTATS:{workflow_id}:")
    if not lignes:
        return ""
    return "Derniers résultats de tests :\n" + _borner(json.dumps([v for _k, v in lignes[-5:]], ensure_ascii=False), 3000)
