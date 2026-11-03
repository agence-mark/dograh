"""[.mark] Builder partie 2, G1b : une seule entrée vers « À améliorer » (clé d'API et Claude Code), la file « À juger » et les compteurs.

Vraie base de test, aucun appel à un fournisseur.
"""

from __future__ import annotations

from api.db import db_client
from api.services.boucle import ingestion
from api.services.builder import stock
from api.services.juge import a_ameliorer
from api.tests.mark.test_boucle_u8 import LIGNES, decor, un_appel, verdict_juge


def un_item(run, agent):
    return {"id": f"appel-{run.id}", "type": "appel", "workflow_id": agent.id, "run_id": run.id}


async def test_un_verdict_par_cle_et_par_claude_code_donnent_le_meme_probleme():
    org, user, _, agent = await decor("g1b-unique")
    par_cle, par_code = await un_appel(agent, user, org), await un_appel(agent, user, org)
    await ingestion.ingerer_un_appel_juge(par_cle, org, [verdict_juge("Suit le parcours")], LIGNES)  # le chemin de l'après-appel
    n = await a_ameliorer.signaler(org, un_item(par_code, agent), [verdict_juge("Suit le parcours")], LIGNES, "claude_code")  # juge_ecrire
    assert n == 1
    lignes, _ = await db_client.lister_les_ameliorations(org)
    assert len(lignes) == 1 and lignes[0]["nb_cas"] == 2 and {c["run_id"] for c in lignes[0]["cas"]} == {par_cle.id, par_code.id}


async def test_rejuger_remplace_le_jugement_et_ne_le_double_jamais():
    org, user, _, agent = await decor("g1b-rejuge")
    run = await un_appel(agent, user, org)
    item = un_item(run, agent)
    await a_ameliorer.signaler(org, item, [verdict_juge("Suit le parcours")], LIGNES, "claude_code")
    await a_ameliorer.signaler(org, item, [verdict_juge("Suit le parcours")], LIGNES, "claude_code")
    assert [p["nb_cas"] for p in (await db_client.lister_les_ameliorations(org))[0]] == [1]
    # rejugé avec un autre critère raté : l'ancien problème (sans autre cas, pas encore traité) disparaît
    await a_ameliorer.signaler(org, item, [verdict_juge("Reste poli")], LIGNES, "claude_code")
    assert [p["titre"] for p in (await db_client.lister_les_ameliorations(org))[0]] == ["Reste poli"]
    # rejugé réussi : plus rien
    assert await a_ameliorer.signaler(org, item, [verdict_juge("Reste poli", v="reussi")], LIGNES, "claude_code") == 0
    assert (await db_client.lister_les_ameliorations(org))[0] == []


async def test_rejuger_garde_un_probleme_deja_en_cours_et_les_cas_des_autres_appels():
    org, user, _, agent = await decor("g1b-garde")
    r1, r2 = await un_appel(agent, user, org), await un_appel(agent, user, org)
    for run in (r1, r2):
        await a_ameliorer.signaler(org, un_item(run, agent), [verdict_juge("Suit le parcours")], LIGNES, "cle_api")
    probleme = (await db_client.lister_les_ameliorations(org))[0][0]
    await db_client.modifier_une_amelioration(org, probleme["id"], etat="en_cours")
    await a_ameliorer.signaler(org, un_item(r1, agent), [verdict_juge("Suit le parcours", v="reussi")], LIGNES, "claude_code")
    apres = await db_client.lire_une_amelioration(org, probleme["id"])
    assert apres["nb_cas"] == 1 and [c["run_id"] for c in apres["cas"]] == [r2.id] and apres["etat"] == "en_cours"


async def test_un_test_juge_entre_par_son_nom_et_se_remplace():
    org, user, _, agent = await decor("g1b-test")
    item = {"id": f"test-{agent.id}-libre", "type": "test", "workflow_id": agent.id, "test": "libre"}
    assert await a_ameliorer.signaler(org, item, [verdict_juge("Ton naturel")], LIGNES, "claude_code") == 1
    assert await a_ameliorer.signaler(org, item, [verdict_juge("Ton naturel")], LIGNES, "claude_code") == 1
    lignes = (await db_client.lister_les_ameliorations(org))[0]
    assert len(lignes) == 1 and lignes[0]["nb_cas"] == 1 and lignes[0]["cas"][0]["test"] == "libre"


async def test_un_appel_d_une_autre_organisation_n_entre_pas():
    org, user, _, agent = await decor("g1b-cloison-a")
    autre, autre_user, _, autre_agent = await decor("g1b-cloison-b")
    run = await un_appel(autre_agent, autre_user, autre)
    assert await a_ameliorer.signaler(org, un_item(run, autre_agent), [verdict_juge("X")], LIGNES, "claude_code") == 0
    assert (await db_client.lister_les_ameliorations(org))[0] == [] and (await db_client.lister_les_ameliorations(autre))[0] == []


async def test_le_stock_provisoire_est_verse_une_fois_puis_supprime():
    org, user, _, agent = await decor("g1b-stock")
    run = await un_appel(agent, user, org)
    point = {"id": f"appel-{run.id}::Suit", "element": f"appel-{run.id}", "type": "appel", "workflow_id": agent.id, "run_id": run.id,
             "critere": "Suit le parcours", "verdict": "rate", "replique": 2, "preuve": "Je veux un rdv", "source": "claude_code"}
    await stock.ecrire(org, a_ameliorer.CLE_PROVISOIRE, {"points": [point]})
    assert await a_ameliorer.verser_le_stock_provisoire(org) == 1
    assert await stock.lire(org, a_ameliorer.CLE_PROVISOIRE) is None
    assert await a_ameliorer.verser_le_stock_provisoire(org) == 0
    lignes = (await db_client.lister_les_ameliorations(org))[0]
    assert len(lignes) == 1 and lignes[0]["nb_cas"] == 1 and lignes[0]["titre"] == "Suit le parcours"
    # lister() verse aussi, et rend les problèmes ouverts
    lus = await a_ameliorer.lister(org, agent.id)
    assert [p["critere"] for p in lus] == ["Suit le parcours"]
