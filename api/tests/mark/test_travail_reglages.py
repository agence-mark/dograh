"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D10, D13) : les réglages du cerveau de fond.

Cinq clés JSON (aucune migration) : ``travail_actif``, ``travail_llm``, ``travail_consigne``,
``travail_outils``, ``travail_delai_max_s``. Éteintes ou vides par défaut : un agent qui n'en a
aucune joue l'appel d'avant, à l'octet.

| Test | La garantie |
|---|---|
| défauts | sans réglage, rien n'est allumé ; la consigne par défaut est vide (à rédiger avec Evan) |
| lecture | les réglages posés sont lus ; un réglage illisible = éteint, jamais une exception |
| forme | un bloc de modèle, une liste d'outils ou un délai mal formés sont refusés (422) |
| clé | la clé du modèle du fond est masquée dans l'API, rendue au retour du masque, refusée si orpheline |
| groupe | les cinq clés sont communes ET suivent le cerveau : « Cerveau propre » garde les siennes |
| outils | le fond ne reçoit jamais un transfert, une passation, la fin d'appel, ni une action qui transfère |
| moteur muet | les phrases d'outil (patience, message, repli) ne sont jamais dites par le fond |
| modèle du fond | bloc vide = le cerveau de conversation de l'agent ; bloc réglé = surcharge ; clé de bibliothèque résolue |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from api.enums import ToolCategory
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.configuration.masking import MASK_MARKER, mask_workflow_configurations
from api.services.groupe.reglages import (
    CLES_COMMUNES,
    CLES_SUIVENT_LE_CERVEAU,
    recopier,
)
from api.services.travail.fabrique import (
    CLE_ESTAMPILLE,
    configuration_du_travail,
    preparer_le_service_du_travail,
    resoudre_le_bloc_du_travail,
    service_du_travail,
)
from api.services.travail.outils import (
    MoteurDeFond,
    outil_permis_au_fond,
    preparer_les_outils,
    uuids_permis,
)
from api.services.travail.reglages import (
    CLE_ACTIF,
    CLE_CONSIGNE,
    CLE_DELAI,
    CLE_LLM,
    CLE_OUTILS,
    CLES_DU_TRAVAIL,
    CONSIGNE_PAR_DEFAUT,
    ReglagesTravail,
)
from api.services.workflow.tools.custom_tool import tool_to_function_schema
from api.tests.mark.test_clavier_porte_la_fiche import FICHE
from api.tests.mark.test_horaires_ouverture_reglage import _enregistrer

CLE = "cle-de-test-du-fond-0123456789"
BLOC = {"provider": "mistral", "model": "mistral-large-2512", "api_key": CLE}
EXISTANTES = {**FICHE, CLE_ACTIF: True, CLE_LLM: BLOC}


# --------------------------------------------------------------------------- #
# Défauts et lecture
# --------------------------------------------------------------------------- #


def test_sans_reglage_rien_n_est_allume_et_la_consigne_est_vide():
    defauts = WorkflowConfigurationDefaults()
    assert defauts.travail_actif is False
    assert defauts.travail_llm is None
    assert defauts.travail_consigne is None
    assert defauts.travail_outils == []
    assert defauts.travail_delai_max_s == 60
    assert ReglagesTravail.depuis(None) == ReglagesTravail()
    assert ReglagesTravail.depuis({}).actif is False
    # La consigne n'est écrite par personne dans le code : à rédiger avec Evan.
    assert CONSIGNE_PAR_DEFAUT == ""
    assert ReglagesTravail.depuis({CLE_ACTIF: True}).consigne == ""


def test_les_reglages_poses_sont_lus():
    lus = ReglagesTravail.depuis(
        {
            CLE_ACTIF: True,
            CLE_LLM: {"provider": "openai", "model": "x"},
            CLE_CONSIGNE: "  Fais la demande.  ",
            CLE_OUTILS: ["a", "b", "a"],
            CLE_DELAI: 90,
        }
    )
    assert lus.actif is True
    assert lus.llm == {"provider": "openai", "model": "x"}
    assert lus.consigne == "Fais la demande."
    assert lus.outils == ("a", "b")  # sans doublon, ordre gardé
    assert lus.delai_max_s == 90


def test_les_reglages_ne_comptent_que_case_allumee():
    """Éteint : les autres réglages, même posés, ne font rien (aucun fond)."""
    lus = ReglagesTravail.depuis({CLE_ACTIF: False, CLE_OUTILS: ["a"], CLE_DELAI: 90})
    assert lus == ReglagesTravail()
    assert ReglagesTravail.depuis({CLE_ACTIF: "oui"}).actif is False


@pytest.mark.parametrize(
    "illisible",
    [
        {CLE_ACTIF: True, CLE_DELAI: 3},
        {CLE_ACTIF: True, CLE_DELAI: "long"},
        {CLE_ACTIF: True, CLE_OUTILS: "pas une liste"},
        {CLE_ACTIF: True, CLE_LLM: {"inconnu": 1}},
    ],
)
def test_un_reglage_illisible_eteint_le_fond_sans_lever(illisible):
    assert ReglagesTravail.depuis(illisible).actif is False


# --------------------------------------------------------------------------- #
# Forme : l'enregistrement refuse ce qui est mal formé
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bloc",
    [
        {"model": 12},
        {"provider": ["mistral"]},
        {"temperature": "chaud"},
        {"provider": "mistrall"},
        {"max_tokens": 50},
        {"provider": "openai", "inconnu": 1},
        {"provider": "openai", "reasoning_effort": "turbo"},
        {"api_key": {"cle": "objet"}},
        {"temperature": True},
    ],
)
def test_un_bloc_de_modele_mal_forme_est_refuse(bloc):
    reponse, ecrit = _enregistrer({**EXISTANTES, CLE_LLM: bloc})
    assert reponse.status_code == 422, reponse.text
    assert "travail_llm" in reponse.text
    assert ecrit is None


@pytest.mark.parametrize(
    "champ, valeur",
    [
        (CLE_DELAI, 4),
        (CLE_DELAI, 301),
        (CLE_DELAI, "soixante"),
        (CLE_OUTILS, "pas une liste"),
        (CLE_OUTILS, ["a", 5]),
        (CLE_OUTILS, [""]),
    ],
)
def test_un_delai_ou_une_liste_d_outils_mal_formes_sont_refuses(champ, valeur):
    reponse, ecrit = _enregistrer({**EXISTANTES, champ: valeur})
    assert reponse.status_code == 422, reponse.text
    assert ecrit is None


def test_les_reglages_du_fournisseur_nomme_sont_acceptes_comme_au_greffier():
    bloc = {
        "provider": "openai",
        "model": "openai/gpt-oss-120b:fp4",
        "base_url": "https://api.scaleway.ai/v1",
        "api": "responses",
        "reasoning_effort": "low",
        "api_key": "mark-cle:343322ca-f4d1-4806-8bf6-b2c7ed904a4a",
    }
    reponse, ecrit = _enregistrer(
        {**EXISTANTES, CLE_LLM: bloc, CLE_OUTILS: ["u1", "u2"], CLE_DELAI: 120, CLE_CONSIGNE: "Consigne."}
    )
    assert reponse.status_code == 200, reponse.text
    assert ecrit[CLE_LLM] == bloc
    assert ecrit[CLE_OUTILS] == ["u1", "u2"]
    assert ecrit[CLE_DELAI] == 120
    assert ecrit[CLE_CONSIGNE] == "Consigne."


def test_un_enregistrement_sans_travail_n_ajoute_aucune_cle():
    """Zéro perte : la charge utile d'un agent qui ne règle pas le fond reste celle d'avant."""
    reponse, ecrit = _enregistrer({**FICHE})
    assert reponse.status_code == 200, reponse.text
    assert not [cle for cle in ecrit if cle in CLES_DU_TRAVAIL]


# --------------------------------------------------------------------------- #
# La clé du modèle du fond
# --------------------------------------------------------------------------- #


def _masque() -> str:
    return mask_workflow_configurations(EXISTANTES)[CLE_LLM]["api_key"]


def test_la_reponse_masque_la_cle_du_fond():
    masque = mask_workflow_configurations(EXISTANTES)
    assert MASK_MARKER in masque[CLE_LLM]["api_key"]
    assert CLE not in str(masque)
    assert masque[CLE_LLM]["model"] == "mistral-large-2512"
    assert EXISTANTES[CLE_LLM]["api_key"] == CLE  # l'original n'est pas touché


def test_le_masque_renvoye_garde_la_vraie_cle():
    entrant = {**EXISTANTES, CLE_LLM: {**BLOC, "api_key": _masque()}}
    reponse, ecrit = _enregistrer(entrant, existantes=EXISTANTES)
    assert reponse.status_code == 200, reponse.text
    assert ecrit[CLE_LLM]["api_key"] == CLE


def test_une_cle_tapee_remplace_l_ancienne():
    nouvelle = "une-autre-cle-de-test-9876543210"
    reponse, ecrit = _enregistrer(
        {**EXISTANTES, CLE_LLM: {**BLOC, "api_key": nouvelle}}, existantes=EXISTANTES
    )
    assert reponse.status_code == 200, reponse.text
    assert ecrit[CLE_LLM]["api_key"] == nouvelle


@pytest.mark.parametrize(
    "existantes",
    [{}, {**EXISTANTES, CLE_LLM: {**BLOC, "provider": "openai"}}],
    ids=["rien-en-base", "autre-fournisseur"],
)
def test_un_masque_orphelin_est_refuse_et_rien_n_est_ecrit(existantes):
    entrant = {**EXISTANTES, CLE_LLM: {**BLOC, "api_key": _masque()}}
    reponse, ecrit = _enregistrer(entrant, existantes=existantes)
    assert reponse.status_code == 422, reponse.text
    assert "background brain's API key is masked" in reponse.text
    assert ecrit is None


def test_les_deux_cles_propres_se_rendent_ensemble():
    """Le greffier et le fond ont chacun sa clé : un enregistrement qui renvoie les deux masques
    garde les deux vraies clés."""
    cle_greffier = "cle-de-test-du-greffier-9999999999"
    existantes = {
        **EXISTANTES,
        "greffier_llm": {"provider": "mistral", "model": "m", "api_key": cle_greffier},
    }
    masque = mask_workflow_configurations(existantes)
    reponse, ecrit = _enregistrer({**existantes, **masque}, existantes=existantes)
    assert reponse.status_code == 200, reponse.text
    assert ecrit["greffier_llm"]["api_key"] == cle_greffier
    assert ecrit[CLE_LLM]["api_key"] == CLE


# --------------------------------------------------------------------------- #
# Dans un groupe
# --------------------------------------------------------------------------- #


def test_les_cinq_cles_sont_communes_et_suivent_le_cerveau():
    for cle in CLES_DU_TRAVAIL:
        assert cle in CLES_COMMUNES, cle
        assert cle in CLES_SUIVENT_LE_CERVEAU, cle


def test_un_specialise_rattache_prend_le_fond_du_principal_et_celui_au_cerveau_propre_garde_le_sien():
    principal = {CLE_ACTIF: True, CLE_OUTILS: ["p"], CLE_DELAI: 30}
    rattache = recopier(principal, {CLE_ACTIF: False, CLE_OUTILS: ["s"]})
    assert rattache[CLE_ACTIF] is True and rattache[CLE_OUTILS] == ["p"]
    propre = recopier(
        principal, {"cerveau_propre": True, CLE_ACTIF: True, CLE_OUTILS: ["s"], CLE_DELAI: 90}
    )
    assert propre[CLE_ACTIF] is True
    assert propre[CLE_OUTILS] == ["s"]
    assert propre[CLE_DELAI] == 90
    # Un principal sans fond : le spécialisé rattaché n'en a pas non plus (le défaut revient).
    sans = recopier({}, {CLE_ACTIF: True})
    assert CLE_ACTIF not in sans


# --------------------------------------------------------------------------- #
# Les outils du fond
# --------------------------------------------------------------------------- #


def _outil(categorie, uuid, **config):
    return SimpleNamespace(
        tool_uuid=uuid,
        name=f"Outil {uuid}",
        description="Un outil.",
        category=categorie,
        definition={"schema_version": 1, "type": categorie, "config": config},
    )


@pytest.mark.parametrize(
    "categorie",
    [
        ToolCategory.END_CALL.value,
        ToolCategory.TRANSFER_CALL.value,
        ToolCategory.TRANSFER_AGENT.value,
    ],
)
def test_le_fond_ne_recoit_jamais_un_outil_qui_agit_sur_l_appel(categorie):
    assert outil_permis_au_fond(_outil(categorie, "x")) is False


def test_le_fond_recoit_les_outils_de_travail():
    for categorie in (
        ToolCategory.HTTP_API.value,
        ToolCategory.CALCULATOR.value,
        ToolCategory.MCP.value,
        ToolCategory.NATIVE.value,
    ):
        assert outil_permis_au_fond(_outil(categorie, "x")) is True, categorie


def test_une_action_interne_qui_peut_transferer_l_appel_n_est_pas_donnee_au_fond():
    """L'équipe peut transférer l'appel (``peut_transferer``) ; le planificateur lit des créneaux."""
    from api.services.integrations.connectors import outil as integration

    equipe = _outil(ToolCategory.INTEGRATION.value, "eq", connecteur="equipe")
    planificateur = _outil(ToolCategory.INTEGRATION.value, "pl", connecteur="planificateur")
    verification = _outil(ToolCategory.INTEGRATION.value, "ve", connecteur="verification")
    internes = {
        o.tool_uuid: integration.connecteur_interne(o)
        for o in (equipe, planificateur, verification)
    }
    assert internes["eq"] is not None and internes["eq"].peut_transferer is True
    assert outil_permis_au_fond(equipe) is False
    assert outil_permis_au_fond(planificateur) is True
    assert outil_permis_au_fond(verification) is True


def test_uuids_permis_garde_l_ordre_et_ecarte_les_interdits():
    lus = [
        _outil(ToolCategory.HTTP_API.value, "a"),
        _outil(ToolCategory.TRANSFER_CALL.value, "b"),
        _outil(ToolCategory.CALCULATOR.value, "c"),
        _outil(ToolCategory.END_CALL.value, "d"),
    ]
    assert uuids_permis(lus) == ["a", "c"]


@pytest.mark.asyncio
async def test_preparer_les_outils_n_enregistre_que_les_outils_permis_sur_le_modele_du_fond():
    """Le gestionnaire de l'amont, devant le modèle du fond : un outil HTTP et la calculatrice
    entrent ; le transfert et la fin d'appel jamais. La base est remplacée par des lignes lues."""
    from pipecat.tests import MockLLMService

    moteur = SimpleNamespace(
        _get_organization_id=AsyncMock(return_value=1),
        _call_context_vars={},
        _gathered_context={},
    )
    agent = SimpleNamespace(
        mcp_sessions={}, workflow_id=7, reglages={}, visit_id="v", llm=object()
    )
    llm = MockLLMService(mock_steps=[], chunk_delay=0)
    lus = [
        _outil(ToolCategory.HTTP_API.value, "http", url="https://exemple.test", method="GET"),
        _outil(ToolCategory.TRANSFER_CALL.value, "transfert", destination="+33100000000"),
        _outil(ToolCategory.END_CALL.value, "fin"),
        _outil(ToolCategory.CALCULATOR.value, "calc"),
    ]
    async def lire(uuids, _organisation):
        # Comme la base : seulement les outils demandés.
        return [o for o in lus if o.tool_uuid in uuids]

    with (
        patch(
            "api.services.workflow.pipecat_engine_custom_tools.db_client.get_tools_by_uuids",
            AsyncMock(side_effect=lire),
        ),
        patch(
            "api.services.workflow.pipecat_engine_custom_tools.precharge_de",
            return_value=None,
        ),
    ):
        schemas, noms = await preparer_les_outils(
            moteur, agent, llm, ("http", "transfert", "fin", "calc")
        )
    assert len(noms) == len(schemas)
    assert "safe_calculator" in noms
    # Le nom de l'outil HTTP vient de sa ligne ; le transfert et la fin d'appel n'ont ni schéma ni
    # gestionnaire sur le modèle du fond.
    http = tool_to_function_schema(lus[0])["function"]["name"]
    assert http in noms
    interdits = {
        tool_to_function_schema(o)["function"]["name"] for o in (lus[1], lus[2])
    }
    assert interdits and not interdits & set(noms)
    enregistres = set(llm._functions)
    assert http in enregistres and "safe_calculator" in enregistres
    assert not interdits & enregistres
    # Aucun outil réglé : aucune lecture de la base.
    assert await preparer_les_outils(moteur, agent, llm, ()) == ([], [])


# --------------------------------------------------------------------------- #
# Le moteur muet
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_les_phrases_d_outil_ne_sont_jamais_dites_par_le_fond():
    """Patience, message avant l'appel, phrase de repli : le fond les rend à la trace, la voix de
    l'appel n'en dit aucune. Tout le reste du moteur se lit sur le vrai."""
    from api.services.pipecat.speech_playback import PlaybackOutcome, SpeechPlaybackTracker

    reel = SimpleNamespace(
        speech_playback=SpeechPlaybackTracker(),
        _gathered_context={"nom": "Dupont"},
        queue_speech=AsyncMock(),
        queue_text_message=AsyncMock(),
    )
    muet = MoteurDeFond(reel)
    parole = await muet.queue_speech("Un instant, je regarde.")
    assert parole.outcome is PlaybackOutcome.SKIPPED
    assert await parole.wait() is False
    assert await muet.queue_text_message("Je n'ai pas pu, je transmets.", mute_user=True) is False
    assert muet.non_dites == ["Un instant, je regarde.", "Je n'ai pas pu, je transmets."]
    reel.queue_speech.assert_not_called()
    reel.queue_text_message.assert_not_called()
    assert muet._gathered_context == {"nom": "Dupont"}  # le reste se lit sur le vrai moteur
    muet._unevaleur = 3
    assert reel._unevaleur == 3  # et une écriture va au vrai moteur


# --------------------------------------------------------------------------- #
# Le modèle du fond
# --------------------------------------------------------------------------- #


def _conversation(provider="mistral", model="mistral-small-2603", **plus):
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration

    return EffectiveAIModelConfiguration.model_validate(
        {
            "llm": {
                "provider": provider,
                "model": model,
                "api_key": "cle-de-la-conversation-de-test",
                **plus,
            }
        }
    )


def test_bloc_vide_le_fond_prend_le_cerveau_de_conversation_tel_quel():
    for vide in (None, {}, {"model": "", "api_key": None}):
        configuration = configuration_du_travail(_conversation(), vide)
        assert configuration.llm.model == "mistral-small-2603"  # jamais Large en dur
        assert configuration.llm.api_key == "cle-de-la-conversation-de-test"


def test_bloc_regle_le_fond_prend_le_modele_et_la_cle_du_bloc_librement():
    """Fournisseur compris : le code ne contraint jamais le choix (D10)."""
    configuration = configuration_du_travail(
        _conversation(),
        {"provider": "openai", "model": "gpt-4.1", "api_key": "cle-propre-au-fond"},
    )
    assert (configuration.llm.provider, configuration.llm.model) == ("openai", "gpt-4.1")
    assert configuration.llm.api_key == "cle-propre-au-fond"


def test_le_plafond_de_jetons_de_la_voix_ne_tronque_pas_le_resultat_du_fond():
    configuration = configuration_du_travail(_conversation(max_tokens=120), None)
    champs = type(configuration.llm).model_fields
    assert configuration.llm.max_tokens == champs["max_tokens"].default


def test_une_reference_de_bibliotheque_non_resolue_est_refusee_en_le_disant():
    with pytest.raises(ValueError, match="background brain's key"):
        configuration_du_travail(_conversation(), {"api_key": "mark-cle:abc"})


@pytest.mark.asyncio
async def test_la_cle_de_bibliotheque_du_fond_est_resolue_dans_l_organisation_de_l_appel():
    run_configs = {CLE_LLM: {"provider": "mistral", "api_key": "mark-cle:abc"}}
    with patch(
        "api.services.cles_reference.cle_d_une_reference",
        AsyncMock(return_value="la-vraie-cle"),
    ) as lecture:
        rendu = await resoudre_le_bloc_du_travail(run_configs, 5)
    assert rendu[CLE_LLM]["api_key"] == "la-vraie-cle"
    assert run_configs[CLE_LLM]["api_key"] == "mark-cle:abc"  # l'original n'est jamais modifié
    lecture.assert_awaited_once_with("mark-cle:abc", "mistral", 5, "background brain")
    # Sans référence, rendu tel quel, sans lire la base.
    simple = {CLE_LLM: {"provider": "mistral", "api_key": "directe"}}
    assert await resoudre_le_bloc_du_travail(simple, 5) is simple


def test_service_du_travail_eteint_ne_construit_rien():
    assert service_du_travail(ReglagesTravail(), {}, _conversation()) == (None, None)


@pytest.mark.asyncio
async def test_le_service_est_construit_par_la_meme_fabrique_et_estampille_sans_la_cle():
    runtime: dict = {}
    reglages, service = await preparer_le_service_du_travail(
        {CLE_ACTIF: True, CLE_LLM: {"api_key": "cle-propre-au-fond"}},
        _conversation(),
        1,
        runtime,
    )
    assert reglages.actif is True
    assert service is not None
    assert runtime[CLE_ESTAMPILLE] == {"provider": "mistral", "model": "mistral-small-2603"}
    assert "cle-" not in str(runtime)


@pytest.mark.asyncio
async def test_un_service_impossible_a_construire_joue_l_agent_sans_fond():
    runtime: dict = {}
    with patch(
        "api.services.travail.fabrique.service_du_travail", side_effect=ValueError("cle-secrete")
    ):
        reglages, service = await preparer_le_service_du_travail(
            {CLE_ACTIF: True}, _conversation(), 1, runtime
        )
    assert (reglages, service) == (None, None)
    assert CLE_ESTAMPILLE not in runtime
    # Éteint : ni lecture, ni estampille.
    assert await preparer_le_service_du_travail({}, _conversation(), 1, runtime) == (None, None)


def test_le_schema_refuse_un_delai_hors_bornes_sans_toucher_aux_autres_agents():
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults(travail_delai_max_s=1)
    assert WorkflowConfigurationDefaults(travail_delai_max_s=300).travail_delai_max_s == 300
