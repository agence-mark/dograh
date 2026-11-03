"""[.mark] builder partie 2, D1 (U4, F3, E16) : pour chaque réglage, sa valeur effective et son origine.

| Test | Ce qu'il prouve |
|---|---|
| défaut | une clé jamais écrite vaut le défaut du schéma, origine ``defaut`` |
| agent | une valeur écrite différente de l'héritée est ``agent`` (propre) ; égale à l'héritée, elle est dite héritée |
| principal | un spécialisé lit chez son principal les clés communes (origine ``principal``, non modifiable) ; cerveau détaché : les clés qui suivent le cerveau restent siennes |
| établissement | un agent qui sert une fiche lit ses horaires et son adresse (origine ``etablissement``), même vides |
| organisation | l'adresse de l'organisation, quand ni l'agent ni une fiche n'en ont ; la configuration des modèles, sans valeur rendue |
| couverture | toutes les clés du schéma et les clés propres sont rendues |
| secret | une valeur au nom de secret est masquée ; aucune clé ne sort par la route ; l'agent d'une autre organisation répond 404 |
"""

from types import SimpleNamespace

import pytest

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services import heritage_reglages as h
from api.services.groupe.reglages import CLES_COMMUNES, CLES_PROPRES
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)


def test_une_cle_jamais_ecrite_vaut_le_defaut():
    r = h.calculer({})["max_call_duration"]
    assert (r["origine"], r["valeur"], r["propre"]) == ("defaut", 600, False)


def test_toutes_les_cles_sont_rendues():
    rendues = set(h.calculer({}))
    assert rendues >= set(WorkflowConfigurationDefaults.model_fields) | set(CLES_PROPRES) | set(CLES_COMMUNES)


def test_une_valeur_differente_est_propre_a_l_agent_une_valeur_egale_est_heritee():
    propre = h.calculer({"max_call_duration": 300})["max_call_duration"]
    assert (propre["origine"], propre["propre"], propre["valeur"], propre["valeur_heritee"]) == ("agent", True, 300, 600)
    # L'écran enregistre toute la configuration : une valeur égale à l'héritée n'est pas « propre ».
    egale = h.calculer({"max_call_duration": 600})["max_call_duration"]
    assert (egale["origine"], egale["propre"]) == ("defaut", False)


def test_un_specialise_lit_les_cles_communes_chez_son_principal():
    r = h.calculer(
        {"agent_principal_id": 7, "max_call_duration": 111, "max_user_idle_timeout": 99},
        configurations_du_principal={"max_call_duration": 450},
    )
    appel = r["max_call_duration"]
    assert (appel["origine"], appel["valeur"], appel["modifiable"]) == ("principal", 450, False)
    # Absente chez le principal : le défaut revient, toujours « du principal ».
    assert r["max_user_idle_timeout"]["origine"] == "principal"
    assert r["max_user_idle_timeout"]["valeur"] == WorkflowConfigurationDefaults().max_user_idle_timeout
    # Une clé propre à l'agent reste la sienne.
    assert r["etablissement_id"]["modifiable"] is True


def test_un_cerveau_detache_garde_les_cles_qui_suivent_le_cerveau():
    reglages = {"agent_principal_id": 7, "cerveau_propre": True, "reflexion_de_relance": "high"}
    r = h.calculer(reglages, configurations_du_principal={"reflexion_de_relance": "low"})
    assert r["reflexion_de_relance"]["modifiable"] is True
    assert r["reflexion_de_relance"]["origine"] == "agent"
    attache = h.calculer({"agent_principal_id": 7}, configurations_du_principal={"reflexion_de_relance": "low"})
    assert attache["reflexion_de_relance"]["origine"] == "principal"


def test_une_fiche_servie_donne_ses_horaires_et_son_adresse_meme_vides():
    fiche = SimpleNamespace(horaires_ouverture="Mo-Fr 09:00-18:00", adresse=None)
    r = h.calculer({"horaires_ouverture": "Mo-Su 00:00-24:00", "etablissement_id": "n"}, fiche=fiche)
    horaires = r["horaires_ouverture"]
    assert (horaires["origine"], horaires["valeur_heritee"]) == ("agent", "Mo-Fr 09:00-18:00")
    # Écrite et différente : propre à l'agent, la fiche reste la valeur héritée.
    assert horaires["propre"] is True
    # Sans adresse sur la fiche : vide, jamais celle de l'organisation.
    assert (r["adresse_etablissement"]["origine"], r["adresse_etablissement"]["valeur"]) == ("etablissement", None)
    # Sans valeur écrite, l'origine est la fiche.
    assert h.calculer({"etablissement_id": "n"}, fiche=fiche)["horaires_ouverture"]["origine"] == "etablissement"


def test_l_adresse_de_l_organisation_quand_rien_d_autre():
    organisation = {"voie": "1 rue X", "code_postal": "60000", "commune": "Beauvais"}
    r = h.calculer({}, adresse_de_l_organisation=organisation)["adresse_etablissement"]
    assert (r["origine"], r["valeur"]) == ("organisation", organisation)
    fiche = SimpleNamespace(horaires_ouverture=None, adresse=None)
    avec_fiche = h.calculer({"etablissement_id": "n"}, fiche=fiche, adresse_de_l_organisation=organisation)
    assert avec_fiche["adresse_etablissement"]["origine"] == "etablissement"


def test_la_configuration_des_modeles_n_a_jamais_de_valeur():
    secret = {"llm": {"provider": "x", "api_key": "sk-ne-sort-pas"}}
    r = h.calculer({"model_overrides": secret}, modeles_de_l_organisation=True)
    assert r["model_overrides"]["masquee"] is True and r["model_overrides"]["valeur"] is None
    assert r["model_overrides"]["propre"] is True
    herite = h.calculer({}, modeles_de_l_organisation=True)["model_overrides"]
    assert (herite["origine"], herite["valeur"]) == ("organisation", None)
    sans = h.calculer({}, modeles_de_l_organisation=False)["model_overrides"]
    assert sans["origine"] == "defaut"


def test_un_champ_au_nom_de_secret_est_masque():
    masque = h._masquer({"a": {"webhook_token": "t", "b": [{"api_key": "k", "ok": 1}]}})
    assert masque == {"a": {"webhook_token": "***", "b": [{"api_key": "***", "ok": 1}]}}


@pytest.mark.usefixtures("sans_preparation_des_organisations")
async def test_la_route_rend_l_origine_sans_secret_et_cloisonne(db_session):
    org = await creer_organisation(db_session, "her-a")
    autre = await creer_organisation(db_session, "her-b")
    user, jeton = await creer_compte(db_session, "her-a@example.com", role="Membre", organisations=[org])
    _autre_user, autre_jeton = await creer_compte(
        db_session, "her-b@example.com", role="Administrateur", organisations=[autre]
    )
    principal = await db_session.create_workflow(
        name="P", workflow_definition={}, user_id=user.id, organization_id=org, workflow_configurations={"max_call_duration": 450}
    )
    specialise = await db_session.create_workflow(
        name="S",
        workflow_definition={},
        user_id=user.id,
        organization_id=org,
        workflow_configurations={
            "agent_principal_id": principal.id,
            "max_call_duration": 100,
            "model_overrides": {"llm": {"provider": "x", "api_key": "sk-ne-sort-pas"}},
        },
    )
    async with client_http() as c:
        lu = await c.get(f"/api/v1/workflow/{specialise.id}/heritage-reglages", headers=entetes(jeton, org))
        chez_l_autre = await c.get(f"/api/v1/workflow/{specialise.id}/heritage-reglages", headers=entetes(autre_jeton, autre))
    assert lu.status_code == 200
    reglages = lu.json()["reglages"]
    assert reglages["max_call_duration"]["origine"] == "principal" and reglages["max_call_duration"]["valeur"] == 450
    assert reglages["model_overrides"]["masquee"] is True
    assert "sk-ne-sort-pas" not in lu.text
    assert chez_l_autre.status_code == 404
