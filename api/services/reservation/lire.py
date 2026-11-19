"""[.mark] La lecture de la réservation (chantier Partie 1, lot 7 ; E16) : un seul outil pour tout ce qui se lit, qui n'écrit JAMAIS rien.

Même règle nommée que la commande (``lecture_sur_une_copie``, ``commande/lire.py`` : une seule fonction) : chaque lecture s'exécute sur une copie profonde de
l'état de la réservation ; la réservation de l'appel est rendue identique. R06 : les places se lisent pour le jour et le nombre de personnes DITS, à défaut
ceux que la fiche a déjà gardés dans le brouillon, sans jamais les écrire. Un sujet sans réponse rend ``renseigne: false``, rien n'est deviné (E27).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from api.db.bases_clients import dates_futures
from api.services.actions_communes.arguments import lire_un_entier, lire_un_texte
from api.services.actions_communes.enveloppe import Enveloppe
from api.services.commande.lire import lecture_sur_une_copie
from api.services.mots_dits import heure_en_lettres, liste_dite
from api.services.reservation import moteur

NON_RENSEIGNE = "Cette information n'est pas renseignée."
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


async def _places_libres(source: Any, copie: dict[str, Any], arguments: dict[str, Any]) -> Enveloppe:
    brouillon = copie.get("brouillon") or {}
    jour = lire_un_texte(arguments, "jour") or brouillon.get("jour")
    if jour and jour == brouillon.get("jour_dit") and brouillon.get("jour"):
        jour = brouillon["jour"]   # le modèle relit le jour avec sa date : « samedi soir » garde son moment, jamais les créneaux du midi
    personnes = lire_un_entier(arguments.get("personnes")) or brouillon.get("personnes") or 1
    r = await moteur.disponibilites(source, copie, jour, personnes)
    if r.statut == "REFUSEE":   # un groupe trop grand : la raison et la suite, jamais des horaires ni « À quelle heure »
        return Enveloppe("LU", resultats=[{"operation": "lire", "sujet": "places_libres", "statut_du_module": r.statut}], raison=str(r.faits.get("detail") or "rien_a_faire"),
                         a_faire=str(r.faits.get("a_faire") or "") or None)
    if r.statut != "OK":
        return Enveloppe("A_PRECISER", resultats=[{"operation": "lire", "sujet": "places_libres", "statut_du_module": r.statut}], faits={"manque": r.manque or "jour"})
    faits = {
        "jour": dates_futures.jour_dit(date.fromisoformat(r.faits["jour"])), "horaires_libres": [c["heure_dite"] for c in r.faits.get("creneaux") or []],
        "complet": bool(r.faits.get("complet")),
    }
    return Enveloppe("LU", resultats=[{"operation": "lire", "sujet": "places_libres", "statut_du_module": r.statut}], faits=faits)


async def _horaires(source: Any) -> Enveloppe:
    services = await source.horaires()
    dits = [f"de {heure_en_lettres(s['debut'].hour, s['debut'].minute)} à {heure_en_lettres(s['fin'].hour, s['fin'].minute)}" for s in services]
    if not dits:
        return Enveloppe("LU", resultats=[{"operation": "lire", "sujet": "horaires"}], faits={"sujet": "horaires", "renseigne": False}, plus={"texte_a_dire": NON_RENSEIGNE})
    return Enveloppe("LU", resultats=[{"operation": "lire", "sujet": "horaires"}], faits={"horaires_de_reservation": liste_dite(dits)})


async def lire(source: Any, etat: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """Lit ``sujet`` sans rien changer ; rend l'enveloppe, statut ``LU`` (ou ``A_PRECISER`` quand le jour manque)."""
    sujet = str(arguments.get("sujet") or "").strip()
    copie = lecture_sur_une_copie(etat)
    if sujet == "places_libres":
        return (await _places_libres(source, copie, arguments)).vers_json()
    if sujet == "horaires":
        return (await _horaires(source)).vers_json()
    return Enveloppe(
        "LU", resultats=[{"operation": "lire", "sujet": sujet}], faits={"sujet": sujet, "renseigne": False}, plus={"texte_a_dire": NON_RENSEIGNE},
    ).vers_json()
