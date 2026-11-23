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


# --------------------------------------------------------------------------- A3 : l'allergie n'est jamais notée « donnée » sans avoir été dite


async def _gateau_et_allergie(essai_de):
    from api.tests.mark.partie_1.aides_briques import brique

    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau aux noix", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "noix"  # le greffier la note
    return e


async def test_a3_fiche_vide_qui_porte_des_faits_d_allergie_fait_repasser_le_modele(essai_de):
    """Phrase libre retenue, puis fiche vide « C'est bien noté pour votre allergie » : les faits (le lait, les noix) n'ont pas été dits ; le modèle repasse."""
    from api.services.actions_communes import parole as PAROLE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await _gateau_et_allergie(essai_de)
    e.dit("au fait, je suis allergique aux noix")
    etat = PAROLE.etat_du_tour(e.fiche_de_l_appel)
    etat.rattrapage_a_joue = True  # la phrase écrite sans outil a déjà été retenue dans ce tour
    PAROLE.garder(e.fiche_de_l_appel, etat)
    r = await e.fiche()
    assert r.get(PAROLE.CLE_FAITS_A_DIRE) and r["faits"]["allergie"], r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est bien noté pour votre allergie."})
    assert d.mode == PAROLE.SECOND_PASSAGE and d.motif == PAROLE.FAITS_A_DIRE, d


async def test_a3_des_faits_non_dits_ne_sont_pas_notes_donnes(essai_de):
    """Quand le code dit sa propre phrase à la place du modèle (le retour ne lui est pas rendu), les faits ne sont pas dits : l'allergie reste « à donner » et revient à la fiche suivante."""
    from api.services.actions_communes import parole as PAROLE
    from api.services.commande import moteur
    from api.services.commande.porte import CLE_TEXTES_DU_CODE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await _gateau_et_allergie(essai_de)
    r = await e.tour("une salade et un gâteau", note_generale="allergique aux noix")
    assert r.get(PAROLE.CLE_FAITS_A_DIRE) and moteur.allergie_a_donner(e.p) is None, r  # donnés au retour : notés
    e.fiche_de_l_appel[CLE_TEXTES_DU_CODE] = {"avant": "Je vous relis : une salade. C'est bon ?"}  # le code dit sa phrase mot pour mot
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "x"})
    assert d.mode == PAROLE.A_DIRE_SEUL, d
    assert moteur.allergie_a_donner(e.p) == "noix", e.p.get("allergie_donnee")  # pas dits : rouverts


# --------------------------------------------------------------------------- A4 : une parenthèse qui porte un fait est dite


async def test_a4_une_parenthese_qui_porte_une_allergie_est_dite():
    from api.services.pipecat.appels_de_fonction_voix import PhraseQuiNEstQuUnAppel, retirer_appels_de_fonction

    for dit in ("(Attention : ce plat contient des arachides.) Autre chose ?", "Votre commande : (sans arachide) une salade thaï.",
                "(Allergie au lait) La margherita en contient.", "(Sans gluten) Une pizza ?"):
        assert await retirer_appels_de_fonction(dit) == dit, dit
    assert await PhraseQuiNEstQuUnAppel().filter("(Attention : ce plat contient des arachides.)") == "(Attention : ce plat contient des arachides.)"
    # la mise en scène reste tue : une liste fermée de formes
    assert await retirer_appels_de_fonction("(En attente) Très bien.") == "Très bien."
    assert await retirer_appels_de_fonction("Très bien. (Pause) Autre chose ?") == "Très bien. Autre chose ?"
    assert await retirer_appels_de_fonction("(Silence.) Bonjour.") == "Bonjour."
    assert await PhraseQuiNEstQuUnAppel().filter("(En attente de la réponse de l'appelant)") == ""
