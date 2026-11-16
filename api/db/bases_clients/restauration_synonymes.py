"""[.mark] Module Restauration, lot 4 : les synonymes d'un produit, proposés à l'import et actifs APRÈS RELECTURE (W31, T-14).

Vit dans la couche d'accès de la carte (seule à écrire les tables du classeur). Les synonymes sont une surcouche : l'import d'une
carte ne les écrase jamais (``importer_carte``) et ``proposer_les_synonymes`` non plus :

- un produit qui a déjà des synonymes (relus, ou déjà proposés) n'est PAS touché ;
- les propositions s'écrivent « à relire » : ``carte_du_restaurant`` ne les rend pas parmi les synonymes actifs, la recherche
  ne s'en sert pas, tant que personne ne les a relus ;
- ``marquer_relus`` les rend actifs (après relecture par .mark), telles quelles ou corrigées.

Hors des 17 fonctions du contrat (``restauration.py``) : un geste de .mark, jamais de l'agent.
"""

from __future__ import annotations

import asyncpg

from api.db.bases_clients.recherche_liste_moteur import nom_nettoye, proposer_synonymes
from api.db.bases_clients.restauration_carte import carte_du_restaurant
from api.db.bases_clients.restauration_commun import poser_session

MAX_SYNONYMES = 10
LONGUEUR_SYNONYME = 80


async def proposer_les_synonymes(connexion: asyncpg.Connection, etablissement_id: int, *, auteur: str = "import") -> dict:
    """Écrit, pour chaque produit SANS synonyme, ceux que son nom propose, « à relire ». Rend ``{proposes, ignores}``.
    Rejouable : un produit déjà proposé ou relu n'est jamais retouché."""
    carte = await carte_du_restaurant(connexion, etablissement_id)
    categories = [c["nom"] for c in carte["categories"]]
    # Les noms déjà portés par un produit (nettoyés) : jamais proposés comme synonyme d'un autre.
    autres = frozenset(nom_nettoye(p["nom"]) for p in carte["produits"])
    bilan = {"proposes": 0, "ignores": 0}
    a_ecrire: dict[str, list[str]] = {}
    for p in carte["produits"]:
        if p["synonymes"] or p["synonymes_a_relire"]:
            bilan["ignores"] += 1
            continue
        a_ecrire[p["id"]] = [s[:LONGUEUR_SYNONYME] for s in proposer_synonymes(p["nom"], categories, autres)][:MAX_SYNONYMES]
    # Un synonyme que deux produits proposent désignerait deux produits : il n'est donné à aucun.
    compte: dict[str, int] = {}
    for propositions in a_ecrire.values():
        for s in {nom_nettoye(x) for x in propositions}:
            compte[s] = compte.get(s, 0) + 1
    async with connexion.transaction():
        await poser_session(connexion, "mark", f"synonymes:{auteur}")
        for ref, propositions in a_ecrire.items():
            propositions = [x for x in propositions if compte[nom_nettoye(x)] == 1]
            if not propositions:
                bilan["ignores"] += 1
                continue
            await connexion.execute(
                "INSERT INTO mark.resto_surcouche (site_id, objet, ref, synonymes, synonymes_a_relire) VALUES ($1, 'produit', $2, $3, true) "
                "ON CONFLICT (site_id, objet, ref) DO UPDATE SET synonymes = EXCLUDED.synonymes, synonymes_a_relire = true "
                "WHERE cardinality(mark.resto_surcouche.synonymes) = 0",
                etablissement_id, ref, propositions,
            )
            bilan["proposes"] += 1
    return bilan


async def marquer_relus(
    connexion: asyncpg.Connection, etablissement_id: int, ref: str, synonymes: list[str] | None = None, *, auteur: str = "mark"
) -> bool:
    """La relecture d'un produit : ses synonymes proposés deviennent actifs (corrigés si ``synonymes`` est donné). ``False`` quand
    il n'y avait rien à relire (rien n'est changé)."""
    if synonymes is not None:
        synonymes = [s.strip()[:LONGUEUR_SYNONYME] for s in synonymes if s and s.strip()][:MAX_SYNONYMES]
    async with connexion.transaction():
        await poser_session(connexion, "mark", f"relecture:{auteur}")
        ligne = await connexion.fetchval(
            "UPDATE mark.resto_surcouche SET synonymes = coalesce($3::text[], synonymes), synonymes_a_relire = false "
            "WHERE site_id = $1 AND objet = 'produit' AND ref = $2 AND synonymes_a_relire RETURNING 1",
            etablissement_id, ref, synonymes,
        )
    return bool(ligne)
