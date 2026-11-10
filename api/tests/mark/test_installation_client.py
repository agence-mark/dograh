"""[.mark] Partie 3, sous-lot 9 (SE-5, § 5 du plan) : « Nouveau client » qui installe vraiment.

| Test | Ce qu'il prouve |
|---|---|
| migration | les deux tables montent et descendent ; une seule installation ouverte par client (contrainte en base) |
| démarrer | le client (organisation, nom) et l'étape 1 ; rejoué sur le même identifiant : la MÊME installation, aucun second client |
| ordre | une étape ne se joue qu'après celles d'avant (faites ou passées) ; une étape nécessaire ne se passe pas |
| sautée | une étape faite est sautée : son exécutant ne tourne pas deux fois |
| double clic | deux requêtes simultanées sur la même étape : une seule exécution |
| coupure | à chaque étape, une coupure laisse l'étape « en cours » ; reprise après le bail, l'exécutant voit ce qu'elle avait produit |
| erreur | arrêt propre : l'étape est « erreur » avec une phrase précise, jamais le texte de l'erreur ; elle se rejoue |
| dépense | l'étape 8 est refusée sans confirmation (montant estimé rendu) ; aucun appel lancé |
| cloisonnement | l'installation d'un client n'est ni lue ni reprise depuis un autre (service, couche de données, route) |
| exécutants | établissements et logiciels rejoués sans doublon ; agent relu avec l'organisation et sa « Principale » ; clé du portail montrée une fois, une seule active, jamais par une clé d'API ; série simulée lancée une fois (réponse enregistrée) |
| permission | chaque route est au registre sous ``clients.creer``, refusée à une clé d'API |
"""

from __future__ import annotations

import asyncio
import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException

from api.db.installation_client_client import InstallationDejaOuverte
from api.services.installation_client import executants, moteur
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import autre_org, org  # noqa: F401

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "e5a1c3f7b2d9_mark_installation_client.py"


def _client(org):
    """Le compte de la personne, dans l'organisation du client (comme l'adresse l'aurait fixée)."""
    org.utilisateur.selected_organization_id = org.organisation.id
    return org.utilisateur


async def _installation(db_session, org, nom="Plomberie Garnier"):
    return await db_session.creer_installation(org.organisation.id, nom, org.utilisateur.id)


def _etat(vue, numero):
    return next(e for e in vue["etapes"] if e["numero"] == numero)["etat"]


class _Faux:
    """Un exécutant enregistré : compte ses appels, peut couper ou échouer."""

    def __init__(self, *, coupe=0, erreur=None, lent=0.0, resultat=None):
        self.appels: list[executants.Contexte] = []
        self.coupe = coupe
        self.erreur = erreur
        self.lent = lent
        self.resultat = resultat or {"fait": True}

    async def __call__(self, ctx):
        self.appels.append(ctx)
        if self.lent:
            await asyncio.sleep(self.lent)
        if self.coupe:
            self.coupe -= 1
            if ctx.noter:
                await ctx.noter({"deja": "produit"})
            raise asyncio.CancelledError()  # le processus s'arrête au milieu de l'étape
        if self.erreur is not None:
            raise self.erreur
        return executants.Sortie(dict(self.resultat))


async def _avancer_jusqu_a(db_session, org, numero, monkeypatch):
    """Passe ou fait (faux exécutants) les étapes 2 à numero-1."""
    user = _client(org)
    for n in range(2, numero):
        faux = _Faux(resultat={"workflow_id": None} if n != 6 else {"workflow_id": org.agent.id})
        monkeypatch.setitem(executants.EXECUTANTS, n, faux)
        await moteur.executer(user, org.organisation.id, n, {}, confirmer=True)


# --- la migration ------------------------------------------------------------------------------------------------------------


def _charger_migration():
    spec = importlib.util.spec_from_file_location("migration_e5a1c3f7b2d9", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEMA = "lot9_essai_migration"


async def test_la_migration_monte_descend_et_ne_garde_qu_une_installation_ouverte(test_engine):
    def cas(c):
        c.execute(sa.text(f"CREATE SCHEMA {SCHEMA}"))
        c.execute(sa.text(f"SET LOCAL search_path TO {SCHEMA}"))
        c.execute(sa.text("CREATE TABLE organizations (id serial PRIMARY KEY)"))
        c.execute(sa.text("INSERT INTO organizations (id) VALUES (1), (2)"))
        with Operations.context(MigrationContext.configure(c)):
            m = _charger_migration()
            m.upgrade()
            montees = _tables(c)
            c.execute(sa.text("INSERT INTO mark_installations_client (organization_id, nom) VALUES (1, 'A')"))
            c.execute(sa.text("INSERT INTO mark_installations_client (organization_id, nom) VALUES (2, 'B')"))
            point = c.begin_nested()
            try:
                c.execute(sa.text("INSERT INTO mark_installations_client (organization_id, nom) VALUES (1, 'A bis')"))
                doublon = True
            except sa.exc.IntegrityError:
                doublon = False
            point.rollback()
            c.execute(sa.text("UPDATE mark_installations_client SET etat = 'terminee' WHERE nom = 'A'"))
            c.execute(sa.text("INSERT INTO mark_installations_client (organization_id, nom) VALUES (1, 'A, seconde')"))
            m.downgrade()
            return montees, doublon, _tables(c)

    async with test_engine.connect() as connexion:
        transaction = await connexion.begin()
        try:
            montees, doublon, apres = await connexion.run_sync(cas)
        finally:
            await transaction.rollback()
    assert {"mark_installations_client", "mark_installations_client_etapes"} <= montees
    assert doublon is False  # deux installations ouvertes pour un client : refusé par la base
    assert not {"mark_installations_client", "mark_installations_client_etapes"} & apres


def _tables(c):
    return set(c.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": SCHEMA}).scalars())


async def test_une_seule_installation_ouverte_par_client(org, db_session):
    premiere = await _installation(db_session, org)
    with pytest.raises(InstallationDejaOuverte):
        await _installation(db_session, org, "Doublon")
    await db_session.terminer_installation(org.organisation.id, premiere["id"])
    seconde = await _installation(db_session, org, "Seconde")
    assert seconde["id"] != premiere["id"]


# --- démarrer ----------------------------------------------------------------------------------------------------------------


async def test_demarrer_cree_le_client_et_rejoue_reprend_la_meme_installation(org, db_session):
    ident = f"client-essai-{uuid.uuid4().hex[:8]}"
    vue = await moteur.demarrer(org.utilisateur, "Plomberie Garnier", ident)
    assert vue["nom"] == "Plomberie Garnier" and vue["etat"] == "ouverte"
    assert _etat(vue, 1) == "faite" and vue["prochaine"] == 2
    client = await db_session.get_organization_by_provider_id(ident)
    assert client.id == vue["organization_id"] and client.id != org.organisation.id
    assert await db_session.is_user_member_of_organization(org.utilisateur.id, client.id)
    # Double clic sur « Créer » (ou réponse perdue) : la même installation, pas un second client.
    rejoue = await moteur.demarrer(org.utilisateur, "Plomberie Garnier", ident)
    assert rejoue["id"] == vue["id"]


async def test_demarrer_sur_un_identifiant_pris_sans_installation_est_refuse(org, db_session, autre_org):
    with pytest.raises(moteur.RefusInstallation) as refus:
        await moteur.demarrer(org.utilisateur, "Autre", autre_org.organisation.provider_id)
    assert refus.value.statut == 409 and refus.value.code == "nom_pris"
    assert set(refus.value.detail()) >= {"code", "fr", "en"}


# --- ordre, sautée -----------------------------------------------------------------------------------------------------------


async def test_les_etapes_se_font_dans_l_ordre(org, db_session, monkeypatch):
    await _installation(db_session, org)
    user = _client(org)
    faux = _Faux()
    monkeypatch.setitem(executants.EXECUTANTS, 3, faux)
    with pytest.raises(moteur.RefusInstallation) as refus:
        await moteur.executer(user, org.organisation.id, 3, {})
    assert refus.value.code == "ordre" and faux.appels == []
    with pytest.raises(moteur.RefusInstallation) as refus:
        await moteur.passer(user, org.organisation.id, 3)
    assert refus.value.code == "ordre"
    vue = await moteur.passer(user, org.organisation.id, 2)
    assert _etat(vue, 2) == "passee"
    resultat = await moteur.executer(user, org.organisation.id, 3, {})
    assert _etat(resultat["installation"], 3) == "faite" and len(faux.appels) == 1
    with pytest.raises(moteur.RefusInstallation) as refus:
        await moteur.passer(user, org.organisation.id, 6)
    assert refus.value.code == "non_passable"


async def test_une_etape_faite_est_sautee(org, db_session, monkeypatch):
    await _installation(db_session, org)
    user = _client(org)
    faux = _Faux()
    monkeypatch.setitem(executants.EXECUTANTS, 2, faux)
    premier = await moteur.executer(user, org.organisation.id, 2, {"nom_base": "client_x"})
    second = await moteur.executer(user, org.organisation.id, 2, {"nom_base": "client_x"})
    assert premier["sautee"] is False and second["sautee"] is True
    assert len(faux.appels) == 1


# --- double clic --------------------------------------------------------------------------------------------------------------


async def test_double_clic_une_seule_execution(org, db_session, monkeypatch):
    await _installation(db_session, org)
    user = _client(org)
    faux = _Faux(lent=0.05)
    monkeypatch.setitem(executants.EXECUTANTS, 2, faux)

    async def un_clic():
        try:
            return await moteur.executer(user, org.organisation.id, 2, {"nom_base": "client_x"})
        except moteur.RefusInstallation as refus:
            return refus

    resultats = await asyncio.gather(un_clic(), un_clic())
    assert len(faux.appels) == 1
    reussis = [r for r in resultats if isinstance(r, dict) and r["sautee"] is False]
    autres = [r for r in resultats if r not in reussis]
    assert len(reussis) == 1 and len(autres) == 1
    autre = autres[0]
    assert (isinstance(autre, moteur.RefusInstallation) and autre.code == "en_cours") or autre["sautee"] is True


# --- coupure et reprise, à chaque étape --------------------------------------------------------------------------------------


@pytest.mark.parametrize("numero", [2, 3, 4, 5, 6, 7, 8, 9])
async def test_reprise_apres_coupure(numero, org, db_session, monkeypatch):
    await _installation(db_session, org)
    await _avancer_jusqu_a(db_session, org, numero, monkeypatch)
    user = _client(org)
    faux = _Faux(coupe=1)
    monkeypatch.setitem(executants.EXECUTANTS, numero, faux)
    with pytest.raises(asyncio.CancelledError):
        await moteur.executer(user, org.organisation.id, numero, {}, confirmer=True)
    assert _etat(await moteur.lire(org.organisation.id), numero) == "en_cours"
    # Tout de suite : l'étape est encore tenue (une autre requête pourrait la jouer), on ne la double pas.
    with pytest.raises(moteur.RefusInstallation) as refus:
        await moteur.executer(user, org.organisation.id, numero, {}, confirmer=True)
    assert refus.value.code == "en_cours" and len(faux.appels) == 1
    # Le bail écoulé : « Reprendre » rejoue l'étape, qui voit ce qu'elle avait déjà produit.
    monkeypatch.setattr(moteur, "BAIL_S", 0)
    await asyncio.sleep(0.01)
    resultat = await moteur.executer(user, org.organisation.id, numero, {}, confirmer=True)
    assert len(faux.appels) == 2 and faux.appels[1].resultat_precedent == {"deja": "produit"}
    if numero == 9:
        assert resultat["installation"]["etat"] == "terminee"
    else:
        assert _etat(resultat["installation"], numero) == "faite"


# --- arrêt propre sur erreur --------------------------------------------------------------------------------------------------


async def test_une_erreur_arrete_l_etape_avec_une_phrase_precise(org, db_session, monkeypatch):
    await _installation(db_session, org)
    user = _client(org)
    monkeypatch.setitem(executants.EXECUTANTS, 2, _Faux(erreur=executants.ErreurEtape("base_prise")))
    resultat = await moteur.executer(user, org.organisation.id, 2, {"nom_base": "client_x"})
    etape = next(e for e in resultat["installation"]["etapes"] if e["numero"] == 2)
    assert etape["etat"] == "erreur" and etape["code_erreur"] == "base_prise"
    assert resultat["echec"]["code"] == "base_prise" and "Choisissez un autre nom" in resultat["echec"]["fr"]
    assert resultat["installation"]["prochaine"] == 2
    # Une panne inattendue : la phrase générique, jamais le texte de l'erreur (qui peut citer une requête ou un secret).
    monkeypatch.setitem(executants.EXECUTANTS, 2, _Faux(erreur=RuntimeError("SELECT secret FROM x")))
    resultat = await moteur.executer(user, org.organisation.id, 2, {"nom_base": "client_x"})
    assert resultat["echec"]["code"] == "inconnue" and "SELECT" not in str(resultat)
    # Corrigée, elle se rejoue.
    monkeypatch.setitem(executants.EXECUTANTS, 2, _Faux())
    resultat = await moteur.executer(user, org.organisation.id, 2, {"nom_base": "client_y"})
    assert resultat["echec"] is None and _etat(resultat["installation"], 2) == "faite"


# --- dépense -----------------------------------------------------------------------------------------------------------------


async def test_l_etape_qui_depense_est_refusee_sans_confirmation(org, db_session, monkeypatch):
    await _installation(db_session, org)
    await _avancer_jusqu_a(db_session, org, 8, monkeypatch)
    user = _client(org)
    faux = _Faux()
    monkeypatch.setitem(executants.EXECUTANTS, 8, faux)
    with pytest.raises(moteur.RefusInstallation) as refus:
        await moteur.executer(user, org.organisation.id, 8, {})
    assert refus.value.statut == 409 and refus.value.code == "confirmation_requise"
    detail = refus.value.detail()
    assert {"scenarios", "montant", "plafond", "devise"} <= set(detail["estimation"])
    assert faux.appels == []  # rien de lancé, rien de dépensé
    vue = await moteur.lire(org.organisation.id)
    assert vue["prochaine"] == 8 and vue["estimation"]["devise"]
    await moteur.executer(user, org.organisation.id, 8, {}, confirmer=True)
    assert len(faux.appels) == 1


# --- cloisonnement -----------------------------------------------------------------------------------------------------------


async def test_l_installation_d_un_client_n_est_ni_lue_ni_reprise_depuis_un_autre(org, autre_org, db_session, monkeypatch, test_client_factory):
    installation_a = await _installation(db_session, org)
    faux = _Faux()
    monkeypatch.setitem(executants.EXECUTANTS, 2, faux)
    user_b = _client(autre_org)
    with pytest.raises(moteur.RefusInstallation) as refus:
        await moteur.lire(autre_org.organisation.id)
    assert refus.value.statut == 404
    with pytest.raises(moteur.RefusInstallation):
        await moteur.executer(user_b, autre_org.organisation.id, 2, {})
    # Même en connaissant l'identifiant de l'installation de A, l'organisation B ne la prend ni ne la lit.
    assert await db_session.prendre_etape(autre_org.organisation.id, installation_a["id"], 2, user_b.id, bail_s=0) is False
    assert await db_session.installation_ouverte(autre_org.organisation.id, installation_id=installation_a["id"]) is None
    assert [i["id"] for i in await db_session.installations_ouvertes([autre_org.organisation.id])] == []
    assert faux.appels == []
    async with test_client_factory(user_b) as client:
        assert (await client.get("/api/v1/installations-client/courante")).status_code == 404
        reponse = await client.post("/api/v1/installations-client/courante/etapes/2", json={"donnees": {"nom_base": "x"}})
        assert reponse.status_code == 404 and reponse.json()["detail"]["code"] == "installation_introuvable"
    assert _etat(await moteur.lire(org.organisation.id), 2) == "a_faire"


# --- les exécutants (routes existantes, réponses enregistrées) ---------------------------------------------------------------


def _contexte(org, installation, donnees, resultat_precedent=None):
    return executants.Contexte(
        user=_client(org), organization_id=org.organisation.id, installation=installation, donnees=donnees, resultat_precedent=resultat_precedent or {}
    )


async def test_etablissements_rejoue_sans_doublon(org, db_session, monkeypatch):
    from api.routes import etablissements as routes
    from api.schemas.etablissements import CatalogueEtablissements, Etablissement

    stock = {"catalogue": CatalogueEtablissements(etablissements=[Etablissement(id="siege", nom="Siège")])}
    ecritures = []

    async def lire(user):
        assert user.selected_organization_id == org.organisation.id
        return stock["catalogue"]

    async def ecrire(request, user):
        ecritures.append([e.id for e in request.etablissements])
        stock["catalogue"] = request
        return request

    monkeypatch.setattr(routes, "get_etablissements", lire)
    monkeypatch.setattr(routes, "save_etablissements", ecrire)
    installation = await _installation(db_session, org)
    donnees = {"etablissements": [{"nom": "Site Nord", "horaires_ouverture": "Lun-Ven 8h-18h"}, {"nom": "Siège"}]}
    sortie = await executants.etablissements(_contexte(org, installation, donnees))
    assert ecritures == [["siege", "site-nord"]] and sortie.resultat["ajoutes"] == ["site-nord"]
    await executants.etablissements(_contexte(org, installation, donnees))
    assert len(ecritures) == 1  # rejoué : rien de doublé, rien d'écrit
    with pytest.raises(executants.ErreurEtape) as erreur:
        await executants.etablissements(_contexte(org, installation, {"etablissements": []}))
    assert erreur.value.code == "etablissement_requis"


async def test_equipe_sans_base_dit_la_base_requise(org, db_session, monkeypatch):
    from api.routes import base_client as routes

    async def sans_base(user):
        raise HTTPException(status_code=409, detail="Attach a client database first: the team lives there.")

    monkeypatch.setattr(routes, "get_equipe", sans_base)
    installation = await _installation(db_session, org)
    with pytest.raises(executants.ErreurEtape) as erreur:
        await executants.equipe(_contexte(org, installation, {"personnes": [{"prenom": "Agnès"}]}))
    assert erreur.value.code == "base_requise"


async def test_logiciels_deja_proposes_ne_sont_pas_doubles(org, db_session, monkeypatch):
    from api.services.integrations.connectors import routes

    proposes = []

    async def proposer(nouvelle, user):
        if nouvelle.connecteur in proposes:
            raise HTTPException(status_code=409, detail="already")
        proposes.append(nouvelle.connecteur)

    monkeypatch.setattr(routes, "post_proposition", proposer)
    installation = await _installation(db_session, org)
    donnees = {"propositions": [{"connecteur": "google_calendar", "compte": "Garnier"}]}
    await executants.logiciels(_contexte(org, installation, donnees))
    sortie = await executants.logiciels(_contexte(org, installation, donnees))
    assert proposes == ["google_calendar"] and sortie.resultat["proposes"] == ["google_calendar"]


async def test_agent_relu_avec_l_organisation_et_sa_principale(org, autre_org, db_session):
    installation = await _installation(db_session, org)
    with pytest.raises(executants.ErreurEtape) as erreur:
        await executants.agent(_contexte(org, installation, {"workflow_id": autre_org.agent.id}))
    assert erreur.value.code == "agent_introuvable"
    with pytest.raises(executants.ErreurEtape) as erreur:
        await executants.agent(_contexte(org, installation, {}))
    assert erreur.value.code == "agent_requis"
    sortie = await executants.agent(_contexte(org, installation, {"workflow_id": org.agent.id}))
    assert sortie.resultat["workflow_id"] == org.agent.id and sortie.resultat["branche"] == "Principale"
    branches = await db_session.lister_les_branches(org.organisation.id, org.agent.id)
    assert [b.est_principale for b in branches] == [True]


async def test_cle_du_portail_montree_une_fois_une_seule_active_jamais_par_une_cle(org, db_session, monkeypatch):
    from api.services.base_client import rattachement

    async def sans_base(organization_id):
        return None

    monkeypatch.setattr(rattachement, "nom_de_la_base", sans_base)
    installation = await _installation(db_session, org)
    premiere = await executants.cle_portail(_contexte(org, installation, {}))
    fiche = premiere.montre["fiche_portail"]
    assert fiche["format"] == "client-portail-mark" and fiche["organisation_id"] == org.organisation.id
    assert fiche["cle_api"]["valeur"] and fiche["base"] is None
    assert fiche["cle_api"]["valeur"] not in str(premiere.resultat)  # rangé : le préfixe, jamais la clé
    # Rejouée après une coupure : la clé jamais montrée est archivée, une seule clé « Portail .mark » reste active.
    seconde = await executants.cle_portail(_contexte(org, installation, {}))
    actives = [c for c in await db_session.get_api_keys_by_organization(org.organisation.id) if c.name == executants.NOM_CLE_PORTAIL and c.is_active]
    assert [c.id for c in actives] == [seconde.resultat["cle_id"]]
    # Jamais par une clé d'API.
    machine = SimpleNamespace(id=org.utilisateur.id, selected_organization_id=org.organisation.id, par_cle_api=True)
    with pytest.raises(executants.ErreurEtape) as erreur:
        await executants.cle_portail(executants.Contexte(user=machine, organization_id=org.organisation.id, installation=installation, donnees={}))
    assert erreur.value.code == "par_une_personne"


async def test_appels_simules_lances_une_fois_sur_reponse_enregistree(org, db_session, monkeypatch):
    from api.routes import appel_simule as routes
    from api.services.appel_simule import reglages
    from api.services.appel_simule.reglages import SerieSimulee

    lancements = []

    async def scenarios(organization_id, workflow_id):
        return [SimpleNamespace(id="s1"), SimpleNamespace(id="s2")]

    async def series(organization_id):
        return []

    async def lancer(workflow_id, request, user):
        lancements.append(request.scenario_ids)
        # Réponse enregistrée (forme de ``SerieSimulee``) : aucun appel joué, aucune dépense.
        return SerieSimulee(id="serie-1", workflow_id=workflow_id, lancee_le="2026-11-05T00:00:00+00:00", lancee_par=user.id, plafond=2.0, cout_estime=None)

    monkeypatch.setattr(reglages, "lire_scenarios", scenarios)
    monkeypatch.setattr(reglages, "lire_series", series)
    monkeypatch.setattr(routes, "lancer_serie_simulee", lancer)
    installation = await _installation(db_session, org)
    installation["etapes"][5]["resultat"] = {"workflow_id": org.agent.id}
    notes = []

    async def noter(resultat):
        notes.append(resultat)

    ctx = _contexte(org, installation, {})
    ctx.noter = noter
    sortie = await executants.appels_simules(ctx)
    assert lancements == [["s1", "s2"]] and sortie.resultat["serie_id"] == "serie-1" and notes
    # Rejouée après une coupure (la série était notée) : rien de relancé.
    rejouee = await executants.appels_simules(_contexte(org, installation, {}, resultat_precedent=notes[0]))
    assert lancements == [["s1", "s2"]] and rejouee.resultat["serie_id"] == "serie-1"


# --- permission ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "methode,chemin",
    [
        ("POST", "/installations-client"),
        ("GET", "/installations-client/ouvertes"),
        ("GET", "/installations-client/courante"),
        ("POST", "/installations-client/courante/etapes/{numero}"),
        ("POST", "/installations-client/courante/etapes/{numero}/passer"),
    ],
)
def test_chaque_route_exige_clients_creer_jamais_par_une_cle(methode, chemin):
    from api.services.equipe_mark.acces import PERMISSIONS_JAMAIS_PAR_CLE
    from api.services.equipe_mark.registre_routes import Permission, decision_de

    decision, _ = decision_de(methode, chemin)
    assert decision == Permission("clients.creer")
    assert "clients.creer" in PERMISSIONS_JAMAIS_PAR_CLE


async def test_la_route_demarre_et_rend_un_refus_en_phrase(org, db_session, test_client_factory):
    ident = f"client-route-{uuid.uuid4().hex[:8]}"
    async with test_client_factory(org.utilisateur) as client:
        reponse = await client.post("/api/v1/installations-client", json={"nom": "Garnier", "identifiant": ident})
        assert reponse.status_code == 201, reponse.text
        vue = reponse.json()
        assert vue["prochaine"] == 2 and [e["numero"] for e in vue["etapes"]] == list(range(1, 10))
        refus = await client.post("/api/v1/installations-client", json={"nom": "X", "identifiant": "AB"})
        assert refus.status_code == 422
    org.utilisateur.selected_organization_id = vue["organization_id"]
    async with test_client_factory(org.utilisateur) as client:
        reponse = await client.post("/api/v1/installations-client/courante/etapes/6/passer")
        assert reponse.status_code == 422 and reponse.json()["detail"]["code"] == "non_passable"
        assert set(reponse.json()["detail"]) == {"code", "fr", "en"}
        assert (await client.get("/api/v1/installations-client/courante")).json()["id"] == vue["id"]


async def test_une_faute_de_saisie_d_une_route_est_rendue_sous_le_champ_jamais_un_autre_texte(org, db_session, monkeypatch):
    """Constaté à l'écran (05/11) : des horaires « Lun-Ven 8h-18h » refusés par la vraie route ; la fenêtre doit dire pourquoi."""
    from api.routes import etablissements as routes
    from api.schemas.etablissements import CatalogueEtablissements

    async def lire(user):
        return CatalogueEtablissements(etablissements=[])

    async def refuser(request, user):
        raise HTTPException(status_code=422, detail=[{"msg": "Atelier : ligne 1 : il manque « : »", "loc": ["body", "etablissements", 0, "horaires_ouverture"]}])

    monkeypatch.setattr(routes, "get_etablissements", lire)
    monkeypatch.setattr(routes, "save_etablissements", refuser)
    await _installation(db_session, org)
    user = _client(org)
    await moteur.passer(user, org.organisation.id, 2)
    resultat = await moteur.executer(user, org.organisation.id, 3, {"etablissements": [{"nom": "Atelier", "horaires_ouverture": "Lun-Ven"}]})
    assert resultat["echec"]["code"] == "etablissements_refuses"
    assert resultat["echec"]["precisions"] == ["Atelier : ligne 1 : il manque « : »"]

    async def panne(request, user):
        raise HTTPException(status_code=503, detail="connection to 10.0.0.3 refused: SELECT secret")

    monkeypatch.setattr(routes, "save_etablissements", panne)
    resultat = await moteur.executer(user, org.organisation.id, 3, {"etablissements": [{"nom": "Atelier"}]})
    assert resultat["echec"]["code"] == "base_injoignable" and resultat["echec"]["precisions"] == []
    assert "SELECT" not in str(resultat)


async def test_un_groupe_se_cree_dans_l_espace_d_un_client_dont_la_principale_est_protegee(org, autre_org, db_session, test_client_factory, monkeypatch):
    """Constaté à l'écran (05/11, étape 6) : « Créer le groupe » répondait 409 chez un client, la configuration du groupe étant
    écrite dans un brouillon juste après la première version (principale protégée, SA-L3c). Elle part désormais avec la création."""
    from api.services.groupe.groupe import CLE_AGENTS_SPECIALISES, CLE_PLAFOND

    monkeypatch.setattr("api.services.builder.constantes.organisation_bibliotheque", lambda: autre_org.organisation.id)
    async with test_client_factory(_client(org)) as client:
        reponse = await client.post("/api/v1/workflow/groupe", json={"name": "Accueil du client"})
    assert reponse.status_code == 200, reponse.text
    agent = await db_session.get_workflow(reponse.json()["workflow_id"], organization_id=org.organisation.id)
    assert agent.workflow_configurations[CLE_AGENTS_SPECIALISES] == [] and CLE_PLAFOND in agent.workflow_configurations
    assert agent.folder_id == reponse.json()["folder_id"]


def test_l_etape_agent_ne_parle_pas_de_recette():
    """Clôture SA-5 (Evan, 09/11) : « pas de recette en dur, ce sont des éléments de la bibliothèque » : l'étape se nomme « L'agent »."""
    from api.services.installation_client.etapes import etape

    titre = etape(6).titre
    assert titre == {"fr": "L'agent", "en": "The agent"}
    assert "recette" not in titre["fr"].lower() and "recipe" not in titre["en"].lower()
