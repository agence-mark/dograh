"""[.mark] Clôture, lot B : les descentes des migrations clientes 022 et 023 (avec la 024 déjà écrite), jouées sur une COPIE (une base neuve par test).

| Test | Ce qu'il prouve |
|---|---|
| descente | de la 024 à la 022, dans l'ordre : chaque version part du registre, les colonnes, tables, vues, fonctions et déclencheurs de la migration disparaissent, ``recevoir_appel`` redevient celui de la 018 |
| rejouable | chaque descente se rejoue sans erreur (IF EXISTS) |
| montée | ``appliquer_migrations`` remonte de la 22 à la 24 et remet exactement l'état d'avant la descente |
| donnée | un appel reçu avant la descente reste lisible après (seules les colonnes propres à la 022 partent) |
"""

from __future__ import annotations

from pathlib import Path

from api.db.bases_clients import connexion as schema
from api.tests.mark.test_apres_appel import _envoi
from api.tests.mark.test_base_client import _serveur, base_essai, base_prete  # noqa: F401

DESCENTES = Path(schema.__file__).parent / "migrations" / "descentes"

DE_LA_022 = {
    "colonnes": [("appel", "page"), ("appel", "mode_site")],
    "tables": ["avis", "evenement_portail"],
    "vues": ["v_portail_avis"],
    "fonctions": ["noter_avis", "contact_du_visiteur", "demander_rappel_site", "emettre_evenement_portail", "demande_apres_avis"],
}
DE_LA_023 = {
    "colonnes": [("contact", "doublon_de"), ("contact", "doublon_raison"), ("contact", "mail_declare"), ("contact", "ne_pas_memoriser")],
    "tables": ["contact_fusion"],
}


async def _existe_colonne(c, table, colonne):
    return bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", table, colonne))


async def _existe_table(c, nom, vue=False):
    if vue:
        return bool(await c.fetchval("SELECT 1 FROM pg_views WHERE schemaname='mark' AND viewname=$1", nom))
    return bool(await c.fetchval("SELECT 1 FROM pg_tables WHERE schemaname='mark' AND tablename=$1", nom))


async def _existe_fonction(c, nom):
    return bool(await c.fetchval("SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='mark' AND p.proname=$1", nom))


async def _etat(c, groupe):
    return {
        "colonnes": [await _existe_colonne(c, t, col) for t, col in groupe.get("colonnes", [])],
        "tables": [await _existe_table(c, t) for t in groupe.get("tables", [])],
        "vues": [await _existe_table(c, v, vue=True) for v in groupe.get("vues", [])],
        "fonctions": [await _existe_fonction(c, f) for f in groupe.get("fonctions", [])],
    }


async def _versions(c):
    return [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version ORDER BY version")]


async def _jouer(c, nom):
    async with c.transaction():
        await c.execute((DESCENTES / nom).read_text(encoding="utf-8"))


async def test_la_descente_de_la_024_a_la_022_retire_chaque_migration_puis_la_montee_la_remet(base_prete):
    c = await schema.connecter_proprietaire(base_prete)  # le propriétaire seul descend (index, colonnes, vues lui appartiennent)
    try:
        assert (await _versions(c))[-3:] == [22, 23, 24]
        # un appel reçu AVANT la descente : il doit rester lisible
        await c.fetchval("SELECT mark.recevoir_appel($1::jsonb)", __import__("json").dumps(_envoi(1, numero="+33611111111", contact={"nom": "Dupont"})))
        avant = {"22": await _etat(c, DE_LA_022), "23": await _etat(c, DE_LA_023)}
        assert all(all(v) for etat in avant.values() for v in etat.values()), avant  # tout existe

        await _jouer(c, "024-descente.sql")
        assert (await _versions(c))[-1] == 23
        await _jouer(c, "023-descente.sql")
        assert (await _versions(c))[-1] == 22
        etat23 = await _etat(c, DE_LA_023)
        assert not any(any(v) for v in etat23.values()), etat23
        await _jouer(c, "022-descente.sql")
        assert (await _versions(c))[-1] == 21
        etat22 = await _etat(c, DE_LA_022)
        assert not any(any(v) for v in etat22.values()), etat22
        # recevoir_appel est celui de la 018 : il ne connaît plus ni page, ni mode_site, ni avis
        source = await c.fetchval("SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='mark' AND p.proname='recevoir_appel'")
        assert "mode_site" not in source and "noter_avis" not in source
        # la donnée d'avant reste lisible, et la base accepte un appel de plus
        assert await c.fetchval("SELECT count(*) FROM mark.appel") == 1
        await c.fetchval("SELECT mark.recevoir_appel($1::jsonb)", __import__("json").dumps(_envoi(2, numero="+33622222222", contact={"nom": "Martin"})))
        assert await c.fetchval("SELECT count(*) FROM mark.appel") == 2

        # chaque descente se rejoue sans erreur
        for nom in ("024-descente.sql", "023-descente.sql", "022-descente.sql"):
            await _jouer(c, nom)
        assert (await _versions(c))[-1] == 21

        # la montée remet exactement l'état d'avant
        assert await schema.appliquer_migrations(c) == [22, 23, 24]
        assert (await _versions(c))[-3:] == [22, 23, 24]
        assert {"22": await _etat(c, DE_LA_022), "23": await _etat(c, DE_LA_023)} == avant
        assert await c.fetchval("SELECT count(*) FROM mark.appel") == 2
    finally:
        await c.close()
