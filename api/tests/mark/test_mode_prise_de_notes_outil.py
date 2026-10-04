"""[.mark] Le mode outil à l'identique, et `noter` partagé par tous les modes (plan mode-prise-de-notes, lot 2).

Plan `Labo-agent-vocal/plans/mode-prise-de-notes/`. Le cœur du gestionnaire de l'outil est extrait
en une fonction `noter` : l'outil, le post-scriptum et le greffier passent par UNE seule copie des
contrôles. L'outil et la relance unique par tour ne sont branchés qu'en mode outil ; l'état de la
fiche et la passe de fin restent dans tous les modes.

| Test | Ce qu'il prouve |
|---|---|
| corpus | sur les vrais tours des runs 861 à 904, `noter` appelé directement (source `post_scriptum`) donne la même fiche que l'outil, à la source près |
| moteur | outil : relance unique branchée ; post-scriptum : pas de relance, mais l'état de la fiche est montré au modèle |
| clavier, outil absent | en post-scriptum, par les vraies routes, un appel à `noter_information` n'écrit rien : l'outil n'est pas proposé |
| clavier, passe de fin | en post-scriptum, la passe de fin d'appel remplit toujours un champ vide |

Le rejeu 861-904 identique octet pour octet à la référence du lot 0 est vérifié à chaque étape
(journal du chantier) : c'est la preuve que le mode outil n'a pas bougé.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_JOURNAL,
    CLE_MODE,
    ENTETE_ETAT,
    MODE_OUTIL,
    MODE_POST_SCRIPTUM,
    ReglagesFiche,
    derniere_question,
    ecrire_dans_la_fiche,
    noter,
    paroles_de_l_appelant,
    reponse_de_l_outil,
)
from api.tests.mark import rejeu_corpus
from api.tests.mark.test_clavier_porte_la_fiche import (
    FICHE,
    _converser,
    _monter,
    _noter,
)
from api.tests.mark.test_fiche_montree import (
    PAROLE,
    PROMPT,
    _contexte,
    _mistral,
    _moteur,
    _requete,
)
from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE
from pipecat.tests import MockLLMService

DONNEES = Path(rejeu_corpus.__file__).parent / "donnees"


# --------------------------------------------------------------------------- #
# 1. Sur le corpus réel : `noter` = l'outil
# --------------------------------------------------------------------------- #


def _sans_source(fiche: dict) -> dict:
    """La fiche, la source du journal et de l'état mise de côté : c'est la
    seule chose qui doit différer d'un mode à l'autre."""
    copie = dict(fiche)
    copie[CLE_JOURNAL] = [
        {k: v for k, v in e.items() if k != "source"}
        for e in fiche.get(CLE_JOURNAL) or []
    ]
    copie[CLE_ETAT] = {
        champ: {k: v for k, v in e.items() if k != "source"}
        for champ, e in (fiche.get(CLE_ETAT) or {}).items()
    }
    return copie


def _gestionnaire_direct(reglages, fiche, messages, suivi=None):
    """Ce que fera le post-scriptum : `noter` sans passer par l'outil."""

    async def gestionnaire(params):
        lus = list(messages())
        note = await noter(
            fiche,
            reglages,
            dict(params.arguments or {}),
            paroles=paroles_de_l_appelant(lus),
            question=derniere_question(lus),
            source=MODE_POST_SCRIPTUM,
        )
        await params.result_callback(reponse_de_l_outil(note))

    return gestionnaire


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corpus",
    ["rejeu_runs_861_881.json", "rejeu_runs_882_895.json", "rejeu_runs_899_904.json"],
)
async def test_noter_donne_la_meme_fiche_que_l_outil_sur_le_corpus(corpus):
    donnees = rejeu_corpus.charger(DONNEES / corpus)
    ecrites = 0
    for run in donnees["runs"]:
        par_l_outil = await rejeu_corpus.rejouer_run(run, donnees)
        with patch.object(rejeu_corpus, "creer_gestionnaire", _gestionnaire_direct):
            en_direct = await rejeu_corpus.rejouer_run(run, donnees)
        assert _sans_source(en_direct["fiche"]) == _sans_source(par_l_outil["fiche"]), (
            run["id"]
        )
        # Les mêmes réponses, tour par tour : les notices du lot 3 en dépendent.
        assert [t["resultats"] for t in en_direct["tours"]] == [
            t["resultats"] for t in par_l_outil["tours"]
        ], run["id"]
        # Et la source dit qui a écrit.
        notes = [
            e for e in en_direct["fiche"].get(CLE_JOURNAL) or [] if e.get("source")
        ]
        assert all(
            e["source"] in (MODE_POST_SCRIPTUM, "balayage", "rue", "commune")
            for e in notes
        )
        ecrites += sum(e["source"] == MODE_POST_SCRIPTUM for e in notes)
    assert ecrites > 0


# --------------------------------------------------------------------------- #
# 2. Le moteur, selon le mode
# --------------------------------------------------------------------------- #


def _reglages(mode: str) -> ReglagesFiche:
    reglages = ReglagesFiche.depuis({**CONFIG_ALLUMEE, CLE_MODE: mode})
    assert reglages is not None and reglages.mode == mode
    return reglages


def test_en_mode_outil_la_relance_unique_est_branchee(three_node_workflow):
    llm = _mistral()
    engine = _moteur(three_node_workflow, llm, _contexte(), _reglages(MODE_OUTIL))
    assert engine._tours_fiche is not None


@pytest.mark.asyncio
async def test_en_post_scriptum_pas_de_relance_mais_l_etat_est_montre(
    three_node_workflow,
):
    llm = _mistral()
    context = _contexte({"role": "user", "content": PAROLE})
    engine = _moteur(three_node_workflow, llm, context, _reglages(MODE_POST_SCRIPTUM))
    assert engine._tours_fiche is None
    ecrire_dans_la_fiche(
        engine._gathered_context,
        _reglages(MODE_POST_SCRIPTUM),
        "nom",
        "Dupont",
        paroles=[PAROLE],
    )
    envoyes = await _requete(llm, context)
    assert envoyes[0] == {"role": "system", "content": PROMPT}
    assert envoyes[-2]["content"].startswith(ENTETE_ETAT[:20])
    assert "Noté : nom = « Dupont »" in envoyes[-2]["content"]


# --------------------------------------------------------------------------- #
# 3. Au clavier, par les vraies routes
# --------------------------------------------------------------------------- #

POST_SCRIPTUM = {**FICHE, CLE_MODE: MODE_POST_SCRIPTUM}


@pytest.mark.asyncio
async def test_en_post_scriptum_l_outil_n_est_pas_propose(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, POST_SCRIPTUM)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            _noter({"nom": "Lemaire"}, "note_1"),
            MockLLMService.create_text_chunks("Merci."),
        ],
        "je m'appelle Lemaire",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert "nom" not in fiche, fiche


@pytest.mark.asyncio
async def test_en_post_scriptum_la_passe_de_fin_remplit_un_champ_vide(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, POST_SCRIPTUM)
    demandes = []

    async def extraction(_gestionnaire, variables, _contexte_parent, consigne, *a, **k):
        demandes.append(sorted(v.name for v in variables))
        return {"nom": "Lemaire"}

    with patch(
        "api.services.workflow.pipecat_engine_variable_extractor."
        "VariableExtractionManager._perform_extraction",
        new=extraction,
    ):
        _, run_id = await _converser(
            test_client_factory,
            user,
            workflow,
            [MockLLMService.create_text_chunks("Très bien, et votre nom ?")],
            "c'est Lemaire pour un entretien",
            finir=True,
        )
    assert demandes == [["motif", "nom"]], demandes
    run = await db_session.get_workflow_run_by_id(run_id)
    contexte = run.gathered_context or {}
    assert contexte.get("nom") == "Lemaire", contexte
    assert any(
        e.get("champ") == "nom" and e.get("source") == "balayage"
        for e in contexte.get(CLE_JOURNAL) or []
    ), contexte.get(CLE_JOURNAL)
