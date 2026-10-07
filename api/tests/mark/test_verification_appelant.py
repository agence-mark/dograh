"""[.mark] Non-regression test of the caller's verification and of the record (chantier l-agent-collegue, L6).

The questions this file answers (V1 to V7, R1):

    Through the engine's REAL dispatcher, a real client database and the real Redis: without a
    verification the code made, does « read the record » return NOTHING? Does a model that
    claims the caller is verified change anything? Does the number calling, the control
    question and the SMS code each count once, the level by kind of data hold, only the fields
    declared readable come back? Two failed attempts: blocked, a call-back noted and SAID?
    Is no answer, no code, kept anywhere (record, Redis, client database)? Are two callers of
    one organization, and two organizations, kept apart? After the call, is each attempt a row
    of ``mark.verification``, once? Does a software that holds the records come in as a
    translator, without touching the hub?

⚠️ What this file does NOT prove: a real SMS (V5: never configured nor tried, stand-ins only),
the bench at the browser.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pipecat.services.llm_service import FunctionCallParams

from api.enums import OrganizationConfigurationKey, ToolCategory
from api.schemas.verification import NiveauLecture, ReglagesVerification
from api.services.integrations.connectors import nango
from api.services.integrations.connectors.catalogue import connecteur
from api.services.verification import etat as etats
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.tests.mark.test_connecteurs import FauxNango, stub_agent_runtime

DUPONT = "+33612345678"
MARTIN = "+33698765432"
# One factor switched on cannot satisfy the default level (2): the settings are refused, so a test
# that switches the number off asks for the level it can reach.
UN_FACTEUR = {"demandes": NiveauLecture(facteurs_requis=1, champs=["statut"])}


def test_les_deux_actions_sont_internes_et_jamais_anticipees():
    c = connecteur("dossier")
    assert c.interne and c.executer_interne is not None and c.gestionnaire_interne is None
    verifier, lire = c.action("verifier_appelant"), c.action("lire_dossier")
    assert not verifier.anticipable_permis and not lire.anticipable_permis
    noms = {p.nom for p in verifier.parametres}
    # No parameter says who is verified; the organization never travels (D6).
    assert noms == {"reference", "nom", "code_postal", "commune", "mail", "envoyer_code", "code"}
    assert [p.nom for p in lire.parametres] == ["quoi"]


# --------------------------------------------------------------------------- #
# The installation: a client database with two records, the agent's switch on
# --------------------------------------------------------------------------- #


async def _dossiers(nom_base) -> dict:
    from api.db.bases_clients import connexion as schema

    connexion = await schema.connecter(nom_base)
    try:
        ids = {}
        for cle, (nom, numero, cp, commune) in {
            "dupont": ("Dupont", DUPONT, "60100", "Creil"),
            "martin": ("Martin", MARTIN, "75011", "Paris"),
        }.items():
            contact = await connexion.fetchval(
                "INSERT INTO mark.contact (nom, prenom) VALUES ($1, 'Alex') RETURNING id", nom)
            await connexion.execute("INSERT INTO mark.telephone (numero, contact_id) VALUES ($1, $2)", numero, contact)
            await connexion.execute(
                "INSERT INTO mark.adresse (contact_id, code_postal, commune) VALUES ($1, $2, $3)", contact, cp, commune)
            demande = await connexion.fetchval(
                "INSERT INTO mark.demande (contact_id, type, resume) VALUES ($1, 'sav', $2) RETURNING id",
                contact, f"Résumé interne {nom}")
            await connexion.execute(
                "INSERT INTO mark.rendez_vous (demande_id, debut, fin, origine) "
                "VALUES ($1, now() + interval '2 days', now() + interval '2 days 1 hour', 'humain')", demande)
            ids[cle] = (contact, demande)
        return ids
    finally:
        await connexion.close()


@pytest.fixture
async def installe(base_v4, smtp, modele, db_session, async_session, monkeypatch):
    from api.tests.mark import test_apres_appel as t

    org = await t._organisation(async_session, db_session)
    org.definition.workflow_configurations = {**org.definition.workflow_configurations, "verification_appelant": True}
    await async_session.flush()
    await t._regler(db_session, org, base_v4, smtp)
    await t._equipe(base_v4)
    ids = await _dossiers(base_v4)
    run = await t._run(db_session, org, numero=DUPONT)
    return SimpleNamespace(org=org, base=base_v4, run=run, t=t, ids=ids, db=db_session, session=async_session)


async def _regler(installe, **reglages) -> None:
    await installe.db.upsert_configuration(
        installe.org.organisation.id, OrganizationConfigurationKey.VERIFICATION_APPELANT.value,
        ReglagesVerification(**reglages).model_dump(mode="json"))


def _outil(action, nom, delai_ms=5000):
    t = MagicMock()
    t.tool_uuid = f"uuid-{nom}"
    t.name = nom
    t.description = None
    t.category = ToolCategory.INTEGRATION.value
    t.definition = {"type": "integration", "config": {"connecteur": "dossier", "action": action, "delai_ms": delai_ms}}
    return t


def _moteur(installe, monkeypatch, numero=DUPONT, run_id=None, organisation=None, contexte=None, delai_ms=5000):
    engine = MagicMock()
    engine.active_agent = stub_agent_runtime(llm=MagicMock())
    engine._gathered_context = {"extracted_variables": {"motif": "où en est ma demande"}}
    engine._call_context_vars = {"caller_number": numero, **(contexte or {})}
    engine._workflow_run_id = run_id or installe.run.id
    engine.queue_text_message = AsyncMock()
    enregistres = {}
    engine.active_agent.llm.register_function = lambda nom, fn, **kw: enregistres.__setitem__(nom, (fn, kw))
    from api.db import db_client

    monkeypatch.setattr(db_client, "get_tools_by_uuids", AsyncMock(
        return_value=[_outil("verifier_appelant", "Verifier", delai_ms), _outil("lire_dossier", "Lire", delai_ms)]))
    mgr = CustomToolManager(engine)
    mgr.get_organization_id = AsyncMock(return_value=organisation or installe.org.organisation.id)
    return engine, mgr, enregistres


async def _pret(installe, monkeypatch, **kw):
    engine, mgr, enregistres = _moteur(installe, monkeypatch, **kw)
    await mgr.register_handlers(["uuid-Verifier", "uuid-Lire"])
    return engine, enregistres["verifier"][0], enregistres["lire"][0]


async def _appeler(fn, arguments):
    capte = []

    async def rappel(resultat, *args, properties=None, **kwargs):
        capte.append(resultat)

    await fn(FunctionCallParams(function_name="x", tool_call_id="t1", arguments=arguments, llm=MagicMock(),
                                pipeline_worker=MagicMock(), context=MagicMock(), result_callback=rappel))
    assert len(capte) == 1
    return capte[0]


SANS_DONNEES = {"status", "reason", "instruction"}


# --------------------------------------------------------------------------- #
# 1. Nothing without the code's verification (V1)
# --------------------------------------------------------------------------- #


async def test_sans_verification_lire_dossier_ne_rend_rien(installe, monkeypatch):
    await _regler(installe)
    engine, _verifier, lire = await _pret(installe, monkeypatch)
    for quoi in ("demandes", "rendez_vous"):
        r = await _appeler(lire, {"quoi": quoi})
        assert r["status"] == "refused" and set(r) <= SANS_DONNEES
    assert "dossier_lu" not in engine._gathered_context


async def test_un_modele_qui_pretend_l_appelant_verifie_ne_change_rien(installe, monkeypatch):
    await _regler(installe)
    engine, verifier, lire = await _pret(installe, monkeypatch)
    # Undeclared parameters are dropped; the extraction writing a look-alike key in the record
    # changes nothing either: the state lives in Redis, under this organization and this run.
    engine._gathered_context["verification_appelant"] = [{"resultat": "verifie", "facteurs_reussis": ["numero", "question", "code_sms"]}]
    engine._gathered_context["verifie"] = True
    r = await _appeler(lire, {"quoi": "demandes", "verifie": True, "niveau": 3, "organization_id": 999})
    assert r["status"] == "refused" and set(r) <= SANS_DONNEES
    r = await _appeler(verifier, {"verifie": True, "facteurs": "numero,question"})
    assert r["status"] == "verified" or r["status"] == "not_verified"
    assert "question" not in (await etats.charger(installe.org.organisation.id, installe.run.id)).reussis


async def test_interrupteur_eteint_rien_ne_tourne(installe, monkeypatch):
    await _regler(installe, lisibles={"demandes": NiveauLecture(facteurs_requis=1, champs=["statut"])})
    installe.org.definition.workflow_configurations = {
        **installe.org.definition.workflow_configurations, "verification_appelant": False}
    await installe.session.flush()
    _engine, verifier, lire = await _pret(installe, monkeypatch)
    assert (await _appeler(verifier, {}))["status"] == "unavailable"
    assert (await _appeler(lire, {"quoi": "demandes"}))["status"] == "refused"


# --------------------------------------------------------------------------- #
# 2. The factors and the levels (V2)
# --------------------------------------------------------------------------- #


async def test_le_numero_seul_suffit_au_niveau_un_et_seuls_les_champs_lisibles_reviennent(installe, monkeypatch):
    await _regler(installe, lisibles={
        "demandes": NiveauLecture(facteurs_requis=1, champs=["reference", "statut"]),
        "rendez_vous": NiveauLecture(facteurs_requis=2, champs=["debut"]),
    })
    engine, verifier, lire = await _pret(installe, monkeypatch)
    r = await _appeler(verifier, {})
    assert r["status"] == "verified" and r["readable"] == ["demandes"]
    lu = await _appeler(lire, {"quoi": "demandes"})
    _contact, demande = installe.ids["dupont"]
    assert lu["elements"] == [{"reference": str(demande), "statut": "À traiter"}]  # never the summary
    assert "Résumé interne" not in json.dumps(lu, ensure_ascii=False)
    assert (await _appeler(lire, {"quoi": "rendez_vous"}))["status"] == "refused"
    [trace] = engine._gathered_context["verification_appelant"]
    assert trace["facteurs_essayes"] == ["numero"] and trace["resultat"] == "verifie"
    assert engine._gathered_context["dossier_lu"][0] == {**engine._gathered_context["dossier_lu"][0],
                                                          "quoi": "demandes", "nombre": 1}


async def test_niveau_deux_par_la_question_nom_au_son_et_code_postal(installe, monkeypatch):
    await _regler(installe)  # defaults: number + question, level 2
    _engine, verifier, lire = await _pret(installe, monkeypatch)
    r = await _appeler(verifier, {})
    assert r["status"] == "not_verified" and r["ask_for"] == ["nom", "code_postal"]
    # Only part of the answers: asked for the rest, not an attempt.
    r = await _appeler(verifier, {"nom": "Dupond"})
    assert r["status"] == "ask" and r["ask_for"] == ["code_postal"]
    r = await _appeler(verifier, {"nom": "Dupond", "code_postal": "60 100"})
    assert r["status"] == "verified" and set(r["readable"]) == {"demandes", "rendez_vous"}
    lu = await _appeler(lire, {"quoi": "rendez_vous"})
    assert lu["status"] == "ok" and set(lu["elements"][0]) == {"debut", "libelle", "statut"}


async def test_deux_echecs_bloquent_le_rappel_est_dit_et_note(installe, monkeypatch):
    await _regler(installe, numero=False, lisibles=UN_FACTEUR)
    engine, verifier, lire = await _pret(installe, monkeypatch, contexte={"phrase_verification_rappel": "Un collègue vous rappelle."})
    r = await _appeler(verifier, {"nom": "Durand", "code_postal": "60100"})
    assert r["status"] == "not_verified" and r["attempts_left"] == 1
    r = await _appeler(verifier, {"nom": "Dupont", "code_postal": "60200"})
    assert r["status"] == "blocked" and r["said_to_caller"] == "Un collègue vous rappelle."
    engine.queue_text_message.assert_awaited_with("Un collègue vous rappelle.", mute_user=True)
    [rappel] = engine._gathered_context["planificateur_rappel"]
    assert rappel["origine"] == "verification" and rappel["numero"] == DUPONT
    # Even the right answers now: blocked for the rest of the call, nothing read.
    assert (await _appeler(verifier, {"nom": "Dupont", "code_postal": "60100"}))["status"] == "blocked"
    assert (await _appeler(lire, {"quoi": "demandes"}))["status"] == "refused"
    # No answer kept: neither in the record nor in Redis.
    fiche = json.dumps(engine._gathered_context, ensure_ascii=False)
    brut = await (await etats._redis()).get(etats.cle(installe.org.organisation.id, installe.run.id))
    for reponse in ("Durand", "60200", "Dupont"):
        assert reponse not in fiche.replace("où en est ma demande", "") and reponse not in brut
    assert [t["resultat"] for t in engine._gathered_context["verification_appelant"]] == ["echec", "bloque"]


async def test_un_dossier_inconnu_ne_se_devine_pas(installe, monkeypatch):
    """A number with no record: the answers fail like wrong answers, nothing tells the model
    whether a record exists."""
    await _regler(installe)
    _engine, verifier, _lire = await _pret(installe, monkeypatch, numero="+33600000000")
    r = await _appeler(verifier, {"nom": "Dupont", "code_postal": "60100"})
    assert r["status"] == "not_verified" and "dossier" not in json.dumps(r)


# --------------------------------------------------------------------------- #
# 3. Kept apart: two callers, two organizations
# --------------------------------------------------------------------------- #


async def test_deux_appelants_de_la_meme_organisation_restent_separes(installe, monkeypatch):
    await _regler(installe)
    _e, verifier, lire = await _pret(installe, monkeypatch)
    assert (await _appeler(verifier, {"nom": "Dupont", "code_postal": "60100"}))["status"] == "verified"
    # Another call, from Martin's number: nothing of Dupont's verification.
    autre = await installe.t._run(installe.db, installe.org, numero=MARTIN)
    _e2, verifier2, lire2 = await _pret(installe, monkeypatch, numero=MARTIN, run_id=autre.id)
    assert (await _appeler(lire2, {"quoi": "demandes"}))["status"] == "refused"
    # Martin answering with Dupont's data is compared with HIS record: a failed attempt.
    r = await _appeler(verifier2, {"nom": "Dupont", "code_postal": "60100"})
    assert r["status"] == "not_verified" and r["attempts_left"] == 1
    # And Dupont's call still reads Dupont only.
    lu = await _appeler(lire, {"quoi": "demandes"})
    assert [e["reference"] for e in lu["elements"]] == [str(installe.ids["dupont"][1])]


async def test_une_autre_organisation_n_atteint_jamais_cet_appel(installe, monkeypatch):
    await _regler(installe)
    _e, verifier, _l = await _pret(installe, monkeypatch)
    assert (await _appeler(verifier, {"nom": "Dupont", "code_postal": "60100"}))["status"] == "verified"
    _e2, verifier2, lire2 = await _pret(installe, monkeypatch, organisation=installe.org.organisation.id + 10_000)
    assert (await _appeler(lire2, {"quoi": "demandes"}))["status"] == "refused"
    assert (await _appeler(verifier2, {}))["status"] == "unavailable"


# --------------------------------------------------------------------------- #
# 4. The SMS code (V5: stand-ins only)
# --------------------------------------------------------------------------- #


async def test_le_code_par_sms_par_doublure_jamais_garde_en_clair(installe, monkeypatch):
    from api.services.apres_appel import sms
    from api.services.telephony import factory

    envoyes = []

    async def envoyer(sid, jeton, expediteur, destinataire, texte):
        envoyes.append((destinataire, texte))
        return "SM1"

    monkeypatch.setattr(sms, "envoyer", envoyer)
    monkeypatch.setattr(factory, "get_telephony_provider_for_run", AsyncMock(return_value=SimpleNamespace(
        account_sid="AC1", auth_token="jeton", default_from_number="+33900000000")))
    await _regler(installe, numero=False, question=False, code_sms=True,
                  lisibles={"demandes": NiveauLecture(facteurs_requis=1, champs=["statut"])})
    _e, verifier, lire = await _pret(installe, monkeypatch)
    r = await _appeler(verifier, {"envoyer_code": True})
    assert r["code"] == "sent" and r["status"] == "not_verified"
    [(destinataire, texte)] = envoyes
    assert destinataire == DUPONT
    code = "".join(c for c in texte if c.isdigit())[:6]
    brut = await (await etats._redis()).get(etats.cle(installe.org.organisation.id, installe.run.id))
    assert code not in brut
    faux = "000000" if code != "000000" else "111111"
    assert (await _appeler(verifier, {"code": faux}))["attempts_left"] == 1
    r = await _appeler(verifier, {"code": " ".join(code)})
    assert r["status"] == "verified" and (await _appeler(lire, {"quoi": "demandes"}))["status"] == "ok"


# --------------------------------------------------------------------------- #
# 5. After the call: each attempt a row, once; the call-back request (V6)
# --------------------------------------------------------------------------- #


async def test_apres_lappel_les_tentatives_sont_ecrites_une_fois_sans_reponse(installe, monkeypatch):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.dossier import ecrire_verifications
    from api.tasks.workflow_completion import process_workflow_completion

    await _regler(installe, numero=False, lisibles=UN_FACTEUR)
    engine, verifier, _l = await _pret(installe, monkeypatch)
    await _appeler(verifier, {"nom": "Durand", "code_postal": "60100"})
    await _appeler(verifier, {"nom": "Durand", "code_postal": "60100"})
    await installe.db.update_workflow_run(installe.run.id, gathered_context=json.loads(json.dumps(engine._gathered_context)))
    with patch("api.tasks.arq.enqueue_job", await installe.t._executer_tout_de_suite([])):
        await process_workflow_completion(None, installe.run.id)
    connexion = await schema.connecter(installe.base)
    try:
        lignes = await connexion.fetch(
            "SELECT contact_id, source, facteurs_essayes, facteurs_reussis, resultat FROM mark.verification ORDER BY id")
        contact, _demande = installe.ids["dupont"]
        assert [dict(r) for r in lignes] == [
            {"contact_id": contact, "source": "hub", "facteurs_essayes": ["question"], "facteurs_reussis": [], "resultat": "echec"},
            {"contact_id": contact, "source": "hub", "facteurs_essayes": ["question"], "facteurs_reussis": [], "resultat": "bloque"},
        ]
        resume = await connexion.fetchval(
            "SELECT d.resume FROM mark.demande d JOIN mark.appel a ON a.demande_id = d.id WHERE a.dograh_run_id = $1",
            installe.run.id)
        assert resume.startswith("Rappel à faire : l'appelant voulait des informations sur son dossier")
        appel_id = await connexion.fetchval("SELECT id FROM mark.appel WHERE dograh_run_id = $1", installe.run.id)
        assert await ecrire_verifications(connexion, appel_id, engine._gathered_context["verification_appelant"]) == 0
        assert await connexion.fetchval("SELECT count(*) FROM mark.verification") == 2
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# 6. A software that holds the records: a translator, the hub untouched (V3)
# --------------------------------------------------------------------------- #


class Dossiers(FauxNango):
    def __init__(self, organization_id: int):
        super().__init__()
        self.connexions.append({"connection_id": "cx-dossiers", "provider_config_key": "dossiers-essai",
                                "tags": {"organization_id": str(organization_id)}})
        self.vus: list[str] = []

    async def __call__(self, requete: httpx.Request) -> httpx.Response:
        chemin = requete.url.path
        if chemin.startswith("/proxy/"):
            self.vus.append(f"{chemin}?{requete.url.query.decode()}")
            fiche = {"ref": "CLI-7", "tel": [DUPONT], "famille": "Dupont", "cp": "60100",
                     "dossiers": [{"reference": "D-1", "statut": "En cours", "resume": "privé"}]}
            return httpx.Response(200, json=[fiche] if chemin == "/proxy/clients" else fiche)
        return await super().__call__(requete)


async def test_un_logiciel_de_dossiers_par_son_traducteur_sans_toucher_au_hub(installe, monkeypatch):
    from api.services.hub.traducteurs import (
        Champ,
        ObjetTraduit,
        Operation,
        Traducteur,
        declarer_traducteur,
        retirer_traducteur,
    )
    from api.services.integrations.connectors.nango import Requete

    faux = Dossiers(installe.org.organisation.id)
    monkeypatch.setenv(nango.VARIABLE_URL, "http://nango.local")
    monkeypatch.setenv(nango.VARIABLE_CLE, "cle-secrete-nango-0123")
    monkeypatch.setattr(nango, "nouveau_client", lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(faux), **o))
    o = (Champ("id_externe", "ref"), Champ("telephones", "tel"), Champ("nom", "famille"), Champ("code_postal", "cp"),
         Champ("demandes", "dossiers"))
    declarer_traducteur(Traducteur(
        systeme="dossiers_essai", libelle="Dossiers d'essai", integration="dossiers-essai", domaine="dossier",
        base_url="http://dossiers.local",
        objets=(ObjetTraduit("dossier", o, {
            "chercher": Operation(lambda a, _o: Requete("GET", "/clients", params={"tel": a.get("telephone") or ""}),
                                  lambda r, _a, ob: [ob.depuis_logiciel(x) for x in r]),
            "lire": Operation(lambda a, _o: Requete("GET", f"/clients/{a['id_externe']}"),
                              lambda r, _a, ob: ob.depuis_logiciel(r)),
        }),),
    ))
    try:
        await _regler(installe, logiciel="dossiers_essai",
                      lisibles={"demandes": NiveauLecture(facteurs_requis=2, champs=["reference", "statut"])})
        _e, verifier, lire = await _pret(installe, monkeypatch)
        r = await _appeler(verifier, {"nom": "Dupont", "code_postal": "60100"})
        assert r["status"] == "verified"
        lu = await _appeler(lire, {"quoi": "demandes"})
        assert lu["elements"] == [{"reference": "D-1", "statut": "En cours"}]
        assert faux.vus[0] == f"/proxy/clients?tel=%2B33612345678" and faux.vus[-1].startswith("/proxy/clients/CLI-7")
    finally:
        retirer_traducteur("dossiers_essai")


# --------------------------------------------------------------------------- #
# 7. The settings: saved, refused when unreadable (G1)
# --------------------------------------------------------------------------- #


def test_les_reglages_refusent_ce_qui_ne_tient_pas():
    with pytest.raises(ValueError):
        ReglagesVerification(champs_controle=["date_de_naissance"])
    with pytest.raises(ValueError):
        ReglagesVerification(question=True, champs_controle=[])
    with pytest.raises(ValueError):
        ReglagesVerification(lisibles={"factures": NiveauLecture()})
    with pytest.raises(ValueError):
        ReglagesVerification(lisibles={"demandes": NiveauLecture(champs=["montant"])})
    # A level above the factors switched on can never be reached: refused, not silently saved.
    with pytest.raises(ValueError):
        ReglagesVerification(numero=False)  # the default level (2) with a single factor on
    with pytest.raises(ValueError):
        ReglagesVerification(lisibles={"demandes": NiveauLecture(facteurs_requis=3, champs=["statut"])})
    ReglagesVerification(numero=False, lisibles={"demandes": NiveauLecture(facteurs_requis=3, champs=[])})  # never read
    with pytest.raises(ValueError):
        ReglagesVerification(envois_max_par_numero=0)
    defaut = ReglagesVerification()
    assert defaut.facteurs_actifs() == ["numero", "question"] and not defaut.code_sms


# --------------------------------------------------------------------------- #
# 8. Revue du 07/10 : appels d'outils en parallèle, appels d'essai, état gardé avant l'envoi lent
# --------------------------------------------------------------------------- #


async def test_quatre_appels_en_parallele_comptent_deux_essais_au_plus(installe, monkeypatch):
    """Pipecat runs the tool calls of a turn in parallel: without a lock, four wrong answers are
    all read at 0 attempts and none blocks (the lock makes the check-and-write one step)."""
    import asyncio

    await _regler(installe, numero=False, lisibles=UN_FACTEUR)
    _e, verifier, lire = await _pret(installe, monkeypatch)
    faux = {"nom": "Durand", "code_postal": "60100"}
    r = await asyncio.gather(*[_appeler(verifier, faux) for _ in range(4)])
    assert sorted(x["status"] for x in r) == ["blocked", "blocked", "blocked", "not_verified"]
    etat = await etats.charger(installe.org.organisation.id, installe.run.id)
    assert etat.tentatives_echouees == 2 and etat.bloque
    assert (await _appeler(lire, {"quoi": "demandes"}))["status"] == "refused"


async def test_une_reussite_en_parallele_n_est_pas_ecrasee_par_un_echec(installe, monkeypatch):
    import asyncio

    await _regler(installe, numero=False, lisibles=UN_FACTEUR)
    _e, verifier, _lire = await _pret(installe, monkeypatch)
    # The read is slowed so that both calls read the state BEFORE either writes it back.
    charger = etats.charger

    async def charger_lent(*a, **k):
        lu = await charger(*a, **k)
        await asyncio.sleep(0.2)
        return lu

    monkeypatch.setattr(etats, "charger", charger_lent)
    bon, faux = {"nom": "Dupont", "code_postal": "60100"}, {"nom": "Durand", "code_postal": "60100"}
    await asyncio.gather(_appeler(verifier, bon), _appeler(verifier, faux))
    etat = await etats.charger(installe.org.organisation.id, installe.run.id)
    assert "question" in etat.reussis, "a success was overwritten by a parallel failure"


async def _sans_plafond() -> None:
    redis = await etats._redis()
    for cle in [c async for c in redis.scan_iter(f"{etats.PREFIXE}sms:*")]:
        await redis.delete(cle)


def _doublures_sms(monkeypatch, *, lent: bool = False):
    from api.services.apres_appel import sms
    from api.services.telephony import factory

    envoyes = []

    async def envoyer(sid, jeton, expediteur, destinataire, texte):
        envoyes.append((destinataire, texte))
        return "SM1"

    async def fournisseur(*a, **k):
        if lent:
            import asyncio

            await asyncio.sleep(3)
        return SimpleNamespace(account_sid="AC1", auth_token="jeton", default_from_number="+33900000000")

    monkeypatch.setattr(sms, "envoyer", envoyer)
    monkeypatch.setattr(factory, "get_telephony_provider_for_run", fournisseur)
    return envoyes


@pytest.mark.parametrize("mode", ["smallwebrtc", "textchat", "simulated"])
async def test_aucun_code_sms_pendant_un_essai(installe, monkeypatch, mode):
    """A test call (browser, keyboard, simulated caller) simulates the transfer: it sends no SMS."""
    await _sans_plafond()
    envoyes = _doublures_sms(monkeypatch)
    await _regler(installe, numero=False, question=False, code_sms=True, lisibles=UN_FACTEUR)
    run = await installe.t._run(installe.db, installe.org, numero=DUPONT, mode=mode)
    _e, verifier, _l = await _pret(installe, monkeypatch, run_id=run.id)
    r = await _appeler(verifier, {"envoyer_code": True})
    assert r["code"] == "not_sent" and envoyes == []
    etat = await etats.charger(installe.org.organisation.id, run.id)
    assert etat.code_envois == 0 and etat.code_empreinte is None


async def test_un_numero_ne_recoit_pas_plus_de_codes_que_le_plafond(installe, monkeypatch):
    await _sans_plafond()
    envoyes = _doublures_sms(monkeypatch)
    await _regler(installe, numero=False, question=False, code_sms=True, envois_max_par_numero=1,
                  lisibles=UN_FACTEUR)
    try:
        _e, verifier, _l = await _pret(installe, monkeypatch)
        assert (await _appeler(verifier, {"envoyer_code": True}))["code"] == "sent"
        # Another call, the same recipient: the cap is by number, not by call.
        autre = await installe.t._run(installe.db, installe.org, numero=DUPONT)
        _e2, verifier2, _l2 = await _pret(installe, monkeypatch, run_id=autre.id)
        assert (await _appeler(verifier2, {"envoyer_code": True}))["code"] == "not_sent"
        assert len(envoyes) == 1
    finally:
        await _sans_plafond()


async def test_la_tentative_ratee_n_est_pas_perdue_si_le_delai_tombe_pendant_l_envoi(installe, monkeypatch):
    """The deadline of the tool cancels the action while the telephony account is being read: the
    failed attempt of THIS call was already kept (state first, slow work after)."""
    await _sans_plafond()
    envoyes = _doublures_sms(monkeypatch, lent=True)
    await _regler(installe, numero=False, code_sms=True, lisibles=UN_FACTEUR)
    try:
        _e, verifier, _l = await _pret(installe, monkeypatch, delai_ms=700)
        await _appeler(verifier, {"nom": "Durand", "code_postal": "60100", "envoyer_code": True})
        etat = await etats.charger(installe.org.organisation.id, installe.run.id)
        assert etat.tentatives_echouees == 1 and envoyes == []
    finally:
        await _sans_plafond()


async def test_le_code_est_garde_avant_l_envoi_lent_et_retire_s_il_n_est_pas_parti(installe, monkeypatch):
    import asyncio

    from api.services.apres_appel import sms

    await _sans_plafond()
    _doublures_sms(monkeypatch)

    async def lent(*a, **k):
        await asyncio.sleep(3)

    monkeypatch.setattr(sms, "envoyer", lent)
    await _regler(installe, numero=False, question=False, code_sms=True, lisibles=UN_FACTEUR)
    try:
        _e, verifier, _l = await _pret(installe, monkeypatch, delai_ms=900)
        r = await _appeler(verifier, {"envoyer_code": True})
        assert r["code"] == "not_sent"
        etat = await etats.charger(installe.org.organisation.id, installe.run.id)
        # Counted (no endless retries), and no code kept that nobody received.
        assert etat.code_envois == 1 and etat.code_empreinte is None
    finally:
        await _sans_plafond()


# Fixtures of the after-call's tests (a real client database, an SMTP stand-in, a model stand-in).
from api.tests.mark.test_apres_appel import base_v4, modele, smtp  # noqa: E402, F401
from api.tests.mark.test_base_client import base_essai  # noqa: E402, F401
