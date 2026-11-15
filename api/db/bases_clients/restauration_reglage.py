"""[.mark] Module Restauration, lots 5 et 6 : les réglages de l'établissement lus pour les outils de l'agent (couche d'accès, lecture seule).

Hors des 17 fonctions du contrat (lecture de ce que le comptoir et le temps réclament) : réglages par type de commande, moyens de paiement
acceptés, prise de l'établissement. Toute requête porte l'établissement dans le ``WHERE`` ; rien n'est jamais lu d'un autre.
"""

from __future__ import annotations

import asyncpg

PRISE_PAR_DEFAUT = "portail"  # sans liaison : le classeur est maître, il n'y a rien à envoyer
MOYENS_PAR_DEFAUT = ("carte", "especes")


async def reglage_du_type(connexion: asyncpg.Connection, etablissement_id: int, type_: str) -> dict | None:
    """La ligne de réglage d'un type de commande (``emporter``, ``livraison``, ``sur_place``, ``reservation``), ou ``None``."""
    r = await connexion.fetchrow("SELECT * FROM mark.resto_reglage_type WHERE site_id = $1 AND type = $2", etablissement_id, type_)
    return dict(r) if r else None


async def reglages_de_paiement(connexion: asyncpg.Connection, etablissement_id: int) -> dict:
    """``{moyens_paiement, plafond_titre}`` : ce que l'établissement accepte (carte et espèces tant que rien n'est réglé)."""
    r = await connexion.fetchrow(
        "SELECT moyens_paiement, plafond_titre_restaurant FROM mark.resto_reglage WHERE site_id = $1", etablissement_id
    )
    return {
        "moyens_paiement": list(r["moyens_paiement"]) if r else list(MOYENS_PAR_DEFAUT),
        "plafond_titre": r["plafond_titre_restaurant"] if r else None,
    }


async def prise_de_l_etablissement(connexion: asyncpg.Connection, etablissement_id: int) -> str:
    """Le nom de la prise attachée à l'établissement (la fiche de liaison), ``portail`` sans liaison."""
    nom = await connexion.fetchval("SELECT prise FROM mark.resto_liaison WHERE site_id = $1", etablissement_id)
    return nom or PRISE_PAR_DEFAUT
