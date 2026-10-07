"""[.mark] Non-regression test for « direct to a person » (chantier l-agent-collegue, L2).

The questions this file answers (C7 to C10, R1):

    Through the engine's real dispatcher, does the internal action give the model the team
    as a CLOSED list (``enum`` built at pick-up)? Is a key outside it, a phone number or an
    e-mail REFUSED, nothing dialled, nothing assigned? Does a person reachable by transfer
    get the call through Dograh's own transfer handler, with HER number read from the copy
    (never from the model)? Does a person not reachable, or a transfer that fails, get the
    request passed on to her, with a sentence SAID (never a silence)? After the call, is
    the request assigned to her, does the mail go to her first, is every transfer a row of
    ``mark.transfert`` -- and is nothing written twice on a replay?

Why it exists
-------------
🔴 The model must never choose a destination: a number it invents, or a key it hears
wrong, would put a caller through to a stranger. Only the dispatcher played for real,
with a model that tries, proves the closed list holds.

⚠️ What this file does NOT prove: a real Twilio transfer (the transfer handler of
Dograh is played in its test mode, which simulates the answer), the bench.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pipecat.services.llm_service import FunctionCallParams

from api.enums import ToolCategory
from api.schemas.base_client import Equipe, Personne, Sujet
from api.services.etablissements import copie as module_copie
from api.services.integrations.connectors.catalogue import connecteur
from api.services.workflow import pipecat_engine_custom_tools as module_outils
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.tests.mark.test_connecteurs import stub_agent_runtime

JOIGNABLE = Personne(
    cle="camille", prenom="Camille", role="Accueil", telephone="+33611111111",
    mail="camille@example.org", joignable_par_transfert=True,
)
SANS_TRANSFERT = Personne(
    cle="sacha", prenom="Sacha", role="Comptabilité", telephone="+33622222222",
    mail="sacha@example.org",
)
EQUIPE = Equipe(personnes=[JOIGNABLE, SANS_TRANSFERT])
CONFIG = {"connecteur": "equipe", "action": "diriger_vers_personne"}


def _outil(config=CONFIG, nom="Diriger"):
    t = MagicMock()
    t.tool_uuid = f"uuid-{nom}"
    t.name = nom
    t.description = None
    t.category = ToolCategory.INTEGRATION.value
    t.definition = {"type": "integration", "config": config}
    return t


def _moteur(monkeypatch, contexte=None):
    engine = MagicMock()
    engine.active_agent = stub_agent_runtime(llm=MagicMock())
    engine._gathered_context = {"extracted_variables": {}}
    engine._call_context_vars = contexte if contexte is not None else {
        "equipe_cles": ["camille", "sacha"]
    }
    # The closed list is read from the stamp the CODE put on the run at pick-up (reserved key); a
    # test that only gives the list gets the stamp it would have had (no establishment served).
    if "equipe_cles" in engine._call_context_vars and "runtime_configuration" not in engine._call_context_vars:
        engine._call_context_vars = {
            **engine._call_context_vars,
            "runtime_configuration": {"equipe": {"cles": list(engine._call_context_vars["equipe_cles"]),
                                                 "etablissement": None}},
        }
    engine._workflow_run_id = 7
    engine.queue_text_message = AsyncMock()
    engine.queue_speech = AsyncMock(return_value=None)
    engine.end_call_with_reason = AsyncMock()
    engine.flush_variable_extraction = AsyncMock()
    enregistres = {}
    engine.active_agent.llm.register_function = lambda nom, fn, **kw: enregistres.__setitem__(nom, (fn, kw))
    from api.db import db_client

    monkeypatch.setattr(db_client, "get_tools_by_uuids", AsyncMock(return_value=[_outil()]))
    monkeypatch.setattr(
        db_client,
        "get_workflow_run_by_id",
        AsyncMock(return_value=SimpleNamespace(mode="textchat", initial_context={}, gathered_context={})),
    )
    mgr = CustomToolManager(engine)
    mgr.get_organization_id = AsyncMock(return_value=1)
    monkeypatch.setattr(
        module_copie,
        "lire_copie_complete",
        AsyncMock(return_value=module_copie.CopieOrganisation(equipe=EQUIPE)),
    )
    return engine, mgr, enregistres


async def _appeler(fn, arguments):
    capte = []

    async def rappel(resultat, *args, properties=None, **kwargs):
        capte.append(resultat)

    params = FunctionCallParams(
        function_name="diriger", tool_call_id="t1", arguments=arguments, llm=MagicMock(),
        pipeline_worker=MagicMock(), context=MagicMock(), result_callback=rappel,
    )
    await fn(params)
    assert len(capte) == 1, f"the model got {len(capte)} results"
    return capte[0]


def _essai(monkeypatch, decision):
    """Dograh's transfer in test mode, the tester's decision given, the number spied."""
    composes = []
    reel = module_outils.resolve_transfer_config

    async def espion(**kwargs):
        resolu = await reel(**kwargs)
        composes.append(resolu.destination)
        return resolu

    monkeypatch.setattr(module_outils, "resolve_transfer_config", espion)
    monkeypatch.setattr(module_outils, "est_un_essai", AsyncMock(return_value=True))
    monkeypatch.setattr(module_outils, "attendre_la_decision", AsyncMock(return_value=decision))
    return composes


# --------------------------------------------------------------------------- #
# 1. The catalogue and the schema the model sees (C7)
# --------------------------------------------------------------------------- #


def test_le_connecteur_equipe_est_interne_et_n_ecrit_jamais_par_le_relais():
    c = connecteur("equipe")
    assert c.interne and c.gestionnaire_interne is not None
    action = c.action("diriger_vers_personne")
    assert action.ecrit and not action.anticipable_permis
    with pytest.raises(RuntimeError):
        action.preparer({}, None)


async def test_le_modele_voit_la_liste_fermee_construite_au_decroche(monkeypatch):
    engine, mgr, enregistres = _moteur(monkeypatch)
    [fs] = await mgr.get_tool_schemas(["uuid-Diriger"])
    assert fs.properties["personne"]["enum"] == ["camille", "sacha"]
    assert fs.properties["geste"]["enum"] == ["transferer", "transmettre"]
    assert fs.required == ["personne"]
    assert "organization_id" not in fs.properties
    # No team in the call (switch off): no list, nothing the model could choose.
    engine._call_context_vars = {}
    [fs] = await mgr.get_tool_schemas(["uuid-Diriger"])
    assert "enum" not in fs.properties["personne"]
    await mgr.register_handlers(["uuid-Diriger"])
    _fn, kw = enregistres["diriger"]
    assert kw["is_node_transition"] is True and kw["timeout_secs"] >= 30 + 60


# --------------------------------------------------------------------------- #
# 2. A model that tries anything else is refused (C7)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "personne", ["+33611111111", "camille@example.org", "julien", "", "Camille"]
)
async def test_un_numero_un_mail_ou_une_cle_inconnue_sont_refuses(monkeypatch, personne):
    engine, mgr, enregistres = _moteur(monkeypatch)
    composes = _essai(monkeypatch, "accepte")
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(enregistres["diriger"][0], {"personne": personne})
    assert r["status"] == "refused" and r["keys"] == ["camille", "sacha"]
    assert composes == []
    assert "equipe_gestes" not in engine._gathered_context
    assert "equipe_assignation" not in engine._gathered_context


async def test_une_cle_de_la_liste_mais_hors_equipe_est_refusee(monkeypatch):
    """The copy changed since pick-up (the person was deactivated): refused, nothing done."""
    engine, mgr, enregistres = _moteur(monkeypatch, {"equipe_cles": ["camille", "noa"]})
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(enregistres["diriger"][0], {"personne": "noa"})
    assert r["status"] == "refused" and r["reason"] == "person_unavailable"


async def test_une_liste_ecrite_ailleurs_que_par_le_code_ne_donne_acces_a_personne(monkeypatch):
    """The context's list (a replay, the client's pre-call fetch) names « noa »: the list the code
    stamped does not, so nothing is dialled, assigned nor passed on."""
    engine, mgr, enregistres = _moteur(monkeypatch, {
        "equipe_cles": ["camille", "sacha", "noa"],
        "runtime_configuration": {"equipe": {"cles": ["camille", "sacha"], "etablissement": "creil"}},
    })
    composes = _essai(monkeypatch, "accepte")
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(enregistres["diriger"][0], {"personne": "noa"})
    assert r["status"] == "refused" and r["reason"] == "unknown_person" and r["keys"] == ["camille", "sacha"]
    assert composes == [] and "equipe_gestes" not in engine._gathered_context
    # No stamp at all (switch off): the tool reaches no one, whatever the context says.
    engine2, mgr2, enregistres2 = _moteur(monkeypatch, {"equipe_cles": ["camille"], "runtime_configuration": {}})
    await mgr2.register_handlers(["uuid-Diriger"])
    assert (await _appeler(enregistres2["diriger"][0], {"personne": "camille"}))["reason"] == "unknown_person"


async def test_une_personne_d_un_autre_etablissement_est_refusee_meme_dans_la_liste(monkeypatch):
    noa = Personne(cle="noa", prenom="Noa", telephone="+33633333333", etablissement="senlis", joignable_par_transfert=True)
    equipe = Equipe(personnes=[JOIGNABLE, noa])
    engine, mgr, enregistres = _moteur(monkeypatch, {
        "equipe_cles": ["camille", "noa"],
        "runtime_configuration": {"equipe": {"cles": ["camille", "noa"], "etablissement": "creil"}},
    })
    monkeypatch.setattr(module_copie, "lire_copie_complete",
                        AsyncMock(return_value=module_copie.CopieOrganisation(equipe=equipe)))
    composes = _essai(monkeypatch, "accepte")
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(enregistres["diriger"][0], {"personne": "noa"})
    assert r["status"] == "refused" and r["reason"] == "person_unavailable" and composes == []
    # The same person, the call served at HER establishment: reached.
    engine._call_context_vars["runtime_configuration"]["equipe"]["etablissement"] = "senlis"
    r = await _appeler(enregistres["diriger"][0], {"personne": "noa"})
    assert r["status"] == "transfer_success" and composes == ["+33633333333"]


# --------------------------------------------------------------------------- #
# 3. Transfer through Dograh's own handler, the number read from the copy (C8, C10)
# --------------------------------------------------------------------------- #


async def test_transfert_vers_la_personne_par_le_transfert_de_dograh(monkeypatch):
    engine, mgr, enregistres = _moteur(monkeypatch)
    composes = _essai(monkeypatch, "accepte")
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(enregistres["diriger"][0], {"personne": "camille", "motif": "un rendez-vous"})
    assert r["status"] == "transfer_success"
    assert composes == ["+33611111111"]  # HER number, from the copy
    engine.queue_speech.assert_awaited_with(
        "Je vous mets en relation avec Camille, ne quittez pas.", append_to_context=False
    )
    [geste] = engine._gathered_context["equipe_gestes"]
    assert geste["geste"] == "transfert" and geste["personne"] == "camille"
    assert geste["numero"] == "+33611111111" and geste["decroche"] is True
    assert isinstance(geste["duree_s"], int)
    assert "equipe_assignation" not in engine._gathered_context
    engine.end_call_with_reason.assert_awaited()


async def test_transfert_sans_reponse_la_demande_est_transmise_et_dite(monkeypatch):
    engine, mgr, enregistres = _moteur(monkeypatch)
    composes = _essai(monkeypatch, "refuse")
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(enregistres["diriger"][0], {"personne": "camille"})
    assert composes == ["+33611111111"]
    assert r["status"] == "passed_on" and r["person"] == "Camille"
    engine.queue_text_message.assert_awaited_with(
        "Je transmets votre demande à Camille, qui reviendra vers vous.", mute_user=True
    )
    transfert, transmission = engine._gathered_context["equipe_gestes"]
    assert transfert["decroche"] is False and transmission["geste"] == "transmission"
    assert engine._gathered_context["equipe_assignation"] == "camille"


async def test_r3_personne_qui_ne_decroche_pas_rappel_a_faire_chez_elle(monkeypatch):
    """R-3 (Evan, 07/10): the transfer fails, the agent takes the call back and the request
    reaches her as a call-back to make -- the caller's number from the CALL (a number the model
    sends is never taken), the object, the slot he wished."""
    engine, mgr, enregistres = _moteur(
        monkeypatch, {"equipe_cles": ["camille", "sacha"], "caller_number": "+33655555555"}
    )
    _essai(monkeypatch, "refuse")
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(
        enregistres["diriger"][0],
        {"personne": "camille", "motif": "suivi de commande", "rappel_souhaite": "demain matin",
         "numero": "+33699999999"},
    )
    assert r["status"] == "passed_on" and r["callback"] is True
    [rappel] = engine._gathered_context["planificateur_rappel"]
    assert rappel == {
        "origine": "equipe", "mode": "rappel", "personne": "camille", "prenom": "Camille",
        "numero": "+33655555555", "objet": "suivi de commande", "souhait": "demain matin",
        "raison": rappel["raison"], "le": rappel["le"],
    }
    assert rappel["raison"].startswith("transfer failed")
    _transfert, transmission = engine._gathered_context["equipe_gestes"]
    assert transmission["rappel"] is True
    assert engine._gathered_context["equipe_assignation"] == "camille"
    # Her mention says it is a call-back to make.
    from api.db.bases_clients.gestes import mentions_des_gestes

    assert [m["extrait"] for m in mentions_des_gestes(engine._gathered_context["equipe_gestes"])] == [
        "suivi de commande", "À rappeler : suivi de commande",
    ]


async def test_r3_une_simple_transmission_nest_pas_un_rappel(monkeypatch):
    """Scope of R-3: only a FAILED transfer makes a call-back; a request passed on by choice
    (or to someone not reachable by transfer) stays what it was (C8)."""
    engine, mgr, enregistres = _moteur(monkeypatch)
    _essai(monkeypatch, "accepte")
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(enregistres["diriger"][0], {"personne": "sacha"})
    assert r["status"] == "passed_on" and "callback" not in r
    assert "planificateur_rappel" not in engine._gathered_context


async def test_personne_non_joignable_transmission_sans_rien_composer(monkeypatch):
    engine, mgr, enregistres = _moteur(monkeypatch)
    composes = _essai(monkeypatch, "accepte")
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(enregistres["diriger"][0], {"personne": "sacha", "geste": "transferer"})
    assert composes == [] and r["status"] == "passed_on"
    [geste] = engine._gathered_context["equipe_gestes"]
    assert geste["raison"] == "not reachable by transfer"
    assert engine._gathered_context["equipe_assignation"] == "sacha"


async def test_transmettre_demande_jamais_de_transfert(monkeypatch):
    engine, mgr, enregistres = _moteur(monkeypatch)
    composes = _essai(monkeypatch, "accepte")
    await mgr.register_handlers(["uuid-Diriger"])
    r = await _appeler(enregistres["diriger"][0], {"personne": "camille", "geste": "transmettre"})
    assert composes == [] and r["status"] == "passed_on"


async def test_la_phrase_du_catalogue_remplace_le_texte_par_defaut(monkeypatch):
    engine, mgr, enregistres = _moteur(
        monkeypatch,
        {"equipe_cles": ["sacha"], "phrase_transmission_personne": "{{prenom}} vous rappelle aujourd'hui."},
    )
    await mgr.register_handlers(["uuid-Diriger"])
    await _appeler(enregistres["diriger"][0], {"personne": "sacha"})
    engine.queue_text_message.assert_awaited_with("Sacha vous rappelle aujourd'hui.", mute_user=True)


# --------------------------------------------------------------------------- #
# 4. After the call: assignee, mail to her first, transfers written once (C8, C10)
# --------------------------------------------------------------------------- #


def test_lenvoi_sans_geste_reste_celui_davant():
    from api.services.apres_appel.envoi import construire_envoi
    from api.schemas.apres_appel import ApresAppelAgent

    def run(contexte):
        return SimpleNamespace(
            id=1, workflow_id=1, definition_id=1, mode="twilio", call_type="inbound",
            initial_context={"caller_number": "+33612345678"}, gathered_context=contexte,
            usage_info={}, created_at=None, definition=None, workflow=None,
        )

    contexte = {"extracted_variables": {"motif": "facture"}}
    avant = construire_envoi(run(contexte), {}, ApresAppelAgent(), [])
    avec = construire_envoi(
        run({**contexte, "equipe_assignation": "sacha", "equipe_gestes": [{"geste": "transmission", "personne": "sacha"}]}),
        {}, ApresAppelAgent(), [],
    )
    assert "equipe" not in avant and "assignee" not in (avant["demande"] or {})
    assert avec["demande"]["assignee"] == "sacha" and avec["equipe"]["assignee"] == "sacha"
    # A request passed on exists even with nothing noted.
    vide = construire_envoi(run({"equipe_assignation": "sacha"}), {}, ApresAppelAgent(), [])
    assert vide["demande"]["type"] == "autre" and vide["demande"]["assignee"] == "sacha"


def test_r3_lenvoi_fait_la_demande_de_rappel_assignee():
    from api.schemas.apres_appel import ApresAppelAgent
    from api.services.apres_appel.envoi import construire_envoi

    run = SimpleNamespace(
        id=1, workflow_id=1, definition_id=1, mode="twilio", call_type="inbound",
        initial_context={"caller_number": "+33612345678"},
        gathered_context={
            "equipe_assignation": "camille",
            "planificateur_rappel": [{"origine": "equipe", "personne": "camille", "prenom": "Camille",
                                      "numero": "+33612345678", "objet": "facture", "souhait": "lundi"}],
        },
        usage_info={}, created_at=None, definition=None, workflow=None,
    )
    envoi = construire_envoi(run, {}, ApresAppelAgent(), [])
    assert envoi["demande"]["assignee"] == "camille" and envoi["demande"]["a_rappeler"] is True
    assert envoi["demande"]["resume"] == (
        "Rappel à faire : Camille n'a pas pu prendre l'appel transféré ; numéro de l'appelant : "
        "+33612345678 ; objet : facture ; créneau souhaité : « lundi »."
    )


@pytest.fixture
def _apres_appel():
    from api.tests.mark import test_apres_appel as t

    return t


async def test_apres_lappel_assignee_mail_et_transferts(
    base_v4, smtp, modele, db_session, async_session, _apres_appel
):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe
    from api.tasks.workflow_completion import process_workflow_completion

    t = _apres_appel
    org = await t._organisation(async_session, db_session)
    await t._regler(db_session, org, base_v4, smtp)
    await t._equipe(base_v4)
    connexion = await schema.connecter(base_v4)
    try:
        await ecrire_equipe(
            connexion,
            Equipe(
                personnes=[
                    Personne(cle="tech", prenom="Technicien", mail="tech@example.org"),
                    Personne(cle="accueil", prenom="Accueil", mail="accueil@example.org", destinataire_defaut=True),
                    Personne(cle="camille", prenom="Camille", mail="camille@example.org",
                             telephone="+33611111111", joignable_par_transfert=True),
                ],
                sujets=[Sujet(code="entretien", libelle="Entretien", mots_declencheurs=["entretien"], destinataires=["tech"])],
            ),
            "test",
        )
    finally:
        await connexion.close()
    run = await t._run(db_session, org)
    await db_session.update_workflow_run(
        run.id,
        gathered_context={
            **run.gathered_context,
            "equipe_assignation": "camille",
            "equipe_gestes": [
                {"geste": "transfert", "personne": "camille", "numero": "+33611111111",
                 "le": "2026-10-07T09:00:05+00:00", "decroche": False, "duree_s": 30},
                {"geste": "transmission", "personne": "camille", "motif": "entretien"},
            ],
        },
    )
    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await t._executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)

    # C8: the mail goes to the person the request was passed on to, not the subject's routing.
    assert [m["a"] for m in smtp.messages] == [["camille@example.org"]]
    connexion = await schema.connecter(base_v4)
    try:
        demande = await connexion.fetchrow(
            "SELECT p.cle FROM mark.demande d JOIN mark.personne p ON p.id = d.assignee_id"
        )
        assert demande["cle"] == "camille"
        transferts = await connexion.fetch(
            "SELECT p.cle, t.numero_compose, t.decroche, t.duree_s FROM mark.transfert t "
            "JOIN mark.personne p ON p.id = t.personne_id"
        )
        assert [dict(r) for r in transferts] == [
            {"cle": "camille", "numero_compose": "+33611111111", "decroche": False, "duree_s": 30}
        ]
        # A replay writes nothing twice, and never overwrites a human's assignment.
        from api.db.bases_clients.gestes import ecrire_gestes

        appel_id = await connexion.fetchval("SELECT id FROM mark.appel")
        demande_id = await connexion.fetchval("SELECT id FROM mark.demande")
        await connexion.execute(
            "UPDATE mark.demande SET assignee_id = (SELECT id FROM mark.personne WHERE cle = 'tech')"
        )
        envoi = (await db_session.get_workflow_run_by_id(run.id)).gathered_context
        ecrit = await ecrire_gestes(connexion, appel_id, demande_id, "camille", envoi["equipe_gestes"])
        assert ecrit == {"assignee_id": None, "transferts": 0, "mentions": 0}
        assert await connexion.fetchval("SELECT count(*) FROM mark.transfert") == 1
    finally:
        await connexion.close()


async def test_r3_apres_lappel_le_rappel_arrive_chez_la_personne(
    base_v4, smtp, modele, db_session, async_session, _apres_appel
):
    """R-3 through the real after-call: the request to call back is written assigned to her,
    its summary carries the number, the object and the slot; the mail goes to her with
    « À rappeler » in its subject; her mention says it."""
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe
    from api.tasks.workflow_completion import process_workflow_completion

    t = _apres_appel
    org = await t._organisation(async_session, db_session)
    await t._regler(db_session, org, base_v4, smtp)
    await t._equipe(base_v4)
    connexion = await schema.connecter(base_v4)
    try:
        await ecrire_equipe(
            connexion,
            Equipe(personnes=[
                Personne(cle="accueil", prenom="Accueil", mail="accueil@example.org", destinataire_defaut=True),
                Personne(cle="camille", prenom="Camille", mail="camille@example.org",
                         telephone="+33611111111", joignable_par_transfert=True),
            ]),
            "test",
        )
    finally:
        await connexion.close()
    run = await t._run(db_session, org)
    await db_session.update_workflow_run(
        run.id,
        gathered_context={
            **run.gathered_context,
            "equipe_assignation": "camille",
            "equipe_gestes": [
                {"geste": "transfert", "personne": "camille", "numero": "+33611111111",
                 "le": "2026-10-07T09:00:05+00:00", "decroche": False, "duree_s": 30, "motif": "facture"},
                {"geste": "transmission", "personne": "camille", "motif": "facture", "rappel": True},
            ],
            "planificateur_rappel": [
                {"origine": "equipe", "mode": "rappel", "personne": "camille", "prenom": "Camille",
                 "numero": "+33612345678", "objet": "facture", "souhait": "demain matin"},
            ],
        },
    )
    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await t._executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)

    [mail] = smtp.messages
    assert mail["a"] == ["camille@example.org"]
    [sujet], [texte] = smtp.sujets(), smtp.textes()
    assert sujet.startswith("À rappeler : ")
    assert "À faire : Rappel à faire : Camille" in texte
    assert "créneau souhaité : « demain matin »" in texte
    connexion = await schema.connecter(base_v4)
    try:
        demande = await connexion.fetchrow(
            "SELECT p.cle, d.resume FROM mark.demande d JOIN mark.personne p ON p.id = d.assignee_id"
        )
        assert demande["cle"] == "camille"
        assert demande["resume"].startswith("Rappel à faire : Camille n'a pas pu prendre l'appel")
        assert "+33612345678" in demande["resume"]
        mentions = await connexion.fetch(
            "SELECT m.source, m.extrait FROM mark.mention m JOIN mark.personne p ON p.id = m.personne_id "
            "WHERE p.cle = 'camille' ORDER BY m.source"
        )
        assert ("transmission", "À rappeler : facture") in [(m["source"], m["extrait"]) for m in mentions]
    finally:
        await connexion.close()


# Fixtures of the after-call's tests (a real client database, an SMTP stand-in, a model stand-in).
from api.tests.mark.test_apres_appel import base_v4, modele, smtp  # noqa: E402, F401
from api.tests.mark.test_base_client import base_essai  # noqa: E402, F401
