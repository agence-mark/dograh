"""[.mark] Module Restauration, lot 26, M21 : les scénarios livrés de la caisse de démo se mettent à niveau au déploiement, sans toucher à ceux d'une personne.

| Test | Ce qu'il prouve |
|---|---|
| livraison | une base neuve reçoit les neuf scénarios, chacun avec l'empreinte de son contenu livré ; rejouée, aucune écriture |
| mise à niveau | un scénario livré avant (contenu d'une ancienne version, sans empreinte) prend le contenu du code ; un livré avec empreinte dont le contenu est resté tel quel aussi |
| jamais écrasé | un scénario enregistré à la main (même du même nom), un livré dont le contenu ne correspond plus à son empreinte : intacts |
| supprimé | un scénario livré supprimé revient (comme avant) ; rien d'autre ne bouge |
| au déploiement | ``au_demarrage`` : éteinte ou sans Labo = rien ; sinon met à niveau la base du Labo et dit quelles clés ont changé |
"""

from __future__ import annotations

import copy
import uuid

import pytest

from api.services.builder import stock
from api.services.restauration.caisse_demo import garde, scenarios
from api.tests.mark.equipe_commun import creer_organisation


async def _org(db_session) -> int:
    return await creer_organisation(db_session, f"labo-{uuid.uuid4().hex[:8]}")


def _ancien(cle: str, **changements) -> dict:
    """Ce qu'une version d'avant livrait : le contenu d'aujourd'hui, un peu différent, SANS empreinte."""
    ligne = {**copy.deepcopy(scenarios.LIVRES[cle]), "livre": True}
    ligne.update(changements)
    return ligne


async def test_une_base_neuve_recoit_les_scenarios_avec_leur_empreinte_et_rejouee_n_ecrit_rien(db_session):
    org = await _org(db_session)
    lus = await scenarios.livrer(org)
    assert sorted(lus) == sorted(scenarios.LIVRES)
    assert all(v["livre"] is True and v["empreinte"] == scenarios._empreinte(scenarios.LIVRES[k]) for k, v in lus.items())
    avant = await db_session.get_configuration(org, scenarios.CLE)
    assert await scenarios.livrer(org) == lus
    apres = await db_session.get_configuration(org, scenarios.CLE)
    assert apres.value == avant.value and apres.updated_at == avant.updated_at  # aucune écriture


async def test_un_scenario_livre_avant_prend_le_contenu_du_code_sans_toucher_a_ceux_d_une_personne(db_session):
    org = await _org(db_session)
    a_la_main = {"nom": "Caisse lente", "etat": "ouvert", "minutes_en_plus": 5, "comportement": {"reponse": "silence"}, "delai": 45, "livre": False}
    modifie = {**scenarios._livre(scenarios.LIVRES["caisse-stricte"]), "delai": 99}  # empreinte d'avant, contenu changé depuis par quelqu'un
    await stock.ecrire(org, scenarios.CLE, {
        "tout-va-bien": _ancien("tout-va-bien", delai=35, comportement={"reponse": "accepte", "acceptation": "manuelle"}),  # livré avant, sans empreinte
        "restaurant-deborde": scenarios._livre({**scenarios.LIVRES["restaurant-deborde"], "minutes_en_plus": 10}),         # livré avec empreinte, intact
        "caisse-lente": a_la_main,                                                                                            # d'une personne, même clé
        "caisse-stricte": modifie,
        "ma-recette": {"nom": "Ma recette", "etat": "ouvert", "minutes_en_plus": 0, "comportement": {}, "delai": 10, "livre": False},
    })
    lus = await scenarios.livrer(org)
    assert lus["tout-va-bien"]["delai"] == 20 and lus["tout-va-bien"]["comportement"] == scenarios.LIVRES["tout-va-bien"]["comportement"]
    assert lus["tout-va-bien"]["empreinte"] == scenarios._empreinte(scenarios.LIVRES["tout-va-bien"]) and lus["tout-va-bien"]["livre"] is True
    assert lus["restaurant-deborde"]["minutes_en_plus"] == 20
    assert lus["caisse-lente"] == a_la_main  # jamais écrasé, même nom qu'un livré
    assert lus["caisse-stricte"] == modifie  # l'empreinte ne correspond plus : une personne l'a changé
    assert lus["ma-recette"]["nom"] == "Ma recette"
    assert sorted(lus) == sorted({*scenarios.LIVRES, "ma-recette"})  # les manquants sont versés


async def test_un_scenario_livre_supprime_revient_et_rien_d_autre_ne_bouge(db_session):
    org = await _org(db_session)
    await scenarios.livrer(org)
    assert await scenarios.supprimer(org, "caisse-muette") is True
    autres = {k: v for k, v in (await scenarios.lire(org)).items()}
    lus = await scenarios.livrer(org)
    assert "caisse-muette" in lus and {k: v for k, v in lus.items() if k != "caisse-muette"} == autres


async def test_au_deploiement_la_base_du_labo_est_mise_a_niveau_et_la_fonction_dit_ce_qui_a_change(db_session, monkeypatch):
    org = await _org(db_session)
    await stock.ecrire(org, scenarios.CLE, {"tout-va-bien": _ancien("tout-va-bien", delai=35)})
    # éteinte : rien
    monkeypatch.delenv(garde.VARIABLE, raising=False)
    assert await scenarios.au_demarrage() is None
    assert (await scenarios.lire(org))["tout-va-bien"]["delai"] == 35
    # allumée mais aucun Labo : rien
    monkeypatch.setenv(garde.VARIABLE, "1")
    async def sans_labo():
        return None
    monkeypatch.setattr(garde, "id_du_labo", sans_labo)
    assert await scenarios.au_demarrage() is None
    # allumée, avec un Labo : mise à niveau
    async def labo():
        return org
    monkeypatch.setattr(garde, "id_du_labo", labo)
    change = await scenarios.au_demarrage()
    assert "tout-va-bien" in change and set(change) == set(scenarios.LIVRES)  # la mise à niveau + les huit versés
    assert (await scenarios.lire(org))["tout-va-bien"]["delai"] == 20
    assert await scenarios.au_demarrage() == []  # rejouée : plus rien à changer
