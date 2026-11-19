"""[.mark] Chantier Partie 1, lot 12 : les briques prix et conditions (``services/commande/briques/prx*.py``).

Une classe par brique (``TestPRX1`` ... ``TestPRX9``), chacune avec sa règle, son aller-retour en caisse et son test de rendu de la fiche (D66) ; plus la migration 041, l'alcool du
format commun importé et la quantité maximale lue dans la donnée. Un test = un essai à la fois.
"""

from __future__ import annotations

import pytest

from api.db.bases_clients import restauration
from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import brique, descendre_jusqu_a, fait, la_brique_change_la_fiche
from api.tests.mark.test_base_client import base_essai  # noqa: F401


async def _ajouter(e, parole: str, **article):
    return await e.tour(parole, ajouter=[article])


# --------------------------------------------------------------------------- #
# L12-01 : la migration 041
# --------------------------------------------------------------------------- #

COLONNES_041 = [("resto_produit", c) for c in ("disponibilite", "modes", "alcool", "degre", "frais", "max_par_commande", "delai_minimal_heures", "personnes_min")] + [
    ("resto_categorie", "disponibilite"), ("resto_option", "disponibilite"), ("resto_option", "modes"), ("resto_option", "prix_par_mode")]


async def test_migration_041_montee_descente(base_prete):
    from api.db.bases_clients import connexion as schema

    async def presentes(c, colonnes) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col)) for t, col in colonnes]

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c, COLONNES_041))
        for _ in range(2):  # descente, remontée, deux fois (rejouable)
            await descendre_jusqu_a(c, 41)
            assert not any(await presentes(c, COLONNES_041)) and 41 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert await presentes(c, [("resto_formule", "modes")]) == [True]  # le mode de la formule appartient à la 040
            assert 41 in await schema.appliquer_migrations(c)
            assert all(await presentes(c, COLONNES_041))
    finally:
        await c.close()


async def test_les_conditions_de_vente_sont_importees_et_chargees(essai_de):
    """Le format commun porte les conditions ; l'import les écrit, la carte chargée les rend (D61 point 1), ``None`` = non dit."""
    e = await essai_de("briques/PRX1")
    carte = await restauration.carte_du_restaurant(e.monde.c, e.monde.a)
    salade = next(p for p in carte["produits"] if p["id"] == "P-SALADE")
    assert salade["disponibilite"]["jours"] == [1, 2, 3, 4, 5] and salade["modes"] is None and salade["max_par_commande"] is None
    assert next(c for c in carte["categories"] if c["id"] == "petitdej")["disponibilite"] == {"heures": [["07:00", "11:00"]]}
    truffe = next(o for g in carte["groupes"] for o in g["options"] if o["nom"] == "Truffe")
    assert truffe["disponibilite"] == {"jours": [6, 7]} and truffe["modes"] is None and truffe["prix_par_mode"] is None
