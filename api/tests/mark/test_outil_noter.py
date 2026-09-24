"""[.mark] Lot 1 de « la fiche au fil de l'eau » : l'outil `noter_information`.

Plan : `Labo-agent-vocal/plans/2026-09-23-plan-fiche-au-fil-de-leau.md`.

| Test | Ce qu'il prouve |
|---|---|
| T1.1 | Interrupteur éteint : l'outil n'est pas proposé, l'extraction est inchangée |
| T1.2 | Une écriture atteint la fiche, la deuxième écrase la première |
| T1.3 | Une valeur dictée que l'appelant n'a jamais dite est refusée et journalisée |
| T1.4 | Une note et une porte du même tour sont toutes deux honorées, dans les deux ordres |
| T1.5 | (D40) La note n'ajoute jamais de relance : une seule, porte ou pas, dans les deux ordres |
| T1.6 | Une valeur non sûre n'écrase pas une valeur sûre |

T1.4 et T1.5 se jouent sur le vrai pipeline Pipecat (agrégateurs, regroupement
des fonctions d'un même tour), pas sur une valeur de retour.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.frames.frames import EndFrame, LLMContextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.tests.mock_transport import MockTransport
from pipecat.transports.base_transport import TransportParams
from pydantic import ValidationError

from api.schemas.fiche_agent import NOMS_RESERVES
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.workflow import pipecat_engine
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_JOURNAL,
    CONSIGNE_NON_DIT,
    NOM_OUTIL,
    NOTE_DESCRIPTIONS,
    ReglagesFiche,
    creer_gestionnaire,
    ecrire_dans_la_fiche,
    est_cite,
    schema_outil,
)
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.pipecat_engine_variable_extractor import (
    VariableExtractionManager,
)
from api.tests.pipecat_test_utils import run_engine_test_pipeline
from pipecat.tests import MockLLMService, MockTTSService

CONFIG_ALLUMEE = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        # Lot 1 : le chemin générique, sans module. Le lecteur « commune » (D42)
        # est éprouvé dans `test_modules_derriere_outil.py`.
        {"nom": "commune", "origine": "dicte", "lecteur": "aucun"},
        {"nom": "telephone", "origine": "dicte"},
        {"nom": "dernier_entretien", "origine": "dicte"},
        {"nom": "motif", "origine": "deduit"},
    ],
}


def _reglages() -> ReglagesFiche:
    reglages = ReglagesFiche.depuis(CONFIG_ALLUMEE)
    assert reglages is not None
    return reglages


class _Params:
    """Le strict nécessaire de `FunctionCallParams` pour appeler le gestionnaire."""

    def __init__(self, arguments: dict):
        self.arguments = arguments
        self.resultats: list[tuple[dict, object]] = []

    async def result_callback(self, result, *, properties=None):
        self.resultats.append((result, properties))


# --- Les réglages ------------------------------------------------------------


def test_eteint_par_defaut_aucun_reglage():
    assert ReglagesFiche.depuis(None) is None
    assert ReglagesFiche.depuis({}) is None
    assert (
        ReglagesFiche.depuis({"fiche_champs": CONFIG_ALLUMEE["fiche_champs"]}) is None
    )
    assert WorkflowConfigurationDefaults().fiche_au_fil_de_leau is False


def test_temps_reel_ou_sans_champ_pas_d_outil():
    assert ReglagesFiche.depuis(CONFIG_ALLUMEE, is_realtime=True) is None
    assert ReglagesFiche.depuis({"fiche_au_fil_de_leau": True}) is None


@pytest.mark.parametrize("nom", sorted(NOMS_RESERVES))
def test_nom_reserve_refuse_a_l_enregistrement(nom):
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults.model_validate({"fiche_champs": [{"nom": nom}]})


def test_nom_en_double_refuse_a_l_enregistrement():
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults.model_validate(
            {"fiche_champs": [{"nom": "nom"}, {"nom": "nom"}]}
        )


def test_les_noms_reserves_couvrent_les_cles_du_moteur():
    """La liste des noms réservés est écrite à la main : ce test la tient à jour."""
    assert pipecat_engine._ENGINE_OWNED_CONTEXT_KEYS <= NOMS_RESERVES


def test_schema_un_parametre_facultatif_par_champ():
    schema = schema_outil(_reglages())
    assert schema.name == NOM_OUTIL
    assert set(schema.properties) == {
        "nom",
        "commune",
        "telephone",
        "dernier_entretien",
        "motif",
    }
    assert schema.required == []
    assert schema.properties["nom"]["description"] == "Nom de famille"
    # A3 : la description de l'outil dit que celles des champs sont à lire.
    assert schema.description.endswith(NOTE_DESCRIPTIONS)
    assert "jamais des questions à poser" in NOTE_DESCRIPTIONS


# --- Le contrôle de citation (D5, D41) ---------------------------------------


@pytest.mark.parametrize(
    "valeur, paroles",
    [
        ("Creil", ["c'est à creil"]),
        ("LEFEVRE", ["je suis madame Lefèvre, L E F E V R E"]),
        ("MOREAU", ["M O R E A U"]),
        ("0612345678", ["mon numéro 06 12 34 56 78"]),
        ("60100", ["à Creil, 60 100"]),
        ("21 rue Pasteur", ["12 rue Pasteur", "non pardon, c'est le 21"]),
        ("l'année dernière", ["l'entretien a été fait l'année dernière"]),
    ],
)
def test_citation_acceptee(valeur, paroles):
    assert est_cite(valeur, paroles)


@pytest.mark.parametrize(
    "valeur, paroles",
    [
        ("Lyon 5ᵉ", ["c'est à Lyon Court"]),  # run 791
        ("2025", ["l'entretien a été fait l'année dernière"]),  # run 791
        ("MORSO", ["M O R E A U"]),  # run 796
        ("le père de la personne concernée", ["c'est pour chez moi"]),  # run 808
    ],
)
def test_citation_refusee(valeur, paroles):
    assert not est_cite(valeur, paroles)


# --- Le point d'écriture unique (D35) ----------------------------------------


def test_T1_2_ecriture_puis_ecrasement():
    fiche: dict = {}
    paroles = ["c'est à Creil", "non, à Senlis pardon"]
    assert (
        ecrire_dans_la_fiche(
            fiche, _reglages(), "commune", "Creil", paroles=paroles
        ).statut
        == "ecrit"
    )
    assert fiche["commune"] == "Creil"
    assert (
        ecrire_dans_la_fiche(
            fiche, _reglages(), "commune", "Senlis", paroles=paroles
        ).statut
        == "ecrit"
    )
    assert fiche["commune"] == "Senlis"
    assert fiche["extracted_variables"]["commune"] == "Senlis"
    assert fiche[CLE_ETAT]["commune"] == {"sure": True, "source": "outil"}


def test_T1_3_valeur_jamais_dite_refusee_et_journalisee():
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "commune", "Lyon 5ᵉ", paroles=["c'est à Lyon Court"]
    )
    assert (verdict.statut, verdict.raison) == ("refuse", "non_dit")
    assert "commune" not in fiche
    assert fiche[CLE_JOURNAL][-1]["raison"] == "non_dit"


def test_champ_deduit_sans_controle_de_citation():
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "motif", "Entretien annuel du poêle", paroles=["bonjour"]
    )
    assert verdict.statut == "ecrit"


def test_champ_inconnu_refuse_valeur_vide_ignoree():
    fiche: dict = {"commune": "Creil"}
    assert (
        ecrire_dans_la_fiche(fiche, _reglages(), "inconnu", "x").raison
        == "champ_inconnu"
    )
    assert (
        ecrire_dans_la_fiche(fiche, _reglages(), "commune", "  ").raison
        == "valeur_vide"
    )
    assert (
        ecrire_dans_la_fiche(fiche, _reglages(), "commune", None).raison
        == "valeur_vide"
    )
    assert fiche["commune"] == "Creil"


def test_T1_6_non_sure_n_ecrase_pas_sure():
    fiche: dict = {}
    paroles = ["Creil", "Crèvecoeur"]
    ecrire_dans_la_fiche(
        fiche, _reglages(), "commune", "Creil", sure=True, paroles=paroles
    )
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "commune", "Crèvecoeur", sure=False, paroles=paroles
    )
    assert (verdict.statut, verdict.raison) == ("refuse", "non_sure_sur_sure")
    assert fiche["commune"] == "Creil"
    # L'inverse est permis : une valeur sûre remplace une valeur non sûre.
    fiche2: dict = {}
    ecrire_dans_la_fiche(
        fiche2, _reglages(), "commune", "Creil", sure=False, paroles=paroles
    )
    assert (
        ecrire_dans_la_fiche(
            fiche2, _reglages(), "commune", "Crèvecoeur", paroles=paroles
        ).statut
        == "ecrit"
    )


def test_seulement_si_vide_n_ecrase_rien():
    fiche: dict = {}
    paroles = ["Creil", "Senlis"]
    ecrire_dans_la_fiche(fiche, _reglages(), "commune", "Creil", paroles=paroles)
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "commune", "Senlis", paroles=paroles, seulement_si_vide=True
    )
    assert verdict.raison == "deja_rempli"
    assert fiche["commune"] == "Creil"


# --- Le gestionnaire ---------------------------------------------------------


@pytest.mark.asyncio
async def test_gestionnaire_chaque_champ_seul_et_aucun_run_llm():
    fiche: dict = {}
    messages = [
        {"role": "assistant", "content": "Bonjour"},
        {"role": "user", "content": "Monsieur Dupont, à Creil"},
    ]
    gestionnaire = creer_gestionnaire(_reglages(), lambda: fiche, lambda: messages)
    params = _Params({"nom": "Dupont", "commune": "Lyon 5ᵉ", "inconnu": "x"})
    await gestionnaire(params)
    ((resultat, properties),) = params.resultats
    assert fiche["nom"] == "Dupont" and "commune" not in fiche
    assert resultat["statut"] == "note"
    assert resultat["ecrits"] == ["nom"]
    assert {r["champ"] for r in resultat["refuses"]} == {"commune", "inconnu"}
    # D40 : jamais de `run_llm` fixé par la note.
    assert properties is None


@pytest.mark.asyncio
async def test_A5_un_refus_non_dit_porte_une_consigne():
    """Runs 831, 837 : sans consigne, le refus poussait le modèle à faire confirmer
    sa version. Le refus dit quoi faire : noter les mots de la personne."""
    fiche: dict = {}
    messages = [{"role": "user", "content": "Monsieur Dupont, à Creil"}]
    gestionnaire = creer_gestionnaire(_reglages(), lambda: fiche, lambda: messages)
    params = _Params({"commune": "Lyon 5ᵉ", "inconnu": "x"})
    await gestionnaire(params)
    ((resultat, _),) = params.resultats
    assert resultat["statut"] == "rien_note"
    assert resultat["consigne"] == CONSIGNE_NON_DIT.format(champs="commune")
    assert "ne lui fais pas confirmer ta version" in resultat["consigne"]


# --- Branchement dans le moteur, sur le vrai pipeline ------------------------


async def _jouer(workflow, reglages, etapes, *, retard: dict[str, float] | None = None):
    """Monte le pipeline de production (agrégateurs compris), dépose une phrase
    de l'appelant, lance le modèle factice et rend (moteur, modèle, schémas vus)."""
    llm = MockLLMService(mock_steps=etapes, chunk_delay=0.001)
    retard = retard or {}
    enregistrer = llm.register_function

    def enregistrer_avec_retard(nom, fonction, *args, **kwargs):
        if nom in retard:

            async def retardee(params, _f=fonction, _d=retard[nom]):
                await asyncio.sleep(_d)
                return await _f(params)

            return enregistrer(nom, retardee, *args, **kwargs)
        return enregistrer(nom, fonction, *args, **kwargs)

    llm.register_function = enregistrer_avec_retard

    transport = MockTransport(
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            audio_out_end_silence_secs=0,
        )
    )
    context = LLMContext()
    engine = PipecatEngine(
        llm=llm,
        context=context,
        workflow=workflow,
        call_context_vars={},
        workflow_run_id=1,
        fiche=reglages,
    )
    paire = LLMContextAggregatorPair(context)
    pipeline = Pipeline(
        [
            transport.input(),
            paire.user(),
            llm,
            MockTTSService(mock_audio_duration_ms=40, frame_delay=0),
            transport.output(),
            paire.assistant(),
        ]
    )
    task = PipelineWorker(pipeline, params=PipelineParams(), enable_rtvi=False)
    engine.set_task(task)
    outils_vus: list[list[str]] = []
    mettre_a_jour = engine._update_llm_context

    async def espion(system_prompt, functions):
        outils_vus.append([f.name for f in functions])
        return await mettre_a_jour(system_prompt, functions)

    engine._update_llm_context = espion

    async def demarrer():
        await engine.set_node(engine.workflow.start_node_id)
        context.add_message({"role": "user", "content": "Bonjour, monsieur Dupont"})
        await engine.llm.queue_frame(LLMContextFrame(context))

        async def arreter():
            await asyncio.sleep(1.5)
            await task.queue_frame(EndFrame())

        asyncio.get_running_loop().create_task(arreter())

    with (
        patch(
            "api.db:db_client.get_organization_id_by_workflow_run_id",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch.object(
            VariableExtractionManager,
            "_perform_extraction",
            new_callable=AsyncMock,
            return_value={"user_name": "EXTRACTION"},
        ) as extraction,
    ):
        await run_engine_test_pipeline(task, engine, transport, on_ready=demarrer)
    return engine, llm, outils_vus, extraction


def _note_et_porte(ordre_des_appels):
    appels = {
        "note": {
            "name": NOM_OUTIL,
            "arguments": {"nom": "Dupont"},
            "tool_call_id": "note_1",
        },
        "porte": {"name": "collect_info", "arguments": {}, "tool_call_id": "porte_1"},
    }
    return [
        MockLLMService.create_multiple_function_call_chunks(
            [appels[a] for a in ordre_des_appels]
        ),
        MockLLMService.create_text_chunks("Très bien."),
        MockLLMService.create_text_chunks("RELANCE EN TROP"),
    ]


@pytest.mark.asyncio
async def test_T1_1_eteint_l_outil_n_est_pas_propose(
    three_node_workflow, no_disposition_mapping
):
    etapes = [MockLLMService.create_text_chunks("Bonjour.")]
    engine, _, outils_vus, _ = await _jouer(three_node_workflow, None, etapes)
    assert outils_vus and all(NOM_OUTIL not in noms for noms in outils_vus)
    assert NOM_OUTIL not in engine.llm._functions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "emission",
    [["note", "porte"], ["porte", "note"]],
    ids=["note-emise-en-premier", "porte-emise-en-premier"],
)
@pytest.mark.parametrize(
    "retard",
    [{NOM_OUTIL: 0.3}, {"collect_info": 0.3}, {}],
    ids=["la-note-finit-apres-la-porte", "la-porte-finit-apres-la-note", "sans-retard"],
)
async def test_T1_4_T1_5_note_et_porte_une_seule_relance(
    three_node_workflow, no_disposition_mapping, retard, emission
):
    """⚠️ Sans `SuiviDesTours`, le cas « la porte finit après la note » relançait
    le modèle DEUX fois (constaté le 24/09 : la note, instantanée, finit avant que
    la porte soit signalée à l'agrégateur de Pipecat)."""
    engine, llm, outils_vus, _ = await _jouer(
        three_node_workflow, _reglages(), _note_et_porte(emission), retard=retard
    )
    # T1.4 : la note ET la porte sont honorées.
    assert engine._gathered_context["nom"] == "Dupont"
    assert engine._current_node.id == "agent"
    # T1.5 : une seule relance après le tour (étape 0 = le tour, étape 1 = la relance).
    assert llm.get_current_step() == 2
    # L'outil est proposé à l'étape d'accueil et à l'étape suivante.
    assert NOM_OUTIL in outils_vus[0] and NOM_OUTIL in outils_vus[-1]


@pytest.mark.asyncio
async def test_T1_5_note_seule_une_relance_pour_parler(
    three_node_workflow, no_disposition_mapping
):
    etapes = [
        MockLLMService.create_function_call_chunks(
            function_name=NOM_OUTIL, arguments={"nom": "Dupont"}, tool_call_id="note_1"
        ),
        MockLLMService.create_text_chunks("C'est noté."),
        MockLLMService.create_text_chunks("RELANCE EN TROP"),
    ]
    engine, llm, _, _ = await _jouer(three_node_workflow, _reglages(), etapes)
    assert engine._gathered_context["nom"] == "Dupont"
    assert engine._current_node.id == "start"
    assert llm.get_current_step() == 2


@pytest.mark.asyncio
async def test_D28_allume_l_extraction_par_etape_est_coupee(
    three_node_workflow, no_disposition_mapping
):
    engine, _, _, extraction = await _jouer(
        three_node_workflow, _reglages(), _note_et_porte(["porte"])
    )
    assert engine._current_node.id == "agent"
    extraction.assert_not_called()
    assert "user_name" not in engine._gathered_context


@pytest.mark.asyncio
async def test_T1_1_eteint_l_extraction_par_etape_est_inchangee(
    three_node_workflow, no_disposition_mapping
):
    engine, _, _, extraction = await _jouer(
        three_node_workflow, None, _note_et_porte(["porte"])
    )
    assert engine._current_node.id == "agent"
    await engine._await_pending_extractions()
    extraction.assert_called()


@pytest.mark.asyncio
async def test_T1_5_deux_notes_dans_le_meme_tour_une_seule_relance(
    three_node_workflow, no_disposition_mapping
):
    etapes = [
        MockLLMService.create_multiple_function_call_chunks(
            [
                {
                    "name": NOM_OUTIL,
                    "arguments": {"nom": "Dupont"},
                    "tool_call_id": "n1",
                },
                {
                    "name": NOM_OUTIL,
                    "arguments": {"motif": "Entretien"},
                    "tool_call_id": "n2",
                },
            ]
        ),
        MockLLMService.create_text_chunks("C'est noté."),
        MockLLMService.create_text_chunks("RELANCE EN TROP"),
    ]
    engine, llm, _, _ = await _jouer(
        three_node_workflow, _reglages(), etapes, retard={NOM_OUTIL: 0.05}
    )
    assert engine._gathered_context["nom"] == "Dupont"
    assert engine._gathered_context["motif"] == "Entretien"
    assert llm.get_current_step() == 2
