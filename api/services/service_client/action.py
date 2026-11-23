"""[.mark] Module Restauration, lot 7 (W44, W23, E-15) : les trois outils du service à l'appelant, joués comme les autres actions internes.

Le connecteur interne ``service`` (``integrations/connectors/actions/service.py``) rend ici : ``executer(action, arguments, ctx, delai_s)``.

- ``infos_pratiques`` (W44) : une information pratique (horaires, accès, paiement…) lue dans la CONNAISSANCE de l'agent, un document par SUJET d'une liste
  fermée. Le réglage ``sujets`` de l'outil dit quel document répond à quel sujet ; le texte est lu en entier (aucune recherche approchée, aucun appel à un
  fournisseur). Un sujet sans document, ou un document vide : ``INCONNU`` et « je ne peux pas vous le confirmer », jamais une réponse inventée ni un passage de main (E-15).
- ``laisser_un_message`` (W23) : une demande de rappel écrite dans la fiche de l'appel, avec son URGENCE prise dans une liste fermée (``normale`` | ``urgente``) ;
  une valeur hors liste est refusée, jamais devinée. M102 (SA-47, lot 3) : le message de toute personne (client, fournisseur, administration,
  démarcheur) porte l'objet tel que dit, le prénom et le nom, l'organisme s'il y en a un, et un numéro : UN manque à la fois (objet, nom et prénom,
  numéro seulement si aucun ne s'affiche ou si la personne en donne un autre). Ce qui est dit est gardé d'un appel du geste au suivant ; le numéro
  dicté est relu par le code une fois (``avec_numeros_retenus``), celui qui s'affiche est gardé sans relecture. Le message laissé pose l'issue de
  l'appel réglée sur l'outil (réglage ``call_disposition``), jamais devinée.
- ``passage_de_main`` (E-15) : la porte avant un transfert vers l'équipe. SEULEMENT sur une plainte ou un problème réel (2 motifs, réglage ``motifs`` de l'outil,
  qui ne peut que restreindre) : ``PASSER`` (l'agent peut alors passer par ``diriger_vers_personne``, le routage de l'équipe) quand l'appel a une équipe à joindre ;
  tout autre motif, ou une équipe vide, devient une demande de rappel (``RAPPEL_NOTE``), jamais un transfert promis à tort.

Aucun mot de métier : les sujets, les motifs et les urgences sont des listes fermées ; leurs phrases viennent de l'outil. Chaque geste est mesuré (W13).
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from api.schemas.apres_appel import numero_e164
from api.services.actions_communes import phrases_d_information as INFO
from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_AGENT
from api.services.commande.resultat import (
    Resultat,
    avec_numeros_retenus,
    numero_est_dit,
)
from api.services.equipe.appel import cles_de_lappel
from api.services.integrations.connectors import mesures

SUJETS = {
    "horaires": "les horaires", "acces": "l'accès", "stationnement": "le stationnement", "paiement": "les moyens de paiement",
    "accessibilite": "l'accessibilité", "animaux": "les animaux", "groupes_et_evenements": "les groupes et les événements", "contact": "les coordonnées",
}
URGENCES = ("normale", "urgente")
MOTIFS_DE_PASSAGE = ("plainte", "probleme_reel")
MOTIFS_DITS = (*MOTIFS_DE_PASSAGE, "autre")
PHRASE_INCONNUE = INFO.NON_CONFIRMABLE
# M102 : le message en cours (gardé d'un appel du geste au suivant) et l'issue que l'outil pose quand il est laissé.
CLE_MESSAGE = "service_message_en_cours"
REGLAGE_ISSUE = "call_disposition"
LONGUEUR_NOM = 60
LONGUEUR_ORGANISME = 100


def _texte(arguments: dict[str, Any], cle: str) -> str | None:
    valeur = arguments.get(cle)
    return str(valeur).strip() or None if valeur is not None else None


# M122 : un titre (« Madame ») n'est pas un prénom. Mots de la langue, aucun mot de métier.
_TITRE = re.compile(r"^(?:monsieur|madame|mademoiselle|mme|mlle|m\.?|mr\.?)(?:\s+|$)", re.IGNORECASE)


def _prenom_sans_titre(valeur: str | None) -> str | None:
    """« Madame » → ``None`` ; « Monsieur Paul » → « Paul »."""
    return _TITRE.sub("", valeur).strip() or None if valeur else None


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


def _ecrire_la_demande(ctx: Any, objet: str | None, urgence: str, motif: str | None, qui: dict[str, Any] | None = None) -> bool:
    if not isinstance(ctx.fiche, dict):
        return False
    qui = qui or {}
    entree = {
        "origine": ORIGINE_AGENT, "mode": "rappel", "numero": qui.get("numero") or numero_e164((ctx.appel or {}).get("caller_number")) or None,
        "objet": objet, "souhait": None, "urgence": urgence, "motif": motif,
        **{cle: qui[cle] for cle in ("prenom", "nom", "organisme") if qui.get(cle)},
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


def _court(texte: str | None, longueur: int) -> str | None:
    return " ".join(texte.split())[:longueur] if texte and texte.strip() else None


def _question_du_nom(m: dict[str, Any]) -> str:
    if m.get("prenom"):
        return "Et votre nom ?"
    if m.get("nom"):
        return "Et votre prénom ?"
    return "C'est de la part de qui ? Votre prénom et votre nom, s'il vous plaît."


def _poser_l_issue(ctx: Any) -> None:
    """M102 : le message laissé pose l'issue de l'appel réglée sur l'outil (une issue de la liste de l'agent, réservée à ce résultat réel),
    jamais une issue devinée ; sans réglage, rien (le classement final décide, comme avant). ⛔ Ne lève jamais."""
    try:
        code = (ctx.reglages or {}).get(REGLAGE_ISSUE)
        if isinstance(code, str) and code.strip() and isinstance(ctx.fiche, dict):
            ctx.fiche["call_disposition"] = code.strip()
    except Exception:  # noqa: BLE001
        pass


async def laisser_un_message(arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    urgence = (_texte(arguments, "urgence") or "normale").casefold()
    if urgence not in URGENCES:
        return _retour("ARGUMENT_INVALIDE", {"possibles": list(URGENCES)}, "", "urgence")
    fiche = ctx.fiche if isinstance(ctx.fiche, dict) else {}
    m = fiche.get(CLE_MESSAGE) if isinstance(fiche.get(CLE_MESSAGE), dict) else {}
    # Ce qui est dit dans cet appel du geste est GARDÉ : le modèle n'a pas à tout renvoyer, rien n'est redemandé.
    for cle, longueur in (("objet", 500), ("prenom", LONGUEUR_NOM), ("nom", LONGUEUR_NOM), ("organisme", LONGUEUR_ORGANISME)):
        dit = _prenom_sans_titre(_texte(arguments, cle)) if cle == "prenom" else _texte(arguments, cle)
        if (valeur := _court(dit, longueur)) is not None:
            m[cle] = valeur
    affiche = numero_e164((ctx.appel or {}).get("caller_number")) or None
    dit = _texte(arguments, "telephone")
    if dit:
        numero = numero_e164(dit)
        if numero is None:
            if isinstance(ctx.fiche, dict):
                ctx.fiche[CLE_MESSAGE] = m
            return _retour("ARGUMENT_INVALIDE", {}, "Je n'ai pas bien compris le numéro : vous pouvez le redire ?", "telephone")
        m["telephone"] = numero
    if isinstance(ctx.fiche, dict):
        ctx.fiche[CLE_MESSAGE] = m
    if not m.get("objet"):
        return _retour("INCOMPLETE", {}, "Que voulez-vous que l'équipe sache ?", "objet")
    if not (m.get("prenom") and m.get("nom")):
        return _retour("INCOMPLETE", {}, _question_du_nom(m), "nom")
    numero = m.get("telephone") or affiche
    if not numero:
        return _retour("INCOMPLETE", {}, "À quel numéro l'équipe peut-elle vous rappeler ?", "telephone")
    qui = {"prenom": m["prenom"], "nom": m["nom"], "organisme": m.get("organisme"), "numero": numero}
    if not _ecrire_la_demande(ctx, m["objet"], urgence, None, qui):
        return _retour("INDISPONIBLE", {}, "")
    mesures.ecrire(ctx.fiche, "service.message_laisse", "service.laisser_un_message", urgence)
    _poser_l_issue(ctx)
    r = Resultat("OK", {"urgence": urgence}, "C'est noté, l'équipe vous rappelle.")
    # Le numéro DICTÉ (pas celui qui s'affiche) est relu par le code, une fois tant qu'il ne change pas.
    relire = numero if numero != affiche and m.get("numero_dit") != numero else None
    if relire:
        m["numero_dit"] = relire
        r = avec_numeros_retenus(r, relire)
    retour = _retour(r.statut, r.faits, r.suggestion, r.manque)
    if numero_est_dit(r.faits):
        retour["_restitution"] = "dit_par_le_code"  # le numéro retenu se dit tel quel, jamais de mémoire (comme la commande et la réservation)
    return retour


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
