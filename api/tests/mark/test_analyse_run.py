"""[.mark] L'analyse d'un run pour sa fenêtre (chantier langwatch-et-fenetre-du-run, lot 1).

Questions, oui ou non :
1. La route rend-elle l'analyse d'un run de l'organisation de l'utilisateur, et 404 pour un run
   d'une AUTRE organisation ou d'un autre agent que celui de l'adresse ?
2. Sur les 35 runs du corpus, chaque bloc se calcule-t-il (aucun « unavailable ») et la latence
   rend-elle les chiffres de l'outil du labo ?
3. Un tour écarté de la mesure est-il MONTRÉ avec sa raison, au lieu de disparaître ?
4. Un bloc qui échoue se voit-il (« unavailable ») sans emporter les autres (R1) ?
5. Un run sans données rend-il « not_captured », jamais un bloc vide ?
"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import analyse_run as route_analyse
from api.services.analyse_run import analyse
from api.services.analyse_run.analyse import analyser_run
from api.services.analyse_run.mesures import mediane_basse, mesurer_run
from api.services.auth.depends import get_user_with_selected_organization
from api.services.workflow.fiche_au_fil_de_leau import NOM_OUTIL

CORPUS = Path(__file__).parent / "donnees" / "analyse_run_corpus_2026-10-05.json"
ORGANISATION_A = 21
ORGANISATION_B = 22
BLOCS = (
    "summary",
    "latency",
    "providers",
    "reading_modules",
    "record",
    "path",
    "conversation",
    "incidents",
)


@pytest.fixture(scope="module")
def corpus():
    return json.loads(CORPUS.read_text(encoding="utf-8"))["runs"]


def _run(corpus, identifiant):
    return copy.deepcopy(next(r for r in corpus if r["id"] == identifiant))


# --------------------------------------------------------------------------- #
# 1. Le cloisonnement de la route
# --------------------------------------------------------------------------- #


class _Base:
    """``db_client.get_workflow_run`` tel que la base le fait : filtré par organisation."""

    def __init__(self, runs):
        self.runs = runs  # (organisation, run)
        self.appels = []

    async def get_workflow_run(self, run_id, user_id=None, organization_id=None):
        self.appels.append(organization_id)
        for organisation, run in self.runs:
            if run.id == run_id and organisation == organization_id:
                return run
        return None


def _ligne(donnees, workflow_id, definition=None):
    return SimpleNamespace(
        id=donnees["id"],
        workflow_id=workflow_id,
        definition_id=17,
        mode=donnees["mode"],
        usage_info=donnees["usage_info"],
        initial_context=donnees["initial_context"],
        gathered_context=donnees["gathered_context"],
        logs=donnees["logs"],
        definition=definition,
    )


def _client(organisation):
    app = FastAPI()
    app.include_router(route_analyse.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: (
        SimpleNamespace(id=1, provider_id="p", selected_organization_id=organisation)
    )
    return TestClient(app)


@pytest.fixture
def base(corpus):
    definition = SimpleNamespace(
        workflow_json={
            "edges": [
                {"data": {"label": "Demande d'entretien"}},
                {"data": {"label": "Rien d'autre a signaler"}},
            ]
        },
        workflow_configurations={
            "fiche_champs": [{"nom": "nom"}, {"nom": "champ_jamais_dit"}]
        },
    )
    # Le corpus est sans texte (pas de fiche) : une fiche fictive d'un seul champ écrit.
    avec_fiche = _run(corpus, 967)
    avec_fiche["gathered_context"].update(
        fiche_etat={"nom": {"sure": True, "source": "outil"}},
        fiche_journal=[
            {
                "champ": "nom",
                "valeur": "Testeur",
                "statut": "ecrit",
                "source": "outil",
                "sure": True,
                "tour": 4,
            }
        ],
        extracted_variables={"nom": "Testeur"},
    )
    memoire = _Base(
        [
            (ORGANISATION_A, _ligne(avec_fiche, 34, definition)),
            (ORGANISATION_B, _ligne(_run(corpus, 966), 34)),
        ]
    )
    with patch.object(route_analyse, "db_client", memoire):
        yield memoire


def test_la_route_rend_l_analyse_d_un_run_de_l_organisation(base):
    reponse = _client(ORGANISATION_A).get("/workflow/34/runs/967/analyse")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["run_id"] == 967
    assert set(BLOCS) <= set(corps)
    assert base.appels == [ORGANISATION_A]


def test_un_run_d_une_autre_organisation_rend_404(base):
    reponse = _client(ORGANISATION_A).get("/workflow/34/runs/966/analyse")
    assert reponse.status_code == 404
    assert base.appels == [ORGANISATION_A]


def test_un_run_d_un_autre_agent_que_celui_de_l_adresse_rend_404(base):
    assert (
        _client(ORGANISATION_A).get("/workflow/35/runs/967/analyse").status_code == 404
    )


def test_la_definition_jouee_nomme_les_portes_et_les_champs_vides(base):
    corps = _client(ORGANISATION_A).get("/workflow/34/runs/967/analyse").json()
    natures = {o["name"]: o["kind"] for o in corps["path"]["tools"]}
    assert natures["noter_information"] == "note"
    assert natures["rien_d_autre_a_signaler"] == "transition"
    vide = next(c for c in corps["record"]["fields"] if c["name"] == "champ_jamais_dit")
    assert vide["declared"] and vide["empty"]


# --------------------------------------------------------------------------- #
# 2. Le corpus entier
# --------------------------------------------------------------------------- #


def test_chaque_bloc_se_calcule_sur_tout_le_corpus(corpus):
    for run in corpus:
        analyse_du_run = analyser_run(run)
        for bloc in BLOCS:
            assert analyse_du_run[bloc]["status"] != "unavailable", (run["id"], bloc)


def test_la_latence_rend_les_chiffres_de_l_outil_du_labo(corpus):
    for run in corpus:
        labo = mesurer_run(run)
        latence = analyser_run(run)["latency"]
        if latence["status"] != "ok":
            continue
        assert latence["stats"]["lab"]["median_turn_secs"] == mediane_basse(
            labo["tour"]
        )
        assert latence["stats"]["median_passes"] == mediane_basse(labo["passes"])
        # Les tours mesurés à l'écran sont ceux que le labo mesure, hors accueil.
        mesures = [t["silence_secs"] for t in latence["turns"] if t["measured"]]
        assert sorted(mesures) == sorted(
            d["complet"]
            for d in labo["detailTours"]
            if d["complet"] is not None and d["tour"] != 1
        ), run["id"]


def test_les_passes_apres_un_outil_sont_nommees(corpus):
    run = _run(corpus, 967)
    latence = analyser_run(run, portes={"rien_d_autre_a_signaler"})["latency"]
    natures = {p["after"] for t in latence["turns"] for p in t["passes"]}
    assert {"note", "reply"} <= natures


def test_le_nom_de_l_outil_de_note_suit_celui_de_la_fiche():
    assert analyse.OUTIL_DE_NOTE == NOM_OUTIL


# --------------------------------------------------------------------------- #
# 3. Les tours écartés se montrent
# --------------------------------------------------------------------------- #


def test_un_tour_sans_detail_de_latence_est_montre_avec_sa_raison(corpus):
    tours = analyser_run(_run(corpus, 1014))["latency"]["turns"]
    tour_6 = next(t for t in tours if t["turn"] == 6)
    assert tour_6["measured"] is False
    assert tour_6["not_measured_reason"] == "no_latency_detail"


def test_un_tour_sans_replique_est_montre_avec_sa_raison(corpus):
    tours = analyser_run(_run(corpus, 967))["latency"]["turns"]
    assert any(t["not_measured_reason"] == "no_reply" for t in tours)


# --------------------------------------------------------------------------- #
# 4. et 5. Aucune défaillance silencieuse
# --------------------------------------------------------------------------- #


def test_un_bloc_en_echec_se_voit_sans_emporter_les_autres(corpus):
    def casse(*args, **kwargs):
        raise KeyError("forme inattendue")

    with patch.object(analyse, "_modules", casse):
        resultat = analyser_run(_run(corpus, 967))
    assert resultat["reading_modules"] == {
        "status": "unavailable",
        "reason": "KeyError",
    }
    assert resultat["latency"]["status"] == "ok"
    assert resultat["path"]["status"] == "ok"


def test_un_run_sans_donnees_dit_non_capte():
    resultat = analyser_run({"id": 1, "workflow_id": 2, "mode": "smallwebrtc"})
    for bloc in (
        "latency",
        "providers",
        "reading_modules",
        "record",
        "path",
        "conversation",
    ):
        assert resultat[bloc]["status"] == "not_captured", bloc
    assert resultat["summary"]["cost"] == {"status": "not_captured"}


def test_le_429_de_mistral_devient_un_incident(corpus):
    """Le run 899 a pris un refus de quota Mistral (code 1300) : la fenêtre le montre."""
    incidents = analyser_run(_run(corpus, 899))["incidents"]["items"]
    assert any(i["kind"] == "model_rate_limited" for i in incidents)


def test_la_fiche_lisible_porte_la_provenance(base):
    champs = (
        _client(ORGANISATION_A)
        .get("/workflow/34/runs/967/analyse")
        .json()["record"]["fields"]
    )
    nom = next(c for c in champs if c["name"] == "nom")
    assert (
        nom["value"] == "Testeur" and nom["source"] == "outil" and nom["sure"] is True
    )
    assert nom["written_at_caller_turn"] == 4 and not nom["empty"]


def test_l_organisation_est_celle_de_l_utilisateur_dans_les_deux_sens(base):
    """R7 : une route qui lirait toujours la même organisation passait les deux tests du haut."""
    client_b = _client(ORGANISATION_B)
    assert client_b.get("/workflow/34/runs/966/analyse").status_code == 200
    assert client_b.get("/workflow/34/runs/967/analyse").status_code == 404
    assert base.appels == [ORGANISATION_B, ORGANISATION_B]
