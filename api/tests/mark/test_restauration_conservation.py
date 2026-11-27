"""[.mark] Module Restauration, lot 2 : la conservation de 30 jours (E-10, T-15, T-23).

| Test | Ce qu'il prouve |
|---|---|
| détail effacé, récapitulatif gardé | les commandes et réservations de plus de 30 jours partent ; le récapitulatif chiffré par jour (nombre, annulées, chiffre d'affaires hors annulées, frais, remises) reste, sans donnée personnelle |
| idempotente | rejouée : rien de plus effacé, le récapitulatif ne double pas |
| journal sans copie | la purge ne laisse pas dans le journal une copie de ce qu'elle efface ; le journal des commandes anciennes part, celui du reste reste |
| fiche du client | effacée après la durée de conservation de l'établissement (12 mois par défaut, réglable) |
| un autre client | la purge d'une base ne touche jamais une autre base |
| copies d'appel de Dograh | transcription, texte et enregistrements des appels de plus de 30 jours des SEULS agents du module sont vidés ; la ligne de l'appel reste ; un autre agent, une autre organisation, un appel récent : intacts ; rejouée : rien de plus |
| de bout en bout | la tâche de nuit lit les agents du module dans la base du client, purge la base puis les copies |
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import asyncpg
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import importer_carte
from api.db.bases_clients.restauration_commande import changer_statut, enregistrer_commande
from api.db.bases_clients.restauration_purge import agents_du_module, purger
from api.services.restauration.appel_et_memoire import conservation
from api.tests.mark.test_base_client import _serveur, base_essai, base_prete  # noqa: F401
from api.tests.mark.test_conservation_appels import (  # noqa: F401  (fixtures et assistants)
    MAINTENANT,
    _relire,
    _run,
    monde,
    stockage,
)
from api.tests.mark.test_restauration_classeur_carte import CARTE, JEUDI_MIDI

PARIS = ZoneInfo("Europe/Paris")


@pytest.fixture
async def resto(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        a = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'a', 'a', 'Europe/Paris' FROM mark.entreprise RETURNING id")
        b = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'b', 'b', 'Europe/Paris' FROM mark.entreprise RETURNING id")
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            await importer_carte(c, a, CARTE, "caisse")
            yield SimpleNamespace(c=c, a=a, b=b, base=base_prete)
    finally:
        await c.close()


async def _commander(resto, quand, *, tel="+33612345678", appel="x", remises=None, annuler=False, lignes=None, mode="emporter", montant=None, etab=None):
    lignes = lignes or [{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 2}, {"code_caisse": "BOI-COCA-COLA-33-CL"}]
    montant = montant if montant is not None else 2380
    with horloge.remplacer(resto.base, quand):
        r = await enregistrer_commande(
            resto.c, etab or resto.a,
            {"mode": mode, "client": {"telephone": tel, "prenom": "Alice"}, "lignes": lignes, "appel_id": appel,
             "paiement": {"moyens": [{"moyen": "carte", "montant": montant}]}, **({"remises": remises} if remises else {})},
            "relu",
        )
        assert r.statut == "ENREGISTREE", r
        # 8b-1a (E2, ``restauration_commande.py:1007`` ; plan final § 17 l.403) : la commande de l'agent naît ``retenue`` et part à la fin de l'appel
        assert (await changer_statut(resto.c, etab or resto.a, r.faits["numero"], "retenue", "nouvelle", "agent")).statut == "OK"
        if annuler:
            assert (await changer_statut(resto.c, etab or resto.a, r.faits["numero"], "nouvelle", "annulee", "portail")).statut == "OK"
    return r.faits["numero"]


async def test_le_detail_est_efface_le_recapitulatif_chiffre_est_garde_et_la_purge_est_idempotente(resto):
    c, a = resto.c, resto.a
    await c.execute("INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, effet, etat) VALUES ($1, 'DIX', 'Dix', 'pourcentage', '{\"pourcentage\": 10}', 'active')", a)
    vieux = JEUDI_MIDI - timedelta(days=40)
    # même jour (40 jours avant) : deux ventes, une annulée ; un autre jour : une vente avec remise
    await _commander(resto, vieux, appel="1")
    await _commander(resto, vieux + timedelta(minutes=5), appel="2", annuler=True)
    await _commander(resto, vieux - timedelta(days=1), appel="3", remises=[{"ref": "DIX"}], montant=2142)
    recente = await _commander(resto, JEUDI_MIDI - timedelta(days=5), appel="4")
    await c.execute(
        "INSERT INTO mark.resto_reservation (numero, site_id, debut, duree_minutes, couverts, telephone, statut) VALUES "
        "(gen_random_uuid(), $1, $2, 60, 2, '+33611111111', 'honoree'), (gen_random_uuid(), $1, $2, 60, 4, '+33622222222', 'annulee'), "
        "(gen_random_uuid(), $1, $3, 60, 2, '+33633333333', 'confirmee')", a, vieux, JEUDI_MIDI + timedelta(days=2),
    )
    await c.execute("INSERT INTO mark.resto_message_recu (fournisseur, identifiant, site_id, recu_le) VALUES ('hubrise', 'vieux', $1, $2), ('hubrise', 'neuf', $1, $3)", a, vieux, JEUDI_MIDI)
    avant = JEUDI_MIDI - timedelta(days=30)
    bilan = await purger(c, avant)
    assert (bilan["commandes"], bilan["reservations"], bilan["messages"]) == (3, 2, 1)
    # le détail : plus de commande ancienne (ni de lignes), la récente reste ; la réservation à venir reste
    assert await c.fetchval("SELECT count(*) FROM mark.resto_commande") == 1
    assert await c.fetchval("SELECT numero::text FROM mark.resto_commande") == recente
    assert await c.fetchval("SELECT count(*) FROM mark.resto_commande_ligne") == 2  # celles de la récente seulement
    assert await c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 1
    assert await c.fetchval("SELECT identifiant FROM mark.resto_message_recu") == "neuf"
    # le récapitulatif : par jour et par mode, annulée comptée à part et hors chiffre d'affaires
    jour = vieux.astimezone(PARIS).date()
    lignes = {(r["jour"], r["mode"]): r for r in await c.fetch("SELECT * FROM mark.resto_recap_jour WHERE site_id = $1", a)}
    assert (lignes[(jour, "emporter")]["nb_commandes"], lignes[(jour, "emporter")]["nb_annulees"], lignes[(jour, "emporter")]["chiffre_affaires"]) == (2, 1, 2380)
    veille = jour - timedelta(days=1)
    assert (lignes[(veille, "emporter")]["nb_commandes"], lignes[(veille, "emporter")]["chiffre_affaires"], lignes[(veille, "emporter")]["remises"]) == (1, 2142, 238)
    assert (lignes[(jour, "reservation")]["nb_commandes"], lignes[(jour, "reservation")]["nb_annulees"]) == (2, 1)
    # aucune donnée personnelle dans le récapitulatif : que des clés et des nombres
    colonnes = {r["column_name"] for r in await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema = 'mark' AND table_name = 'resto_recap_jour'")}
    assert colonnes == {"site_id", "jour", "mode", "nb_commandes", "nb_annulees", "chiffre_affaires", "frais", "remises"}
    # idempotente : rejouée, rien de plus effacé, le récapitulatif ne double pas
    avant_recap = await c.fetch("SELECT * FROM mark.resto_recap_jour ORDER BY site_id, jour, mode")
    rejouee = await purger(c, avant)
    assert (rejouee["journal"], rejouee["clients"]) == (0, 0)
    assert (rejouee["commandes"], rejouee["reservations"], rejouee["messages"]) == (0, 0, 0)
    assert [dict(r) for r in await c.fetch("SELECT * FROM mark.resto_recap_jour ORDER BY site_id, jour, mode")] == [dict(r) for r in avant_recap]
    with pytest.raises(ValueError):
        await purger(c, avant.replace(tzinfo=None))


async def test_la_purge_ne_laisse_pas_de_copie_dans_le_journal_et_garde_celui_des_reglages(resto):
    c, a = resto.c, resto.a
    vieux = JEUDI_MIDI - timedelta(days=40)
    await _commander(resto, vieux, appel="1")
    avant_journal = await c.fetchval("SELECT count(*) FROM mark.resto_journal WHERE objet IN ('resto_commande', 'resto_client')")
    assert avant_journal >= 2  # la création est journalisée
    zone_journal = await c.fetchval("SELECT count(*) FROM mark.resto_journal WHERE objet = 'resto_produit'")
    # le journal est daté de la source d'heure de la base (la création est ancienne dans le temps réel du test : on le date)
    await c.execute("UPDATE mark.resto_journal SET le = $1", vieux)
    await purger(c, JEUDI_MIDI - timedelta(days=30))
    restes = [dict(r) for r in await c.fetch("SELECT objet, operation, le FROM mark.resto_journal WHERE objet IN ('resto_commande', 'resto_client', 'resto_reservation')")]
    assert restes == [], restes
    assert await c.fetchval("SELECT count(*) FROM mark.resto_journal WHERE operation = 'delete'") == 0  # pas de copie de ce qui part
    assert await c.fetchval("SELECT count(*) FROM mark.resto_journal WHERE objet = 'resto_produit'") == zone_journal  # le reste reste


async def test_la_fiche_du_client_part_apres_la_duree_de_son_etablissement(resto):
    c, a, b = resto.c, resto.a, resto.b
    treize_mois = JEUDI_MIDI - timedelta(days=400)
    await _commander(resto, treize_mois, tel="+33600000001", appel="a")   # 13 mois : part (12 mois par défaut)
    await _commander(resto, JEUDI_MIDI - timedelta(days=200), tel="+33600000002", appel="b")
    await c.execute("INSERT INTO mark.resto_reglage (site_id, conservation_client_mois) VALUES ($1, 24)", b)
    await c.execute("INSERT INTO mark.resto_client (site_id, telephone, derniere_commande_le, cree_le) VALUES ($1, '+33600000003', $2, $2)", b, treize_mois)  # 13 mois mais durée 24 : reste
    await c.execute("INSERT INTO mark.resto_client (site_id, telephone, cree_le) VALUES ($1, '+33600000004', $2)", a, JEUDI_MIDI - timedelta(days=500))   # jamais commandé : depuis sa création
    bilan = await purger(c, JEUDI_MIDI - timedelta(days=30))
    restants = {r["telephone"] for r in await c.fetch("SELECT telephone FROM mark.resto_client")}
    assert restants == {"+33600000002", "+33600000003"} and bilan["clients"] == 2


async def test_la_purge_d_une_base_ne_touche_jamais_une_autre_base(resto, monkeypatch):
    # une seconde base de client, avec sa propre commande ancienne
    autre = f"mark_essai_{uuid.uuid4().hex[:10]}"
    await schema.creer_base(autre)
    c2 = await schema.connecter(autre)
    try:
        await c2.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Autre')")
        site2 = await c2.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'x', 'x', 'Europe/Paris' FROM mark.entreprise RETURNING id")
        await importer_carte(c2, site2, CARTE, "caisse")
        vieux = JEUDI_MIDI - timedelta(days=40)
        with horloge.remplacer(autre, vieux):
            r = await enregistrer_commande(c2, site2, {"mode": "emporter", "client": {"telephone": "+33600000009"}, "lignes": [{"code_caisse": "BOI-COCA-COLA-33-CL"}],
                                                       "paiement": {"moyens": [{"moyen": "carte", "montant": 200}]}}, "relu")
            assert r.statut == "ENREGISTREE"
        await _commander(resto, vieux, appel="1")
        await purger(resto.c, JEUDI_MIDI - timedelta(days=30))
        assert await resto.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0
        assert await c2.fetchval("SELECT count(*) FROM mark.resto_commande") == 1  # l'autre base est intacte
        assert await c2.fetchval("SELECT count(*) FROM mark.resto_recap_jour") == 0
    finally:
        await c2.close()
        admin = await asyncpg.connect(f"{_serveur()}/postgres", timeout=5)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{autre}" WITH (FORCE)')
            for suffixe in ("portail", "salarie", "direction", "interface", "ecriture"):
                await admin.execute(f'DROP ROLE IF EXISTS "{autre}_{suffixe}"')
        finally:
            await admin.close()


# --------------------------------------------------------------------------- #
# Les copies d'appel de Dograh
# --------------------------------------------------------------------------- #


async def test_les_copies_d_appel_des_seuls_agents_du_module_sont_videes(monde, async_session, db_session, stockage):
    avant = MAINTENANT - timedelta(days=30)
    vieux = await _run(async_session, monde.agent_a, jours=40)
    recent = await _run(async_session, monde.agent_a, jours=10)
    autre_agent = await db_session.create_workflow(name="Autre agent", workflow_definition=monde.agent_a.workflow_definition, user_id=monde.user_a.id, organization_id=monde.org_a.id)
    hors_module = await _run(async_session, autre_agent, jours=40)
    autre_org = await _run(async_session, monde.agent_b, jours=40)

    # l'agent de l'autre organisation, glissé dans la liste : jamais touché (le périmètre est l'organisation)
    bilan = await conservation.purger_les_copies_du_module(monde.org_a.id, [monde.agent_a.id, monde.agent_b.id], avant, quand=MAINTENANT)
    assert bilan == {"texte": 1, "audio": 1, "echecs": 0}
    apres = await _relire(db_session, vieux.id)
    assert (apres.logs, apres.gathered_context, apres.annotations, apres.initial_context) == ({}, {}, {}, {})
    assert apres.transcript_url is None and apres.recording_url is None  # transcription et enregistrements : plus d'adresse
    assert apres.usage_info == {"duree_s": 123} and apres.cost_info == {"total": 0.42} and apres.extra["call_id"] == "CA123"
    assert set(stockage.supprimes) == {f"transcripts/{vieux.id}.txt", f"recordings/{vieux.id}.wav", f"recordings/{vieux.id}/user.wav", f"recordings/{vieux.id}/bot.wav"}
    for intact in (recent, hors_module, autre_org):
        garde = await _relire(db_session, intact.id)
        assert garde.gathered_context and garde.transcript_url and garde.logs, intact.id
    # rejouée : rien de plus
    assert await conservation.purger_les_copies_du_module(monde.org_a.id, [monde.agent_a.id], avant, quand=MAINTENANT) == {"texte": 0, "audio": 0, "echecs": 0}
    # aucun agent : rien
    assert await conservation.purger_les_copies_du_module(monde.org_a.id, [], avant, quand=MAINTENANT) == {"texte": 0, "audio": 0, "echecs": 0}


async def test_la_tache_de_nuit_lit_les_agents_du_module_et_purge_la_base_puis_les_copies(monde, async_session, db_session, stockage, base_prete):
    c = await schema.connecter(base_prete)
    proprietaire = await schema.connecter_proprietaire(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        a = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'a', 'a', 'Europe/Paris' FROM mark.entreprise RETURNING id")
        await importer_carte(c, a, CARTE, "caisse")
        assert await agents_du_module(c) == []  # le module n'est allumé nulle part : aucune copie d'appel n'est touchée
        await proprietaire.execute("INSERT INTO mark.module (code, libelle) VALUES ('restauration', 'Restauration')")
        agent = await proprietaire.fetchval("INSERT INTO mark.agent (dograh_workflow_id, nom) VALUES ($1, 'Agent') RETURNING id", monde.agent_a.id)
        await proprietaire.execute("INSERT INTO mark.module_agent (module_code, agent_id) VALUES ('restauration', $1)", agent)
        assert await agents_du_module(c) == [monde.agent_a.id]
        vieux = await _run(async_session, monde.agent_a, jours=40)
        with horloge.remplacer(base_prete, MAINTENANT - timedelta(days=40)):
            await enregistrer_commande(c, a, {"mode": "emporter", "client": {"telephone": "+33600000009"}, "lignes": [{"code_caisse": "BOI-COCA-COLA-33-CL"}],
                                              "paiement": {"moyens": [{"moyen": "carte", "montant": 200}]}}, "relu")
    finally:
        await c.close()
        await proprietaire.close()
    # sous la source d'heure fixée au moment des appels
    c = await schema.connecter(base_prete)
    try:
        with horloge.remplacer(base_prete, MAINTENANT):
            sortie = await conservation.purger_une_organisation_du_module(monde.org_a.id, base_prete)
        assert sortie["base"]["commandes"] == 1 and sortie["copies"]["texte"] == 1 and sortie["agents"] == [monde.agent_a.id]
        assert await c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0 and await c.fetchval("SELECT count(*) FROM mark.resto_recap_jour") == 1
        assert (await _relire(db_session, vieux.id)).gathered_context == {}
        with horloge.remplacer(base_prete, MAINTENANT):
            resultat = await conservation.purge_restauration_de_nuit(None, bases=[(monde.org_b.id, "mark_essai_inexistante"), (monde.org_a.id, base_prete)])
        assert resultat[monde.org_b.id]["statut"] == "echec"  # une base qui échoue n'arrête pas les autres
        assert resultat[monde.org_a.id]["statut"] == "faite" and resultat[monde.org_a.id]["base"]["commandes"] == 0
    finally:
        await c.close()


async def test_une_commande_retenue_suit_la_meme_duree_que_les_autres(resto):
    """8b-1a (E2) : une commande de l'agent ``retenue`` (sa fin d'appel jamais jouée) n'est ni purgée avant les 30 jours ni gardée au-delà."""
    c, a = resto.c, resto.a
    for quand, appel in ((JEUDI_MIDI - timedelta(days=40), "vieille"), (JEUDI_MIDI - timedelta(days=5), "recente")):
        with horloge.remplacer(resto.base, quand):
            r = await enregistrer_commande(
                c, a, {"mode": "emporter", "client": {"telephone": "+33612345678"}, "lignes": [{"code_caisse": "BOI-COCA-COLA-33-CL"}], "appel_id": appel,
                       "paiement": {"moyens": [{"moyen": "carte", "montant": 200}]}}, "relu",
            )
            assert r.statut == "ENREGISTREE", r
    assert await c.fetchval("SELECT count(*) FROM mark.resto_commande WHERE statut = 'retenue'") == 2
    assert (await purger(c, JEUDI_MIDI - timedelta(days=30)))["commandes"] == 1
    assert await c.fetchval("SELECT appel_id FROM mark.resto_commande WHERE statut = 'retenue'") == "recente"
