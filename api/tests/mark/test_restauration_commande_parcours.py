"""[.mark] Module Restauration, lot 5, étape 6 : le parcours de bout en bout, par les outils de l'agent, jusqu'à la prise de test.

Le modèle ne fait que des gestes de la conversation ; l'envoi à la prise part de l'ENREGISTREMENT, en tâche de fond, par le code. Vraie base,
vraie liaison de l'établissement à la prise ``test`` (tests seulement), vrai gestionnaire d'outil, vrai flux.

| Test | Ce qu'il prouve |
|---|---|
| Regina + Coca | l'appel complet : mode, deux articles dont une taille demandée, relecture, « oui », commande enregistrée, envoyée à la prise, acceptée |
| le modèle n'envoie jamais | aucun outil ne parle à la caisse ; l'envoi n'a lieu qu'à l'enregistrement et une seule fois |
| incomplet refusé | pas de prénom, pas de règlement, pas de taille : rien n'est enregistré, le manque est dit |
| doublon impossible | deux « oui » en même temps : une seule commande, une seule réception par la prise |
| changement de mode | les articles sont gardés ; en livraison la zone est demandée et le minimum de la zone tient |
| panier neuf | après l'enregistrement, la commande suivante repart d'un panier neuf, le client reste connu |
| prise en panne | la commande est enregistrée quand même, l'envoi reste à reprendre (jamais perdue, jamais doublée) |
"""

from __future__ import annotations

import asyncio

import pytest

from api.db.bases_clients import horloge
from api.services.commande import panier
from api.services.restauration.prises.prise import poser_prise_de_test
from api.services.restauration.prises.prise_essai import PriseTest
from api.services.restauration import source_commande
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_outils import appel_de_test  # noqa: F401


@pytest.fixture
async def prise(commerce, monkeypatch):
    """L'établissement A branché sur la prise de test, et le vrai lanceur d'envoi (tâche de fond sur sa propre connexion)."""
    la_prise = PriseTest()
    poser_prise_de_test(la_prise)
    await commerce.c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test')", commerce.a)
    monkeypatch.setattr(source_commande, "LANCEUR", source_commande.lancer_l_envoi)
    yield la_prise
    poser_prise_de_test(None)
    await attendre_les_envois()


async def attendre_les_envois():
    taches = list(source_commande._TACHES)
    if taches:
        await asyncio.gather(*taches)


async def jusqu_a_la_relecture(jouer, articles="une regina normale et un coca"):
    await jouer("choisir_mode", mode="à emporter")
    r = await jouer("ajouter", articles=articles)
    assert r["statut"] in ("OK", "CHOIX_OBLIGATOIRE"), r
    for _ in range(5):
        r = await jouer("finaliser", prenom="Alice", moyen="carte")
        if r.get("manque") == "relecture":
            return r
    raise AssertionError(r)


async def test_regina_et_coca_de_bout_en_bout_jusqu_a_la_prise(appel_de_test, prise, commerce):
    jouer = appel_de_test.jouer
    assert (await jouer("choisir_mode", mode="à emporter"))["statut"] == "OK"
    r = await jouer("ajouter", articles="une regina et un coca")
    assert r["statut"] == "CHOIX_OBLIGATOIRE" and r["manque"] == "taille"  # la taille de la regina, une question fermée
    assert (await jouer("ajouter", choix="normale"))["statut"] == "OK"
    relecture = None
    for _ in range(4):
        relecture = await jouer("finaliser", prenom="Alice", moyen="carte")
        if relecture.get("manque") == "relecture":
            break
    assert relecture["texte_a_dire"].startswith("Je vous relis : un Regina Normale et un Coca-Cola")
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0  # rien n'est enregistré avant le « oui »
    assert prise.recues == []  # ni envoyé
    fait = await jouer("finaliser", confirmer=True)
    assert fait["statut"] == "ENREGISTREE" and fait["faits"]["total"] == 1490
    assert "enregistrée" in fait["suggestion"]
    await attendre_les_envois()
    (commande,) = await commerce.c.fetch("SELECT * FROM mark.resto_commande")
    assert (commande["total"], commande["statut"], commande["cree_par"]) == (1490, "acceptee", "agent")
    (recue,) = prise.recues
    assert recue["numero"] == str(commande["numero"]) and recue["total"] == 1490
    assert [(l["code_caisse"], l["quantite"]) for l in recue["lignes"]] == [("PIZ-REGINA-NORMALE", 1), ("BOI-COCA-COLA-33-CL", 1)]


async def test_aucun_outil_n_envoie_a_la_prise_l_envoi_n_a_lieu_qu_a_l_enregistrement(appel_de_test, prise, commerce):
    jouer = appel_de_test.jouer
    await jusqu_a_la_relecture(jouer)
    for outil in ("voir_commande", "vider_commande"):
        await jouer(outil)
    await attendre_les_envois()
    assert prise.recues == [] and await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0
    await jouer("ajouter", articles="une regina normale et un coca")
    await jusqu_a_la_relecture(jouer, articles="un coca")
    await jouer("finaliser", confirmer=True)
    await attendre_les_envois()
    assert len(prise.recues) == 1


async def test_l_incomplet_est_refuse_et_le_manque_est_dit_sans_rien_enregistrer(appel_de_test, prise, commerce):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="à emporter")
    await jouer("ajouter", articles="une regina")  # la taille manque
    r = await jouer("finaliser", confirmer=True)
    assert r["statut"] == "CHOIX_OBLIGATOIRE" and r["manque"] == "taille"
    await jouer("ajouter", choix="mega")
    sans_prenom = await jouer("finaliser", moyen="carte", confirmer=True)
    assert sans_prenom["manque"] in ("vente_en_plus", "prenom")
    for _ in range(3):
        sans_prenom = await jouer("finaliser", moyen="carte", confirmer=True)
    assert (sans_prenom["statut"], sans_prenom["manque"]) == ("INCOMPLETE", "prenom")
    sans_reglement = await jouer("finaliser", prenom="Alice", confirmer=True)
    assert (sans_reglement["statut"], sans_reglement["manque"]) == ("INCOMPLETE", "paiement")
    await attendre_les_envois()
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0 and prise.recues == []


async def test_deux_oui_en_meme_temps_une_seule_commande_une_seule_reception(appel_de_test, prise, commerce):
    jouer = appel_de_test.jouer
    await jusqu_a_la_relecture(jouer)
    a, b = await asyncio.gather(jouer("finaliser", confirmer=True), jouer("finaliser", confirmer=True))
    assert sorted([a["statut"], b["statut"]]) in (["DEJA_FAIT", "ENREGISTREE"], ["ENREGISTREE", "ENREGISTREE"])
    await attendre_les_envois()
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 1
    assert len(prise.recues) == 1
    if a["statut"] == b["statut"] == "ENREGISTREE":
        assert a["faits"]["numero"] == b["faits"]["numero"]  # le verrou rend le numéro du premier


async def test_changer_de_mode_garde_les_articles_et_en_livraison_la_zone_et_son_minimum_tiennent(appel_de_test, prise, commerce):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="à emporter")
    await jouer("ajouter", articles="un coca")
    r = await jouer("choisir_mode", mode="en livraison")
    assert r["statut"] == "OK" and r["manque"] == "zone" and r["suggestion"] == "Quelle est l'adresse de livraison ?"
    assert [l["nom"] for l in appel_de_test.fiche[panier.CLE]["lignes"]] == ["Coca-Cola"]
    appel_de_test.fiche[panier.CLE]["zone"] = {"id": commerce.zones["Proches"], "nom": "Proches"}  # minimum 15 €, le coca fait 2 €
    voir = await jouer("voir_commande")
    assert voir["statut"] == "MINIMUM_NON_ATTEINT"
    ajoute = await jouer("ajouter", articles="deux regina normale")
    assert ajoute["statut"] == "OK"
    assert (await jouer("voir_commande"))["faits"]["total"] == 200 + 2 * 1290


async def test_apres_l_enregistrement_la_commande_suivante_repart_d_un_panier_neuf(appel_de_test, prise, commerce):
    jouer = appel_de_test.jouer
    await jusqu_a_la_relecture(jouer)
    premiere = await jouer("finaliser", confirmer=True)
    assert premiere["statut"] == "ENREGISTREE"
    r = await jouer("ajouter", articles="un tiramisu", choix="classic")
    assert r["statut"] == "OK" and [l["nom"] for l in appel_de_test.fiche[panier.CLE]["lignes"]] == ["Tiramisu"]
    p = appel_de_test.fiche[panier.CLE]
    assert p["enregistree"] is None and p["client"]["prenom"] == "Alice" and p["mode"] == "emporter"  # le client et le mode restent
    for _ in range(5):
        seconde = await jouer("finaliser", moyen="carte")
        if seconde.get("manque") == "relecture":
            break
    assert (await jouer("finaliser", confirmer=True))["faits"]["numero"] != premiere["faits"]["numero"]
    await attendre_les_envois()
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 2


async def test_une_prise_en_panne_n_empeche_pas_l_enregistrement_et_l_envoi_reste_a_reprendre(appel_de_test, commerce, monkeypatch):
    panne = PriseTest("panne")
    poser_prise_de_test(panne)
    await commerce.c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test')", commerce.a)
    monkeypatch.setattr(source_commande, "LANCEUR", source_commande.lancer_l_envoi)
    try:
        jouer = appel_de_test.jouer
        await jusqu_a_la_relecture(jouer)
        fait = await jouer("finaliser", confirmer=True)
        assert fait["statut"] == "ENREGISTREE"  # l'agent dit « c'est enregistré » : la commande est dans le classeur
        await attendre_les_envois()
        (commande,) = await commerce.c.fetch("SELECT statut, tentatives FROM mark.resto_commande")
        assert commande["statut"] == "envoyee" and commande["tentatives"] == 1  # reste à reprendre (lot 10), jamais perdue
        assert panne.recues == []
    finally:
        poser_prise_de_test(None)
        await attendre_les_envois()


_ = (horloge, JEUDI_MIDI)
