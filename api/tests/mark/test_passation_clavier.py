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
| retour | l'étape marquée rend la main au principal sans tour de modèle intermédiaire ; le principal répond à l'appelant ; il ne reçoit que la dernière étape du spécialisé |
| fin figée | le nœud de fin avec `fins` dit la phrase choisie sur la fiche, sans modèle, et clôt |
| plafond | au-delà du plafond du groupe, la passation est refusée et tracée |
| soi-même | une passation vers soi-même est refusée |
| hors du groupe | une passation vers un spécialisé hors de la liste du principal est refusée |
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


def _principal(outils=(), fins=None, avec_retour=False):
    """Le principal : accueil (outils de passation) et un nœud de fin. ``avec_retour`` (lot 2 d'orchestrateur-
    trois-cerveaux, D1) : et son étape de retour, sans arête entrante, qui porte les mêmes outils."""
    fin = {"fins": fins} if fins else {}
    noeuds = [
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
    ]
    aretes = [_arete("p_start", "p_fin", "fin")]
    if avec_retour:
        noeuds.append(
            _noeud(
                "p_retour",
                "agentNode",
                "reprise",
                "Tu reprends la conversation.",
                etape_de_retour=True,
                tool_uuids=list(outils),
            )
        )
        aretes.append(_arete("p_retour", "p_fin", "fin"))
    return {"nodes": noeuds, "edges": aretes}


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
    avec_retour=False,
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
        db_session,
        principal,
        _principal([outil.tool_uuid], fins, avec_retour),
        reglages,
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
async def test_l_agent_qui_parle_puis_passe_la_main_laisse_une_note_au_specialise(
    db_session, async_session, test_client_factory
):
    """D1 (rejeu du 16/10) : le principal parle puis passe la main dans le même tour ; le
    spécialisé n'ouvre jamais sur un message de l'assistant (Mistral le refuse)."""
    from api.services.groupe.passations import NOTE_DE_PASSATION

    user, principal, specialise = await _groupe(db_session, async_session)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            _dit([*_texte("Je vous passe le service."), *_appel("passer_a_s", "p1")]),
            _vide(),
            _dit(_texte("Ici le spécialisé, que se passe-t-il ?")),
        ],
        ["j'ai une panne"],
    )
    point = _checkpoint(reponses[0])
    assert point["agent_actif"]["workflow_id"] == specialise.id, point
    assert NOTE_DE_PASSATION in str(point), point
    assert "Ici le spécialisé" in str(reponses[0])


def test_finit_par_l_assistant():
    from api.services.groupe.passations import finit_par_l_assistant

    assert finit_par_l_assistant([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
    assert not finit_par_l_assistant([{"role": "assistant", "content": "b"}, {"role": "tool", "content": "{}"}])
    assert not finit_par_l_assistant([{"role": "user", "content": "a"}, {"role": "system", "content": "s"}])


def test_la_note_de_passation_n_est_jamais_une_parole_de_l_appelant():
    """Relecture de D1 : au retour, le principal n'y voit pas l'appelant qui attend, et
    l'agent suivant ne la reçoit pas."""
    from api.services.groupe.passations import NOTE_DE_PASSATION, l_appelant_a_parle_en_dernier
    from api.services.workflow.agent_handoff_context import conversation_messages

    messages = [
        {"role": "user", "content": "j'ai une panne"},
        {"role": "assistant", "content": "Je vous passe le service."},
        {"role": "user", "content": NOTE_DE_PASSATION},
    ]
    assert not l_appelant_a_parle_en_dernier(messages)
    assert conversation_messages(messages) == messages[:2]


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
async def test_le_retour_arrive_sur_l_etape_de_retour_de_l_accueil_avec_sa_note(
    db_session, async_session, test_client_factory
):
    """Lot 2 d'orchestrateur-trois-cerveaux (D1, D2) : le graphe de l'accueil a une étape de retour ;
    le retour du spécialisé y arrive (et non sur ``p_start``), le tour d'après se joue dessus, et son
    prompt porte la note de retour écrite par le code depuis la fiche."""
    user, principal, specialise = await _groupe(db_session, async_session, avec_retour=True)
    accueil_du_tour_3 = _dit(_texte("Je vous écoute pour la facture."))
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            _dit([*_appel("passer_a_s", "p1")]),
            _vide(),
            _dit(_texte("C'est noté.")),
            _vide(),
            _dit([*_texte("Est-ce que je peux faire autre chose pour vous ?"), *_appel("retour", "r1")]),
            _vide(),  # la fabrique construit le principal ; il ne parle pas
            accueil_du_tour_3,  # tour 3 : le premier agent, reconstruit sur son étape de retour
        ],
        ["j'ai une panne", "c'est tout pour la panne", "une facture aussi"],
    )
    point = _checkpoint(reponses[1])
    assert "agent_actif" not in point, point
    assert point["current_node_id"] == "p_retour", point
    parcours = point["gathered_context"].get("parcours_etapes") or []
    assert parcours[-1].get("etape") == "reprise", parcours
    assert "Je vous écoute pour la facture." in str(reponses[2]), reponses[2]
    instruction = str(getattr(accueil_du_tour_3._settings, "system_instruction", "") or "")
    assert "# Retour du collègue « Spécialisé »" in instruction, instruction
    assert "Tu reprends la conversation." in instruction
    assert "L'appelant a une autre demande" in instruction


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
async def test_au_retour_le_principal_ne_recoit_que_la_derniere_etape_du_specialise(
    db_session, async_session, test_client_factory
):
    """Après le banc du 16/10 (décision d'Evan) : au retour, le principal ne relit plus toute
    la conversation (il y recopiait des questions périmées), seulement les échanges de la
    dernière étape du spécialisé, en entier ; la fiche porte le reste."""
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
            _vide(),
            _dit(
                [
                    *_texte("Est-ce que je peux faire autre chose pour vous ?"),
                    *_appel("retour", "r1"),
                ]
            ),
            _vide(),
            _dit(_texte("Je vous écoute pour la facture.")),
        ],
        ["j'ai une panne", "c'est tout pour la panne", "une facture aussi"],
    )
    textes = [
        str(m.get("content"))
        for m in _checkpoint(reponses[2])["messages"]
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]
    assert not any("j'ai une panne" in t for t in textes), textes
    assert any("autre chose pour vous" in t for t in textes), textes
    assert any("c'est tout pour la panne" in t for t in textes), textes
    assert any("une facture aussi" in t for t in textes), textes


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


@pytest.mark.asyncio
async def test_une_passation_vers_un_specialise_hors_de_la_liste_est_refusee(
    db_session, async_session, test_client_factory
):
    """Garde-fou du 16/10 : un principal dont l'outil vise un spécialisé qui n'est pas dans SA
    liste ``agents_specialises`` (le repère du banc branché sur le groupe d'un autre accueil)
    est refusé ; l'incohérence se voit, au lieu d'un retour vers un autre accueil."""
    user, principal, _ = await _groupe(
        db_session, async_session, reglages_principal={"agents_specialises": [999999]}
    )
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [_vide(), _dit([*_appel("passer_a_s", "p1")], _texte("Je continue."))],
        ["j'ai une panne"],
    )
    point = _checkpoint(reponses[0])
    assert "agent_actif" not in point, point
    refus = point["gathered_context"].get("passations") or []
    assert refus and refus[-1].get("motif") == "hors_groupe", refus


def test_hors_du_groupe_ne_concerne_qu_un_principal():
    from api.services.groupe.passations import hors_du_groupe

    assert hors_du_groupe({"agents_specialises": [1, 2]}, 3) is True
    assert hors_du_groupe({"agents_specialises": [1, "2"]}, 2) is False
    assert hors_du_groupe({"agent_principal_id": 5}, 3) is False, "un spécialisé n'a pas de liste"
    assert hors_du_groupe({}, 3) is False, "un agent seul garde le comportement d'avant"
