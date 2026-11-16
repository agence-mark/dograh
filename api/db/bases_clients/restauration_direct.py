"""[.mark] Module Restauration : les lectures du direct des appels (lot 21) et de la fenêtre Caisse / POS du Labo (lot 20).

Couche d'accès : les seules requêtes sur les tables ``resto_*`` de ces deux usages vivent ici (le test de contrat du classeur
refuse toute requête sur ces tables hors des fichiers ``restauration*.py``). Lecture seule.
"""

from __future__ import annotations

from typing import Any

import asyncpg

# Le motif de fin d'un appel, dans l'ordre où il se lit : une commande l'emporte sur une réservation.
_SIGNAUX_DE_FIN = (
    ("Commande", "SELECT EXISTS (SELECT 1 FROM mark.resto_commande WHERE site_id = $1 AND appel_id = $2)"),
    ("Réservation", "SELECT EXISTS (SELECT 1 FROM mark.resto_reservation WHERE site_id = $1 AND appel_id = $2)"),
)


async def motif_ecrit_par_l_appel(connexion: asyncpg.Connection, etablissement_id: int, appel_id: str) -> str | None:
    """« Commande » ou « Réservation » si cet appel en a écrit une dans cet établissement, sinon ``None``."""
    for motif, requete in _SIGNAUX_DE_FIN:
        if await connexion.fetchval(requete, etablissement_id, appel_id):
            return motif
    return None


async def module_actif(connexion: asyncpg.Connection, etablissement_id: int) -> bool:
    """Le module Restauration est-il allumé pour cet établissement (``resto_reglage.module_actif``) ?"""
    return bool(await connexion.fetchval("SELECT EXISTS (SELECT 1 FROM mark.resto_reglage WHERE site_id = $1 AND module_actif)", etablissement_id))


async def reservation_de_l_appel(connexion: asyncpg.Connection, etablissement_id: int, appel_id: str) -> dict[str, Any] | None:
    """La dernière réservation que cet appel a faite dans cet établissement : heure, durée, couverts, état, noms des tables.
    Jamais le prénom ni le numéro de l'appelant."""
    ligne = await connexion.fetchrow(
        "SELECT r.numero, r.debut, r.duree_minutes, r.couverts, r.statut, r.table_ids FROM mark.resto_reservation r "
        "WHERE r.site_id = $1 AND r.appel_id = $2 AND EXISTS (SELECT 1 FROM mark.site s WHERE s.id = r.site_id) ORDER BY r.cree_le DESC LIMIT 1",
        etablissement_id, appel_id,
    )
    if ligne is None:
        return None
    tables = [
        t["nom"]
        for t in await connexion.fetch(
            "SELECT nom FROM mark.resto_table WHERE site_id = $1 AND id = ANY($2::bigint[]) ORDER BY nom", etablissement_id, list(ligne["table_ids"])
        )
    ]
    return {
        "numero": str(ligne["numero"]), "debut": ligne["debut"].isoformat(), "duree_minutes": ligne["duree_minutes"],
        "couverts": ligne["couverts"], "statut": ligne["statut"], "tables": tables,
    }
