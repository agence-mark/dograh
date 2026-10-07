"""[.mark] Non-regression test for the mentions and each employee's access (l-agent-collegue, L3).

The questions this file answers (C11, C14, C15, X2), on a REAL client database:

    Is every gesture of the code a certain mention, written once even on a replay? After a
    real after-call, with « Team known to the agent » on, are the mail's recipient and the
    names cited in the record mentions -- and with the switch off, NOTHING? Does an
    employee's login role read ITS mentions and the calls of ITS establishment, and nothing
    else: not another's mention, not another establishment's call, not the team, not the
    tables? Does a deactivated person lose her login?

Why it exists
-------------
🔴 Access rules fail open in silence: a view that forgets its filter, a role that inherits
too much, and an employee reads the whole company. Only a real login, refused or answered
by Postgres itself, proves the lock (C14).
"""

from __future__ import annotations

import uuid
from urllib.parse import urlsplit

import asyncpg
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.equipe import ecrire_equipe
from api.db.bases_clients.gestes import donner_acces, ecrire_gestes, ecrire_mentions
from api.schemas.base_client import Equipe, Personne, Sujet
from api.tests.mark.test_base_client import _serveur

MOT_DE_PASSE = "essai-salarie-" + uuid.uuid4().hex[:8]


@pytest.fixture
async def base_mentions(base_prete):
    """The base, two establishments, three people, one call on each establishment."""
    connexion = await schema.connecter(base_prete)
    try:
        await connexion.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        for cle in ("site-a", "site-b"):
            await connexion.execute(
                "INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, $1, $1 FROM mark.entreprise",
                cle,
            )
        await ecrire_equipe(
            connexion,
            Equipe(
                personnes=[
                    Personne(cle="alice", prenom="Alice", nom="Martin", etablissement="site-a",
                             mail="alice@example.org", telephone="+33611111111"),
                    Personne(cle="bruno", prenom="Bruno", nom="Petit", etablissement="site-b",
                             mail="bruno@example.org"),
                    Personne(cle="chris", prenom="Chris", nom="Roux", mail="chris@example.org"),
                ],
                sujets=[Sujet(code="facture", libelle="Facture", destinataires=["alice"])],
            ),
            "test",
        )
        await connexion.execute(
            "INSERT INTO mark.agent (dograh_workflow_id, nom) VALUES (1, 'a');"
            "INSERT INTO mark.version_agent (agent_id, dograh_definition_id) SELECT id, 1 FROM mark.agent;"
        )
        for run, site in ((101, "site-a"), (102, "site-b")):
            await connexion.execute(
                "INSERT INTO mark.appel (dograh_run_id, version_agent_id, site_id, canal, debut, motif) "
                "SELECT $1, v.id, s.id, 'telephone', now(), 'motif ' || $2 FROM mark.version_agent v, mark.site s WHERE s.cle = $2",
                run,
                site,
            )
    finally:
        await connexion.close()
    # The employees' roles are dropped with the base (``base_essai``).
    return base_prete


async def _appels(connexion) -> dict[str, int]:
    return {
        r["cle"]: r["id"]
        for r in await connexion.fetch(
            "SELECT s.cle, a.id FROM mark.appel a JOIN mark.site s ON s.id = a.site_id"
        )
    }


async def _connexion_du_salarie(nom_base, role):
    m = urlsplit(_serveur())
    hote = m.netloc.rsplit("@", 1)[-1]
    return await asyncpg.connect(f"postgresql://{role}:{MOT_DE_PASSE}@{hote}/{nom_base}", timeout=5)


# --------------------------------------------------------------------------- #
# 1. Mentions written by the code (C11)
# --------------------------------------------------------------------------- #


async def test_les_gestes_sont_des_mentions_certaines_ecrites_une_fois(base_mentions):
    connexion = await schema.connecter(base_mentions)
    try:
        appel = (await _appels(connexion))["site-a"]
        gestes = [
            {"geste": "transfert", "personne": "alice", "numero": "+33611111111", "decroche": False, "duree_s": 30},
            {"geste": "transmission", "personne": "alice", "motif": "une facture"},
        ]
        premier = await ecrire_gestes(connexion, appel, None, None, gestes)
        rejeu = await ecrire_gestes(connexion, appel, None, None, gestes)
        assert premier["mentions"] == 2 and rejeu["mentions"] == 0
        lignes = await connexion.fetch(
            "SELECT p.cle, m.source, m.certitude, m.extrait FROM mark.mention m "
            "JOIN mark.personne p ON p.id = m.personne_id ORDER BY m.source"
        )
        assert [tuple(r) for r in lignes] == [
            ("alice", "transfert", "certaine", None),
            ("alice", "transmission", "certaine", "une facture"),
        ]
        # A surer finding replaces a less sure one, never the other way round.
        await ecrire_mentions(connexion, appel, [{"cle": "bruno", "source": "nom_cite", "certitude": "a_confirmer"}])
        await ecrire_mentions(connexion, appel, [{"cle": "bruno", "source": "nom_cite", "certitude": "detectee"}])
        await ecrire_mentions(connexion, appel, [{"cle": "bruno", "source": "nom_cite", "certitude": "a_confirmer"}])
        assert await connexion.fetchval(
            "SELECT certitude FROM mark.mention m JOIN mark.personne p ON p.id = m.personne_id WHERE p.cle = 'bruno'"
        ) == "detectee"
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# 2. The lock in Postgres: one login per employee (C14), proved by real logins
# --------------------------------------------------------------------------- #


async def test_un_salarie_ne_voit_que_ses_mentions_et_les_appels_de_son_etablissement(base_mentions):
    connexion = await schema.connecter(base_mentions)
    try:
        appels = await _appels(connexion)
        await ecrire_mentions(connexion, appels["site-a"], [{"cle": "alice", "source": "transmission", "certitude": "certaine"}])
        await ecrire_mentions(connexion, appels["site-b"], [{"cle": "bruno", "source": "transfert", "certitude": "certaine"},
                                                             {"cle": "alice", "source": "nom_cite", "certitude": "detectee"}])
    finally:
        await connexion.close()
    proprietaire = await schema.connecter_proprietaire(base_mentions)
    try:
        role_alice = await donner_acces(proprietaire, "alice", MOT_DE_PASSE)
        role_chris = await donner_acces(proprietaire, "chris", MOT_DE_PASSE)
        with pytest.raises(asyncpg.RaiseError):
            await donner_acces(proprietaire, "inconnu", MOT_DE_PASSE)
        with pytest.raises(asyncpg.RaiseError):
            await donner_acces(proprietaire, "bruno", "court")
    finally:
        await proprietaire.close()

    alice = await _connexion_du_salarie(base_mentions, role_alice)
    try:
        mentions = await alice.fetch("SELECT appel_id, source FROM mark.v_mes_mentions ORDER BY source")
        # Her two mentions (one on a call of ANOTHER establishment: her name was cited there),
        # never Bruno's.
        assert sorted((r["appel_id"], r["source"]) for r in mentions) == sorted(
            [(appels["site-a"], "transmission"), (appels["site-b"], "nom_cite")]
        )
        vus = [r["id"] for r in await alice.fetch("SELECT id FROM mark.v_appels_de_mon_etablissement")]
        assert vus == [appels["site-a"]]
        # Nothing else: not the tables, not the team, not the interface's views.
        for requete in (
            "SELECT * FROM mark.mention",
            "SELECT * FROM mark.appel",
            "SELECT * FROM mark.personne",
            "SELECT * FROM mark.v_cahier_appels",
            "SELECT * FROM mark.v_a_rappeler",
            "SELECT * FROM mark.role_personne",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await alice.fetch(requete)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await alice.execute("SELECT mark.donner_acces('bruno', 'un-mot-de-passe-long', NULL)")
    finally:
        await alice.close()

    # Whole-company scope: her mentions only, no establishment's calls until one is opened.
    chris = await _connexion_du_salarie(base_mentions, role_chris)
    try:
        assert await chris.fetch("SELECT id FROM mark.v_appels_de_mon_etablissement") == []
    finally:
        await chris.close()
    proprietaire = await schema.connecter_proprietaire(base_mentions)
    try:
        await donner_acces(proprietaire, "chris", MOT_DE_PASSE, ["site-b"])
    finally:
        await proprietaire.close()
    chris = await _connexion_du_salarie(base_mentions, role_chris)
    try:
        assert [r["id"] for r in await chris.fetch("SELECT id FROM mark.v_appels_de_mon_etablissement")] == [appels["site-b"]]
    finally:
        await chris.close()


async def test_la_securite_par_ligne_de_mention_tient_meme_en_lecture_directe(base_mentions):
    """Defence in depth: a SELECT granted by mistake on the table still shows her rows only."""
    connexion = await schema.connecter(base_mentions)
    try:
        appels = await _appels(connexion)
        await ecrire_mentions(connexion, appels["site-a"], [{"cle": "alice", "source": "transmission", "certitude": "certaine"},
                                                             {"cle": "bruno", "source": "nom_cite", "certitude": "detectee"}])
    finally:
        await connexion.close()
    proprietaire = await schema.connecter_proprietaire(base_mentions)
    try:
        role = await donner_acces(proprietaire, "alice", MOT_DE_PASSE)
        await proprietaire.execute(f'GRANT SELECT ON mark.mention TO "{role}"')
    finally:
        await proprietaire.close()
    alice = await _connexion_du_salarie(base_mentions, role)
    try:
        assert await alice.fetchval("SELECT count(*) FROM mark.mention") == 1
    finally:
        await alice.close()


async def test_une_personne_desactivee_perd_sa_connexion(base_mentions):
    proprietaire = await schema.connecter_proprietaire(base_mentions)
    try:
        role = await donner_acces(proprietaire, "alice", MOT_DE_PASSE)
    finally:
        await proprietaire.close()
    (await _connexion_du_salarie(base_mentions, role)).terminate()
    # Deactivated from Dograh's screen (the usual connection, not the owner).
    connexion = await schema.connecter(base_mentions)
    try:
        await connexion.execute("UPDATE mark.personne SET actif = false WHERE cle = 'alice'")
    finally:
        await connexion.close()
    with pytest.raises(asyncpg.InvalidAuthorizationSpecificationError):
        await _connexion_du_salarie(base_mentions, role)


# --------------------------------------------------------------------------- #
# 3. Through the real after-call: recipients and names cited, only with the switch (X2)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("allume", [True, False])
async def test_apres_lappel_destinataire_et_nom_cite_seulement_interrupteur_allume(
    allume, base_v4, smtp, modele, db_session, async_session
):
    from unittest.mock import patch

    from api.tasks.workflow_completion import process_workflow_completion
    from api.tests.mark import test_apres_appel as t

    org = await t._organisation(async_session, db_session)
    if allume:
        org.definition.workflow_configurations = {**org.definition.workflow_configurations, "equipe_connue": True}
        await async_session.flush()
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
                    Personne(cle="camille", prenom="Camille", nom="Martin"),
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
            "extracted_variables": {
                **run.gathered_context["extracted_variables"],
                # The caller bears an employee's name: never a mention of her.
                "nom": "Martin",
                "precisions": "La personne a déjà parlé à Kamil la semaine dernière.",
            },
        },
    )
    with patch("api.tasks.arq.enqueue_job", await t._executer_tout_de_suite([])):
        await process_workflow_completion(None, run.id)

    connexion = await schema.connecter(base_v4)
    try:
        lignes = {
            (r["cle"], r["source"], r["certitude"])
            for r in await connexion.fetch(
                "SELECT p.cle, m.source, m.certitude FROM mark.mention m JOIN mark.personne p ON p.id = m.personne_id"
            )
        }
    finally:
        await connexion.close()
    if allume:
        assert lignes == {("tech", "destinataire", "certaine"), ("camille", "nom_cite", "a_confirmer")}
    else:
        assert lignes == set()


from api.tests.mark.test_apres_appel import base_v4, modele, smtp  # noqa: E402, F401
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: E402, F401
