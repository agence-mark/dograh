"""[.mark] Module Restauration, lot 1 : les tables du classeur (migrations 025 à 030), leurs droits, leurs descentes.

| Test | Ce qu'il prouve |
|---|---|
| montée, descente, remontée | chaque migration 025 à 030 monte, se descend (dans l'ordre inverse), puis remonte : même état, rejouable |
Les droits (RLS par établissement), le journal et la version de la carte : ``test_restauration_classeur_droits.py``.
"""

from __future__ import annotations

from pathlib import Path


from api.db.bases_clients import connexion as schema
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401

DESCENTES = Path(schema.__file__).parent / "migrations" / "descentes"

# Les versions au-dessus de la 036 (lots de la partie 1 : 037 et suivantes) : lues dans le dossier, jamais écrites en dur (D49, nettoyeur).
HAUTES = sorted(int(f.name[:3]) for f in DESCENTES.parent.glob("[0-9][0-9][0-9]-*.sql") if int(f.name[:3]) > 36)

TABLES = {
    25: ["resto_categorie", "resto_produit", "resto_declinaison", "resto_groupe_choix", "resto_option", "resto_formule", "resto_surcouche"],
    26: ["resto_rupture", "resto_etat_caisse", "resto_reglage_type", "resto_zone", "resto_commande", "resto_commande_ligne",
         "resto_message_recu", "resto_liaison", "resto_compteur_jour"],
    27: ["resto_client", "resto_remise", "resto_envoi", "resto_reglage"],
    28: ["resto_salle", "resto_table", "resto_service", "resto_duree_groupe", "resto_regle_reservation", "resto_reservation",
         "resto_journal", "resto_recap_jour", "resto_version_carte"],
    29: ["resto_liaison_acces", "resto_imprimante", "resto_ticket"],
    30: ["resto_temps_recurrent"],
    31: [],  # une contrainte seulement : la liste fermée des douze mécanismes de remise (lot 20)
    32: [],  # une contrainte seulement : « carte à la livraison » dans les moyens de paiement (lot 26, M19)
    33: ["resto_plan_soir", "resto_recap_jour_taux"],
    34: ["resto_remise_offre"],  # offres de remise dites et acceptées (M38)
    36: [],  # numéro de carte : une colonne, aucune table (SA-48)
    35: ["resto_module"],  # état « module allumé » au niveau de la base (M50)
    37: ["resto_signalement_carte"],  # lot 1 (partie 1) : les signalements de la carte ; 038 à 041 : des colonnes seulement, aucune table
}
TOUTES = [t for v in sorted(TABLES) for t in TABLES[v]]


async def _tables(c):
    return sorted(r["tablename"] for r in await c.fetch("SELECT tablename FROM pg_tables WHERE schemaname='mark' AND tablename LIKE 'resto\\_%'"))


async def _versions(c):
    return [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version ORDER BY version")]


async def _jouer(c, nom):
    async with c.transaction():
        await c.execute((DESCENTES / nom).read_text(encoding="utf-8"))


async def test_chaque_migration_monte_se_descend_et_remonte(base_prete):
    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert (await _versions(c))[-(12 + len(HAUTES)):] == [25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, *HAUTES]
        avant = await _tables(c)
        assert avant == sorted(TOUTES)
        fonctions = await c.fetchval("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='mark' AND p.proname LIKE 'resto\\_%'")
        assert fonctions > 0
        for _ in range(2):  # descente puis remontée, deux fois (rejouable)
            for v in (*reversed(HAUTES), 36, 35, 34, 33, 32, 31, 30, 29, 28, 27, 26, 25):
                await _jouer(c, f"0{v}-descente.sql")
                assert (await _versions(c))[-1] == v - 1
                restantes = await _tables(c)
                assert not any(t in restantes for t in TABLES.get(v, ())), (v, restantes)
            assert await _tables(c) == []
            assert await c.fetchval("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='mark' AND p.proname LIKE 'resto\\_%'") == 0
            # chaque descente se rejoue sans erreur
            for v in (*reversed(HAUTES), 36, 35, 34, 33, 32, 31, 30, 29, 28, 27, 26, 25):
                await _jouer(c, f"0{v}-descente.sql")
            assert await schema.appliquer_migrations(c) == [25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, *HAUTES]
            assert await _tables(c) == avant
            assert await c.fetchval("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='mark' AND p.proname LIKE 'resto\\_%'") == fonctions
    finally:
        await c.close()
