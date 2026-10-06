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
from api.routes import credentials as route_amont
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.schemas.appel_simule import ReglagesAppelantSimule, RoleSimule, VoixSimulee
from api.services import bibliotheque_cles as bibliotheque
from api.services import cles_reference
from api.services.appel_simule import reglages as stockage
from api.services.appel_simule import serie as moteur
from api.services.appel_simule.serie import SerieRefusee
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.configuration import ai_model_configuration as configuration_modeles
from api.services.configuration.check_validity import UserConfigurationValidator
from api.services.configuration.masking import mask_key
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
            description=None,
            credential_type="bearer_token",
            credential_data=donnees,
            created_at=datetime(2026, 10, 6, tzinfo=UTC),
            updated_at=None,
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
        patch.object(route_amont, "db_client", db),
        patch.object(bibliotheque, "db_client", db),
        patch.object(stockage, "db_client", db),
        patch.object(moteur, "db_client", db),
        patch("api.db.db_client", db),
        patch.object(
            bibliotheque,
            "get_organization_ai_model_configuration_v2",
            AsyncMock(return_value=None),
        ) as modeles_organisation,
    ):
        yield SimpleNamespace(db=db, coffre=coffre, modeles=modeles_organisation)


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
        "/cles", json={"fournisseur": "inconnu", "nom": "X", "cle": "12345678"}
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


@pytest.fixture
def ecran_amont(base):
    app = FastAPI()
    app.include_router(route_amont.router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=3, selected_organization_id=ORG
    )
    return TestClient(app)


def test_les_ecrans_http_de_dograh_ne_voient_ni_ne_touchent_une_cle_de_la_bibliotheque(
    ecran_amont, base
):
    # Décision d'Evan, 06/10 : une clé de la bibliothèque se gère dans « Keys » seulement.
    assert [c["uuid"] for c in ecran_amont.get("/credentials/").json()] == [
        "outil-http"
    ]
    for requete in (
        lambda: ecran_amont.get("/credentials/cle-mistral"),
        lambda: ecran_amont.put("/credentials/cle-mistral", json={"name": "Renommée"}),
        lambda: ecran_amont.delete("/credentials/cle-mistral"),
    ):
        reponse = requete()
        assert reponse.status_code == 409
        assert "managed in « Keys »" in reponse.json()["detail"]
    assert base.coffre.lignes["cle-mistral"].is_active
    assert base.coffre.lignes["cle-mistral"].name == "Mistral org 2"
    # R7 : un identifiant HTTP ordinaire reste lisible et supprimable par Dograh.
    assert ecran_amont.get("/credentials/outil-http").status_code == 200
    assert ecran_amont.delete("/credentials/outil-http").status_code == 200


# --- Lot 0 bis : la bibliothèque dans « Models » et les réglages de modèle d'un agent ------------


def _configuration(llm_cle, tts_cles):
    return EffectiveAIModelConfiguration.model_validate(
        {
            "llm": {
                "provider": "mistral",
                "model": "mistral-small-latest",
                "api_key": llm_cle,
            },
            "tts": {
                "provider": "elevenlabs",
                "model": "eleven_flash_v2_5",
                "voice": "v",
                "api_key": tts_cles,
            },
        }
    )


def test_les_fournisseurs_sont_ceux_de_models(ecran):
    fournisseurs = ecran.get("/cles/fournisseurs").json()
    assert {"mistral", "elevenlabs", "openai", "deepgram", "cartesia"} <= set(
        fournisseurs
    )
    assert (
        ecran.post(
            "/cles",
            json={"fournisseur": "openai", "nom": "OpenAI", "cle": "sk-12345678"},
        ).status_code
        == 201
    )


def test_une_reference_se_remplace_par_la_cle_et_une_cle_tapee_reste(base):
    configuration = _configuration(
        "mark-cle:cle-mistral", ["mark-cle:cle-eleven", "cle-tapee-a-la-main"]
    )
    resolue = executer(
        cles_reference.resoudre_les_cles(configuration, ORG, strict=True)
    )
    assert resolue.llm.api_key == "SECRET-M"
    assert resolue.tts.get_all_api_keys() == ["SECRET-E", "cle-tapee-a-la-main"]
    # La configuration lue n'est pas modifiée : l'écran garde la référence.
    assert configuration.llm.api_key == "mark-cle:cle-mistral"


def test_une_configuration_sans_reference_ne_lit_pas_la_base(base):
    configuration = _configuration("cle-tapee", "autre-cle-tapee")
    base.db.get_credential_by_uuid = AsyncMock(side_effect=AssertionError("lue"))
    assert (
        executer(cles_reference.resoudre_les_cles(configuration, ORG, strict=True))
        is configuration
    )


def test_une_reference_introuvable_refuse_l_enregistrement_et_ne_se_tait_pas_a_l_appel(
    base,
):
    # R7 : la clé d'une autre organisation et une clé d'outil HTTP ne se résolvent pas.
    for uuid in ("cle-autre-org", "outil-http", "jamais-vue"):
        configuration = _configuration(f"mark-cle:{uuid}", "cle-tapee")
        with pytest.raises(cles_reference.CleIntrouvable, match="llm key .* deleted"):
            executer(cles_reference.resoudre_les_cles(configuration, ORG, strict=True))
        with patch.object(cles_reference.logger, "error") as erreur:
            resolue = executer(
                cles_reference.resoudre_les_cles(configuration, ORG, strict=False)
            )
        assert resolue.llm.api_key == f"mark-cle:{uuid}"
        assert "[.mark]" in erreur.call_args.args[0]


def test_l_appel_lit_la_cle_et_la_validation_aussi(base):
    configuration = _configuration("mark-cle:cle-mistral", "cle-tapee")
    with patch.object(
        configuration_modeles,
        "_effective_for_workflow",
        AsyncMock(return_value=configuration),
    ):
        effective = executer(
            configuration_modeles.get_effective_ai_model_configuration_for_workflow(
                organization_id=ORG, workflow_configurations={}
            )
        )
    assert effective.llm.api_key == "SECRET-M"

    vues = []
    validateur = UserConfigurationValidator()

    def relever(service, *args, **kwargs):
        if service is not None:
            vues.append(service.__dict__.get("api_key"))
        return []

    validateur._validate_service = relever
    executer(validateur.validate(configuration, organization_id=ORG))
    assert vues[0] == "SECRET-M"
    with pytest.raises(ValueError, match="deleted"):
        executer(
            validateur.validate(
                _configuration("mark-cle:jamais-vue", "x"), organization_id=ORG
            )
        )


def test_une_reference_n_est_pas_masquee_une_cle_si():
    assert mask_key("mark-cle:cle-mistral") == "mark-cle:cle-mistral"
    assert "SECRET" not in mask_key("SECRET-MISTRAL-1234")


def test_les_usages_comptent_models_et_les_reglages_de_modele_des_agents(ecran, base):
    base.modeles.return_value = SimpleNamespace(
        model_dump_json=lambda: '{"llm": {"api_key": "mark-cle:cle-mistral"}}'
    )
    base.db.get_all_workflows.return_value = [
        SimpleNamespace(
            name="essai_ndf",
            current_definition=SimpleNamespace(
                workflow_json={},
                workflow_configurations={
                    "model_overrides": {"tts": {"api_key": "mark-cle:cle-eleven"}}
                },
            ),
            workflow_configurations=None,
        )
    ]
    assert ecran.get("/cles/cle-mistral/usages").json() == [
        {"ou": "modeles_organisation", "nom": None}
    ]
    assert ecran.get("/cles/cle-eleven/usages").json() == [
        {"ou": "modeles_agent", "nom": "essai_ndf"}
    ]


def test_une_cle_d_un_autre_fournisseur_ne_part_jamais(base):
    # Revue du lot 0 bis : la clé Mistral posée sur la voix ElevenLabs.
    configuration = _configuration("cle-tapee", "mark-cle:cle-mistral")
    with pytest.raises(cles_reference.CleIntrouvable, match="is a mistral key"):
        executer(cles_reference.resoudre_les_cles(configuration, ORG, strict=True))
    with patch.object(cles_reference.logger, "error"):
        resolue = executer(
            cles_reference.resoudre_les_cles(configuration, ORG, strict=False)
        )
    assert "SECRET" not in str(resolue.tts.get_all_api_keys())


def test_une_cle_se_propose_a_toute_sa_famille_de_fournisseurs(ecran):
    uuid = ecran.post(
        "/cles", json={"fournisseur": "openai", "nom": "OpenAI", "cle": "sk-12345678"}
    ).json()["uuid"]
    assert [
        c["uuid"] for c in ecran.get("/cles?fournisseur=openai_realtime").json()
    ] == [uuid]
    assert ecran.get("/cles?fournisseur=mistral").json()[0]["uuid"] == "cle-mistral"
    assert cles_reference.famille("openai_realtime") == cles_reference.famille("openai")


def test_la_cle_propre_du_greffier_ne_peut_pas_etre_une_reference():
    from api.services.pipecat.greffier import configuration_du_greffier

    with pytest.raises(ValueError, match="scribe's own key"):
        configuration_du_greffier(
            _configuration("SECRET-M", "x"), {"api_key": "mark-cle:cle-mistral"}
        )
