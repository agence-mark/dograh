"""[.mark] L'ÉTAT de la réservation en cours, donné au modèle de conversation à chaque requête de l'étape (chantier Partie 1, lot 7 ; E20).

Même rôle que ``commande/etat_pour_le_modele.py`` : le modèle lit ici, en quelques lignes, ce que le code sait (ce qui est pris, la réservation de l'appel ou
retrouvée, la question en attente, ce qui manque ensuite) pour poser la bonne question sans appeler d'outil. Recopie de ``ReservationV6.etat``
(``banc-b13/reservation_b13.py``), aux noms de la version finale. Le texte se calcule SANS requête : sur l'état de la réservation de la fiche de l'appel
et sur ce que les gestes ont retenu (``retenir_la_reservation_visee``). Des faits, jamais une consigne de conduite. ⛔ Ne lève jamais.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes.enveloppe import QUESTIONS_DITES_PAR_LE_CODE
from typing import Any

from loguru import logger

from api.services.commande.etat_pour_le_modele import LIGNE_B, ligne_du_greffier
from api.services.reservation import moteur

ENTETE = "[État de la réservation, tenu par le code]"
NOMS_DES_QUESTIONS = {"recapitulatif": "récapitulatif", "recap_modif": "récapitulatif du changement", "choix": "choix", "annulation": "annulation"}
CLE_VISEE = "visee"  # dans l'état : ce que les gestes ont retenu de la réservation visée (personnes, quand_dit, prenom), pour l'état sans requête


def retenir_la_reservation_visee(etat: dict[str, Any], faits: dict[str, Any]) -> None:
    """Ce qu'un geste a dit de la réservation visée (enregistrée, retrouvée, changée) : gardé pour l'état, rien n'est relu."""
    etat[CLE_VISEE] = {k: faits.get(k) for k in ("numero", "personnes", "quand_dit", "prenom") if faits.get(k) is not None}


def _la_visee(etat: dict[str, Any]) -> str:
    v = etat.get(CLE_VISEE) or {}
    if not v:
        return ""
    return f"{moteur._personnes_dites(int(v['personnes']))}, {v['quand_dit']}, au nom de {v['prenom']}" if v.get("personnes") and v.get("quand_dit") else ""


def ce_qui_manque_ensuite(etat: dict[str, Any], numero_affiche: bool) -> str | None:
    if etat.get("derniere") or etat.get("cible"):
        return None
    if etat.get("recherche"):
        return "le nom et le jour de sa réservation d'avant"
    b = etat.get("brouillon") or {}
    if not b.get("personnes"):
        return "le nombre de personnes"
    if not b.get("jour"):
        return "le jour"
    if not b.get("heure"):
        return "l'heure"
    if not b.get("prenom"):
        return "le nom"
    if not numero_affiche and not b.get("telephone_dit"):
        return "le numéro de téléphone"
    return None


def objet_en_cours(etat: dict[str, Any]) -> bool:
    b = etat.get("brouillon") or {}
    return bool(any(b.get(k) for k in ("personnes", "jour", "heure", "prenom")) or etat.get("derniere") or etat.get("cible") or etat.get("recherche"))


def _question(q: dict[str, Any]) -> str:
    """Le texte n'y est que pour une question que le code dit lui-même ; le choix entre réservations n'a que ses candidats (ligne « Ses réservations à venir »)."""
    nom = NOMS_DES_QUESTIONS.get(q.get("type"), q.get("type"))
    dite = f" : « {q.get('texte') or ''} »" if q.get("type") in QUESTIONS_DITES_PAR_LE_CODE else ""
    return f"- Question en attente : {q['id']} ({nom}){dite} ; réponses : accepte, refuse, autre."


def texte(fiche: dict | None, appel: dict | None = None) -> str | None:
    """L'état de la réservation, au format de la version finale. ⛔ Ne lève jamais."""
    try:
        etat = moteur.etat_du_dossier(fiche) if isinstance(fiche, dict) else {}
        affiche = bool((appel or {}).get("caller_number"))
        b = etat.get("brouillon") or {}
        lignes = [ENTETE]
        derniere, cible, q = etat.get("derniere"), etat.get("cible"), CONV.question_de(etat)
        if derniere:
            lignes.append(f"- Réservation de cet appel : enregistrée, {_la_visee(etat)}. Une seule réservation par appel : ce qu'elle change maintenant change celle-ci.")
        elif cible:
            annulee = " (annulée)" if cible in (etat.get("annulees") or []) else ""
            lignes.append(f"- Réservation d'un appel précédent retrouvée : {_la_visee(etat)}{annulee}.")
        else:
            lignes.append("- Réservation de cet appel : pas encore enregistrée.")
        if q and q.get("type") == "choix":
            lignes.append("- Ses réservations à venir, dans cet ordre : " + " ; ".join(q.get("candidats_dits") or []) + ".")
        elif not derniere and not cible and not etat.get("recherche"):
            lignes.append("- Pris : " + " ; ".join([
                f"personnes {b['personnes']}" if b.get("personnes") else "personnes pas encore dites",
                f"jour {b['jour_dit'] if b.get('jour_dit') else b['jour']}" if b.get("jour") else "jour pas encore dit",
                f"heure {b['heure']}" if b.get("heure") else "heure pas encore dite",
                f"nom {b['prenom']}" if b.get("prenom") else "nom pas encore dit"]) + ".")
        if etat.get("modification"):
            lignes.append("- Changement en cours : " + ", ".join(f"{ {'prenom': 'nom'}.get(k, k)} {v}" for k, v in etat["modification"].items()) + ".")
        lignes.append("- Numéro de téléphone : " + ("celui d'où elle appelle, gardé." if affiche else (f"dicté : {b['telephone_dit']}." if b.get("telephone_dit") else "masqué : à demander quand l'état le dit.")))
        if q:
            lignes.append(_question(q))
        else:
            lignes.append("- Question en attente : aucune.")
            manque = ce_qui_manque_ensuite(etat, affiche)
            if manque:
                lignes.append(f"- Ce qui manque ensuite : {manque}.")
        greffier = ligne_du_greffier(fiche)
        if greffier:
            lignes.append(greffier)
        if objet_en_cours(etat) or q:
            lignes.append(LIGNE_B)
        return "\n".join(lignes)
    except Exception as erreur:  # noqa: BLE001 -- l'état ne coûte jamais la requête
        logger.warning(f"[reservation] état pour le modèle non calculé : {erreur!r}")
        return None


def ligne_de_l_appel(fiche: Any) -> str:
    """La ligne de la réservation dans l'état de l'appel montré à l'accueil (``banc-b13`` ``etat_appel_v6``, résumé de la réservation)."""
    etat = moteur.etat_du_dossier(fiche) if isinstance(fiche, dict) else {}
    if etat.get("derniere"):
        return f"- Réservation de cet appel : enregistrée, {_la_visee(etat)}." if _la_visee(etat) else "- Réservation de cet appel : enregistrée."
    if etat and (etat.get("brouillon") or etat.get("cible")):
        return "- Réservation de cet appel : commencée, pas encore enregistrée."
    return "- Réservation de cet appel : aucune."
