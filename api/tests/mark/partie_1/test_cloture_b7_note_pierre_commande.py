"""[.mark] Clôture de la Partie 1, note d'audit de Pierre du 23/11 (agent « commande ») : un test de règle par point, vu rouge avant le correctif.

* A2 : le remplacement d'une commande enregistrée se fait en tout ou rien ; un changement que l'enregistrement refuserait (plafond des titres,
  rupture relue en base, fermeture) est constaté AVANT d'annuler l'ancienne, qui reste la commande de l'appel.
"""

from __future__ import annotations

from datetime import timedelta

from api.db.bases_clients.restauration_commun import maintenant
from api.services.commande import moteur

from .test_l04_cuisine import _a_emporter, _faits, _jusqu_a_l_enregistrement, _premier_article, _refuser_la_proposition


async def _enregistree_en_titres(e):
    await _a_emporter(e)
    await _premier_article(e)
    await _refuser_la_proposition(e)
    await _jusqu_a_l_enregistrement(e, moyen="titre_restaurant")
    return moteur.commande_de_l_appel(e.p)


async def test_a2_changement_refuse_par_le_plafond_garde_la_commande_enregistree(essai_de):
    e = await essai_de()
    avant = await _enregistree_en_titres(e)
    assert avant is not None
    await e.monde.c.execute(
        "INSERT INTO mark.resto_reglage (site_id, plafond_titre_restaurant) VALUES ($1, $2) ON CONFLICT (site_id) DO UPDATE SET plafond_titre_restaurant = $2",
        e.monde.a, avant["total"],
    )
    ligne = e.p["lignes"][0]["n"]
    r = await e.tour("finalement deux margheritas", changer_quantite=[{"ligne": ligne, "quantite": 2}])
    reste = moteur.commande_de_l_appel(e.p)
    assert reste is not None and reste["numero"] == avant["numero"], (reste, avant, r)  # la commande de l'appel est toujours la première
    assert e.p["lignes"][0]["quantite"] == 1, e.p["lignes"]  # le panier redevient celui d'avant
    assert await e.monde.c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero::text = $1", avant["numero"]) != "annulee"
    assert "plafond" in _faits(r).casefold(), r  # et la raison est dite


async def test_a2_changement_refuse_par_une_rupture_garde_la_commande_enregistree(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    await _refuser_la_proposition(e)
    await _jusqu_a_l_enregistrement(e)
    avant = moteur.commande_de_l_appel(e.p)
    ligne = e.p["lignes"][0]
    code = await e.monde.c.fetchval("SELECT code_caisse FROM mark.resto_commande_ligne WHERE numero::text = $1 LIMIT 1", avant["numero"])
    # posée directement en base, sans passer par le cache de la carte : le chiffrage de l'appel ne la voit pas, l'enregistrement la relit (lot 5)
    await e.monde.c.execute(
        "INSERT INTO mark.resto_rupture (site_id, code_caisse, disponible, debut) VALUES ($1, $2, false, $3)", e.monde.a, code, (await maintenant(e.monde.c)) - timedelta(hours=1)
    )
    await e.tour("finalement deux margheritas", changer_quantite=[{"ligne": ligne["n"], "quantite": 2}])
    reste = moteur.commande_de_l_appel(e.p)
    assert reste is not None and reste["numero"] == avant["numero"], e.retours[-1]
    assert await e.monde.c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero::text = $1", avant["numero"]) != "annulee"
