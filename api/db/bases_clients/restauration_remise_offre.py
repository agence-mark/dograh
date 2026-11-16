"""[.mark] Module Restauration, lot 26 (M38) : les offres de remise DITES par l'agent et leur ACCEPTATION.

Pour les colonnes « Dite » et « Acceptée » de l'écran Remises (migration 034, ``resto_remise_offre``).

- ``noter_une_offre_dite`` : l'agent vient de dire cette remise à l'appelant. Une offre n'est comptée qu'une fois par appel (quand l'appel est connu) :
  la redire dans le même appel ne change rien. Une remise qui n'est pas de cet établissement n'est pas notée.
- ``noter_l_acceptation`` : la commande enregistrée porte ces remises. Seules les offres DITES dans cet appel passent à « acceptée » (jamais plus
  d'acceptations que d'offres dites) ; une remise appliquée sans avoir été dite n'est pas comptée.
- ``compter_les_offres`` : pour l'écran, ``{remise_id: (dites, acceptees)}``.

Qui l'appelle : l'outil de remise (``services/commande/moteur.py``, au moment où il rend une offre à dire) et l'enregistrement de la commande
(``restauration_commande.py``). Ces deux endroits sont ceux du comptoir : le branchement est fait par la fenêtre principale, pas ici.
L'heure vient de la source d'heure de l'organisation (D6).
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

import asyncpg

from api.db.bases_clients.restauration_commun import maintenant


async def noter_une_offre_dite(connexion: asyncpg.Connection, etablissement_id: int, remise_id: int, appel_id: str | None = None) -> bool:
    """Note que l'agent a dit cette offre. Rend ``True`` si une ligne est née, ``False`` si la remise n'est pas de cet établissement ou si
    l'appel l'avait déjà dite (rejouable sans effet double)."""
    quand = await maintenant(connexion)
    if appel_id is not None and not appel_id.strip():
        appel_id = None
    ligne = await connexion.fetchval(
        "INSERT INTO mark.resto_remise_offre (site_id, remise_id, appel_id, dite_le) "
        "SELECT r.site_id, r.id, $3, $4 FROM mark.resto_remise r WHERE r.id = $2 AND r.site_id = $1 "
        "ON CONFLICT (remise_id, appel_id) WHERE appel_id IS NOT NULL DO NOTHING RETURNING id",
        etablissement_id, remise_id, appel_id, quand,
    )
    return ligne is not None


async def noter_une_offre_dite_par_ref(connexion: asyncpg.Connection, etablissement_id: int, ref: str, appel_id: str | None = None) -> bool:
    """Comme ``noter_une_offre_dite``, la remise étant désignée par sa référence (celle que le moteur de commande manipule : ``ref`` ou, à défaut, son numéro)."""
    remise_id = await connexion.fetchval(
        "SELECT id FROM mark.resto_remise WHERE site_id = $1 AND (ref = $2 OR id::text = $2) ORDER BY id LIMIT 1", etablissement_id, str(ref)
    )
    if remise_id is None:
        return False
    return await noter_une_offre_dite(connexion, etablissement_id, remise_id, appel_id)


async def noter_l_acceptation(
    connexion: asyncpg.Connection, etablissement_id: int, appel_id: str | None, remise_ids: Iterable[int], commande_numero: UUID | str | None = None
) -> int:
    """Passe à « acceptée » les offres dites dans cet appel dont la remise est sur la commande enregistrée. Rend le nombre d'offres acceptées.
    Sans appel connu, rien n'est noté (on ne sait pas laquelle des offres dites l'appelant a prise)."""
    ids = sorted({int(i) for i in remise_ids})
    if appel_id is None or not appel_id.strip() or not ids:
        return 0
    quand = await maintenant(connexion)
    numero = UUID(str(commande_numero)) if commande_numero is not None else None
    lignes = await connexion.fetch(
        "UPDATE mark.resto_remise_offre SET acceptee_le = $4, commande_numero = $5 "
        "WHERE site_id = $1 AND appel_id = $2 AND remise_id = ANY($3::bigint[]) AND acceptee_le IS NULL AND dite_le <= $4 RETURNING id",
        etablissement_id, appel_id, ids, quand, numero,
    )
    return len(lignes)


async def compter_les_offres(connexion: asyncpg.Connection, etablissement_id: int) -> dict[int, tuple[int, int]]:
    """``{remise_id: (dites, acceptees)}`` de l'établissement : ce que montrent les colonnes « Dite » et « Acceptée »."""
    lignes = await connexion.fetch(
        "SELECT remise_id, count(*)::int AS dites, count(acceptee_le)::int AS acceptees FROM mark.resto_remise_offre WHERE site_id = $1 GROUP BY remise_id",
        etablissement_id,
    )
    return {r["remise_id"]: (r["dites"], r["acceptees"]) for r in lignes}
