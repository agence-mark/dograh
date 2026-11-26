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
| prise en panne | la commande est enregistrée quand même, l'envoi reste à reprendre (jamais perdue, jamais doublée) |

Lot 4 de la partie 1 (D49) : les outils n'existent plus (lot 3) ; le parcours se joue par les gestes nommés de la cuisine (montage
``appel_de_test`` de ``test_restauration_commande_lot6``), avec la fin du contrat : le récapitulatif et son accord, puis le règlement et le
prénom, puis l'enregistrement. « Panier neuf après l'enregistrement » est retiré : une commande par appel (E30).
"""

from __future__ import annotations

import asyncio

import pytest

from api.db.bases_clients import horloge
from api.services.commande import panier
from api.services.restauration.caisse.prises.prise import poser_prise_de_test
from api.services.restauration.caisse.prises.prise_essai import PriseTest
from api.services.restauration import source_commande
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_restauration_commande_lot6 import appel_de_test  # noqa: F401


@pytest.fixture
async def prise(commerce, monkeypatch):
    """L'établissement A branché sur la prise de test, et le vrai lanceur d'envoi (tâche de fond sur sa propre connexion)."""
    la_prise = PriseTest()
    # Une tâche d'envoi laissée par un test d'AVANT (sa connexion est fermée) ferait échouer le ``gather`` d'ici (PendingRollbackError, vu dans la suite entière, jamais seul) : on repart de zéro
    source_commande._TACHES.clear()
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


async def jusqu_a_la_relecture(jouer, articles=(A("regina", 1, "Normale"), "coca")):
    await jouer("choisir_mode", mode="à emporter")
    r = await jouer("ajouter", articles=list(articles))
    assert r["statut"] in ("OK", "CHOIX_OBLIGATOIRE"), r
    for _ in range(5):
        r = await jouer("finaliser")
        if r.get("manque") == "relecture":
            return r
    raise AssertionError(r)


async def oui(jouer):
    """Son « oui » au récapitulatif, avec le règlement et le prénom dits (les cases de fin de la fiche)."""
    return await jouer("finaliser", confirmer=True, prenom="Alice", moyen="carte")  # le numéro qui s'affiche : le montage dit « oui » aussi


async def test_regina_et_coca_de_bout_en_bout_jusqu_a_la_prise(appel_de_test, prise, commerce):
    jouer = appel_de_test.jouer
    assert (await jouer("choisir_mode", mode="à emporter"))["statut"] == "OK"
    r = await jouer("ajouter", articles=["regina", "coca"])
    assert r["statut"] == "CHOIX_OBLIGATOIRE" and r["manque"] == "taille"  # la taille de la regina, une question fermée
    assert (await jouer("repondre", choix="normale"))["statut"] == "OK"
    relecture = None
    for _ in range(4):
        relecture = await jouer("finaliser")
        if relecture.get("manque") == "relecture":
            break
    assert not relecture["suggestion"] and [l["nom"] for l in relecture["faits"]["lignes"]] == ["Regina Normale", "Coca-Cola"], relecture  # C6 (décision d'Evan 25/11 9 h 30) : des faits
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0  # rien n'est enregistré avant le « oui »
    assert prise.recues == []  # ni envoyé
    fait = await oui(jouer)
    assert fait["statut"] == "ENREGISTREE" and fait["faits"]["total"] == 1490
    assert fait["suggestion"] == "" and fait["faits"]["quand_dit"], fait  # C7 B9 (0e89e408) : plus de texte ; « enregistrée, prête/livrée … » est dans les faits mode et quand_dit
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
    await jusqu_a_la_relecture(jouer, articles=["coca"])
    await oui(jouer)
    await attendre_les_envois()
    assert len(prise.recues) == 1


async def test_l_incomplet_est_refuse_et_le_manque_est_dit_sans_rien_enregistrer(appel_de_test, prise, commerce):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="à emporter")
    await jouer("ajouter", articles=["regina"])  # la taille manque
    r = await jouer("finaliser", confirmer=True)
    assert r["statut"] == "CHOIX_OBLIGATOIRE" and r["manque"] == "taille"
    await jouer("repondre", choix="mega")
    r = await jouer("finaliser", moyen="carte", confirmer=True)
    assert r["manque"] in ("vente_en_plus", "relecture")  # sans récapitulatif lu, un « oui » ne suffit pas
    for _ in range(3):
        if r["manque"] == "relecture":
            break
        r = await jouer("finaliser", moyen="carte", confirmer=True)
    assert (r["statut"], r["manque"]) == ("INCOMPLETE", "relecture")
    sans_prenom = await jouer("finaliser", moyen="carte", confirmer=True)
    assert (sans_prenom["statut"], sans_prenom["manque"]) == ("INCOMPLETE", "prenom")
    await attendre_les_envois()
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0 and prise.recues == []


# test_deux_oui_en_meme_temps_une_seule_commande_une_seule_reception : supprimé au lot 4 (D49) : deux gestes d'enregistrement sur une même connexion ne se jouent plus côté cuisine, la porte refuse le second ; sens repris par partie_1/test_l03_porte.py::test_second_enregistrement_refuse



async def test_changer_de_mode_garde_les_articles_et_en_livraison_la_zone_et_son_minimum_tiennent(appel_de_test, prise, commerce):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="à emporter")
    await jouer("ajouter", articles=["coca"])
    r = await jouer("choisir_mode", mode="en livraison")
    assert r["statut"] == "OK" and r["manque"] == "zone" and r["suggestion"] == ""  # C7 B5 (Evan 25/11 8 h 45) : le modèle demande l'adresse d'après le manque
    assert [l["nom"] for l in appel_de_test.fiche[panier.CLE]["lignes"]] == ["Coca-Cola"]
    appel_de_test.fiche[panier.CLE]["zone"] = {"id": commerce.zones["Proches"], "nom": "Proches"}  # minimum 15 €, le coca fait 2 €
    voir = await jouer("voir_commande")
    assert voir["statut"] == "OK" and voir["faits"]["minimum_non_atteint"]["manque"] == 1300  # lot 26, M27 : les lignes, et ce qui manque (plus un refus)
    ajoute = await jouer("ajouter", articles=[A("regina", 2, "Normale")])
    assert ajoute["statut"] == "OK"
    assert (await jouer("voir_commande"))["faits"]["total"] == 200 + 2 * 1290


# test_apres_l_enregistrement_la_commande_suivante_repart_d_un_panier_neuf : supprimé au lot 4 (D49), une commande par appel (E30) : un changement après l'enregistrement remplace la commande de l'appel ; sens repris par partie_1/test_l04_cuisine.py::test_commande_de_l_appel_apres_enregistrement et partie_1/test_l03_porte.py::test_second_enregistrement_refuse.


async def test_une_prise_en_panne_n_empeche_pas_l_enregistrement_et_l_envoi_reste_a_reprendre(appel_de_test, commerce, monkeypatch):
    panne = PriseTest("panne")
    poser_prise_de_test(panne)
    await commerce.c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test')", commerce.a)
    monkeypatch.setattr(source_commande, "LANCEUR", source_commande.lancer_l_envoi)
    try:
        jouer = appel_de_test.jouer
        await jusqu_a_la_relecture(jouer)
        fait = await oui(jouer)
        assert fait["statut"] == "ENREGISTREE"  # l'agent dit « c'est enregistré » : la commande est dans le classeur
        await attendre_les_envois()
        (commande,) = await commerce.c.fetch("SELECT statut, tentatives FROM mark.resto_commande")
        assert commande["statut"] == "envoyee" and commande["tentatives"] == 1  # reste à reprendre (lot 10), jamais perdue
        assert panne.recues == []
    finally:
        poser_prise_de_test(None)
        await attendre_les_envois()


_ = (horloge, JEUDI_MIDI)
