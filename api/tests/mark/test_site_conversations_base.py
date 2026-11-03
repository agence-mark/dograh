"""[.mark] Builder partie 2, U10.3 / lot S3 : les conversations du site dans la base du client (migration 022).

Vraie base de test, vrais rôles. Le cloisonnement d'abord : le portail ne lit que les avis, les événements et les
lignes de ses lieux.

| Test | Ce qu'il prouve |
|---|---|
| cloisonnement | un lieu ne lit ni les avis, ni les événements, ni les indicateurs de l'autre ; sans variable, rien |
| canal site | une conversation du site arrive avec canal, page et mode ; un mode inconnu n'entre pas |
| contact par mail | sans numéro, le contact est retrouvé par son mail (minuscules, espaces) ou créé ; avec les deux, le numéro l'emporte |
| avis | un par conversation ; l'avis avant la conversation entre avec elle ; 1-2 étoiles + rappel crée une demande « rappel » |
| événements | un INSERT réveille un ``LISTEN portail`` (JSON court, sans donnée personnelle) ; la table garde l'ordre |
| indicateurs | les colonnes d'avant sont inchangées, celles par canal et avis viennent en dernier |
| suppression | l'appel effacé efface son avis ; la purge garde les événements 30 jours |
| rappel du site | une demande « rappel » sans conversation, avec ou sans lieu ; ni téléphone ni mail = refus |
"""

from __future__ import annotations

import asyncio
import json

import asyncpg
import pytest

from api.db.bases_clients import apres_appel as sql
from api.db.bases_clients import connexion as schema
from api.tests.mark.test_apres_appel import _envoi
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_base_portail import (  # noqa: F401  (fixtures)
    _connexion_du_portail,
    base_portail,
    portail,
)


def _site(run, **plus):
    """Une conversation du widget : sans numéro, canal site, un mail laissé en route."""
    base = dict(
        canal="site",
        page="/tarifs",
        mode_site="voix",
        demande=None,
        contact={"nom": "Visiteur", "mail": "  Visiteur@Exemple.FR "},
        etablissement="site-a",
    )
    return _envoi(run, numero=None, **{**base, **plus})


async def _ecrire(base, *envois):
    connexion = await schema.connecter(base)
    try:
        return [await sql.recevoir_appel(connexion, e) for e in envois]
    finally:
        await connexion.close()


async def _un(connexion, requete, *args):
    return await connexion.fetchrow(requete, *args)


# --------------------------------------------------------------------------- #
# Canal site, page, mode, contact par mail
# --------------------------------------------------------------------------- #


async def test_une_conversation_du_site_arrive_avec_canal_page_et_mode(base_portail):
    (res,) = await _ecrire(base_portail, _site(2001))
    connexion = await schema.connecter(base_portail)
    try:
        ligne = await _un(
            connexion, "SELECT canal, page, mode_site, numero_appelant FROM mark.appel WHERE id = $1", res["appel_id"]
        )
        assert dict(ligne) == {"canal": "site", "page": "/tarifs", "mode_site": "voix", "numero_appelant": None}
        # Un mode que la base ne connaît pas n'entre pas (le contrôle ne lève pas : la colonne reste vide).
        (autre,) = await _ecrire(base_portail, _site(2002, mode_site="n_importe_quoi"))
        assert await connexion.fetchval("SELECT mode_site FROM mark.appel WHERE id = $1", autre["appel_id"]) is None
    finally:
        await connexion.close()


async def test_sans_numero_le_contact_est_retrouve_par_son_mail_en_minuscules(base_portail):
    premier, second = await _ecrire(
        base_portail,
        _site(2011),
        _site(2012, contact={"nom": "Autre nom", "mail": "visiteur@exemple.fr"}),
    )
    assert premier["contact_id"] == second["contact_id"]
    connexion = await schema.connecter(base_portail)
    try:
        contact = await _un(connexion, "SELECT nom, mail FROM mark.contact WHERE id = $1", premier["contact_id"])
        assert contact["mail"] == "visiteur@exemple.fr"  # minuscules, sans espaces
        assert contact["nom"] == "Visiteur"  # ce qui était su ne s'écrase pas
        # La seconde conversation retrouve la première (même contact, appel précédent).
        precedent = await connexion.fetchval(
            "SELECT appel_precedent_id FROM mark.appel WHERE id = $1", second["appel_id"]
        )
        assert precedent == premier["appel_id"]
        # Un autre mail est un autre contact.
        (autre,) = await _ecrire(base_portail, _site(2013, contact={"mail": "quelquun@autre.fr"}))
        assert autre["contact_id"] != premier["contact_id"]
        # Ni numéro ni mail : une conversation anonyme, sans contact.
        (anonyme,) = await _ecrire(base_portail, _site(2014, contact={}))
        assert anonyme["contact_id"] is None
    finally:
        await connexion.close()


async def test_avec_un_numero_et_un_mail_le_numero_l_emporte_comme_avant(base_portail):
    (par_numero,) = await _ecrire(
        base_portail, _envoi(2021, numero="+33611112222", contact={"nom": "Par numéro"})
    )
    (les_deux,) = await _ecrire(
        base_portail,
        _site(2022, numero_appelant="+33611112222", contact={"mail": "nouveau@exemple.fr"}),
    )
    assert les_deux["contact_id"] == par_numero["contact_id"]
    connexion = await schema.connecter(base_portail)
    try:
        # Le mail manquant à la fiche s'est complété, sans créer un second contact.
        assert (
            await connexion.fetchval("SELECT mail FROM mark.contact WHERE id = $1", par_numero["contact_id"])
            == "nouveau@exemple.fr"
        )
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# L'avis
# --------------------------------------------------------------------------- #


async def test_un_avis_par_conversation_et_le_mauvais_avis_avec_rappel_cree_une_demande(base_portail):
    (res,) = await _ecrire(base_portail, _site(2031, contact={}))
    connexion = await schema.connecter(base_portail)
    try:
        avis = {
            "etoiles": 2,
            "obtenu": False,
            "raisons": ["trop long", "pas compris"],
            "commentaire": "Je voulais un humain.",
            "rappel_demande": True,
            "publication_acceptee": False,
            "contact": {"nom": "Claire", "telephone": "+33644445555", "mail": "claire@exemple.fr"},
        }
        ecrit = await sql.noter_avis(connexion, 2031, avis)
        assert ecrit == {"ecrit": True, "nouveau": True}
        # Un second avis pour la même conversation n'écrit rien.
        assert await sql.noter_avis(connexion, 2031, {**avis, "etoiles": 5}) == {"ecrit": True, "nouveau": False}
        ligne = await _un(connexion, "SELECT * FROM mark.avis WHERE appel_id = $1", res["appel_id"])
        assert ligne["etoiles"] == 2 and ligne["raisons"] == ["trop long", "pas compris"]
        assert ligne["publication_acceptee"] is False and ligne["consentement_le"] is None
        # Les coordonnées laissées sont celles du contact de la conversation (créé).
        contact_id = await connexion.fetchval("SELECT contact_id FROM mark.appel WHERE id = $1", res["appel_id"])
        assert contact_id is not None
        assert await connexion.fetchval("SELECT mail FROM mark.contact WHERE id = $1", contact_id) == "claire@exemple.fr"
        assert await connexion.fetchval("SELECT contact_id FROM mark.telephone WHERE numero = '+33644445555'") == contact_id
        # Une demande « rappel » a été créée, liée à la conversation, à rappeler.
        demande = await _un(
            connexion,
            "SELECT d.type, d.statut, d.contact_id, d.site_id FROM mark.demande d JOIN mark.appel a ON a.demande_id = d.id "
            "WHERE a.id = $1",
            res["appel_id"],
        )
        assert demande["type"] == "rappel" and demande["statut"] == "a_traiter" and demande["contact_id"] == contact_id
        assert await connexion.fetchval("SELECT count(*) FROM mark.v_a_rappeler WHERE id = (SELECT demande_id FROM mark.appel WHERE id = $1)", res["appel_id"]) == 1
        # Un bon avis, ou 3 étoiles, ne crée rien.
        await _ecrire(base_portail, _site(2032, contact={}), _site(2033, contact={}))
        avant = await connexion.fetchval("SELECT count(*) FROM mark.demande WHERE type = 'rappel'")
        await sql.noter_avis(connexion, 2032, {"etoiles": 5, "rappel_demande": True})
        await sql.noter_avis(connexion, 2033, {"etoiles": 3, "rappel_demande": True})
        assert await connexion.fetchval("SELECT count(*) FROM mark.demande WHERE type = 'rappel'") == avant
        # Une publication acceptée porte la date du consentement.
        await _ecrire(base_portail, _site(2034, contact={}))
        await sql.noter_avis(connexion, 2034, {"etoiles": 5, "publication_acceptee": True})
        assert (
            await connexion.fetchval(
                "SELECT consentement_le IS NOT NULL FROM mark.avis v JOIN mark.appel a ON a.id = v.appel_id WHERE a.dograh_run_id = 2034"
            )
            is True
        )
        # Cinq étoiles hors bornes : refusé par la base.
        await _ecrire(base_portail, _site(2035, contact={}))
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await sql.noter_avis(connexion, 2035, {"etoiles": 6})
    finally:
        await connexion.close()


async def test_un_avis_donne_avant_la_conversation_entre_avec_elle(base_portail):
    connexion = await schema.connecter(base_portail)
    try:
        # La conversation n'est pas dans la base : l'avis n'est pas écrit (et rien ne se perd, il attend sur le run).
        assert await sql.noter_avis(connexion, 2041, {"etoiles": 4}) == {"ecrit": False}
        assert await connexion.fetchval("SELECT count(*) FROM mark.avis") == 0
        await sql.recevoir_appel(connexion, _site(2041, contact={}, avis={"etoiles": 4, "obtenu": True}))
        ligne = await _un(
            connexion,
            "SELECT v.etoiles, v.obtenu FROM mark.avis v JOIN mark.appel a ON a.id = v.appel_id WHERE a.dograh_run_id = 2041",
        )
        assert dict(ligne) == {"etoiles": 4, "obtenu": True}
        # Rejouer l'envoi ne double rien.
        await sql.recevoir_appel(connexion, _site(2041, contact={}, avis={"etoiles": 1}))
        assert await connexion.fetchval("SELECT count(*) FROM mark.avis") == 1
    finally:
        await connexion.close()


async def test_l_appel_efface_efface_son_avis(base_portail):
    (res,) = await _ecrire(base_portail, _site(2051, contact={}))
    connexion = await schema.connecter(base_portail)
    try:
        await sql.noter_avis(connexion, 2051, {"etoiles": 5})
        assert await connexion.fetchval("SELECT count(*) FROM mark.avis") == 1
        await connexion.execute("DELETE FROM mark.appel WHERE id = $1", res["appel_id"])
        assert await connexion.fetchval("SELECT count(*) FROM mark.avis") == 0
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# Le cloisonnement du portail
# --------------------------------------------------------------------------- #


async def test_le_portail_ne_lit_que_les_avis_les_evenements_et_les_indicateurs_de_ses_lieux(portail):
    a, b = portail.ids["site"]["site-a"], portail.ids["site"]["site-b"]
    await _ecrire(
        portail.base,
        _site(2061, etablissement="site-a", contact={}),
        _site(2062, etablissement="site-b", contact={}, canal="site"),
    )
    connexion = await schema.connecter(portail.base)
    try:
        await sql.noter_avis(connexion, 2061, {"etoiles": 5, "commentaire": "Très bien"})
        await sql.noter_avis(connexion, 2062, {"etoiles": 1, "commentaire": "Pas bien"})
    finally:
        await connexion.close()

    c = await _connexion_du_portail(portail.base, str(a))
    try:
        avis = await c.fetch("SELECT * FROM mark.v_portail_avis")
        assert [(r["site_id"], r["etoiles"], r["page"], r["mode_site"]) for r in avis] == [(a, 5, "/tarifs", "voix")]
        assert [r["commentaire"] for r in await c.fetch("SELECT commentaire FROM mark.avis")] == ["Très bien"]
        # Les événements : seulement ceux de son lieu.
        sites_vus = {r["site_id"] for r in await c.fetch("SELECT site_id FROM mark.evenement_portail")}
        assert sites_vus == {a}
        # Les indicateurs : une conversation du site et un avis, rien de l'autre lieu.
        kpi = await c.fetch("SELECT * FROM mark.v_portail_kpi")
        assert len(kpi) == 1 and kpi[0]["site_id"] == a
        assert kpi[0]["appels_site"] == 1 and kpi[0]["avis_nombre"] == 1 and kpi[0]["avis_etoiles_total"] == 5
    finally:
        await c.close()

    # Tous les lieux voient les deux ; la variable vide ou absente, rien.
    tous = await _connexion_du_portail(portail.base, "*")
    try:
        assert {r["site_id"] for r in await tous.fetch("SELECT site_id FROM mark.v_portail_avis")} == {a, b}
    finally:
        await tous.close()
    for sites in ("", None):
        vide = await _connexion_du_portail(portail.base, sites)
        try:
            assert await vide.fetchval("SELECT count(*) FROM mark.v_portail_avis") == 0
            assert await vide.fetchval("SELECT count(*) FROM mark.avis") == 0
            assert await vide.fetchval("SELECT count(*) FROM mark.evenement_portail") == 0
        finally:
            await vide.close()


async def test_le_portail_ne_peut_ni_ecrire_un_avis_ni_un_evenement(portail):
    a = portail.ids["site"]["site-a"]
    c = await _connexion_du_portail(portail.base, str(a))
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await c.execute("INSERT INTO mark.avis (appel_id, etoiles) VALUES (1, 5)")
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await c.execute("INSERT INTO mark.evenement_portail (tbl, ligne, sorte) VALUES ('x', '1', 'x')")
    finally:
        await c.close()


async def test_les_colonnes_d_avant_de_v_portail_kpi_gardent_leur_ordre(portail):
    c = await _connexion_du_portail(portail.base, "*")
    try:
        colonnes = [
            r["attname"]
            for r in await c.fetch(
                "SELECT attname FROM pg_attribute WHERE attrelid = 'mark.v_portail_kpi'::regclass AND attnum > 0 ORDER BY attnum"
            )
        ]
    finally:
        await c.close()
    assert colonnes[:11] == [
        "site_id", "jour", "appels", "hors_horaires", "regles_seul", "transmis",
        "premiers_appels", "nouveaux_projets", "urgents", "duree_totale_s", "rendez_vous_pris",
    ]
    assert colonnes[11:] == ["appels_perdus", "appels_site", "appels_telephone", "avis_nombre", "avis_etoiles_total"]


# --------------------------------------------------------------------------- #
# Les événements du portail
# --------------------------------------------------------------------------- #


async def test_un_insert_reveille_le_portail_sans_donnee_personnelle(base_portail):
    recus: list[dict] = []
    ecoute = await schema.ecouter(
        base_portail, "portail", lambda _c, _p, _canal, charge: recus.append(json.loads(charge))
    )
    try:
        (res,) = await _ecrire(
            base_portail,
            _site(2071, demande={"type": "devis"}, contact={"nom": "Secret", "mail": "secret@exemple.fr"}, degre_urgence="danger"),
        )
        for _ in range(50):
            if len(recus) >= 2:
                break
            await asyncio.sleep(0.1)
    finally:
        await ecoute.close()
    sortes = {(r["table"], r["sorte"]) for r in recus}
    assert ("demande", "nouvelle") in sortes
    assert all(set(r) == {"evt", "table", "id", "site_id", "sorte"} for r in recus)
    assert "secret" not in json.dumps(recus).lower()
    connexion = await schema.connecter(base_portail)
    try:
        lignes = await connexion.fetch("SELECT id, tbl, ligne, sorte FROM mark.evenement_portail ORDER BY id")
        assert ("demande", str(res["demande_id"]), "nouvelle") in [(l["tbl"], l["ligne"], l["sorte"]) for l in lignes]
        assert [l["id"] for l in lignes] == sorted(l["id"] for l in lignes)
    finally:
        await connexion.close()


async def test_les_sortes_d_evenements_du_lot_1(portail):
    """Assignation, urgence, commentaire, incident, action en échec, rendez-vous de l'agent, réglage."""
    connexion = await schema.connecter(portail.base)
    try:
        demande = await connexion.fetchval("SELECT demande_id FROM mark.appel WHERE dograh_run_id = 901")
        personne = await connexion.fetchval("SELECT id FROM mark.personne LIMIT 1")
        avant = await connexion.fetchval("SELECT max(id) FROM mark.evenement_portail") or 0
        await connexion.execute("UPDATE mark.demande SET assignee_id = $2 WHERE id = $1", demande, personne)
        await connexion.execute("UPDATE mark.demande SET degre_urgence = 'danger' WHERE id = $1", demande)
        await connexion.execute(
            "INSERT INTO mark.commentaire (appel_id, auteur_compte, texte) SELECT id, 'c', 'x' FROM mark.appel WHERE dograh_run_id = 901"
        )
        await connexion.execute("INSERT INTO mark.incident (debut, brique) VALUES (now(), 'essai')")
        await connexion.execute("UPDATE mark.action SET statut = 'echec' WHERE demande_id = $1", demande)
        await connexion.execute(
            "INSERT INTO mark.rendez_vous (demande_id, debut, fin, origine) VALUES ($1, now(), now() + interval '1 hour', 'agent')",
            demande,
        )
        await connexion.execute(
            "INSERT INTO mark.rendez_vous (demande_id, debut, fin, origine) VALUES ($1, now(), now() + interval '1 hour', 'humain')",
            demande,
        )
        sortes = [
            (r["tbl"], r["sorte"])
            for r in await connexion.fetch("SELECT tbl, sorte FROM mark.evenement_portail WHERE id > $1", avant)
        ]
    finally:
        await connexion.close()
    for attendu in (
        ("demande", "assignee"), ("demande", "urgence"), ("commentaire", "commentaire"), ("incident", "incident"),
        ("action", "echec"), ("rendez_vous", "pose"),
    ):
        assert attendu in sortes, (attendu, sortes)
    assert sortes.count(("rendez_vous", "pose")) == 1  # le rendez-vous d'un humain ne réveille personne


async def test_la_purge_garde_les_evenements_trente_jours(base_portail):
    await _ecrire(base_portail, _site(2081, demande={"type": "devis"}))
    connexion = await schema.connecter_proprietaire(base_portail)
    try:
        assert await connexion.fetchval("SELECT count(*) FROM mark.evenement_portail") >= 1
        await connexion.execute("UPDATE mark.evenement_portail SET le = now() - interval '31 days' WHERE id = (SELECT min(id) FROM mark.evenement_portail)")
        await connexion.execute("SET search_path = mark")  # purger() est écrite sans chemin de recherche
        lignes = {r["table_nom"]: r["lignes"] for r in await connexion.fetch("SELECT * FROM mark.purger()")}
        assert lignes["evenement_portail"] == 1
        assert await connexion.fetchval("SELECT count(*) FROM mark.evenement_portail") >= 1  # les récents restent
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# La demande de rappel d'un visiteur dont l'agent a atteint son plafond
# --------------------------------------------------------------------------- #


async def test_la_demande_de_rappel_du_site_avec_ou_sans_lieu_et_refus_sans_coordonnees(base_portail):
    connexion = await schema.connecter(base_portail)
    try:
        avec = await sql.demander_rappel_site(
            connexion,
            {"etablissement": "site-a", "chemin": "/contact", "message": "Rappelez-moi", "contact": {"nom": "Léa", "telephone": "+33655556666"}},
        )
        sans = await sql.demander_rappel_site(
            connexion, {"etablissement": "inconnu", "contact": {"mail": "Lea@Exemple.fr"}}
        )
        lignes = {
            r["id"]: r
            for r in await connexion.fetch(
                "SELECT id, type, site_id, resume, contact_id FROM mark.demande WHERE id = ANY($1::bigint[])",
                [avec["demande_id"], sans["demande_id"]],
            )
        }
        assert lignes[avec["demande_id"]]["type"] == "rappel"
        assert lignes[avec["demande_id"]]["site_id"] is not None and lignes[sans["demande_id"]]["site_id"] is None
        assert "Rappelez-moi" in lignes[avec["demande_id"]]["resume"] and "/contact" in lignes[avec["demande_id"]]["resume"]
        assert await connexion.fetchval("SELECT mail FROM mark.contact WHERE id = $1", sans["contact_id"]) == "lea@exemple.fr"
        with pytest.raises(asyncpg.exceptions.RaiseError):
            await sql.demander_rappel_site(connexion, {"contact": {"nom": "Sans moyen"}})
    finally:
        await connexion.close()
