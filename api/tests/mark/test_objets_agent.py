"""[.mark] Lot F7 du chantier cloture-code-avant-migration : les objets de l'agent (migration 019, D106 à D119).

Chaque test passe par une VRAIE base du client (le rôle du portail se connecte pour de bon, avec son compte),
par la vraie route et la vraie authentification (clé d'API), ou par la vraie lecture de l'appel. Il échoue si
la fonctionnalité ne produit rien.

| Test | Ce qu'il prouve |
|---|---|
| la 019 monte et se rejoue | une base en 18 monte en 19 ; rejouée, la 019 ne casse rien |
| type en SQL | un montant est un nombre, une date une date, un oui/non « oui » ou « non » ; une ligne vide est refusée |
| historique | création, valeur changée, ligne ajoutée et retirée, objet supprimé : tout est gardé avec l'auteur ; ni modifié, ni supprimé, ni vidé |
| cloisonnement | le portail d'un établissement voit ses objets et ceux de toute l'entreprise, jamais ceux d'un autre (objets, colonnes, lignes, historique) ; variable absente = rien ; il change une valeur, jamais un nom |
| colonne de .mark | le portail ne la supprime ni ne la renomme ; il ajoute la sienne, la remplit, la supprime (ses cellules partent) |
| plafond | réglé dans la base, bloquant pour Dograh ET pour le portail ; le texte calculé en SQL est celui du fork |
| vue du portail | un objet s'y montre seulement lu par un agent rattaché, dans un lieu visible |
| lecture de l'appel | les objets sont lus avec la fiche ; rendus dans le contexte (valeur, tableau) ; une valeur déjà là est gardée |
| base injoignable | `{{nom}}` reste écrit tel quel (le moteur ne le vide pas), estampille, incident après l'appel |
| utilisé par | `{{nom}}`, `{{ nom }}`, `{{nom | repli}}` et une phrase du catalogue qui le nomme ; jamais un autre nom |
| routes | créer, lire (taille, plafond), réécrire, supprimer ; auteur réel à l'historique ; plafond bloquant (422) ; sans clé 401 ; autre organisation : rien |
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.objets import (
    ObjetRefuse,
    ecrire_objet,
    ecrire_plafond,
    ecrire_utilisation,
    lire_objets,
    supprimer_objet,
)
from api.enums import OrganizationConfigurationKey
from api.schemas.objets_agent import ColonneObjet, LigneObjet, ObjetEnvoye
from api.services.objets_agent.appel import (
    BRIQUE_INCIDENT,
    incidents_des_objets,
    injecter_objets,
)
from api.services.objets_agent.rendu import rendre
from api.services.objets_agent.utilisation import agents_qui_lisent
from api.tests.mark.test_agents_servis import (  # noqa: F401  (fixtures)
    _client,
    _cle,
    _groupe_avec_capacites,
    _organisation,
    base_v4,
    smtp,
)
from api.tests.mark.test_base_client import _RedisFactice, base_essai, base_prete  # noqa: F401
from api.tests.mark.test_base_portail import (  # noqa: F401  (fixtures)
    _connexion_du_portail,
    base_portail,
    portail,
)
from api.utils.template_renderer import render_template

AUTEUR = "dograh:essai"


def _valeur(nom="frais", type_="montant", valeur="35", etablissement=None, **plus):
    return ObjetEnvoye(
        nom=nom, libelle=plus.pop("libelle", nom.capitalize()), forme="valeur", type=type_, valeur=valeur,
        etablissement=etablissement, **plus,
    )


def _liste(nom="marques", etablissement=None, lignes=(("Edilkamin", "oui"), ("Rika", "non"))):
    return ObjetEnvoye(
        nom=nom,
        libelle="Marques prises en charge",
        description="Pour l'agent",
        forme="liste",
        etablissement=etablissement,
        colonnes=[
            ColonneObjet(libelle="Marque", type="texte", ordre=1),
            ColonneObjet(libelle="Prise en charge", type="oui_non", ordre=2),
        ],
        lignes=[
            LigneObjet(ordre=i, valeurs={"Marque": m, "Prise en charge": p}) for i, (m, p) in enumerate(lignes)
        ],
    )


async def _ecriture(base):
    return await schema.connecter(base)


# --------------------------------------------------------------------------- #
# 1. La migration
# --------------------------------------------------------------------------- #


async def test_une_base_en_version_18_monte_en_19_et_la_019_se_rejoue(base_essai):
    from api.tests.mark.test_base_portail import _appliquer_jusqua, _base_en_version_14

    await _base_en_version_14(base_essai)
    proprietaire = await schema.connecter_proprietaire(base_essai)
    try:
        assert await _appliquer_jusqua(proprietaire, 18) == [15, 16, 17, 18]
        assert await schema.appliquer_migrations(proprietaire) == [19]
        assert await schema.version_de(proprietaire) == 19 == schema.version_attendue()
        await ecrire_objet(proprietaire, _liste(), AUTEUR)
        migration = next(m for m in schema.migrations() if m.version == 19)
        corps = migration.sql[: migration.sql.index("INSERT INTO schema_version")]
        async with proprietaire.transaction():
            await proprietaire.execute(corps)
        assert await schema.appliquer_migrations(proprietaire) == []
        # Rejouée : l'objet, ses lignes et le plafond sont intacts, rien n'est dupliqué.
        assert [len(o.lignes) for o in await lire_objets(proprietaire)] == [2]
        assert await proprietaire.fetchval("SELECT count(*) FROM mark.objet_agent_reglage") == 1
    finally:
        await proprietaire.close()


# --------------------------------------------------------------------------- #
# 2. Le type, l'historique
# --------------------------------------------------------------------------- #


async def test_le_type_est_valide_en_sql_et_une_ligne_vide_est_refusee(base_prete):
    c = await _ecriture(base_prete)
    try:
        await ecrire_objet(c, _valeur(valeur="12,50"), AUTEUR)
        await ecrire_objet(c, _valeur(nom="ouverture", type_="date", valeur="2026-10-22"), AUTEUR)
        for nom, type_, mauvaise in (
            ("a", "montant", "douze"),
            ("b", "montant", "12,555"),
            ("c", "nombre", "1e3"),
            ("d", "date", "2026-02-30"),
            ("e", "date", "22/10/2026"),
            ("f", "oui_non", "peut-être"),
        ):
            with pytest.raises(ObjetRefuse):
                await ecrire_objet(c, _valeur(nom=nom, type_=type_, valeur=mauvaise), AUTEUR)
        with pytest.raises(ObjetRefuse, match="oui_non"):
            await ecrire_objet(c, _liste(lignes=(("Edilkamin", "parfois"),)), AUTEUR)
        with pytest.raises(ObjetRefuse, match="vide"):
            await ecrire_objet(c, _liste(lignes=(("  ", ""),)), AUTEUR)
        # Rien des refus n'est resté : deux objets, ceux qui étaient valides.
        assert sorted(o.nom for o in await lire_objets(c)) == ["frais", "ouverture"]
    finally:
        await c.close()


async def test_l_historique_garde_tout_avec_l_auteur_et_ne_s_efface_jamais(base_prete):
    c = await _ecriture(base_prete)
    try:
        ident = await ecrire_objet(c, _liste(), "portail : Camille Dupont (dograh:1)")
        objet = next(o for o in await lire_objets(c) if o.id == ident)
        envoi = objet.model_dump(include=set(ObjetEnvoye.model_fields))
        envoi["lignes"] = [envoi["lignes"][0], {"ordre": 5, "valeurs": {"Marque": "Jøtul", "Prise en charge": "oui"}}]
        await ecrire_objet(c, ObjetEnvoye.model_validate(envoi), AUTEUR, ident)
        await supprimer_objet(c, ident, AUTEUR)
        lignes = await c.fetch(
            "SELECT table_nom, operation, auteur FROM mark.objet_agent_historique WHERE objet_id = $1 ORDER BY id",
            ident,
        )
        operations = [(r["table_nom"], r["operation"]) for r in lignes]
        assert operations[0] == ("objet_agent", "insert")
        assert operations.count(("objet_agent_colonne", "insert")) == 2
        assert ("objet_agent_ligne", "delete") in operations  # Rika retirée
        assert operations.count(("objet_agent_ligne", "insert")) == 3  # deux d'abord, Jøtul ensuite
        assert ("objet_agent", "delete") in operations
        assert lignes[0]["auteur"] == "portail : Camille Dupont (dograh:1)"
        for geste in (
            "DELETE FROM mark.objet_agent_historique",
            "UPDATE mark.objet_agent_historique SET auteur = 'x'",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await c.execute(geste)
    finally:
        await c.close()
    proprietaire = await schema.connecter_proprietaire(base_prete)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await proprietaire.execute("TRUNCATE mark.objet_agent_historique")
        assert await proprietaire.fetchval("SELECT count(*) FROM mark.objet_agent_historique") > 5
    finally:
        await proprietaire.close()


# --------------------------------------------------------------------------- #
# 3. Le portail : cloisonnement, colonnes de .mark, plafond, vue
# --------------------------------------------------------------------------- #


async def _trois_objets(base):
    """Un objet du lieu A, un du lieu B, un de toute l'entreprise."""
    c = await _ecriture(base)
    try:
        return {
            "a": await ecrire_objet(c, _liste(nom="marques_a", etablissement="site-a"), AUTEUR),
            "b": await ecrire_objet(c, _liste(nom="marques_b", etablissement="site-b"), AUTEUR),
            "tous": await ecrire_objet(c, _valeur(nom="frais"), AUTEUR),
        }
    finally:
        await c.close()


async def test_le_portail_ne_voit_que_les_objets_de_ses_etablissements(portail):
    ids = await _trois_objets(portail.base)
    a = str(portail.ids["site"]["site-a"])
    c = await _connexion_du_portail(portail.base, a)
    try:
        assert sorted(r["nom"] for r in await c.fetch("SELECT nom FROM mark.objet_agent")) == ["frais", "marques_a"]
        objets_colonnes = {r["objet_id"] for r in await c.fetch("SELECT objet_id FROM mark.objet_agent_colonne")}
        objets_lignes = {r["objet_id"] for r in await c.fetch("SELECT objet_id FROM mark.objet_agent_ligne")}
        assert objets_colonnes == objets_lignes == {ids["a"]}
        historique = {r["objet_id"] for r in await c.fetch("SELECT objet_id FROM mark.objet_agent_historique")}
        assert historique == {ids["a"], ids["tous"]}
        # Il change une valeur ; jamais celle d'un objet qu'il ne voit pas ; jamais un nom.
        assert await c.execute("UPDATE mark.objet_agent SET valeur = '40' WHERE nom = 'frais'") == "UPDATE 1"
        assert await c.execute("UPDATE mark.objet_agent_ligne SET ordre = 9 WHERE objet_id = $1", ids["b"]) == "UPDATE 0"
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute("UPDATE mark.objet_agent SET nom = 'autre' WHERE nom = 'frais'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute("DELETE FROM mark.objet_agent")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute(
                "INSERT INTO mark.objet_agent (nom, libelle, forme, type) VALUES ('x', 'X', 'valeur', 'texte')"
            )
        colonne_b = await _une_colonne(portail.base, ids["b"])
        with pytest.raises(asyncpg.InsufficientPrivilegeError):  # sécurité par ligne : l'objet B est hors de vue
            await c.execute(
                "INSERT INTO mark.objet_agent_ligne (objet_id, valeurs) VALUES ($1, $2::jsonb)",
                ids["b"], json.dumps({str(colonne_b): "Intrus"}),
            )
    finally:
        await c.close()
    for variable in (None, "", "garbage"):
        c = await _connexion_du_portail(portail.base, variable)
        try:
            for table in ("objet_agent", "objet_agent_colonne", "objet_agent_ligne", "objet_agent_historique"):
                assert await c.fetchval(f"SELECT count(*) FROM mark.{table}") == 0, (variable, table)
        finally:
            await c.close()
    c = await _connexion_du_portail(portail.base, "*")
    try:
        assert await c.fetchval("SELECT count(*) FROM mark.objet_agent") == 3
    finally:
        await c.close()


async def _une_colonne(base, objet_id, pose_par="mark"):
    c = await _ecriture(base)
    try:
        return await c.fetchval(
            "SELECT id FROM mark.objet_agent_colonne WHERE objet_id = $1 AND pose_par = $2 ORDER BY ordre LIMIT 1",
            objet_id, pose_par,
        )
    finally:
        await c.close()


async def test_une_colonne_de_mark_ne_se_supprime_pas_depuis_le_portail(portail):
    ids = await _trois_objets(portail.base)
    colonne = await _une_colonne(portail.base, ids["a"])
    c = await _connexion_du_portail(portail.base, str(portail.ids["site"]["site-a"]))
    try:
        for geste in (
            "DELETE FROM mark.objet_agent_colonne WHERE id = $1",
            "UPDATE mark.objet_agent_colonne SET libelle = 'Renommée' WHERE id = $1",
            "UPDATE mark.objet_agent_colonne SET type = 'nombre' WHERE id = $1",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match=".mark"):
                await c.execute(geste, colonne)
        # Sa propre colonne : il l'ajoute (elle est à lui d'office), la remplit, la renomme, la supprime.
        sienne = await c.fetchval(
            "INSERT INTO mark.objet_agent_colonne (objet_id, libelle, type, ordre) VALUES ($1, 'Note', 'texte', 3) "
            "RETURNING id",
            ids["a"],
        )
        assert await c.fetchval("SELECT pose_par FROM mark.objet_agent_colonne WHERE id = $1", sienne) == "client"
        await c.execute(
            "UPDATE mark.objet_agent_ligne SET valeurs = valeurs || jsonb_build_object($2::text, 'à revoir') "
            "WHERE objet_id = $1",
            ids["a"], str(sienne),
        )
        await c.execute("UPDATE mark.objet_agent_colonne SET libelle = 'Remarque' WHERE id = $1", sienne)
        assert await c.execute("DELETE FROM mark.objet_agent_colonne WHERE id = $1", sienne) == "DELETE 1"
        restes = [json.loads(r["valeurs"]) for r in await c.fetch(
            "SELECT valeurs FROM mark.objet_agent_ligne WHERE objet_id = $1", ids["a"]
        )]
        assert restes and all(str(sienne) not in v for v in restes)
    finally:
        await c.close()
    c = await _ecriture(portail.base)
    try:
        assert await c.fetchval("SELECT count(*) FROM mark.objet_agent_colonne WHERE id = $1", colonne) == 1
    finally:
        await c.close()


async def test_le_plafond_bloque_dograh_et_le_portail_et_le_texte_sql_est_celui_du_fork(portail):
    ids = await _trois_objets(portail.base)
    c = await _ecriture(portail.base)
    try:
        for objet in await lire_objets(c):
            assert await c.fetchval("SELECT mark.objet_agent_texte($1)", objet.id) == rendre(objet)
        await ecrire_plafond(c, 100, AUTEUR)
        longues = tuple((f"Marque numéro {i}", "oui") for i in range(10))
        with pytest.raises(ObjetRefuse, match="plafond"):
            await ecrire_objet(c, _liste(nom="trop_longue", lignes=longues), AUTEUR)
        assert "trop_longue" not in [o.nom for o in await lire_objets(c)]
    finally:
        await c.close()
    colonne = await _une_colonne(portail.base, ids["a"])
    p = await _connexion_du_portail(portail.base, str(portail.ids["site"]["site-a"]))
    try:
        assert await p.fetchval("SELECT plafond_caracteres FROM mark.objet_agent_reglage") == 100
        with pytest.raises(asyncpg.CheckViolationError, match="plafond"):
            async with p.transaction():
                for i in range(10):
                    await p.execute(
                        "INSERT INTO mark.objet_agent_ligne (objet_id, ordre, valeurs) VALUES ($1, $2, $3::jsonb)",
                        ids["a"], 10 + i, json.dumps({str(colonne): f"Une marque de plus {i}"}),
                    )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await p.execute("UPDATE mark.objet_agent_reglage SET plafond_caracteres = 50000")
    finally:
        await p.close()


async def test_la_vue_du_portail_ne_montre_que_les_objets_lus_par_un_agent_rattache(portail):
    ids = await _trois_objets(portail.base)
    c = await _ecriture(portail.base)
    try:
        await c.execute("INSERT INTO mark.agent (dograh_workflow_id, nom) VALUES (501, 'Accueil'), (502, 'Test')")
        await ecrire_utilisation(c, {"marques_a": [501], "frais": [502], "marques_b": [501]})
    finally:
        await c.close()
    a = str(portail.ids["site"]["site-a"])
    p = await _connexion_du_portail(portail.base, a)
    try:
        # Aucun agent rattaché : rien à afficher, même un objet lu par un agent.
        assert await p.fetchval("SELECT count(*) FROM mark.v_portail_objets") == 0
    finally:
        await p.close()
    c = await _ecriture(portail.base)
    try:
        await c.execute("UPDATE mark.agent SET rattache_le = now() WHERE dograh_workflow_id = 501")
    finally:
        await c.close()
    p = await _connexion_du_portail(portail.base, a)
    try:
        lignes = await p.fetch("SELECT * FROM mark.v_portail_objets")
        # marques_b est lu par l'agent rattaché, mais dans un autre lieu ; frais n'est lu que par une copie de test.
        assert [(r["id"], r["utilise_par"]) for r in lignes] == [(ids["a"], ["Accueil"])]
        assert lignes[0]["taille"] > 0 and lignes[0]["plafond_caracteres"] == 3000
        assert lignes[0]["dernier_changement"] is not None and lignes[0]["site_nom"] == "site-a"
    finally:
        await p.close()


# --------------------------------------------------------------------------- #
# 4. L'appel
# --------------------------------------------------------------------------- #


async def test_les_objets_sont_lus_avec_la_fiche_et_rendus_dans_le_contexte(base_prete):
    from api.services.base_client.synchro import lire_depuis_la_base

    c = await _ecriture(base_prete)
    try:
        await ecrire_objet(c, _liste(), AUTEUR)
        await ecrire_objet(c, _valeur(), AUTEUR)
    finally:
        await c.close()
    with patch("api.services.objets_agent.stockage.db_client") as dograh:
        dograh.get_configuration = AsyncMock(return_value=None)
        dograh.upsert_configuration = AsyncMock()
        copie = await lire_depuis_la_base(1, base_prete)
    assert copie.objets_etat == "lu" and sorted(copie.objets_noms) == ["frais", "marques"]
    contexte, estampille = injecter_objets({"frais": "déjà là"}, copie)
    assert contexte["marques"] == "Marque | Prise en charge\nEdilkamin | oui\nRika | non"
    assert contexte["frais"] == "déjà là"  # un rejeu, le pré-appel : gardé
    assert estampille == {"etat": "lu", "poses": ["marques"], "gardes": ["frais"]}
    # Partout où {{nom}} apparaît, par le moteur de toujours.
    assert render_template("Les marques :\n{{marques}}", contexte).endswith("Rika | non")
    # Sans base ou sans objet : rien ne change, pas même l'estampille.
    for etat in ("sans_base", "lu"):
        assert injecter_objets({"x": 1}, SimpleNamespace(objets_etat=etat, objets=[], objets_noms=[])) == ({"x": 1}, None)


async def test_base_injoignable_la_variable_reste_ecrite_et_un_incident_est_note(monkeypatch):
    from datetime import UTC, datetime

    from api.services.etablissements import copie as module_copie

    async def base_rattachee(_org):
        return "mark_essai_absente"

    async def tombe(*_a, **_k):
        raise schema.BaseClientIndisponible("down")

    with (
        patch("api.services.etablissements.stockage.nom_de_la_base_strict", base_rattachee),
        patch("api.services.etablissements.stockage.lire_etablissements", AsyncMock(return_value=module_copie.CatalogueEtablissements())),
        patch("api.services.etablissements.stockage.lire_phrases", AsyncMock(return_value=module_copie.CataloguePhrases())),
        patch("api.services.base_client.synchro.lire_depuis_la_base", tombe),
        patch("api.services.objets_agent.stockage.lire_noms", AsyncMock(return_value=["tarifs"])),
    ):
        copie = await module_copie.lire_source(7)
    assert copie.objets_etat == "injoignable" and copie.objets_noms == ["tarifs"]
    contexte, estampille = injecter_objets({}, copie)
    assert render_template("Tarifs : {{tarifs}}", contexte) == "Tarifs : {{tarifs}}"
    assert estampille == {"etat": "injoignable", "noms": ["tarifs"]}
    incidents = incidents_des_objets({"objets": estampille}, datetime(2026, 10, 22, tzinfo=UTC))
    assert [i["brique"] for i in incidents] == [BRIQUE_INCIDENT]
    assert incidents_des_objets({"objets": {"etat": "lu"}}, datetime.now(UTC)) == []
    assert incidents_des_objets({}, datetime.now(UTC)) == []


def test_utilise_par_trouve_le_nom_et_ses_phrases_jamais_un_autre():
    agents = [
        (1, "Accueil", json.dumps({"prompt": "Voici {{ marques }}"})),
        (2, "Devis", json.dumps({"prompt": "{{marques | aucune}}"})),
        (3, "Fin", json.dumps({"phrase": "{{phrase_des_marques}}"})),
        (4, "Autre", json.dumps({"prompt": "{{marques_saint_maximin}} {{marquesx}}"})),
    ]
    utilisation = agents_qui_lisent(["marques"], agents, {"phrase_des_marques": ["Nous prenons {{marques}}."]})
    assert [a.nom for a in utilisation["marques"]] == ["Accueil", "Devis", "Fin"]


# --------------------------------------------------------------------------- #
# 5. Les routes
# --------------------------------------------------------------------------- #


async def test_les_routes_creent_lisent_reecrivent_et_suppriment_un_objet(base_v4, smtp, db_session, async_session):
    from api.tests.mark.test_ecritures_par_element import RACINE, _garnir, _installer, _rediriger

    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)
            r = await client.post(
                f"{RACINE}/objets",
                json=_liste(etablissement="nord").model_dump(mode="json"),
                headers=entetes,
            )
            assert r.status_code == 200, r.text
            cree = r.json()
            assert cree["taille"] == len("Marque | Prise en charge\nEdilkamin | oui\nRika | non")
            assert cree["etablissement"] == "nord" and cree["utilise_par"] == []
            lue = (await client.get(f"{RACINE}/objets", headers=entetes)).json()
            assert lue["plafond_caracteres"] == 3000 and [o["nom"] for o in lue["objets"]] == ["marques"]
            # Réécrire : la colonne et la ligne envoyées avec leur id restent, l'autre ligne part.
            envoi = {k: cree[k] for k in ObjetEnvoye.model_fields}
            envoi["lignes"] = [cree["lignes"][0]]
            r = await client.put(f"{RACINE}/objets/{cree['id']}", json=envoi, headers=entetes)
            assert r.status_code == 200, r.text
            assert [ligne["valeurs"]["Marque"] for ligne in r.json()["lignes"]] == ["Edilkamin"]
            assert r.json()["colonnes"][0]["id"] == cree["colonnes"][0]["id"]
            # Le plafond, réglé ici, bloque.
            r = await client.put(f"{RACINE}/objets/reglages", json={"plafond_caracteres": 100}, headers=entetes)
            assert r.status_code == 200 and r.json() == {"plafond_caracteres": 100}
            longues = tuple((f"Marque numéro {i}", "oui") for i in range(10))
            r = await client.post(
                f"{RACINE}/objets", json=_liste(nom="longue", lignes=longues).model_dump(mode="json"), headers=entetes
            )
            assert r.status_code == 422 and "plafond" in r.json()["detail"]
            # Un nom pris : 409 ; un type faux : 422 ; un objet inconnu : 404.
            r = await client.post(f"{RACINE}/objets", json=_liste().model_dump(mode="json"), headers=entetes)
            assert r.status_code == 409
            r = await client.post(
                f"{RACINE}/objets", json=_valeur(valeur="douze").model_dump(mode="json"), headers=entetes
            )
            assert r.status_code == 422
            assert (await client.delete(f"{RACINE}/objets/999999", headers=entetes)).status_code == 404
            r = await client.delete(f"{RACINE}/objets/{cree['id']}", headers=entetes)
            assert r.status_code == 200
            assert (await client.get(f"{RACINE}/objets", headers=entetes)).json()["objets"] == []
            # Sans clé : refusé par l'authentification.
            assert (await client.get(f"{RACINE}/objets")).status_code in (401, 403)
    c = await schema.connecter(base_v4)
    try:
        auteurs = {r["auteur"] for r in await c.fetch("SELECT auteur FROM mark.objet_agent_historique")}
        assert auteurs and all("Camille Dupont" in a for a in auteurs)
    finally:
        await c.close()


async def test_la_cle_d_une_autre_organisation_n_atteint_pas_ses_objets(base_v4, smtp, db_session, async_session):
    from api.tests.mark.test_ecritures_par_element import RACINE, _installer, _rediriger

    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    autre = await _organisation(async_session, db_session)
    cle_b = await _cle(db_session, autre.organisation.id, autre.utilisateur.id)
    with _rediriger():
        async with _client() as client:
            r = await client.post(f"{RACINE}/objets", json=_valeur().model_dump(mode="json"), headers=entetes)
            assert r.status_code == 200, r.text
            ident = r.json()["id"]
            b = {"X-API-Key": cle_b}
            # L'autre organisation n'a pas de base : la sienne est absente, celle de A n'est jamais lue.
            assert (await client.get(f"{RACINE}/objets", headers=b)).status_code == 409
            assert (await client.delete(f"{RACINE}/objets/{ident}", headers=b)).status_code == 409
            await db_session.upsert_configuration(
                autre.organisation.id, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": "mark_essai_autre"}
            )
            assert (await client.delete(f"{RACINE}/objets/{ident}", headers=b)).status_code in (404, 503)
            assert [o["id"] for o in (await client.get(f"{RACINE}/objets", headers=entetes)).json()["objets"]] == [ident]
