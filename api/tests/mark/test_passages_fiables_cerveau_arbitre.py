"""[.mark] passages-fiables, lot B : le cerveau de l'arbitre, au niveau de l'agent, sur le modèle exact du greffier.

Plan `Labo-agent-vocal/plans/passages-fiables/` (§ 7). Le bloc `arbitre_llm` de la configuration de l'agent porte le modèle
de l'arbitre au format d'une surcharge de modèle. Sa clé est masquée dans toutes les réponses, remise à sa vraie valeur
quand l'écran renvoie le masque, résolue depuis la bibliothèque de clés. Bloc absent : l'arbitre suit le greffier, sinon la
conversation (comportement d'avant, à l'octet).

| Test | Ce qu'il prouve |
|---|---|
| masque | la réponse de l'API ne montre jamais la clé de l'arbitre |
| aller-retour | un enregistrement qui renvoie le masque garde la vraie clé ; une clé tapée remplace l'ancienne |
| masque orphelin | un masque sans clé à retrouver est refusé (422), le message nomme l'arbitre |
| forme | un bloc mal formé est refusé (422) ; les réglages du fournisseur nommé sont acceptés |
| bibliothèque | une référence de clé est résolue ; introuvable ou d'un autre fournisseur, elle reste et la configuration la refuse |
| bloc absent | rien n'est construit, aucune estampille : l'arbitre suit le greffier, sinon la conversation |
| bloc réglé | le service est construit à part (`usage_context="arbitre"`), estampille sans clé ; en échec, le greffier est gardé |
| priorité | service propre, sinon service du greffier, sinon cerveau de conversation |
| chemins | téléphone et clavier résolvent le bloc, construisent le service et le passent au décideur |
| thème | la clé est classée dans « Données de l'appel » des modèles de réglages |
"""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services.configuration.masking import MASK_MARKER, mask_workflow_configurations
from api.services.workflow import arbitre as module
from api.services.workflow.arbitre import (
    CLE_ESTAMPILLE,
    ArbitreDuPassage,
    bloc_regle,
    configuration_de_l_arbitre,
    preparer_l_arbitre,
    resoudre_le_bloc_de_l_arbitre,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE
from api.tests.mark.test_horaires_ouverture_reglage import _enregistrer

CLE = "cle-de-test-de-l-arbitre-0123456789"
BLOC = {"provider": "mistral", "model": "mistral-small-latest", "api_key": CLE}
EXISTANTES = {**FICHE, "arbitre_llm": BLOC}
REF = "mark-cle:343322ca-f4d1-4806-8bf6-b2c7ed904a4a"
SCALEWAY = "https://api.scaleway.ai/v1"


def _masque() -> str:
    return mask_workflow_configurations(EXISTANTES)["arbitre_llm"]["api_key"]


def test_la_reponse_masque_la_cle_de_l_arbitre():
    masque = mask_workflow_configurations(EXISTANTES)
    assert MASK_MARKER in masque["arbitre_llm"]["api_key"] and CLE not in str(masque)
    assert masque["arbitre_llm"]["model"] == "mistral-small-latest"
    assert EXISTANTES["arbitre_llm"]["api_key"] == CLE


def test_le_masque_renvoye_garde_la_vraie_cle_et_une_cle_tapee_la_remplace():
    reponse, ecrit = _enregistrer({**EXISTANTES, "arbitre_llm": {**BLOC, "api_key": _masque()}}, existantes=EXISTANTES)
    assert reponse.status_code == 200, reponse.text
    assert ecrit["arbitre_llm"]["api_key"] == CLE
    reponse, ecrit = _enregistrer(
        {**EXISTANTES, "arbitre_llm": {**BLOC, "api_key": "une-autre-cle-9876543210"}}, existantes=EXISTANTES
    )
    assert reponse.status_code == 200 and ecrit["arbitre_llm"]["api_key"] == "une-autre-cle-9876543210"


@pytest.mark.parametrize(
    "existantes", [{}, {**EXISTANTES, "arbitre_llm": {**BLOC, "provider": "openai"}}], ids=["rien-en-base", "autre-fournisseur"]
)
def test_un_masque_orphelin_est_refuse_et_rien_n_est_ecrit(existantes):
    reponse, ecrit = _enregistrer({**EXISTANTES, "arbitre_llm": {**BLOC, "api_key": _masque()}}, existantes=existantes)
    assert reponse.status_code == 422, reponse.text
    assert "arbiter's API key is masked" in reponse.text and ecrit is None


def test_une_cle_vide_reste_vide():
    reponse, ecrit = _enregistrer(
        {**EXISTANTES, "arbitre_llm": {"provider": "mistral", "model": "m"}}, existantes=EXISTANTES
    )
    assert reponse.status_code == 200 and "api_key" not in ecrit["arbitre_llm"]


@pytest.mark.parametrize(
    "bloc",
    [
        {"model": 12},
        {"provider": ["mistral"]},
        {"temperature": "chaud"},
        {"provider": "mistrall"},
        {"max_tokens": 50},
        {"provider": "openai", "inconnu": 1},
        {"provider": "openai", "max_tokens": 0},
        {"provider": "openai", "format_garanti": True},  # la case du greffier n'existe pas ici
        {"api_key": {"cle": "objet"}},
    ],
)
def test_un_bloc_mal_forme_est_refuse(bloc):
    reponse, ecrit = _enregistrer({**EXISTANTES, "arbitre_llm": bloc})
    assert reponse.status_code == 422, reponse.text
    assert ecrit is None


def test_les_reglages_du_fournisseur_nomme_sont_acceptes():
    bloc = {
        "provider": "openai",
        "model": "mistral-small-3.2-24b-instruct-2506",
        "base_url": SCALEWAY,
        "reasoning_effort": "low",
        "max_tokens": 200,
        "api_key": REF,
    }
    reponse, ecrit = _enregistrer({**EXISTANTES, "arbitre_llm": bloc})
    assert reponse.status_code == 200, reponse.text
    assert ecrit["arbitre_llm"]["base_url"] == SCALEWAY


def _conversation():
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration

    return EffectiveAIModelConfiguration.model_validate(
        {"llm": {"provider": "mistral", "model": "mistral-large-2512", "api_key": "cle-conv"}}
    )


def _patch_cle(retour):
    return patch("api.services.cles_reference._cle", AsyncMock(return_value=retour))


BLOC_BIBLIOTHEQUE = {
    "provider": "openai",
    "model": "mistral-small-3.2-24b-instruct-2506",
    "base_url": SCALEWAY,
    "reasoning_effort": "low",
    "api_key": REF,
}


@pytest.mark.asyncio
async def test_la_reference_est_remplacee_par_la_cle_de_l_organisation():
    run_configs = {"arbitre_llm": dict(BLOC_BIBLIOTHEQUE), "autre": 1}
    with _patch_cle(("vraie-cle-scaleway", "openai")) as lecture:
        rendu = await resoudre_le_bloc_de_l_arbitre(run_configs, 2)
    lecture.assert_awaited_once_with(REF.split(":", 1)[1], 2)
    assert rendu["arbitre_llm"]["api_key"] == "vraie-cle-scaleway" and rendu["autre"] == 1
    assert run_configs["arbitre_llm"]["api_key"] == REF


@pytest.mark.asyncio
@pytest.mark.parametrize("retour", [None, ("cle-mistral", "mistral")])
async def test_introuvable_ou_autre_fournisseur_la_reference_reste_et_la_configuration_la_refuse(retour):
    with _patch_cle(retour):
        rendu = await resoudre_le_bloc_de_l_arbitre({"arbitre_llm": dict(BLOC_BIBLIOTHEQUE)}, 2)
    assert rendu["arbitre_llm"]["api_key"] == REF
    with pytest.raises(ValueError):
        configuration_de_l_arbitre(_conversation(), rendu["arbitre_llm"])
    # L'appel ne casse pas : le greffier est gardé, aucune référence n'est envoyée au fournisseur.
    assert preparer_l_arbitre(rendu, _conversation(), {}) is None


def test_l_arbitre_part_chez_scaleway_avec_ses_reglages():
    llm = configuration_de_l_arbitre(_conversation(), {**BLOC_BIBLIOTHEQUE, "api_key": "vraie"}).llm
    assert (llm.provider, llm.model, llm.base_url) == ("openai", BLOC_BIBLIOTHEQUE["model"], SCALEWAY)
    assert llm.reasoning_effort == "low" and llm.api_key == "vraie"


@pytest.mark.parametrize(
    "configs", [None, {}, {"arbitre_llm": None}, {"arbitre_llm": {}}, {"arbitre_llm": {"model": "", "api_key": None}}]
)
def test_bloc_absent_ou_vide_rien_n_est_construit_aucune_estampille(configs):
    estampilles: dict = {}
    with patch("api.services.pipecat.service_factory.create_llm_service") as fabrique:
        assert preparer_l_arbitre(configs, _conversation(), estampilles) is None
    fabrique.assert_not_called()
    assert estampilles == {} and not bloc_regle(configs)


def test_bloc_regle_le_service_est_construit_a_part_pour_le_cout_de_l_arbitre():
    estampilles: dict = {}
    service = object()
    with patch("api.services.pipecat.service_factory.create_llm_service", return_value=service) as fabrique:
        rendu = preparer_l_arbitre(
            {"arbitre_llm": {**BLOC_BIBLIOTHEQUE, "api_key": "vraie"}}, _conversation(), estampilles, correlation_id="c1"
        )
    assert rendu is service
    assert fabrique.call_args.kwargs["usage_context"] == "arbitre" and fabrique.call_args.kwargs["correlation_id"] == "c1"
    assert estampilles[CLE_ESTAMPILLE] == {"provider": "openai", "model": BLOC_BIBLIOTHEQUE["model"]}
    assert "vraie" not in str(estampilles)


def test_un_service_qui_ne_se_construit_pas_laisse_le_greffier():
    with patch("api.services.pipecat.service_factory.create_llm_service", side_effect=RuntimeError("boum")):
        assert preparer_l_arbitre({"arbitre_llm": dict(BLOC)}, _conversation(), {}) is None


def test_le_service_de_l_arbitre_est_le_sien_sinon_celui_du_greffier_sinon_la_conversation():
    greffier, conversation = SimpleNamespace(_service="greffier"), "conversation"
    moteur = SimpleNamespace(greffier=greffier, active_agent=SimpleNamespace(llm=conversation))
    assert ArbitreDuPassage(moteur)._service() == "greffier"
    moteur.arbitre_service = "propre"
    assert ArbitreDuPassage(moteur)._service() == "propre"
    moteur = SimpleNamespace(greffier=None, active_agent=SimpleNamespace(llm=conversation))
    assert ArbitreDuPassage(moteur)._service() == "conversation"


def test_le_decideur_garde_le_service_propre_et_sans_bloc_ne_touche_a_rien():
    from api.services.workflow.decideur_de_fin_de_tour import brancher_le_decideur_de_fin_de_tour
    from api.tests.mark.test_filet_de_fin import _Agregateur

    for service in (None, "propre"):
        moteur = SimpleNamespace(context=None, arbitre=None)
        brancher_le_decideur_de_fin_de_tour(moteur, _Agregateur(), service)
        assert getattr(moteur, "arbitre_service", None) == service


def test_les_deux_chemins_resolvent_construisent_et_passent_le_service_au_decideur():
    from api.services.pipecat import run_pipeline
    from api.services.workflow import text_chat_runner

    for mod in (run_pipeline, text_chat_runner):
        source = inspect.getsource(mod)
        assert "await resoudre_le_bloc_de_l_arbitre(run_configs, workflow.organization_id)" in source, mod.__name__
        assert "preparer_l_arbitre(" in source, mod.__name__
        assert "brancher_le_decideur_de_fin_de_tour(engine, assistant_context_aggregator, service_arbitre)" in source, mod.__name__


def test_la_cle_est_classee_dans_les_donnees_de_l_appel_a_cote_du_greffier():
    from api.services.groupe.reglages import CLES_THEME_DONNEES

    assert "arbitre_llm" in CLES_THEME_DONNEES
    assert CLES_THEME_DONNEES.index("arbitre_llm") == CLES_THEME_DONNEES.index("greffier_llm") + 1
    assert module.CLE_LLM == "arbitre_llm"
