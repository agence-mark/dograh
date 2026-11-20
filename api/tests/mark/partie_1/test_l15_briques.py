"""[.mark] Chantier Partie 1, lot 15 : les briques allergènes et régimes (``services/commande/briques/inf*.py``) et la décision D22.

Les allergènes d'un produit ou d'une option sont PROPOSÉS depuis les ingrédients par la table officielle (annexe II du règlement (UE) n° 1169/2011), VALIDÉS par une
personne, et l'agent ne lit que les validés. Une classe par brique (``TestINF1`` à ``TestINF7``) avec sa règle, son test de rendu de la fiche (D66) et son aller-retour en caisse.
Un test = un essai à la fois.
"""

from __future__ import annotations

from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a
from api.tests.mark.test_base_client import base_essai  # noqa: F401


# --------------------------------------------------------------------------- #
# L15-01 : la migration 046 (la fiche disait 044, déjà prise par le code de remise)
# --------------------------------------------------------------------------- #

COLONNES = (
    ("resto_option", "allergenes"), ("resto_option", "allergenes_etat"), ("resto_option", "allergenes_source"),
    ("resto_produit", "allergenes_etat"), ("resto_produit", "allergenes_source"), ("resto_produit", "regimes"), ("resto_produit", "epice"), ("resto_produit", "nutrition"),
    ("resto_reglage", "consigne_allergie"), ("resto_reglage", "halal_restaurant"), ("resto_reglage", "allergies_renvoyees_au_restaurant"),
)


async def test_migration_046_montee_descente(base_prete):
    """Montée, descente, remontée : les colonnes du lot 15 apparaissent et disparaissent ; l'établissement qui renvoie les allergies vers le restaurant est éteint par défaut."""
    from api.db.bases_clients import connexion as schema

    async def presentes(c) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col)) for t, col in COLONNES]

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c))
        assert await c.fetchval("SELECT column_default FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_reglage' AND column_name='allergies_renvoyees_au_restaurant'") == "false"
        for _ in range(2):
            await descendre_jusqu_a(c, 46)
            assert not any(await presentes(c)) and 46 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 46 in await schema.appliquer_migrations(c)
            assert all(await presentes(c))
    finally:
        await c.close()


# --------------------------------------------------------------------------- #
# L15-02 : la table officielle INCO
# --------------------------------------------------------------------------- #


def test_table_inco_quatorze_codes():
    """La table dit les quatorze codes de ``LES_QUATORZE`` et seulement eux, chacun lié à son point de l'annexe II (1 à 14), et cite l'adresse lue."""
    from api.services.restauration.allergenes_suggeres import table_inco
    from api.services.restauration.signalements import LES_QUATORZE

    t = table_inco()
    assert set(t["allergenes"]) == set(LES_QUATORZE) and len(t["allergenes"]) == 14
    assert sorted(v["annexe"] for v in t["allergenes"].values()) == list(range(1, 15))
    assert t["adresse"].startswith("https://eur-lex.europa.eu/") and "1169/2011" in t["source"] and t["lu_le"]
    assert all(v["ingredients"] for v in t["allergenes"].values())
