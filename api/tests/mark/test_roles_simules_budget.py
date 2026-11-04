"""[.mark] Partie 3, lot 12 (SE-23, M-5 et M-6) : l'appelant simulé et le juge séparés, chacun son interrupteur et son budget du mois.

Vraie base de test (transaction annulée), cerveaux factices : aucun appel à un fournisseur, aucune dépense réelle.

| Test | Ce qu'il prouve |
|---|---|
| défauts | un rôle neuf est ÉTEINT, sans budget ; son nom lui est posé |
| migration | la montée allume les rôles déjà réglés (jamais deux fois), la descente retire les champs et la table |
| interrupteur | un rôle éteint ne construit aucun cerveau : aucun appel au fournisseur |
| dépense suivie | chaque tour est rangé (appels, jetons, coût) dans la ligne du rôle et du mois |
| budget atteint | l'appel suivant est refusé AVANT le fournisseur, avec la phrase précise ; l'autre rôle n'est pas touché |
| prix inconnus | un budget sans prix pour compter refuse, au lieu de ne rien couper |
| cloisonnement | la dépense d'une organisation n'est ni lue ni comptée par une autre ; la route ne montre que la sienne |
| rejeu | le budget atteint arrête la suite comme un plafond de rejeu, avec la cause |
| juge des vrais appels | éteint ou budget atteint : l'appel n'est pas jugé et le run le dit |
| série | un rôle éteint ou au budget atteint refuse la série ; chaque rôle a sa clé jusque dans le sous-processus |
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from api.db import db_client
from api.schemas.appel_simule import ReglagesAppelantSimule, RoleSimule
from api.services.appel_simule import serie as moteur
from api.services.appel_simule.serie import SerieRefusee
from api.services.builder.cerveau import budget_roles, simules
from api.services.builder.cerveau.budget_roles import BudgetDuRole
from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
from api.services.builder.cerveau.reglages import ReglagesCerveau
from api.services.builder.tests_agent import execution
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)
from api.tests.mark.builder_commun import monde  # noqa: F401
from api.tests.mark.test_juge_unifie import _juge, _run, mondes  # noqa: F401 -- le monde simulé du juge

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "a3d9e5b7c142_mark_depense_roles_simules.py"
PRIX = ReglagesCerveau(prix_entree_par_million=10.0, prix_sortie_par_million=10.0)  # un tour factice (100 + 50 jetons) = 0,0015


@pytest.fixture(autouse=True)
def _dans_une_transaction_annulee(request):
    """Les tests asynchrones passent dans la transaction annulée de ``db_session`` : aucun compte ni dépense ne reste en base."""
    import inspect

    if inspect.iscoroutinefunction(request.function) and "test_engine" not in request.fixturenames:
        request.getfixturevalue("db_session")
    yield


@pytest.fixture
def cerveau_branche(monkeypatch):
    """``cerveau_du_role`` avec une clé trouvée et un cerveau factice de trois tours ; rend la liste des cerveaux construits."""
    construits: list[CerveauFactice] = []

    def fabriquer(reglages, cle):
        c = CerveauFactice(*[tour(texte("ok")) for _ in range(3)])
        construits.append(c)
        return c

    monkeypatch.setattr("api.services.appel_simule.serie.cle_d_identifiant", AsyncMock(return_value="cle-factice"))
    monkeypatch.setattr(simules, "fabriquer", fabriquer)
    return construits


async def _organisation(nom):
    return await creer_organisation(db_client, f"org-{nom}-{uuid.uuid4().hex[:8]}")


def _role(nom, **champs):
    reglages = ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="c", identifiant="k", actif=True), juge=RoleSimule(consigne="j", identifiant="k", actif=True)
    )
    return getattr(reglages, nom).model_copy(update=champs)


async def _jouer_un_tour(cerveau):
    return [e async for e in cerveau.tour(systeme="s", messages=[], outils=[])]


# --- les défauts -------------------------------------------------------------------------------------------------------


def test_un_role_neuf_est_eteint_sans_budget_et_porte_son_nom():
    reglages = ReglagesAppelantSimule()
    assert (reglages.appelant.actif, reglages.appelant.budget_mois) == (False, 0.0)
    assert (reglages.juge.actif, reglages.juge.budget_mois) == (False, 0.0)
    assert (reglages.appelant.nom, reglages.juge.nom) == ("appelant", "juge")
    # le nom survit à une copie (les sources sont relues par ``model_copy``) et n'entre jamais dans le JSON enregistré
    assert reglages.juge.model_copy(update={"source": "claude_code"}).nom == "juge"
    assert "nom" not in reglages.model_dump(mode="json")["juge"] and "_nom" not in str(reglages.model_dump(mode="json"))


# --- la migration ------------------------------------------------------------------------------------------------------


def _migration():
    spec = importlib.util.spec_from_file_location("migration_a3d9e5b7c142", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEMA = "lot12_essai_migration"


async def _jouer(test_engine, fonction):
    async with test_engine.connect() as connexion:
        transaction = await connexion.begin()
        try:
            return await connexion.run_sync(fonction)
        finally:
            await transaction.rollback()


def _decor_migration(c, valeurs):
    c.execute(sa.text(f"CREATE SCHEMA {SCHEMA}"))
    c.execute(sa.text(f"SET LOCAL search_path TO {SCHEMA}"))
    c.execute(sa.text("CREATE TABLE organizations (id serial PRIMARY KEY)"))
    c.execute(sa.text("CREATE TABLE organization_configurations (id serial PRIMARY KEY, organization_id int, key varchar, value json)"))
    for i, valeur in enumerate(valeurs, start=1):
        c.execute(sa.text("INSERT INTO organizations (id) VALUES (:i)"), {"i": i})
        c.execute(
            sa.text("INSERT INTO organization_configurations (organization_id, key, value) VALUES (:i, 'APPELANT_SIMULE', CAST(:v AS json))"),
            {"i": i, "v": json.dumps(valeur)},
        )


def _lire_valeurs(c):
    return [r[0] for r in c.execute(sa.text("SELECT value FROM organization_configurations ORDER BY id")).fetchall()]


def _tables(c):
    return set(c.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": SCHEMA}).scalars())


async def test_la_montee_allume_les_roles_deja_regles_une_seule_fois_et_la_descente_rend_tout(test_engine):
    avant = [
        {"appelant": {"modele": "m", "consigne": "c"}, "juge": {"modele": "j", "consigne": "j", "actif": False}, "plafond": 5.0},
        {"appelant": {"modele": "m", "consigne": "c"}},  # un seul rôle écrit
        "pas un objet",
    ]

    def cas(c):
        _decor_migration(c, avant)
        with Operations.context(MigrationContext.configure(c)):
            m = _migration()
            m.upgrade()
            apres_montee = _lire_valeurs(c)
            table = "mark_depense_roles" in _tables(c)
            m.allumer_les_roles(c)  # rejouer le remplissage n'a aucun effet de plus
            rejoue = _lire_valeurs(c)
            posee = json.loads(json.dumps(apres_montee[0]))
            for role in ("appelant", "juge"):
                posee[role]["budget_mois"] = 3.0  # la descente doit aussi retirer le budget
            c.execute(sa.text("UPDATE organization_configurations SET value = CAST(:v AS json) WHERE id = 1"), {"v": json.dumps(posee)})
            m.downgrade()
            return apres_montee, table, rejoue, _lire_valeurs(c), _tables(c)

    montee, table, rejoue, descente, tables = await _jouer(test_engine, cas)
    assert table is True
    assert montee[0]["appelant"]["actif"] is True and montee[0]["juge"]["actif"] is False  # un choix déjà écrit n'est jamais écrasé
    assert montee[1]["appelant"]["actif"] is True and "juge" not in montee[1] and montee[2] == "pas un objet"
    assert rejoue == montee  # idempotent
    assert descente[0] == {"appelant": {"modele": "m", "consigne": "c"}, "juge": {"modele": "j", "consigne": "j"}, "plafond": 5.0}
    assert "mark_depense_roles" not in tables


# --- l'interrupteur ----------------------------------------------------------------------------------------------------


async def test_un_role_eteint_ne_construit_aucun_cerveau(cerveau_branche):
    org = await _organisation("eteint")
    assert await simules.cerveau_du_role(org, _role("juge", actif=False), PRIX) is None
    assert cerveau_branche == []  # rien n'a été construit : aucun appel au fournisseur possible
    assert await simules.cerveau_du_role(org, _role("juge"), PRIX) is not None


# --- la dépense suivie et le budget ----------------------------------------------------------------------------------------


async def test_chaque_tour_est_range_dans_la_depense_du_role_et_du_mois(cerveau_branche):
    org = await _organisation("depense")
    cerveau = await simules.cerveau_du_role(org, _role("appelant"), PRIX)
    await _jouer_un_tour(cerveau)
    await _jouer_un_tour(cerveau)
    depense = await budget_roles.depense_du_mois(org)
    assert depense["appelant"]["appels"] == 2 and depense["appelant"]["jetons"] == 300
    assert depense["appelant"]["cout"] == pytest.approx(0.003)
    assert depense["juge"] == {"appels": 0, "jetons": 0, "cout": 0.0}


async def test_budget_atteint_l_appel_suivant_est_refuse_avant_le_fournisseur_et_l_autre_role_n_est_pas_touche(cerveau_branche):
    org = await _organisation("budget")
    juge = await simules.cerveau_du_role(org, _role("juge", budget_mois=0.001), PRIX)
    await _jouer_un_tour(juge)  # 0,0015 dépensé : le budget de 0,001 est atteint
    with pytest.raises(BudgetDuRole) as refus:
        await _jouer_un_tour(juge)
    assert refus.value.code == "budget_mois" and refus.value.role == "juge"
    assert "The monthly budget of the judge is reached (0.00 of 0.00)" in refus.value.message  # deux décimales
    assert "Labo settings" in refus.value.message
    assert len(cerveau_branche[0].requetes) == 1  # le second tour n'est JAMAIS parti vers le cerveau
    # l'appelant a son propre budget : il joue
    appelant = await simules.cerveau_du_role(org, _role("appelant", budget_mois=1.0), PRIX)
    assert await _jouer_un_tour(appelant)
    # budget 0 = aucun plafond
    sans = await simules.cerveau_du_role(org, _role("juge", budget_mois=0.0), PRIX)
    assert await _jouer_un_tour(sans)


async def test_un_budget_sans_prix_pour_compter_refuse_au_lieu_de_ne_rien_couper(cerveau_branche):
    org = await _organisation("sansprix")
    cerveau = await simules.cerveau_du_role(org, _role("juge", budget_mois=5.0), ReglagesCerveau())
    with pytest.raises(BudgetDuRole, match="needs the model's prices"):
        await _jouer_un_tour(cerveau)
    assert cerveau_branche[0].requetes == []


async def test_le_prix_du_role_vient_de_la_table_des_prix_de_son_modele(monkeypatch):
    from api.services.builder.cerveau import prix

    table = prix.TableDesPrix(modeles=[prix.PrixDUnModele(modele="mistral-small-latest", entree_par_million=1.5, sortie_par_million=4.5)])
    monkeypatch.setattr(prix, "lire", AsyncMock(return_value=table))
    role = RoleSimule(consigne="c", modele="mistral/mistral-small-latest")
    assert await simules.prix_du_role(1, role, PRIX) == (1.5, 4.5)
    autre = RoleSimule(consigne="c", modele="mistral/inconnu")
    assert await simules.prix_du_role(1, autre, PRIX) == (10.0, 10.0)  # repli : les prix des réglages du cerveau


# --- le cloisonnement ----------------------------------------------------------------------------------------------------------


async def test_la_depense_d_une_organisation_n_est_ni_lue_ni_comptee_par_une_autre(cerveau_branche):
    a, b = await _organisation("a"), await _organisation("b")
    cerveau_a = await simules.cerveau_du_role(a, _role("juge", budget_mois=0.001), PRIX)
    await _jouer_un_tour(cerveau_a)
    assert (await budget_roles.depense_du_mois(a))["juge"]["appels"] == 1
    assert (await budget_roles.depense_du_mois(b))["juge"] == {"appels": 0, "jetons": 0, "cout": 0.0}
    cerveau_b = await simules.cerveau_du_role(b, _role("juge", budget_mois=0.001), PRIX)
    assert await _jouer_un_tour(cerveau_b)  # le budget de A atteint ne ferme pas B


async def test_la_route_de_depense_ne_montre_que_l_organisation_de_l_appelant(cerveau_branche):
    a, b = await _organisation("ra"), await _organisation("rb")
    _, jeton_a = await creer_compte(db_client, f"ra{uuid.uuid4().hex[:8]}@example.test", role="Administrateur", organisations=[a])
    _, jeton_b = await creer_compte(db_client, f"rb{uuid.uuid4().hex[:8]}@example.test", role="Administrateur", organisations=[b])
    cerveau = await simules.cerveau_du_role(a, _role("appelant"), PRIX)
    await _jouer_un_tour(cerveau)
    async with client_http() as c:
        vue_a = (await c.get("/api/v1/appel-simule/depense", headers=entetes(jeton_a, a))).json()
        vue_b = (await c.get("/api/v1/appel-simule/depense", headers=entetes(jeton_b, b))).json()
        sans_session = await c.get("/api/v1/appel-simule/depense")
    assert vue_a["appelant"]["appels"] == 1 and vue_a["appelant"]["cout"] == pytest.approx(0.0015)
    assert vue_a["appelant"]["atteint"] is False and vue_a["appelant"]["budget_mois"] == 0
    assert vue_b["appelant"]["appels"] == 0 and vue_b["appelant"]["cout"] == 0
    assert sans_session.status_code in (401, 403)


# --- le rejeu des tests du builder ------------------------------------------------------------------------------------------------


async def test_un_budget_atteint_arrete_le_rejeu_comme_un_plafond_et_dit_la_cause(cerveau_branche):
    org = await _organisation("rejeu")
    brut = await simules.cerveau_du_role(org, _role("appelant", budget_mois=0.001), PRIX)
    compte = execution.CerveauCompte(brut, simules.reglages_du_role(_role("appelant"), PRIX))
    async for _ in compte.tour(systeme="s", messages=[], outils=[]):
        pass
    with pytest.raises(execution.PlafondDuRejeu) as arret:
        async for _ in compte.tour(systeme="s", messages=[], outils=[]):
            pass
    assert arret.value.quoi == "budget_appelant"


# --- le juge des vrais appels ------------------------------------------------------------------------------------------------------


async def test_un_juge_eteint_ou_au_budget_atteint_ne_juge_pas_et_le_run_le_dit(mondes, monkeypatch):  # noqa: F811
    from api.services.juge import appels, file
    from api.tests.mark.builder_commun import AGENT, ORG_CLIENT

    await file.regler(ORG_CLIENT, AGENT, True)
    fabrique = AsyncMock()
    monkeypatch.setattr(simules, "cerveau_du_role", fabrique)
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k", actif=False)
    await appels.apres_appel(_run(), ORG_CLIENT)
    assert mondes.ecrits[-1][1]["juge"]["etat"] == "non_regle" and "switched off" in mondes.ecrits[-1][1]["juge"]["raison"]
    assert fabrique.await_count == 0

    _juge(monkeypatch, modele="openai/juge-m", identifiant="k", actif=True, budget_mois=1.0)
    fabrique.return_value = CerveauFactice()
    monkeypatch.setattr(budget_roles, "depense_du_mois", AsyncMock(return_value={"juge": {"cout": 1.0}, "appelant": {"cout": 0.0}}))
    monkeypatch.setattr(simules, "prix_du_role", AsyncMock(return_value=(1.0, 1.0)))
    await appels.apres_appel(_run(), ORG_CLIENT)
    juge = mondes.ecrits[-1][1]["juge"]
    assert juge["etat"] == "budget_atteint" and "monthly budget of the judge is reached" in juge["raison"]
    assert fabrique.return_value.requetes == []  # aucun tour du cerveau


# --- la série ------------------------------------------------------------------------------------------------------------------------


async def test_une_serie_est_refusee_si_un_role_est_eteint_ou_au_budget_atteint(monkeypatch):
    reglages = ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="c", identifiant="k", actif=True), juge=RoleSimule(consigne="j", identifiant="k", actif=False)
    )
    monkeypatch.setattr(budget_roles, "depense_du_mois", AsyncMock(return_value={"appelant": {"cout": 0.0}, "juge": {"cout": 0.0}}))
    with pytest.raises(SerieRefusee, match="judge is switched off"):
        await moteur._roles_permis(1, reglages)
    reglages.juge.actif = True
    reglages.appelant.budget_mois = 2.0
    monkeypatch.setattr(budget_roles, "depense_du_mois", AsyncMock(return_value={"appelant": {"cout": 2.5}, "juge": {"cout": 0.0}}))
    with pytest.raises(SerieRefusee, match="monthly budget of the simulated caller is reached"):
        await moteur._roles_permis(1, reglages)
    monkeypatch.setattr(budget_roles, "depense_du_mois", AsyncMock(return_value={"appelant": {"cout": 1.0}, "juge": {"cout": 9.0}}))
    await moteur._roles_permis(1, reglages)  # le juge n'a pas de budget : il joue


async def test_chaque_role_a_sa_cle_et_le_sous_processus_recoit_les_deux(monkeypatch):
    cles = {"ka": "SECRET-APPELANT", "kj": "SECRET-JUGE", "kv": "SECRET-VOIX"}
    monkeypatch.setattr(moteur, "cle_d_identifiant", AsyncMock(side_effect=lambda org, i: cles.get(i)))
    reglages = ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="c", identifiant="ka"),
        juge=RoleSimule(consigne="j", identifiant="kj"),
        voix={"voix": "v", "identifiant": "kv"},
    )
    trois = await moteur._cles(1, reglages)
    assert trois == ("SECRET-APPELANT", "SECRET-VOIX", "SECRET-JUGE")
    env = moteur.environnement(trois[0], trois[1], "/tmp/x", cle_juge=trois[2])
    assert env["SIMULATEUR_CLE_MODELE"] == "SECRET-APPELANT" and env["SIMULATEUR_CLE_JUGE"] == "SECRET-JUGE"
    # même clé pour les deux : une seule variable, comme avant
    reglages.juge.identifiant = "ka"
    meme = await moteur._cles(1, reglages)
    assert meme[2] is None and "SIMULATEUR_CLE_JUGE" not in moteur.environnement(meme[0], meme[1], "/tmp/x", cle_juge=meme[2])
    # la clé du juge supprimée se nomme
    reglages.juge.identifiant = "supprimee"
    with pytest.raises(SerieRefusee, match="judge model key .* was deleted or is unusable"):
        await moteur._cles(1, reglages)
    reglages.juge.identifiant = None
    with pytest.raises(SerieRefusee, match="Choose the model key of the judge"):
        await moteur._cles(1, reglages)
