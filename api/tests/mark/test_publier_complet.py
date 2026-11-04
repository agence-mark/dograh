"""[.mark] Builder partie 3, sous-lot 3 (SE-12 / D-1, D-2, D-4) : « Publier » complet.

| Test | Ce qu'il prouve |
|---|---|
| tableau des changements | une ligne par champ changé avec le texte avant et après, par étape ajoutée ou retirée, par liaison et par réglage ; un déplacement n'est pas un changement ; un champ au nom de secret est masqué ; les textes sont raccourcis |
| route des changements | le brouillon comparé à la version publiée (vraie route, vraie base) ; un agent d'une autre organisation est un 404 ; sans brouillon, 409 |
| spécialistes du groupe | un choix par spécialiste : seuls ceux cochés partent, le principal reste en brouillon si on le dit ; un agent hors du groupe est refusé ; sans corps, tout le groupe comme avant |
| défauts de l'organisation | éteints par défaut ; écrits, ils valent pour un agent sans réglages propres (fenêtre et publication à part) ; les réglages propres d'un agent gagnent ; une autre organisation ne les voit pas |
"""

from __future__ import annotations

from api.services.groupe import groupe as service
from api.services.publication import changements, defauts_org, deploiement
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _creer_groupe, _oublier, autre_org, org  # noqa: F401


def _graphe(prompt="Bonjour", position=(0, 0), extra=None):
    return {
        "nodes": [
            {
                "id": "1",
                "type": "agentNode",
                "position": {"x": position[0], "y": position[1]},
                "data": {"name": "Accueil", "prompt": prompt, **(extra or {})},
            }
        ],
        "edges": [],
    }


# --- le calcul (pur) --------------------------------------------------------------------------------------------------------------


def test_une_ligne_par_champ_change_avec_l_avant_et_l_apres():
    r = changements.calculer(_graphe("Bonjour, ici le cabinet."), _graphe("Bonjour"))
    assert r["total"] == 1
    assert r["lignes"][0] == {
        "genre": "node_changed",
        "ou": "Accueil",
        "champ": "prompt",
        "avant": "Bonjour",
        "apres": "Bonjour, ici le cabinet.",
    }


def test_un_deplacement_dans_le_graphe_n_est_pas_un_changement():
    assert changements.calculer(_graphe(position=(50, 80)), _graphe(position=(0, 0))) == {"lignes": [], "total": 0}


def test_etapes_et_liaisons_ajoutees_retirees_changees():
    ancien = {
        "nodes": _graphe()["nodes"] + [{"id": "2", "data": {"name": "Fin"}}],
        "edges": [{"id": "e1", "source": "1", "target": "2", "data": {"condition": "a"}}],
    }
    nouveau = {
        "nodes": _graphe()["nodes"] + [{"id": "3", "data": {"name": "Rendez-vous"}}],
        "edges": [
            {"id": "e1", "source": "1", "target": "3", "data": {"condition": "b"}},
            {"id": "e2", "source": "3", "target": "1"},
        ],
    }
    genres = sorted(ligne["genre"] for ligne in changements.calculer(nouveau, ancien)["lignes"])
    assert genres == ["link_added", "link_changed", "node_added", "node_removed"]


def test_un_reglage_change_est_une_ligne_et_un_secret_est_masque():
    r = changements.calculer(
        _graphe(extra={"api_key": "sk-secret-123"}),
        _graphe(extra={"api_key": "sk-ancien-456"}),
        {"user_speech_timeout": 1.4, "mon_token": "t2"},
        {"user_speech_timeout": 1.0, "mon_token": "t1"},
    )
    corps = repr(r)
    assert "sk-secret-123" not in corps and "sk-ancien-456" not in corps
    assert "'t1'" not in corps and "'t2'" not in corps
    reglage = next(ligne for ligne in r["lignes"] if ligne["ou"] == "user_speech_timeout")
    assert (reglage["genre"], reglage["avant"], reglage["apres"]) == ("setting_changed", "1.0", "1.4")


def test_les_textes_sont_raccourcis_et_les_lignes_bornees():
    r = changements.calculer(_graphe("x" * 5000), _graphe("y"))
    assert len(r["lignes"][0]["apres"]) <= changements.LONGUEUR_MAX + 1
    beaucoup = {"nodes": [{"id": str(i), "data": {"name": f"n{i}"}} for i in range(200)], "edges": []}
    gros = changements.calculer(beaucoup, None)
    assert gros["total"] == 200 and len(gros["lignes"]) == changements.LIGNES_MAX


def test_une_premiere_publication_montre_tout_comme_ajoute():
    r = changements.calculer(_graphe(), None)
    assert [ligne["genre"] for ligne in r["lignes"]] == ["node_added"]


# --- la route des changements ------------------------------------------------------------------------------------------------------


async def _groupe(client, db_session, org):
    principal_id, _, specialises = await _creer_groupe(client, db_session, org, specialises=("Un", "Deux"))
    return principal_id, specialises


async def test_la_route_compare_le_brouillon_a_la_version_publiee(org, db_session, async_session, test_client_factory):
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _ = await _groupe(client, db_session, org)
        await _oublier(async_session)
        assert (await client.post(f"/api/v1/workflow/{principal_id}/publish")).status_code == 200
        await _oublier(async_session)
        agent = await service.lire_agent(principal_id, org.organisation.id)
        graphe = agent.definition
        avant = graphe["nodes"][1]["data"]["prompt"]
        graphe["nodes"][1]["data"]["prompt"] = avant + " Nouvelle phrase."
        await db_session.save_workflow_draft(principal_id, workflow_definition=graphe)
        await _oublier(async_session)
        r = await client.get(f"/api/v1/builder/publication/{principal_id}/changements")
        assert r.status_code == 200, r.text
        corps = r.json()
        assert corps["version_publiee"] is not None and corps["version_brouillon"] > corps["version_publiee"]
        ligne = next(ligne for ligne in corps["lignes"] if ligne["champ"] == "prompt")
        assert avant.startswith(ligne["avant"][:20]) and ligne["apres"].endswith("Nouvelle phrase.")


async def test_la_route_des_changements_refuse_un_autre_client_et_dit_quand_il_n_y_a_pas_de_brouillon(
    org, autre_org, db_session, async_session, test_client_factory
):
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _ = await _groupe(client, db_session, org)
        await _oublier(async_session)
        await client.post(f"/api/v1/workflow/{principal_id}/publish")
        await _oublier(async_session)
        assert (await client.get(f"/api/v1/builder/publication/{principal_id}/changements")).status_code == 409
    async with test_client_factory(autre_org.utilisateur) as autre:
        assert (await autre.get(f"/api/v1/builder/publication/{principal_id}/changements")).status_code == 404


# --- les spécialistes du groupe, un choix par spécialiste --------------------------------------------------------------------------


async def test_seuls_les_specialistes_coches_partent_et_le_principal_reste_en_brouillon(
    org, db_session, async_session, test_client_factory
):
    async with test_client_factory(org.utilisateur) as client:
        principal_id, [s1, s2] = await _groupe(client, db_session, org)
        await _oublier(async_session)
        r = await client.post(
            f"/api/v1/workflow/{principal_id}/groupe/publier", json={"specialises": [s2], "avec_le_principal": False}
        )
        assert r.status_code == 200, r.text
        assert [p["id"] for p in r.json()["publies"]] == [s2]
    await _oublier(async_session)
    assert await db_session.get_draft_version(s2) is None
    assert await db_session.get_draft_version(s1) is not None, "le spécialiste non coché reste en brouillon"
    assert await db_session.get_draft_version(principal_id) is not None, "le principal n'est pas parti"


async def test_un_agent_hors_du_groupe_ou_le_principal_ne_sont_pas_des_specialistes_a_publier(
    org, db_session, async_session, test_client_factory
):
    async with test_client_factory(org.utilisateur) as client:
        principal_id, [s1, _] = await _groupe(client, db_session, org)
        seul = await db_session.create_workflow(
            name="Seul",
            workflow_definition=service.graphe_minimal_du_principal(),
            user_id=org.utilisateur.id,
            organization_id=org.organisation.id,
        )
        await _oublier(async_session)
        for intrus in (seul.id, principal_id):
            r = await client.post(f"/api/v1/workflow/{principal_id}/groupe/publier", json={"specialises": [s1, intrus]})
            assert r.status_code == 404, r.text
    await _oublier(async_session)
    assert await db_session.get_draft_version(s1) is not None, "rien n'est parti si un choix est refusé"


# --- les défauts de l'organisation -------------------------------------------------------------------------------------------------


async def test_les_defauts_sont_eteints_puis_ecrits_et_cloisonnes(org, autre_org, test_client_factory):
    async with test_client_factory(org.utilisateur) as client:
        vide = (await client.get("/api/v1/builder/publication-organisation")).json()
        assert vide["deploiement"]["actif"] is False and vide["controles"]["tests_obligatoires"] == "bloque"
        corps = {"controles": {**vide["controles"], "attaques": "previent"}, "deploiement": {"actif": True}}
        r = await client.put("/api/v1/builder/publication-organisation", json=corps)
        assert r.status_code == 200, r.text
        relu = (await client.get("/api/v1/builder/publication-organisation")).json()
        assert relu["deploiement"]["actif"] is True and relu["controles"]["attaques"] == "previent"
        refuse = await client.put("/api/v1/builder/publication-organisation", json={"controles": {"inconnu": "bloque"}})
        assert refuse.status_code == 422
    async with test_client_factory(autre_org.utilisateur) as autre:
        assert (await autre.get("/api/v1/builder/publication-organisation")).json()["deploiement"]["actif"] is False


async def test_un_agent_sans_reglages_propres_recoit_ceux_de_l_organisation_et_le_sien_gagne(
    org, db_session, async_session, test_client_factory
):
    async with test_client_factory(org.utilisateur) as client:
        principal_id, [s1, _] = await _groupe(client, db_session, org)
        await _oublier(async_session)
        # Sans défauts de l'organisation : une part est refusée (déploiement éteint).
        assert (await client.post(f"/api/v1/workflow/{principal_id}/publish")).status_code == 200
        await db_session.save_workflow_draft(principal_id, workflow_configurations={"user_speech_timeout": 1.2})
        await _oublier(async_session)
        refus = await client.post(f"/api/v1/workflow/{principal_id}/publish", json={"pourcentage": 25})
        assert refus.status_code == 422, refus.text
        # L'organisation allume le déploiement : la fenêtre le montre, la publication par part passe, la ligne est écrite.
        await client.put("/api/v1/builder/publication-organisation", json={"controles": {}, "deploiement": {"actif": True}})
        vue = (await client.get(f"/api/v1/builder/publication/{principal_id}")).json()
        assert vue["deploiement_actif"] is True
        ok = await client.post(f"/api/v1/workflow/{principal_id}/publish", json={"pourcentage": 25})
        assert ok.status_code == 200, ok.text
        await _oublier(async_session)
        ligne = await deploiement.lire(org.organisation.id, principal_id)
        assert ligne is not None and ligne["pourcentage"] == 25
        publie = (await db_session.get_workflow(principal_id, organization_id=org.organisation.id)).released_definition
        assert publie.workflow_configurations["publication"]["deploiement"]["actif"] is True
        # Le sien gagne : un agent qui a écrit « éteint » ne suit pas l'organisation.
        await db_session.save_workflow_draft(s1, workflow_configurations={"publication": {"deploiement": {"actif": False}}})
        await _oublier(async_session)
        propre = (await client.get(f"/api/v1/builder/publication/{s1}")).json()
        assert propre["deploiement_actif"] is False


async def test_effectives_ne_lit_rien_quand_l_agent_a_ses_reglages(monkeypatch):
    async def interdit(*_a, **_k):
        raise AssertionError("must not read the organization when the agent has its own settings")

    monkeypatch.setattr(defauts_org, "lire", interdit)
    propres = {"publication": {"deploiement": {"actif": False}}}
    assert await defauts_org.effectives(1, propres) == propres
