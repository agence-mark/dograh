"""[.mark] Chantier agents-specialises, lot 2 : la passation au clavier, le retour au
principal par le code, la fin par le code, le plafond de passations.

Plan `Labo-agent-vocal/plans/agents-specialises/` (A1, A17, A18, A21). Ces tests passent
par les VRAIES routes HTTP du clavier (création de session, messages), sur la base de
test ; seuls les modèles (réponses écrites d'avance) sont remplacés.

| Test | Ce qu'il prouve |
|---|---|
| passation | l'outil `transfer_agent` bascule sur l'agent cible ; il ouvre dans le même tour ; le tour suivant se joue sur son graphe |
| autre organisation | une cible d'une autre organisation est refusée, A continue |
| cible absente | une cible inexistante est refusée, A continue |
| sans passation | rien ne change : ni `agent_actif`, ni `passations` (checkpoint d'avant) |
| retour | l'étape marquée rend la main au principal sans tour de modèle intermédiaire ; le principal répond à l'appelant |
| fin figée | le nœud de fin avec `fins` dit la phrase choisie sur la fiche, sans modèle, et clôt |
| plafond | au-delà du plafond du groupe, la passation est refusée et tracée |
| soi-même | une passation vers soi-même est refusée |
"""

import copy
from unittest.mock import AsyncMock, patch

import pytest

from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from pipecat.tests import MockLLMService


def _noeud(identifiant, typ, nom, prompt, **data):
    return {
        "id": identifiant,
        "type": typ,
        "position": {"x": 0, "y": 0},
        "data": {
            "name": nom,
            "prompt": prompt,
            "allow_interrupt": False,
            "add_global_prompt": False,
            **({"is_start": True} if typ == "startCall" else {}),
            **({"is_end": True} if typ == "endCall" else {}),
            **data,
        },
    }


def _arete(source, cible, label):
    return {
        "id": f"{source}-{cible}",
        "source": source,
        "target": cible,
        "data": {"label": label, "condition": "Quand il le faut."},
    }


def _principal(outils=(), fins=None):
    """Le principal : accueil (outils de passation) et un nœud de fin."""
    fin = {"fins": fins} if fins else {}
    return {
        "nodes": [
            _noeud(
                "p_start",
                "startCall",
                "accueil",
                "Tu routes.",
                greeting_type="text",
                greeting="Bonjour.",
                tool_uuids=list(outils),
            ),
            _noeud("p_fin", "endCall", "fin", "Conclure.", **fin),
        ],
        "edges": [_arete("p_start", "p_fin", "fin")],
    }


def _specialise():
    """Un spécialisé : une étape, puis l'étape de retour au principal."""
    return {
        "nodes": [
            _noeud("s_start", "startCall", "etape", "Tu traites la demande."),
            _noeud(
                "s_retour", "agentNode", "retour", "Retour.", retour_au_principal=True
            ),
        ],
        "edges": [_arete("s_start", "s_retour", "retour")],
    }


async def _agent_de_l_organisation(
    db_session, user, organisation, nom, definition, reglages
):
    workflow = await db_session.create_workflow(
        name=nom,
        workflow_definition=definition,
        user_id=user.id,
        organization_id=organisation,
    )
    await db_session.save_workflow_draft(
        workflow.id, workflow_definition=definition, workflow_configurations=reglages
    )
    await db_session.publish_workflow_draft(workflow.id)
    return workflow


async def _outil_de_passation(db_session, user, organisation, nom, cible):
    return await db_session.create_tool(
        organization_id=organisation,
        user_id=user.id,
        name=nom,
        description=f"Passer à {nom}",
        category="transfer_agent",
        definition={
            "schema_version": 1,
            "type": "transfer_agent",
            "config": {"workflow_id": cible, "message": "", "play_greeting": False},
        },
    )


async def _republier(db_session, workflow, definition, reglages):
    await db_session.save_workflow_draft(
        workflow.id, workflow_definition=definition, workflow_configurations=reglages
    )
    await db_session.publish_workflow_draft(workflow.id)


async def _groupe(
    db_session,
    async_session,
    *,
    reglages_principal=None,
    fins=None,
    outil_vers_soi=False,
):
    """Un principal (le premier agent du run) et un spécialisé, liés des deux côtés."""
    base = copy.deepcopy(FICHE)
    user, principal = await _monter(db_session, async_session, base, _principal())
    organisation = principal.organization_id
    specialise = await _agent_de_l_organisation(
        db_session,
        user,
        organisation,
        "Spécialisé",
        _specialise(),
        {**base, "agent_principal_id": principal.id},
    )
    outil = await _outil_de_passation(
        db_session,
        user,
        organisation,
        "Passer a S",
        principal.id if outil_vers_soi else specialise.id,
    )
    reglages = {
        **base,
        "agents_specialises": [specialise.id],
        **(reglages_principal or {}),
    }
    await _republier(
        db_session, principal, _principal([outil.tool_uuid], fins), reglages
    )
    return user, principal, specialise


async def _session(test_client_factory, user, workflow, modeles, messages):
    """Crée la session (accueil), puis envoie les messages ; rend la dernière réponse
    et la liste des réponses."""
    reponses = []
    async with test_client_factory(user) as client:
        with (
            patch(
                "api.services.workflow.text_chat_runner.create_llm_service",
                side_effect=modeles,
            ),
            patch(
                "api.services.workflow.text_chat_runner.db_client.has_active_recordings",
                new=AsyncMock(return_value=False),
            ),
        ):
            creee = await client.post(
                f"/api/v1/workflow/{workflow.id}/text-chat/sessions", json={}
            )
            assert creee.status_code == 200, creee.text
            session = creee.json()
            revision = session["revision"]
            for texte in messages:
                reponse = await client.post(
                    f"/api/v1/workflow/{workflow.id}/text-chat/sessions/"
                    f"{session['workflow_run_id']}/messages",
                    json={"text": texte, "expected_revision": revision},
                )
                assert reponse.status_code == 200, reponse.text
                reponses.append(reponse.json())
                revision = reponse.json()["revision"]
    return reponses


def _vide():
    return MockLLMService(mock_steps=[], chunk_delay=0.001)


def _dit(*pas):
    return MockLLMService(mock_steps=list(pas), chunk_delay=0.001)


def _appel(nom, identifiant):
    return MockLLMService.create_function_call_chunks(nom, {}, tool_call_id=identifiant)


def _texte(t):
    return MockLLMService.create_text_chunks(t)


def _textes(charge):
    tours = (charge.get("session") or charge).get("turns") or []
    return [((t.get("assistant_message") or {}).get("text") or "") for t in tours]


def _checkpoint(charge):
    return charge["checkpoint"]


@pytest.mark.asyncio
async def test_passation_au_clavier_bascule_et_l_agent_appele_ouvre(
    db_session, async_session, test_client_factory
):
    user, principal, specialise = await _groupe(db_session, async_session)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),  # accueil (texte fixe)
            _dit([*_appel("passer_a_s", "p1")]),  # le principal passe la main
            _vide(),  # la fabrique construit l'agent appelé (son modèle n'est pas joué)
            _dit(
                _texte("Ici le spécialisé, que se passe-t-il ?")
            ),  # il ouvre au passage suivant
            _vide(),  # tour suivant : le modèle du premier agent est créé (non joué)
            _dit(
                _texte("Je note, merci.")
            ),  # tour suivant, sur le graphe du spécialisé
        ],
        ["j'ai une panne", "le poêle fume"],
    )
    premier = reponses[0]
    point = _checkpoint(premier)
    assert point["agent_actif"]["workflow_id"] == specialise.id, point
    assert point["current_node_id"] == "s_start", point
    fiche = point["gathered_context"]
    assert any(
        e.get("vers") == specialise.id
        and not e.get("refusee")
        and e.get("issue") == "completed"
        for e in fiche.get("passations") or []
    ), fiche.get("passations")
    assert [t.get("outcome") for t in fiche.get("agent_transfers") or []] == [
        "completed"
    ]
    evenements = premier.get("events") or premier.get("session", {}).get("events") or []
    assert any(
        (e.get("payload") or {}).get("agent") == "Spécialisé" for e in evenements
    ) or "Spécialisé" in str(premier), premier
    assert "Ici le spécialisé" in str(premier), premier
    second = reponses[1]
    assert "Je note, merci." in str(second), second
    assert _checkpoint(second)["agent_actif"]["workflow_id"] == specialise.id


@pytest.mark.asyncio
async def test_une_cible_d_une_autre_organisation_est_refusee_et_a_continue(
    db_session, async_session, test_client_factory
):
    base = copy.deepcopy(FICHE)
    user, principal = await _monter(db_session, async_session, base, _principal())
    autre_user, etranger = await _monter(db_session, async_session, base, _specialise())
    outil = await _outil_de_passation(
        db_session, user, principal.organization_id, "Passer a S", etranger.id
    )
    await _republier(db_session, principal, _principal([outil.tool_uuid]), base)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            _dit([*_appel("passer_a_s", "p1")], _texte("Je reste avec vous.")),
        ],
        ["j'ai une panne"],
    )
    point = _checkpoint(reponses[0])
    assert "agent_actif" not in point, point
    issues = [
        t.get("outcome") for t in point["gathered_context"].get("agent_transfers") or []
    ]
    assert issues == ["destination_not_found"], issues
    assert "Je reste avec vous." in str(reponses[0])


@pytest.mark.asyncio
async def test_une_cible_absente_est_refusee_et_a_continue(
    db_session, async_session, test_client_factory
):
    base = copy.deepcopy(FICHE)
    user, principal = await _monter(db_session, async_session, base, _principal())
    outil = await _outil_de_passation(
        db_session, user, principal.organization_id, "Passer a S", 987654321
    )
    await _republier(db_session, principal, _principal([outil.tool_uuid]), base)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [_vide(), _dit([*_appel("passer_a_s", "p1")], _texte("Je reste avec vous."))],
        ["j'ai une panne"],
    )
    point = _checkpoint(reponses[0])
    assert "agent_actif" not in point
    assert "Je reste avec vous." in str(reponses[0])


@pytest.mark.asyncio
async def test_sans_passation_le_checkpoint_est_celui_d_avant(
    db_session, async_session, test_client_factory
):
    user, principal, _ = await _groupe(db_session, async_session)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [_vide(), _dit(_texte("Qu'est-ce que je peux faire pour vous ?"))],
        ["bonjour"],
    )
    point = _checkpoint(reponses[0])
    assert "agent_actif" not in point, point
    assert "passations" not in point["gathered_context"], point["gathered_context"]
    assert set(point) == {
        "version",
        "anchor_turn_id",
        "current_node_id",
        "messages",
        "gathered_context",
        "tool_state",
    }


@pytest.mark.asyncio
async def test_l_etape_de_retour_rend_la_main_au_principal_sans_tour_intermediaire(
    db_session, async_session, test_client_factory
):
    user, principal, specialise = await _groupe(db_session, async_session)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            _dit([*_appel("passer_a_s", "p1")]),
            _vide(),
            _dit(_texte("Est-ce que je peux faire autre chose pour vous ?")),
            # Tour 2 : le modèle du premier agent (le principal) est créé d'abord ; c'est
            # lui qui répond au passage suivant, après le retour.
            _dit(_texte("Très bien, je vous passe la suite.")),
            _dit(
                [*_appel("retour", "r1")]
            ),  # le spécialisé prend la porte de retour, rien d'autre
            _vide(),  # la fabrique construit le principal
        ],
        ["j'ai une panne", "oui, une facture aussi"],
    )
    second = reponses[1]
    point = _checkpoint(second)
    assert "agent_actif" not in point, point  # le premier agent, de nouveau
    assert point["current_node_id"] == "p_start", point
    passations = point["gathered_context"].get("passations") or []
    assert [(e.get("raison"), e.get("vers")) for e in passations] == [
        ("Passer a S", specialise.id),
        ("retour", principal.id),
    ], passations
    assert "Très bien, je vous passe la suite." in str(second), second


@pytest.mark.asyncio
async def test_le_retour_apres_autre_chose_attend_la_reponse_de_l_appelant(
    db_session, async_session, test_client_factory
):
    """La porte de retour prise avec « autre chose ? » : le principal ne parle pas,
    il attend la réplique de l'appelant (A21)."""
    user, principal, _ = await _groupe(db_session, async_session)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            _dit([*_appel("passer_a_s", "p1")]),
            _vide(),
            _dit(_texte("C'est noté.")),
            # Tour 2 : le modèle du premier agent (non joué), puis le spécialisé dit
            # « autre chose ? » et prend la porte de retour dans la même réponse.
            _vide(),
            _dit(
                [
                    *_texte("Est-ce que je peux faire autre chose pour vous ?"),
                    *_appel("retour", "r1"),
                ]
            ),
            _vide(),  # la fabrique construit le principal ; il ne parle pas
            # Tour 3 : la réplique de l'appelant arrive au principal.
            _dit(_texte("Je vous écoute pour la facture.")),
        ],
        ["j'ai une panne", "c'est tout pour la panne", "une facture aussi"],
    )
    assert "agent_actif" not in _checkpoint(reponses[1])
    assert "Je vous écoute pour la facture." in str(reponses[2]), reponses[2]


@pytest.mark.asyncio
async def test_le_noeud_de_fin_dit_la_phrase_figee_choisie_sur_la_fiche(
    db_session, async_session, test_client_factory
):
    fins = [
        {"champ": "nom", "phrase": "Votre demande est transmise. Au revoir."},
        {"phrase": "Merci de votre appel."},
    ]
    user, principal, _ = await _groupe(db_session, async_session, fins=fins)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            _dit(
                MockLLMService.create_function_call_chunks(
                    "noter_information", {"nom": "Lemaire"}, tool_call_id="n1"
                ),
                _texte("C'est noté."),
            ),
            _dit([*_appel("fin", "f1")]),
        ],
        ["je m'appelle Lemaire", "c'est tout"],
    )
    second = reponses[1]
    assert "Votre demande est transmise. Au revoir." in str(second), second
    assert "Merci de votre appel." not in str(second)


@pytest.mark.asyncio
async def test_au_dela_du_plafond_la_passation_est_refusee_et_tracee(
    db_session, async_session, test_client_factory
):
    user, principal, specialise = await _groupe(
        db_session, async_session, reglages_principal={"passations_max_par_appel": 0}
    )
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            _dit([*_appel("passer_a_s", "p1")], _texte("Je prends votre demande.")),
        ],
        ["j'ai une panne"],
    )
    point = _checkpoint(reponses[0])
    assert "agent_actif" not in point
    refus = point["gathered_context"].get("passations") or []
    assert refus and refus[-1].get("refusee") and refus[-1].get("motif") == "plafond", (
        refus
    )
    assert "Je prends votre demande." in str(reponses[0])


@pytest.mark.asyncio
async def test_une_passation_vers_soi_meme_est_refusee(
    db_session, async_session, test_client_factory
):
    user, principal, _ = await _groupe(db_session, async_session, outil_vers_soi=True)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [_vide(), _dit([*_appel("passer_a_s", "p1")], _texte("Je continue."))],
        ["j'ai une panne"],
    )
    refus = _checkpoint(reponses[0])["gathered_context"].get("passations") or []
    assert refus and refus[-1].get("motif") == "soi_meme", refus
