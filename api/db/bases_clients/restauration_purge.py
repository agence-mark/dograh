"""[.mark] Module Restauration, lot 2 : la conservation (E-10, T-15, T-23) dans la base du client.

``purger(connexion, avant)`` : efface le DÉTAIL des commandes et des réservations plus anciennes que ``avant`` (30 jours,
décidé par l'appelant d'après la source d'heure) et garde un récapitulatif chiffré par jour et par mode, SANS aucune
donnée personnelle (T-23). Efface aussi les messages reçus, le journal des changements qui porte des données de clients
(commandes, clients, réservations) et les fiches de client qui ont dépassé la durée de conservation de leur établissement
(T-15, 12 mois par défaut, réglable). IDEMPOTENTE : une transaction, le récapitulatif s'additionne au moment même où le
détail disparaît ; rejouée, il ne reste rien à compter. Ne touche qu'aux tables du module de CETTE base.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

from api.db.bases_clients.restauration_commun import maintenant, poser_session

OBJETS_PERSONNELS = ("resto_commande", "resto_client", "resto_reservation")
SANS_VENTE = "('annulee', 'refusee', 'echec')"
MODULE = "restauration"


async def purger(connexion: asyncpg.Connection, avant: datetime) -> dict:
    """Le bilan : ``{commandes, reservations, messages, journal, clients, compteurs, recapitulatif}`` (lignes effacées ;
    ``recapitulatif`` : lignes de récapitulatif écrites ou complétées)."""
    if avant.tzinfo is None:
        raise ValueError("``avant`` doit être aware.")
    maintenant_ = await maintenant(connexion)
    async with connexion.transaction():
        await poser_session(connexion, "mark", "purge")
        await connexion.execute("SELECT set_config('mark.purge', 'on', true)")  # le journal ne copie pas ce que la purge efface
        # 1. Les commandes : on les compte par jour (jour de l'établissement) et par mode, puis le détail part.
        recap_commandes = await connexion.execute(
            f"""
            WITH vieilles AS (
                SELECT c.*, (c.cree_le AT TIME ZONE s.fuseau)::date AS jour
                FROM mark.resto_commande c JOIN mark.site s ON s.id = c.site_id
                WHERE c.cree_le < $1 FOR UPDATE OF c
            ), somme AS (
                SELECT site_id, jour, mode,
                       count(*)::int AS nb,
                       (count(*) FILTER (WHERE statut IN {SANS_VENTE}))::int AS annulees,
                       coalesce(sum(total) FILTER (WHERE statut NOT IN {SANS_VENTE}), 0)::int AS ca,
                       coalesce(sum(frais) FILTER (WHERE statut NOT IN {SANS_VENTE}), 0)::int AS frais,
                       coalesce(sum((SELECT coalesce(sum((r ->> 'montant')::int), 0) FROM jsonb_array_elements(remises) r))
                                FILTER (WHERE statut NOT IN {SANS_VENTE}), 0)::int AS remises
                FROM vieilles GROUP BY site_id, jour, mode
            )
            INSERT INTO mark.resto_recap_jour (site_id, jour, mode, nb_commandes, nb_annulees, chiffre_affaires, frais, remises)
            SELECT site_id, jour, mode, nb, annulees, ca, frais, remises FROM somme
            ON CONFLICT (site_id, jour, mode) DO UPDATE SET
                nb_commandes = mark.resto_recap_jour.nb_commandes + EXCLUDED.nb_commandes,
                nb_annulees = mark.resto_recap_jour.nb_annulees + EXCLUDED.nb_annulees,
                chiffre_affaires = mark.resto_recap_jour.chiffre_affaires + EXCLUDED.chiffre_affaires,
                frais = mark.resto_recap_jour.frais + EXCLUDED.frais,
                remises = mark.resto_recap_jour.remises + EXCLUDED.remises
            """,
            avant,
        )
        commandes = await connexion.fetchval("WITH d AS (DELETE FROM mark.resto_commande WHERE cree_le < $1 RETURNING 1) SELECT count(*) FROM d", avant)
        # 2. Les réservations passées : comptées en mode « reservation » (honorées = nb, annulées ou absentes = nb_annulees).
        await connexion.execute(
            """
            WITH vieilles AS (
                SELECT r.*, (r.debut AT TIME ZONE s.fuseau)::date AS jour
                FROM mark.resto_reservation r JOIN mark.site s ON s.id = r.site_id
                WHERE r.debut < $1 FOR UPDATE OF r
            ), somme AS (
                SELECT site_id, jour, count(*)::int AS nb,
                       (count(*) FILTER (WHERE statut IN ('annulee', 'absente')))::int AS annulees
                FROM vieilles GROUP BY site_id, jour
            )
            INSERT INTO mark.resto_recap_jour (site_id, jour, mode, nb_commandes, nb_annulees)
            SELECT site_id, jour, 'reservation', nb, annulees FROM somme
            ON CONFLICT (site_id, jour, mode) DO UPDATE SET
                nb_commandes = mark.resto_recap_jour.nb_commandes + EXCLUDED.nb_commandes,
                nb_annulees = mark.resto_recap_jour.nb_annulees + EXCLUDED.nb_annulees
            """,
            avant,
        )
        reservations = await connexion.fetchval("WITH d AS (DELETE FROM mark.resto_reservation WHERE debut < $1 RETURNING 1) SELECT count(*) FROM d", avant)
        # 3. Le reste du détail.
        messages = await connexion.fetchval("WITH d AS (DELETE FROM mark.resto_message_recu WHERE recu_le < $1 RETURNING 1) SELECT count(*) FROM d", avant)
        journal = await connexion.fetchval(
            "WITH d AS (DELETE FROM mark.resto_journal WHERE le < $1 AND objet = ANY($2::text[]) RETURNING 1) SELECT count(*) FROM d",
            avant, list(OBJETS_PERSONNELS),
        )
        # 4. Les fiches de client : la durée de CHAQUE établissement (12 mois par défaut), depuis la dernière commande.
        clients = await connexion.fetchval(
            """
            WITH d AS (
                DELETE FROM mark.resto_client c
                USING mark.site s
                WHERE s.id = c.site_id
                  AND coalesce(c.derniere_commande_le, c.cree_le)
                      + make_interval(months => coalesce((SELECT g.conservation_client_mois FROM mark.resto_reglage g WHERE g.site_id = c.site_id), 12))
                      < $1
                RETURNING 1
            ) SELECT count(*) FROM d
            """,
            maintenant_,
        )
        # 5. Les compteurs du numéro court des jours passés.
        compteurs = await connexion.fetchval(
            "WITH d AS (DELETE FROM mark.resto_compteur_jour k USING mark.site s WHERE s.id = k.site_id "
            "AND k.jour < (($1::timestamptz) AT TIME ZONE s.fuseau)::date RETURNING 1) SELECT count(*) FROM d",
            avant,
        )
    return {
        "commandes": commandes, "reservations": reservations, "messages": messages, "journal": journal,
        "clients": clients, "compteurs": compteurs, "recapitulatif": int(recap_commandes.split()[-1]),
    }


async def agents_du_module(connexion: asyncpg.Connection) -> list[int]:
    """Les agents (identifiants d'agent chez Dograh) sur lesquels le module est allumé, lus dans la base du client."""
    lignes = await connexion.fetch(
        "SELECT a.dograh_workflow_id FROM mark.module_agent ma JOIN mark.agent a ON a.id = ma.agent_id "
        "WHERE ma.module_code = $1 ORDER BY 1",
        MODULE,
    )
    return [r["dograh_workflow_id"] for r in lignes]
