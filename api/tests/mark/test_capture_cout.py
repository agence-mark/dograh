"""[.mark] Le coût estimé d'un appel (chantier langwatch-et-fenetre-du-run, lot 2, étape 5, L5).

Questions :
1. Consommation × table de prix : le total est-il celui qu'on calcule à la main, au tarif daté ?
2. Une consommation sans prix déclaré est-elle listée « unpriced » (total partiel), jamais devinée ?
3. Sans table, le coût est-il « not_captured », jamais 0 ?
4. La table refuse-t-elle un prix manquant, un prix d'une autre brique, un modèle déclaré deux fois ?
5. Les routes lisent et écrivent la table de l'organisation de l'utilisateur, et l'écran refuse de
   montrer une table illisible (qu'un enregistrement écraserait) ?
"""

import copy
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.routes import table_des_prix as route_prix
from api.schemas.table_des_prix import LignePrix, TableDesPrix
from api.services.analyse_run import cout
from api.services.analyse_run.analyse import analyser_run
from api.services.analyse_run.cout import cout_du_run
from api.services.auth.depends import get_user_with_selected_organization

CORPUS = Path(__file__).parent / "donnees" / "analyse_run_corpus_2026-10-05.json"
TARIF = date(2026, 10, 1)


def _run_967():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    return copy.deepcopy(next(r for r in corpus["runs"] if r["id"] == 967))


def _table(*lignes):
    return TableDesPrix(devise="USD", lignes=list(lignes))


LARGE = LignePrix(
    brique="llm",
    modele="mistral-large-2512",
    entree_par_million=2.0,
    cache_par_million=0.2,
    sortie_par_million=6.0,
    date_du_tarif=TARIF,
)
FLUX = LignePrix(
    brique="stt", modele="flux-general-multi", par_minute=0.0077, date_du_tarif=TARIF
)


def test_le_total_est_celui_du_calcul_a_la_main():
    # Run 967 : 154 096 jetons d'entrée dont 103 936 en cache, 887 en sortie ; 155,479 s transcrites.
    bilan = cout_du_run(_run_967(), _table(LARGE, FLUX))
    modele = (154_096 - 103_936) * 2.0 / 1e6 + 103_936 * 0.2 / 1e6 + 887 * 6.0 / 1e6
    transcription = 155.47899999999785 / 60 * 0.0077
    assert bilan["status"] == "ok"
    assert bilan["total"] == round(modele + transcription, 4)
    assert bilan["rate_dates"] == ["2026-10-01"]
    assert bilan["currency"] == "USD"


def test_une_consommation_sans_prix_est_listee_jamais_devinee():
    bilan = cout_du_run(_run_967(), _table(LARGE))
    assert bilan["partial"] is True
    assert {(u["component"], u["model"]) for u in bilan["unpriced"]} == {
        ("stt", "flux-general-multi"),
        ("tts", "eleven_flash_v2_5"),
    }


def test_sans_table_le_cout_n_est_pas_capte():
    assert cout_du_run(_run_967(), None)["status"] == "not_captured"
    assert cout_du_run(_run_967(), _table())["status"] == "not_captured"
    assert analyser_run(_run_967())["summary"]["cost"]["status"] == "not_captured"


def test_la_telephonie_ne_compte_que_pour_un_appel_telephonique():
    twilio = LignePrix(
        brique="telephony", modele="twilio", par_minute=0.0085, date_du_tarif=TARIF
    )
    run = _run_967()
    run["initial_context"]["provider"] = "twilio"
    assert not any(
        l["component"] == "telephony" for l in cout_du_run(run, _table(twilio))["lines"]
    )
    run["mode"] = "twilio"
    lignes = cout_du_run(run, _table(twilio))["lines"]
    assert [l["component"] for l in lignes] == ["telephony"]
    assert lignes[0]["cost"] == round(158 / 60 * 0.0085, 6)


@pytest.mark.parametrize(
    "ligne",
    [
        {
            "brique": "llm",
            "modele": "m",
            "entree_par_million": 1,
            "date_du_tarif": "2026-10-01",
        },
        {
            "brique": "stt",
            "modele": "m",
            "par_minute": 1,
            "entree_par_million": 1,
            "date_du_tarif": "2026-10-01",
        },
        {"brique": "tts", "modele": "m", "date_du_tarif": "2026-10-01"},
        {
            "brique": "llm",
            "modele": "m",
            "entree_par_million": -1,
            "sortie_par_million": 1,
            "date_du_tarif": "2026-10-01",
        },
    ],
)
def test_une_ligne_fautive_est_refusee(ligne):
    with pytest.raises(ValidationError):
        LignePrix.model_validate(ligne)


def test_un_modele_declare_deux_fois_est_refuse():
    with pytest.raises(ValidationError):
        _table(LARGE, LARGE)


class _Base:
    def __init__(self, lignes=None):
        self.lignes = dict(lignes or {})

    async def get_configuration(self, organization_id, key):
        valeur = self.lignes.get((organization_id, key))
        return None if valeur is None else SimpleNamespace(value=valeur)

    async def upsert_configuration(
        self, organization_id, key, value, last_validated_at=None
    ):
        self.lignes[(organization_id, key)] = value


def _client(organisation):
    app = FastAPI()
    app.include_router(route_prix.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: (
        SimpleNamespace(id=1, selected_organization_id=organisation)
    )
    return TestClient(app)


def test_les_routes_lisent_et_ecrivent_la_table_de_l_organisation():
    base = _Base()
    with patch.object(cout, "db_client", base):
        corps = _table(LARGE).model_dump(mode="json")
        assert (
            _client(31).put("/organizations/table-des-prix", json=corps).status_code
            == 200
        )
        assert (
            _client(31)
            .get("/organizations/table-des-prix")
            .json()["lignes"][0]["modele"]
            == "mistral-large-2512"
        )
        assert _client(32).get("/organizations/table-des-prix").json()["lignes"] == []
        assert list(base.lignes) == [(31, cout.CLE)]


def test_une_saisie_fautive_est_refusee_en_422_sans_rien_ecrire():
    base = _Base()
    with patch.object(cout, "db_client", base):
        corps = {
            "lignes": [{"brique": "tts", "modele": "x", "date_du_tarif": "2026-10-01"}]
        }
        assert (
            _client(31).put("/organizations/table-des-prix", json=corps).status_code
            == 422
        )
    assert base.lignes == {}


def test_l_ecran_refuse_une_table_illisible_plutot_que_la_montrer_vide():
    base = _Base({(31, cout.CLE): {"lignes": "pas une liste"}})
    with patch.object(cout, "db_client", base):
        assert _client(31).get("/organizations/table-des-prix").status_code == 500


@pytest.mark.asyncio
async def test_l_analyse_lit_la_table_sans_jamais_lever():
    with patch.object(
        cout, "db_client", _Base({(31, cout.CLE): {"lignes": "pas une liste"}})
    ):
        assert await cout.lire_table_des_prix(31) is None
    with patch.object(
        cout,
        "db_client",
        _Base({(31, cout.CLE): _table(LARGE).model_dump(mode="json")}),
    ):
        assert (await cout.lire_table_des_prix(31)).lignes[
            0
        ].modele == "mistral-large-2512"
