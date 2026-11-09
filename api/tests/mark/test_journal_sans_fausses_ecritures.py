"""[.mark] Clôture, lot A (D23) : le journal n'inscrit que de vraies écritures, et dit lesquelles (quoi : geste et objet).

| Test | Ce qu'il prouve |
|---|---|
| inventaire | chaque route déclarée « sans écriture » existe, passe par POST sous une permission, et se dit avec sa raison ; une route d'écriture ordinaire reste journalisée |
| lecture par POST | ouvrir un agent (``POST /workflow/{id}/validate``) n'écrit aucune ligne |
| vraie écriture | une écriture écrit EXACTEMENT UNE ligne, avec la route et sa cible (``workflow_id``), jamais le corps |
| noms | une page du journal résout les noms des objets en une requête, avec l'organisation de CHAQUE ligne ; un objet supprimé ou d'une autre organisation n'a pas de nom |
| lecture | la route du journal rend le geste et la cible nommée ; une ligne d'avant, sans cible, reste lisible |
"""

from __future__ import annotations

from api.services.equipe_mark import journal_cibles
from api.services.equipe_mark.registre_routes import SANS_ECRITURE, Permission, decision_de, ecrit_quelque_chose
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401
from api.tests.mark.test_principale_protegee import AUTRE, GRAPHE, _agent, _branche_fermee, labo_est  # noqa: F401
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401


def test_chaque_route_sans_ecriture_existe_passe_par_post_sous_une_permission_et_les_autres_restent_journalisees():
    from api.app import app

    routes = {(m, r.path[len("/api/v1"):]) for r in app.routes if getattr(r, "path", "").startswith("/api/v1") for m in (getattr(r, "methods", None) or ())}
    gabarits = [chemin for methode, chemin in routes if methode == "POST"]
    for regle in SANS_ECRITURE:
        trouvees = [c for c in gabarits if regle.motif.match(c)]
        assert trouvees, f"règle sans route : {regle.motif.pattern}"
        for chemin in trouvees:
            decision = decision_de("POST", chemin)
            assert decision is not None and isinstance(decision[0], Permission), chemin
    assert ecrit_quelque_chose("POST", "/workflow/4/validate") is False
    assert ecrit_quelque_chose("PUT", "/workflow/4") is True
    assert ecrit_quelque_chose("POST", "/workflow/4/publish") is True  # une publication écrit
    assert ecrit_quelque_chose("POST", "/tools/") is True


def test_le_geste_se_lit_dans_la_route():
    verbe = lambda route: journal_cibles.verbe_de({"route": route})  # noqa: E731
    assert verbe("POST /workflow/{workflow_id}/publish") == "publier"
    assert verbe("DELETE /tools/{tool_uuid}") == "supprimer"
    assert verbe("POST /tools/") == "creer"
    assert verbe("PUT /workflow/{workflow_id}") == "modifier"
    assert verbe("POST /workflow/{workflow_id}/duplicate") == "dupliquer"
    assert journal_cibles.verbe_de(None) is None
    assert journal_cibles.cible_de({"route": "PUT /x", "cible": {"workflow_id": 4}}) == ("agent", "4")
    assert journal_cibles.cible_de({"route": "PUT /x"}) is None  # ligne d'avant : lisible, sans cible


async def _decider(methode: str, gabarit: str, params: dict):
    """``appliquer_acces`` joué comme le serveur le joue (session d'équipe administratrice) ; rend les lignes que ``journaliser`` a reçues."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from api.services.equipe_mark.acces import appliquer_acces

    connexion = SimpleNamespace(headers={}, path_params=params, scope={"route": SimpleNamespace(path_format=gabarit), "type": "http", "method": methode})
    utilisateur = SimpleNamespace(id=1, selected_organization_id=5)
    acces = SimpleNamespace(permissions=frozenset({"agents.modifier", "agents.publier"}), labo_ouvert=True, tous_les_clients=True, organisations=frozenset({5}))
    ecrites = AsyncMock()
    with (
        patch("api.services.equipe_mark.espaces.rafraichir_labo", AsyncMock()),
        patch("api.services.equipe_mark.acces.acces_de", AsyncMock(return_value=acces)),
        patch("api.services.equipe_mark.acces.detacher_de_sa_session", lambda u: None),
        patch("api.services.equipe_mark.acces.journaliser", ecrites),
    ):
        await appliquer_acces(connexion, utilisateur, par_cle_api=False)
    return [c.args for c in ecrites.await_args_list]


async def test_ouvrir_un_agent_n_ecrit_aucune_ligne_et_une_vraie_ecriture_en_ecrit_une_avec_sa_cible():
    gabarit_lecture = "/api/v1/workflow/{workflow_id}/validate"
    for _ in range(2):  # ouvrir deux fois : jamais de ligne
        assert await _decider("POST", gabarit_lecture, {"workflow_id": 4}) == []
    ecrites = await _decider("PUT", "/api/v1/workflow/{workflow_id}", {"workflow_id": 4})
    assert len(ecrites) == 1  # exactement une
    _, action, organisation, detail = ecrites[0]
    assert action == "agents.modifier" and organisation == 5
    assert detail == {"route": "PUT /workflow/{workflow_id}", "cible": {"workflow_id": 4}}  # la route et sa cible, jamais le corps
    secret = await _decider("PUT", "/api/v1/workflow/{workflow_id}", {"workflow_id": 4, "embed_token": "abc"})
    assert "abc" not in str(secret)  # un paramètre qui ressemble à un secret n'est pas gardé


async def test_les_noms_se_resolvent_en_une_requete_avec_l_organisation_de_la_ligne(org, autre_org, db_session):
    agent = await _agent(db_session, org, nom="Standard des Tilleuls")
    o = org.organisation.id
    noms = await db_session.noms_des_cibles([(o, "agent", str(agent.id)), (autre_org.organisation.id, "agent", str(agent.id)), (o, "agent", "999999"), (o, "agent", "pas-un-nombre")])
    assert noms == {(o, "agent", str(agent.id)): "Standard des Tilleuls"}  # pas d'une autre organisation, pas un objet disparu
    assert await db_session.noms_des_cibles([(autre_org.organisation.id, "agent", str(agent.id))]) == {}  # l'agent d'une autre organisation n'est jamais lu
    assert await db_session.noms_des_cibles([]) == {}


async def test_la_route_du_journal_rend_le_geste_la_cible_nommee_et_garde_lisible_une_ligne_d_avant(org, db_session, async_session, test_client_factory, labo_est):
    agent = await _agent(db_session, org, nom="Standard des Tilleuls")
    o = org.organisation.id
    labo_est(o)
    await _oublier(async_session)
    await db_session.ecrire_journal(user_id=org.utilisateur.id, auteur="x", action="agents.publier", organization_id=o, detail={"route": "POST /workflow/{workflow_id}/publish", "cible": {"workflow_id": agent.id}}, origine="ecran")
    await db_session.ecrire_journal(user_id=org.utilisateur.id, auteur="x", action="agents.modifier", organization_id=o, detail={"route": "PUT /workflow/{workflow_id}", "cible": {"workflow_id": 987654}}, origine="ecran")
    await db_session.ecrire_journal(user_id=org.utilisateur.id, auteur="x", action="agents.modifier", organization_id=o, detail={"route": "PUT /workflow/{workflow_id}"}, origine="ecran")
    async with test_client_factory(org.utilisateur) as client:
        r = await client.get("/api/v1/equipe-mark/journal", params={"organization_id": o, "limit": 10})
    assert r.status_code == 200, r.text
    lignes = {tuple(sorted((l["detail"] or {}).get("cible", {}).items())): l for l in r.json()["lignes"] if l["auteur"] == "x"}
    publie = lignes[(("workflow_id", agent.id),)]
    assert publie["geste"] == "publier" and publie["cible"] == {"type": "agent", "id": str(agent.id), "nom": "Standard des Tilleuls"}
    supprime = lignes[(("workflow_id", 987654),)]
    assert supprime["cible"]["nom"] is None  # objet disparu : repli propre côté écran
    ancienne = lignes[()]
    assert ancienne["cible"] is None and ancienne["geste"] == "modifier"
