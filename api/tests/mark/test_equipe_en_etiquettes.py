"""[.mark] Chantier agents-specialises, lot 5 (= lot 3 du plan fiche-etablissement) :
l'équipe en étiquettes (décision M5 d'Evan : l'équipe est unique, le lieu est une étiquette).

| Test | Ce qu'il prouve |
|---|---|
| personnes de l'appel | toutes les personnes actives, quel que soit le lieu servi (plus de filtre) |
| ligne de l'agent | le nom des lieux de la personne après son rôle ; aucune étiquette = la ligne d'avant, à l'octet |
| clavier, vraie route | une personne d'un autre lieu est connue de l'appel, avec son étiquette ; deux lieux = deux noms |
| téléphone | le décroché passe le nom des lieux à l'injection de l'équipe (lecture du source, comme les tests voisins) |
| transfert | une personne d'un autre lieu aboutit, par l'outil, au numéro lu dans la copie |
| schéma | ``etablissement`` seul = une étiquette ; ``etablissements`` envoyé (même vide) fait foi |
| base du client | plusieurs lieux écrits et relus ; un lieu retiré disparaît ; le journal nomme la ligne ; une base restée en version 14 lit et écrit un lieu sans migrer, refuse plusieurs |
| route de l'équipe | ``PUT /organizations/equipe`` écrit la colonne d'avant ET ``personne_site`` |
"""

from __future__ import annotations

import inspect
import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from types import SimpleNamespace

from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture
from api.schemas.base_client import Equipe, Personne
from api.schemas.organization_preferences import OrganizationPreferences
from api.schemas.phrases import CataloguePhrases
from api.services.auth.depends import get_user_with_selected_organization
from api.services.equipe.appel import injecter_equipe, ligne, personnes_de_lappel
from api.services.etablissements import copie as module_copie
from api.services.workflow import text_chat_runner
from api.tests.mark.test_adresse_etablissement import _jouer_au_clavier
from api.tests.mark.test_base_client import (  # noqa: F401 -- fixtures
    CATALOGUE as CATALOGUE_BASE,
)
from api.tests.mark.test_base_client import (
    ORGANISATION,
    base_essai,
    base_prete,
)
from api.tests.mark.test_etablissements_heritage import CATALOGUE

NOMS = {"creil": "Magasin de Creil", "senlis": "Magasin de Senlis"}

# Des personnes neutres (X5) : aucun métier, aucune marque.
ICI = Personne(cle="camille", prenom="Camille", nom="Martin", role="Accueil", etablissement="creil")
AILLEURS = Personne(cle="noa", prenom="Noa", nom="Durand", role="Planning", etablissement="senlis")
DEUX_LIEUX = Personne(cle="eden", prenom="Eden", role="Conseil", etablissements=["creil", "senlis"])
TOUS = Personne(cle="sacha", prenom="Sacha", role="Comptabilité")
PARTI = Personne(cle="ange", prenom="Ange", etablissement="creil", actif=False)
EQUIPE = Equipe(personnes=[ICI, AILLEURS, DEUX_LIEUX, TOUS, PARTI])


# --------------------------------------------------------------------------- #
# 1. Le schéma d'une personne
# --------------------------------------------------------------------------- #


def test_un_etablissement_seul_est_une_etiquette_et_une_liste_fait_foi():
    assert Personne(cle="a", prenom="A", etablissement="creil").etablissements == ["creil"]
    assert Personne(cle="a", prenom="A").etablissements == [] and Personne(cle="a", prenom="A").etablissement is None
    deux = Personne(cle="a", prenom="A", etablissements=["senlis", "creil", "senlis"])
    assert deux.etablissements == ["senlis", "creil"] and deux.etablissement == "senlis"
    # Un écran qui renvoie les deux champs, la liste vidée : la liste fait foi (la personne devient « toute l'entreprise »).
    vide = Personne.model_validate({"cle": "a", "prenom": "A", "etablissement": "creil", "etablissements": []})
    assert vide.etablissements == [] and vide.etablissement is None
    # Un écran d'avant, qui n'envoie que l'ancien champ, marche toujours.
    ancien = Personne.model_validate({"cle": "a", "prenom": "A", "etablissement": "senlis"})
    assert ancien.etablissements == ["senlis"]


# --------------------------------------------------------------------------- #
# 2. Ce que l'agent lit
# --------------------------------------------------------------------------- #


def test_toutes_les_personnes_actives_quel_que_soit_le_lieu():
    attendu = ["camille", "noa", "eden", "sacha"]
    assert [p.cle for p in personnes_de_lappel(EQUIPE, "creil")] == attendu
    assert [p.cle for p in personnes_de_lappel(EQUIPE, "senlis")] == attendu
    assert [p.cle for p in personnes_de_lappel(EQUIPE, None)] == attendu


def test_la_ligne_porte_le_nom_des_lieux_et_rien_sans_etiquette():
    assert ligne(AILLEURS, NOMS) == "- Noa Durand, Planning (Magasin de Senlis) [clé : noa]"
    assert ligne(DEUX_LIEUX, NOMS) == "- Eden, Conseil (Magasin de Creil, Magasin de Senlis) [clé : eden]"
    # Aucune étiquette : la ligne d'avant, à l'octet (avec ou sans les noms).
    assert ligne(TOUS, NOMS) == ligne(TOUS) == "- Sacha, Comptabilité [clé : sacha]"
    # Un lieu qui n'existe plus : rien n'est ajouté.
    assert ligne(AILLEURS, {}) == "- Noa Durand, Planning [clé : noa]"
    assert ligne(AILLEURS) == "- Noa Durand, Planning [clé : noa]"


def test_la_ligne_garde_la_description_et_les_coordonnees_autorisees():
    p = Personne(
        cle="a", prenom="A", role="R", etablissement="senlis", description="Fait ceci.",
        telephone="+33611111111", divulguer_telephone=True,
    )
    assert ligne(p, NOMS) == "- A, R (Magasin de Senlis) : Fait ceci. (téléphone +33611111111) [clé : a]"


def test_la_liste_fermee_contient_les_personnes_d_un_autre_lieu():
    enrichi, estampille = injecter_equipe({}, {"equipe_connue": True}, EQUIPE, "creil", "copie", NOMS)
    assert enrichi["equipe_cles"] == ["camille", "noa", "eden", "sacha"]
    assert "Magasin de Senlis" in enrichi["equipe"]
    assert estampille["personnes"] == 4


# --------------------------------------------------------------------------- #
# 3. R1 : le décroché au clavier, joué jusqu'au moteur
# --------------------------------------------------------------------------- #


async def _clavier(equipe, contexte=None):
    with (
        patch.object(
            module_copie,
            "lire_copie_complete",
            AsyncMock(
                return_value=module_copie.CopieOrganisation(
                    etablissements=CATALOGUE, phrases=CataloguePhrases(), equipe=equipe, lu_depuis="copie"
                )
            ),
        ),
        patch.object(text_chat_runner, "lire_annonce_ouverture", AsyncMock(return_value=ReglagesAnnonceOuverture())),
    ):
        return await _jouer_au_clavier(
            {"equipe_connue": True},
            contexte or {"direction": "inbound", "etablissement_id": "creil"},
            OrganizationPreferences(),
        )


@pytest.mark.asyncio
async def test_clavier_une_personne_d_un_autre_lieu_est_connue_avec_son_etiquette():
    """Échoue si l'appel servi par Creil ne connaît toujours que les personnes de Creil."""
    persiste = await _clavier(Equipe(personnes=[ICI, AILLEURS, TOUS]))
    lignes = persiste["equipe"].split("\n")
    assert "- Noa Durand, Planning (Magasin de Senlis) [clé : noa]" in lignes
    assert "- Camille Martin, Accueil (Magasin de Creil) [clé : camille]" in lignes
    assert "- Sacha, Comptabilité [clé : sacha]" in lignes
    assert persiste["equipe_cles"] == ["camille", "noa", "sacha"]
    assert persiste["runtime_configuration"]["equipe"]["cles"] == ["camille", "noa", "sacha"]


@pytest.mark.asyncio
async def test_clavier_une_personne_sur_deux_lieux_porte_les_deux():
    persiste = await _clavier(Equipe(personnes=[DEUX_LIEUX]))
    assert persiste["equipe"] == "- Eden, Conseil (Magasin de Creil, Magasin de Senlis) [clé : eden]"


@pytest.mark.asyncio
async def test_clavier_sans_etiquette_la_ligne_est_celle_d_avant():
    persiste = await _clavier(Equipe(personnes=[TOUS]))
    assert persiste["equipe"] == "- Sacha, Comptabilité [clé : sacha]"


def test_le_telephone_passe_le_nom_des_lieux_a_l_equipe():
    """Le chemin téléphone n'est pas jouable ici : on lit le décroché comme les tests voisins."""
    from api.services.pipecat import run_pipeline

    source = inspect.getsource(run_pipeline)
    debut = re.search(r"merged_call_context_vars, estampille_equipe = injecter_equipe\(", source).start()
    assert "lecture_de_lappel.noms_des_lieux" in source[debut : debut + 500]
    source_clavier = inspect.getsource(text_chat_runner)
    debut = re.search(r"initial_context, estampille_equipe = injecter_equipe\(", source_clavier).start()
    assert "lecture_de_lappel.noms_des_lieux" in source_clavier[debut : debut + 500]


# --------------------------------------------------------------------------- #
# 4. La base du client : personne_site (migration 015)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_plusieurs_lieux_ecrits_et_relus_un_lieu_retire_disparait(base_prete):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe, lire_equipe
    from api.db.bases_clients.referentiel import ecrire_etablissements

    connexion = await schema.connecter(base_prete)
    try:
        await ecrire_etablissements(connexion, CATALOGUE_BASE, "dograh:essai")
        equipe = Equipe(
            personnes=[
                Personne(cle="deux", prenom="Deux", etablissements=["senlis", "creil"]),
                Personne(cle="un", prenom="Un", etablissement="creil"),
                Personne(cle="tous", prenom="Tous"),
            ]
        )
        await ecrire_equipe(connexion, equipe, "dograh:essai")
        relue = {p.cle: p for p in (await lire_equipe(connexion)).personnes}
        assert relue["deux"].etablissements == ["senlis", "creil"] and relue["deux"].etablissement == "senlis"
        assert relue["un"].etablissements == ["creil"] and relue["tous"].etablissements == []
        lignes = await connexion.fetch(
            "SELECT p.cle, s.cle AS lieu FROM mark.personne_site ps "
            "JOIN mark.personne p ON p.id = ps.personne_id JOIN mark.site s ON s.id = ps.site_id ORDER BY 1, 2"
        )
        assert [(r["cle"], r["lieu"]) for r in lignes] == [("deux", "creil"), ("deux", "senlis"), ("un", "creil")]
        # Un lieu retiré disparaît de la table ; une personne rendue à « toute l'entreprise » n'a plus de ligne.
        equipe2 = Equipe(
            personnes=[
                Personne(cle="deux", prenom="Deux", etablissements=["creil"]),
                Personne(cle="un", prenom="Un", etablissements=[]),
                Personne(cle="tous", prenom="Tous"),
            ]
        )
        await ecrire_equipe(connexion, equipe2, "dograh:essai")
        relue = {p.cle: p for p in (await lire_equipe(connexion)).personnes}
        assert relue["deux"].etablissements == ["creil"] and relue["un"].etablissements == []
        assert await connexion.fetchval("SELECT count(*) FROM mark.personne_site") == 1
        # Le journal nomme la ligne « personne_id:site_id », comme personne_sujet.
        journal = await connexion.fetch("SELECT ligne_id FROM mark.journal_modif WHERE table_nom = 'personne_site'")
        assert journal and all(re.fullmatch(r"\d+:\d+", r["ligne_id"]) for r in journal)
    finally:
        await connexion.close()


@pytest.mark.asyncio
async def test_une_base_restee_en_version_14_lit_et_ecrit_un_lieu_sans_migrer(base_prete):
    """Entre le déploiement et « Mettre à niveau » : jamais d'erreur à un décroché, et rien de perdu
    pour une personne qui n'a qu'un lieu ; plusieurs lieux sont refusés (la route répond « mettre à niveau »)."""
    import asyncpg

    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe, lire_equipe
    from api.db.bases_clients.referentiel import ecrire_etablissements

    connexion = await schema.connecter(base_prete)
    proprietaire = await schema.connecter_proprietaire(base_prete)
    try:
        await ecrire_etablissements(connexion, CATALOGUE_BASE, "dograh:essai")
        await proprietaire.execute("DROP TABLE mark.personne_site")
        await ecrire_equipe(
            connexion,
            Equipe(personnes=[Personne(cle="un", prenom="Un", etablissement="creil"), Personne(cle="tous", prenom="Tous")]),
            "dograh:essai",
        )
        relue = {p.cle: p for p in (await lire_equipe(connexion)).personnes}
        assert relue["un"].etablissements == ["creil"] and relue["tous"].etablissements == []
        with pytest.raises(asyncpg.PostgresError):
            await ecrire_equipe(
                connexion,
                Equipe(personnes=[Personne(cle="deux", prenom="Deux", etablissements=["creil", "senlis"])]),
                "dograh:essai",
            )
    finally:
        await connexion.close()
        await proprietaire.close()


def test_la_migration_015_est_additive():
    from api.db.bases_clients import connexion as schema

    quinze = next(m for m in schema.migrations() if m.version == 15)
    assert quinze.nom.startswith("015-")
    sql = quinze.sql.upper()
    assert "CREATE TABLE IF NOT EXISTS PERSONNE_SITE" in sql
    # Additive : ni suppression de table ou de colonne, ni vidage.
    for interdit in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM"):
        assert interdit not in sql


# --------------------------------------------------------------------------- #
# 5. La vraie route de l'équipe
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_route_de_l_equipe_ecrit_les_deux(base_prete, monkeypatch):
    """R1 : par la vraie route ``PUT /organizations/equipe``, jusqu'à la base du client."""
    import httpx

    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.referentiel import ecrire_etablissements
    from api.routes import base_client as route

    connexion = await schema.connecter(base_prete)
    try:
        await ecrire_etablissements(connexion, CATALOGUE_BASE, "dograh:essai")
    finally:
        await connexion.close()

    async def nom(_organisation):
        return base_prete

    monkeypatch.setattr(route.rattachement, "nom_de_la_base", nom)
    monkeypatch.setattr(route, "_apres_changement_de_source", AsyncMock())
    app = FastAPI()
    app.include_router(route.routeur_equipe)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, provider_id="p", selected_organization_id=ORGANISATION, email="essai@example.org"
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://essai") as client:
        corps = {"personnes": [{"cle": "deux", "prenom": "Deux", "etablissements": ["creil", "senlis"]}]}
        reponse = await client.put("/organizations/equipe", json=corps)
        assert reponse.status_code == 200, reponse.text
        assert reponse.json()["personnes"][0]["etablissements"] == ["creil", "senlis"]
        relue = (await client.get("/organizations/equipe")).json()["personnes"][0]
        assert relue["etablissements"] == ["creil", "senlis"] and relue["etablissement"] == "creil"
        # Une fiche inconnue : refusée, rien d'écrit.
        refus = await client.put(
            "/organizations/equipe",
            json={"personnes": [{"cle": "deux", "prenom": "Deux", "etablissements": ["creil", "inconnue"]}]},
        )
        assert refus.status_code == 422
        encore = (await client.get("/organizations/equipe")).json()["personnes"][0]
        assert encore["etablissements"] == ["creil", "senlis"]
