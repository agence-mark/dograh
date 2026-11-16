"""[.mark] Module Restauration, lot 7 (W44, W23, E-15) : les trois outils du service à l'appelant, joués comme les autres actions internes.

Le connecteur interne ``service`` (``integrations/connectors/actions/service.py``) rend ici : ``executer(action, arguments, ctx, delai_s)``.

- ``infos_pratiques`` (W44) : une information pratique (horaires, accès, paiement…) lue dans la CONNAISSANCE de l'agent, un document par SUJET d'une liste
  fermée. Le réglage ``sujets`` de l'outil dit quel document répond à quel sujet ; le texte est lu en entier (aucune recherche approchée, aucun appel à un
  fournisseur). Un sujet sans document, ou un document vide : ``INCONNU`` et « je ne peux pas vous le confirmer », jamais une réponse inventée ni un passage de main (E-15).
- ``laisser_un_message`` (W23) : une demande de rappel écrite dans la fiche de l'appel, avec son URGENCE prise dans une liste fermée (``normale`` | ``urgente``) ;
  une valeur hors liste est refusée, jamais devinée.
- ``passage_de_main`` (E-15) : la porte avant un transfert vers l'équipe. SEULEMENT sur une plainte ou un problème réel (2 motifs, réglage ``motifs`` de l'outil,
  qui ne peut que restreindre) : ``PASSER`` (l'agent peut alors passer par ``diriger_vers_personne``, le routage de l'équipe) quand l'appel a une équipe à joindre ;
  tout autre motif, ou une équipe vide, devient une demande de rappel (``RAPPEL_NOTE``), jamais un transfert promis à tort.

Aucun mot de métier : les sujets, les motifs et les urgences sont des listes fermées ; leurs phrases viennent de l'outil. Chaque geste est mesuré (W13).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.schemas.apres_appel import numero_e164
from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_AGENT
from api.services.equipe.appel import cles_de_lappel
from api.services.integrations.connectors import mesures

SUJETS = {
    "horaires": "les horaires", "acces": "l'accès", "stationnement": "le stationnement", "paiement": "les moyens de paiement",
    "accessibilite": "l'accessibilité", "animaux": "les animaux", "groupes_et_evenements": "les groupes et les événements", "contact": "les coordonnées",
}
URGENCES = ("normale", "urgente")
MOTIFS_DE_PASSAGE = ("plainte", "probleme_reel")
MOTIFS_DITS = (*MOTIFS_DE_PASSAGE, "autre")
PHRASE_INCONNUE = "Je ne peux pas vous le confirmer."


def _texte(arguments: dict[str, Any], cle: str) -> str | None:
    valeur = arguments.get(cle)
    return str(valeur).strip() or None if valeur is not None else None


def _retour(statut: str, faits: dict[str, Any], suggestion: str = "", manque: str | None = None) -> dict[str, Any]:
    sortie: dict[str, Any] = {"statut": statut, "faits": faits, "suggestion": suggestion}
    if manque:
        sortie["manque"] = manque
    return sortie


async def _texte_du_sujet(sujets: Any, sujet: str, organisation: int | None) -> str | None:
    """Le texte du document de ce sujet, lu en entier ; ``None`` : pas de document, ou vide. Jamais une recherche approchée."""
    uuid = sujets.get(sujet) if isinstance(sujets, dict) else None
    if not uuid or organisation is None:
        return None
    from api.db import db_client

    documents = await db_client.get_full_text_documents(organisation, [str(uuid)])
    texte = "\n".join(str(d.full_text).strip() for d in documents if getattr(d, "full_text", None)).strip()
    return texte or None


async def infos_pratiques(arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    sujet = (_texte(arguments, "sujet") or "").casefold()
    if sujet not in SUJETS:
        return _retour("ARGUMENT_INVALIDE", {"possibles": list(SUJETS)}, "Sur quoi voulez-vous des précisions ?", "sujet")
    texte = await _texte_du_sujet((ctx.reglages or {}).get("sujets"), sujet, ctx.organization_id)
    if texte is None:
        mesures.ecrire(ctx.fiche, "service.info_inconnue", "service.infos_pratiques", sujet)
        return _retour("INCONNU", {"sujet": sujet}, PHRASE_INCONNUE)
    return _retour("OK", {"sujet": sujet, "texte": texte}, "")


def _ecrire_la_demande(ctx: Any, objet: str | None, urgence: str, motif: str | None) -> bool:
    if not isinstance(ctx.fiche, dict):
        return False
    entree = {
        "origine": ORIGINE_AGENT, "mode": "rappel", "numero": numero_e164((ctx.appel or {}).get("caller_number")) or None,
        "objet": objet, "souhait": None, "urgence": urgence, "motif": motif,
    }
    liste = ctx.fiche.setdefault(CLE_RAPPEL, [])
    if not isinstance(liste, list):
        liste = ctx.fiche[CLE_RAPPEL] = []
    for i, ancienne in enumerate(liste):
        if isinstance(ancienne, dict) and ancienne.get("origine") == ORIGINE_AGENT:
            liste[i] = entree                                   # une demande de rappel par appel : la nouvelle remplace l'ancienne
            return True
    liste.append(entree)
    return True


async def laisser_un_message(arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    urgence = (_texte(arguments, "urgence") or "normale").casefold()
    if urgence not in URGENCES:
        return _retour("ARGUMENT_INVALIDE", {"possibles": list(URGENCES)}, "", "urgence")
    objet = _texte(arguments, "objet")
    if objet is None:
        return _retour("INCOMPLETE", {}, "Que voulez-vous que l'équipe sache ?", "objet")
    if not _ecrire_la_demande(ctx, objet, urgence, None):
        return _retour("INDISPONIBLE", {}, "")
    mesures.ecrire(ctx.fiche, "service.message_laisse", "service.laisser_un_message", urgence)
    return _retour("OK", {"urgence": urgence}, "C'est noté, l'équipe vous rappelle.")


async def passage_de_main(arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    motif = (_texte(arguments, "motif") or "").casefold()
    if motif not in MOTIFS_DITS:
        return _retour("ARGUMENT_INVALIDE", {"possibles": list(MOTIFS_DITS)}, "", "motif")
    permis = (ctx.reglages or {}).get("motifs")
    permis = tuple(m for m in MOTIFS_DE_PASSAGE if m in permis) if isinstance(permis, (list, tuple)) else MOTIFS_DE_PASSAGE   # le réglage ne peut que restreindre
    objet = _texte(arguments, "objet")
    if motif in permis and cles_de_lappel(ctx.appel)[0]:
        mesures.ecrire(ctx.fiche, "service.passage_de_main", "service.passage_de_main", motif)
        return _retour("PASSER", {"motif": motif}, "Je vous passe quelqu'un de l'équipe.")
    # SA-18 (C12) : sans personne à joindre dans l'appel (aucune ligne d'équipe), « je vous passe quelqu'un » serait une promesse fausse :
    # la demande est notée, comme un motif qui ne passe pas.
    urgence = "normale"
    if not _ecrire_la_demande(ctx, objet, urgence, motif):
        return _retour("INDISPONIBLE", {}, "")
    mesures.ecrire(ctx.fiche, "service.message_laisse", "service.passage_de_main", urgence)
    return _retour("RAPPEL_NOTE", {"motif": motif}, "Je note votre demande, l'équipe vous rappelle.")


async def executer(action: Any, arguments: dict[str, Any], ctx: Any, delai_s: float) -> dict[str, Any]:
    """Un geste du service. Ne lève pas pour une panne : ``INDISPONIBLE`` (R1 : au journal)."""
    try:
        if action.nom == "infos_pratiques":
            return await infos_pratiques(arguments, ctx)
        if action.nom == "laisser_un_message":
            return await laisser_un_message(arguments, ctx)
        if action.nom == "passage_de_main":
            return await passage_de_main(arguments, ctx)
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal, l'outil dit « indisponible », l'appel continue
        logger.error(f"[.mark] Service tool {action.nom} failed: {erreur!r}")
        return _retour("INDISPONIBLE", {}, "")
    raise ValueError(f"Geste de service inconnu : {action.nom!r}")
