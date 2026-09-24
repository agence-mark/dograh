"""[.mark] Lot 4 de « la fiche au fil de l'eau » : la fiche de l'agent, et le balayage de fin d'appel.

Plan : `Labo-agent-vocal/plans/2026-09-23-plan-fiche-au-fil-de-leau.md` (D10, D11, D35, D36).

| Test | Ce qu'il prouve |
|---|---|
| T4.1 | Interrupteur allumé : une information donnée dans n'importe quelle étape atteint son champ |
| T4.2 | Le balayage de fin d'appel remplit un champ vide |
| T4.3 | Le balayage n'écrase jamais un champ écrit par l'outil |
| T4.4 | L'extraction par étape ne tourne plus quand l'interrupteur est allumé |
| T4.5 | Interrupteur éteint : l'extraction par étape est inchangée |

T4.4 et T4.5 sont joués sur le vrai pipeline dans `test_outil_noter.py`
(`test_D28_…` et `test_T1_1_eteint_l_extraction_par_etape_est_inchangee`) ; ce
fichier ajoute leur pendant au moment du balayage.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext

from api.services.pipecat.service_factory import stamp_pipeline_settings
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    CONSIGNE_BALAYAGE,
    NOM_OUTIL,
    ReglagesFiche,
    balayer_la_fiche,
    ecrire_dans_la_fiche,
)
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.pipecat_engine_variable_extractor import (
    VariableExtractionManager,
)
from api.tests.mark.test_outil_noter import _jouer
from pipecat.tests import MockLLMService

CONFIG = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom", "description": "Nom de famille"},
        {"nom": "telephone"},
        {"nom": "motif", "origine": "deduit"},
    ],
}
MESSAGES = [
    {"role": "assistant", "content": "Bonjour"},
    {"role": "user", "content": "Monsieur Dupont, je vous appelle pour mon poêle"},
    {"role": "user", "content": "mon numéro c'est 06 12 34 56 78"},
]


def _reglages() -> ReglagesFiche:
    reglages = ReglagesFiche.depuis(CONFIG)
    assert reglages is not None
    return reglages


class Extracteur:
    """L'extraction de Dograh, remplacée : rend ce qu'on lui dit, garde ce qu'on lui a demandé."""

    def __init__(self, reponse: dict):
        self.reponse = reponse
        self.appels: list[tuple[list[str], str]] = []

    async def __call__(self, variables, consigne):
        self.appels.append(([v.name for v in variables], consigne))
        return dict(self.reponse)


# --- T4.1 : n'importe quelle étape -------------------------------------------


@pytest.mark.asyncio
async def test_T4_1_une_note_faite_a_une_autre_etape_atteint_son_champ(
    three_node_workflow, no_disposition_mapping
):
    """La porte d'abord (on quitte l'accueil), puis la note à l'étape suivante."""
    etapes = [
        MockLLMService.create_function_call_chunks(
            function_name="collect_info", arguments={}, tool_call_id="porte_1"
        ),
        MockLLMService.create_function_call_chunks(
            function_name=NOM_OUTIL, arguments={"nom": "Dupont"}, tool_call_id="note_1"
        ),
        MockLLMService.create_text_chunks("C'est noté."),
        MockLLMService.create_text_chunks("RELANCE EN TROP"),
    ]
    engine, llm, outils_vus, _ = await _jouer(three_node_workflow, _reglages(), etapes)
    assert engine._current_node.id == "agent"
    assert engine._gathered_context["nom"] == "Dupont"
    assert llm.get_current_step() == 3


# --- T4.2 et T4.3 : le balayage ----------------------------------------------


@pytest.mark.asyncio
async def test_T4_2_le_balayage_remplit_un_champ_vide():
    fiche: dict = {}
    extraire = Extracteur({"telephone": "0612345678", "motif": "Poêle en panne"})
    ecrits = await balayer_la_fiche(_reglages(), extraire, fiche, MESSAGES)
    assert ecrits == {"telephone": "0612345678", "motif": "Poêle en panne"}
    assert fiche["telephone"] == "0612345678"
    assert fiche["fiche_etat"]["telephone"]["source"] == "balayage"
    assert extraire.appels[0][1] == CONSIGNE_BALAYAGE


@pytest.mark.asyncio
async def test_T4_3_le_balayage_n_ecrase_jamais_l_outil_et_ne_redemande_que_les_vides():
    fiche: dict = {}
    ecrire_dans_la_fiche(fiche, _reglages(), "nom", "Dupont", paroles=["Dupont"])
    extraire = Extracteur({"nom": "Durand", "telephone": "0612345678"})
    await balayer_la_fiche(_reglages(), extraire, fiche, MESSAGES)
    assert fiche["nom"] == "Dupont"
    # Seuls les champs vides sont demandés à l'extraction.
    assert extraire.appels[0][0] == ["telephone", "motif"]


@pytest.mark.asyncio
async def test_le_balayage_passe_par_les_memes_controles():
    """D35 : un nom que personne n'a dit est refusé, même venu du balayage."""
    fiche: dict = {}
    await balayer_la_fiche(_reglages(), Extracteur({"nom": "Durand"}), fiche, MESSAGES)
    assert "nom" not in fiche
    assert fiche[CLE_JOURNAL][-1]["raison"] == "non_dit"


@pytest.mark.asyncio
async def test_fiche_pleine_aucun_appel_au_modele():
    fiche: dict = {}
    for champ, valeur in [
        ("nom", "Dupont"),
        ("telephone", "06 12 34 56 78"),
        ("motif", "x"),
    ]:
        ecrire_dans_la_fiche(
            fiche, _reglages(), champ, valeur, paroles=[m["content"] for m in MESSAGES]
        )
    extraire = Extracteur({})
    assert await balayer_la_fiche(_reglages(), extraire, fiche, MESSAGES) == {}
    assert extraire.appels == []


@pytest.mark.asyncio
async def test_A4_un_champ_deduit_qui_recopie_un_autre_champ_est_refuse():
    """Run 837 : `symptome` recevait la phrase d'appel, déjà notée dans
    `verbatim_demande`. Un champ déduit n'a pas de contrôle de citation : la
    recopie d'un champ déjà rempli est refusée, et le refus est au journal."""
    fiche = {"telephone": "0612345678"}
    reglages = ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": [
                {"nom": "verbatim", "origine": "dicte"},
                {"nom": "telephone", "origine": "dicte"},
                {"nom": "symptome", "origine": "deduit"},
            ],
        }
    )
    ecrire_dans_la_fiche(
        fiche,
        reglages,
        "verbatim",
        "J'appelle pour l'entretien de mon poêle à granulés",
        paroles=["J'appelle pour l'entretien de mon poêle à granulés"],
    )
    extraire = Extracteur(
        {"symptome": "J'appelle pour l'entretien de mon poêle à granulés"}
    )
    assert await balayer_la_fiche(reglages, extraire, fiche, MESSAGES) == {}
    assert "symptome" not in fiche
    assert fiche[CLE_JOURNAL][-1]["raison"] == "recopie_de_verbatim"


def test_A4_la_consigne_du_balayage_ecarte_ce_qui_ne_correspond_pas():
    assert "« tout fonctionne » ne décrit aucun problème" in CONSIGNE_BALAYAGE
    assert "Ne mets jamais la même phrase dans deux variables" in CONSIGNE_BALAYAGE


# --- Le déclenchement, par le moteur (D36) -----------------------------------


def _moteur(workflow, fiche):
    context = LLMContext()
    for message in MESSAGES:
        context.add_message(message)
    engine = PipecatEngine(
        llm=MockLLMService(),
        context=context,
        workflow=workflow,
        call_context_vars={},
        workflow_run_id=1,
        fiche=fiche,
    )
    engine._variable_extraction_manager = VariableExtractionManager(engine)
    engine._current_node = workflow.nodes["agent"]
    return engine


@pytest.mark.asyncio
async def test_T4_2_le_moteur_balaye_en_fin_d_appel(three_node_workflow):
    engine = _moteur(three_node_workflow, _reglages())
    with patch.object(
        VariableExtractionManager,
        "_perform_extraction",
        new_callable=AsyncMock,
        return_value={"telephone": "0612345678", "user_name": "HORS FICHE"},
    ) as extraction:
        await engine.perform_final_variable_extraction()
    assert engine._gathered_context["telephone"] == "0612345678"
    # Seuls les champs de la fiche sont demandés, jamais les variables de l'étape.
    demandes = [v.name for v in extraction.call_args.args[0]]
    assert demandes == ["nom", "telephone", "motif"]
    assert "user_name" not in engine._gathered_context


@pytest.mark.asyncio
async def test_T4_4_allume_un_changement_d_etape_ne_relit_rien(three_node_workflow):
    engine = _moteur(three_node_workflow, _reglages())
    with patch.object(
        VariableExtractionManager, "_perform_extraction", new_callable=AsyncMock
    ) as extraction:
        await engine._perform_variable_extraction_if_needed(
            engine._current_node, run_in_background=False
        )
    extraction.assert_not_called()


@pytest.mark.asyncio
async def test_T4_5_eteint_la_fin_d_appel_relit_l_etape_comme_avant(
    three_node_workflow,
):
    engine = _moteur(three_node_workflow, None)
    with patch.object(
        VariableExtractionManager,
        "_perform_extraction",
        new_callable=AsyncMock,
        return_value={"user_name": "Dupont"},
    ) as extraction:
        await engine.perform_final_variable_extraction()
    assert [v.name for v in extraction.call_args.args[0]] == ["user_name"]
    assert engine._gathered_context["user_name"] == "Dupont"


# --- L'estampille : un appel dit s'il a joué avec la fiche --------------------


def test_l_interrupteur_et_la_fiche_sont_estampilles_en_json():
    estampille = stamp_pipeline_settings({}, CONFIG)["pipeline_settings"]
    assert estampille["fiche_au_fil_de_leau"] is True
    assert [c["nom"] for c in estampille["fiche_champs"]] == [
        "nom",
        "telephone",
        "motif",
    ]
    # Estampillé tel que réglé : vide = « d'après le nom ».
    assert estampille["fiche_champs"][0]["lecteur"] is None
    json.dumps(estampille)  # stocké en base : doit passer en JSON
    eteint = stamp_pipeline_settings({}, {})["pipeline_settings"]
    assert eteint["fiche_au_fil_de_leau"] is False and eteint["fiche_champs"] == []


@pytest.mark.asyncio
async def test_A8_en_fin_d_appel_le_numero_en_conflit_est_marque_a_verifier():
    """Run 837 : la fiche gardait 06 12 34 56 68, la personne avait dicté le 78
    en dernier. Le balayage ne l'écrase pas (D11), il le marque à vérifier."""
    fiche = {
        "telephone": "0612345668",
        "fiche_etat": {"telephone": {"sure": True, "source": "outil"}},
        "nombres_lus": [
            {"type": "telephone", "ecrit": "06 12 34 56 68"},
            {"type": "telephone", "ecrit": "06 12 34 56 78"},
        ],
    }
    await balayer_la_fiche(_reglages(), Extracteur({}), fiche, MESSAGES)
    assert fiche["telephone"] == "0612345668"
    assert fiche["fiche_etat"]["telephone"]["sure"] is False
    (entree,) = [e for e in fiche[CLE_JOURNAL] if e["statut"] == "a_verifier"]
    assert entree["dernier_dicte"] == "0612345678"
    # Un deuxième passage (routage d'un transfert) ne double pas le journal.
    await balayer_la_fiche(_reglages(), Extracteur({}), fiche, MESSAGES)
    assert len([e for e in fiche[CLE_JOURNAL] if e["statut"] == "a_verifier"]) == 1
