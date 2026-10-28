"""[.mark] passages-fiables, lot H (correctif de clôture, 29/10) : au rejeu, les outils sortants sont simulés.

| Test | La garantie |
|---|---|
| hors rejeu | ``simuler_si_rejeu`` rend le gestionnaire tel quel : un vrai appel est identique à la base |
| quels outils | la catégorie (HTTP, MCP, connecteur, transfert d'appel) et les actions d'écriture / d'annulation de la fiche ; pas la calculatrice, la fin d'appel, ni la passation à un agent de l'appel |
| simulé | l'outil ne s'exécute pas, l'appel et ses arguments sont notés, le modèle reçoit un résultat neutre de réussite |
| de bout en bout | un rejeu sur la session clavier avec un vrai outil HTTP : aucune requête ne part, l'appel est noté dans le run d'essai, le critère « outil appelé avec ses arguments » est vrai ; drapeau retiré : la requête partirait |
"""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.enums import ToolCategory
from api.services.tests_rejouables.modele import TestRejouable
from api.services.tests_rejouables.rejeu import rejouer, rendre
from api.services.tests_rejouables.simulation import (
    CLE_NOTES,
    CLE_REJEU,
    RESULTAT_NEUTRE,
    en_rejeu,
    est_sortant,
    simuler_si_rejeu,
)
from api.services.workflow.tools.custom_tool import tool_to_function_schema
from api.tests.mark.test_tests_rejouables import DEFINITION, _brancher, _organisation
from pipecat.tests import MockLLMService

MODULE_HTTP = "api.services.workflow.tools.custom_tool"


def _moteur(rejeu=True, champs=()):
    fiche = {CLE_REJEU: True} if rejeu else {}
    return SimpleNamespace(_gathered_context=fiche, _fiche=SimpleNamespace(champs=tuple(champs)))


def _champ(**kw):
    return SimpleNamespace(rempli_par_outil=kw.get("rempli"), annule_par_outil=kw.get("annule"))


async def _appeler(gestionnaire, **arguments):
    rendus = []

    async def rendre_(resultat, **_):
        rendus.append(resultat)

    await gestionnaire(SimpleNamespace(arguments=arguments, result_callback=rendre_))
    return rendus


@pytest.mark.asyncio
async def test_hors_rejeu_le_gestionnaire_est_rendu_tel_quel():
    async def vrai(params):  # pragma: no cover
        raise AssertionError("jamais appelé ici")

    for categorie in ToolCategory:
        assert simuler_si_rejeu(_moteur(rejeu=False), categorie.value, "envoyer", vrai) is vrai
    assert simuler_si_rejeu(None, "http_api", "x", vrai) is vrai  # ne lève jamais
    assert not en_rejeu(_moteur(rejeu=False)) and not en_rejeu(None) and en_rejeu(_moteur())


def test_les_outils_sortants_se_repèrent_par_la_categorie_et_par_les_actions_de_la_fiche():
    moteur = _moteur(champs=[_champ(rempli="reserver"), _champ(annule="annuler")])
    for sortant in ("http_api", "mcp", "integration", "transfer_call"):
        assert est_sortant(moteur, sortant, "quelconque")
    for interne in ("calculator", "end_call", "transfer_agent", "native"):
        assert not est_sortant(moteur, interne, "quelconque")
    # une action d'écriture ou d'annulation l'est quelle que soit sa catégorie
    assert est_sortant(moteur, "native", "reserver") and est_sortant(moteur, "native", "annuler")


@pytest.mark.asyncio
async def test_un_outil_sortant_au_rejeu_n_est_pas_execute_il_est_note_et_le_modele_lit_une_reussite():
    appels = []

    async def vrai(params):  # pragma: no cover
        appels.append(params.arguments)

    moteur = _moteur(champs=[_champ(rempli="reserver")])
    moteur._gathered_context["tour_appelant"] = 4
    for categorie, nom in (("http_api", "envoyer_sms"), ("mcp", "poster"), ("transfer_call", "passer"), ("native", "reserver")):
        simule = simuler_si_rejeu(moteur, categorie, nom, vrai)
        assert simule is not vrai
        assert await _appeler(simule, destinataire="0601020304", texte="Bonjour") == [RESULTAT_NEUTRE]
    assert appels == []
    notes = moteur._gathered_context[CLE_NOTES]
    assert [n["nom"] for n in notes] == ["envoyer_sms", "poster", "passer", "reserver"]
    assert notes[0]["arguments"] == {"destinataire": "0601020304", "texte": "Bonjour"} and notes[0]["tour"] == 4
    assert [n["ecriture"] for n in notes] == [False, False, False, True]  # la lecture est simulée aussi, et distinguée


@pytest.mark.asyncio
async def test_un_outil_interne_n_est_pas_simule_au_rejeu():
    async def vrai(params):  # pragma: no cover
        await params.result_callback("vrai")

    moteur = _moteur()
    for categorie in ("calculator", "end_call", "transfer_agent"):
        assert simuler_si_rejeu(moteur, categorie, "x", vrai) is vrai
    assert CLE_NOTES not in moteur._gathered_context


@pytest.mark.asyncio
async def test_les_notes_sont_bornees_et_la_simulation_ne_leve_jamais():
    async def vrai(params):  # pragma: no cover
        pass

    moteur = _moteur()
    simule = simuler_si_rejeu(moteur, "http_api", "x", vrai)
    for _ in range(80):
        await _appeler(simule, a=1)
    assert len(moteur._gathered_context[CLE_NOTES]) == 50
    sans_fiche = SimpleNamespace(_gathered_context={CLE_REJEU: True})
    sans_fiche._gathered_context[CLE_NOTES] = "abîmé"
    assert await _appeler(simuler_si_rejeu(sans_fiche, "http_api", "x", vrai)) == [RESULTAT_NEUTRE]


# --- De bout en bout, sur la session clavier -------------------------------------------------------------------


async def _monter(db_session, async_session):
    org, user, copie = await _organisation(db_session, async_session, "sortants")
    outil = await db_session.create_tool(
        organization_id=org.id,
        user_id=user.id,
        name="Envoyer SMS",
        description="Envoie un SMS.",
        category=ToolCategory.HTTP_API.value,
        definition={
            "schema_version": 1,
            "type": "http_api",
            "config": {
                "method": "POST",
                "url": "https://sms.example.test/envoyer",
                "parameters": [{"name": "texte", "type": "string", "description": "Le texte", "required": True}],
            },
        },
    )
    definition = copy.deepcopy(DEFINITION)
    definition["nodes"][0]["data"]["tool_uuids"] = [outil.tool_uuid]
    await db_session.save_workflow_draft(copie.id, workflow_definition=definition, workflow_configurations={})
    await db_session.publish_workflow_draft(copie.id)
    return org, copie, outil


def _cerveau_qui_envoie(nom_outil):
    def fabrique(*_a, **_k):
        return MockLLMService(
            mock_steps=[
                MockLLMService.create_function_call_chunks(nom_outil, {"texte": "Bonjour"}, tool_call_id="call_sms"),
                MockLLMService.create_text_chunks("ALPHA envoyé"),
            ],
            chunk_delay=0.001,
        )

    return fabrique


def _requete_http():
    client = MagicMock()
    session = AsyncMock()
    reponse = MagicMock(status_code=200, text="")
    reponse.json.return_value = {"ok": True}
    session.request.return_value = reponse
    client.return_value.__aenter__.return_value = session
    return client, session


def _test(organisation_id):
    return TestRejouable(
        nom="sms-au-rejeu",
        replique="envoyez-moi un SMS",
        critere={"type": "outil", "nom": "envoyer_sms", "arguments": {"texte": "Bonjour"}},
        historique=[
            {"role": "assistant", "texte": "Bonjour, que puis-je faire ?"},
            {"role": "user", "texte": "je voudrais un SMS"},
            {"role": "assistant", "texte": "Bien sûr."},
        ],
        etape={"id": "start", "nom": "Accueil", "agent": None},
        fiche={"nom": "Lemaire", "tour_appelant": 1},
        organisation_id=organisation_id,
    )


@pytest.mark.asyncio
async def test_rejeu_de_bout_en_bout_le_sms_ne_part_pas_l_appel_est_note_et_le_critere_est_vrai(db_session, async_session):
    org, copie, outil = await _monter(db_session, async_session)
    nom_outil = tool_to_function_schema(outil)["function"]["name"]
    assert nom_outil == "envoyer_sms"
    client, session = _requete_http()
    _, enregistrements = _brancher(["inutile"])
    with (
        patch("api.services.workflow.text_chat_runner.create_llm_service", side_effect=_cerveau_qui_envoie(nom_outil)),
        enregistrements,
        patch(f"{MODULE_HTTP}.httpx.AsyncClient", client),
    ):
        resultat = await rejouer(_test(org.id), copie.id, 1)
    essai = resultat.essais[0]
    assert essai.erreur is None, essai.erreur
    assert session.request.call_count == 0, "la requête HTTP est partie : le SMS aurait été envoyé"
    assert essai.reussi and resultat.vert, essai.detail  # « outil appelé avec ses arguments » marche toujours
    (note,) = essai.observe["simules"]
    assert note["nom"] == "envoyer_sms" and note["categorie"] == "http_api" and note["arguments"] == {"texte": "Bonjour"}
    assert essai.observe["texte"] == "ALPHA envoyé"  # le modèle a lu la réussite et continué
    assert "outils simulés (rien n'est parti) : envoyer_sms" in rendre([resultat])
    run = await db_session.get_workflow_run_by_id(essai.run_id)
    assert run.gathered_context[CLE_NOTES][0]["nom"] == "envoyer_sms"


@pytest.mark.asyncio
async def test_sans_le_drapeau_de_rejeu_la_meme_requete_partirait(db_session, async_session):
    """Contre-épreuve : le montage fait bien appeler l'outil HTTP ; seul le drapeau l'en empêche."""
    org, copie, outil = await _monter(db_session, async_session)
    client, session = _requete_http()
    _, enregistrements = _brancher(["inutile"])
    with (
        patch("api.services.workflow.text_chat_runner.create_llm_service", side_effect=_cerveau_qui_envoie("envoyer_sms")),
        enregistrements,
        patch(f"{MODULE_HTTP}.httpx.AsyncClient", client),
        patch("api.services.tests_rejouables.rejeu.CLE_REJEU", "pas_le_drapeau"),
    ):
        resultat = await rejouer(_test(org.id), copie.id, 1)
    assert resultat.essais[0].erreur is None, resultat.essais[0].erreur
    assert session.request.call_count == 1
