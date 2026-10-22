"""[.mark] Lot F8 du chantier cloture-code-avant-migration : les modules de l'agent (migration 020, D120 à D122,
M1 à M8, D124).

Chaque test passe par une VRAIE base du client (le rôle du portail se connecte pour de bon, avec son compte),
par la vraie route et la vraie authentification (clé d'API), ou par le vrai registre et les vrais schémas. Il
échoue si la fonctionnalité ne produit rien.

| Test | Ce qu'il prouve |
|---|---|
| registre | ses clés d'agent sont exactement ``CLES_THEME_MODULES`` ; chaque clé existe au schéma, chaque connecteur au catalogue, chaque domaine chez les traducteurs ; seul le planificateur a des réglages terrain (D124), qui existent dans la base |
| interrupteur | défaut du schéma quand la clé manque, « false » en texte éteint ; l'outil d'un module coupé est reconnu, jamais un autre, jamais sans configuration |
| la 020 monte et se rejoue | une base en 19 monte en 20 ; rejouée, la 020 ne casse rien |
| clé déclarée | une valeur sous une clé que le module ne déclare pas est refusée (aucun réglage inventé), même par Dograh |
| historique | création, changement, retrait gardés avec l'auteur ; jamais modifiés, supprimés ni vidés |
| cloisonnement | le portail d'un établissement voit ses valeurs et celles de toute l'entreprise, jamais celles d'un autre ; variable absente = rien ; il change une valeur, jamais un module, une clé ni un catalogue |
| vue du portail | un module s'y montre seulement allumé sur un agent rattaché ET porteur de réglages terrain |
| routes | ``/organizations/modules`` et ``/agents/{id}/modules`` : besoins, traducteur branché, « utilisé par », ``actif`` ; catalogue et agents écrits dans la base ; sans clé 401 ; agent d'une autre organisation 404 |
"""

from __future__ import annotations

import json

import asyncpg
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.modules import ecrire_agents_des_modules, ecrire_catalogue
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.groupe.reglages import CLES_THEME_MODULES
from api.services.modules import registre
from api.services.modules.etat import (
    actif_sur,
    interrupteur_allume,
    outil_d_un_module_coupe,
)
from api.services.modules.lecture import catalogue_pour_la_base
from api.tests.mark.test_agents_servis import (  # noqa: F401  (fixtures)
    _cle,
    _client,
    _groupe_avec_capacites,
    _integration,
    _organisation,
    base_v4,
    smtp,
)
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_base_portail import (  # noqa: F401  (fixtures)
    _connexion_du_portail,
    base_portail,
    portail,
)

AUTEUR = "dograh:essai"
# Un module d'essai qui déclare UNE clé dans le magasin commun : aucun module du registre n'en déclare.
ESSAI = ("module_essai", "Module d'essai", [{"cle": "seuil", "lieu": "module_reglage", "bloc": None, "modifiable": True}])


class _Outil:
    def __init__(self, connecteur):
        self.category = "integration"
        self.definition = {"config": {"connecteur": connecteur, "action": "x"}}


# --------------------------------------------------------------------------- #
# 1. Le registre
# --------------------------------------------------------------------------- #


def test_les_cles_du_registre_sont_celles_du_theme_modules_et_existent_au_schema():
    assert registre.cles_des_modules() == CLES_THEME_MODULES
    champs = WorkflowConfigurationDefaults.model_fields
    for module in registre.MODULES:
        for cle in module.cles_de_l_agent():
            assert cle in champs, (module.code, cle)
        if module.interrupteur:
            assert champs[module.interrupteur].annotation is bool, module.code
    assert len({m.code for m in registre.MODULES}) == len(registre.MODULES)


def test_connecteurs_et_domaines_du_registre_existent():
    from api.services.hub.traducteurs import OBJETS, traducteurs
    from api.services.integrations.connectors.catalogue import connecteur

    # Les deux domaines que le hub sert (réf. 24) : l'agenda (livré : Google, Outlook) et le dossier (format
    # commun posé, aucun traducteur livré : la base du client sert, V4). ``traducteurs_choisis`` les lit tous deux.
    assert {"rendez_vous", "dossier"} <= set(OBJETS)
    assert {t.domaine for t in traducteurs()} <= {"agenda", "dossier"}
    domaines = {"agenda", "dossier"}
    for module in registre.MODULES:
        for nom in module.connecteurs:
            assert connecteur(nom) is not None, (module.code, nom)
        for besoin in module.besoins:
            assert besoin.domaine is None or besoin.domaine in domaines, (module.code, besoin.code)
            assert besoin.domaine or besoin.source_interne, (module.code, besoin.code)
        # Un module sans interrupteur s'allume par ses outils : il en a forcément.
        assert module.interrupteur or module.connecteurs, module.code


def test_seul_le_planificateur_a_des_reglages_terrain_ceux_de_D124():
    avec = {m.code: m for m in registre.MODULES if m.terrain}
    assert list(avec) == ["planificateur"]
    blocs: dict[str, list[str]] = {}
    for r in avec["planificateur"].terrain:
        blocs.setdefault(r.bloc, []).append(r.cle)
    assert blocs == {
        "quand": ["plages", "delai_minimal_h", "jours_feries"],
        "quoi": ["libelle", "duree_min", "marge_avant_min", "marge_apres_min", "actif"],
        "ou": ["zone_communes", "zone_rayon_km", "trajets_comptes"],
        "qui": ["repartition", "personne_visible"],
    }
    assert [r.cle for r in avec["planificateur"].terrain if not r.modifiable] == ["jours_feries"]


async def test_chaque_reglage_d_une_table_existe_dans_la_base(base_prete):
    c = await schema.connecter(base_prete)
    try:
        colonnes = {
            (r["table_name"], r["column_name"])
            for r in await c.fetch(
                "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'mark'"
            )
        }
    finally:
        await c.close()
    for module in registre.MODULES:
        for r in (*module.construction, *module.terrain):
            if r.lieu != registre.AGENT:
                assert (r.lieu, r.cle) in colonnes, (module.code, r.lieu, r.cle)


def test_l_interrupteur_lit_le_defaut_du_schema_et_un_outil_coupe_est_reconnu():
    communes = registre.PAR_CODE["communes_et_voies"]
    equipe = registre.PAR_CODE["equipe"]
    planificateur = registre.PAR_CODE["planificateur"]
    # Absent : le défaut du schéma (communes allumées, équipe éteinte), comme chaque module le lit.
    assert interrupteur_allume(communes, {}) is True
    assert interrupteur_allume(equipe, {}) is False
    assert interrupteur_allume(communes, {"verification_communes": "false"}) is False
    assert interrupteur_allume(equipe, {"equipe_connue": True}) is True
    # L'outil de l'équipe : coupé sans équipe connue, gardé avec ; jamais filtré sans configuration.
    assert outil_d_un_module_coupe(_Outil("equipe"), {}) is True
    assert outil_d_un_module_coupe(_Outil("equipe"), {"equipe_connue": True}) is False
    assert outil_d_un_module_coupe(_Outil("equipe"), None) is False
    assert outil_d_un_module_coupe(_Outil("dossier"), {"verification_appelant": False}) is True
    # Le planificateur n'a pas de clé : ses outils ne sont jamais retirés, ils l'allument.
    assert outil_d_un_module_coupe(_Outil("planificateur"), {}) is False
    assert actif_sur(planificateur, {}, [_Outil("planificateur")]) is True
    assert actif_sur(planificateur, {}, [_Outil("equipe")]) is False


# --------------------------------------------------------------------------- #
# 2. La migration, la clé déclarée, l'historique
# --------------------------------------------------------------------------- #


async def test_une_base_en_version_19_monte_en_20_et_la_020_se_rejoue(base_essai):
    from api.tests.mark.test_base_portail import _appliquer_jusqua, _base_en_version_14

    await _base_en_version_14(base_essai)
    proprietaire = await schema.connecter_proprietaire(base_essai)
    try:
        assert await _appliquer_jusqua(proprietaire, 19) == [15, 16, 17, 18, 19]
        assert await schema.appliquer_migrations(proprietaire) == [20]
        assert await schema.version_de(proprietaire) == 20 == schema.version_attendue()
        await ecrire_catalogue(proprietaire, [*catalogue_pour_la_base(), ESSAI])
        await proprietaire.execute(
            "INSERT INTO mark.module_reglage (module_code, cle, valeur) VALUES ('module_essai', 'seuil', '3')"
        )
        migration = next(m for m in schema.migrations() if m.version == 20)
        corps = migration.sql[: migration.sql.index("INSERT INTO schema_version")]
        async with proprietaire.transaction():
            await proprietaire.execute(corps)
        assert await schema.appliquer_migrations(proprietaire) == []
        assert await proprietaire.fetchval("SELECT count(*) FROM mark.module") == len(registre.MODULES) + 1
        assert await proprietaire.fetchval("SELECT count(*) FROM mark.module_reglage") == 1
    finally:
        await proprietaire.close()


async def test_seule_une_cle_declaree_s_ecrit_et_l_historique_ne_s_efface_jamais(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await ecrire_catalogue(c, [*catalogue_pour_la_base(), ESSAI])
        assert await c.fetchval("SELECT a_reglages_terrain FROM mark.module WHERE code = 'planificateur'") is True
        assert await c.fetchval("SELECT a_reglages_terrain FROM mark.module WHERE code = 'nombres'") is False
        # Aucun réglage inventé : une clé non déclarée, ou une clé du planificateur (dans SES tables), refusée.
        for module, cle in (("module_essai", "autre"), ("planificateur", "plages"), ("nombres", "seuil")):
            with pytest.raises(asyncpg.CheckViolationError):
                await c.execute(
                    "INSERT INTO mark.module_reglage (module_code, cle, valeur) VALUES ($1, $2, '1')", module, cle
                )
        await c.execute("SELECT set_config('mark.auteur', $1, false)", AUTEUR)
        ident = await c.fetchval(
            "INSERT INTO mark.module_reglage (module_code, cle, valeur) VALUES ('module_essai', 'seuil', '3') RETURNING id"
        )
        await c.execute("UPDATE mark.module_reglage SET valeur = '4' WHERE id = $1", ident)
        await c.execute("UPDATE mark.module_reglage SET valeur = '4' WHERE id = $1", ident)  # rien ne change
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute("UPDATE mark.module_reglage SET cle = 'autre' WHERE id = $1", ident)
        await c.execute("DELETE FROM mark.module_reglage WHERE id = $1", ident)
        lignes = await c.fetch("SELECT operation, avant, apres, auteur FROM mark.module_reglage_historique ORDER BY id")
        assert [r["operation"] for r in lignes] == ["insert", "update", "delete"]
        assert {r["auteur"] for r in lignes} == {AUTEUR}
        assert json.loads(lignes[1]["avant"])["valeur"] == 3 and json.loads(lignes[1]["apres"])["valeur"] == 4
        for geste in (
            "UPDATE mark.module_reglage_historique SET auteur = 'x'",
            "DELETE FROM mark.module_reglage_historique",
            "TRUNCATE mark.module_reglage_historique",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await c.execute(geste)
        # Un module qui a gardé des valeurs n'est pas retiré du catalogue quand le registre ne le déclare plus.
        await c.execute("INSERT INTO mark.module_reglage (module_code, cle, valeur) VALUES ('module_essai', 'seuil', '5')")
        await ecrire_catalogue(c, catalogue_pour_la_base())
        assert await c.fetchval("SELECT count(*) FROM mark.module WHERE code = 'module_essai'") == 1
    finally:
        await c.close()


# --------------------------------------------------------------------------- #
# 3. Le portail : cloisonnement, vue
# --------------------------------------------------------------------------- #


async def _trois_valeurs(base, ids):
    c = await schema.connecter(base)
    try:
        await ecrire_catalogue(c, [*catalogue_pour_la_base(), ESSAI])
        for site, valeur in ((ids["site"]["site-a"], "1"), (ids["site"]["site-b"], "2"), (None, "0")):
            await c.execute(
                "INSERT INTO mark.module_reglage (module_code, site_id, cle, valeur) VALUES ('module_essai', $1, 'seuil', $2::jsonb)",
                site, valeur,
            )
    finally:
        await c.close()


async def test_le_portail_ne_voit_que_les_valeurs_de_ses_etablissements(portail):
    await _trois_valeurs(portail.base, portail.ids)
    a, b = portail.ids["site"]["site-a"], portail.ids["site"]["site-b"]
    c = await _connexion_du_portail(portail.base, str(a))
    try:
        vues = {r["site_id"]: r["valeur"] for r in await c.fetch("SELECT site_id, valeur FROM mark.module_reglage")}
        assert vues == {a: "1", None: "0"}
        assert {r["site_id"] for r in await c.fetch("SELECT site_id FROM mark.module_reglage_historique")} == {a, None}
        # Le catalogue se lit en entier ; il ne s'écrit pas.
        assert await c.fetchval("SELECT count(*) FROM mark.module") == len(registre.MODULES) + 1
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute("UPDATE mark.module SET libelle = 'x'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute("INSERT INTO mark.module_agent (module_code, agent_id) VALUES ('nombres', 1)")
        # Il change une valeur ; jamais celle d'un lieu qu'il ne voit pas ; jamais la clé ni le module.
        assert await c.execute("UPDATE mark.module_reglage SET valeur = '7' WHERE site_id = $1", a) == "UPDATE 1"
        assert await c.execute("UPDATE mark.module_reglage SET valeur = '7' WHERE site_id = $1", b) == "UPDATE 0"
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute("UPDATE mark.module_reglage SET cle = 'autre'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):  # sécurité par ligne : le lieu B est hors de vue
            await c.execute(
                "INSERT INTO mark.module_reglage (module_code, site_id, cle, valeur) VALUES ('module_essai', $1, 'seuil', '9')",
                b,
            )
        # Revenir à l'hérité puis reposer, sur son lieu : permis ; l'auteur réel va à l'historique.
        await c.execute("SELECT set_config('mark.auteur', 'portail : Camille', false)")
        await c.execute("DELETE FROM mark.module_reglage WHERE site_id = $1", a)
        await c.execute(
            "INSERT INTO mark.module_reglage (module_code, site_id, cle, valeur) VALUES ('module_essai', $1, 'seuil', '8')", a
        )
        assert await c.fetchval(
            "SELECT count(*) FROM mark.module_reglage_historique WHERE auteur = 'portail : Camille'"
        ) == 2
    finally:
        await c.close()
    for variable in (None, "", "garbage"):
        c = await _connexion_du_portail(portail.base, variable)
        try:
            for table in ("module_reglage", "module_reglage_historique"):
                assert await c.fetchval(f"SELECT count(*) FROM mark.{table}") == 0, (variable, table)
        finally:
            await c.close()


async def test_la_vue_du_portail_ne_montre_qu_un_module_allume_sur_un_agent_rattache_et_porteur_de_terrain(portail):
    c = await schema.connecter(portail.base)
    try:
        await ecrire_catalogue(c, catalogue_pour_la_base())
        await c.execute("INSERT INTO mark.agent (dograh_workflow_id, nom) VALUES (601, 'Accueil'), (602, 'Test')")
        # Le planificateur sur la copie de test, les communes sur l'accueil (sans réglage terrain).
        await ecrire_agents_des_modules(c, {"planificateur": [602], "communes_et_voies": [601], "nombres": []})
    finally:
        await c.close()
    a = str(portail.ids["site"]["site-a"])
    p = await _connexion_du_portail(portail.base, a)
    try:
        assert await p.fetchval("SELECT count(*) FROM mark.v_portail_modules") == 0
        assert await p.fetchval("SELECT count(*) FROM mark.module_agent") == 2
    finally:
        await p.close()
    c = await schema.connecter(portail.base)
    try:
        await c.execute("UPDATE mark.agent SET rattache_le = now()")
        await ecrire_agents_des_modules(c, {"planificateur": [601, 602], "communes_et_voies": [601]})
        await c.execute(
            "INSERT INTO mark.reglage_planificateur (site_id, plages) VALUES ($1, 'Mo-Fr 09:00-12:00')",
            portail.ids["site"]["site-a"],
        )
    finally:
        await c.close()
    p = await _connexion_du_portail(portail.base, a)
    try:
        lignes = await p.fetch("SELECT * FROM mark.v_portail_modules")
        # Les communes sont allumées sur un agent rattaché, mais sans réglage terrain : jamais au portail (M6).
        assert [(r["code"], r["utilise_par"]) for r in lignes] == [("planificateur", ["Accueil", "Test"])]
        assert lignes[0]["dernier_changement"] is not None
        assert [d["cle"] for d in json.loads(lignes[0]["reglages_terrain"])][:2] == ["plages", "delai_minimal_h"]
    finally:
        await p.close()
    # Un autre établissement ne voit pas ce changement-là.
    p = await _connexion_du_portail(portail.base, str(portail.ids["site"]["site-b"]))
    try:
        assert (await p.fetchrow("SELECT dernier_changement FROM mark.v_portail_modules"))["dernier_changement"] is None
    finally:
        await p.close()


# --------------------------------------------------------------------------- #
# 4. Les routes
# --------------------------------------------------------------------------- #


async def test_les_routes_rendent_les_modules_de_l_organisation_et_d_un_agent(base_v4, smtp, db_session, async_session):
    from api.tests.mark.test_ecritures_par_element import _installer, _rediriger

    _user, org, entetes = await _installer(db_session, async_session, base_v4)
    # Le spécialisé porte l'outil du planificateur (fixture) ; l'agenda Google est choisi.
    await db_session.upsert_configuration(org, "TRADUCTEURS", {"agenda": "google_agenda"})
    workflows = {w.name: w.id for w in await db_session.list_workflows_for_model_configuration_migration(org)}
    c = await schema.connecter(base_v4)
    try:
        for nom, ident in workflows.items():
            await c.execute(
                "INSERT INTO mark.agent (dograh_workflow_id, nom) VALUES ($1, $2) ON CONFLICT DO NOTHING", ident, nom
            )
    finally:
        await c.close()
    with _rediriger():
        async with _client() as client:
            r = await client.get("/api/v1/organizations/modules", headers=entetes)
            assert r.status_code == 200, r.text
            modules = {m["code"]: m for m in r.json()["modules"]}
            assert list(modules) == [m.code for m in registre.MODULES]
            planificateur = modules["planificateur"]
            assert planificateur["interrupteur"] is None and planificateur["connecteurs"] == ["planificateur"]
            assert [b["traducteur"]["systeme"] for b in planificateur["besoins"]] == ["google_agenda", "google_agenda"]
            assert len(planificateur["utilise_par"]) == 1
            specialise = planificateur["utilise_par"][0]["id"]
            # La vérification : aucun logiciel choisi, la base du client (source interne) est dite.
            [dossier] = modules["verification_appelant"]["besoins"]
            assert dossier["traducteur"] is None and dossier["source_interne"]["fr"].startswith("Base du client")
            # Les communes sont allumées par défaut sur tous les agents actifs.
            assert len(modules["communes_et_voies"]["utilise_par"]) == len(workflows)
            r = await client.get(f"/api/v1/agents/{specialise}/modules", headers=entetes)
            assert r.status_code == 200, r.text
            actifs = {m["code"]: m["actif"] for m in r.json()["modules"]}
            assert actifs["planificateur"] is True and actifs["equipe"] is False and actifs["communes_et_voies"] is True
            autre = next(i for i in workflows.values() if i != specialise)
            r = await client.get(f"/api/v1/agents/{autre}/modules", headers=entetes)
            assert {m["code"]: m["actif"] for m in r.json()["modules"]}["planificateur"] is False
            # Sans clé : refusé ; un agent d'une autre organisation : introuvable.
            assert (await client.get("/api/v1/organizations/modules")).status_code in (401, 403)
            ailleurs = await _organisation(async_session, db_session)
            cle_b = await _cle(db_session, ailleurs.organisation.id, ailleurs.utilisateur.id)
            r = await client.get(f"/api/v1/agents/{specialise}/modules", headers={"X-API-Key": cle_b})
            assert r.status_code == 404
    c = await schema.connecter(base_v4)
    try:
        assert await c.fetchval("SELECT count(*) FROM mark.module") == len(registre.MODULES)
        planifie = await c.fetch(
            "SELECT a.dograh_workflow_id FROM mark.module_agent ma JOIN mark.agent a ON a.id = ma.agent_id "
            "WHERE ma.module_code = 'planificateur'"
        )
        assert [r["dograh_workflow_id"] for r in planifie] == [specialise]
    finally:
        await c.close()
