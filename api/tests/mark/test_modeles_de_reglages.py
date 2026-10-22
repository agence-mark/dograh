"""[.mark] Non-regression test for the settings templates (cloture-code-avant-migration, lot 5; plan
``modeles-de-reglages``, M1 to M11).

The questions this file answers, and only these:

    Is every setting of an agent classified (template, kept by the agent, own to the agent), so that a
    setting added tomorrow is made to be sorted? Does a template, created through the REAL route from an
    agent's settings, apply to the DRAFT of another agent by section -- the published version untouched,
    the agent's own data untouched, a setting the template does not set back to its default? Does a template
    and its exported file hold NO key of access, and does the agent that receives it keep its OWN keys? Does
    the import refuse, by name, what it does not know? Is one organization's template never seen, applied,
    changed or exported by another?

Why it exists
-------------
The labo finds many combinations of settings and keeps one: it must be frozen under a name and applied in
one gesture to the next agent (decision of 11/09, « le labo fige des configs »). Two defects this file keeps
out: a key of access travelling inside a template (the file goes from one client to the next), and an
application that writes half a pair of bricks (an override without its key stops the calls).

⚠️ What this file does NOT prove: that the screen shows the modal (``modeles-ecran.test.tsx``), nor what the
agent does with the settings (the other tests of this folder).
"""

import json
from types import SimpleNamespace

import pytest

from api.db.models import OrganizationModel, UserModel
from api.enums import OrganizationConfigurationKey
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.configuration.resolve import _SECTION_MAP
from api.services.groupe.reglages import CLES_COMMUNES, CLES_PROPRES, CLES_SUIVENT_LE_CERVEAU
from api.services.modeles_reglages import classement as cl
from api.services.modeles_reglages.service import (
    calculer_l_application,
    cles_reglees_par_le_principal,
    sections_reglees_par_le_principal,
)

ROUTE = "/api/v1/organizations/modeles-de-reglages"
GRAPHE = {
    "nodes": [
        {"id": "1", "type": "startCall", "data": {"name": "Start", "prompt": "Hello"}},
        {"id": "2", "type": "endCall", "data": {"name": "End", "prompt": "Bye"}},
    ],
    "edges": [{"id": "e1", "source": "1", "target": "2", "data": {"label": "End"}}],
}
JOURS_FERMES = "".join(f"{j} : fermé\n" for j in ("mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"))
HORAIRES_A = "lundi : 09:00-12:00\n" + JOURS_FERMES
HORAIRES_B = "lundi : 08:00-19:00\n" + JOURS_FERMES
CLE_SECRETE_A = "sk-SECRET-AGENT-A-0001"
CLE_SECRETE_B = "sk-SECRET-AGENT-B-0002"


def _v2(cle_llm, modele="gpt-4.1", cle_tts="el-key", cle_stt="dg-key"):
    """A valid full configuration of bricks; a ``None`` key leaves the field out."""

    def _service(fournisseur, cle, **reste):
        bloc = {"provider": fournisseur, **reste}
        if cle is not None:
            bloc["api_key"] = cle
        return bloc

    return {
        "version": 2,
        "mode": "byok",
        "byok": {
            "mode": "pipeline",
            "pipeline": {
                "llm": _service("openai", cle_llm, model=modele),
                "tts": _service("elevenlabs", cle_tts, model="eleven_flash_v2_5", voice="Rachel"),
                "stt": _service("deepgram", cle_stt, model="nova-3-general"),
            },
        },
    }


CONFIG_A = {
    "max_call_duration": 600,
    "turn_start_strategy": "min_words",
    "turn_start_min_words": 4,
    "vad_stop_secs": 0.6,
    "tts_text_aggregation_mode": "token",
    "lexique_metier": True,
    "relance_tour_vide": True,
    "greffier_llm": {"provider": "openai", "model": "gpt-4.1-mini", "api_key": CLE_SECRETE_A},
    "model_configuration_v2_override": _v2(CLE_SECRETE_A),
    "attente": {"son": "aucun", "duree_min_s": 2.0, "phrase_pont": "PHRASE-A-DE-ATTENTE"},
    # Data of the agent A: never in a template.
    "user_idle_prompt": "PROMPT-DE-A",
    "dictionary": "MOT-DE-A",
    "tts_replacements": ["SAV:S. A. V."],
    "horaires_ouverture": HORAIRES_A,
}

CONFIG_B = {
    "max_call_duration": 300,
    "turn_start_strategy": "default",
    "vad_stop_secs": 0.9,
    "user_idle_max_prompts": 7,  # not set by A: back to its default if its section is taken
    "tts_text_aggregation_mode": "sentence",
    "model_configuration_v2_override": _v2(CLE_SECRETE_B, modele="gpt-4.1-nano", cle_tts="b-tts", cle_stt="b-stt"),
    "attente": {"son": "musique", "phrase_pont": "PHRASE-B-DE-ATTENTE"},
    "user_idle_prompt": "PROMPT-DE-B",
    "dictionary": "MOT-DE-B",
    "tts_replacements": ["XX:Y Y"],
    "horaires_ouverture": HORAIRES_B,
}


@pytest.fixture
async def monde(db_session, async_session):
    """Two organizations, each with a user; A holds an agent with its settings, B two agents."""
    async def _organisation(nom):
        org = OrganizationModel(provider_id=f"org-modeles-{nom}")
        async_session.add(org)
        await async_session.flush()
        user = UserModel(provider_id=f"user-modeles-{nom}", selected_organization_id=org.id)
        async_session.add(user)
        await async_session.flush()
        return org, user

    async def _agent(user, org, nom, configurations):
        workflow = await db_session.create_workflow(
            name=nom, workflow_definition=GRAPHE, user_id=user.id, organization_id=org.id
        )
        await db_session.save_workflow_draft(workflow.id, workflow_configurations=configurations)
        await db_session.publish_workflow_draft(workflow.id)
        return workflow

    org_a, user_a = await _organisation("a")
    org_b, user_b = await _organisation("b")
    agent_a = await _agent(user_a, org_a, "Agent A", CONFIG_A)
    agent_b = await _agent(user_b, org_b, "Agent B", CONFIG_B)
    agent_b2 = await _agent(user_b, org_b, "Agent B2", {})
    agent_a2 = await _agent(user_a, org_a, "Agent A2", CONFIG_B)
    return SimpleNamespace(
        org_a=org_a, user_a=user_a, org_b=org_b, user_b=user_b,
        agent_a=agent_a, agent_a2=agent_a2, agent_b=agent_b, agent_b2=agent_b2,
    )


async def _creer(client, nom, workflow_id):
    reponse = await client.post(ROUTE, json={"nom": nom, "workflow_id": workflow_id})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


async def _active(db_session, workflow_id):
    """The configuration the page of the agent would show: the draft if any, else the published one."""
    brouillon = await db_session.get_draft_version(workflow_id)
    if brouillon is not None:
        return brouillon.workflow_configurations or {}
    workflow = await db_session.get_workflow_by_id(workflow_id)
    return workflow.released_definition.workflow_configurations or {}


# --------------------------------------------------------------------------- #
# 1. The sweep: every setting is sorted
# --------------------------------------------------------------------------- #


def test_toute_cle_connue_est_classee():
    connues = set(WorkflowConfigurationDefaults.model_fields) | set(CLES_COMMUNES) | set(CLES_PROPRES)
    assert len(connues) > 90, "a parse that found nothing would make this test vacuous"
    assert cl.cles_sans_classement(connues) == []


def test_une_cle_ajoutee_demain_et_non_rangee_fait_echouer_le_balayage():
    # The test that proves the sweep is not vacuous: a key nobody sorted is reported by its name.
    assert cl.cles_sans_classement(["reglage_ajoute_demain"]) == ["reglage_ajoute_demain"]


def test_une_seule_liste_de_cles_les_sections_sont_les_themes_de_cles_communes():
    reunion = [c for cles in cl.SECTIONS.values() for c in cles]
    assert tuple(reunion) == tuple(CLES_COMMUNES)
    assert len(set(reunion)) == len(reunion), "a key in two sections"
    assert not set(cl.EXCLUES_DU_MODELE) - set(CLES_COMMUNES), "an exclusion for a key that is not common"
    assert not set(cl.cles_du_modele()) & set(CLES_PROPRES)


def test_les_sous_cles_de_la_surcharge_par_service_sont_celles_que_la_resolution_lit():
    # The legacy overlays (``model_overrides``) are one key of the « bricks » section: the services it can
    # hold are those the resolution knows, none is left to be sorted.
    assert set(_SECTION_MAP) == {"llm", "tts", "stt", "realtime"}
    assert cl.section_de("model_overrides") == "briques"


def test_prompts_outils_et_donnees_du_client_ne_sont_pas_dans_un_modele():
    for cle in ("user_idle_prompt", "greffier_consigne", "travail_consigne", "travail_outils", "dictionary",
                "tts_replacements", "apres_appel", "panne", "voicemail_detection", "fiche_champs"):
        assert cl.section_de(cle) is None and cle not in cl.cles_du_modele(), cle
    for cle in ("turn_start_min_words", "vad_stop_secs", "tts_text_aggregation_mode", "model_configuration_v2_override"):
        assert cle in cl.cles_du_modele(), cle


# --------------------------------------------------------------------------- #
# 2. Create, list, rename, delete -- through the real route
# --------------------------------------------------------------------------- #


async def test_creer_lister_renommer_supprimer(monde, test_client_factory):
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Reglage de reference", monde.agent_a.id)
        assert modele["nombre_de_reglages"] >= 8
        assert modele["origine"]["agent_nom"] == "Agent A" and modele["origine"]["version_status"] == "published"
        assert {"tour", "voix", "briques"} <= set(modele["sections"])

        liste = (await client.get(ROUTE)).json()
        assert [m["nom"] for m in liste["modeles"]] == ["Reglage de reference"]
        assert liste["sections"] == list(cl.SECTIONS)

        doublon = await client.post(ROUTE, json={"nom": "reglage DE reference", "workflow_id": monde.agent_a.id})
        assert doublon.status_code == 409

        renomme = await client.patch(f"{ROUTE}/{modele['id']}", json={"nom": "Nouveau nom"})
        assert renomme.status_code == 200 and renomme.json()["nom"] == "Nouveau nom"
        vide = await client.patch(f"{ROUTE}/{modele['id']}", json={"nom": "   "})
        assert vide.status_code == 422

        assert (await client.delete(f"{ROUTE}/{modele['id']}")).status_code == 204
        assert (await client.get(ROUTE)).json()["modeles"] == []
        assert (await client.delete(f"{ROUTE}/{modele['id']}")).status_code == 404


async def test_le_modele_est_gele_sur_la_version_active_le_brouillon_s_il_existe(monde, test_client_factory, db_session):
    await db_session.save_workflow_draft(
        monde.agent_a.id, workflow_configurations={**CONFIG_A, "turn_start_min_words": 9}
    )
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Brouillon", monde.agent_a.id)
        assert modele["origine"]["version_status"] == "draft"
        fichier = (await client.get(f"{ROUTE}/{modele['id']}/export")).json()
        assert fichier["valeurs"]["turn_start_min_words"] == 9


# --------------------------------------------------------------------------- #
# 3. Apply: a copy on the draft, by section
# --------------------------------------------------------------------------- #


async def test_appliquer_par_section_sur_le_brouillon(monde, test_client_factory, db_session):
    """The sections ticked take the template's values exactly; the others, the published version and the
    agent's own data stay."""
    async with test_client_factory(monde.user_b) as client_b, test_client_factory(monde.user_a) as client_a:
        # B has no template: the model is frozen in A, exported, imported in B (M1: the only road).
        modele_a = await _creer(client_a, "De A", monde.agent_a.id)
        fichier = (await client_a.get(f"{ROUTE}/{modele_a['id']}/export")).json()
    async with test_client_factory(monde.user_b) as client_b:
        importe = await client_b.post(f"{ROUTE}/import", json=fichier)
        assert importe.status_code == 200, importe.text
        publie_avant = (await db_session.get_workflow_by_id(monde.agent_b.id)).released_definition.workflow_configurations

        reponse = await client_b.post(
            f"{ROUTE}/{importe.json()['id']}/appliquer",
            json={"workflow_id": monde.agent_b.id, "sections": ["tour", "voix"]},
        )
        assert reponse.status_code == 200, reponse.text
        resultat = reponse.json()
        assert resultat["ecrit"] is True and resultat["non_appliquees"] == []

    brouillon = await db_session.get_draft_version(monde.agent_b.id)
    assert brouillon is not None, "the application is written on a DRAFT (M5)"
    nouvelle = brouillon.workflow_configurations
    # Taken from the template, section « tour » and « voix ».
    assert nouvelle["turn_start_min_words"] == 4 and nouvelle["turn_start_strategy"] == "min_words"
    assert nouvelle["vad_stop_secs"] == 0.6
    assert nouvelle["tts_text_aggregation_mode"] == "token"
    # Not ticked: « agent », « briques », « rythme »... stay what they were.
    assert nouvelle["max_call_duration"] == 300
    assert nouvelle["user_idle_max_prompts"] == 7
    assert nouvelle["model_configuration_v2_override"] == CONFIG_B["model_configuration_v2_override"]
    # Own data: untouched, whatever the sections.
    for cle in ("user_idle_prompt", "dictionary", "tts_replacements", "horaires_ouverture"):
        assert nouvelle[cle] == CONFIG_B[cle], cle
    # The published version did not move.
    publie_apres = (await db_session.get_workflow_by_id(monde.agent_b.id)).released_definition.workflow_configurations
    assert publie_apres == publie_avant == CONFIG_B


async def test_un_reglage_que_le_modele_ne_pose_pas_revient_au_defaut_dans_la_section_cochee(
    monde, test_client_factory, db_session
):
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Sans rythme", monde.agent_a.id)
        # Agent A2 (same organization) carries a rythme setting the template does not set.
        await db_session.save_workflow_draft(
            monde.agent_a2.id, workflow_configurations={**CONFIG_B, "user_idle_max_prompts": 7}
        )
        reponse = await client.post(
            f"{ROUTE}/{modele['id']}/appliquer",
            json={"workflow_id": monde.agent_a2.id, "sections": ["rythme", "tour"]},
        )
        assert reponse.status_code == 200, reponse.text
        assert "user_idle_max_prompts" in reponse.json()["retirees"]
    nouvelle = await _active(db_session, monde.agent_a2.id)
    assert "user_idle_max_prompts" not in nouvelle
    assert nouvelle["max_call_duration"] == 600, "the section « rythme » holds max_call_duration, taken"


async def test_appliquer_garde_les_phrases_du_client_dans_une_cle_du_modele(monde, test_client_factory, db_session):
    """``attente`` is a template setting, but its bridge sentence is the client's own words."""
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Attente", monde.agent_a.id)
        fichier = (await client.get(f"{ROUTE}/{modele['id']}/export")).json()
        assert "phrase_pont" not in json.dumps(fichier["valeurs"]["attente"])
        assert "PHRASE-A-DE-ATTENTE" not in json.dumps(fichier)
        reponse = await client.post(
            f"{ROUTE}/{modele['id']}/appliquer",
            json={"workflow_id": monde.agent_a2.id, "sections": ["agent"]},
        )
        assert reponse.status_code == 200, reponse.text
    attente = (await _active(db_session, monde.agent_a2.id))["attente"]
    assert attente["son"] == "aucun" and attente["duree_min_s"] == 2.0
    assert attente["phrase_pont"] == "PHRASE-B-DE-ATTENTE"


async def test_l_agent_garde_la_mention_du_modele_applique(monde, test_client_factory):
    async with test_client_factory(monde.user_a) as client:
        assert (await client.get(f"{ROUTE}/agent/{monde.agent_a2.id}")).json()["mention"] is None
        modele = await _creer(client, "Mention", monde.agent_a.id)
        await client.post(
            f"{ROUTE}/{modele['id']}/appliquer",
            json={"workflow_id": monde.agent_a2.id, "sections": ["tour", "voix"]},
        )
        mention = (await client.get(f"{ROUTE}/agent/{monde.agent_a2.id}")).json()["mention"]
        assert mention["nom"] == "Mention" and mention["sections"] == ["tour", "voix"] and mention["applique_le"]
        # M4: a copy. Delete the template: the agent keeps the mention, nothing else moves.
        await client.delete(f"{ROUTE}/{modele['id']}")
        mention = (await client.get(f"{ROUTE}/agent/{monde.agent_a2.id}")).json()["mention"]
        assert mention["nom"] == "Mention"


async def test_appliquer_a_blanc_n_ecrit_rien(monde, test_client_factory, db_session):
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "A blanc", monde.agent_a.id)
        reponse = await client.post(
            f"{ROUTE}/{modele['id']}/appliquer",
            json={"workflow_id": monde.agent_a2.id, "sections": ["tour"], "a_blanc": True},
        )
        assert reponse.status_code == 200 and reponse.json()["ecrit"] is False
        assert reponse.json()["posees"], "the dry run says what would be set"
        assert (await client.get(f"{ROUTE}/agent/{monde.agent_a2.id}")).json()["mention"] is None
    assert await db_session.get_draft_version(monde.agent_a2.id) is None


async def test_une_section_inconnue_ou_aucune_section_est_refusee(monde, test_client_factory):
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Sections", monde.agent_a.id)
        for sections in (["inconnue"], []):
            reponse = await client.post(
                f"{ROUTE}/{modele['id']}/appliquer", json={"workflow_id": monde.agent_a2.id, "sections": sections}
            )
            assert reponse.status_code == 422, sections


# --------------------------------------------------------------------------- #
# 4. Keys of access: never in a template, never in a file, kept by the agent
# --------------------------------------------------------------------------- #


async def test_ni_le_modele_ni_le_fichier_ni_la_ligne_ne_portent_une_cle(monde, test_client_factory, db_session):
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Sans cle", monde.agent_a.id)
        brut_fichier = (await client.get(f"{ROUTE}/{modele['id']}/export")).text
        brut_liste = (await client.get(ROUTE)).text
    ligne = await db_session.get_configuration(monde.org_a.id, OrganizationConfigurationKey.MODELES_REGLAGES.value)
    for texte in (brut_fichier, brut_liste, json.dumps(ligne.value)):
        assert CLE_SECRETE_A not in texte
        assert "api_key" not in texte
    # The bricks themselves are there (provider, model), without their key.
    assert "gpt-4.1" in brut_fichier and "elevenlabs" in brut_fichier


def test_toute_forme_de_cle_est_retiree_a_toute_profondeur():
    valeur = {
        "a": {"api_key": "SECRET1", "b": [{"credentials": "SECRET2", "ok": 1}]},
        "aws_access_key": "SECRET3", "aws_secret_key": "SECRET4", "aws_session_token": "SECRET5",
        "secret": "SECRET6", "password": "SECRET7", "token": "SECRET8", "client_secret": "SECRET9",
        "garde": "valeur",
    }
    propre = cl.retirer_les_cles(valeur)
    assert "SECRET" not in json.dumps(propre)
    assert propre["garde"] == "valeur" and propre["a"]["b"][0]["ok"] == 1
    assert cl.premiere_cle_trouvee(valeur) is not None and cl.premiere_cle_trouvee(propre) is None


async def test_l_agent_cible_garde_sa_propre_cle(monde, test_client_factory, db_session):
    """The template brings the bricks (provider, model); the agent that receives them keeps ITS keys."""
    async with test_client_factory(monde.user_a) as client_a:
        modele_a = await _creer(client_a, "Briques de A", monde.agent_a.id)
        fichier = (await client_a.get(f"{ROUTE}/{modele_a['id']}/export")).json()
    async with test_client_factory(monde.user_b) as client_b:
        importe = (await client_b.post(f"{ROUTE}/import", json=fichier)).json()
        reponse = await client_b.post(
            f"{ROUTE}/{importe['id']}/appliquer", json={"workflow_id": monde.agent_b.id, "sections": ["briques"]}
        )
        assert reponse.status_code == 200, reponse.text
        assert reponse.json()["non_appliquees"] == [] and reponse.json()["fournisseurs_sans_cle"] == []
    nouvelle = await _active(db_session, monde.agent_b.id)
    pipeline = nouvelle["model_configuration_v2_override"]["byok"]["pipeline"]
    assert pipeline["llm"]["model"] == "gpt-4.1", "the template's model"
    assert pipeline["llm"]["api_key"] == CLE_SECRETE_B, "B's own key, not A's"
    assert pipeline["tts"]["api_key"] == "b-tts" and pipeline["stt"]["api_key"] == "b-stt"
    assert CLE_SECRETE_A not in json.dumps(nouvelle)


async def test_une_brique_sans_cle_n_est_pas_ecrite_et_le_dit_avant_et_apres(monde, test_client_factory, db_session):
    """An agent with no key for a provider the template brings: the brick is NOT written (an override without
    its key would stop the calls), the rest is applied, and the dry run says which provider lacks a key."""
    async with test_client_factory(monde.user_a) as client_a:
        modele_a = await _creer(client_a, "Briques de A", monde.agent_a.id)
        fichier = (await client_a.get(f"{ROUTE}/{modele_a['id']}/export")).json()
    async with test_client_factory(monde.user_b) as client_b:
        importe = (await client_b.post(f"{ROUTE}/import", json=fichier)).json()
        corps = {"workflow_id": monde.agent_b2.id, "sections": ["briques", "tour"]}  # B2 has no settings at all
        a_blanc = (await client_b.post(f"{ROUTE}/{importe['id']}/appliquer", json={**corps, "a_blanc": True})).json()
        assert {"openai", "elevenlabs", "deepgram"} <= set(a_blanc["fournisseurs_sans_cle"])
        assert a_blanc["non_appliquees"][0]["raison"] == "cle-manquante"
        assert await db_session.get_draft_version(monde.agent_b2.id) is None

        reel = (await client_b.post(f"{ROUTE}/{importe['id']}/appliquer", json=corps)).json()
        assert reel["ecrit"] is True and reel["non_appliquees"][0]["cle"] == "model_configuration_v2_override"
    nouvelle = await _active(db_session, monde.agent_b2.id)
    assert "model_configuration_v2_override" not in nouvelle, "no half-written brick"
    assert nouvelle["turn_start_min_words"] == 4, "the other section is applied"


def test_les_briques_vont_ensemble_ou_pas_du_tout():
    """Pure: a template with a full configuration, applied to an agent that holds per-service overlays, does
    not leave both on the agent (they exclude one another)."""
    base = {"model_overrides": {"llm": {"provider": "openai", "model": "x", "api_key": "K-B"}}, "mark_per_service_override": True}
    valeurs = {"model_configuration_v2_override": cl.retirer_les_cles(_v2("K-A"))}
    # Without a key the brick is refused and the agent's overlays stay.
    nouveau, resultat = calculer_l_application(valeurs, ["briques"], base)
    assert nouveau == base and resultat.non_appliquees
    # With the organization's keys, the full configuration replaces the overlays, together with their marker.
    cles_org = {"model_configuration_v2_override": _v2("K-ORG")}
    nouveau, resultat = calculer_l_application(valeurs, ["briques"], base, cles_de_l_organisation=cles_org)
    assert "model_overrides" not in nouveau and "mark_per_service_override" not in nouveau
    assert nouveau["model_configuration_v2_override"]["byok"]["pipeline"]["llm"]["api_key"] == "K-ORG"
    assert {"model_overrides", "mark_per_service_override"} <= set(resultat.retirees)


# --------------------------------------------------------------------------- #
# 5. Export, import: the file refuses what it does not know
# --------------------------------------------------------------------------- #


def _fichier(valeurs, **plus):
    return {"format": "modele-de-reglages-mark", "version_du_format": 1, "nom": "Importe", "valeurs": valeurs, **plus}


async def test_l_import_refuse_ce_qu_il_ne_connait_pas_en_nommant_la_cle(monde, test_client_factory):
    cas = [
        ({"reglage_inconnu": 1}, "reglage_inconnu"),
        ({"user_idle_prompt": "bonjour"}, "user_idle_prompt"),  # kept with the agent
        ({"horaires_ouverture": HORAIRES_A}, "horaires_ouverture"),  # own to the agent
        ({"max_call_duration": -5}, "max_call_duration"),  # out of bounds
        ({"greffier_llm": {"provider": "openai", "api_key": "sk-DANS-LE-FICHIER"}}, "api_key"),  # a key
        ({"turn_start_min_words": None}, "turn_start_min_words"),
    ]
    async with test_client_factory(monde.user_b) as client:
        for valeurs, nom_attendu in cas:
            reponse = await client.post(f"{ROUTE}/import", json=_fichier(valeurs))
            assert reponse.status_code == 422, (valeurs, reponse.text)
            assert nom_attendu in reponse.text, (valeurs, reponse.text)
        autre_format = await client.post(f"{ROUTE}/import", json=_fichier({}, format="autre-chose"))
        assert autre_format.status_code == 422
        assert (await client.get(ROUTE)).json()["modeles"] == [], "nothing was kept"


async def test_aller_retour_export_import_donne_les_memes_valeurs(monde, test_client_factory):
    async with test_client_factory(monde.user_a) as client_a:
        modele = await _creer(client_a, "Aller", monde.agent_a.id)
        fichier = (await client_a.get(f"{ROUTE}/{modele['id']}/export")).json()
        assert fichier["format"] == "modele-de-reglages-mark" and fichier["version_du_format"] == 1
    async with test_client_factory(monde.user_b) as client_b:
        premier = await client_b.post(f"{ROUTE}/import", json=fichier)
        second = await client_b.post(f"{ROUTE}/import", json=fichier)
        assert premier.json()["nom"] == "Aller" and second.json()["nom"] == "Aller (2)"
        assert premier.json()["origine"] is None, "the origin of a file is another organization's agent"
        retour = (await client_b.get(f"{ROUTE}/{premier.json()['id']}/export")).json()
    assert retour["valeurs"] == fichier["valeurs"]


# --------------------------------------------------------------------------- #
# 6. One organization never sees another's templates (M1)
# --------------------------------------------------------------------------- #


async def test_cloisonnement_entre_organisations(monde, test_client_factory, db_session):
    async with test_client_factory(monde.user_a) as client_a:
        modele = await _creer(client_a, "Prive a A", monde.agent_a.id)
    async with test_client_factory(monde.user_b) as client_b:
        assert (await client_b.get(ROUTE)).json()["modeles"] == []
        assert (await client_b.get(f"{ROUTE}/{modele['id']}/export")).status_code == 404
        assert (await client_b.patch(f"{ROUTE}/{modele['id']}", json={"nom": "Pris"})).status_code == 404
        assert (await client_b.delete(f"{ROUTE}/{modele['id']}")).status_code == 404
        corps = {"workflow_id": monde.agent_b.id, "sections": ["tour"]}
        assert (await client_b.post(f"{ROUTE}/{modele['id']}/appliquer", json=corps)).status_code == 404
        # B cannot freeze or set A's agent either.
        assert (await client_b.post(ROUTE, json={"nom": "Vol", "workflow_id": monde.agent_a.id})).status_code == 404
        assert (await client_b.get(f"{ROUTE}/agent/{monde.agent_a.id}")).status_code == 404
    async with test_client_factory(monde.user_a) as client_a:
        pris = {"workflow_id": monde.agent_b.id, "sections": ["tour"]}
        assert (await client_a.post(f"{ROUTE}/{modele['id']}/appliquer", json=pris)).status_code == 404
        # A's row is intact.
        assert [m["nom"] for m in (await client_a.get(ROUTE)).json()["modeles"]] == ["Prive a A"]
    assert await db_session.get_draft_version(monde.agent_b.id) is None, "nothing was written on B's agent"


async def test_sans_organisation_choisie_les_routes_refusent(test_client_factory):
    sans_organisation = SimpleNamespace(selected_organization_id=None)
    async with test_client_factory(sans_organisation) as client:
        for methode, chemin, corps in (
            ("get", ROUTE, None),
            ("post", ROUTE, {"nom": "x", "workflow_id": 1}),
            ("post", f"{ROUTE}/import", _fichier({})),
            ("get", f"{ROUTE}/agent/1", None),
            ("patch", f"{ROUTE}/abc", {"nom": "x"}),
            ("delete", f"{ROUTE}/abc", None),
            ("get", f"{ROUTE}/abc/export", None),
            ("post", f"{ROUTE}/abc/appliquer", {"workflow_id": 1, "sections": ["tour"]}),
        ):
            reponse = await getattr(client, methode)(chemin, **({"json": corps} if corps is not None else {}))
            assert reponse.status_code == 400, (methode, chemin, reponse.status_code)


def test_un_secret_sous_un_autre_nom_ne_part_jamais_dans_un_modele():
    # Revue du chantier : reconnu à un mot de son nom, pas à une liste exacte.
    bloc = {
        "provider": "x",
        "model": "m",
        "auth_token": "s1",
        "access_token": "s2",
        "api_secret": "s3",
        "private_key": "s4",
        "max_tokens": 200,
        "keyterms": ["mot"],
    }
    propre = cl.retirer_les_cles({"llm": bloc})
    assert propre == {"llm": {"provider": "x", "model": "m", "max_tokens": 200, "keyterms": ["mot"]}}
    assert cl.premiere_cle_trouvee({"llm": {"provider": "x", "private_key": "s"}}) == "llm.private_key"
    assert cl.fournisseurs_sans_cle({"llm": {"provider": "x", "auth_token": "s"}}) == []


# --------------------------------------------------------------------------- #
# 8. A specialised agent: its common settings are the main agent's (constat 18)
# --------------------------------------------------------------------------- #


# « Établissement » ne porte que des clés gardées par l'agent : aucune section à griser.
SECTIONS_AVEC_REGLAGES = [s for s in cl.SECTIONS if cl.cles_de_la_section(s)]


def test_chez_un_specialise_les_cles_communes_ne_sont_jamais_ecrites():
    """Pure: the common settings of a specialised agent go to ``non_appliquees`` and keep their value; the
    own ones are untouched."""
    base = {"agent_principal_id": 7, "turn_start_min_words": 2, "horaires_ouverture": HORAIRES_A}
    valeurs = {"turn_start_min_words": 9, "vad_stop_secs": 0.4}
    bloquees = cles_reglees_par_le_principal(base)
    nouveau, resultat = calculer_l_application(valeurs, ["tour"], base, reglees_par_le_principal=bloquees)
    assert nouveau == base
    assert resultat.posees == [] and resultat.retirees == []
    refusees = {r.cle: r.raison for r in resultat.non_appliquees}
    assert refusees == {"turn_start_min_words": "reglee-par-le-principal", "vad_stop_secs": "reglee-par-le-principal"}


def test_un_agent_seul_ou_principal_n_est_pas_concerne():
    assert cles_reglees_par_le_principal({"turn_start_min_words": 2}) == frozenset()
    assert sections_reglees_par_le_principal({}) == []


def test_un_cerveau_propre_garde_les_cles_qui_suivent_le_cerveau():
    seul = cles_reglees_par_le_principal({"agent_principal_id": 7})
    propre = cles_reglees_par_le_principal({"agent_principal_id": 7, "cerveau_propre": True})
    assert set(CLES_SUIVENT_LE_CERVEAU).isdisjoint(propre) and set(CLES_SUIVENT_LE_CERVEAU) <= seul
    # Every section is made of common settings: all greyed with the brain attached, the ones holding only
    # brain-following settings are not once it is detached.
    assert sections_reglees_par_le_principal({"agent_principal_id": 7}) == SECTIONS_AVEC_REGLAGES
    assert "tour" not in sections_reglees_par_le_principal({"agent_principal_id": 7, "cerveau_propre": True})


async def test_appliquer_a_un_specialise_n_ecrit_aucune_cle_commune(monde, test_client_factory, db_session):
    """Through the REAL route: the mention says which sections the main agent sets, the application writes none
    of the common settings and names each with its reason."""
    await db_session.save_workflow_draft(
        monde.agent_a2.id, workflow_configurations={**CONFIG_B, "agent_principal_id": monde.agent_a.id}
    )
    avant = await _active(db_session, monde.agent_a2.id)
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Pour le principal", monde.agent_a.id)
        mention = (await client.get(f"{ROUTE}/agent/{monde.agent_a2.id}")).json()
        assert mention["sections_reglees_par_le_principal"] == SECTIONS_AVEC_REGLAGES
        principal = (await client.get(f"{ROUTE}/agent/{monde.agent_a.id}")).json()
        assert principal["sections_reglees_par_le_principal"] == []

        reponse = await client.post(
            f"{ROUTE}/{modele['id']}/appliquer",
            json={"workflow_id": monde.agent_a2.id, "sections": ["tour", "voix"]},
        )
        assert reponse.status_code == 200, reponse.text
        resultat = reponse.json()
    assert resultat["posees"] == [] and resultat["retirees"] == []
    assert resultat["non_appliquees"] and {r["raison"] for r in resultat["non_appliquees"]} == {"reglee-par-le-principal"}
    apres = await _active(db_session, monde.agent_a2.id)
    assert apres == avant, "nothing common was written on the specialised agent"
