"""[.mark] Mécanisme commun : les outils de la réservation, joués comme les autres actions internes (deadline, estampille, résultat utile).

Le connecteur interne ``reservation`` (``integrations/connectors/actions/reservation.py``) rend ici : ``executer(action, arguments, ctx, delai_s)``.
L'état de la réservation en cours vit dans la fiche de l'appel (``ctx.fiche``), la source de la capacité est ouverte pour UN geste
(``source.ouvrir``), le moteur fait le travail et son ``Resultat`` fermé devient le retour de l'outil : ``{statut, faits, suggestion, manque}``.

- Les arguments du modèle sont coupés à ce que l'action déclare ; la base, l'établissement et l'organisation ne viennent jamais du modèle.
- Une panne de la capacité ou de la base ne casse jamais l'appel : ``INDISPONIBLE`` et la phrase de repli.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from loguru import logger

from api.schemas.apres_appel import numero_e164
from api.services.commande.resultat import Resultat, numero_est_dit
from api.services.reservation import moteur, source as registre_des_sources
from api.services.restauration import mesures as mesures_du_module

SOURCE_DE_L_OUTIL = "source"
PHRASE_DE_PANNE = "Je n'arrive pas à gérer la réservation à l'instant : je transmets votre demande à l'équipe, qui vous rappelle."


def _jsonable(valeur: Any) -> Any:
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, dict):
        return {str(k): _jsonable(v) for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in valeur]
    return valeur


GESTES_DITS_PAR_LE_CODE = ("reserver", "modifier_reservation", "annuler_reservation")


def _dit_par_le_code(nom: str, r: Resultat) -> bool:
    """W17 : la relecture (``manque`` = ``relecture`` ou ``confirmation``) et la confirmation finale (heure comprise) des gestes qui écrivent."""
    if nom not in GESTES_DITS_PAR_LE_CODE:
        return False
    return r.manque in ("relecture", "confirmation") or r.statut in ("ENREGISTREE", "OK") or numero_est_dit(r.faits)


def _retour(r: Resultat, nom: str = "") -> dict[str, Any]:
    sortie = {"statut": r.statut, "faits": _jsonable(r.faits), "suggestion": r.suggestion}
    if r.manque:
        sortie["manque"] = r.manque
    if _dit_par_le_code(nom, r):
        sortie["_restitution"] = "dit_par_le_code"  # le conseil de l'outil, réglable dans sa fiche (T-01) ; consommé par le connecteur
    return sortie


def _texte(arguments: dict[str, Any], cle: str) -> str | None:
    valeur = arguments.get(cle)
    return str(valeur).strip() or None if valeur is not None else None


def _entier(valeur: Any) -> int | None:
    if isinstance(valeur, bool):
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    return int(nombre) if nombre.is_integer() else None


async def _geste(source, etat: dict[str, Any], nom: str, a: dict[str, Any], appelant: moteur.Appelant) -> Resultat:
    if "personnes" in a and _entier(a["personnes"]) is None:
        return Resultat("ARGUMENT_INVALIDE", {}, "Pour combien de personnes exactement ?", "personnes")
    personnes = _entier(a["personnes"]) if "personnes" in a else None
    if nom == "disponibilites":
        return await moteur.disponibilites(source, etat, _texte(a, "jour"), personnes, _texte(a, "heure"))
    if nom == "reserver":
        return await moteur.reserver(
            source, etat, appelant, jour=_texte(a, "jour"), heure=_texte(a, "heure"), personnes=personnes, prenom=_texte(a, "prenom"),
            telephone=_texte(a, "telephone"), note=_texte(a, "note"), confirmer=a.get("confirmer") is True,
        )
    if nom == "modifier_reservation":
        return await moteur.modifier(
            source, etat, appelant, reference=_texte(a, "reference"), jour=_texte(a, "jour"), heure=_texte(a, "heure"), personnes=personnes,
            prenom=_texte(a, "prenom"), note=_texte(a, "note"), confirmer=a.get("confirmer") is True,
        )
    if nom == "annuler_reservation":
        return await moteur.annuler(source, etat, appelant, reference=_texte(a, "reference"), confirmer=a.get("confirmer") is True)
    if nom == "retrouver_reservation":
        return await moteur.retrouver(source, etat, appelant, reference=_texte(a, "reference"), jour=_texte(a, "jour"), prenom=_texte(a, "prenom"))
    raise ValueError(f"Geste de réservation inconnu : {nom!r}")


async def executer(action: Any, arguments: dict[str, Any], ctx: Any, delai_s: float) -> dict[str, Any]:
    """Un geste de la réservation. Ne lève pas pour une panne : ``INDISPONIBLE`` (R1 : au journal)."""
    etat = moteur.etat_du_dossier(ctx.fiche)
    appelant = moteur.Appelant(numero_e164((ctx.appel or {}).get("caller_number")), str(ctx.run_id) if ctx.run_id else None)
    try:
        async with registre_des_sources.ouvrir((ctx.reglages or {}).get(SOURCE_DE_L_OUTIL), ctx) as source:
            r = await _geste(source, etat, action.nom, arguments, appelant)
            if r.statut in ("ENREGISTREE", "OK") and action.nom in ("reserver", "modifier_reservation", "annuler_reservation"):
                try:
                    await source.apres_le_geste(action.nom, r, ctx)
                except Exception as erreur:  # noqa: BLE001 -- R1 : le portail relit la base ; un flux qui ne part pas ne casse jamais l'appel
                    logger.error(f"[.mark] Reservation tool {action.nom}: live feed not written: {erreur!r}")
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal, l'outil dit « indisponible », l'appel continue
        logger.error(f"[.mark] Reservation tool {action.nom} failed: {erreur!r}")
        panne = {"statut": "INDISPONIBLE", "faits": {}, "suggestion": PHRASE_DE_PANNE}
        mesures_du_module.de_la_reservation(ctx.fiche, action.nom, panne)
        return panne
    retour = _retour(r, action.nom)
    mesures_du_module.de_la_reservation(ctx.fiche, action.nom, retour)
    return retour
