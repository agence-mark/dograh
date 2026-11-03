"""[.mark] Builder partie 2, U3 sexies points 1 à 4 : les routes d'Outils par la vraie application, et l'essai de tous les types.

| Test | Ce qu'il prouve |
|---|---|
| un type, une relecture | chaque type d'outil est créé, enregistré et relu à l'identique par la vraie route |
| essai HTTP | un outil qui écrit refuse l'essai direct ; en réponse simulée il passe sans contacter le service |
| essai d'un logiciel | validation à blanc des paramètres, sans rien envoyer |
| essai MCP | exige un compte de test ; réponses enregistrées en fichier |
| calculatrice | essayée directement |
| premier essai | validé par une personne, seulement après un essai réussi ; une mise à jour de l'outil le garde |
| secret | la valeur d'un en-tête secret n'est jamais dans une réponse de l'API |
| cloisonnement | l'essai, la validation et les statistiques d'un outil d'une autre organisation : 404 |
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

HTTP = {
    "schema_version": 1,
    "type": "http_api",
    "config": {
        "method": "POST",
        "url": "https://agenda.example.test/rdv/{{id}}",
        "parameters": [
            {"name": "id", "type": "string", "description": "Rendez-vous.", "required": True, "emplacement": "chemin"},
            {"name": "ton", "type": "string", "description": "Ton.", "required": False, "valeurs_permises": ["court", "long"], "defaut": "court"},
        ],
        "chemins_gardes": ["rdv.date"],
        "copies_dans_la_fiche": [{"chemin": "rdv.id", "cle": "rdv_id"}],
        "reponses_simulees": [{"nom": "ok", "quand": {"id": "1"}, "statut": 200, "donnees": {"rdv": {"id": 1, "date": "jeudi"}}}],
        "phrase_avant_mode": "auto",
        "customMessage": "Je regarde",
        "mode_execution": "immediat",
        "interruption_appelant": True,
        "phrase_attente": "Toujours là",
        "seuil_patience_ms": 900,
        "phrase_repli": "Je note votre demande",
        "en_tetes_ext": [{"nom": "X-Source", "sorte": "texte", "valeur": "mark"}],
    },
}
MCP = {
    "schema_version": 1,
    "type": "mcp",
    "config": {
        "transport": "sse",
        "url": "https://mcp.example.test/sse",
        "timeout_secs": 12,
        "sse_read_timeout_secs": 60,
        "reglages_outils": {"effacer": "desactive", "payer": "confirmer"},
        "en_tetes_ext": [{"nom": "X-Zone", "sorte": "texte", "valeur": "eu"}],
        "phrase_attente": "Un instant",
    },
}
CALCULATRICE = {"schema_version": 1, "type": "calculator"}
FIN = {"schema_version": 1, "type": "end_call", "config": {"endCallReason": True}}
DECOUVERTS = [{"name": "chercher", "description": "Cherche."}, {"name": "effacer", "description": "Efface."}, {"name": "payer", "description": "Paye."}]


async def _monde(db, suffixe: str):
    org = await creer_organisation(db, f"outils-{suffixe}")
    user, jeton = await creer_compte(db, f"outils-{suffixe}@example.com", role="Administrateur", organisations=[org])
    return org, user, jeton


async def _creer(c, jeton, org, nom, definition):
    with patch("api.services.tool_management.discover_mcp_tools", AsyncMock(return_value=DECOUVERTS)):
        r = await c.post("/api/v1/tools/", headers=entetes(jeton, org), json={"name": nom, "definition": definition})
    assert r.status_code == 200, r.text
    return r.json()


def _contient(envoye, relu) -> bool:
    """Tout ce qui a été envoyé est relu à l'identique (la relecture ajoute seulement des valeurs par défaut vides)."""
    if isinstance(envoye, dict):
        return isinstance(relu, dict) and all(k in relu and _contient(v, relu[k]) for k, v in envoye.items())
    if isinstance(envoye, list):
        return isinstance(relu, list) and len(envoye) == len(relu) and all(_contient(a, b) for a, b in zip(envoye, relu))
    return envoye == relu


def _meme_config(envoyee: dict, relue: dict) -> None:
    for cle, valeur in envoyee.items():
        assert _contient(valeur, relue[cle]), cle


@pytest.mark.parametrize("definition", [HTTP, MCP, FIN])
async def test_chaque_type_est_cree_et_relu_a_l_identique(db_session, definition):
    org, _, jeton = await _monde(db_session, f"relecture-{definition['type']}")
    async with client_http() as c:
        cree = await _creer(c, jeton, org, f"Outil {definition['type']}", definition)
        relu = (await c.get(f"/api/v1/tools/{cree['tool_uuid']}", headers=entetes(jeton, org))).json()
    assert relu["category"] == definition["type"]
    _meme_config(definition["config"], relu["definition"]["config"])
    if definition["type"] == "mcp":
        assert relu["definition"]["config"]["discovered_tools"] == DECOUVERTS  # catalogue découvert en SSE


async def test_une_calculatrice_est_creee_et_relue(db_session):
    org, _, jeton = await _monde(db_session, "calc")
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Calcul", CALCULATRICE)
        relu = (await c.get(f"/api/v1/tools/{cree['tool_uuid']}", headers=entetes(jeton, org))).json()
    assert relu["definition"]["type"] == "calculator"


async def test_un_outil_logiciel_est_cree_et_relu(db_session):
    from api.services.integrations.connectors.catalogue import connecteurs

    c0 = next(x for x in connecteurs() if not x.interne and x.actions)
    action = c0.actions[0]
    definition = {
        "schema_version": 1,
        "type": "integration",
        "config": {"connecteur": c0.nom, "action": action.nom, "reglages": {}, "phrase_attente": "Un instant", "phrase_repli": "Je note"},
    }
    org, _, jeton = await _monde(db_session, "logiciel")
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Logiciel", definition)
        relu = (await c.get(f"/api/v1/tools/{cree['tool_uuid']}", headers=entetes(jeton, org))).json()
    _meme_config({k: v for k, v in definition["config"].items() if k != "reglages"}, relu["definition"]["config"])


async def test_essai_http_un_outil_qui_ecrit_exige_une_reponse_simulee(db_session):
    org, _, jeton = await _monde(db_session, "essai-http")
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Rdv", HTTP)
        uuid = cree["tool_uuid"]
        direct = await c.post(f"/api/v1/tools/{uuid}/essai", headers=entetes(jeton, org), json={"arguments": {"id": "1"}, "mode": "direct"})
        simule = await c.post(f"/api/v1/tools/{uuid}/essai", headers=entetes(jeton, org), json={"arguments": {"id": "1"}, "mode": "simule"})
        relu = (await c.get(f"/api/v1/tools/{uuid}", headers=entetes(jeton, org))).json()
    assert direct.status_code == 409  # POST : écrit chez le client
    corps = simule.json()
    assert simule.status_code == 200 and corps["reussi"] and corps["simulee"] and corps["ecrit"]
    assert corps["donnees"] == {"rdv": {"date": "jeudi"}} and corps["copies"] == {"rdv_id": 1}
    assert relu["definition"]["config"]["dernier_essai"]["reussi"] is True


async def test_essai_simule_sans_reponse_enregistree_est_refuse(db_session):
    sans = {**HTTP, "config": {**HTTP["config"], "reponses_simulees": []}}
    org, _, jeton = await _monde(db_session, "essai-sans")
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Rdv", sans)
        r = await c.post(f"/api/v1/tools/{cree['tool_uuid']}/essai", headers=entetes(jeton, org), json={"arguments": {"id": "1"}, "mode": "simule"})
    assert r.status_code == 422


async def test_essai_http_en_lecture_part_directement(db_session):
    lecture = {**HTTP, "config": {**HTTP["config"], "method": "GET", "reponses_simulees": []}}
    org, _, jeton = await _monde(db_session, "essai-get")
    fausse = AsyncMock(return_value={"status": "success", "status_code": 200, "data": {"rdv": {"id": 3, "date": "lundi"}}})
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Lire", lecture)
        with patch("api.services.workflow.tools.custom_tool.execute_http_tool", fausse):
            r = await c.post(f"/api/v1/tools/{cree['tool_uuid']}/essai", headers=entetes(jeton, org), json={"arguments": {"id": "3"}, "mode": "direct"})
    assert r.status_code == 200 and r.json()["reussi"] and not r.json()["ecrit"]
    assert fausse.await_args.kwargs["simuler"] is False  # l'essai direct ne sert jamais une simulation


async def test_essai_calculatrice(db_session):
    org, _, jeton = await _monde(db_session, "essai-calc")
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Calcul", CALCULATRICE)
        r = await c.post(f"/api/v1/tools/{cree['tool_uuid']}/essai", headers=entetes(jeton, org), json={"arguments": {"expression": "2 * (3 + 4)"}})
        vide = await c.post(f"/api/v1/tools/{cree['tool_uuid']}/essai", headers=entetes(jeton, org), json={"arguments": {}})
    assert r.status_code == 200 and r.json()["reussi"] and "14" in str(r.json()["donnees"])
    assert vide.status_code == 422


async def test_essai_d_une_action_de_logiciel_valide_a_blanc_sans_rien_envoyer(db_session):
    from api.services.integrations.connectors.catalogue import connecteurs

    c0 = next(x for x in connecteurs() if not x.interne and any(a.ecrit for a in x.actions))
    action = next(a for a in c0.actions if a.ecrit)
    definition = {"schema_version": 1, "type": "integration", "config": {"connecteur": c0.nom, "action": action.nom, "reglages": {}}}
    requis = {p.nom: "x" for p in action.parametres if p.obligatoire}
    org, _, jeton = await _monde(db_session, "essai-logiciel")
    relais = AsyncMock()
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Ecrire", definition)
        with patch("api.services.integrations.connectors.nango.relayer", relais):
            direct = await c.post(f"/api/v1/tools/{cree['tool_uuid']}/essai", headers=entetes(jeton, org), json={"arguments": requis, "mode": "direct"})
            simule = await c.post(f"/api/v1/tools/{cree['tool_uuid']}/essai", headers=entetes(jeton, org), json={"arguments": requis, "mode": "simule"})
            manque = await c.post(f"/api/v1/tools/{cree['tool_uuid']}/essai", headers=entetes(jeton, org), json={"arguments": {}, "mode": "simule"})
    assert direct.status_code == 409  # une action qui écrit
    assert simule.json()["reussi"] is True and simule.json()["simulee"] is True
    relais.assert_not_awaited()
    if any(p.obligatoire for p in action.parametres):
        assert manque.json()["reussi"] is False and manque.json()["manquants"]


async def test_essai_mcp_sur_un_compte_de_test_avec_reponse_enregistree(db_session):
    org, _, jeton = await _monde(db_session, "essai-mcp")
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Serveur", MCP)
        uuid = cree["tool_uuid"]
        direct = await c.post(f"/api/v1/tools/{uuid}/essai", headers=entetes(jeton, org), json={"arguments": {}, "mode": "direct", "outil_mcp": "chercher"})
        simule = await c.post(f"/api/v1/tools/{uuid}/essai", headers=entetes(jeton, org), json={"arguments": {}, "mode": "simule", "outil_mcp": "chercher"})
        sans_nom = await c.post(f"/api/v1/tools/{uuid}/essai", headers=entetes(jeton, org), json={"arguments": {}, "mode": "compte_de_test"})
        with patch("api.services.outils_mark.essai.appeler_outil_mcp", AsyncMock(return_value="trouvé : 3")):
            ok = await c.post(f"/api/v1/tools/{uuid}/essai", headers=entetes(jeton, org), json={"arguments": {"q": "x"}, "mode": "compte_de_test", "outil_mcp": "chercher"})
        with patch("api.services.outils_mark.essai.appeler_outil_mcp", AsyncMock(side_effect=RuntimeError("serveur muet"))):
            ko = await c.post(f"/api/v1/tools/{uuid}/essai", headers=entetes(jeton, org), json={"arguments": {}, "mode": "compte_de_test", "outil_mcp": "chercher"})
    assert direct.status_code == 409 and simule.status_code == 422 and sans_nom.status_code == 422
    assert ok.json()["reussi"] is True and ok.json()["donnees"] == "trouvé : 3"
    assert ko.json()["reussi"] is False and "serveur muet" in ko.json()["message"]


async def test_un_type_sans_essai_est_refuse(db_session):
    org, _, jeton = await _monde(db_session, "essai-fin")
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Fin", FIN)
        r = await c.post(f"/api/v1/tools/{cree['tool_uuid']}/essai", headers=entetes(jeton, org), json={"arguments": {}})
    assert r.status_code == 400


async def test_le_premier_essai_est_valide_par_une_personne_apres_un_essai_reussi(db_session):
    org, user, jeton = await _monde(db_session, "premier")
    async with client_http() as c:
        cree = await _creer(c, jeton, org, "Rdv", HTTP)
        uuid = cree["tool_uuid"]
        trop_tot = await c.post(f"/api/v1/tools/{uuid}/premier-essai", headers=entetes(jeton, org))
        await c.post(f"/api/v1/tools/{uuid}/essai", headers=entetes(jeton, org), json={"arguments": {"id": "1"}, "mode": "simule"})
        valide = await c.post(f"/api/v1/tools/{uuid}/premier-essai", headers=entetes(jeton, org))
        # Une mise à jour de l'outil par l'écran garde le premier essai (il est écrit par le serveur).
        miseajour = await c.put(
            f"/api/v1/tools/{uuid}", headers=entetes(jeton, org), json={"definition": {**HTTP, "config": {**HTTP["config"], "premier_essai": {"valide_par": "pirate"}}}}
        )
        relu = (await c.get(f"/api/v1/tools/{uuid}", headers=entetes(jeton, org))).json()
    assert trop_tot.status_code == 409
    assert valide.status_code == 200 and valide.json()["mode"] == "simule" and valide.json()["valide_par"]
    assert miseajour.status_code == 200
    premier = relu["definition"]["config"]["premier_essai"]
    assert premier["valide_par"] != "pirate" and premier["valide_par"] == valide.json()["valide_par"]
    assert relu["definition"]["config"]["dernier_essai"]["reussi"] is True


async def test_un_secret_n_est_jamais_dans_une_reponse_de_l_api(db_session):
    org, _, jeton = await _monde(db_session, "secret")
    async with client_http() as c:
        identifiant = await c.post(
            "/api/v1/credentials/",
            headers=entetes(jeton, org),
            json={"name": "Clé agenda", "credential_type": "custom_header", "credential_data": {"header_name": "X-K", "header_value": "valeur-ultra-secrete"}},
        )
        uuid_cle = identifiant.json()["uuid"]
        definition = {**HTTP, "config": {**HTTP["config"], "en_tetes_ext": [{"nom": "X-K", "sorte": "secret", "identifiant_uuid": uuid_cle}]}}
        cree = await _creer(c, jeton, org, "Rdv secret", definition)
        liste = await c.get("/api/v1/tools/", headers=entetes(jeton, org))
        essai = await c.post(f"/api/v1/tools/{cree['tool_uuid']}/essai", headers=entetes(jeton, org), json={"arguments": {"id": "1"}, "mode": "simule"})
        relu = await c.get(f"/api/v1/credentials/{uuid_cle}", headers=entetes(jeton, org))
    for r in (identifiant, liste, essai, relu):
        assert "valeur-ultra-secrete" not in r.text


async def test_un_en_tete_secret_d_une_autre_organisation_est_refuse_a_l_enregistrement(db_session):
    org_a, _, jeton_a = await _monde(db_session, "iso-a")
    org_b, _, jeton_b = await _monde(db_session, "iso-b")
    async with client_http() as c:
        cle_b = (
            await c.post(
                "/api/v1/credentials/",
                headers=entetes(jeton_b, org_b),
                json={"name": "Clé B", "credential_type": "bearer_token", "credential_data": {"token": "jeton-de-b"}},
            )
        ).json()["uuid"]
        definition = {**HTTP, "config": {**HTTP["config"], "en_tetes_ext": [{"nom": "X-K", "sorte": "secret", "identifiant_uuid": cle_b}]}}
        r = await c.post("/api/v1/tools/", headers=entetes(jeton_a, org_a), json={"name": "Vol", "definition": definition})
    assert r.status_code == 404 and "jeton-de-b" not in r.text


async def test_cloisonnement_essai_validation_et_statistiques(db_session):
    org_a, _, jeton_a = await _monde(db_session, "cloison-a")
    org_b, _, jeton_b = await _monde(db_session, "cloison-b")
    async with client_http() as c:
        cree = await _creer(c, jeton_a, org_a, "Rdv", HTTP)
        uuid = cree["tool_uuid"]
        essai = await c.post(f"/api/v1/tools/{uuid}/essai", headers=entetes(jeton_b, org_b), json={"arguments": {"id": "1"}, "mode": "simule"})
        valide = await c.post(f"/api/v1/tools/{uuid}/premier-essai", headers=entetes(jeton_b, org_b))
        stats = await c.get(f"/api/v1/tools/{uuid}/statistiques", headers=entetes(jeton_b, org_b))
        resume = await c.get("/api/v1/tools/statistiques", headers=entetes(jeton_b, org_b))
    assert essai.status_code == 404 and valide.status_code == 404 and stats.status_code == 404
    assert resume.status_code == 200 and uuid not in resume.json()
