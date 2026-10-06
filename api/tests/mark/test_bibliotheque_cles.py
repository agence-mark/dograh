"""[.mark] La bibliothèque de clés (chantier direct-et-passe-muette, lot 0, P15, P16).

Ce qui doit tenir : une clé ajoutée est rangée dans le coffre de Dograh avec son fournisseur, et
jamais renvoyée ; la liste ne montre que les clés de la bibliothèque de l'organisation ; un
identifiant d'outil HTTP ou d'une autre organisation ne se supprime pas par la bibliothèque ;
une suppression dit où la clé servait ; une série dont la clé a été supprimée est refusée en le
disant ; un nom libéré par une suppression se réutilise (la base garde l'unicité sur les lignes
supprimées : le faux coffre aussi, sinon il masquerait le défaut) ; une clé mal saisie n'est pas
renvoyée dans l'erreur ; un réglage qui désigne un identifiant d'avant la bibliothèque ne se dit pas
« supprimé ».
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from api.routes import cles as route
from api.schemas.appel_simule import ReglagesAppelantSimule, RoleSimule, VoixSimulee
from api.services import bibliotheque_cles as bibliotheque
from api.services.appel_simule import reglages as stockage
from api.services.appel_simule import serie as moteur
from api.services.appel_simule.serie import SerieRefusee
from api.services.auth.depends import get_user_with_selected_organization
from api.tests.mark.boucle_isolee import (
    executer_sans_toucher_la_boucle_courante as executer,
)

ORG = 7
AUTRE_ORG = 8


class Coffre:
    """``external_credentials`` en mémoire, avec la suppression douce de Dograh et sa contrainte
    ``unique_org_credential_name`` qui porte AUSSI sur les lignes supprimées."""

    def __init__(self):
        self.lignes: dict[str, SimpleNamespace] = {}

    def poser(self, uuid, org, nom, donnees):
        self.lignes[uuid] = SimpleNamespace(
            credential_uuid=uuid,
            organization_id=org,
            name=nom,
            credential_type="bearer_token",
            credential_data=donnees,
            created_at=datetime(2026, 10, 6, tzinfo=UTC),
            is_active=True,
        )

    async def create_credential(
        self, organization_id, user_id, name, credential_type, credential_data
    ):
        if any(
            l.organization_id == organization_id and l.name == name
            for l in self.lignes.values()
        ):
            raise IntegrityError("INSERT", {}, Exception("unique_org_credential_name"))
        uuid = f"nouvelle-{len(self.lignes)}"
        self.poser(uuid, organization_id, name, credential_data)
        self.lignes[uuid].credential_type = credential_type
        return self.lignes[uuid]

    async def get_credentials_for_organization(self, organization_id):
        return [
            l
            for l in self.lignes.values()
            if l.organization_id == organization_id and l.is_active
        ]

    async def get_credential_by_uuid(self, uuid, organization_id):
        ligne = self.lignes.get(uuid)
        if ligne and ligne.organization_id == organization_id and ligne.is_active:
            return ligne
        return None

    async def update_credential(self, uuid, organization_id, name=None):
        ligne = await self.get_credential_by_uuid(uuid, organization_id)
        if ligne is not None and name is not None:
            ligne.name = name
        return ligne

    async def delete_credential(self, uuid, organization_id):
        ligne = await self.get_credential_by_uuid(uuid, organization_id)
        if ligne is None:
            return False
        ligne.is_active = False
        return True


class Configurations:
    def __init__(self):
        self.lignes: dict[tuple[int, str], dict] = {}

    async def get_configuration(self, org, cle):
        valeur = self.lignes.get((org, cle))
        return None if valeur is None else SimpleNamespace(value=valeur)

    async def upsert_configuration(self, org, cle, valeur):
        self.lignes[(org, cle)] = valeur


@pytest.fixture
def base():
    coffre = Coffre()
    coffre.poser(
        "cle-mistral",
        ORG,
        "Mistral org 2",
        bibliotheque.donnees_d_une_cle("mistral", "SECRET-M"),
    )
    coffre.poser(
        "cle-eleven",
        ORG,
        "ElevenLabs",
        bibliotheque.donnees_d_une_cle("elevenlabs", "SECRET-E"),
    )
    coffre.poser(
        "outil-http", ORG, "CRM", {"header_name": "X-Key", "api_key": "SECRET-CRM"}
    )
    coffre.poser(
        "cle-autre-org",
        AUTRE_ORG,
        "Mistral voisin",
        bibliotheque.donnees_d_une_cle("mistral", "SECRET-V"),
    )
    configurations = Configurations()
    db = MagicMock()
    for nom in (
        "create_credential",
        "get_credentials_for_organization",
        "get_credential_by_uuid",
        "update_credential",
        "delete_credential",
    ):
        setattr(db, nom, getattr(coffre, nom))
    db.get_configuration = configurations.get_configuration
    db.upsert_configuration = configurations.upsert_configuration
    db.get_tools_for_organization = AsyncMock(return_value=[])
    db.get_all_workflows = AsyncMock(return_value=[])
    with (
        patch.object(route, "db_client", db),
        patch.object(bibliotheque, "db_client", db),
        patch.object(stockage, "db_client", db),
        patch.object(moteur, "db_client", db),
    ):
        yield SimpleNamespace(db=db, coffre=coffre)


@pytest.fixture
def ecran(base):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: (
        SimpleNamespace(id=3, selected_organization_id=ORG)
    )
    return TestClient(app)


def _reglages():
    return ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="Appelant.", identifiant="cle-mistral"),
        juge=RoleSimule(consigne="Juge.", identifiant="cle-mistral"),
        voix=VoixSimulee(voix="voix-fr", identifiant="cle-eleven"),
    )


def test_une_cle_ajoutee_est_rangee_avec_son_fournisseur_et_jamais_renvoyee(
    ecran, base
):
    reponse = ecran.post(
        "/cles",
        json={
            "fournisseur": "mistral",
            "nom": " Mistral org 3 ",
            "cle": " SECRET-NEUF ",
        },
    )
    assert reponse.status_code == 201
    corps = reponse.json()
    assert corps["nom"] == "Mistral org 3" and corps["fournisseur"] == "mistral"
    assert "SECRET" not in str(corps)
    rangee = base.coffre.lignes[corps["uuid"]]
    assert rangee.organization_id == ORG
    assert rangee.credential_type == "bearer_token"
    assert rangee.credential_data["token"] == "SECRET-NEUF"
    assert "SECRET" not in str(ecran.get("/cles").json())


def test_la_cle_ajoutee_se_lit_par_l_appelant_simule(ecran, base):
    uuid = ecran.post(
        "/cles", json={"fournisseur": "elevenlabs", "nom": "Voix", "cle": "SECRET-VOIX"}
    ).json()["uuid"]

    async def lire():
        return await moteur.cle_d_identifiant(ORG, uuid)

    assert executer(lire()) == "SECRET-VOIX"


def test_un_nom_deja_pris_et_un_fournisseur_inconnu_sont_refuses(ecran):
    pris = ecran.post(
        "/cles",
        json={"fournisseur": "mistral", "nom": "Mistral org 2", "cle": "12345678"},
    )
    assert pris.status_code == 409 and "already exists" in pris.json()["detail"]
    inconnu = ecran.post(
        "/cles", json={"fournisseur": "openai", "nom": "X", "cle": "12345678"}
    )
    assert inconnu.status_code == 422
    vide = ecran.post(
        "/cles", json={"fournisseur": "mistral", "nom": "Y", "cle": "        "}
    )
    assert vide.status_code == 422


def test_la_liste_ne_montre_que_la_bibliotheque_de_l_organisation(ecran):
    toutes = ecran.get("/cles").json()
    assert [c["uuid"] for c in toutes] == ["cle-eleven", "cle-mistral"]
    assert [c["uuid"] for c in ecran.get("/cles?fournisseur=mistral").json()] == [
        "cle-mistral"
    ]


def test_un_identifiant_hors_bibliotheque_ou_d_une_autre_organisation_ne_se_supprime_pas(
    ecran, base
):
    # R7 : la garde rougit sur les deux cas construits, et la ligne reste intacte.
    assert ecran.delete("/cles/outil-http").status_code == 404
    assert ecran.delete("/cles/cle-autre-org").status_code == 404
    assert ecran.get("/cles/cle-autre-org/usages").status_code == 404
    assert base.coffre.lignes["outil-http"].is_active
    assert base.coffre.lignes["cle-autre-org"].is_active


def test_une_suppression_dit_ou_la_cle_servait(ecran, base):
    executer(stockage.enregistrer_reglages(ORG, _reglages()))
    base.db.get_tools_for_organization.return_value = [
        SimpleNamespace(
            name="Envoyer le SMS",
            definition={"config": {"credential_uuid": "cle-eleven"}},
        ),
        SimpleNamespace(name="Autre", definition={"config": {}}),
    ]
    base.db.get_all_workflows.return_value = [
        SimpleNamespace(
            name="essai_ndf",
            current_definition=SimpleNamespace(
                workflow_json={
                    "nodes": [
                        {"data": {"pre_call_fetch_credential_uuid": "cle-mistral"}}
                    ]
                }
            ),
        ),
        SimpleNamespace(name="sans version", current_definition=None),
    ]
    assert ecran.get("/cles/cle-mistral/usages").json() == [
        {"ou": "reglages_modele", "nom": None},
        {"ou": "agent", "nom": "essai_ndf"},
    ]
    reponse = ecran.delete("/cles/cle-eleven")
    assert reponse.status_code == 200
    assert reponse.json()["usages"] == [
        {"ou": "reglages_voix", "nom": None},
        {"ou": "outil", "nom": "Envoyer le SMS"},
    ]
    assert not base.coffre.lignes["cle-eleven"].is_active
    assert [c["uuid"] for c in ecran.get("/cles").json()] == ["cle-mistral"]


def test_une_serie_dont_la_cle_a_ete_supprimee_est_refusee_en_le_disant(ecran, base):
    executer(stockage.enregistrer_reglages(ORG, _reglages()))
    executer(
        moteur._cles(ORG, _reglages())
    )  # les deux clés sont là : rien n'est refusé
    ecran.delete("/cles/cle-eleven")
    with pytest.raises(
        SerieRefusee, match="ElevenLabs key .* was deleted or is unusable"
    ):
        executer(moteur._cles(ORG, _reglages()))
    ecran.delete("/cles/cle-mistral")
    with pytest.raises(SerieRefusee, match="model key .* was deleted or is unusable"):
        executer(moteur._cles(ORG, _reglages()))
    sans_choix = _reglages()
    sans_choix.appelant.identifiant = sans_choix.juge.identifiant = None
    with pytest.raises(SerieRefusee, match="Choose the model key"):
        executer(moteur._cles(ORG, sans_choix))


def test_une_cle_supprimee_libere_son_nom(ecran, base):
    # R7 : sans le changement de nom avant la suppression, le faux coffre (comme la base) renvoie 409.
    assert ecran.delete("/cles/cle-mistral").status_code == 200
    assert base.coffre.lignes["cle-mistral"].name.startswith("Mistral org 2 · deleted ")
    remplacee = ecran.post(
        "/cles",
        json={
            "fournisseur": "mistral",
            "nom": "Mistral org 2",
            "cle": "SECRET-NOUVELLE",
        },
    )
    assert remplacee.status_code == 201
    assert [c["nom"] for c in ecran.get("/cles?fournisseur=mistral").json()] == [
        "Mistral org 2"
    ]


def test_un_nom_pris_par_un_identifiant_supprime_hors_bibliotheque_dit_409(ecran, base):
    base.coffre.poser("vieux", ORG, "Ancien", {"token": "x"})
    base.coffre.lignes["vieux"].is_active = False
    reponse = ecran.post(
        "/cles", json={"fournisseur": "mistral", "nom": "Ancien", "cle": "12345678"}
    )
    assert reponse.status_code == 409


def test_une_cle_mal_saisie_n_est_pas_renvoyee_dans_l_erreur(ecran):
    for cle in ("COURTE", "        ", "X" * 501):
        reponse = ecran.post(
            "/cles", json={"fournisseur": "mistral", "nom": "N", "cle": cle}
        )
        assert reponse.status_code == 422
        assert "8 to 500" in reponse.json()["detail"]
        if cle.strip():
            assert cle not in reponse.text


def test_ce_que_designe_un_reglage(ecran):
    assert ecran.get("/cles/designee/cle-mistral").json() == {
        "etat": "bibliotheque",
        "nom": "Mistral org 2",
    }
    # Un identifiant d'avant la bibliothèque marche toujours : il ne se dit pas « supprimé ».
    assert ecran.get("/cles/designee/outil-http").json() == {
        "etat": "hors_bibliotheque",
        "nom": "CRM",
    }
    assert ecran.get("/cles/designee/cle-autre-org").json()["etat"] == "supprimee"
    ecran.delete("/cles/cle-eleven")
    assert ecran.get("/cles/designee/cle-eleven").json()["etat"] == "supprimee"
