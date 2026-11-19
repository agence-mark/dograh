"""[.mark] Chantier Partie 1, lot 8 (E29) : les signalements de carte, la couche d'accès.

Une règle que la carte exprime et que l'agent ne sait pas appliquer ne bloque jamais la commande : elle part en note de ligne, et ELLE EST SIGNALÉE ici pour que le
restaurateur la précise au portail. Un signalement par couple (établissement, produit, texte), rejouable sans effet double. Aucune donnée personnelle.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from api.db.bases_clients.restauration_commun import maintenant

LONGUEUR_MAX = 300
PAGE_MAX = 100


async def signaler_une_regle_inconnue(connexion: asyncpg.Connection, etablissement_id: int, produit_ref: str, texte: str) -> bool:
    """Écrit le signalement de CET établissement ; ``False`` : déjà signalé (rien n'est écrit deux fois) ou texte vide."""
    texte = " ".join((texte or "").split())[:LONGUEUR_MAX]
    if not texte or not str(produit_ref or "").strip():
        return False
    ecrit = await connexion.fetchval(
        "INSERT INTO mark.resto_signalement_carte (site_id, produit_ref, texte, cree_le) VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (site_id, produit_ref, texte) DO NOTHING RETURNING id",
        etablissement_id, str(produit_ref).strip(), texte, await maintenant(connexion),
    )
    return ecrit is not None


async def signalements_de_la_carte(connexion: asyncpg.Connection, etablissement_id: int, limite: int = 50, avant: int | None = None) -> dict[str, Any]:
    """Les signalements de CET établissement, du plus récent au plus ancien, par pages (``avant`` : l'identifiant de la dernière ligne vue)."""
    limite = max(1, min(int(limite), PAGE_MAX))
    lignes = await connexion.fetch(
        "SELECT id, produit_ref, texte, cree_le FROM mark.resto_signalement_carte WHERE site_id = $1 AND ($2::bigint IS NULL OR id < $2) ORDER BY id DESC LIMIT $3",
        etablissement_id, avant, limite + 1,
    )
    page = lignes[:limite]
    return {
        "signalements": [{"id": r["id"], "produit": r["produit_ref"], "texte": r["texte"], "cree_le": r["cree_le"]} for r in page],
        "suivant": page[-1]["id"] if len(lignes) > limite else None,
    }
