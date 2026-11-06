"""[.mark] Builder partie 3, SA-17c : les trois gestes des contacts du portail, par la vraie route, la vraie authentification
(la clé d'API du client) et une vraie base du client (migration 023).

| Test | Ce qu'il prouve |
|---|---|
| fusion | conversations, demandes, commentaires, numéros passent sur la fiche gardée ; aucun champ écrasé ; mail et « déclaré » repris s'il manquait ; « ne pas mémoriser » cumulé ; le doublon disparaît ; un doute vers le doublon va vers la fiche gardée ; journal avec l'auteur réel |
| fusion rejouée | un second passage rend la même fiche gardée (``deja_fait``), sans rien changer |
| sans doute | une fiche sans doute n'est pas fusionnée (409), rien ne bouge |
| séparer | le doute est levé, les deux fiches restent avec tout leur contenu ; rejoué, rien de plus |
| mémoriser | se coche et se décoche ; idempotent ; le corps est validé (champ inconnu, absent, non booléen : 422) |
| l'agent ne lit plus l'historique | par le vrai chemin de lecture du dossier (source du hub) : fiche marquée = identité sans demande ni rendez-vous ; décochée = tout revient |
| cloisonnement | la clé d'un autre client ne touche pas le contact (404, rien ne change) ; sans clé 401 ; un contact inconnu 404 |
| permission | une session d'équipe sans ``contacts.traiter`` : 403 ; avec : passe ; la clé du client passe |
| migration des droits | la montée donne la permission aux rôles qui ont ``agents.modifier`` et à eux seuls, deux fois sans doublon ; la descente la retire |
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import asyncpg
import pytest
import sqlalchemy as sa

from api.db.bases_clients import apres_appel as sql_appel
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import dossier as sql_dossier
from api.enums import OrganizationConfigurationKey
from api.services.equipe_mark.permissions import PERMISSIONS, PERMISSIONS_DE_CLE
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)
from api.tests.mark.test_apres_appel import _envoi
from api.tests.mark.test_base_client import _serveur, base_essai  # noqa: F401

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "c9e4b7a2d1f5_permission_contacts_traiter.py"
RACINE = "/api/v1/organizations/contacts"
AUTEUR = "portail : Martine Leroy"


@pytest.fixture
async def seconde_base(base_essai):  # noqa: F811
    """La base d'un autre client, retirée à la fin."""
    nom = f"mark_essai_{uuid.uuid4().hex[:10]}"
    await schema.creer_base(base_essai)
    await schema.creer_base(nom)
    try:
        yield base_essai, nom
    finally:
        c = await asyncpg.connect(f"{_serveur()}/postgres", timeout=5)
        try:
            await c.execute(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)')
            for suffixe in ("portail", "salarie", "direction", "interface", "ecriture", "portail_c"):
                await c.execute(f'DROP ROLE IF EXISTS "{nom}_{suffixe}"')
            for role in await c.fetch("SELECT rolname FROM pg_roles WHERE rolname LIKE $1", rf"{nom}\_p\_%"):
                await c.execute(f'DROP ROLE IF EXISTS "{role["rolname"]}"')
        finally:
            await c.close()


async def _cas(db, seconde_base):
    base_a, base_b = seconde_base
    a = await creer_organisation(db, f"ct-a-{uuid.uuid4().hex[:6]}")
    b = await creer_organisation(db, f"ct-b-{uuid.uuid4().hex[:6]}")
    await db.upsert_configuration(a, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": base_a})
    await db.upsert_configuration(b, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": base_b})
    admin, _ = await creer_compte(db, f"ct-admin-{uuid.uuid4().hex[:6]}@example.com", role="Administrateur", organisations=[a, b])
    _, cle_a = await db.create_api_key(a, "portail A", admin.id)
    _, cle_b = await db.create_api_key(b, "portail B", admin.id)
    return SimpleNamespace(a=a, b=b, base_a=base_a, base_b=base_b, cle_a=cle_a, cle_b=cle_b, admin=admin)


def _cle(cle: str, auteur: str | None = AUTEUR) -> dict:
    h = {"X-API-Key": cle}
    if auteur:
        h["X-Mark-Auteur"] = auteur
    return h


async def _garnir(base: str) -> SimpleNamespace:
    """Une fiche gardée et son doublon, chacune avec un appel, un commentaire et un numéro ; une troisième fiche qui doute du doublon."""
    c = await schema.connecter(base)
    try:
        garde = (await sql_appel.recevoir_appel(c, _envoi(101, numero="+33611111111", contact={"nom": "Dupont"})))["contact_id"]
        doublon = (await sql_appel.recevoir_appel(c, _envoi(102, numero="+33622222222", contact={"nom": "Dupond", "mail": "d@exemple.fr"})))["contact_id"]
        autre = (await sql_appel.recevoir_appel(c, _envoi(103, numero="+33633333333", contact={"nom": "Autre"})))["contact_id"]
        await c.execute("UPDATE mark.contact SET prenom = 'Alex', nature = 'professionnel' WHERE id = $1", garde)
        await c.execute(
            "UPDATE mark.contact SET prenom = 'Alexandre', mail_declare = true, ne_pas_memoriser = true, doublon_de = $2, "
            "doublon_raison = 'même nom' WHERE id = $1", doublon, garde)
        await c.execute("UPDATE mark.contact SET doublon_de = $2, doublon_raison = 'même mail' WHERE id = $1", autre, doublon)
        await c.execute("INSERT INTO mark.adresse (contact_id, code_postal, commune) VALUES ($1, '60100', 'Creil')", doublon)
        for contact, texte in ((garde, "note gardée"), (doublon, "note du doublon")):
            await c.execute("INSERT INTO mark.commentaire (contact_id, auteur_compte, texte) VALUES ($1, 'essai', $2)", contact, texte)
        return SimpleNamespace(garde=garde, doublon=doublon, autre=autre)
    finally:
        await c.close()


async def _lire(base, requete, *args):
    c = await schema.connecter(base)
    try:
        return await c.fetch(requete, *args)
    finally:
        await c.close()


# --------------------------------------------------------------------------- fusionner


async def test_la_fusion_deplace_tout_sans_ecraser_un_champ(db_session, seconde_base):
    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    async with client_http() as c:
        r = await c.post(f"{RACINE}/{ids.doublon}/fusionner", headers=_cle(cas.cle_a))
    assert r.status_code == 200, r.text
    fiche = r.json()
    assert fiche["id"] == ids.garde and fiche["fusionne_depuis"] == ids.doublon and fiche["deja_fait"] is False
    # Aucun champ de la fiche gardée écrasé ; ce qui lui manquait vient du doublon (mail et son « déclaré »).
    assert (fiche["nom"], fiche["prenom"], fiche["nature"]) == ("Dupont", "Alex", "professionnel")
    assert fiche["mail"] == "d@exemple.fr" and fiche["mail_declare"] is True
    assert fiche["ne_pas_memoriser"] is True  # se cumule
    assert fiche["telephones"] == ["+33611111111", "+33622222222"]
    assert fiche["nb_appels"] == 2 and fiche["nb_commentaires"] == 2 and fiche["doublon"] is None
    # Le doublon disparaît ; son adresse passe (la fiche gardée n'en avait pas) ; le doute d'une autre fiche suit.
    assert not await _lire(cas.base_a, "SELECT 1 FROM mark.contact WHERE id = $1", ids.doublon)
    assert len(await _lire(cas.base_a, "SELECT 1 FROM mark.adresse WHERE contact_id = $1", ids.garde)) == 1
    [autre] = await _lire(cas.base_a, "SELECT doublon_de FROM mark.contact WHERE id = $1", ids.autre)
    assert autre["doublon_de"] == ids.garde
    assert len(await _lire(cas.base_a, "SELECT 1 FROM mark.demande WHERE contact_id = $1", ids.garde)) == 2
    # Qui, quoi, quand : l'auteur réel au journal.
    [ligne] = await _lire(cas.base_a, "SELECT champ, auteur FROM mark.journal_modif WHERE table_nom = 'contact' AND champ = 'fusion'")
    assert AUTEUR in ligne["auteur"]


async def test_un_nom_ou_un_mail_deja_su_n_est_jamais_ecrase_par_la_fusion(db_session, seconde_base):
    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    await _lire(cas.base_a, "SELECT 1")
    c = await schema.connecter(cas.base_a)
    try:
        await c.execute("UPDATE mark.contact SET mail = 'gardé@exemple.fr', mail_declare = false WHERE id = $1", ids.garde)
    finally:
        await c.close()
    async with client_http() as cl:
        r = await cl.post(f"{RACINE}/{ids.doublon}/fusionner", headers=_cle(cas.cle_a))
    assert r.status_code == 200
    assert r.json()["mail"] == "gardé@exemple.fr" and r.json()["mail_declare"] is False and r.json()["nom"] == "Dupont"


async def test_une_fusion_rejouee_rend_la_meme_fiche_sans_rien_changer(db_session, seconde_base):
    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    async with client_http() as c:
        premier = await c.post(f"{RACINE}/{ids.doublon}/fusionner", headers=_cle(cas.cle_a))
        avant = await _lire(cas.base_a, "SELECT count(*) AS n FROM mark.journal_modif")
        second = await c.post(f"{RACINE}/{ids.doublon}/fusionner", headers=_cle(cas.cle_a))
        apres = await _lire(cas.base_a, "SELECT count(*) AS n FROM mark.journal_modif")
    assert second.status_code == 200, second.text
    assert second.json() == {**premier.json(), "deja_fait": True}
    assert avant[0]["n"] == apres[0]["n"]


async def test_une_fiche_sans_doute_n_est_pas_fusionnee(db_session, seconde_base):
    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    async with client_http() as c:
        r = await c.post(f"{RACINE}/{ids.garde}/fusionner", headers=_cle(cas.cle_a))
    assert r.status_code == 409
    assert len(await _lire(cas.base_a, "SELECT 1 FROM mark.contact")) == 3


# --------------------------------------------------------------------------- séparer


async def test_separer_leve_le_doute_et_garde_les_deux_fiches_entieres(db_session, seconde_base):
    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    async with client_http() as c:
        r = await c.post(f"{RACINE}/{ids.doublon}/separer", headers=_cle(cas.cle_a))
        rejoue = await c.post(f"{RACINE}/{ids.doublon}/separer", headers=_cle(cas.cle_a))
    assert r.status_code == 200, r.text
    assert r.json()["doublon"] is None and r.json()["id"] == ids.doublon and r.json()["nb_appels"] == 1
    assert rejoue.status_code == 200 and rejoue.json() == r.json()
    assert len(await _lire(cas.base_a, "SELECT 1 FROM mark.contact")) == 3
    assert len(await _lire(cas.base_a, "SELECT 1 FROM mark.commentaire")) == 2
    # Une seule ligne de journal : le second passage n'a rien levé.
    assert len(await _lire(cas.base_a, "SELECT 1 FROM mark.journal_modif WHERE table_nom = 'contact' AND champ = 'doublon'")) == 1
    # L'autre fiche, qui doutait toujours du doublon, n'est pas touchée.
    [autre] = await _lire(cas.base_a, "SELECT doublon_de FROM mark.contact WHERE id = $1", ids.autre)
    assert autre["doublon_de"] == ids.doublon


# --------------------------------------------------------------------------- mémoriser


async def test_ne_pas_memoriser_se_coche_et_se_decoche_idempotent(db_session, seconde_base):
    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    async with client_http() as c:
        coche = await c.put(f"{RACINE}/{ids.garde}/memoriser", headers=_cle(cas.cle_a), json={"memoriser": False})
        coche2 = await c.put(f"{RACINE}/{ids.garde}/memoriser", headers=_cle(cas.cle_a), json={"memoriser": False})
        journal = await _lire(cas.base_a, "SELECT 1 FROM mark.journal_modif WHERE champ = 'ne_pas_memoriser'")
        decoche = await c.put(f"{RACINE}/{ids.garde}/memoriser", headers=_cle(cas.cle_a), json={"memoriser": True})
        decoche2 = await c.put(f"{RACINE}/{ids.garde}/memoriser", headers=_cle(cas.cle_a), json={"memoriser": True})
    assert coche.status_code == 200 and coche.json()["ne_pas_memoriser"] is True and coche2.json() == coche.json()
    assert len(journal) == 1  # le second geste identique ne journalise rien
    assert decoche.json()["ne_pas_memoriser"] is False and decoche2.json() == decoche.json()


@pytest.mark.parametrize("corps", [{}, {"memoriser": "peut-etre"}, {"memoriser": True, "id": 5}, [True]])
async def test_le_corps_du_geste_memoriser_est_valide(db_session, seconde_base, corps):
    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    async with client_http() as c:
        r = await c.put(f"{RACINE}/{ids.garde}/memoriser", headers=_cle(cas.cle_a), json=corps)
    assert r.status_code == 422


async def test_l_agent_ne_lit_plus_aucun_historique_d_une_personne_qui_ne_veut_pas_etre_memorisee(db_session, seconde_base):
    """R1 : par le vrai chemin de lecture du dossier de l'agent (la source du hub), pas par une doublure."""
    from api.services.verification import source as source_dossier

    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    c = await schema.connecter(cas.base_a)
    try:
        demande = await c.fetchval("SELECT id FROM mark.demande WHERE contact_id = $1", ids.garde)
        await c.execute(
            "INSERT INTO mark.rendez_vous (demande_id, debut, fin, origine) "
            "VALUES ($1, now() + interval '2 days', now() + interval '2 days 1 hour', 'humain')", demande)
    finally:
        await c.close()

    async def lire(identifiant):
        async def _connexion(_org):
            return await schema.connecter(cas.base_a)

        with patch.object(source_dossier, "_connexion", new=_connexion):
            return await source_dossier.lire(cas.a, source_dossier.HUB, str(identifiant))

    avant = await lire(ids.garde)
    assert len(avant["demandes"]) == 1 and len(avant["rendez_vous"]) == 1 and avant["references"] == [str(demande)]
    async with client_http() as cl:
        await cl.put(f"{RACINE}/{ids.garde}/memoriser", headers=_cle(cas.cle_a), json={"memoriser": False})
    oublie = await lire(ids.garde)
    assert oublie["demandes"] == [] and oublie["rendez_vous"] == [] and oublie["references"] == []
    assert oublie["nom"] == "Dupont" and oublie["telephones"] == ["+33611111111"]  # de quoi la reconnaître, rien de son historique
    async with client_http() as cl:
        await cl.put(f"{RACINE}/{ids.garde}/memoriser", headers=_cle(cas.cle_a), json={"memoriser": True})
    assert await lire(ids.garde) == avant
    # La lecture directe de SQL du dossier (sans la source) obéit au même drapeau.
    c = await schema.connecter(cas.base_a)
    try:
        assert (await sql_dossier.lire_dossier(c, ids.doublon))["demandes"] == []  # le doublon était marqué
    finally:
        await c.close()


# --------------------------------------------------------------------------- cloisonnement et permission


async def test_la_cle_d_un_autre_client_ne_touche_aucun_contact(db_session, seconde_base):
    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    # L'autre client a une fiche portant le même numéro d'identifiant : la clé B n'atteint que SA base.
    await _garnir(cas.base_b)
    c = await schema.connecter(cas.base_b)
    try:
        await c.execute("DELETE FROM mark.contact WHERE id = $1", ids.doublon)
    finally:
        await c.close()
    async with client_http() as cl:
        fusion = await cl.post(f"{RACINE}/{ids.doublon}/fusionner", headers=_cle(cas.cle_b))
        separer = await cl.post(f"{RACINE}/{ids.doublon}/separer", headers=_cle(cas.cle_b))
        memo = await cl.put(f"{RACINE}/{ids.doublon}/memoriser", headers=_cle(cas.cle_b), json={"memoriser": False})
        inconnu = await cl.post(f"{RACINE}/987654/separer", headers=_cle(cas.cle_a))
        sans_cle = await cl.post(f"{RACINE}/{ids.doublon}/fusionner")
        # L'adresse ne déplace pas la clé : l'organisation du corps ou de l'adresse n'existe pas ici.
        autre_org = await cl.post(f"{RACINE}/{ids.doublon}/fusionner", headers={**_cle(cas.cle_b), "X-Mark-Organisation": str(cas.a)})
    assert (fusion.status_code, separer.status_code, memo.status_code) == (404, 404, 404)
    assert inconnu.status_code == 404 and sans_cle.status_code == 401 and autre_org.status_code in (403, 404)
    # Rien n'a bougé chez le client A.
    [fiche] = await _lire(cas.base_a, "SELECT doublon_de, ne_pas_memoriser FROM mark.contact WHERE id = $1", ids.doublon)
    assert fiche["doublon_de"] == ids.garde and fiche["ne_pas_memoriser"] is True
    assert len(await _lire(cas.base_a, "SELECT 1 FROM mark.contact_fusion")) == 0


async def test_la_permission_est_exigee_d_une_session_d_equipe(db_session, seconde_base):
    cas = await _cas(db_session, seconde_base)
    ids = await _garnir(cas.base_a)
    sans = await db_session.creer_role(nom="Ct-sans", labo_ouvert=False, tous_les_clients=True, permissions=["conversations.voir"], organisations=[])
    avec = await db_session.creer_role(nom="Ct-avec", labo_ouvert=False, tous_les_clients=True, permissions=["contacts.traiter"], organisations=[])
    refuse, j_refuse = await creer_compte(db_session, f"ct-sans-{uuid.uuid4().hex[:6]}@example.com", organisations=[cas.a])
    await db_session.poser_membre(refuse.id, sans)
    passe, j_passe = await creer_compte(db_session, f"ct-avec-{uuid.uuid4().hex[:6]}@example.com", organisations=[cas.a])
    await db_session.poser_membre(passe.id, avec)
    async with client_http() as c:
        non = await c.post(f"{RACINE}/{ids.doublon}/separer", headers=entetes(j_refuse, cas.a))
        oui = await c.post(f"{RACINE}/{ids.doublon}/separer", headers=entetes(j_passe, cas.a))
        cle = await c.post(f"{RACINE}/{ids.doublon}/separer", headers=_cle(cas.cle_a))
    assert non.status_code == 403 and "contacts.traiter" in non.json()["detail"]
    assert oui.status_code == 200, oui.text
    assert cle.status_code == 200
    [fiche] = await _lire(cas.base_a, "SELECT doublon_de FROM mark.contact WHERE id = $1", ids.doublon)
    assert fiche["doublon_de"] is None


def test_la_permission_est_dans_la_liste_fermee_des_cles():
    assert "contacts.traiter" in PERMISSIONS and "contacts.traiter" in PERMISSIONS_DE_CLE


# --------------------------------------------------------------------------- migration des droits


def _charger_migration():
    spec = importlib.util.spec_from_file_location("migration_contacts_traiter", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_la_migration_accorde_la_permission_aux_roles_qui_modifient_les_agents_et_se_defait(db_session):
    avec = await db_session.creer_role(nom="Mig-ct-avec", labo_ouvert=False, tous_les_clients=True, permissions=["agents.modifier"], organisations=[])
    sans = await db_session.creer_role(nom="Mig-ct-sans", labo_ouvert=False, tous_les_clients=True, permissions=["conversations.voir"], organisations=[])
    migration = _charger_migration()

    async def permissions(role: int) -> set[str]:
        async with db_session.async_session() as session:
            lignes = await session.execute(sa.text("SELECT permission FROM mark_role_permissions WHERE role_id = :r"), {"r": role})
            return {p for (p,) in lignes}

    async def jouer(instructions):
        async with db_session.async_session() as session:
            for instruction in instructions:
                await session.execute(sa.text(instruction))
            await session.commit()

    class _Op:
        def __init__(self):
            self.instructions: list[str] = []

        def execute(self, texte):
            self.instructions.append(texte)

    for _ in range(2):  # deux montées de suite : aucun doublon
        op = _Op()
        with patch.object(migration, "op", op):
            migration.upgrade()
        await jouer(op.instructions)
    assert await permissions(avec) == {"agents.modifier", "contacts.traiter"}
    assert await permissions(sans) == {"conversations.voir"}
    op = _Op()
    with patch.object(migration, "op", op):
        migration.downgrade()
    await jouer(op.instructions)
    assert await permissions(avec) == {"agents.modifier"}
