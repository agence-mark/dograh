"""[.mark] U3 bis (E62) : variables en étiquettes, côté serveur.

| Test | Ce qu'il prouve |
|---|---|
| citations | clés lues partout (étape, réglages), repli reconnu, variables du moteur écartées |
| catalogue | quatre sources, une clé = une source, valeurs d'essai = colonnes de campagne seulement |
| garde | une clé inconnue est détectée, `initial_context.*` est ouvert, la publication est refusée avec la clé, l'étape et le champ |
| citations d'une clé | les champs à réécrire avant de renommer ou supprimer une variable |
| cloisonnement | le catalogue d'une organisation ne contient rien d'une autre |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.builder.tests_agent import publication
from api.services.variables_agent import catalogue as cat
from api.services.variables_agent import citations as cit
from api.services.variables_agent import garde

GRAPHE = {
    "nodes": [
        {"id": "1", "type": "startCall", "data": {"name": "Accueil", "prompt": "Bonjour, ici {{etablissement}}. {{ prenom | fallback:cher client }} {{ tarif_a }}", "greeting": "Salut {{initial_context.ville}}"}},
        {"id": "2", "type": "endCall", "data": {"name": "Fin", "prompt": "Il est {{current_time_Europe/Paris}}, {{inconnue_x}}"}},
    ],
    "edges": [],
}


def test_les_citations_sont_lues_partout_avec_leur_repli_et_sans_les_variables_du_moteur():
    cs = cit.citations_de(GRAPHE, {"phrases": {"patience": "Un instant {{adresse_etablissement}}"}})
    cles = {c.cle for c in cs}
    assert cles == {"etablissement", "prenom", "tarif_a", "initial_context.ville", "inconnue_x", "adresse_etablissement"}
    assert next(c for c in cs if c.cle == "prenom").avec_repli is True
    assert next(c for c in cs if c.cle == "etablissement").etape == "Accueil"
    assert next(c for c in cs if c.cle == "adresse_etablissement").etape is None


def test_le_catalogue_a_quatre_sources_et_une_cle_n_a_qu_une_source():
    v = cat.construire(
        objets=[{"nom": "tarif_a", "libelle": "Tarif A", "exemple": "12 EUR"}, {"nom": "etablissement", "libelle": "doublon"}],
        champs_fiche=["prenom"],
        colonnes_campagne=["prenom", "societe"],
    )
    par_cle = {x.cle: x for x in v}
    assert par_cle["tarif_a"].source == "entreprise" and par_cle["tarif_a"].exemple == "12 EUR"
    assert par_cle["prenom"].source == "fiche"  # la fiche passe avant la campagne
    assert par_cle["societe"].source == "campagne"
    assert par_cle["etablissement"].libelle != "doublon"  # le code passe avant un objet
    assert {x.source for x in v} == set(cat.SOURCES)
    assert len([x for x in v if x.cle == "prenom"]) == 1


def test_une_cle_absente_du_catalogue_est_inconnue_et_initial_context_reste_ouvert():
    connues = cat.cles_connues(cat.construire(objets=[{"nom": "tarif_a"}], champs_fiche=["prenom"]))
    inconnues = {c.cle for c in cit.inconnues(cit.citations_de(GRAPHE, None), connues)}
    assert inconnues == {"inconnue_x"}


def test_les_champs_qui_citent_une_variable_avec_ou_sans_repli():
    agents = [
        (1, "Standard", GRAPHE, {}),
        (2, "Autre", {"nodes": [{"id": "9", "data": {"name": "Z", "prompt": "{{prenom | madame}}"}}]}, None),
        (3, "Rien", {"nodes": [{"id": "9", "data": {"name": "Z", "prompt": "prenomx {{prenomx}}"}}]}, None),
    ]
    champs = garde.champs_citant("prenom", agents)
    assert {(c["agent_id"], c["etape"]) for c in champs} == {(1, "Accueil"), (2, "Z")}


async def test_le_brouillon_qui_cite_une_cle_inconnue_est_signale(monkeypatch):
    async def catalogue(organisation, graphe, configs, essai):
        return cat.construire(objets=[{"nom": "tarif_a"}], champs_fiche=["prenom"])

    monkeypatch.setattr(garde, "catalogue_de", catalogue)
    brouillon = SimpleNamespace(workflow_json=GRAPHE, workflow_configurations={}, version_number=2)
    sortie = await garde.cles_inconnues_du_brouillon(SimpleNamespace(template_context_variables={}), brouillon, 5)
    assert sortie == [{"cle": "inconnue_x", "champ": "nodes[2].prompt", "etape": "Fin"}]


async def test_une_erreur_du_calcul_ne_bloque_jamais_la_publication(monkeypatch):
    monkeypatch.setattr(garde, "catalogue_de", AsyncMock(side_effect=RuntimeError("panne")))
    brouillon = SimpleNamespace(workflow_json=GRAPHE, workflow_configurations={}, version_number=2)
    assert await garde.cles_inconnues_du_brouillon(SimpleNamespace(), brouillon, 5) == []


async def test_la_publication_est_refusee_avec_la_cle_et_passe_une_fois_la_variable_creee(monkeypatch):
    monkeypatch.setattr(publication, "problemes_des_tests_obligatoires", AsyncMock(return_value=[]))
    monkeypatch.setattr(publication, "agent_suivi", AsyncMock(return_value=False))
    monkeypatch.delenv(publication.INTERRUPTEUR, raising=False)
    objets = [{"nom": "tarif_a"}]

    async def catalogue(organisation, graphe, configs, essai):
        return cat.construire(objets=objets, champs_fiche=["prenom"])

    monkeypatch.setattr(garde, "catalogue_de", catalogue)
    brouillon = SimpleNamespace(workflow_json=GRAPHE, workflow_configurations={}, version_number=2)
    agent = SimpleNamespace(id=1, template_context_variables={})
    refus = await publication.verifier_avant_publication(agent, brouillon, 5)
    assert refus["is_valid"] is False and refus["garde"] == "builder"
    assert any("[Unknown variable] {{inconnue_x}}" in e["message"] for e in refus["errors"])
    assert refus["variables_inconnues"][0]["etape"] == "Fin"
    objets.append({"nom": "inconnue_x"})
    assert await publication.verifier_avant_publication(agent, brouillon, 5) is None


async def test_le_catalogue_d_une_organisation_ne_contient_rien_d_une_autre(monkeypatch):
    noms = {1: ["secret_de_a"], 2: ["secret_de_b"]}

    async def objets(org):
        return [{"nom": n, "libelle": n, "exemple": ""} for n in noms[org]]

    monkeypatch.setattr(cat, "_objets", objets)
    monkeypatch.setattr(cat, "_phrases", AsyncMock(return_value=[]))
    cles_a = cat.cles_connues(await cat.catalogue_de(1))
    cles_b = cat.cles_connues(await cat.catalogue_de(2))
    assert "secret_de_a" in cles_a and "secret_de_b" not in cles_a
    assert "secret_de_b" in cles_b and "secret_de_a" not in cles_b


async def test_la_route_du_catalogue_refuse_l_agent_d_une_autre_organisation(monkeypatch):
    from fastapi import HTTPException

    from api.routes import variables_agent as route

    monkeypatch.setattr(route.db_client, "get_workflow", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as e:
        await route.lire_le_catalogue(agent=9, user=SimpleNamespace(selected_organization_id=1))
    assert e.value.status_code == 404
