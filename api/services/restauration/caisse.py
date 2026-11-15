"""[.mark] Module Restauration, lot 9 : ce que le portail demande à la liaison avec la caisse (fiche de liaison, rupture poussée à la caisse).

Générique : seule la FICHE de la prise est lue, jamais un nom de fournisseur. Rien de ce qui part vers la caisse ne bloque le classeur : une rupture est d'abord
posée chez nous (l'agent la respecte aussitôt), puis poussée ; si la caisse ne répond pas, la liaison le dit (code fermé) et la réponse dit
``poussee_a_la_caisse: false`` : jamais un échec silencieux (R1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg
from loguru import logger

from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as liaison_db
from api.services.restauration import flux
from api.services.restauration.prises.capacites import Capacites
from api.services.restauration.prises.prise import ContexteDePrise, capacites_de, prise_de_l_etablissement
from api.services.restauration.synchro_caisse import code_d_erreur, dire_la_liaison

PRISE_SANS_CAISSE = "portail"


def capacites_rendues(capacites: Capacites) -> dict[str, Any]:
    """La fiche pour l'écran : listes triées, sans l'adresse des fournisseurs (liste fermée côté serveur seulement)."""
    return {
        "carte": capacites.carte, "carte_notifiee": capacites.carte_notifiee, "ruptures": capacites.ruptures,
        "ruptures_posees_par_nous": capacites.ruptures_posees_par_nous, "etat_restaurant": capacites.etat_restaurant,
        "temps_preparation": capacites.temps_preparation, "horaires": capacites.horaires, "commande_non_payee": capacites.commande_non_payee,
        "controle_avant_creation": capacites.controle_avant_creation, "annulation": capacites.annulation, "etapes": sorted(capacites.etapes),
        "anti_doublon": capacites.anti_doublon, "notifications": capacites.notifications, "clients_lus": capacites.clients_lus,
        "remises_lues": capacites.remises_lues, "represente": sorted(capacites.represente), "limites": list(capacites.limites),
    }


async def fiche_de_liaison(connexion: asyncpg.Connection, etablissement_id: int) -> dict[str, Any]:
    """``GET …/caisse`` : prise, capacités, état, dernière erreur, dernière synchro, état que la caisse porte. Sans liaison : le portail, état ``aucune``."""
    liaison = await liaison_db.liaison(connexion, etablissement_id)
    nom = liaison["prise"] if liaison else PRISE_SANS_CAISSE
    etat = await restauration.etat_caisse(connexion, etablissement_id)
    return {
        "prise": nom,
        "etat": liaison["etat"] if liaison else "aucune",
        "derniere_erreur": liaison["derniere_erreur"] if liaison else None,
        "derniere_synchro": liaison["derniere_synchro"] if liaison else None,
        "point_de_vente": liaison["point_de_vente"] if liaison else None,
        "mode_passif": liaison["mode_passif"] if liaison else False,
        "derniere_releve": liaison["derniere_releve"] if liaison else None,
        "avertissements": liaison["avertissements"] if liaison else [],
        "etat_caisse": None if etat is None else {k: etat[k] for k in ("mode", "minutes_en_plus", "reprise", "temps_preparation")},
        "capacites": capacites_rendues(capacites_de(nom)),
    }


async def poser_la_rupture(
    connexion: asyncpg.Connection, organization_id: int, etablissement_id: int, code_caisse: str, disponible: bool, fin: datetime | None,
    *, nom_base: str | None = None, transport: Any = None
) -> tuple[Any, bool]:
    """Pose (ou lève) la rupture dans le classeur, émet ``rupture.changee``, puis la pousse à la caisse si la prise sait la poser.
    Rend ``(Resultat du classeur, poussee_a_la_caisse)``. Un échec de la caisse laisse la rupture posée chez nous."""
    resultat = await restauration.poser_rupture(connexion, etablissement_id, code_caisse, disponible, fin, "portail")
    if resultat.statut != "OK":
        return resultat, False
    donnees: dict[str, Any] = {"code_caisse": code_caisse, "disponible": disponible}
    if fin is not None and not disponible:
        donnees["fin"] = fin
    await flux.emettre(organization_id, etablissement_id, "rupture.changee", donnees)
    if await liaison_db.liaison(connexion, etablissement_id) is None:
        return resultat, False  # pas de caisse : le classeur est maître, il n'y a rien à pousser
    prise = await prise_de_l_etablissement(ContexteDePrise(connexion, organization_id, etablissement_id, nom_base, transport))
    if not prise.capacites.ruptures_posees_par_nous:
        return resultat, False
    try:
        await prise.poser_rupture(code_caisse, disponible, fin)
    except Exception as erreur:  # noqa: BLE001 -- R1 : la caisse qui ne répond pas se voit sur la liaison, la rupture reste posée chez nous
        code = code_d_erreur(erreur)
        logger.warning(f"[.mark] Stock-out not pushed to the till for establishment {etablissement_id}: {type(erreur).__name__}")
        if code != "jeton_refuse":  # un jeton refusé a déjà passé la liaison à « rompue » (la prise l'a dit)
            await dire_la_liaison(connexion, organization_id, etablissement_id, "erreur", code)
        return resultat, False
    return resultat, True
