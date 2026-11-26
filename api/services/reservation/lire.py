"""[.mark] La lecture de la réservation (chantier Partie 1, lot 7 ; E16) : un seul outil pour tout ce qui se lit, qui n'écrit JAMAIS rien.

Même règle nommée que la commande (``lecture_sur_une_copie``, ``commande/lire.py`` : une seule fonction) : chaque lecture s'exécute sur une copie profonde de
l'état de la réservation ; la réservation de l'appel est rendue identique. R06 : les places se lisent pour le jour et le nombre de personnes DITS, à défaut
ceux que la fiche a déjà gardés dans le brouillon, sans jamais les écrire. Un sujet sans réponse rend ``renseigne: false``, rien n'est deviné (E27).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from api.db.bases_clients import dates_futures
from api.db.bases_clients.capacite import GROUPE_TROP_GRAND
from api.services.actions_communes.arguments import lire_un_entier, lire_un_texte
from api.services.actions_communes.enveloppe import Enveloppe
from api.services.commande.lire import lecture_sur_une_copie
from api.services.mots_dits import heure_en_lettres, liste_dite
from api.services.reservation import moteur

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

# F6 (lot 7b-C7), puis C7 B9 : la suite d'un groupe trop grand, la même partout où il est refusé (avant le jour, capacité du jour, enregistrement, changement).
# C'est une consigne au modèle : elle vit dans la porte de la réservation (ici, que la porte et la lecture lisent), jamais dans les faits de la base.
A_FAIRE_DU_GROUPE = "dis-lui qu'un groupe de cette taille se règle avec l'équipe et propose de laisser un message à l'équipe"


def a_faire_du_refus(faits: dict[str, Any] | None) -> str | None:
    """La consigne que la porte pose sur un refus de la base, lue de son ``detail`` (liste fermée) : seul le groupe trop grand en a une."""
    return A_FAIRE_DU_GROUPE if (faits or {}).get("detail") == GROUPE_TROP_GRAND else None


async def _places_libres(source: Any, copie: dict[str, Any], arguments: dict[str, Any]) -> Enveloppe:
    brouillon = copie.get("brouillon") or {}
    jour = lire_un_texte(arguments, "jour") or brouillon.get("jour")
    if jour and jour == brouillon.get("jour_dit") and brouillon.get("jour"):
        jour = brouillon["jour"]   # le modèle relit le jour avec sa date : « samedi soir » garde son moment, jamais les créneaux du midi
    personnes = lire_un_entier(arguments.get("personnes")) or brouillon.get("personnes") or 1
    r = await moteur.disponibilites(source, copie, jour, personnes)
    if r.statut == "REFUSEE":   # un groupe trop grand : la raison et la suite, jamais des horaires ni « À quelle heure »
        return Enveloppe("LU", resultats=[{"operation": "lire", "sujet": "places_libres", "statut_du_module": r.statut}], raison=str(r.faits.get("detail") or "rien_a_faire"),
                         a_faire=a_faire_du_refus(r.faits))
    if r.statut != "OK":
        manque = {"manque": r.manque or "jour"}   # F5 : un jour ambigu garde les jours possibles dits (« ce jeudi ou le suivant ? »), jamais ``candidats`` et leurs dates
        if r.faits.get("jours_possibles"):
            manque["jours_possibles"] = r.faits["jours_possibles"]
        return Enveloppe("A_PRECISER", resultats=[{"operation": "lire", "sujet": "places_libres", "statut_du_module": r.statut}], faits=manque)
    faits = {
        "jour": dates_futures.jour_dit(date.fromisoformat(r.faits["jour"])), "horaires_libres": [c["heure_dite"] for c in r.faits.get("creneaux") or []],
        "complet": bool(r.faits.get("complet")),
    }
    return Enveloppe("LU", resultats=[{"operation": "lire", "sujet": "places_libres", "statut_du_module": r.statut}], faits=faits)


async def _horaires(source: Any) -> Enveloppe:
    services = await source.horaires()
    dits = [f"de {heure_en_lettres(s['debut'].hour, s['debut'].minute)} à {heure_en_lettres(s['fin'].hour, s['fin'].minute)}" for s in services]
    if not dits:
        return Enveloppe("LU", resultats=[{"operation": "lire", "sujet": "horaires"}], faits={"sujet": "horaires", "renseigne": False})
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
        "LU", resultats=[{"operation": "lire", "sujet": sujet}], faits={"sujet": sujet, "renseigne": False},
    ).vers_json()
