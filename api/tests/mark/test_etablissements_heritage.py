"""[.mark] Non-regression test for the establishments and their inheritance.

The questions this file answers (chantier l-agent-travaille, L1, E1 to E4, B3):

    Does a call find ITS establishment from the called number, and read the
    hours, address and sentences of that establishment, the agent's own values
    first? Does an organization without establishments -- every client today --
    get back EXACTLY the call of before? Is the establishment stamped on the
    run? Does the save route refuse what a call would hear wrong, and keep a
    number of another organization out?

Why it exists
-------------
🔴 An inheritance that stops being applied fails in silence: the agent simply
announces the hours of the agent (or none) instead of the shop's. Only a test
that RUNS the keyboard path up to the engine sees it.

⚠️ What this file does NOT prove: that the screen shows the establishments
(``ui/src/components/mark/``).
"""

import inspect
import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.routes import etablissements as route_etablissements
from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture
from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.schemas.organization_preferences import OrganizationPreferences
from api.schemas.phrases import CataloguePhrases
from api.services.auth.depends import get_user_with_selected_organization
from api.services.etablissements import copie as module_copie
from api.services.etablissements import stockage as module_stockage
from api.services.etablissements.appel import (
    EtablissementDeLappel,
    LectureDeLappel,
    annonce_heritee,
    choisir_etablissement,
    configuration_heritee,
    etablissements_de_lagent,
    injecter_etablissement,
)
from api.services.pipecat import run_pipeline
from api.services.workflow import text_chat_runner
from api.tests.mark.test_adresse_etablissement import ORGANISATION, _jouer_au_clavier

SENLIS = {"code_postal": "60300", "code_insee": "60612", "commune": "Senlis"}
HORAIRES_CREIL = "\n".join(
    [f"{jour} : 9h-12h et 14h-18h" for jour in ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi")]
    + ["dimanche : fermé"]
)
HORAIRES_AGENT = HORAIRES_CREIL.replace("9h-12h et 14h-18h", "8h-20h")

CREIL = Etablissement(
    id="creil",
    nom="Magasin de Creil",
    numeros=["+33344000001"],
    numero_transfert="+33344000099",
    horaires_ouverture=HORAIRES_CREIL,
    adresse=SENLIS,
    annonce_fermeture="Le magasin de Creil est fermé[, nous rouvrons {reouverture}].",
)
SENLIS_SITE = Etablissement(id="senlis", nom="Magasin de Senlis", numeros=["+33344000002"])
SANS_NUMERO = Etablissement(id="a-rattacher", nom="Nouveau site")
CATALOGUE = CatalogueEtablissements(etablissements=[CREIL, SENLIS_SITE, SANS_NUMERO])


# --------------------------------------------------------------------------- #
# 1. The format
# --------------------------------------------------------------------------- #


def test_un_numero_ne_mene_qua_un_etablissement():
    with pytest.raises(ValidationError, match="one establishment only"):
        CatalogueEtablissements(
            etablissements=[
                Etablissement(id="a", nom="A", numeros=["+33344000001"]),
                Etablissement(id="b", nom="B", numeros=["+33 3 44 00 00 01"]),
            ]
        )


def test_identifiants_uniques_et_numeros_au_format_international():
    with pytest.raises(ValidationError, match="share the identifier"):
        CatalogueEtablissements(etablissements=[Etablissement(id="a", nom="A"), Etablissement(id="a", nom="B")])
    with pytest.raises(ValidationError, match="international format"):
        Etablissement(id="a", nom="A", numeros=["0344000001"])
    with pytest.raises(ValidationError):
        Etablissement(id="A B", nom="A")


def test_un_champ_vide_est_herite_jamais_rien():
    etablissement = Etablissement(id="a", nom="A", horaires_ouverture="  ", annonce_fermeture="", numero_transfert="")
    assert etablissement.horaires_ouverture is None
    assert etablissement.annonce_fermeture is None
    assert etablissement.numero_transfert is None


def test_une_phrase_mal_entendue_est_refusee():
    with pytest.raises(ValidationError, match="does not exist"):
        Etablissement(id="a", nom="A", annonce_fermeture="Fermé, retour {reouvertue}.")


# --------------------------------------------------------------------------- #
# 2. Which establishment (E3), pure
# --------------------------------------------------------------------------- #


def test_le_numero_appele_designe_letablissement():
    assert choisir_etablissement(CATALOGUE, {"called_number": "+33344000002"}) == (SENLIS_SITE, "numero_appele")


def test_un_numero_appele_hors_catalogue_ne_donne_aucun_etablissement():
    """⛔ Never « the first »: a number attached to no establishment is the call of before."""
    assert choisir_etablissement(CATALOGUE, {"called_number": "+33100000000"}) is None


def test_un_essai_prend_le_choix_puis_le_premier_de_lagent_puis_le_premier():
    assert choisir_etablissement(CATALOGUE, {"etablissement_id": "senlis"}) == (SENLIS_SITE, "essai")
    assert choisir_etablissement(CATALOGUE, {}, ["+33344000002"]) == (SENLIS_SITE, "premier_de_lagent")
    assert choisir_etablissement(CATALOGUE, {}) == (CREIL, "premier")
    assert choisir_etablissement(CATALOGUE, {"etablissement_id": "inconnu"}) == (CREIL, "premier")


def test_sans_etablissement_rien_nest_choisi():
    assert choisir_etablissement(CatalogueEtablissements(), {"called_number": "+33344000001"}) is None
    assert choisir_etablissement(CatalogueEtablissements(), {}) is None


# --------------------------------------------------------------------------- #
# 3. The inheritance (E2), pure
# --------------------------------------------------------------------------- #


def test_sans_etablissement_la_meme_configuration_revient():
    configs = {"horaires_ouverture": HORAIRES_AGENT}
    retour, origines = configuration_heritee(configs, None)
    assert retour is configs and origines == {}


def test_lagent_lemporte_puis_letablissement():
    retour, origines = configuration_heritee({"horaires_ouverture": HORAIRES_AGENT}, CREIL)
    assert retour["horaires_ouverture"] == HORAIRES_AGENT and origines["horaires_ouverture"] == "agent"
    retour, origines = configuration_heritee({}, CREIL)
    assert retour["horaires_ouverture"] == HORAIRES_CREIL and origines["horaires_ouverture"] == "etablissement"
    assert retour["adresse_etablissement"]["code_insee"] == "60612" and origines["adresse"] == "etablissement"
    retour, origines = configuration_heritee({}, SENLIS_SITE)
    assert "horaires_ouverture" not in retour and origines == {"horaires_ouverture": "aucune", "adresse": "organisation"}


def test_la_configuration_de_lagent_nest_jamais_modifiee():
    configs = {"max_call_duration": 300}
    configuration_heritee(configs, CREIL)
    assert configs == {"max_call_duration": 300}


def test_les_phrases_de_letablissement_remplacent_celles_de_lorganisation():
    organisation = ReglagesAnnonceOuverture(etat_force="FERME")
    retour = annonce_heritee(organisation, CREIL)
    assert retour.annonce_fermeture == CREIL.annonce_fermeture
    assert retour.annonce_pause == organisation.annonce_pause
    assert retour.etat_force == "FERME"
    assert annonce_heritee(organisation, SENLIS_SITE) is organisation
    assert annonce_heritee(organisation, None) is organisation


def test_le_nom_et_le_numero_de_transfert_sont_donnes_sans_ecraser():
    servi = EtablissementDeLappel(etablissement=CREIL, source="numero_appele", lu_depuis="copie")
    assert injecter_etablissement({}, servi) == {"etablissement": "Magasin de Creil", "numero_transfert": "+33344000099"}
    assert injecter_etablissement({"numero_transfert": "+33999"}, servi)["numero_transfert"] == "+33999"
    contexte = {"a": 1}
    assert injecter_etablissement(contexte, None) is contexte


# --------------------------------------------------------------------------- #
# 4. The in-memory copy (B3)
# --------------------------------------------------------------------------- #


class _RedisFactice:
    def __init__(self, valeurs=None, en_panne=False):
        self.valeurs = dict(valeurs or {})
        self.en_panne = en_panne

    async def get(self, cle):
        if self.en_panne:
            raise ConnectionError("redis down")
        return self.valeurs.get(cle)

    async def set(self, cle, valeur):
        if self.en_panne:
            raise ConnectionError("redis down")
        self.valeurs[cle] = valeur


@pytest.mark.asyncio
async def test_la_copie_est_lue_en_memoire_puis_reconstruite_si_absente():
    redis = _RedisFactice()
    with (
        patch.object(module_copie, "_redis", AsyncMock(return_value=redis)),
        patch.object(module_stockage, "lire_etablissements", AsyncMock(return_value=CATALOGUE)) as stockage,
        patch.object(module_stockage, "lire_phrases", AsyncMock(return_value=CataloguePhrases())),
    ):
        catalogue, origine = await module_copie.lire_copie(ORGANISATION)
        assert (catalogue, origine) == (CATALOGUE, "stockage")
        catalogue, origine = await module_copie.lire_copie(ORGANISATION)
        assert (catalogue, origine) == (CATALOGUE, "copie")
        assert stockage.await_count == 1


@pytest.mark.asyncio
async def test_redis_en_panne_le_stockage_prend_le_relais():
    with (
        patch.object(module_copie, "_redis", AsyncMock(return_value=_RedisFactice(en_panne=True))),
        patch.object(module_stockage, "lire_etablissements", AsyncMock(return_value=CATALOGUE)),
        patch.object(module_stockage, "lire_phrases", AsyncMock(return_value=CataloguePhrases())),
    ):
        assert await module_copie.lire_copie(ORGANISATION) == (CATALOGUE, "stockage")


@pytest.mark.asyncio
async def test_un_enregistrement_met_la_copie_a_jour_aussitot():
    redis = _RedisFactice()
    with (
        patch.object(module_copie, "_redis", AsyncMock(return_value=redis)),
        patch.object(module_stockage, "db_client") as base,
    ):
        base.upsert_configuration = AsyncMock()
        base.get_configuration = AsyncMock(
            side_effect=lambda _org, cle: SimpleNamespace(value=CATALOGUE.model_dump(mode="json"))
            if cle == "ETABLISSEMENTS"
            else None
        )
        await module_stockage.enregistrer_etablissements(ORGANISATION, CATALOGUE)
        assert await module_copie.lire_copie(ORGANISATION) == (CATALOGUE, "copie")


# --------------------------------------------------------------------------- #
# 5. The save route
# --------------------------------------------------------------------------- #


def _application(numeros=("+33344000001", "+33344000002")):
    app = FastAPI()
    app.include_router(route_etablissements.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, provider_id="p", selected_organization_id=ORGANISATION
    )
    lignes = [(n, None, None, None, True) for n in numeros]
    return app, lignes


def _put(corps, numeros=("+33344000001", "+33344000002")):
    app, lignes = _application(numeros)
    with (
        patch.object(route_etablissements, "db_client") as base,
        patch.object(route_etablissements, "enregistrer_etablissements", AsyncMock(side_effect=lambda _o, c, _auteur="dograh": c)) as ecrit,
        # No real database behind the route test (a TestClient runs on its own loop).
        patch.object(route_etablissements, "lire_phrases_strict", AsyncMock(return_value=CataloguePhrases())),
    ):
        base.lister_numeros_de_lorganisation = AsyncMock(return_value=lignes)
        reponse = TestClient(app).put("/organizations/etablissements", json=corps)
        return reponse, ecrit


def test_enregistrement_valide_relu_avec_le_nom_officiel():
    reponse, ecrit = _put(CATALOGUE.model_dump(mode="json"))
    assert reponse.status_code == 200, reponse.text
    assert ecrit.await_count == 1
    assert reponse.json()["etablissements"][0]["adresse"]["commune"] == "Senlis"


def test_des_horaires_illisibles_sont_refuses_sans_rien_ecrire():
    corps = {"etablissements": [{"id": "a", "nom": "A", "horaires_ouverture": "lundi : neuf heures"}]}
    reponse, ecrit = _put(corps)
    assert reponse.status_code == 422 and "A:" in reponse.text and "ligne 1" in reponse.text
    assert ecrit.await_count == 0


def test_un_numero_dune_autre_organisation_est_refuse():
    corps = {"etablissements": [{"id": "a", "nom": "A", "numeros": ["+33999000001"]}]}
    reponse, ecrit = _put(corps)
    assert reponse.status_code == 422 and "not a Telephony number of this organization" in reponse.text
    assert ecrit.await_count == 0


def test_une_commune_qui_ne_porte_pas_ce_code_est_refusee():
    corps = {"etablissements": [{"id": "a", "nom": "A", "adresse": {**SENLIS, "code_postal": "60740"}}]}
    reponse, ecrit = _put(corps)
    assert reponse.status_code == 422 and ecrit.await_count == 0


def test_la_lecture_de_lecran_refuse_une_ligne_illisible():
    app, _ = _application()
    with patch.object(route_etablissements, "lire_etablissements_strict", AsyncMock(side_effect=ValueError("x"))):
        assert TestClient(app).get("/organizations/etablissements").status_code == 500


def test_les_routes_figurent_dans_la_spec_publiee():
    from api.app import app

    chemins = app.openapi()["paths"]
    for chemin in ("", "/numeros", "/agent"):
        assert f"/api/v1/organizations/etablissements{chemin}" in chemins


# --------------------------------------------------------------------------- #
# 6. The agent's screen: the same resolution as the call (E8)
# --------------------------------------------------------------------------- #


def test_lecran_de_lagent_dit_dou_vient_chaque_valeur():
    vue = etablissements_de_lagent(
        CATALOGUE,
        ["+33344000001", "+33100000000"],
        {"horaires_ouverture": None},
        "60740 Saint-Maximin",
        ReglagesAnnonceOuverture(),
    )
    assert [e.id for e in vue.etablissements] == ["creil"]
    creil = vue.etablissements[0]
    assert (creil.horaires_ouverture.origine, creil.adresse.origine) == ("etablissement", "etablissement")
    assert creil.annonce_pause.origine == "organisation"
    assert vue.numeros_sans_etablissement == ["+33100000000"]
    vue = etablissements_de_lagent(CATALOGUE, ["+33344000002"], {"horaires_ouverture": HORAIRES_AGENT}, None, None)
    assert vue.etablissements[0].horaires_ouverture.origine == "agent"


# --------------------------------------------------------------------------- #
# 7. Branched: the keyboard path RUN up to the engine (R1), the phone path in order
# --------------------------------------------------------------------------- #

MARDI_11H = datetime(2026, 10, 6, 11, 0, tzinfo=ZoneInfo("Europe/Paris"))
DIMANCHE_11H = datetime(2026, 10, 4, 11, 0, tzinfo=ZoneInfo("Europe/Paris"))


async def _clavier(catalogue, configurations=None, contexte=None, maintenant=DIMANCHE_11H, phrases=None, preferences=None):
    from api.services.pipecat import etat_ouverture

    reel = etat_ouverture.injecter_etat_ouverture
    with (
        patch.object(
            module_copie,
            "lire_copie_complete",
            AsyncMock(return_value=module_copie.CopieOrganisation(etablissements=catalogue, phrases=phrases or CataloguePhrases(), lu_depuis="copie")),
        ),
        patch.object(
            text_chat_runner,
            "injecter_etat_ouverture",
            lambda ctx, cfg, **kw: reel(ctx, cfg, maintenant=maintenant, **kw),
        ),
        patch.object(text_chat_runner, "lire_annonce_ouverture", AsyncMock(return_value=ReglagesAnnonceOuverture())),
    ):
        return await _jouer_au_clavier(
            configurations or {}, contexte or {"direction": "inbound"}, preferences or OrganizationPreferences()
        )


@pytest.mark.asyncio
async def test_clavier_lit_les_horaires_ladresse_et_les_phrases_de_letablissement():
    persiste = await _clavier(CATALOGUE, contexte={"direction": "inbound", "etablissement_id": "creil"})
    assert persiste["etablissement"] == "Magasin de Creil"
    assert persiste["numero_transfert"] == "+33344000099"
    assert persiste["horaires_ouverture"] == HORAIRES_CREIL
    assert persiste["etat_ouverture"] == "FERME"
    assert persiste["annonce_ouverture"].startswith("Le magasin de Creil est fermé")
    assert persiste["adresse_etablissement"] == "60300 Senlis"
    estampille = persiste["runtime_configuration"]["etablissement"]
    assert estampille["id"] == "creil" and estampille["source"] == "essai" and estampille["lu_depuis"] == "copie"
    assert estampille["origines"]["horaires_ouverture"] == "etablissement"


@pytest.mark.asyncio
async def test_clavier_sans_etablissement_lappel_davant_a_lidentique():
    """🔒 Zero loss (E4, X2): no establishment, the persisted context is exactly
    the one of an organization that never heard of the feature."""
    avec_agent = {"horaires_ouverture": HORAIRES_AGENT}
    vide = await _clavier(CatalogueEtablissements(), avec_agent)
    with patch.object(text_chat_runner, "lire_lappel", AsyncMock(return_value=LectureDeLappel())):
        avant = await _clavier(CatalogueEtablissements(), avec_agent)
    assert vide == avant
    assert "etablissement" not in vide and "etablissement" not in vide["runtime_configuration"]
    assert vide["horaires_ouverture"] == HORAIRES_AGENT


def _position(source: str, motif: str, quoi: str) -> int:
    trouve = re.search(motif, source)
    assert trouve, f"{quoi} not found in the source"
    return trouve.start()


def test_le_telephone_resout_letablissement_avant_les_trois_injections_et_lestampille():
    source = inspect.getsource(run_pipeline)
    resolution = _position(source, r"lecture_de_lappel = await lire_lappel\(", "resolution")
    ouverture = _position(source, r"injecter_etat_ouverture\(\s*merged_call_context_vars,\s*configs_heritees", "opening state")
    adresse = _position(source, r"lire_adresse_etablissement\(\s*configs_heritees", "address")
    estampille = _position(source, r'runtime_configuration\["etablissement"\]', "stamp")
    persistance = _position(source, r"await db_client\.update_workflow_run\(\s*workflow_run_id, initial_context", "persistence")
    assert resolution < ouverture < adresse < estampille < persistance
    assert len(re.findall(r"lire_lappel\(", source)) == 1


def test_les_deux_chemins_derivent_la_configuration_heritee_de_celle_de_lagent():
    """The neighbouring branch tests now see ``configs_heritees``: this is what makes it
    the agent's own configuration (and the SAME dict without an establishment)."""
    for module in (run_pipeline, text_chat_runner):
        source = inspect.getsource(module)
        assert re.search(r"configs_heritees, origines_heritees = configuration_heritee\(\s*run_configs,", source)
