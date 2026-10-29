"""[.mark] passages-fiables, lot H : les tests rejouables (créer depuis un run, rejouer, suite).

Aucun appel réel à un modèle : le cerveau est un faux (réponses écrites d'avance). La base est celle des tests.

| Test | Ce qu'il prouve |
|---|---|
| coupe | un journal fictif est coupé juste avant le bon tour : historique, étape, réplique ; fiche remise dans l'état d'avant |
| coupe hors rang | un rang qui n'existe pas → erreur claire |
| criteres | chacun des quatre critères, vrai et faux (outil : égalité, inclusion, absent) |
| fichier | un fichier illisible ou incohérent → erreur claire ; un bon fichier fait l'aller-retour |
| création | depuis un run en base (organisation vérifiée) ; le run d'une autre organisation est refusé |
| taux | 3 essais, faux cerveau : 3/3 puis 1/3, avec ce qui a été observé à chaque essai |
| reprise | le tour rejoué repart de l'historique, de l'étape et de la fiche du test |
| protégé | agents 139-145 et 223-243 refusés (test et suite), avant toute écriture |
| autre organisation | agent d'une autre organisation que celle du test refusé |
| suite | un fichier illisible n'arrête pas la suite |
"""

import copy
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from api.db.models import OrganizationModel, UserModel, organization_users_association
from api.enums import OrganizationConfigurationKey
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.configuration.ai_model_configuration import (
    convert_legacy_ai_model_configuration_to_v2,
)
from api.services.tests_rejouables.creation import couper_au_tour, creer_depuis_un_run
from api.services.tests_rejouables.modele import (
    AGENTS_PROTEGES,
    ErreurTestRejouable,
    Observation,
    TestRejouable,
    ecrire_test,
    evaluer,
    lire_test,
)
from api.services.tests_rejouables.rejeu import jouer_suite, rejouer
from api.tests.integrations._run_pipeline_helpers import USER_CONFIGURATION
from pipecat.tests import MockLLMService

DEFINITION = {
    "nodes": [
        {
            "id": "start",
            "type": "startCall",
            "position": {"x": 0, "y": 0},
            "data": {
                "name": "Accueil",
                "prompt": "Tu accueilles la personne.",
                "is_start": True,
                "allow_interrupt": False,
                "add_global_prompt": False,
                "greeting_type": "text",
                "greeting": "Bonjour.",
            },
        },
        {
            "id": "end",
            "type": "endCall",
            "position": {"x": 0, "y": 200},
            "data": {
                "name": "Fin",
                "prompt": "Fin.",
                "is_end": True,
                "allow_interrupt": False,
                "add_global_prompt": False,
            },
        },
    ],
    "edges": [
        {
            "id": "start-end",
            "source": "start",
            "target": "end",
            "data": {"label": "Fin", "condition": "Quand c'est fini."},
        }
    ],
}


def _journal():
    """Trois tours de la personne ; la fiche s'écrit au tour 2 (nom) et au tour 3 (motif)."""
    t = iter(f"2026-10-28T10:00:{i:02d}+00:00" for i in range(60))

    def ev(genre, payload, **en_plus):
        return {"type": genre, "payload": payload, "timestamp": next(t), **en_plus}

    return [
        ev("rtf-node-transition", {"node_id": "start", "node_name": "Accueil"}),
        ev("rtf-bot-text", {"text": "Bonjour, que puis-je faire ?"}),
        ev("rtf-user-transcription", {"text": "euh", "final": False}),
        ev("rtf-user-transcription", {"text": "Bonjour", "final": True}),
        ev("rtf-user-transcription", {"text": "je voudrais un devis", "final": True}),
        ev("rtf-bot-text", {"text": "Très bien."}),
        ev("rtf-bot-text", {"text": "Votre nom ?"}),
        ev("rtf-user-transcription", {"text": "Lemaire", "final": True}),
        ev("rtf-bot-text", {"text": "Merci, et le motif ?"}),
        ev("rtf-user-transcription", {"text": "un entretien", "final": True}),
        ev("rtf-node-transition", {"node_id": "end", "node_name": "Fin"}),
        ev("rtf-bot-text", {"text": "C'est noté."}),
    ]


FICHE_FINALE = {
    "nom": "Lemaire",
    "motif": "entretien",
    "tour_appelant": 3,
    "call_disposition": "user_hangup",
    "fiche_journal": [
        {"champ": "nom", "valeur": "Lemaire", "statut": "ecrit", "sure": True, "source": "outil", "tour": 2},
        {"champ": "motif", "valeur": "entretien", "statut": "ecrit", "sure": True, "source": "outil", "tour": 3},
    ],
    "fiche_etat": {"nom": {"sure": True}, "motif": {"sure": True}},
    "extracted_variables": {"nom": "Lemaire", "motif": "entretien"},
    "nombres_lus": [{"type": "telephone", "tour": 3}, {"type": "code_postal", "tour": 1}],
    "nodes_visited": ["Accueil", "Fin"],
}

CRITERE = {"type": "texte_present", "texte": "motif"}


# --- Coupe (pur) ---------------------------------------------------------------------------------


def test_coupe_historique_etape_replique_et_fiche_d_avant_le_tour():
    coupe = couper_au_tour(_journal(), FICHE_FINALE, 3)
    assert coupe["replique"] == "un entretien"
    # Deux paroles de suite du même côté n'en font qu'une ; le partiel (final faux) est ignoré.
    assert coupe["historique"] == [
        {"role": "assistant", "texte": "Bonjour, que puis-je faire ?"},
        {"role": "user", "texte": "Bonjour je voudrais un devis"},
        {"role": "assistant", "texte": "Très bien. Votre nom ?"},
        {"role": "user", "texte": "Lemaire"},
        {"role": "assistant", "texte": "Merci, et le motif ?"},
    ]
    assert coupe["etape"] == {"id": "start", "nom": "Accueil", "agent": None}
    fiche = coupe["fiche"]
    assert fiche["nom"] == "Lemaire" and "motif" not in fiche
    assert [e["champ"] for e in fiche["fiche_journal"]] == ["nom"]
    assert "motif" not in fiche["fiche_etat"] and "motif" not in fiche["extracted_variables"]
    assert fiche["nombres_lus"] == [{"type": "code_postal", "tour": 1}]
    assert fiche["tour_appelant"] == 2  # le message rejoué sera lu comme le 3e
    assert "call_disposition" not in fiche
    assert fiche["nodes_visited"] == ["Accueil"]
    # Le run d'origine n'est pas modifié.
    assert FICHE_FINALE["motif"] == "entretien" and len(FICHE_FINALE["fiche_journal"]) == 2


def test_coupe_au_premier_tour_fiche_vide_et_rang_inexistant():
    coupe = couper_au_tour(_journal(), FICHE_FINALE, 1)
    assert coupe["replique"] == "Bonjour je voudrais un devis"
    assert "nom" not in coupe["fiche"] and "motif" not in coupe["fiche"]
    with pytest.raises(ErreurTestRejouable, match="n'a que 3"):
        couper_au_tour(_journal(), FICHE_FINALE, 4)
    with pytest.raises(ErreurTestRejouable, match="commence à 1"):
        couper_au_tour(_journal(), FICHE_FINALE, 0)


def test_coupe_ecarte_une_ecriture_sans_numero_de_tour_et_refuse_un_autre_agent():
    fiche = copy.deepcopy(FICHE_FINALE)
    fiche["fiche_journal"][0].pop("tour")
    assert "nom" not in couper_au_tour(_journal(), fiche, 3)["fiche"]
    journal = _journal()
    journal[0]["payload"]["agent"] = "Un autre agent"
    with pytest.raises(ErreurTestRejouable, match="passation"):
        couper_au_tour(journal, FICHE_FINALE, 3, nom_de_l_agent="Le premier")


# --- Critères et fichier (pur) -------------------------------------------------------------------


def _obs():
    return Observation(
        texte="Je note : le Mardi à 14 h, Très bien.",
        outils=[{"nom": "noter_information", "arguments": {"nom": "Lemaire", "tel": "0601020304"}}],
        etape_id="end",
        etape_nom="Fin",
        etapes_traversees=["Fin"],
    )


@pytest.mark.parametrize(
    ("critere", "attendu"),
    [
        ({"type": "etape", "attendue": "fin"}, True),
        ({"type": "etape", "attendue": "end"}, True),
        ({"type": "etape", "attendue": "Accueil"}, False),
        ({"type": "outil", "nom": "noter_information"}, True),
        ({"type": "outil", "nom": "transferer"}, False),
        ({"type": "outil", "nom": "noter_information", "arguments": {"nom": "Lemaire"}}, True),
        ({"type": "outil", "nom": "noter_information", "arguments": {"nom": "Durand"}}, False),
        (
            {"type": "outil", "nom": "noter_information", "arguments": {"nom": "Lemaire"}, "mode": "egalite"},
            False,
        ),
        (
            {
                "type": "outil",
                "nom": "noter_information",
                "arguments": {"nom": "Lemaire", "tel": "0601020304"},
                "mode": "egalite",
            },
            True,
        ),
        ({"type": "outil", "nom": "transferer", "appele": False}, True),
        ({"type": "outil", "nom": "noter_information", "appele": False}, False),
        ({"type": "texte_present", "texte": "TRES bien"}, True),
        ({"type": "texte_present", "texte": "mercredi"}, False),
        ({"type": "texte_absent", "texte": "mercredi"}, True),
        ({"type": "texte_absent", "texte": "mardi à 14 h"}, False),
    ],
)
def test_chaque_critere_vrai_et_faux(critere, attendu):
    reussi, detail = evaluer(critere, _obs())
    assert reussi is attendu
    assert detail


def _brut(**en_plus):
    return {
        "version": 1,
        "nom": "essai",
        "replique": "bonjour",
        "historique": [{"role": "assistant", "texte": "Bonjour."}],
        "critere": CRITERE,
        **en_plus,
    }


def test_fichier_illisible_ou_incoherent_erreur_claire_et_aller_retour(tmp_path):
    (tmp_path / "casse.json").write_text("{pas du json", encoding="utf-8")
    with pytest.raises(ErreurTestRejouable, match="casse.json : fichier illisible"):
        lire_test(tmp_path / "casse.json")
    with pytest.raises(ErreurTestRejouable, match="introuvable"):
        lire_test(tmp_path / "absent.json")
    for mauvais, motif in [
        (_brut(version=2), "version"),
        (_brut(replique=" "), "replique"),
        (_brut(critere={"type": "magie"}), "type de critère inconnu"),
        (_brut(critere={"type": "outil", "nom": "x", "mode": "flou"}), "mode inconnu"),
        (_brut(historique=[{"role": "robot", "texte": "x"}]), "message 1"),
        (_brut(organisation_id="douze"), "organisation_id"),
    ]:
        f = tmp_path / "mauvais.json"
        f.write_text(json.dumps(mauvais), encoding="utf-8")
        with pytest.raises(ErreurTestRejouable, match=motif):
            lire_test(f)
    bon = lire_test(ecrire_test(TestRejouable("aller-retour", "salut", CRITERE), tmp_path / "ok.json"))
    assert bon.nom == "aller-retour" and bon.replique == "salut" and bon.critere == CRITERE


# --- Avec la base --------------------------------------------------------------------------------


async def _organisation(db_session, async_session, etiquette):
    suffixe = uuid.uuid4().hex[:10]
    org = OrganizationModel(provider_id=f"test-org-rejouable-{etiquette}-{suffixe}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(
        provider_id=f"test-user-rejouable-{etiquette}-{suffixe}",
        selected_organization_id=org.id,
    )
    async_session.add(user)
    await async_session.flush()
    await async_session.execute(
        organization_users_association.insert().values(user_id=user.id, organization_id=org.id)
    )
    modeles = copy.deepcopy(USER_CONFIGURATION)
    modeles["stt"]["language"] = "fr"
    await db_session.upsert_configuration(
        org.id,
        OrganizationConfigurationKey.MODEL_CONFIGURATION_V2.value,
        convert_legacy_ai_model_configuration_to_v2(
            EffectiveAIModelConfiguration.model_validate(modeles)
        ).model_dump(mode="json", exclude_none=True),
    )
    workflow = await db_session.create_workflow(
        name=f"Copie {etiquette}",
        workflow_definition=DEFINITION,
        user_id=user.id,
        organization_id=org.id,
    )
    await db_session.save_workflow_draft(
        workflow.id, workflow_definition=DEFINITION, workflow_configurations={}
    )
    await db_session.publish_workflow_draft(workflow.id)
    return org, user, workflow


def _faux_cerveau(reponses):
    """Un faux modèle par essai : la i-ème construction rend la i-ème réponse (la dernière se répète)."""
    appels = {"n": 0}

    def fabrique(*_a, **_k):
        i = min(appels["n"], len(reponses) - 1)
        appels["n"] += 1
        return MockLLMService(
            mock_steps=[MockLLMService.create_text_chunks(reponses[i])], chunk_delay=0.001
        )

    return fabrique


def _test_a_rejouer(organisation_id=None):
    return TestRejouable(
        nom="tour-fautif",
        replique="un entretien",
        critere={"type": "texte_present", "texte": "ALPHA"},
        historique=[
            {"role": "assistant", "texte": "Bonjour, que puis-je faire ?"},
            {"role": "user", "texte": "je voudrais un devis"},
            {"role": "assistant", "texte": "Merci, et le motif ?"},
        ],
        etape={"id": "start", "nom": "Accueil", "agent": None},
        fiche={"nom": "Lemaire", "tour_appelant": 1},
        organisation_id=organisation_id,
    )


def _brancher(reponses):
    return (
        patch(
            "api.services.workflow.text_chat_runner.create_llm_service",
            side_effect=_faux_cerveau(reponses),
        ),
        patch(
            "api.services.workflow.text_chat_runner.db_client.has_active_recordings",
            new=AsyncMock(return_value=False),
        ),
    )


@pytest.mark.asyncio
async def test_creation_depuis_un_run_et_organisation_verifiee(db_session, async_session):
    org, user, workflow = await _organisation(db_session, async_session, "a")
    autre, _, _ = await _organisation(db_session, async_session, "b")
    run = await db_session.create_workflow_run(
        name="WR-fictif",
        workflow_id=workflow.id,
        mode="textchat",
        user_id=user.id,
        organization_id=org.id,
        gathered_context=FICHE_FINALE,
        logs={"realtime_feedback_events": _journal()},
    )
    test = await creer_depuis_un_run(run.id, org.id, 3, CRITERE, "nom-du-test")
    assert test.replique == "un entretien"
    assert test.organisation_id == org.id
    assert test.source == {"run_id": run.id, "rang": 3, "agent_id": workflow.id}
    assert test.etape["nom"] == "Accueil" and len(test.historique) == 5
    assert "motif" not in test.fiche and test.fiche["nom"] == "Lemaire"
    # Le run d'une autre organisation est « introuvable » ; un critère faux est refusé avant tout.
    with pytest.raises(ErreurTestRejouable, match="introuvable"):
        await creer_depuis_un_run(run.id, autre.id, 3, CRITERE, "x")
    with pytest.raises(ErreurTestRejouable, match="introuvable"):
        await creer_depuis_un_run(run.id + 10_000_000, org.id, 3, CRITERE, "x")
    with pytest.raises(ErreurTestRejouable, match="type de critère"):
        await creer_depuis_un_run(run.id, org.id, 3, {"type": "?"}, "x")


@pytest.mark.asyncio
async def test_rejeu_trois_fois_taux_juste_et_observations(db_session, async_session):
    org, _, copie = await _organisation(db_session, async_session, "taux")
    test = _test_a_rejouer(org.id)
    llm, enregistrements = _brancher(["ALPHA ok", "ALPHA encore", "ALPHA toujours"])
    with llm, enregistrements:
        vert = await rejouer(test, copie.id, 3)
    assert vert.taux == "3/3" and vert.vert
    assert all(e.erreur is None for e in vert.essais), [e.erreur for e in vert.essais]
    assert [e.observe["texte"] for e in vert.essais] == ["ALPHA ok", "ALPHA encore", "ALPHA toujours"]

    llm, enregistrements = _brancher(["ALPHA ok", "Bêta", "Gamma"])
    with llm, enregistrements:
        rouge = await rejouer(test, copie.id, 3)
    assert rouge.taux == "1/3" and not rouge.vert
    assert [e.reussi for e in rouge.essais] == [True, False, False]
    assert "Bêta" in rouge.essais[1].detail


@pytest.mark.asyncio
async def test_rejeu_repart_de_l_historique_de_l_etape_et_de_la_fiche(db_session, async_session):
    org, _, copie = await _organisation(db_session, async_session, "reprise")
    llm, enregistrements = _brancher(["ALPHA"])
    with llm, enregistrements:
        res = await rejouer(_test_a_rejouer(org.id), copie.id, 1)
    essai = res.essais[0]
    assert essai.erreur is None, essai.erreur
    run = await db_session.get_workflow_run_by_id(essai.run_id)
    assert run.is_completed and run.name.startswith("REJEU-")
    assert run.gathered_context.get("nom") == "Lemaire"
    session = await db_session.get_workflow_run_text_session(essai.run_id, organization_id=org.id)
    tours = session.session_data["turns"]
    assert [t["status"] for t in tours] == ["completed", "completed"]
    assert tours[1]["user_message"]["text"] == "un entretien"
    messages = json.dumps(session.checkpoint["messages"], ensure_ascii=False)
    for morceau in ("je voudrais un devis", "Merci, et le motif ?", "un entretien", "ALPHA"):
        assert morceau in messages, morceau
    assert session.checkpoint["current_node_id"] == "start"
    assert essai.observe["etape"]["nom"] == "Accueil"


@pytest.mark.asyncio
async def test_agents_proteges_refuses_avant_toute_ecriture(db_session, tmp_path):
    assert {139, 145, 223, 243} <= AGENTS_PROTEGES and 146 not in AGENTS_PROTEGES
    for agent in (139, 145, 223, 243):
        with pytest.raises(ErreurTestRejouable, match="COPIE"):
            await rejouer(_test_a_rejouer(), agent, 3)
        with pytest.raises(ErreurTestRejouable, match="COPIE"):
            await jouer_suite(tmp_path, agent, 3)


@pytest.mark.asyncio
async def test_agent_d_une_autre_organisation_refuse(db_session, async_session):
    org, _, _ = await _organisation(db_session, async_session, "mienne")
    _, _, etrangere = await _organisation(db_session, async_session, "etrangere")
    with pytest.raises(ErreurTestRejouable, match="autre"):
        await rejouer(_test_a_rejouer(org.id), etrangere.id, 1)
    with pytest.raises(ErreurTestRejouable, match="introuvable"):
        await rejouer(_test_a_rejouer(org.id), 99_999_999, 1)


@pytest.mark.asyncio
async def test_suite_un_fichier_illisible_n_arrete_pas_les_autres(db_session, async_session, tmp_path):
    org, _, copie = await _organisation(db_session, async_session, "suite")
    (tmp_path / "a-casse.json").write_text("{", encoding="utf-8")
    ecrire_test(_test_a_rejouer(org.id), tmp_path / "b-bon.json")
    llm, enregistrements = _brancher(["ALPHA"])
    with llm, enregistrements:
        resultats = await jouer_suite(tmp_path, copie.id, 2)
    assert [r.nom for r in resultats] == ["a-casse", "tour-fautif"]
    assert "illisible" in resultats[0].erreur and not resultats[0].essais
    assert resultats[1].taux == "2/2"
    (tmp_path / "vide").mkdir()
    with pytest.raises(ErreurTestRejouable, match="aucun test"):
        await jouer_suite(tmp_path / "vide", copie.id, 1)
