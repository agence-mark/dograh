"""[.mark] Module Restauration, lots 5 et 6 : les réglages de l'établissement lus pour les outils de l'agent (couche d'accès, lecture seule).

Hors des 17 fonctions du contrat (lecture de ce que le comptoir et le temps réclament) : réglages par type de commande, moyens de paiement
acceptés, prise de l'établissement. Toute requête porte l'établissement dans le ``WHERE`` ; rien n'est jamais lu d'un autre.
"""

from __future__ import annotations

import asyncpg

from api.db.bases_clients.instantane import stable, vivant
from api.db.bases_clients.restauration_commun import maintenant

PRISE_PAR_DEFAUT = "portail"  # sans liaison : le classeur est maître, il n'y a rien à envoyer
MOYENS_PAR_DEFAUT = ("carte", "especes")


async def reglage_du_type(connexion: asyncpg.Connection, etablissement_id: int, type_: str) -> dict | None:
    """La ligne de réglage d'un type de commande (``emporter``, ``livraison``, ``sur_place``, ``reservation``), ou ``None``."""
    r = (await vivant(connexion, etablissement_id, await maintenant(connexion))).types.get(type_)  # lot 5 : l'état vivant (pause, délai)
    return dict(r) if r else None


async def types_de_commande_eteints(connexion: asyncpg.Connection, etablissement_id: int, possibles: tuple[str, ...]) -> set[str]:
    """Les types de commande que l'établissement a éteints (``ouvert`` faux sur sa ligne de réglage), parmi ``possibles`` : ce qu'il ne prend
    jamais (un restaurant sans salle). Un type sans ligne, ou en pause, n'en fait pas partie."""
    types = (await vivant(connexion, etablissement_id, await maintenant(connexion))).types
    return {t for t, r in types.items() if t in possibles and not r["ouvert"]}


async def reglages_de_paiement(connexion: asyncpg.Connection, etablissement_id: int) -> dict:
    """``{moyens_paiement, plafond_titre, titre_alcool_exclu, titre_sans_rendu, notes_libres}`` : ce que l'établissement accepte (carte et espèces tant que rien n'est réglé)."""
    r = await _ligne_de_reglage(connexion, etablissement_id)
    module = await reglages_du_module(connexion, etablissement_id)
    return {
        "moyens_paiement": list(r["moyens_paiement"]) if r else list(MOYENS_PAR_DEFAUT),
        "plafond_titre": r["plafond_titre_restaurant"] if r else None,
        "titre_alcool_exclu": module["titre_alcool_exclu"], "titre_sans_rendu": module["titre_sans_rendu"], "notes_libres": module["notes_libres"],
    }


async def prise_de_l_etablissement(connexion: asyncpg.Connection, etablissement_id: int) -> str:
    """Le nom de la prise attachée à l'établissement (la fiche de liaison), ``portail`` sans liaison."""
    async def lire() -> str | None:
        return await connexion.fetchval("SELECT prise FROM mark.resto_liaison WHERE site_id = $1", etablissement_id)

    return await stable(connexion, ("prise", etablissement_id), lire) or PRISE_PAR_DEFAUT


async def _ligne_de_reglage(connexion: asyncpg.Connection, etablissement_id: int) -> asyncpg.Record | None:
    """La ligne de réglage de l'établissement (paiement, module) : lue une fois par appel (lot 5), à chaque lecture hors d'un appel."""

    async def lire() -> asyncpg.Record | None:
        return await connexion.fetchrow("SELECT * FROM mark.resto_reglage WHERE site_id = $1", etablissement_id)

    return await stable(connexion, ("reglage", etablissement_id), lire)


SOURCES_REGLABLES = ("carte", "ruptures", "etat", "horaires")  # les objets que le comptoir lit chez la caisse et qu'un restaurant peut tenir ici
PAR_DEFAUT_DU_MODULE: dict = {
    "pause_caisse_pause_telephone": True, "sources": {}, "numero_mode": "aucun", "prefixe_mixte": "MIX",
    "notes_libres": True, "titre_alcool_exclu": True, "titre_sans_rendu": True,
    "moities_prix": "plus_chere",  # lot 10 (RET6) : la règle de prix des moitiés de l'établissement
    # Lot 15 (INF4, INF6, D22) : le texte d'allergie du restaurant, le halal de l'établissement, et le choix « renvoyer vers le restaurant » (éteint par défaut)
    "consigne_allergie": None, "halal_restaurant": False, "allergies_renvoyees_au_restaurant": False,
}


async def reglages_du_module(connexion: asyncpg.Connection, etablissement_id: int) -> dict:
    """Les réglages du module que le comptoir lit : pause du téléphone avec la caisse (T-05), sources par objet (F4), numéro court, titre-restaurant,
    notes libres. Sans ligne de réglage (ou une base pas encore montée en 030) : les valeurs par défaut, toutes celles de la migration."""
    r = await _ligne_de_reglage(connexion, etablissement_id)
    sortie = dict(PAR_DEFAUT_DU_MODULE)
    if r is not None:
        for cle in sortie:
            if cle in r.keys() and r[cle] is not None:  # noqa: SIM118 -- un Record asyncpg : ``in`` teste les valeurs, pas les colonnes
                sortie[cle] = r[cle]
    if isinstance(sortie["sources"], str):
        import json

        sortie["sources"] = json.loads(sortie["sources"])
    return sortie


async def source_tenue_ici(connexion: asyncpg.Connection, etablissement_id: int, objet: str) -> bool:
    """Vrai si l'établissement a choisi de tenir cet objet ici : le comptoir ne le lit plus chez la caisse (un objet absent suit la caisse)."""
    return (await reglages_du_module(connexion, etablissement_id))["sources"].get(objet) == "ici"
