"""[.mark] Module Restauration, lot 5, étape 5 : le flux en direct de la commande et la panne en pleine commande (W24).

Par le VRAI gestionnaire d'un outil ``integration`` (fiche de l'appel, base du client, Redis du flux).

| Test | Ce qu'il prouve |
|---|---|
| ``commande.panier`` | chaque geste qui change le panier émet l'événement du contrat (appel, version qui avance) ; une simple lecture n'émet rien |
| ``commande.creee`` | l'enregistrement émet numéro, numéro court, mode, heure annoncée, total ; tous les événements passent le contrôle du contrat |
| vrai flux | l'événement est dans la liste Redis de CET établissement et d'aucun autre |
| flux en panne | un flux qui ne part pas ne casse ni l'outil ni la commande (R1 : au journal) |
| panne | une panne du catalogue ou de la base rend ``INDISPONIBLE`` avec la phrase de l'équipe, jamais un panier perdu |
| message à l'équipe | le contenu de la commande en cours est joint à la demande de rappel de l'appel (une seule entrée, remplacée) et se lit dans son résumé |
| panne à l'enregistrement | rien n'est enregistré, la commande est transmise à l'équipe |
"""

from __future__ import annotations

import json

import pytest
import redis.asyncio as aioredis

from api.constants import REDIS_URL
from api.services.apres_appel import rappels
from api.services.commande import panier
from api.services.restauration import flux
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_outils import appel_de_test  # noqa: F401


@pytest.fixture
def evenements(monkeypatch):
    """Les événements que le comptoir émet, ramassés ; chacun est d'abord passé au contrôle du contrat (un champ en trop ou en moins est refusé)."""
    emis: list[tuple[int, int, str, dict]] = []

    async def emettre(organisation, etablissement, type_, donnees, **_):
        flux.verifier(type_, donnees)
        emis.append((organisation, etablissement, type_, donnees))
        return "1-0"

    monkeypatch.setattr(flux, "emettre", emettre)
    return emis


async def _tout_jusqu_a_la_relecture(jouer):
    await jouer("choisir_mode", mode="emporter")
    await jouer("ajouter", articles="une regina normale et un coca")
    for _ in range(4):
        r = await jouer("finaliser", prenom="Alice", moyen="carte")
        if r.get("manque") == "relecture":
            return r
    raise AssertionError(r)


async def test_chaque_geste_qui_change_le_panier_emet_commande_panier_et_une_lecture_n_emet_rien(appel_de_test, evenements):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="emporter")
    await jouer("ajouter", articles="un coca")
    avant = len(evenements)
    await jouer("voir_commande")
    assert len(evenements) == avant  # lire n'est pas changer
    await jouer("modifier", ligne="1", quantite=3)
    paniers = [(o, e, d) for o, e, t, d in evenements if t == "commande.panier"]
    assert len(paniers) == 3
    versions = [d["version"] for _, _, d in paniers]
    assert versions == sorted(set(versions)) and all(d["appel_id"] == "4242" for _, _, d in paniers)
    assert {(o, e) for o, e, _ in paniers} == {(7, appel_de_test.commerce.a)}


async def test_l_enregistrement_emet_commande_creee_avec_le_contrat(appel_de_test, evenements):
    jouer = appel_de_test.jouer
    await _tout_jusqu_a_la_relecture(jouer)
    r = await jouer("finaliser", confirmer=True)
    assert r["statut"] in ("ENREGISTREE", "TRANSMISE"), r
    (creee,) = [d for _, _, t, d in evenements if t == "commande.creee"]
    assert creee["numero"] == r["faits"]["numero"] and creee["numero_court"] == "C1"
    assert (creee["mode"], creee["total"]) == ("emporter", 1490)
    assert flux.verifier("commande.creee", creee)["heure_annoncee"].startswith("2026-11-12T")  # l'heure annoncée, écrite en ISO par le flux
    assert [t for _, _, t, _ in evenements].count("commande.creee") == 1


async def test_un_second_oui_n_emet_pas_une_seconde_commande_creee(appel_de_test, evenements):
    jouer = appel_de_test.jouer
    await _tout_jusqu_a_la_relecture(jouer)
    await jouer("finaliser", confirmer=True)
    seconde = await jouer("finaliser", confirmer=True)
    assert seconde["statut"] == "DEJA_FAIT"
    assert [t for _, _, t, _ in evenements].count("commande.creee") == 1


async def test_l_evenement_est_dans_le_vrai_flux_de_cet_etablissement_seulement(appel_de_test):
    flux._redis = None
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    cle_a, cle_b = flux.cle_du_flux(7, appel_de_test.commerce.a), flux.cle_du_flux(7, appel_de_test.commerce.b)
    await r.delete(cle_a, cle_b)
    try:
        await appel_de_test.jouer("choisir_mode", mode="emporter")
        await appel_de_test.jouer("ajouter", articles="un coca")
        dans_a = await r.xrange(cle_a)
        assert [json.loads(c["donnees"])["version"] > 0 for _, c in dans_a if c["type"] == "commande.panier"] == [True, True]
        assert await r.xrange(cle_b) == []  # jamais chez un autre établissement
    finally:
        await r.delete(cle_a, cle_b)
        await r.aclose()
        flux._redis = None


async def test_un_flux_qui_ne_part_pas_ne_casse_ni_l_outil_ni_la_commande(appel_de_test, monkeypatch):
    async def en_panne(*a, **k):
        raise ConnectionError("redis injoignable")

    monkeypatch.setattr(flux, "emettre", en_panne)
    await appel_de_test.jouer("choisir_mode", mode="emporter")
    r = await appel_de_test.jouer("ajouter", articles="un coca")
    assert r["statut"] == "OK" and appel_de_test.fiche[panier.CLE]["lignes"]


# --------------------------------------------------------------------------- #
# La panne en pleine commande
# --------------------------------------------------------------------------- #


async def test_une_panne_du_catalogue_rend_indisponible_et_joint_la_commande_a_l_equipe(appel_de_test, monkeypatch):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="emporter")
    await jouer("ajouter", articles="une regina normale et un coca")

    async def casse(self, *a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(SourceClasseur, "chiffrer", casse)
    r = await jouer("voir_commande")
    assert r["statut"] == "INDISPONIBLE" and r["faits"]["transmise_a_l_equipe"] is True
    assert "équipe" in r["suggestion"] and "rappelle" in r["suggestion"]
    (entree,) = rappels.rappels_de(appel_de_test.fiche)
    assert entree["origine"] == rappels.ORIGINE_COMMANDE and entree["numero"] == "+33612345678"
    assert "une Regina Normale et un Coca-Cola" in entree["objet"] and "à emporter" in entree["objet"]
    resume = rappels.resume_du_rappel(entree)
    assert "commande en cours" in resume and "Regina Normale" in resume and "numéro de l'appelant : +33612345678" in resume
    # une seconde panne remplace l'entrée : une seule demande par appel
    await jouer("voir_commande")
    assert len(rappels.rappels_de(appel_de_test.fiche)) == 1


async def test_sans_rien_dans_le_panier_une_panne_ne_joint_rien(appel_de_test, monkeypatch):
    async def casse(self, *a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(SourceClasseur, "etat", casse)
    r = await appel_de_test.jouer("choisir_mode", mode="emporter")
    assert r["statut"] == "INDISPONIBLE" and r["faits"]["transmise_a_l_equipe"] is False and r["suggestion"] == ""
    assert rappels.rappels_de(appel_de_test.fiche) == []


async def test_une_panne_a_l_enregistrement_n_enregistre_rien_et_transmet_la_commande(appel_de_test, monkeypatch):
    jouer = appel_de_test.jouer
    await _tout_jusqu_a_la_relecture(jouer)

    async def casse(self, *a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(SourceClasseur, "enregistrer", casse)
    r = await jouer("finaliser", confirmer=True)
    assert r["statut"] == "INDISPONIBLE" and r["faits"]["transmise_a_l_equipe"] is True
    assert await appel_de_test.commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0
    assert "Regina Normale" in rappels.rappels_de(appel_de_test.fiche)[0]["objet"]


async def test_les_lignes_en_attente_d_une_question_sont_aussi_jointes(appel_de_test, monkeypatch):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="emporter")
    await jouer("ajouter", articles="une regina et un coca")  # la taille de la regina reste une question

    async def casse(self, *a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(SourceClasseur, "chiffrer", casse)
    await jouer("voir_commande")
    assert "Regina" in rappels.rappels_de(appel_de_test.fiche)[0]["objet"]  # rien de ce que l'appelant a dit n'est perdu
