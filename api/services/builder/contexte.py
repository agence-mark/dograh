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
    ligne = await lire_contexte_agent(organization_id, workflow_id)
    await stock.ecrire(organization_id, cle_builder(workflow_id, "contexte"), {**ligne, "notes": notes[:20000]})


async def noter_un_candidat(organization_id: int, workflow_id: int, famille: str, slug: str, version: int) -> None:
    """La mention « contient des candidats » de l'agent (B35) : ce qu'il utilise de non prouvé."""
    ligne = await lire_contexte_agent(organization_id, workflow_id)
    candidats = [c for c in ligne.get("candidats") or [] if (c.get("famille"), c.get("slug")) != (famille, slug)]
    candidats.append({"famille": famille, "slug": slug, "version": version})
    await stock.ecrire(organization_id, cle_builder(workflow_id, "contexte"), {**ligne, "candidats": candidats})


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


async def enregistrer(organization_id: int, workflow_id: int, conversation: dict[str, Any]) -> None:
    messages = conversation["messages"]
    if len(messages) > CONVERSATION_MESSAGES_MAX:
        # Au-delà du plafond de lignes : les plus vieux passent au résumé, à une frontière de message utilisateur.
        coupure = _coupure(messages, len(messages) - CONVERSATION_MESSAGES_MAX)
        conversation["resume"] = _fusionner(conversation["resume"], _resume_sec(messages[:coupure]))
        conversation["messages"] = messages[coupure:]
    conversation["revision"] = int(conversation.get("revision", 0)) + 1
    await stock.ecrire(organization_id, cle_builder(workflow_id, "conversation"), conversation)


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
