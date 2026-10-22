"""[.mark] Chantier agents-specialises, lot 8 : la base du client prête pour le portail et pour les
motifs multiples (migration 015 complétée, réception d'un appel, fermeture par fiche, agents de l'appel,
équipe sur plusieurs lieux).

Plan `Labo-agent-vocal/plans/agents-specialises/` (lot 8 = lot 5 du plan fiche-etablissement, A8, D48,
D76, D83, M5, C5). Chaque test passe par une VRAIE connexion à une base de test (le rôle du portail se
connecte pour de bon) ou par la vraie route de l'après-appel : il échoue si la fonctionnalité ne produit
rien.

| Test | Ce qu'il prouve |
|---|---|
| la 015 monte et se rejoue | une base en version 14 monte en 15 ; rejouée, la 015 ne casse rien |
| portail : variable absente | rien de lisible, ni appel, ni demande, ni contact, ni texte |
| portail : un lieu, deux lieux, tous | chacun ne lit que les lignes de ses établissements, sur TOUTES les tables |
| portail : écritures | prendre une demande, commenter : seulement sur une ligne visible, seulement les colonnes permises |
| portail : le groupe lui-même | `SET ROLE` sur le groupe ne contourne rien |
| portail : vues d'indicateurs | comptes justes, aucune donnée personnelle, rien pour un autre rôle |
| motifs | liste, chaîne à « ; », chaîne simple, phrase trop longue : `appel.motif` = le premier, `appel_motif` complet |
| agents de l'appel | `appel_agent` dans l'ordre, noms gardés, repli sur l'agent qui décroche |
| incidents | un incident, plusieurs appels ; rejouable ; muet sur une base en version 14 |
| fermeture par fiche | écrite dans `site`, relue, `etat_force` présent ; base en 14 : refusée, jamais perdue en silence |
| équipe sur plusieurs lieux | le courriel et le planificateur voient la personne de chacun de ses lieux ; le salarié aussi |
| lectures du portail (017) | incident, appel perdu, société, adresse, type de rendez-vous : par lieu ; indicateurs (appels perdus, urgence de la demande) ; journal sans coordonnées et selon le lieu ; variable absente = rien ; `set_config(..., true)` disparaît à la validation |
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import asyncpg
import pytest

from api.db.bases_clients import apres_appel as sql
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import traces
from api.db.bases_clients.equipe import ecrire_equipe
from api.db.bases_clients.gestes import donner_acces
from api.db.bases_clients.referentiel import ecrire_etablissements
from api.schemas.base_client import Equipe, Personne
from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.services.apres_appel import chaine
from api.services.apres_appel.envoi import (
    _motifs,
    agents_de_l_appel,
    hors_horaires_de,
    incidents_de,
    transferts_de,
)
from api.services.base_client.referentiel import lire_referentiel
from api.tests.mark.test_apres_appel import (  # noqa: F401  (fixtures)
    _envoi,
    _executer_tout_de_suite,
    _organisation,
    _regler,
    base_v4,
    modele,
    smtp,
)
from api.tests.mark.test_base_client import _serveur, base_essai, base_prete  # noqa: F401
from api.tests.mark.test_mentions_et_acces import (
    MOT_DE_PASSE,
    _connexion_du_salarie,
    base_mentions,
)  # noqa: F401

MOT_DE_PASSE_PORTAIL = "essai-portail-" + uuid.uuid4().hex[:8]


# --------------------------------------------------------------------------- #
# Le décor : une base, deux établissements, des appels bien remplis
# --------------------------------------------------------------------------- #


def _appel(run, site, numero, **plus):
    """Un envoi complet pour ``mark.recevoir_appel`` : un appel, sa demande, sa fiche, ses tours."""
    base = dict(
        etablissement=site,
        dograh_workflow_id=7,
        agent_nom="Principal",
        motif="entretien",
        issue="rappel_demande",
        degre_urgence="faible",
    )
    return _envoi(run, numero=numero, **{**base, **plus})


@pytest.fixture
async def base_portail(base_prete):
    """Deux établissements ; quatre appels (deux en A, un en B, un sans établissement), chacun avec sa
    demande, son contact, son texte, sa fiche ; un transfert, un rendez-vous, un commentaire."""
    connexion = await schema.connecter(base_prete)
    try:
        await connexion.execute(
            "INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')"
        )
        for cle in ("site-a", "site-b"):
            await connexion.execute(
                "INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise",
                cle,
            )
        await ecrire_equipe(
            connexion,
            Equipe(
                personnes=[
                    Personne(
                        cle="alice",
                        prenom="Alice",
                        nom="Martin",
                        etablissements=["site-a"],
                        mail="alice@example.org",
                        telephone="+33611111111",
                    ),
                    Personne(
                        cle="bruno",
                        prenom="Bruno",
                        nom="Petit",
                        etablissements=["site-b"],
                        mail="bruno@example.org",
                    ),
                ],
                sujets=[],
            ),
            "test",
        )
        # Les cases des listes, cochées comme le ferait .mark.
        await connexion.execute(
            "INSERT INTO mark.liste_valeur (liste, code, libelle, regle_seul) VALUES ('issue_appel', 'regle_par_agent', 'Réglé', true) "
            "ON CONFLICT DO NOTHING"
        )
        await connexion.execute(
            "INSERT INTO mark.liste_valeur (liste, code, libelle, urgent) VALUES ('degre_urgence', 'danger', 'Danger', true)"
        )
        debut = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=3)
        appels = [
            (
                901,
                "site-a",
                "+33600000001",
                dict(
                    motif="devis",
                    issue="regle_par_agent",
                    degre_urgence="danger",
                    hors_horaires=True,
                    debut=debut.isoformat(),
                ),
            ),
            (
                902,
                "site-a",
                "+33600000002",
                dict(
                    motif="entretien ; devis",
                    hors_horaires=False,
                    debut=(debut + timedelta(minutes=5)).isoformat(),
                ),
            ),
            (
                903,
                "site-b",
                "+33600000003",
                dict(motif="panne", debut=(debut + timedelta(minutes=10)).isoformat()),
            ),
            (
                904,
                None,
                "+33600000004",
                dict(
                    motif="entretien", debut=(debut + timedelta(minutes=15)).isoformat()
                ),
            ),
        ]
        for run, site, numero, plus in appels:
            await sql.recevoir_appel(connexion, _appel(run, site, numero, **plus))
        # « devis » est une opportunité (case de la liste des motifs).
        await connexion.execute(
            "UPDATE mark.liste_valeur SET opportunite = true WHERE liste = 'motif_appel' AND code = 'devis'"
        )
    finally:
        await connexion.close()
    return base_prete


async def _ids(connexion) -> dict:
    return {
        "site": {
            r["cle"]: r["id"]
            for r in await connexion.fetch("SELECT id, cle FROM mark.site")
        },
        "appel": {
            r["dograh_run_id"]: r["id"]
            for r in await connexion.fetch("SELECT id, dograh_run_id FROM mark.appel")
        },
    }


async def _peupler_les_traces(base):
    """Un transfert, une action, un commentaire sur chaque appel, un rendez-vous sur l'appel 901."""
    connexion = await schema.connecter(base)
    try:
        ids = await _ids(connexion)
        for run, appel in ids["appel"].items():
            await connexion.execute(
                "INSERT INTO mark.transfert (appel_id, numero_compose, debut, decroche) VALUES ($1, '+33600000000', now(), true)",
                appel,
            )
            demande = await connexion.fetchval(
                "SELECT demande_id FROM mark.appel WHERE id = $1", appel
            )
            await connexion.execute(
                "INSERT INTO mark.action (appel_id, demande_id, canal, destinataire, statut) VALUES ($1, $2, 'mail', 'x@example.org', 'envoyee')",
                appel,
                demande,
            )
            await connexion.execute(
                "INSERT INTO mark.commentaire (appel_id, auteur_compte, texte) VALUES ($1, 'compte-1', $2)",
                appel,
                f"note {run}",
            )
        demande = await connexion.fetchval(
            "SELECT demande_id FROM mark.appel WHERE dograh_run_id = 901"
        )
        await connexion.execute(
            "INSERT INTO mark.rendez_vous (demande_id, debut, fin, origine) VALUES ($1, now() + interval '1 day', now() + interval '1 day 1 hour', 'agent')",
            demande,
        )
        contact = await connexion.fetchval(
            "SELECT contact_id FROM mark.appel WHERE dograh_run_id = 903"
        )
        await connexion.execute(
            "INSERT INTO mark.commentaire (contact_id, auteur_compte, texte) VALUES ($1, 'compte-1', 'sur le contact B')",
            contact,
        )
        return ids
    finally:
        await connexion.close()


async def _connexion_du_portail(base, sites: str | None, *, groupe: bool = False):
    """Le portail se connecte pour de bon, avec son compte de connexion, et pose la variable de
    session. ``sites`` : « 3,7 », « * », « » ou ``None`` (variable jamais posée)."""
    from urllib.parse import urlsplit

    m = urlsplit(_serveur())
    hote = m.netloc.rsplit("@", 1)[-1]
    connexion = await asyncpg.connect(
        f"postgresql://{base}_portail_c:{MOT_DE_PASSE_PORTAIL}@{hote}/{base}", timeout=5
    )
    if groupe:
        await connexion.execute(f'SET ROLE "{base}_portail"')
    if sites is not None:
        await connexion.execute(
            "SELECT set_config('mark.sites_portail', $1, false)", sites
        )
    return connexion


@pytest.fixture
async def portail(base_portail):
    """La base peuplée + le compte de connexion du portail (créé par le propriétaire)."""
    ids = await _peupler_les_traces(base_portail)
    proprietaire = await schema.connecter_proprietaire(base_portail)
    try:
        role = await proprietaire.fetchval(
            "SELECT mark.donner_connexion_portail($1)", MOT_DE_PASSE_PORTAIL
        )
        assert role == f"{base_portail}_portail_c"
    finally:
        await proprietaire.close()
    return SimpleNamespace(base=base_portail, ids=ids)


# --------------------------------------------------------------------------- #
# 1. La 015 monte depuis la 14 et se rejoue
# --------------------------------------------------------------------------- #


async def _base_en_version_14(nom):
    """Crée la base et applique les migrations 1 à 14 seulement (comme une installation d'avant)."""
    maintenance = await asyncpg.connect(f"{_serveur()}/postgres", timeout=5)
    try:
        await maintenance.execute(f'CREATE DATABASE "{nom}"')
    finally:
        await maintenance.close()
    connexion = await schema.connecter_proprietaire(nom)
    try:
        for migration in schema.migrations():
            if migration.version > 14:
                break
            sql_migration = migration.sql.replace("\nBEGIN;\n", "\n").replace(
                "\nCOMMIT;\n", "\n"
            )
            async with connexion.transaction():
                await connexion.execute(sql_migration)
        await schema.assurer_compte_courant(connexion, nom)
        assert await schema.version_de(connexion) == 14
    finally:
        await connexion.close()


async def _appliquer_jusqua(connexion, version: int) -> list[int]:
    """Comme ``appliquer_migrations``, mais s'arrête à ``version`` (une installation de cette époque-là)."""
    actuelle = await schema.version_de(connexion) or 0
    appliquees = []
    for migration in schema.migrations():
        if actuelle < migration.version <= version:
            sql = migration.sql.replace("\nBEGIN;\n", "\n").replace("\nCOMMIT;\n", "\n")
            async with connexion.transaction():
                await connexion.execute(sql)
            appliquees.append(migration.version)
    return appliquees


async def test_une_base_en_version_14_monte_en_15_et_la_015_se_rejoue(base_essai):
    await _base_en_version_14(base_essai)
    connexion = await schema.connecter(base_essai)
    try:
        await connexion.execute(
            "INSERT INTO mark.entreprise (raison_sociale) VALUES ('E')"
        )
        # Un appel d'AVANT la 015 : son motif et son agent doivent être rangés par la montée.
        await sql.recevoir_appel(
            connexion, _appel(1, None, "+33600000001", motif="entretien")
        )
    finally:
        await connexion.close()
    proprietaire = await schema.connecter_proprietaire(base_essai)
    try:
        # La 015, puis la 016 (la fiche à plusieurs demandes). Rejouées AVANT la 017 : la 015 recrée
        # v_portail_kpi sans appels_perdus, elle ne se rejoue donc plus une fois la 017 montée.
        assert await _appliquer_jusqua(proprietaire, 16) == [15, 16]
        assert await schema.version_de(proprietaire) == 16
        # Rejouée (sans sa ligne de version), la 015 ne casse rien et ne duplique rien.
        migration = next(m for m in schema.migrations() if m.version == 15)
        corps = migration.sql[: migration.sql.index("INSERT INTO schema_version")]
        async with proprietaire.transaction():
            await proprietaire.execute(corps)
        # La 016 aussi se rejoue : elle ne casse rien et ne duplique rien.
        suivante = next(m for m in schema.migrations() if m.version == 16)
        corps_016 = suivante.sql[: suivante.sql.index("INSERT INTO schema_version")]
        async with proprietaire.transaction():
            await proprietaire.execute(corps_016)
        # La 017 (les lectures du portail) monte depuis la 16, puis se rejoue sans rien casser.
        assert await schema.appliquer_migrations(proprietaire) == list(
            range(17, schema.version_attendue() + 1)
        )
        assert await schema.version_de(proprietaire) == schema.version_attendue()
        assert await schema.appliquer_migrations(proprietaire) == []
        corps_017 = next(m for m in schema.migrations() if m.version == 17).sql
        corps_017 = corps_017[: corps_017.index("INSERT INTO schema_version")]
        async with proprietaire.transaction():
            await proprietaire.execute(corps_017)
        assert await proprietaire.fetchval("SELECT count(*) FROM mark.appel_motif") == 1
        assert await proprietaire.fetchval("SELECT count(*) FROM mark.appel_agent") == 1
        assert (
            await proprietaire.fetchval(
                "SELECT count(*) FROM mark.liste_valeur WHERE liste = 'motif_appel' AND code = 'entretien'"
            )
            == 1
        )
    finally:
        await proprietaire.close()


# --------------------------------------------------------------------------- #
# 2. Le portail : sécurité par ligne par variable de session (D76)
# --------------------------------------------------------------------------- #

TABLES_PAR_APPEL = (
    "verbatim",
    "champ_appel",
    "tour",
    "transfert",
    "appel_agent",
    "appel_motif",
    "action",
    "mention",
)


async def _compter(connexion, table: str) -> int:
    return await connexion.fetchval(f"SELECT count(*) FROM mark.{table}")


async def test_variable_absente_ou_vide_ou_illisible_rien_n_est_lisible(portail):
    for sites in (None, "", "   ", "abc", "1;DROP TABLE mark.appel", "0"):
        c = await _connexion_du_portail(portail.base, sites)
        try:
            for table in (
                "appel",
                "demande",
                "contact",
                "telephone",
                "site",
                "commentaire",
                *TABLES_PAR_APPEL,
                "rendez_vous",
            ):
                assert await _compter(c, table) == 0, (sites, table)
            for vue in (
                "v_portail_kpi",
                "v_portail_motifs",
                "v_portail_charge",
                "v_portail_rappels",
            ):
                assert await _compter(c, vue) == 0, (sites, vue)
        finally:
            await c.close()


async def test_un_lieu_ne_lit_que_ses_lignes_sur_toutes_les_tables(portail):
    a = portail.ids["site"]["site-a"]
    c = await _connexion_du_portail(portail.base, str(a))
    try:
        assert {r["cle"] for r in await c.fetch("SELECT cle FROM mark.site")} == {
            "site-a"
        }
        assert sorted(
            r["dograh_run_id"]
            for r in await c.fetch("SELECT dograh_run_id FROM mark.appel")
        ) == [901, 902]
        assert await _compter(c, "demande") == 2
        assert await _compter(c, "contact") == 2 and await _compter(c, "telephone") == 2
        # Chaque table d'un appel : les deux appels de A, jamais ceux de B ni de nulle part.
        assert await _compter(c, "verbatim") == 2
        assert await _compter(c, "transfert") == 2 and await _compter(c, "action") == 2
        assert await _compter(c, "appel_agent") == 2
        assert await _compter(c, "appel_motif") == 3  # devis ; entretien + devis
        assert await _compter(c, "tour") == 2 and await _compter(c, "champ_appel") == 4
        assert await _compter(c, "rendez_vous") == 1
        # Les commentaires : sur ses appels (2) ; ceux de B, du contact de B et de l'appel sans lieu : jamais.
        assert sorted(
            r["texte"] for r in await c.fetch("SELECT texte FROM mark.commentaire")
        ) == ["note 901", "note 902"]
    finally:
        await c.close()


async def test_deux_lieux_les_deux_et_tous_les_lieux_tout_y_compris_l_appel_sans_lieu(
    portail,
):
    a, b = portail.ids["site"]["site-a"], portail.ids["site"]["site-b"]
    deux = await _connexion_du_portail(portail.base, f" {a} , {b} ")
    try:
        assert sorted(
            r["dograh_run_id"]
            for r in await deux.fetch("SELECT dograh_run_id FROM mark.appel")
        ) == [901, 902, 903]
        # Le contact de B porte un commentaire : visible, par son appel.
        assert "sur le contact B" in [
            r["texte"] for r in await deux.fetch("SELECT texte FROM mark.commentaire")
        ]
        assert await _compter(deux, "site") == 2
    finally:
        await deux.close()
    tous = await _connexion_du_portail(portail.base, "*")
    try:
        assert (
            await _compter(tous, "appel") == 4 and await _compter(tous, "demande") == 4
        )
        assert (
            await _compter(tous, "site") == 2 and await _compter(tous, "contact") == 4
        )
    finally:
        await tous.close()


async def test_le_groupe_du_portail_lui_meme_ne_contourne_rien(portail):
    """Un compte du groupe peut faire SET ROLE sur le groupe : la règle le suit."""
    a = portail.ids["site"]["site-a"]
    sans = await _connexion_du_portail(portail.base, None, groupe=True)
    try:
        assert await _compter(sans, "appel") == 0
    finally:
        await sans.close()
    avec = await _connexion_du_portail(portail.base, str(a), groupe=True)
    try:
        assert await _compter(avec, "appel") == 2
    finally:
        await avec.close()


async def test_le_portail_ne_lit_ni_le_courriel_ni_les_tables_internes(portail):
    c = await _connexion_du_portail(portail.base, "*")
    try:
        # Les noms de l'équipe, jamais un courriel ni un téléphone.
        assert (
            len(
                await c.fetch(
                    "SELECT id, cle, prenom, nom, role, site_id, actif FROM mark.personne"
                )
            )
            == 2
        )
        for requete in (
            "SELECT mail FROM mark.personne",
            "SELECT * FROM mark.personne",
            "SELECT * FROM mark.verification",
            "SELECT * FROM mark.role_personne",
            "SELECT * FROM mark.role_site",
            "SELECT * FROM mark.journal_modif",
            "SELECT * FROM mark.reglage_metier",
            "SELECT * FROM mark.v_cahier_appels",
            "SELECT * FROM mark.kpi_jour",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await c.fetch(requete)
        for ordre in (
            "SELECT mark.donner_acces('alice', 'un-mot-de-passe-long', NULL)",
            "SELECT mark.donner_connexion_portail('un-mot-de-passe-long')",
            "DELETE FROM mark.appel",
            "UPDATE mark.appel SET motif = 'x'",
            "INSERT INTO mark.site (entreprise_id, nom) VALUES (1, 'x')",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await c.execute(ordre)
    finally:
        await c.close()


async def test_le_portail_agit_sur_une_demande_visible_et_commente_seulement_chez_lui(
    portail,
):
    a = portail.ids["site"]["site-a"]
    c = await _connexion_du_portail(portail.base, str(a))
    try:
        # Prendre en charge une demande de A.
        mises = await c.execute(
            "UPDATE mark.demande SET prise_par_compte = 'compte-7', prise_le = now(), statut = 'en_cours'"
        )
        assert mises == "UPDATE 2"
        assert (
            await c.fetchval(
                "SELECT count(*) FROM mark.demande WHERE prise_par_compte = 'compte-7'"
            )
            == 2
        )
        # Une demande de B : aucune ligne touchée (elle n'existe pas pour ce compte).
        assert (
            await c.execute(
                "UPDATE mark.demande SET prise_par_compte = 'compte-7' WHERE site_id = $1",
                portail.ids["site"]["site-b"],
            )
            == "UPDATE 0"
        )
        # Une colonne qui n'est pas au portail : refusée.
        for colonne in (
            "site_id = NULL",
            "contact_id = NULL",
            "resume = 'x'",
            "rattachee_a_id = 1",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await c.execute(f"UPDATE mark.demande SET {colonne}")
        # Commenter un appel visible, un contact visible ; jamais un appel d'ailleurs.
        appel_a = portail.ids["appel"][901]
        appel_b = portail.ids["appel"][903]
        await c.execute(
            "INSERT INTO mark.commentaire (appel_id, auteur_compte, texte) VALUES ($1, 'compte-7', 'vu')",
            appel_a,
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute(
                "INSERT INTO mark.commentaire (appel_id, auteur_compte, texte) VALUES ($1, 'compte-7', 'espion')",
                appel_b,
            )
        # Un commentaire est sur un appel OU un contact, jamais les deux ni aucun.
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute(
                "INSERT INTO mark.commentaire (appel_id, contact_id, auteur_compte, texte) "
                "SELECT $1, contact_id, 'compte-7', 'deux' FROM mark.appel WHERE id = $1",
                appel_a,
            )
        # L'auteur modifie son texte et le supprime doucement ; il ne l'efface pas.
        assert (
            await c.execute(
                "UPDATE mark.commentaire SET texte = 'vu et corrigé', modifie_le = now() WHERE texte = 'vu'"
            )
            == "UPDATE 1"
        )
        assert (
            await c.execute(
                "UPDATE mark.commentaire SET supprime_le = now() WHERE texte = 'vu et corrigé'"
            )
            == "UPDATE 1"
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute("DELETE FROM mark.commentaire")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute("UPDATE mark.commentaire SET appel_id = 1")
    finally:
        await c.close()


async def test_les_autres_roles_ne_changent_pas_la_connexion_courante_lit_tout(portail):
    connexion = await schema.connecter(portail.base)
    try:
        assert (
            await _compter(connexion, "appel") == 4
            and await _compter(connexion, "contact") == 4
        )
        assert (
            await _compter(connexion, "site") == 2
            and await _compter(connexion, "commentaire") == 5
        )
        # Et ne lit aucune vue du portail (la règle est « portail seulement »).
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await _compter(connexion, "v_portail_kpi")
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# 3. Les vues d'indicateurs : justes, sans donnée personnelle
# --------------------------------------------------------------------------- #


async def test_les_indicateurs_sont_justes_par_lieu_et_sans_donnee_personnelle(portail):
    a = portail.ids["site"]["site-a"]
    c = await _connexion_du_portail(portail.base, str(a))
    try:
        kpi = await c.fetch("SELECT * FROM mark.v_portail_kpi")
        assert len(kpi) == 1
        ligne = dict(kpi[0])
        assert ligne["site_id"] == a
        # 901 : réglé par l'agent (case), danger (case urgent), hors horaires, motif « devis » (opportunité).
        # 902 : « entretien ; devis » (devis = opportunité), dans les horaires.
        assert (
            ligne["appels"] == 2 and ligne["regles_seul"] == 1 and ligne["urgents"] == 1
        )
        assert ligne["hors_horaires"] == 1 and ligne["nouveaux_projets"] == 2
        assert ligne["premiers_appels"] == 2 and ligne["transmis"] == 2
        assert (
            ligne["rendez_vous_pris"] == 1
        )  # le rendez-vous posé par l'agent sur la demande de 901
    finally:
        await c.close()


async def test_rendez_vous_pris_compte_les_rendez_vous_poses_par_l_agent(portail):
    connexion = await schema.connecter(portail.base)
    try:
        # Un rendez-vous annulé et un posé à la main ne comptent pas.
        demande = await connexion.fetchval(
            "SELECT demande_id FROM mark.appel WHERE dograh_run_id = 902"
        )
        await connexion.execute(
            "INSERT INTO mark.rendez_vous (demande_id, debut, fin, origine, statut) VALUES "
            "($1, now(), now() + interval '1 hour', 'agent', 'annule'), ($1, now(), now() + interval '1 hour', 'humain', 'pose')",
            demande,
        )
    finally:
        await connexion.close()
    c = await _connexion_du_portail(portail.base, "*")
    try:
        assert (
            await c.fetchval("SELECT sum(rendez_vous_pris) FROM mark.v_portail_kpi")
            == 1
        )
    finally:
        await c.close()


async def test_les_motifs_la_charge_et_les_rappels(portail):
    c = await _connexion_du_portail(portail.base, "*")
    try:
        motifs = {
            r["motif"]: (r["appels"], r["opportunite"])
            for r in await c.fetch(
                "SELECT motif, sum(appels)::int AS appels, bool_or(opportunite) AS opportunite FROM mark.v_portail_motifs GROUP BY motif"
            )
        }
        # Un appel par motif : devis (901, 902), entretien (902, 904), panne (903).
        assert motifs == {
            "devis": (2, True),
            "entretien": (2, False),
            "panne": (1, False),
        }
        assert await c.fetchval("SELECT sum(appels) FROM mark.v_portail_charge") == 4
        rappels = dict(
            await c.fetchrow(
                "SELECT sum(demandes)::int AS demandes, sum(ouvertes)::int AS ouvertes FROM mark.v_portail_rappels"
            )
        )
        assert rappels == {"demandes": 4, "ouvertes": 4}
    finally:
        await c.close()
    # Une demande rappelée sort des ouvertes et entre dans le délai.
    connexion = await schema.connecter(portail.base)
    try:
        await connexion.execute(
            "UPDATE mark.demande SET rappelee_le = creee_le + interval '90 minutes' WHERE id = "
            "(SELECT demande_id FROM mark.appel WHERE dograh_run_id = 901)"
        )
    finally:
        await connexion.close()
    c = await _connexion_du_portail(portail.base, "*")
    try:
        r = dict(
            await c.fetchrow(
                "SELECT sum(rappelees)::int AS rappelees, sum(delai_rappel_total_s)::int AS delai, sum(ouvertes)::int AS ouvertes "
                "FROM mark.v_portail_rappels"
            )
        )
        assert r == {"rappelees": 1, "delai": 5400, "ouvertes": 3}
    finally:
        await c.close()


async def test_aucune_vue_d_indicateurs_ne_porte_de_donnee_personnelle(portail):
    c = await _connexion_du_portail(portail.base, "*")
    try:
        for vue in (
            "v_portail_kpi",
            "v_portail_motifs",
            "v_portail_charge",
            "v_portail_rappels",
        ):
            colonnes = {
                a["attname"]
                for a in await c.fetch(
                    "SELECT attname FROM pg_attribute WHERE attrelid = $1::regclass AND attnum > 0 AND NOT attisdropped",
                    f"mark.{vue}",
                )
            }
            interdits = {
                "numero",
                "numero_appelant",
                "nom",
                "prenom",
                "mail",
                "telephone",
                "synthese",
                "contact_id",
                "texte",
            }
            assert not (colonnes & interdits), (vue, colonnes & interdits)
    finally:
        await c.close()


# --------------------------------------------------------------------------- #
# 4. Les motifs et les agents d'un appel, à la réception (A8, D48, D83)
# --------------------------------------------------------------------------- #


async def _motifs_ecrits(connexion, run):
    ligne = await connexion.fetchrow(
        "SELECT id, motif FROM mark.appel WHERE dograh_run_id = $1", run
    )
    liste = [
        r["motif"]
        for r in await connexion.fetch(
            "SELECT motif FROM mark.appel_motif WHERE appel_id = $1 ORDER BY ordre",
            ligne["id"],
        )
    ]
    return ligne["motif"], liste


@pytest.mark.parametrize(
    "brut, premier, tous",
    [
        (["entretien", "devis"], "entretien", ["entretien", "devis"]),
        (
            "entretien ; devis ;; panne ; devis",
            "entretien",
            ["entretien", "devis", "panne"],
        ),
        # Une chaîne sans « ; » est UN motif, virgules comprises : comportement d'avant.
        (
            "entretien du poêle, panne",
            "entretien du poêle, panne",
            ["entretien du poêle, panne"],
        ),
        ("devis", "devis", ["devis"]),
        ([], None, []),
        (None, None, []),
        ("  ", None, []),
    ],
)
async def test_les_motifs_recus_une_liste_ou_une_chaine_a_point_virgule(
    base_prete, brut, premier, tous
):
    connexion = await schema.connecter(base_prete)
    try:
        envoi = _envoi(11, motif=None)
        envoi.pop("motif")
        envoi["motif" if isinstance(brut, str) or brut is None else "motifs"] = brut
        await sql.recevoir_appel(connexion, envoi)
        assert await _motifs_ecrits(connexion, 11) == (premier, tous)
        # Chaque motif est aussi une valeur de la liste fermée.
        dans_la_liste = {
            r["code"]
            for r in await connexion.fetch(
                "SELECT code FROM mark.liste_valeur WHERE liste = 'motif_appel'"
            )
        }
        assert set(tous) <= dans_la_liste
        # Rejoué : rien de plus.
        rejeu = await sql.recevoir_appel(connexion, envoi)
        assert rejeu["doublon"] is True
        assert await _motifs_ecrits(connexion, 11) == (premier, tous)
    finally:
        await connexion.close()


async def test_une_phrase_libre_trop_longue_reste_le_motif_sans_entrer_dans_la_liste(
    base_prete,
):
    phrase = (
        "Le poêle à granulés de la maison de campagne ne s'allume plus depuis la semaine dernière "
        * 2
    )
    connexion = await schema.connecter(base_prete)
    try:
        await sql.recevoir_appel(connexion, _envoi(12, motif=phrase))
        premier, tous = await _motifs_ecrits(connexion, 12)
        assert premier == phrase.strip() and tous == []
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.liste_valeur WHERE liste = 'motif_appel'"
            )
            == 0
        )
    finally:
        await connexion.close()


async def test_les_agents_de_l_appel_dans_l_ordre_et_sans_liste_l_agent_qui_decroche(
    base_prete,
):
    connexion = await schema.connecter(base_prete)
    try:
        debut = datetime.now(UTC).replace(microsecond=0)
        await sql.recevoir_appel(
            connexion,
            _envoi(
                21,
                dograh_workflow_id=7,
                agent_nom="Principal",
                agents=[
                    {"dograh_workflow_id": 7, "nom": "Principal"},
                    {"dograh_workflow_id": 9, "nom": "Spécialisé"},
                    {
                        "dograh_workflow_id": 7,
                        "nom": None,
                    },  # il rend la main au principal
                    {
                        "dograh_workflow_id": 11,
                        "nom": None,
                        "heure": (debut + timedelta(seconds=40)).isoformat(),
                    },
                ],
                debut=debut.isoformat(),
            ),
        )
        lignes = await connexion.fetch(
            "SELECT aa.ordre, a.dograh_workflow_id AS wid, a.nom, aa.heure FROM mark.appel_agent aa "
            "JOIN mark.agent a ON a.id = aa.agent_id JOIN mark.appel c ON c.id = aa.appel_id "
            "WHERE c.dograh_run_id = 21 ORDER BY aa.ordre"
        )
        assert [(r["ordre"], r["wid"], r["nom"]) for r in lignes] == [
            (1, 7, "Principal"),
            (2, 9, "Spécialisé"),
            (3, 7, "Principal"),
            (4, 11, "Agent"),
        ]
        assert lignes[0]["heure"] == debut and lignes[1]["heure"] is None
        assert lignes[3]["heure"] == debut + timedelta(seconds=40)
        # Sans liste (les appelants d'avant) : l'agent qui a décroché, seul.
        await sql.recevoir_appel(
            connexion, _envoi(22, dograh_workflow_id=7, agent_nom="Principal")
        )
        assert [
            r["wid"]
            for r in await connexion.fetch(
                "SELECT a.dograh_workflow_id AS wid FROM mark.appel_agent aa JOIN mark.agent a ON a.id = aa.agent_id "
                "JOIN mark.appel c ON c.id = aa.appel_id WHERE c.dograh_run_id = 22"
            )
        ] == [7]
    finally:
        await connexion.close()


# Ce que l'envoi construit à partir du run (fonctions pures, mêmes entrées que la vraie chaîne).


def test_l_envoi_range_les_motifs_les_agents_les_transferts_et_les_horaires():
    assert _motifs(["a", " b ", "a", None, ""]) == ["a", "b"]
    assert (
        _motifs("a ; b") == ["a", "b"]
        and _motifs("a, b") == ["a, b"]
        and _motifs(None) == []
    )
    run = SimpleNamespace(workflow_id=7, workflow=SimpleNamespace(name="Principal"))
    contexte = {
        "agent_transfers": [
            {"destination_workflow_id": 9, "to_visit_id": "v2", "outcome": "completed"},
            {
                "destination_workflow_id": 10,
                "to_visit_id": None,
                "outcome": "cancelled",
            },  # n'a pas abouti
            {"destination_workflow_id": 7, "to_visit_id": "v3", "outcome": "completed"},
        ]
    }
    assert [a["dograh_workflow_id"] for a in agents_de_l_appel(run, contexte)] == [
        7,
        9,
        7,
    ]
    assert transferts_de(
        {
            "transferts_humains": [{"le": "x", "cible": "alice", "issue": "decroche"}],
            "transferts": [
                {"cible": "numero:***1234", "issue": "repondeur"},
                {"cible": "z"},
            ],
        }
    ) == [
        {"le": "x", "cible": "alice", "issue": "decroche"},
        {"le": None, "cible": "numero:***1234", "issue": "repondeur"},
    ]
    assert [
        hors_horaires_de({"etat_ouverture": e})
        for e in ("OUVERT", "SUR_RENDEZ_VOUS", "FERME", "PAUSE", None)
    ] == [False, False, True, True, None]
    analyse = {
        "incidents": {
            "items": [
                {
                    "kind": "silence_after_tool",
                    "fatal": False,
                    "processor": "outil",
                },  # pas un incident
                {
                    "kind": "provider_error",
                    "fatal": False,
                    "processor": "VoixService",
                    "detail": "connexion coupée",
                },
                {
                    "kind": "provider_error",
                    "fatal": False,
                    "processor": "VoixService",
                    "detail": "connexion coupée",
                },  # doublon
                {
                    "kind": "model_timeout",
                    "fatal": False,
                    "processor": None,
                    "detail": "3.2 s > 3 s (attempt 2)",
                },
            ]
        }
    }
    assert incidents_de(analyse, datetime(2026, 10, 16, tzinfo=UTC)) == [
        {
            "brique": "VoixService",
            "cause": "provider_error : connexion coupée",
            "debut": "2026-10-16T00:00:00+00:00",
        },
        {
            "brique": "model_timeout",
            "cause": "model_timeout",
            "debut": "2026-10-16T00:00:00+00:00",
        },
    ]


# --------------------------------------------------------------------------- #
# 5. Les incidents (lot 9) : une brique, une cause, plusieurs appels
# --------------------------------------------------------------------------- #


async def test_un_incident_plusieurs_appels_rejouable_et_distinct_au_dela_de_30_minutes(
    base_prete,
):
    connexion = await schema.connecter(base_prete)
    try:
        debut = datetime.now(UTC).replace(microsecond=0)
        for run in (31, 32, 33):
            await sql.recevoir_appel(connexion, _envoi(run, debut=debut.isoformat()))
        appels = {
            r["dograh_run_id"]: r["id"]
            for r in await connexion.fetch("SELECT id, dograh_run_id FROM mark.appel")
        }
        premier = await traces.noter_incident(
            connexion,
            appel_id=appels[31],
            brique="Voix",
            cause="provider_error",
            debut=debut,
        )
        meme = await traces.noter_incident(
            connexion,
            appel_id=appels[32],
            brique="Voix",
            cause="provider_error",
            debut=debut + timedelta(minutes=10),
        )
        rejeu = await traces.noter_incident(
            connexion,
            appel_id=appels[31],
            brique="Voix",
            cause="provider_error",
            debut=debut,
        )
        autre_cause = await traces.noter_incident(
            connexion,
            appel_id=appels[32],
            brique="Voix",
            cause="pipeline_error",
            debut=debut,
        )
        plus_tard = await traces.noter_incident(
            connexion,
            appel_id=appels[33],
            brique="Voix",
            cause="provider_error",
            debut=debut + timedelta(hours=3),
        )
        assert premier == meme == rejeu and len({premier, autre_cause, plus_tard}) == 3
        liens = await connexion.fetch(
            "SELECT incident_id, appel_id FROM mark.incident_appel ORDER BY incident_id, appel_id"
        )
        assert [(r["incident_id"], r["appel_id"]) for r in liens] == sorted(
            [
                (premier, appels[31]),
                (premier, appels[32]),
                (autre_cause, appels[32]),
                (plus_tard, appels[33]),
            ]
        )
        fin = await connexion.fetchval(
            "SELECT fin FROM mark.incident WHERE id = $1", premier
        )
        assert fin >= debut + timedelta(minutes=10)
    finally:
        await connexion.close()


async def test_sur_une_base_en_version_14_les_traces_se_taisent_sans_lever(base_essai):
    await _base_en_version_14(base_essai)
    connexion = await schema.connecter(base_essai)
    try:
        assert (
            await traces.noter_incident(connexion, appel_id=None, brique="x", cause="y")
            is None
        )
        assert (
            await traces.ecrire_issues_de_transfert(
                connexion, 1, None, [{"issue": "decroche", "cible": "a"}]
            )
            == 0
        )
        assert await traces.agents_rattaches(connexion) == set()
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# 6. La fermeture par fiche, écrite dans `site` et relue (C5)
# --------------------------------------------------------------------------- #


def _fiche(**plus):
    return Etablissement(id="fiche-a", nom="Fiche A", **plus)


async def test_une_fiche_fermee_s_ecrit_dans_site_et_se_relit_etat_force_present(
    base_prete,
):
    fin = datetime(2026, 12, 24, 18, 0)  # une heure de Paris, sans décalage
    connexion = await schema.connecter(base_prete)
    try:
        await ecrire_etablissements(
            connexion,
            CatalogueEtablissements(
                etablissements=[
                    _fiche(etat_force="FERME", etat_force_jusqu_a=fin),
                    Etablissement(id="fiche-b", nom="Fiche B"),
                ]
            ),
            "test",
        )
        brut = await connexion.fetchrow(
            "SELECT etat_force, etat_force_jusqu_a FROM mark.site WHERE cle = 'fiche-a'"
        )
        assert (brut["etat_force"], brut["etat_force_jusqu_a"]) == ("FERME", fin)
        relu = await lire_referentiel(connexion)
        par_id = {e.id: e for e in relu.etablissements.etablissements}
        assert (
            par_id["fiche-a"].etat_force == "FERME"
            and par_id["fiche-a"].etat_force_jusqu_a == fin
        )
        assert par_id["fiche-b"].etat_force is None and relu.refus == []
        # Rouverte : l'état forcé s'efface aussi.
        await ecrire_etablissements(
            connexion,
            CatalogueEtablissements(
                etablissements=[_fiche(), Etablissement(id="fiche-b", nom="Fiche B")]
            ),
            "test",
        )
        assert (
            await connexion.fetchval(
                "SELECT etat_force FROM mark.site WHERE cle = 'fiche-a'"
            )
            is None
        )
    finally:
        await connexion.close()


async def test_une_base_en_version_14_refuse_de_fermer_une_fiche_au_lieu_de_la_perdre(
    base_essai,
):
    await _base_en_version_14(base_essai)
    connexion = await schema.connecter(base_essai)
    try:
        # Sans fermeture, rien ne change : la base d'avant écrit comme avant.
        await ecrire_etablissements(
            connexion, CatalogueEtablissements(etablissements=[_fiche()]), "test"
        )
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.site WHERE cle = 'fiche-a'"
            )
            == 1
        )
        relu = await lire_referentiel(connexion)
        assert relu.etablissements.etablissements[0].etat_force is None
        # Avec une fermeture : refusée, dite (mettre à niveau), et rien n'est écrit.
        with pytest.raises(schema.BaseClientIndisponible, match="Upgrade"):
            await ecrire_etablissements(
                connexion,
                CatalogueEtablissements(etablissements=[_fiche(etat_force="PAUSE")]),
                "test",
            )
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# 7. Une personne sur plusieurs lieux est vue de chacun de ses lieux (M5)
# --------------------------------------------------------------------------- #


async def _equipe_a_deux_lieux(base):
    connexion = await schema.connecter(base)
    try:
        await connexion.execute(
            "INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise') ON CONFLICT DO NOTHING"
        )
        for cle in ("site-a", "site-b"):
            await connexion.execute(
                "INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, $1, $1 FROM mark.entreprise LIMIT 1 ON CONFLICT DO NOTHING",
                cle,
            )
        await ecrire_equipe(
            connexion,
            Equipe(
                personnes=[
                    # Sur les deux lieux (le premier est dans la colonne d'avant, le second seulement dans personne_site).
                    Personne(
                        cle="duo",
                        prenom="Duo",
                        mail="duo@example.org",
                        destinataire_defaut=True,
                        etablissements=["site-a", "site-b"],
                    ),
                    Personne(
                        cle="solo",
                        prenom="Solo",
                        mail="solo@example.org",
                        destinataire_defaut=True,
                        etablissements=["site-a"],
                    ),
                    Personne(
                        cle="partout",
                        prenom="Partout",
                        mail="partout@example.org",
                        destinataire_defaut=True,
                    ),
                ],
                sujets=[],
            ),
            "test",
        )
    finally:
        await connexion.close()


async def test_les_destinataires_par_defaut_voient_la_personne_de_chacun_de_ses_lieux(
    base_prete,
):
    await _equipe_a_deux_lieux(base_prete)
    connexion = await schema.connecter(base_prete)
    try:
        a = [d["cle"] for d in await sql.destinataires_de(connexion, None, "site-a")]
        b = [d["cle"] for d in await sql.destinataires_de(connexion, None, "site-b")]
        sans_lieu = [
            d["cle"] for d in await sql.destinataires_de(connexion, None, None)
        ]
        # Une personne d'un lieu d'abord, toute l'entreprise ensuite.
        assert (
            a == ["duo", "solo", "partout"]
            and b == ["duo", "partout"]
            and sans_lieu == ["partout"]
        )
    finally:
        await connexion.close()


async def test_le_courriel_apres_appel_part_chez_la_personne_du_second_lieu(
    base_v4, smtp, modele, db_session, async_session
):
    """Par la vraie route (après-appel complet, SMTP réel sur la boucle locale) : un appel pris au lieu B
    écrit à la personne dont B est le SECOND lieu."""
    from api.db.models import UserModel  # noqa: F401
    from api.tasks.workflow_completion import process_workflow_completion
    from api.tests.mark import test_apres_appel as t

    org = await _organisation(async_session, db_session)
    await _regler(db_session, org, base_v4, smtp)
    await _equipe_a_deux_lieux(base_v4)
    run = await db_session.create_workflow_run(
        name="essai",
        workflow_id=org.agent.id,
        mode="twilio",
        user_id=org.utilisateur.id,
        call_type=t.CallType.INBOUND,
        organization_id=org.organisation.id,
        definition_id=org.definition.id,
        initial_context={
            "caller_number": "+33612345678",
            "runtime_configuration": {
                "llm_provider": "mistral",
                "etablissement": {"id": "site-b"},
            },
        },
        gathered_context={
            "extracted_variables": {"nom": "Dupont", "motif": "autre chose"},
            "call_disposition": "rappel_demande",
        },
        logs={"realtime_feedback_events": t._evenements()},
    )
    await db_session.update_workflow_run(
        run.id, usage_info={"call_duration_seconds": 42.4}
    )
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite([])):
        await process_workflow_completion(None, run.id)
    # Le premier destinataire par défaut du lieu B : « duo » (second lieu) ; « solo » (lieu A) n'y est pas.
    assert [m["a"] for m in smtp.messages] == [
        ["duo@example.org", "partout@example.org"]
    ]


async def test_le_salarie_sur_deux_lieux_voit_les_appels_des_deux(base_mentions):
    """sites_du_salarie lit personne_site : Alice, sur A et B, voit les appels de A et de B."""
    connexion = await schema.connecter(base_mentions)
    try:
        ids = await _ids(connexion)
        await ecrire_equipe(
            connexion,
            Equipe(
                personnes=[
                    Personne(
                        cle="alice",
                        prenom="Alice",
                        mail="alice@example.org",
                        etablissements=["site-a", "site-b"],
                    ),
                    Personne(
                        cle="bruno",
                        prenom="Bruno",
                        mail="bruno@example.org",
                        etablissements=["site-b"],
                    ),
                ],
                sujets=[],
            ),
            "test",
        )
    finally:
        await connexion.close()
    proprietaire = await schema.connecter_proprietaire(base_mentions)
    try:
        role = await donner_acces(proprietaire, "alice", MOT_DE_PASSE)
    finally:
        await proprietaire.close()
    alice = await _connexion_du_salarie(base_mentions, role)
    try:
        vus = sorted(
            r["id"]
            for r in await alice.fetch(
                "SELECT id FROM mark.v_appels_de_mon_etablissement"
            )
        )
        assert vus == sorted(ids["appel"].values())
    finally:
        await alice.close()


# --------------------------------------------------------------------------- #
# 8. Le planificateur voit la personne de chacun de ses lieux
# --------------------------------------------------------------------------- #

from api.tests.mark.test_planificateur import (  # noqa: E402, F401
    CAMILLE,
    SACHA,
    _appeler,
    _moteur,
    _outil,
    installe,
)


async def test_le_planificateur_propose_les_creneaux_de_la_personne_du_second_lieu(
    installe, monkeypatch
):
    """Par la vraie route (l'outil du moteur, la vraie base, le vrai répartiteur) : l'appel est pris au
    lieu B ; Camille est sur A et B, Sacha sur A seulement : seuls les créneaux de Camille sont proposés."""
    from api.db.bases_clients import connexion as sch
    from api.services.etablissements.appel import EtablissementDeLappel
    from api.services.planificateur import action as module_action

    from api.schemas.base_client import Sujet

    connexion = await sch.connecter(installe.base)
    try:
        await connexion.execute(
            "INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'site-b', 'Site B' FROM mark.entreprise LIMIT 1"
        )
        await ecrire_equipe(
            connexion,
            Equipe(
                personnes=[
                    Personne(
                        cle="camille",
                        prenom="Camille",
                        agendas={"google_agenda": CAMILLE},
                        etablissements=["site-a", "site-b"],
                    ),
                    Personne(
                        cle="sacha",
                        prenom="Sacha",
                        agendas={"google_agenda": SACHA},
                        etablissements=["site-a"],
                    ),
                ],
                sujets=[
                    Sujet(
                        code="visite",
                        libelle="Visite",
                        destinataires=["camille", "sacha"],
                    )
                ],
            ),
            "test",
        )
    finally:
        await connexion.close()

    async def au_lieu_b(_ctx):
        return EtablissementDeLappel(
            etablissement=Etablissement(id="site-b", nom="Site B"),
            source="numero_appele",
            lu_depuis="copie",
        )

    monkeypatch.setattr(module_action, "_etablissement_servi", au_lieu_b)
    engine, mgr, enregistres = _moteur(
        installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux")]
    )
    await mgr.register_handlers(["uuid-Creneaux"])
    r = await _appeler(enregistres["creneaux"][0], {"souhait": "jeudi"})
    assert r.get("creneaux"), r
    [estampille] = engine._gathered_context["planificateur"]
    assert estampille["ordre"] == ["camille"] and {
        c["personne"] for c in estampille["creneaux"]
    } == {"camille"}


# --------------------------------------------------------------------------- #
# 5. Les lectures du portail (migration 017, lot F1)
# --------------------------------------------------------------------------- #


def _jsonb(valeur):
    """asyncpg rend le jsonb en texte : on le relit."""
    return json.loads(valeur) if isinstance(valeur, str) else valeur


async def _ajouter_lectures(base, ids):
    """Ce que le portail lit de plus, par lieu : un incident et un appel perdu (lieu A et lieu B), une
    société et une adresse par contact, un type de rendez-vous par lieu et un pour toute l'entreprise,
    une valeur « urgente » sur la demande de l'appel A."""
    connexion = await schema.connecter(base)
    try:
        a = ids["site"]["site-a"]
        b = ids["site"]["site-b"]
        appel_a, appel_b = ids["appel"][901], ids["appel"][903]
        contact_a = await connexion.fetchval(
            "SELECT contact_id FROM mark.appel WHERE id = $1", appel_a
        )
        contact_b = await connexion.fetchval(
            "SELECT contact_id FROM mark.appel WHERE id = $1", appel_b
        )
        demande_a = await connexion.fetchval(
            "SELECT demande_id FROM mark.appel WHERE id = $1", appel_a
        )
        await connexion.execute(
            "INSERT INTO mark.site_numero (numero, site_id) VALUES ('+33600000011', $1), ('+33600000012', $2)",
            a,
            b,
        )
        await connexion.execute(
            "INSERT INTO mark.appel_perdu (call_sid, numero, numero_appele, debut) VALUES "
            "('CA-A', '+33611111110', '+33600000011', now()), "
            "('CA-B', '+33622222220', '+33600000012', now())"
        )
        for cause, appel in (("pont-A", appel_a), ("pont-B", appel_b)):
            incident = await connexion.fetchval(
                "INSERT INTO mark.incident (debut, cause) VALUES (now(), $1) RETURNING id",
                cause,
            )
            await connexion.execute(
                "INSERT INTO mark.incident_appel (incident_id, appel_id) VALUES ($1, $2)",
                incident,
                appel,
            )
        # Un incident sans appel : personne ne le voit, même pas l'entreprise.
        await connexion.execute(
            "INSERT INTO mark.incident (debut, cause) VALUES (now(), 'sans-appel')"
        )
        for nom, contact in (("Société A", contact_a), ("Société B", contact_b)):
            societe = await connexion.fetchval(
                "INSERT INTO mark.societe (nom) VALUES ($1) RETURNING id", nom
            )
            await connexion.execute(
                "UPDATE mark.contact SET societe_id = $1 WHERE id = $2", societe, contact
            )
        await connexion.execute(
            "INSERT INTO mark.adresse (contact_id, voie) VALUES ($1, 'Rue A'), ($2, 'Rue B')",
            contact_a,
            contact_b,
        )
        await connexion.execute(
            "INSERT INTO mark.type_rendez_vous (code, site_id, libelle, duree_min) VALUES "
            "('pose_a', $1, 'Pose A', 30), ('pose_b', $2, 'Pose B', 30), "
            "('pose_tous', NULL, 'Pose partout', 30)",
            a,
            b,
        )
        await connexion.execute(
            "INSERT INTO mark.liste_valeur (liste, code, libelle, urgent) "
            "VALUES ('degre_urgence', 'tres_urgent', 'Très urgent', true)"
        )
        await connexion.execute(
            "UPDATE mark.demande SET degre_urgence = 'tres_urgent' WHERE id = $1", demande_a
        )
    finally:
        await connexion.close()


LECTURES_NOUVELLES = {
    "incident": "SELECT cause AS v FROM mark.incident",
    "appel_perdu": "SELECT call_sid AS v FROM mark.appel_perdu",
    "societe": "SELECT nom AS v FROM mark.societe",
    "adresse": "SELECT voie AS v FROM mark.adresse",
    "type_rendez_vous": "SELECT code AS v FROM mark.type_rendez_vous",
}


async def test_le_portail_lit_ses_incidents_appels_perdus_societes_adresses_et_types_de_rdv(
    portail,
):
    await _ajouter_lectures(portail.base, portail.ids)
    a = str(portail.ids["site"]["site-a"])
    b = str(portail.ids["site"]["site-b"])
    attendus = {
        a: {
            "incident": ["pont-A"],
            "appel_perdu": ["CA-A"],
            "societe": ["Société A"],
            "adresse": ["Rue A"],
            "type_rendez_vous": ["pose_a", "pose_tous"],
        },
        b: {
            "incident": ["pont-B"],
            "appel_perdu": ["CA-B"],
            "societe": ["Société B"],
            "adresse": ["Rue B"],
            "type_rendez_vous": ["pose_b", "pose_tous"],
        },
    }
    for sites, attendu in attendus.items():
        c = await _connexion_du_portail(portail.base, sites)
        try:
            for table, requete in LECTURES_NOUVELLES.items():
                lus = sorted(r["v"] for r in await c.fetch(requete))
                assert lus == attendu[table], (sites, table)
        finally:
            await c.close()
    # Toute l'entreprise voit les deux incidents liés à un appel ; l'incident sans appel reste invisible.
    c = await _connexion_du_portail(portail.base, "*")
    try:
        incidents = sorted(r["v"] for r in await c.fetch(LECTURES_NOUVELLES["incident"]))
        assert incidents == ["pont-A", "pont-B"]
        perdus = sorted(r["v"] for r in await c.fetch(LECTURES_NOUVELLES["appel_perdu"]))
        assert perdus == ["CA-A", "CA-B"]
    finally:
        await c.close()


async def test_les_indicateurs_comptent_les_appels_perdus_et_l_urgence_de_la_demande(
    portail,
):
    await _ajouter_lectures(portail.base, portail.ids)
    a = str(portail.ids["site"]["site-a"])
    b = str(portail.ids["site"]["site-b"])
    requete = (
        "SELECT coalesce(sum(appels_perdus), 0) AS perdus, coalesce(sum(urgents), 0) AS urgents "
        "FROM mark.v_portail_kpi"
    )
    for sites, perdus, urgents in ((a, 1, 1), (b, 1, 0), ("*", 2, 1)):
        c = await _connexion_du_portail(portail.base, sites)
        try:
            ligne = await c.fetchrow(requete)
            assert (ligne["perdus"], ligne["urgents"]) == (perdus, urgents), sites
        finally:
            await c.close()


async def test_le_journal_du_portail_sans_coordonnees_et_selon_le_lieu(portail):
    base = portail.base
    a = str(portail.ids["site"]["site-a"])
    b = str(portail.ids["site"]["site-b"])
    await _ajouter_lectures(base, portail.ids)
    connexion = await schema.connecter(base)
    try:
        await connexion.execute(
            "UPDATE mark.site SET nom = 'Site B renommé' WHERE cle = 'site-b'"
        )
        await connexion.execute(
            "UPDATE mark.personne SET mail = 'nouveau@example.org', telephone = '+33699999999' "
            "WHERE prenom = 'Alice'"
        )
        await connexion.execute(
            "UPDATE mark.entreprise SET nom_commercial = 'Nom commercial'"
        )
    finally:
        await connexion.close()
    c = await _connexion_du_portail(base, a)
    try:
        bruno = await c.fetchval("SELECT id FROM mark.personne WHERE prenom = 'Bruno'")
        alice = await c.fetchval("SELECT id FROM mark.personne WHERE prenom = 'Alice'")
        lignes = await c.fetch(
            "SELECT table_nom, ligne_id, avant, apres FROM mark.v_portail_historique"
        )
        vus = {(r["table_nom"], r["ligne_id"]) for r in lignes}
        # Le lieu A : son lieu, ses personnes, la liste ; jamais le lieu B, ni l'entreprise.
        assert ("site", a) in vus and ("site", b) not in vus
        assert ("liste_valeur", "degre_urgence:tres_urgent") in vus
        assert not any(t == "entreprise" for t, _ in vus)
        assert ("personne", str(alice)) in vus and ("personne", str(bruno)) not in vus
        # Sans coordonnées : aucune trace du courriel ni du téléphone d'une personne.
        for r in lignes:
            if r["table_nom"] == "personne":
                for valeur in (r["avant"], r["apres"]):
                    if valeur is not None:
                        assert "mail" not in _jsonb(valeur)
                        assert "telephone" not in _jsonb(valeur)
    finally:
        await c.close()
    # Toute l'entreprise voit le changement d'entreprise ; un compte sans variable ne voit rien.
    c = await _connexion_du_portail(base, "*")
    try:
        tables = {
            r["table_nom"]
            for r in await c.fetch("SELECT table_nom FROM mark.v_portail_historique")
        }
        assert "entreprise" in tables
    finally:
        await c.close()
    c = await _connexion_du_portail(base, None)
    try:
        assert await _compter(c, "v_portail_historique") == 0
    finally:
        await c.close()


async def test_variable_absente_ou_illisible_rien_des_lectures_nouvelles(portail):
    await _ajouter_lectures(portail.base, portail.ids)
    for sites in (None, "", "abc", "0"):
        c = await _connexion_du_portail(portail.base, sites)
        try:
            for table in (
                "incident",
                "incident_appel",
                "appel_perdu",
                "societe",
                "adresse",
                "type_rendez_vous",
                "v_portail_historique",
                "v_portail_kpi",
            ):
                assert await _compter(c, table) == 0, (sites, table)
        finally:
            await c.close()


async def test_une_variable_posee_dans_une_transaction_disparait_apres_validation(portail):
    a = str(portail.ids["site"]["site-a"])
    c = await _connexion_du_portail(portail.base, None)
    try:
        async with c.transaction():
            await c.execute("SELECT set_config('mark.sites_portail', $1, true)", a)
            assert await _compter(c, "appel") == 2
        assert await _compter(c, "appel") == 0
        assert await _compter(c, "site") == 0
    finally:
        await c.close()
