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

from api.routes import fenetre_du_run as route_prix
from api.schemas.fenetre_du_run import LignePrix, ReglagesFenetreDuRun
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
    return ReglagesFenetreDuRun(devise="USD", lignes=list(lignes))


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
            _client(31).put("/organizations/fenetre-du-run", json=corps).status_code
            == 200
        )
        assert (
            _client(31)
            .get("/organizations/fenetre-du-run")
            .json()["lignes"][0]["modele"]
            == "mistral-large-2512"
        )
        assert _client(32).get("/organizations/fenetre-du-run").json()["lignes"] == []
        assert list(base.lignes) == [(31, cout.CLE)]


def test_une_saisie_fautive_est_refusee_en_422_sans_rien_ecrire():
    base = _Base()
    with patch.object(cout, "db_client", base):
        corps = {
            "lignes": [{"brique": "tts", "modele": "x", "date_du_tarif": "2026-10-01"}]
        }
        assert (
            _client(31).put("/organizations/fenetre-du-run", json=corps).status_code
            == 422
        )
    assert base.lignes == {}


def test_l_ecran_refuse_une_table_illisible_plutot_que_la_montrer_vide():
    base = _Base({(31, cout.CLE): {"lignes": "pas une liste"}})
    with patch.object(cout, "db_client", base):
        assert _client(31).get("/organizations/fenetre-du-run").status_code == 500


@pytest.mark.asyncio
async def test_l_analyse_lit_la_table_sans_jamais_lever():
    with patch.object(
        cout, "db_client", _Base({(31, cout.CLE): {"lignes": "pas une liste"}})
    ):
        assert await cout.lire_reglages_fenetre(31) is None
    with patch.object(
        cout,
        "db_client",
        _Base({(31, cout.CLE): _table(LARGE).model_dump(mode="json")}),
    ):
        assert (await cout.lire_reglages_fenetre(31)).lignes[
            0
        ].modele == "mistral-large-2512"


# --------------------------------------------------------------------------- #
# Détecteur de silence anormal (L6) et seuils réglables (L18)
# --------------------------------------------------------------------------- #

from api.schemas.fenetre_du_run import Seuils  # noqa: E402
from api.services.analyse_run.analyse import silences_apres_outil  # noqa: E402


def _ev(type_, tour, a, **charge):
    return {
        "type": type_,
        "turn": tour,
        "timestamp": f"2026-10-05T10:00:{a:06.3f}+00:00",
        "payload": charge,
    }


def _dit(qui, tour, debut, fin):
    horo = lambda s: f"2026-10-05T10:00:{s:06.3f}+00:00"  # noqa: E731
    if qui == "caller":
        return _ev(
            "rtf-user-transcription",
            tour,
            fin,
            final=True,
            timestamp=horo(debut),
            end_timestamp=horo(fin),
        )
    return _ev(
        "rtf-bot-text", tour, fin, timestamp=horo(debut), end_timestamp=horo(fin)
    )


def _detail(tour, a, passes):
    ttfb = [{"processor": "DograhMistralLLMService#0", "duration_secs": 0.5}] * passes
    return _ev("mark-latency-breakdown", tour, a, ttfb=ttfb)


def _run(*evenements):
    return {"id": 1, "logs": {"realtime_feedback_events": list(evenements)}}


def test_l_agent_muet_apres_l_outil_jusqu_a_ce_que_l_appelant_reparle_est_un_incident():
    run = _run(
        _dit("caller", 2, 1.0, 3.0),
        _ev("rtf-function-call-start", 2, 4.0, function_name="noter_information"),
        _ev("rtf-function-call-end", 2, 4.0, function_name="noter_information"),
        _detail(2, 4.5, passes=1),  # aucune passe après l'outil : signature du #5960
        _dit("caller", 3, 11.0, 12.0),
    )
    [silence] = silences_apres_outil(run, 5.0)
    assert silence == {
        "turn": 2,
        "tool": "noter_information",
        "secs": 7.0,
        "broken_by": "caller",
        "model_pass_after_tool": False,
    }
    incident = next(
        i
        for i in analyser_run(run)["incidents"]["items"]
        if i["kind"] == "silence_after_tool"
    )
    assert incident["detail"]["threshold_secs"] == 5.0


def test_une_replique_qui_couvre_l_outil_n_est_pas_un_silence():
    """Faux positif du run 885 au premier essai : la réplique commencée avant la porte durait après."""
    run = _run(
        _dit("agent", 6, 1.0, 12.0),
        _ev("rtf-function-call-end", 6, 7.0, function_name="dossier_decrit"),
        _dit("caller", 7, 14.0, 15.0),
    )
    assert silences_apres_outil(run, 5.0) == []


def test_sous_le_seuil_rien_et_le_seuil_de_l_organisation_est_celui_qui_joue():
    run = _run(
        _ev("rtf-function-call-end", 2, 4.0, function_name="noter_information"),
        _detail(2, 4.5, passes=2),
        _dit("agent", 2, 8.0, 9.0),
    )
    assert silences_apres_outil(run, 5.0) == []
    reglages = ReglagesFenetreDuRun(seuils=Seuils(silence_apres_outil_s=3.0))
    incidents = analyser_run(run, reglages_fenetre=reglages)["incidents"]["items"]
    [silence] = [i for i in incidents if i["kind"] == "silence_after_tool"]
    assert (
        silence["detail"]["broken_by"] == "agent"
        and silence["detail"]["model_pass_after_tool"] is True
    )


def test_le_seuil_du_tour_lent_vient_de_l_organisation():
    run = _run_967()
    lents = lambda r: sum(t["slow"] for t in r["latency"]["turns"])  # noqa: E731
    assert lents(analyser_run(run)) < lents(
        analyser_run(
            run, reglages_fenetre=ReglagesFenetreDuRun(seuils=Seuils(tour_lent_s=1.0))
        )
    )


def test_sur_les_35_vrais_runs_trois_silences_dont_une_signature_du_5960():
    """Constat du 05/10 (journal du chantier) : sur 357 résultats d'outil, au seuil de 5 s, trois
    silences rompus par l'appelant ; un seul sans passe du modèle après l'outil (run 964, tour 2)."""
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))["runs"]
    trouves = [
        (r["id"], s["turn"], s["model_pass_after_tool"])
        for r in corpus
        for s in silences_apres_outil(r, 5.0)
    ]
    assert sorted(trouves) == [(909, 3, True), (964, 2, False), (967, 9, True)]


def test_les_seuils_sont_bornes():
    with pytest.raises(ValidationError):
        Seuils(silence_apres_outil_s=0.5)
    with pytest.raises(ValidationError):
        Seuils(tour_lent_s=60)
    assert ReglagesFenetreDuRun().seuils == Seuils(
        silence_apres_outil_s=5.0, tour_lent_s=3.0
    )
