"""RA-A, R2 (a) (audit du 04/11, rouge n° 7) : écrire un modèle de réglages est un geste de l'équipe, au Labo.

Les cinq routes d'écriture de ``routes/modeles_reglages.py`` (POST ``""``, ``/import``, PATCH, DELETE,
``/appliquer``) n'exigeaient aucun droit d'équipe : un compte client avec ``agents.modifier`` pouvait
écrire. La lecture reste ouverte (décision 10 : les modèles sont l'outil de .mark).
"""

from __future__ import annotations

import pytest

from api.db import db_client
from api.services.equipe_mark.registre_routes import Permission, decision_de
from api.services.modeles_reglages import service
from api.tests.mark.test_modeles_de_reglages import ROUTE, monde  # noqa: F401

CHEMIN = "/organizations/modeles-de-reglages"
ECRITURES = (
    ("POST", CHEMIN),
    ("POST", f"{CHEMIN}/import"),
    ("PATCH", f"{CHEMIN}/x"),
    ("DELETE", f"{CHEMIN}/x"),
    ("POST", f"{CHEMIN}/x/appliquer"),
)


@pytest.fixture
async def equipe_au_labo(monde):  # noqa: F811
    """Le compte A est de l'équipe .mark, dans le Labo (l'organisation A) ; le compte B est un client."""
    await db_client.add_user_to_organization(monde.user_a.id, monde.org_a.id)
    return monde


def test_le_registre_demande_une_permission_d_equipe_pour_les_cinq_ecritures():
    for methode, chemin in ECRITURES:
        decision, _ = decision_de(methode, chemin)
        assert isinstance(decision, Permission) and decision.cle == "atelier.regler", (methode, chemin, decision)


def test_la_lecture_reste_ouverte_a_tout_membre():
    decision, _ = decision_de("GET", CHEMIN)
    assert not isinstance(decision, Permission)


async def _corps(client, monde, ecritures_du_client):  # noqa: F811
    """Un modèle dans le stock du client B (posé sans passer par la route), et son fichier."""
    modele = await service.creer_un_modele(monde.org_b.id, "Modele du client", monde.agent_b.id, "test")
    fichier = service.fichier_du_modele(service.trouver(await service.lire_le_stock(monde.org_b.id), modele.id))
    return modele, fichier.model_dump(mode="json")


@pytest.mark.asyncio
async def test_un_compte_client_est_refuse_sur_les_cinq_ecritures(equipe_au_labo, test_client_factory):
    monde = equipe_au_labo
    modele, fichier = await _corps(None, monde, None)
    fichier["nom"] = "Importe par un client"
    async with test_client_factory(monde.user_b) as client:
        reponses = {
            "POST": await client.post(ROUTE, json={"nom": "Pirate", "workflow_id": monde.agent_b.id}),
            "import": await client.post(f"{ROUTE}/import", json=fichier),
            "PATCH": await client.patch(f"{ROUTE}/{modele.id}", json={"nom": "Renomme"}),
            "appliquer": await client.post(
                f"{ROUTE}/{modele.id}/appliquer",
                json={"workflow_id": monde.agent_b2.id, "sections": ["tour"], "a_blanc": False},
            ),
            "DELETE": await client.delete(f"{ROUTE}/{modele.id}"),
        }
        lecture = await client.get(ROUTE)
    assert {k: r.status_code for k, r in reponses.items()} == dict.fromkeys(reponses, 403), {
        k: r.text[:120] for k, r in reponses.items()
    }
    assert lecture.status_code == 200  # la lecture reste ouverte


@pytest.mark.asyncio
async def test_l_equipe_au_labo_ecrit_les_cinq(equipe_au_labo, test_client_factory):
    monde = equipe_au_labo
    async with test_client_factory(monde.user_a) as client:
        cree = await client.post(ROUTE, json={"nom": "Modele equipe", "workflow_id": monde.agent_a.id})
        assert cree.status_code == 200, cree.text
        identifiant = cree.json()["id"]
        fichier = (await client.get(f"{ROUTE}/{identifiant}/export")).json()
        fichier["nom"] = "Modele importe"
        importe = await client.post(f"{ROUTE}/import", json=fichier)
        renomme = await client.patch(f"{ROUTE}/{identifiant}", json={"nom": "Modele renomme"})
        applique = await client.post(
            f"{ROUTE}/{identifiant}/appliquer",
            json={"workflow_id": monde.agent_a2.id, "sections": ["tour"], "a_blanc": False},
        )
        supprime = await client.delete(f"{ROUTE}/{identifiant}")
    assert (importe.status_code, renomme.status_code, applique.status_code, supprime.status_code) == (200, 200, 200, 204), (
        importe.text, renomme.text, applique.text
    )
