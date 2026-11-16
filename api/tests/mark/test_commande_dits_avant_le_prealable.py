"""[.mark] SA-33, défaut 4 (appel 2559) : un article dit avant que la commande ait ses préalables (le mode, la zone) n'est jamais perdu.

Constat : à l'entrée du spécialiste, le modèle appelle ``ajouter`` avec « une Regina » avant ``choisir_mode`` ; ``ajouter`` rendait
``INCOMPLETE`` (mode) et ``articles: 0`` : la Regina était perdue, il fallait la redire. Mécanisme de la commande sur catalogue : ce qui est dit
avant un préalable est GARDÉ en attente dans le panier de l'appel, et pris dès que le préalable est posé, sans qu'on le redise.

| Test | Ce qu'il prouve |
|---|---|
| avant le mode | ``ajouter`` rend la question du mode (inchangée) ; l'article est gardé ; ``choisir_mode`` le prend ; plus rien n'est demandé deux fois |
| question en attente | gardé, l'article qui demande un choix pose sa question dès le mode posé |
| avant la zone | gardé pendant la question de la zone, pris quand l'adresse pose la zone |
| à la fin | ``finaliser`` après le préalable ne parle jamais d'un panier vide quand un article était gardé |
| redit | l'article gardé puis redit n'est pas pris deux fois |
| vider | vider la commande oublie aussi ce qui était gardé |
"""

from __future__ import annotations

from api.services.commande import moteur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_finaliser import Appel
from api.tests.mark.test_restauration_commande_lot6 import _zones


def _noms(a) -> list[tuple[str, int]]:
    return [(l["nom"], l["quantite"]) for l in a.p["lignes"]]


async def test_l_article_dit_avant_le_mode_est_pris_des_que_le_mode_est_pose(commerce):
    a = Appel(commerce, vente_en_plus=False)
    r = await moteur.ajouter(a.source, a.p, a.regles, articles="une regina normale")
    assert (r.statut, r.manque) == ("INCOMPLETE", "mode"), r  # la question du préalable, inchangée
    assert r.suggestion == (await moteur.finaliser(a.source, a.p, a.regles, a.appelant)).suggestion
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    assert r.statut == "OK" and r.manque != "articles", r  # jamais « Qu'est-ce que je vous mets ? » : la Regina est là
    assert _noms(a) == [("Regina Normale", 1)]
    assert r.faits.get("ajoutes") == ["Regina Normale"], r


async def test_l_article_garde_pose_sa_question_au_mode(commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.ajouter(a.source, a.p, a.regles, articles="une regina")
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    assert (r.statut, r.manque) == ("CHOIX_OBLIGATOIRE", "taille"), r
    r = await moteur.ajouter(a.source, a.p, a.regles, choix="normale")
    assert r.statut == "OK" and _noms(a) == [("Regina Normale", 1)], r


async def test_l_article_dit_avant_la_zone_est_pris_quand_la_zone_est_posee(commerce):
    await _zones(commerce)
    a = Appel(commerce, vente_en_plus=False)
    await moteur.ajouter(a.source, a.p, a.regles, articles="deux regina normale")
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    assert r.manque == "zone" and a.p["lignes"] == [], r  # la zone d'abord (ordre imposé) : toujours gardé
    r = await moteur.ajouter(a.source, a.p, a.regles, articles="un coca")
    assert r.manque == "zone", r  # gardé aussi
    r = await moteur.verifier_adresse(a.source, a.p, a.regles, "12 rue de la République à Senlis")
    assert r.statut == "RETENU", r
    assert sorted(_noms(a)) == [("Coca-Cola", 1), ("Regina Normale", 2)]


async def test_finaliser_apres_le_mode_ne_dit_jamais_un_panier_vide(commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.ajouter(a.source, a.p, a.regles, articles="une regina normale")
    a.p["mode"] = "emporter"  # le mode posé par un autre chemin : le filet de ``finaliser`` prend ce qui était gardé
    r = await moteur.finaliser(a.source, a.p, a.regles, a.appelant)
    assert r.manque != "articles" and _noms(a) == [("Regina Normale", 1)], r


async def test_l_article_garde_puis_redit_n_est_pas_pris_deux_fois(commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.ajouter(a.source, a.p, a.regles, articles="une regina normale")
    await moteur.ajouter(a.source, a.p, a.regles, articles="une regina normale")
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    assert _noms(a) == [("Regina Normale", 1)]


async def test_vider_la_commande_oublie_aussi_ce_qui_etait_garde(commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.ajouter(a.source, a.p, a.regles, articles="une regina normale")
    await moteur.vider_commande(a.source, a.p, a.regles)
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    assert a.p["lignes"] == [] and r.manque == "articles", r
