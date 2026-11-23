"""[.mark] Module Restauration, lot 5, étape 5 : le flux en direct de la commande et la panne en pleine commande (W24).

Par la vraie porte de la fiche (lot 4, D49 : une fiche par tour, plus un geste par outil ; fiche de l'appel, base du client, Redis du flux).

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
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.partie_1.porte_essai import Essai
from api.tests.mark.partie_1.test_l04_cuisine import _jusqu_a_l_enregistrement
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401


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


@pytest.fixture
def appel_de_test(commerce, monkeypatch):  # noqa: F811
    """Lot 4 (D49) : l'appel sur la fiche. Le montage de la porte (vraie source, vraie porte), avec l'organisation 7 et l'appel 4242 comme avant ;
    l'envoi à la prise part en tâche de fond : ramassé ici, aucune tâche ne survit au test."""
    monkeypatch.setattr("api.services.restauration.source_commande.LANCEUR", lambda *a: None)
    e = Essai(commerce, monkeypatch, appelant="+33612345678")
    e.ctx.organization_id, e.ctx.run_id = 7, 4242
    e.commerce = commerce
    return e


REGINA_ET_COCA = [{"article": "regina", "quantite": 1, "variante": "Normale"}, {"article": "coca", "quantite": 1}]


async def _a_emporter(e):
    return await e.tour("à emporter", mode_de_retrait="emporter")


async def _tout_jusqu_a_l_enregistrement(e):
    await _a_emporter(e)
    await e.tour("une regina normale et un coca", ajouter=REGINA_ET_COCA)
    return await _jusqu_a_l_enregistrement(e, prenom="Alice")


async def test_chaque_geste_qui_change_le_panier_emet_commande_panier_et_une_lecture_n_emet_rien(appel_de_test, evenements):
    e = appel_de_test
    await _a_emporter(e)
    await e.tour("un coca", ajouter=[{"article": "coca", "quantite": 1}])
    avant = len(evenements)
    await e.lecture(sujet="panier")
    assert len(evenements) == avant  # lire n'est pas changer
    await e.tour("trois cocas plutôt", changer_quantite=[{"ligne": "Coca-Cola", "quantite": 3}])
    paniers = [(o, ev, d) for o, ev, t, d in evenements if t == "commande.panier"]
    assert len(paniers) >= 2  # un événement par fiche qui change le panier (D49 : une fiche par tour, plus un par geste)
    versions = [d["version"] for _, _, d in paniers]
    assert versions == sorted(set(versions)) and all(d["appel_id"] == "4242" for _, _, d in paniers)
    assert {(o, ev) for o, ev, _ in paniers} == {(7, e.commerce.a)}


async def test_l_enregistrement_emet_commande_creee_avec_le_contrat(appel_de_test, evenements):
    e = appel_de_test
    await _tout_jusqu_a_l_enregistrement(e)
    enregistree = e.p["enregistree"]
    (creee,) = [d for _, _, t, d in evenements if t == "commande.creee"]
    assert creee["numero"] == enregistree["numero"] and creee["numero_court"] == "C1"
    assert (creee["mode"], creee["total"]) == ("emporter", 1490)
    assert flux.verifier("commande.creee", creee)["heure_annoncee"].startswith("2026-11-12T")  # l'heure annoncée, écrite en ISO par le flux
    assert [t for _, _, t, _ in evenements].count("commande.creee") == 1


async def test_un_second_oui_n_emet_pas_une_seconde_commande_creee(appel_de_test, evenements):
    e = appel_de_test
    await _tout_jusqu_a_l_enregistrement(e)
    seconde = await e.tour("oui", c_est_tout=True, reponse={"question_id": "?", "sens": "accepte"})
    assert [t for _, _, t, _ in evenements].count("commande.creee") == 1, seconde  # le second enregistrement est refusé par la porte (``deja_fait``)


async def test_l_evenement_est_dans_le_vrai_flux_de_cet_etablissement_seulement(appel_de_test):
    flux._redis = None
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    cle_a, cle_b = flux.cle_du_flux(7, appel_de_test.commerce.a), flux.cle_du_flux(7, appel_de_test.commerce.b)
    await r.delete(cle_a, cle_b)
    try:
        await _a_emporter(appel_de_test)
        await appel_de_test.tour("un coca", ajouter=[{"article": "coca", "quantite": 1}])
        dans_a = await r.xrange(cle_a)
        assert [json.loads(c["donnees"])["version"] > 0 for _, c in dans_a if c["type"] == "commande.panier"]  # au moins un événement, chez A
        assert await r.xrange(cle_b) == []  # jamais chez un autre établissement
    finally:
        await r.delete(cle_a, cle_b)
        await r.aclose()
        flux._redis = None


async def test_un_flux_qui_ne_part_pas_ne_casse_ni_l_outil_ni_la_commande(appel_de_test, monkeypatch):
    async def en_panne(*a, **k):
        raise ConnectionError("redis injoignable")

    monkeypatch.setattr(flux, "emettre", en_panne)
    await _a_emporter(appel_de_test)
    r = await appel_de_test.tour("un coca", ajouter=[{"article": "coca", "quantite": 1}])
    assert not (r.get("faits") or {}).get("indisponible") and appel_de_test.fiche_de_l_appel[panier.CLE]["lignes"], r


# --------------------------------------------------------------------------- #
# La panne en pleine commande
# --------------------------------------------------------------------------- #


async def test_une_panne_du_catalogue_rend_indisponible_et_joint_la_commande_a_l_equipe(appel_de_test, monkeypatch):
    e = appel_de_test
    await _a_emporter(e)
    await e.tour("une regina normale et un coca", ajouter=REGINA_ET_COCA)

    async def casse(self, *a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(SourceClasseur, "chiffrer", casse)
    r = await e.lecture(sujet="panier")
    assert r["faits"]["indisponible"] is True and r["faits"]["transmise_a_l_equipe"] is True
    (entree,) = rappels.rappels_de(e.fiche_de_l_appel)
    assert entree["origine"] == rappels.ORIGINE_COMMANDE and entree["numero"] == "+33612345678"
    assert "une Regina Normale et un Coca-Cola" in entree["objet"] and "à emporter" in entree["objet"]
    resume = rappels.resume_du_rappel(entree)
    assert "commande en cours" in resume and "Regina Normale" in resume and "numéro de l'appelant : +33612345678" in resume
    # une seconde panne remplace l'entrée : une seule demande par appel
    await e.lecture(sujet="panier")
    assert len(rappels.rappels_de(e.fiche_de_l_appel)) == 1


async def test_sans_rien_dans_le_panier_une_panne_ne_joint_rien(appel_de_test, monkeypatch):
    async def casse(self, *a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(SourceClasseur, "etat", casse)
    r = await appel_de_test.tour("à emporter", mode_de_retrait="emporter")
    assert r["faits"]["indisponible"] is True and r["faits"]["transmise_a_l_equipe"] is False
    assert rappels.rappels_de(appel_de_test.fiche_de_l_appel) == []


async def test_une_panne_a_l_enregistrement_n_enregistre_rien_et_transmet_la_commande(appel_de_test, monkeypatch):
    e = appel_de_test
    await _a_emporter(e)
    await e.tour("une regina normale et un coca", ajouter=REGINA_ET_COCA)

    async def casse(self, *a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(SourceClasseur, "enregistrer", casse)
    try:
        await _jusqu_a_l_enregistrement(e, prenom="Alice")
    except AssertionError:
        pass  # l'enregistrement tombe en panne : la fiche n'a pas de commande enregistrée
    assert await e.commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0
    assert "Regina Normale" in rappels.rappels_de(e.fiche_de_l_appel)[0]["objet"]


async def test_les_lignes_en_attente_d_une_question_sont_aussi_jointes(appel_de_test, monkeypatch):
    e = appel_de_test
    await _a_emporter(e)
    await e.tour("une regina et un coca", ajouter=[{"article": "regina", "quantite": 1}, {"article": "coca", "quantite": 1}])  # la taille de la regina reste une question

    async def casse(self, *a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(SourceClasseur, "chiffrer", casse)
    await e.lecture(sujet="panier")
    assert "Regina" in rappels.rappels_de(e.fiche_de_l_appel)[0]["objet"]  # rien de ce que l'appelant a dit n'est perdu
