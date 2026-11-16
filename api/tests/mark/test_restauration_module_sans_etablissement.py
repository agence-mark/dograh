"""[.mark] Module Restauration, lot 26 (M50) : l'état « module allumé » vit au niveau de la base (migration 035), pas dans les lignes d'établissement.

| Test | Ce qu'il prouve |
|---|---|
| sans établissement | « Ajouter un module » sur une base sans aucun établissement : l'état est retenu (allumé) et relu allumé |
| établissement créé ensuite | un établissement créé après l'allumage reçoit sa ligne de réglage allumée d'office ; module éteint, aucune ligne n'est créée |
| retirer | retirer éteint l'état et les lignes, sans effacer de donnée ; remettre rallume |
| base d'avant | une base sans ligne ``resto_module`` mais avec une ligne de réglage allumée reste lue allumée |
"""

from __future__ import annotations

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.restauration_ecran import module_allume, poser_le_module
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401


async def _site(c, cle):
    await c.execute("INSERT INTO mark.entreprise (raison_sociale) SELECT 'E' WHERE NOT EXISTS (SELECT 1 FROM mark.entreprise)")
    return await c.fetchval(
        "INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise LIMIT 1 RETURNING id", cle
    )


async def test_ajouter_le_module_sans_aucun_etablissement_est_retenu(base_prete):
    c = await schema.connecter(base_prete)
    try:
        assert await c.fetchval("SELECT count(*) FROM mark.site") == 0
        assert await module_allume(c) is False
        assert await poser_le_module(c, True, "test") is True  # le serveur rend l'état relu, pas celui demandé
        assert await module_allume(c) is True
    finally:
        await c.close()


async def test_un_etablissement_cree_apres_l_allumage_recoit_sa_ligne_allumee(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await poser_le_module(c, True, "test")
        a = await _site(c, "a")
        assert await c.fetchval("SELECT module_actif FROM mark.resto_reglage WHERE site_id = $1", a) is True
        # module éteint : un nouvel établissement ne reçoit rien
        await poser_le_module(c, False, "test")
        b = await _site(c, "b")
        assert await c.fetchval("SELECT count(*) FROM mark.resto_reglage WHERE site_id = $1", b) == 0
        assert await c.fetchval("SELECT module_actif FROM mark.resto_reglage WHERE site_id = $1", a) is False
        assert await module_allume(c) is False
        # on le remet : tous les établissements existants sont allumés
        assert await poser_le_module(c, True, "test") is True
        assert [r["module_actif"] for r in await c.fetch("SELECT module_actif FROM mark.resto_reglage")] == [True, True]
    finally:
        await c.close()


async def test_une_base_d_avant_la_035_garde_son_etat_par_ses_lignes(base_prete):
    c = await schema.connecter(base_prete)
    try:
        a = await _site(c, "a")
        await c.execute("INSERT INTO mark.resto_reglage (site_id) VALUES ($1)", a)
        await c.execute("DELETE FROM mark.resto_module")
        assert await module_allume(c) is True
    finally:
        await c.close()
