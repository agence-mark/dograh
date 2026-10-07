"""[.mark] Non-regression test for the after-call in the fork (chantier l-agent-travaille, L4).

The questions this file answers (A1 to A10, X2, R1, R7):

    At the end of a call, through the REAL completion job (``process_workflow_completion``),
    does an agent that switched the after-call on get its call written in the client's
    database (call, contact, request, record, turns, transcript), its summary, its mail
    on a real SMTP server, each step « ok » on the run? Does a replay write nothing twice?
    Does a step forced to fail show red, NOT block the next ones, and leave in a mail to
    the notification addresses? Does the night purge delete what it must and keep the
    human verdicts? Does an agent that switched nothing on stay untouched? Are a key of
    another organization, or a run of another organization, refused?

Why it exists
-------------
🔴 R1: an after-call that stops producing (a key renamed, a step that swallows its error)
is a request nobody calls back, and nothing on the call says so. Only a real Postgres, a
real SMTP conversation and the real completion job prove the chain.

Needs the Postgres of the tests (``DATABASE_URL``): skipped without it. The summary model
is a stand-in (``httpx.MockTransport``): no key, no request leaves the machine. The SMTP
server is a small one started by the test on the loopback.

⚠️ What this file does NOT prove: that the screen shows the section (``ui/src/components/
mark/``), and that a mail reaches a real mailbox (Q1: the sending service is not chosen).
"""

from __future__ import annotations

import asyncio
import email
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from api.db.bases_clients import apres_appel as sql
from api.db.bases_clients import connexion as schema
from api.db.bases_clients.equipe import ecrire_equipe
from api.db.models import OrganizationModel, UserModel
from api.enums import CallType, OrganizationConfigurationKey, WebhookCredentialType
from api.schemas.apres_appel import ApresAppelAgent, ReglagesSynthese
from api.schemas.base_client import Equipe, Personne, Sujet
from api.services.apres_appel import chaine, synthese
from api.services.apres_appel.envoi import choisir_sujet
from api.services.bibliotheque_cles import donnees_d_une_cle
from api.services.cles_reference import reference_de
from api.tests.mark.test_base_client import (  # noqa: F401
    _postgres_joignable,
    _serveur,
    base_essai,  # noqa: F401  (fixture)
)

# --------------------------------------------------------------------------- #
# A small SMTP server on the loopback (the real smtplib conversation)
# --------------------------------------------------------------------------- #


class ServeurSmtp:
    def __init__(self):
        self.messages: list[dict] = []
        self.serveur = None
        self.port = None
        self.refuser = False

    async def _client(self, lecteur, ecrivain):
        def dire(ligne):
            ecrivain.write((ligne + "\r\n").encode())

        dire("220 essai ESMTP")
        courant = {"de": None, "a": [], "corps": b""}
        while True:
            ligne = await lecteur.readline()
            if not ligne:
                break
            commande = ligne.decode(errors="replace").strip()
            haut = commande.upper()
            if haut.startswith(("EHLO", "HELO")):
                dire("250 essai")
            elif haut.startswith("MAIL FROM"):
                courant = {"de": commande[10:], "a": [], "corps": b""}
                dire("250 ok")
            elif haut.startswith("RCPT TO"):
                if self.refuser:
                    dire("451 essayez plus tard")
                else:
                    courant["a"].append(commande[8:].strip("<>"))
                    dire("250 ok")
            elif haut == "DATA":
                dire("354 fin par un point")
                corps = b""
                while True:
                    morceau = await lecteur.readline()
                    if morceau in (b".\r\n", b".\n"):
                        break
                    corps += morceau
                courant["corps"] = corps
                self.messages.append(dict(courant))
                dire("250 recu")
            elif haut == "QUIT":
                dire("221 au revoir")
                await ecrivain.drain()
                break
            else:
                dire("250 ok")
            await ecrivain.drain()
        ecrivain.close()

    async def demarrer(self):
        self.serveur = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self.serveur.sockets[0].getsockname()[1]

    async def arreter(self):
        self.serveur.close()
        await self.serveur.wait_closed()

    def sujets(self) -> list[str]:
        return [
            str(
                email.header.make_header(
                    email.header.decode_header(
                        email.message_from_bytes(m["corps"])["Subject"]
                    )
                )
            )
            for m in self.messages
        ]

    def textes(self) -> list[str]:
        sortie = []
        for m in self.messages:
            message = email.message_from_bytes(m["corps"], policy=email.policy.default)
            sortie.append(message.get_content())
        return sortie


@pytest.fixture
async def smtp():
    serveur = ServeurSmtp()
    await serveur.demarrer()
    try:
        yield serveur
    finally:
        await serveur.arreter()


# --------------------------------------------------------------------------- #
# The summary model, a stand-in
# --------------------------------------------------------------------------- #

SYNTHESE_FACTICE = (
    "La personne a demandé un rappel pour un entretien. L'assistant a promis un rappel."
)


class ModeleFactice:
    def __init__(self, statut=200):
        self.requetes: list[dict] = []
        self.statut = statut

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.requetes.append(
            {
                "url": str(requete.url),
                "auth": requete.headers.get("authorization"),
                "corps": json.loads(requete.content),
            }
        )
        if self.statut != 200:
            return httpx.Response(self.statut, json={"message": "refused"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": SYNTHESE_FACTICE}}],
                "usage": {"prompt_tokens": 10},
            },
        )


@pytest.fixture
def modele(monkeypatch):
    factice = ModeleFactice()
    monkeypatch.setattr(
        synthese,
        "nouveau_client",
        lambda **options: httpx.AsyncClient(
            transport=httpx.MockTransport(factice), **options
        ),
    )
    return factice


# --------------------------------------------------------------------------- #
# An organization, its agent, a finished run (in Dograh's test database)
# --------------------------------------------------------------------------- #

CLE_MISTRAL = "cle-mistral-de-test-0123456789"
SECRET_WEBHOOK = "secret-webhook-de-test-0123"


def _evenements():
    def t(secondes):
        return (
            datetime(2026, 10, 7, 9, 0, tzinfo=UTC) + timedelta(seconds=secondes)
        ).isoformat()

    return [
        {
            "type": "rtf-bot-text",
            "turn": 1,
            "timestamp": t(0),
            "payload": {"text": "Bonjour, que puis-je pour vous ?"},
        },
        {
            "type": "rtf-user-transcription",
            "turn": 1,
            "timestamp": t(3),
            "payload": {
                "text": "Je voudrais un entretien de mon appareil, vous pouvez me rappeler ?",
                "final": True,
            },
        },
        {
            "type": "rtf-bot-text",
            "turn": 2,
            "timestamp": t(6),
            "payload": {"text": "C'est noté, on vous rappelle."},
        },
    ]


async def _organisation(
    async_session, db_session, *, actif=True, modules=(), essais=False
):
    suffixe = uuid.uuid4().hex[:10]
    organisation = OrganizationModel(provider_id=f"apres-appel-org-{suffixe}")
    async_session.add(organisation)
    await async_session.flush()
    utilisateur = UserModel(
        provider_id=f"apres-appel-user-{suffixe}",
        selected_organization_id=organisation.id,
    )
    async_session.add(utilisateur)
    await async_session.flush()
    agent = await db_session.create_workflow(
        name="Agent d'essai",
        workflow_definition={"nodes": [], "edges": []},
        user_id=utilisateur.id,
        organization_id=organisation.id,
    )
    await async_session.refresh(agent, ["current_definition"])
    definition = agent.current_definition
    definition.workflow_configurations = {
        **(definition.workflow_configurations or {}),
        "apres_appel": ApresAppelAgent(
            actif=actif, modules=list(modules), essais=essais
        ).model_dump(),
    }
    await async_session.flush()
    return SimpleNamespace(
        organisation=organisation,
        utilisateur=utilisateur,
        agent=agent,
        definition=definition,
    )


async def _cle(db_session, org, fournisseur, valeur, nom):
    identifiant = await db_session.create_credential(
        organization_id=org.organisation.id,
        user_id=org.utilisateur.id,
        name=nom,
        credential_type=WebhookCredentialType.BEARER_TOKEN.value,
        credential_data=donnees_d_une_cle(fournisseur, valeur),
    )
    return reference_de(identifiant.credential_uuid)


async def _regler(
    db_session,
    org,
    nom_base,
    smtp,
    *,
    webhook_url=None,
    adresses=("alerte@example.org",),
):
    o = org.organisation.id
    await db_session.upsert_configuration(
        o, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": nom_base}
    )
    await db_session.upsert_configuration(
        o,
        OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value,
        {"adresses_notification": list(adresses)},
    )
    reglages = {
        "synthese": {
            "cle": await _cle(db_session, org, "mistral", CLE_MISTRAL, "Mistral client")
        },
        "smtp": {
            "hote": "127.0.0.1",
            "port": smtp.port,
            "securite": "aucune",
            "expediteur": "agent@example.org",
        },
    }
    if webhook_url:
        reglages["webhook"] = {
            "url": webhook_url,
            "secret": await _cle(db_session, org, "webhook", SECRET_WEBHOOK, "Webhook"),
        }
    await db_session.upsert_configuration(
        o, OrganizationConfigurationKey.APRES_APPEL.value, reglages
    )


async def _run(db_session, org, numero="+33612345678", mode="twilio"):
    """A REAL call by default (Twilio): since the 07/10 decision, a test call (browser,
    keyboard, simulated) skips the after-call unless the agent lets it through."""
    run = await db_session.create_workflow_run(
        name="essai",
        workflow_id=org.agent.id,
        mode=mode,
        user_id=org.utilisateur.id,
        call_type=CallType.INBOUND,
        organization_id=org.organisation.id,
        definition_id=org.definition.id,
        initial_context={
            "caller_number": numero,
            "runtime_configuration": {
                "llm_provider": "mistral",
                "etablissement": {"id": "site-a"},
            },
        },
        gathered_context={
            "extracted_variables": {
                "nom": "Dupont",
                "motif": "entretien de l'appareil",
                "degre_urgence": "faible",
            },
            "call_disposition": "rappel_demande",
        },
        logs={"realtime_feedback_events": _evenements()},
    )
    await db_session.update_workflow_run(
        run.id, usage_info={"call_duration_seconds": 42.4}
    )
    return run


async def _equipe(nom_base):
    connexion = await schema.connecter(nom_base)
    try:
        await connexion.execute(
            "INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise') ON CONFLICT DO NOTHING"
        )
        await connexion.execute(
            "INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'site-a', 'Site A' FROM mark.entreprise LIMIT 1"
        )
        await ecrire_equipe(
            connexion,
            Equipe(
                personnes=[
                    Personne(cle="tech", prenom="Technicien", mail="tech@example.org"),
                    Personne(
                        cle="accueil",
                        prenom="Accueil",
                        mail="accueil@example.org",
                        destinataire_defaut=True,
                    ),
                ],
                sujets=[
                    Sujet(
                        code="entretien",
                        libelle="Entretien",
                        mots_declencheurs=["entretien"],
                        destinataires=["tech"],
                    )
                ],
            ),
            "test",
        )
    finally:
        await connexion.close()


@pytest.fixture
async def base_v4(base_essai):  # noqa: F811
    await schema.creer_base(base_essai)
    return base_essai


async def _executer_tout_de_suite(file):
    """``enqueue`` of the chain, played at once (deferred jobs noted, not played)."""

    async def enqueue(nom, run_id, etapes=None, tentative=1, **options):
        file.append(
            {
                "nom": nom,
                "run_id": run_id,
                "etapes": etapes,
                "tentative": tentative,
                **options,
            }
        )
        if "_defer_by" not in options:
            await chaine.executer(run_id, etapes, tentative, enqueue=enqueue)

    return enqueue


# --------------------------------------------------------------------------- #
# 1. The client's schema: recevoir_appel, ecrire_synthese, nuit (A2, A8)
# --------------------------------------------------------------------------- #


def _envoi(run_id, numero="+33612345678", **plus):
    return {
        "dograh_run_id": run_id,
        "dograh_workflow_id": 7,
        "agent_nom": "Agent",
        "dograh_definition_id": 70 + run_id,
        "canal": "telephone",
        "numero_appelant": numero,
        "debut": datetime.now(UTC).isoformat(),
        "issue": "issue_nouvelle",
        "motif": "entretien",
        "contact": {"nom": "Dupont"},
        "demande": {"type": "entretien", "sujet": None},
        "champs": [
            {"nom": "nom", "valeur": "Dupont", "origine": "dicte"},
            {"nom": "motif", "valeur": "entretien"},
        ],
        "tours": [{"numero": 1, "locuteur": "agent", "silence_s": 0.8}],
        "verbatim": [{"tour": 1, "qui": "appelant", "texte": "bonjour"}],
        **plus,
    }


async def test_schema_004_recevoir_appel_doublon_indice_et_nuit(base_v4):
    connexion = await schema.connecter(base_v4)
    try:
        assert await schema.version_de(connexion) == schema.version_attendue() >= 4
        premier = await sql.recevoir_appel(connexion, _envoi(1))
        assert (
            premier["doublon"] is False
            and premier["demande_id"]
            and premier["contact_id"]
        )
        # A replay creates nothing (the same run).
        rejoue = await sql.recevoir_appel(connexion, _envoi(1))
        assert rejoue["doublon"] is True and rejoue["appel_id"] == premier["appel_id"]
        assert await connexion.fetchval("SELECT count(*) FROM mark.appel") == 1
        # The same number calls again: same contact, the hint of the other open request.
        second = await sql.recevoir_appel(connexion, _envoi(2))
        assert second["contact_id"] == premier["contact_id"]
        assert second["autre_demande_ouverte_id"] == premier["demande_id"]
        # The record, the turns (no text), the transcript and its expiry (6 months by default).
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.champ_appel WHERE appel_id = $1",
                premier["appel_id"],
            )
            == 2
        )
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.tour WHERE appel_id = $1",
                premier["appel_id"],
            )
            == 1
        )
        expire = await connexion.fetchval(
            "SELECT expire_le - (SELECT debut FROM mark.appel WHERE id = $1) FROM mark.verbatim WHERE appel_id = $1",
            premier["appel_id"],
        )
        assert timedelta(days=180) <= expire <= timedelta(days=184)
        # An issue unknown to the list enters it; an unknown request type becomes « autre ».
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.liste_valeur WHERE liste = 'issue_appel' AND code = 'issue_nouvelle'"
            )
            == 1
        )
        assert (
            await connexion.fetchval(
                "SELECT type FROM mark.demande WHERE id = $1", premier["demande_id"]
            )
            == "entretien"
        )
        assert (
            await sql.recevoir_appel(connexion, _envoi(3, demande={"type": "inconnu"}))
        )["demande_id"]
        assert (
            await connexion.fetchval(
                "SELECT type FROM mark.demande ORDER BY id DESC LIMIT 1"
            )
            == "autre"
        )
        # The summary on the call, and on its request when empty.
        await sql.ecrire_synthese(connexion, premier["appel_id"], "Résumé.")
        assert (
            await connexion.fetchval(
                "SELECT synthese FROM mark.appel WHERE id = $1", premier["appel_id"]
            )
            == "Résumé."
        )
        assert (
            await connexion.fetchval(
                "SELECT resume FROM mark.demande WHERE id = $1", premier["demande_id"]
            )
            == "Résumé."
        )

        # A8: a forced purge. The transcript expired, a call older than 12 months with a
        # human verdict: both go, the verdict stays (its call set to null), the proof is kept.
        vieux = await sql.recevoir_appel(
            connexion,
            _envoi(4, numero="+33698765432", debut="2024-01-01T10:00:00+00:00"),
        )
        await connexion.execute(
            "INSERT INTO mark.observation (appel_id, auteur, note) VALUES ($1, 'evan', 4)",
            vieux["appel_id"],
        )
        await connexion.execute(
            "UPDATE mark.verbatim SET expire_le = now() - interval '1 day' WHERE appel_id = $1",
            premier["appel_id"],
        )
        resultat = await sql.nuit(connexion)
        assert resultat["purge"]["verbatim"] >= 2  # the expired one and the old call's
        assert resultat["purge"]["appel"] == 1
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.appel WHERE id = $1", vieux["appel_id"]
            )
            == 0
        )
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.observation WHERE appel_id IS NULL AND auteur = 'evan'"
            )
            == 1
        )
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.verbatim WHERE appel_id = $1",
                second["appel_id"],
            )
            == 1
        )
        derniere = await sql.derniere_nuit(connexion)
        assert (
            derniere["statut"] == "faite"
            and derniere["resultat"]["purge"]["appel"] == 1
        )
    finally:
        await connexion.close()


def test_routage_par_mots_declencheurs():
    sujets = [
        {"code": "sav", "mots_declencheurs": ["panne", "fuite"]},
        {"code": "entretien", "mots_declencheurs": []},
    ]
    assert choisir_sujet(sujets, "Une FUITE d'eau")["code"] == "sav"
    assert choisir_sujet(sujets, "entretien annuel")["code"] == "entretien"
    assert choisir_sujet(sujets, "autre chose") is None
    assert choisir_sujet(sujets, None, None) is None


# --------------------------------------------------------------------------- #
# 2. The chain through the real completion job (R1)
# --------------------------------------------------------------------------- #


async def test_fin_dappel_ecrit_resume_et_envoie_le_mail(
    base_v4, smtp, modele, db_session, async_session
):
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session)
    await _regler(db_session, org, base_v4, smtp)
    await _equipe(base_v4)
    run = await _run(db_session, org)

    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)

    bloc = await db_session.lire_apres_appel(run.id)
    assert {n: e["statut"] for n, e in bloc["etapes"].items()} == {
        "ecriture": "ok",
        "synthese": "ok",
        "mail": "ok",
    }
    # The summary: the client's key, the smaller model, the generic prompt (no trade word).
    requete = modele.requetes[0]
    assert requete["auth"] == f"Bearer {CLE_MISTRAL}"
    assert requete["corps"]["model"] == "mistral-small-latest"
    assert "nom, motif, degre_urgence" in requete["corps"]["messages"][0]["content"]
    # The mail: routed by the subject « entretien » to the technician, the summary inside.
    assert [m["a"] for m in smtp.messages] == [["tech@example.org"]]
    assert "Nouvelle demande : entretien de l'appareil" in smtp.sujets()[0]
    assert SYNTHESE_FACTICE in smtp.textes()[0]

    connexion = await schema.connecter(base_v4)
    try:
        appel = await connexion.fetchrow(
            "SELECT * FROM mark.appel WHERE dograh_run_id = $1", run.id
        )
        assert appel["synthese"] == SYNTHESE_FACTICE and appel["canal"] == "telephone"
        assert appel["duree_s"] == 42 and appel["issue"] == "rappel_demande"
        assert appel["site_id"] == await connexion.fetchval(
            "SELECT id FROM mark.site WHERE cle = 'site-a'"
        )
        demande = await connexion.fetchrow(
            "SELECT * FROM mark.demande WHERE id = $1", appel["demande_id"]
        )
        assert demande["resume"] == SYNTHESE_FACTICE
        assert (
            await connexion.fetchval(
                "SELECT code FROM mark.sujet WHERE id = $1", demande["sujet_id"]
            )
            == "entretien"
        )
        assert (
            await connexion.fetchval(
                "SELECT nom FROM mark.contact WHERE id = $1", appel["contact_id"]
            )
            == "Dupont"
        )
        actions = await connexion.fetch(
            "SELECT canal, destinataire, statut FROM mark.action"
        )
        assert [tuple(a) for a in actions] == [("mail", "tech@example.org", "envoyee")]
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.verbatim WHERE appel_id = $1", appel["id"]
            )
            == 1
        )
    finally:
        await connexion.close()

    # Replayed (the safety net, a retried job): nothing written or sent twice.
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await chaine.executer(run.id, ["ecriture", "synthese", "mail"])
    assert len(smtp.messages) == 1 and len(modele.requetes) == 1


async def test_agent_eteint_rien_ne_change(
    base_v4, smtp, modele, db_session, async_session
):
    """X2: an agent that did not switch the after-call on is left alone."""
    org = await _organisation(async_session, db_session, actif=False)
    await _regler(db_session, org, base_v4, smtp)
    run = await _run(db_session, org)
    file: list[dict] = []
    assert (
        await chaine.demarrer(run.id, enqueue=await _executer_tout_de_suite(file))
        is False
    )
    assert file == [] and smtp.messages == [] and modele.requetes == []
    assert await db_session.lire_apres_appel(run.id) == {}


async def test_panne_agent_eteint_la_demande_a_rappeler_est_ecrite(
    base_v4, smtp, modele, db_session, async_session
):
    """Revue 2 (PN1): an outage run of an agent whose after-call is OFF writes its request
    « to call back », through the real ``process_workflow_completion`` → ``demarrer`` →
    ``executer`` ; nothing else runs (no summary, no mail)."""
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session, actif=False)
    await _regler(db_session, org, base_v4, smtp)
    run = await _run(db_session, org)
    await db_session.update_workflow_run(
        run.id,
        gathered_context={
            "extracted_variables": {},
            "panne": {"a_rappeler": "+33612345678", "raison": "modele_lent"},
        },
    )
    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)

    bloc = await db_session.lire_apres_appel(run.id)
    assert {n: e["statut"] for n, e in bloc["etapes"].items()} == {"ecriture": "ok"}
    assert smtp.messages == [] and modele.requetes == []
    connexion = await schema.connecter(base_v4)
    try:
        demande = await connexion.fetchrow(
            "SELECT d.priorite, d.resume FROM mark.demande d JOIN mark.appel a ON a.demande_id = d.id"
            " WHERE a.dograh_run_id = $1",
            run.id,
        )
    finally:
        await connexion.close()
    assert demande["priorite"] == 1 and "panne" in demande["resume"]


async def test_mail_dune_demande_nee_dune_panne_a_son_objet(
    base_v4, smtp, modele, db_session, async_session
):
    """Décision d'Evan du 07/10 (formulaire, point 7): the mail of a request born of an outage
    is titled « À rappeler : appel perdu par une panne », through the real chain."""
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session)
    await _regler(db_session, org, base_v4, smtp)
    await _equipe(base_v4)
    run = await _run(db_session, org)
    await db_session.update_workflow_run(
        run.id,
        gathered_context={
            "extracted_variables": {},
            "panne": {"a_rappeler": "+33612345678", "raison": "voix_lente"},
        },
    )
    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)
    assert smtp.sujets() == ["À rappeler : appel perdu par une panne"]
    assert [m["a"] for m in smtp.messages] == [["accueil@example.org"]]


@pytest.mark.parametrize("mode", ["smallwebrtc", "textchat", "simulated"])
async def test_un_essai_ne_passe_pas_par_l_apres_appel_par_defaut(
    mode, base_v4, smtp, modele, db_session, async_session
):
    """Décision d'Evan du 07/10 (point 3): a test call (browser, keyboard, simulated series)
    writes nothing at the client's and sends nothing, through the real chain; the run's
    section says why. The agent's switch lets the tests through."""
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session)
    await _regler(db_session, org, base_v4, smtp)
    await _equipe(base_v4)
    run = await _run(db_session, org, mode=mode)
    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)
    bloc = await db_session.lire_apres_appel(run.id)
    assert bloc.get("essai") is True and not bloc.get("etapes")
    assert smtp.messages == [] and modele.requetes == [] and file == []
    connexion = await schema.connecter(base_v4)
    try:
        assert await connexion.fetchval("SELECT count(*) FROM mark.appel") == 0
    finally:
        await connexion.close()


async def test_un_essai_passe_par_l_apres_appel_si_l_agent_le_permet(
    base_v4, smtp, modele, db_session, async_session
):
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session, essais=True)
    await _regler(db_session, org, base_v4, smtp)
    await _equipe(base_v4)
    run = await _run(db_session, org, mode="smallwebrtc")
    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)
    bloc = await db_session.lire_apres_appel(run.id)
    assert {e["statut"] for e in bloc["etapes"].values()} == {"ok"}
    assert len(smtp.messages) == 1


async def test_fin_dappel_rejouee_ne_refait_rien_qui_a_abouti(
    base_v4, smtp, modele, db_session, async_session
):
    """Revue 3: ``process_workflow_completion`` played twice for the same run never resets a
    step already « ok » : no second summary, no second mail, the steps keep their date."""
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session)
    await _regler(db_session, org, base_v4, smtp)
    await _equipe(base_v4)
    run = await _run(db_session, org)
    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)
    avant = await db_session.lire_apres_appel(run.id)
    assert {e["statut"] for e in avant["etapes"].values()} == {"ok"}

    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)
    apres = await db_session.lire_apres_appel(run.id)
    assert apres["etapes"] == avant["etapes"] and apres["lance_le"] == avant["lance_le"]
    assert len(smtp.messages) == 1 and len(modele.requetes) == 1


async def test_mail_envoye_puis_trace_ratee_jamais_renvoye(
    base_v4, smtp, modele, db_session, async_session, monkeypatch
):
    """Revue 4 (A10): the mail left, then writing its « action » row failed: the step is
    retried, the mail is NOT sent again ; its rows are written at the retry."""
    org = await _organisation(async_session, db_session)
    await _regler(db_session, org, base_v4, smtp)
    await _equipe(base_v4)
    run = await _run(db_session, org)
    await chaine.executer(run.id, ["ecriture", "synthese"])

    vraie = sql.noter_action
    coupee = {"fois": 0}

    async def noter_action_qui_tombe(*args, **kwargs):
        if kwargs.get("statut") == "envoyee" and coupee["fois"] == 0:
            coupee["fois"] += 1
            raise ConnectionError("database gone right after the sending")
        return await vraie(*args, **kwargs)

    monkeypatch.setattr(sql, "noter_action", noter_action_qui_tombe)
    file: list[dict] = []
    enqueue = await _executer_tout_de_suite(file)
    await chaine.executer(run.id, ["mail"], 1, enqueue=enqueue)
    assert len(smtp.messages) == 1
    assert (await db_session.lire_apres_appel(run.id))["etapes"]["mail"][
        "statut"
    ] == "echec"
    # The retry (deferred, played here by hand).
    await chaine.executer(run.id, ["mail"], 2, enqueue=enqueue)
    bloc = await db_session.lire_apres_appel(run.id)
    assert bloc["etapes"]["mail"]["statut"] == "ok"
    assert len(smtp.messages) == 1
    connexion = await schema.connecter(base_v4)
    try:
        actions = await connexion.fetch(
            "SELECT canal, destinataire, statut FROM mark.action"
        )
    finally:
        await connexion.close()
    assert [tuple(a) for a in actions] == [("mail", "tech@example.org", "envoyee")]


# --------------------------------------------------------------------------- #
# 3. A step forced to fail (A9, A10, A5)
# --------------------------------------------------------------------------- #


async def test_echec_force_rouge_sans_bloquer_puis_notifie(
    base_v4, smtp, modele, db_session, async_session
):
    org = await _organisation(async_session, db_session, modules=["webhook"])
    await _regler(
        db_session, org, base_v4, smtp, webhook_url="https://webhook.example.org/fin"
    )
    await _equipe(base_v4)
    run = await _run(db_session, org)

    recus: list[httpx.Request] = []

    def webhook(requete):
        recus.append(requete)
        return httpx.Response(500)

    file: list[dict] = []
    enqueue = await _executer_tout_de_suite(file)
    with patch(
        "api.services.apres_appel.modules.nouveau_client",
        lambda **options: httpx.AsyncClient(
            transport=httpx.MockTransport(webhook), **options
        ),
    ):
        await chaine.demarrer(run.id, enqueue=enqueue)
        bloc = await db_session.lire_apres_appel(run.id)
        etape = bloc["etapes"]["module:webhook"]
        # Failed, retried later (not final yet); the steps before it are « ok ».
        assert (
            etape["statut"] == "echec"
            and etape["definitive"] is False
            and etape["prochaine_tentative"]
        )
        assert [f["etapes"] for f in file if "_defer_by" in f] == [["module:webhook"]]
        assert {
            bloc["etapes"][n]["statut"] for n in ("ecriture", "synthese", "mail")
        } == {"ok"}
        # The secret travels in the header; the organization is not in the body.
        assert recus[0].headers["X-Mark-Secret"] == SECRET_WEBHOOK
        assert "organization" not in recus[0].content.decode().lower()
        # The 2nd and 3rd attempts (what the deferred jobs do): the 3rd is final.
        await chaine.executer(run.id, ["module:webhook"], 2, enqueue=enqueue)
        await chaine.executer(run.id, ["module:webhook"], 3, enqueue=enqueue)
    etape = (await db_session.lire_apres_appel(run.id))["etapes"]["module:webhook"]
    assert etape["statut"] == "echec" and etape["definitive"] is True
    assert etape["notifie_a"] == ["alerte@example.org"]
    assert len(recus) == 3
    alerte = [m for m, s in zip(smtp.messages, smtp.sujets()) if "échec" in s]
    assert alerte and alerte[0]["a"] == ["alerte@example.org"]
    assert SECRET_WEBHOOK not in "".join(smtp.textes())


async def test_base_detachee_ecriture_rouge_la_synthese_passe(
    base_v4, smtp, modele, db_session, async_session
):
    """A10: the write fails for good (no database), the summary still runs, the mail says why."""
    org = await _organisation(async_session, db_session)
    await _regler(db_session, org, base_v4, smtp)
    await db_session.upsert_configuration(
        org.organisation.id,
        OrganizationConfigurationKey.BASE_CLIENT.value,
        {"nom_base": None},
    )
    run = await _run(db_session, org)
    await chaine.demarrer(run.id, enqueue=await _executer_tout_de_suite([]))
    etapes = (await db_session.lire_apres_appel(run.id))["etapes"]
    assert (
        etapes["ecriture"]["statut"] == "echec"
        and etapes["ecriture"]["definitive"] is True
    )
    assert etapes["synthese"]["statut"] == "ok"
    assert etapes["mail"]["statut"] == "echec"
    assert any("échec : ecriture" in s for s in smtp.sujets())


# --------------------------------------------------------------------------- #
# 4. The summary alone, the routes and the tenant isolation
# --------------------------------------------------------------------------- #


async def test_synthese_cle_jamais_dans_une_erreur():
    factice = ModeleFactice(statut=401)
    client = httpx.AsyncClient(transport=httpx.MockTransport(factice))
    lignes = [{"speaker": "caller", "text": "bonjour"}]
    with pytest.raises(synthese.SyntheseImpossible) as erreur:
        await synthese.resumer(
            "cle-secrete-123", ReglagesSynthese(), lignes, {}, client=client
        )
    assert "cle-secrete-123" not in str(erreur.value) and "401" in str(erreur.value)
    texte = synthese.consigne(
        ReglagesSynthese(nom_assistant="Léa", nom_entreprise="Société X"), ["nom"]
    )
    assert "Léa" in texte and "Société X" in texte and "{" not in texte


def _app(user):
    from api.routes import apres_appel as route
    from api.services.auth.depends import get_user_with_selected_organization

    app = FastAPI()
    app.include_router(route.router)
    app.include_router(route.routeur_run)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: user
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://essai"
    )


async def test_routes_cloisonnees(base_v4, smtp, modele, db_session, async_session):
    a = await _organisation(async_session, db_session)
    b = await _organisation(async_session, db_session)
    await _regler(db_session, a, base_v4, smtp)
    await _equipe(base_v4)
    cle_de_b = await _cle(db_session, b, "mistral", "cle-de-b-0123456789", "Mistral B")
    run = await _run(db_session, a)
    await chaine.demarrer(run.id, enqueue=await _executer_tout_de_suite([]))

    client_a, client_b = _app(a.utilisateur), _app(b.utilisateur)
    # A key of another organization is refused at save.
    reponse = await client_a.put(
        "/organizations/apres-appel", json={"synthese": {"cle": cle_de_b}}
    )
    assert reponse.status_code == 422 and "deleted" in reponse.json()["detail"]
    # A password typed instead of a key is refused.
    assert (
        await client_a.put(
            "/organizations/apres-appel", json={"smtp": {"mot_de_passe": "en-clair"}}
        )
    ).status_code == 422
    # The run's section: read by its organization only.
    chemin = f"/workflow/{a.agent.id}/runs/{run.id}/apres-appel"
    vue = (await client_a.get(chemin)).json()
    assert vue["actif"] is True and [e["nom"] for e in vue["etapes"]] == [
        "ecriture",
        "synthese",
        "mail",
    ]
    assert vue["synthese"] == SYNTHESE_FACTICE
    assert (await client_b.get(chemin)).status_code == 404
    # « Retry » only on a failed or skipped step.
    assert (await client_a.post(f"{chemin}/mail/relancer")).status_code == 409
    # The screen reads the settings back, never a key's value.
    ecran = (await client_a.get("/organizations/apres-appel")).json()
    assert ecran["base_rattachee"] is True and CLE_MISTRAL not in json.dumps(ecran)
    # Forced purge from the screen.
    assert (await client_a.post("/organizations/apres-appel/nuit")).json()[
        "statut"
    ] == "faite"
    assert (await client_b.post("/organizations/apres-appel/nuit")).status_code == 422


async def test_reglage_agent_verifie_a_lenregistrement():
    from api.routes.workflow import UpdateWorkflowRequest

    with pytest.raises(Exception, match="Unknown module"):
        UpdateWorkflowRequest(
            workflow_configurations={
                "apres_appel": {"actif": True, "modules": ["inconnu"]}
            }
        )
    ok = UpdateWorkflowRequest(
        workflow_configurations={
            "apres_appel": {"actif": True, "champs": {"nom": "nom_client"}}
        }
    )
    assert ok.workflow_configurations.apres_appel["champs"] == {"nom": "nom_client"}
    # At call time, an unreadable setting is « off », never an error (X2).
    from api.services.apres_appel.reglages import reglages_de_lagent

    assert reglages_de_lagent({"apres_appel": {"modules": ["inconnu"]}}).actif is False
    assert reglages_de_lagent(None).actif is False


async def test_postgres_des_tests_joignable_sinon_saute():
    """The file's tests that need Postgres skip without it; this one says which case ran."""
    if not await _postgres_joignable():
        pytest.skip("No Postgres for the tests")
    connexion = await asyncpg.connect(f"{_serveur()}/postgres", timeout=3)
    await connexion.close()


async def test_une_base_en_version_3_se_met_a_niveau_en_4(base_essai):  # noqa: F811
    """« Upgrade » on screen: a database made before L4 (version 3) receives 004 and the ones after it (005 since L7, 006 and 007 since the 07/10 decisions)."""
    maintenance = await asyncpg.connect(f"{_serveur()}/postgres", timeout=5)
    try:
        await maintenance.execute(f'CREATE DATABASE "{base_essai}"')
    finally:
        await maintenance.close()
    connexion = await schema.connecter_proprietaire(
        base_essai
    )  # « Upgrade » = the owner
    try:
        for migration in schema.migrations()[:3]:
            sql_brut = migration.sql.replace("\nBEGIN;\n", "\n").replace(
                "\nCOMMIT;\n", "\n"
            )
            async with connexion.transaction():
                await connexion.execute(sql_brut)
        assert await schema.version_de(connexion) == 3
        assert await schema.appliquer_migrations(connexion) == [4, 5, 6, 7]
        assert await connexion.fetchval(
            "SELECT to_regprocedure('mark.recevoir_appel(jsonb)') IS NOT NULL"
        )
        jours = await connexion.fetchval(
            "SELECT extract(epoch FROM duree) / 86400 FROM mark.politique_conservation WHERE table_nom = 'verbatim'"
        )
        assert 180 <= jours <= 184
    finally:
        await connexion.close()
