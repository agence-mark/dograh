"""[.mark] cloture-code, F-8 (règle d'Evan du 22/10) : un établissement a ses propres règles complètes.

Aucune valeur n'est héritée de l'organisation ; la valeur commune préremplit seulement un nouvel
établissement (et sert aux appels qui n'en servent aucun). Les sept mécanismes :

| # | Mécanisme | Où c'est prouvé |
|---|---|---|
| 1 | règles du planificateur | ``lire`` du vrai planificateur sur une vraie base : servi sans règle = défauts du code |
| 2 | fenêtre du tour de rôle | même ligne, même lecture (``fenetre_equite_jours``) |
| 3 | types de rendez-vous | ``lire`` : servi = ses types seuls ; sans établissement = ceux de l'organisation |
| 4 | réglages terrain des modules | la base : préremplissage et 021 (aucun lecteur dans le code : aucun module ne déclare de clé) |
| 5 | catalogue des phrases | ``valeurs_des_phrases`` (et le clavier dans ``test_etablissements_heritage.py``) |
| 6 | horaires et adresse servis par Dograh | ``configuration_heritee`` (et le clavier) |
| 7 | annonces de fermeture et de pause | ``annonce_heritee`` |

Et : la création (la route de Dograh, l'écriture dans la base), la migration 021 (version 20 -> 21,
valeur posée intacte, second passage sans effet), le script de Dograh (à blanc, réel, second passage),
et la preuve du zéro changement au téléphone pour un client existant (ce qu'il lisait avant la règle,
oracle écrit en clair, = ce qu'il lit après le script).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import etablissements as route_etablissements
from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture
from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.schemas.organization_preferences import AdresseEtablissement, OrganizationPreferences
from api.schemas.phrases import CataloguePhrases, Phrase
from api.schemas.planificateur import DEFAUTS
from api.services.auth.depends import get_user_with_selected_organization
from api.services.communes.adresse import _adresse_de, resoudre_adresse
from api.services.etablissements import reprise as module_reprise
from api.services.etablissements import stockage as module_stockage
from api.services.etablissements.appel import annonce_heritee, configuration_heritee
from api.services.etablissements.complets import (
    nouveaux_preremplis,
    plan_complets,
    preremplir,
)
from api.services.etablissements.phrases import valeurs_des_phrases
from api.services.etablissements.reprise import AgentVu
from api.services.planificateur import action as module_action
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_etablissements_heritage import CREIL, HORAIRES_AGENT, HORAIRES_CREIL

ORGANISATION = 11
ADRESSE_ORG = AdresseEtablissement(code_postal="60300", code_insee="60612", commune="Senlis")
ADRESSE_AGENT = {"code_postal": "60100", "code_insee": "60175", "commune": "Creil"}
ANNONCE_ORG = ReglagesAnnonceOuverture()  # its default sentences: what a client hears today
PHRASES = CataloguePhrases(
    phrases=[
        Phrase(variable="phrase_acces", description="Accès", contenu="En centre-ville.", niveau="etablissement"),
        Phrase(variable="phrase_rgpd", description="Mention", contenu="Vos données restent chez nous.", niveau="organisation"),
    ]
)
NUMERO_NORD = "+33344000011"
NUMERO_SUD = "+33344000012"
NORD = Etablissement(id="nord", nom="Nord", numeros=[NUMERO_NORD])  # nothing of its own
SUD = Etablissement(
    id="sud",
    nom="Sud",
    numeros=[NUMERO_SUD],
    horaires_ouverture=HORAIRES_CREIL,
    adresse=ADRESSE_AGENT,
    annonce_fermeture="Sud est fermé.",
    phrases={"phrase_acces": "Derrière la gare."},
)


def _agent(identifiant, nom, numeros, **configurations):
    return AgentVu(id=identifiant, nom=nom, numeros=numeros, configurations=dict(configurations))


# --------------------------------------------------------------------------- #
# 5, 6, 7 : ce qu'un appel lit (pur) -- servi sans valeur, servi avec, sans établissement
# --------------------------------------------------------------------------- #


def test_6_horaires_et_adresse_de_l_etablissement_seul():
    agent = {"horaires_ouverture": HORAIRES_AGENT, "adresse_etablissement": ADRESSE_AGENT}
    vide, origines = configuration_heritee(agent, NORD)
    assert "horaires_ouverture" not in vide and resoudre_adresse(vide, OrganizationPreferences(adresse_etablissement=ADRESSE_ORG)) is None
    assert origines == {"horaires_ouverture": "aucune", "adresse": "aucune"}
    plein, origines = configuration_heritee(agent, SUD)
    assert plein["horaires_ouverture"] == HORAIRES_CREIL and origines["adresse"] == "etablissement"
    sans, origines = configuration_heritee(agent, None)
    assert sans is agent and origines == {}
    assert resoudre_adresse(sans, OrganizationPreferences(adresse_etablissement=ADRESSE_ORG)).commune == "Creil"


def test_7_annonces_de_l_etablissement_seules():
    vide = annonce_heritee(ANNONCE_ORG, NORD)
    assert (vide.annonce_fermeture, vide.annonce_pause) == ("", "")
    assert annonce_heritee(ANNONCE_ORG, SUD).annonce_fermeture == "Sud est fermé."
    assert annonce_heritee(ANNONCE_ORG, None) is ANNONCE_ORG


def test_5_phrases_de_l_etablissement_seules():
    assert valeurs_des_phrases(PHRASES, NORD) == {"phrase_rgpd": "Vos données restent chez nous."}
    assert valeurs_des_phrases(PHRASES, SUD)["phrase_acces"] == "Derrière la gare."
    assert valeurs_des_phrases(PHRASES, None)["phrase_acces"] == "En centre-ville."


# --------------------------------------------------------------------------- #
# Création côté Dograh : préremplissage (pur) et la vraie route
# --------------------------------------------------------------------------- #


def test_un_nouvel_etablissement_recoit_les_valeurs_communes_jamais_sur_une_valeur_posee():
    rempli = preremplir(NORD, ADRESSE_ORG, ANNONCE_ORG, PHRASES)
    assert rempli.adresse == ADRESSE_ORG
    assert (rempli.annonce_fermeture, rempli.annonce_pause) == (ANNONCE_ORG.annonce_fermeture, ANNONCE_ORG.annonce_pause)
    assert rempli.phrases == {"phrase_acces": "En centre-ville."}  # the organization-level one is not a field of it
    assert rempli.horaires_ouverture is None  # no common hours in Dograh: nothing to copy
    garde = preremplir(SUD, ADRESSE_ORG, ANNONCE_ORG, PHRASES)
    assert garde.adresse.commune == "Creil" and garde.annonce_fermeture == "Sud est fermé."
    assert garde.phrases == {"phrase_acces": "Derrière la gare."}
    assert garde.annonce_pause == ANNONCE_ORG.annonce_pause  # its empty field only
    # Nothing common: the SAME object.
    assert preremplir(NORD, None, ReglagesAnnonceOuverture(annonce_fermeture="", annonce_pause=""), None) is NORD


def test_seuls_les_etablissements_nouveaux_sont_preremplis():
    avant = CatalogueEtablissements(etablissements=[NORD])
    apres = CatalogueEtablissements(etablissements=[NORD, Etablissement(id="est", nom="Est")])
    resultat = nouveaux_preremplis(avant, apres, ADRESSE_ORG, ANNONCE_ORG, PHRASES)
    assert resultat.etablissements[0] == NORD  # existing: never prefilled again (it lives its own life)
    assert resultat.etablissements[1].adresse == ADRESSE_ORG
    assert nouveaux_preremplis(avant, avant, ADRESSE_ORG, ANNONCE_ORG, PHRASES) is avant


def _put(corps, catalogue_lu):
    app = FastAPI()
    app.include_router(route_etablissements.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, provider_id="p", selected_organization_id=ORGANISATION, email="essai@exemple.invalid"
    )
    with (
        patch.object(route_etablissements, "db_client") as base,
        patch.object(route_etablissements, "enregistrer_etablissements", AsyncMock(side_effect=lambda _o, c, _a="dograh", **_k: c)) as ecrit,
        patch.object(route_etablissements, "lire_phrases_strict", AsyncMock(return_value=PHRASES)),
        patch.object(module_stockage, "lire_etablissements_strict", AsyncMock(return_value=catalogue_lu)),
        patch.object(module_stockage, "lire_phrases_strict", AsyncMock(return_value=PHRASES)),
        patch("api.services.annonce.stockage.lire_annonce_ouverture_strict", AsyncMock(return_value=ANNONCE_ORG)),
        patch(
            "api.services.organization_preferences.get_organization_preferences",
            AsyncMock(return_value=OrganizationPreferences(adresse_etablissement=ADRESSE_ORG)),
        ),
    ):
        base.lister_numeros_de_lorganisation = AsyncMock(return_value=[(NUMERO_NORD, None, None, None, True)])
        return TestClient(app).put("/organizations/etablissements", json=corps), ecrit


def test_la_route_d_enregistrement_preremplit_un_nouvel_etablissement_et_pas_les_autres():
    corps = CatalogueEtablissements(etablissements=[NORD, Etablissement(id="est", nom="Est")]).model_dump(mode="json")
    reponse, ecrit = _put(corps, CatalogueEtablissements(etablissements=[NORD]))
    assert reponse.status_code == 200, reponse.text
    (_org, ecrits, _auteur), _ = ecrit.await_args
    nord, est = ecrits.etablissements
    assert nord.annonce_fermeture is None and nord.phrases == {} and nord.adresse is None  # already known: untouched
    assert est.annonce_fermeture == ANNONCE_ORG.annonce_fermeture
    assert est.adresse.commune == "Senlis" and est.phrases == {"phrase_acces": "En centre-ville."}


# --------------------------------------------------------------------------- #
# La base du client : création, appel (1 à 4), migration 021
# --------------------------------------------------------------------------- #


async def _valeurs_communes(connexion) -> None:
    """L'organisation règle tout : planificateur (avec la fenêtre), deux types, une phrase au niveau de
    l'établissement, un module qui déclare un réglage terrain et sa valeur commune."""
    from api.db.bases_clients.planificateur import ecrire_planificateur
    from api.db.bases_clients.referentiel import ecrire_phrases
    from api.schemas.planificateur import Planificateur, ReglagesPlanificateur, TypeRendezVous

    await connexion.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('E')")
    await ecrire_planificateur(connexion, Planificateur(
        reglages=ReglagesPlanificateur(nombre_creneaux=2, repartition="tour_de_role", fenetre_equite_jours=45),
        types=[TypeRendezVous(code="visite", libelle="Visite", duree_min=60),
               TypeRendezVous(code="examen", libelle="Examen", duree_min=30)],
    ), "test")
    await ecrire_phrases(connexion, PHRASES, "test")
    await connexion.execute(
        "INSERT INTO mark.module (code, libelle, reglages_terrain) VALUES ('essai', 'Essai', $1::jsonb)",
        json.dumps([{"cle": "seuil", "lieu": "module_reglage"}]),
    )
    await connexion.execute("INSERT INTO mark.module_reglage (module_code, site_id, cle, valeur) VALUES ('essai', NULL, 'seuil', '5')")


async def _du_lieu(connexion, cle: str) -> dict:
    site = await connexion.fetchval("SELECT id FROM mark.site WHERE cle = $1", cle)
    regle = await connexion.fetchrow("SELECT * FROM mark.reglage_planificateur WHERE site_id = $1", site)
    return {
        "reglages": dict(regle) if regle else None,
        "types": {r["code"]: r["duree_min"] for r in await connexion.fetch(
            "SELECT code, duree_min FROM mark.type_rendez_vous WHERE site_id = $1", site)},
        "modules": {r["cle"]: json.loads(r["valeur"]) for r in await connexion.fetch(
            "SELECT cle, valeur FROM mark.module_reglage WHERE site_id = $1", site)},
        "phrases": {r["variable"]: r["contenu"] for r in await connexion.fetch(
            "SELECT variable, contenu FROM mark.phrase_site WHERE site_id = $1", site)},
    }


async def test_1_a_5_un_lieu_cree_par_dograh_est_prerempli_puis_vit_sa_vie(base_prete):  # noqa: F811
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.referentiel import ecrire_etablissements

    connexion = await schema.connecter(base_prete)
    try:
        await _valeurs_communes(connexion)
        await ecrire_etablissements(connexion, CatalogueEtablissements(etablissements=[NORD]), "dograh:essai")
        nord = await _du_lieu(connexion, "nord")
        assert (nord["reglages"]["nombre_creneaux"], nord["reglages"]["repartition"], nord["reglages"]["fenetre_equite_jours"]) == (
            2, "tour_de_role", 45)
        assert nord["types"] == {"visite": 60, "examen": 30}
        assert nord["modules"] == {"seuil": 5}
        assert nord["phrases"] == {"phrase_acces": "En centre-ville."}
        assert await connexion.fetchval(
            "SELECT count(*) FROM mark.journal_modif WHERE table_nom = 'type_rendez_vous' AND champ = 'insert' "
            "AND auteur = 'dograh:essai' AND apres ->> 'site_id' IS NOT NULL") == 2  # journalled, by Dograh
        # Then it lives its own life: the organization changes, a second save of the fiche adds nothing.
        await connexion.execute("UPDATE mark.reglage_planificateur SET nombre_creneaux = 6 WHERE site_id IS NULL")
        await connexion.execute("DELETE FROM mark.type_rendez_vous WHERE code = 'examen' AND site_id IS NOT NULL")
        await ecrire_etablissements(connexion, CatalogueEtablissements(etablissements=[NORD]), "dograh:essai")
        apres = await _du_lieu(connexion, "nord")
        assert apres["reglages"]["nombre_creneaux"] == 2 and apres["types"] == {"visite": 60}
        # A copy (or the transfer into a new database) takes nothing common.
        await ecrire_etablissements(
            connexion, CatalogueEtablissements(etablissements=[NORD, Etablissement(id="copie", nom="Copie")]),
            "dograh:essai", preremplir=False)
        assert await _du_lieu(connexion, "copie") == {"reglages": None, "types": {}, "modules": {}, "phrases": {}}
    finally:
        await connexion.close()


async def _lire_pour(base, monkeypatch, etablissement: str | None):
    """Le VRAI ``lire`` du planificateur (celui des deux actions), l'établissement servi choisi."""
    servi = SimpleNamespace(etablissement=SimpleNamespace(id=etablissement)) if etablissement else None
    monkeypatch.setattr("api.services.hub.choix.lire_choix", AsyncMock(return_value=SimpleNamespace(agenda="essai")))
    monkeypatch.setattr("api.services.base_client.rattachement.nom_de_la_base", AsyncMock(return_value=base))
    monkeypatch.setattr(module_action, "_etablissement_servi", AsyncMock(return_value=servi))
    lecture, _choisi, types = await module_action.lire(SimpleNamespace(organization_id=ORGANISATION, run_id=None, appel={}), None)
    return lecture.reglages, sorted(t.code for t in types)


async def test_1_2_3_l_appel_lit_les_regles_et_les_types_du_lieu_servi_seuls(base_prete, monkeypatch):  # noqa: F811
    from api.db.bases_clients import connexion as schema

    connexion = await schema.connecter(base_prete)
    try:
        await _valeurs_communes(connexion)
        # « nord » and « sud » created by hand (no prefill): « nord » has nothing, « sud » its own.
        await connexion.execute("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'nord', 'Nord' FROM mark.entreprise")
        await connexion.execute("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'sud', 'Sud' FROM mark.entreprise")
        sud = await connexion.fetchval("SELECT id FROM mark.site WHERE cle = 'sud'")
        await connexion.execute(
            "INSERT INTO mark.reglage_planificateur (site_id, nombre_creneaux, fenetre_equite_jours) VALUES ($1, 4, 7)", sud)
        await connexion.execute(
            "INSERT INTO mark.type_rendez_vous (code, site_id, libelle, duree_min) VALUES ('visite', $1, 'Visite longue', 90)", sud)
    finally:
        await connexion.close()
    reglages, types = await _lire_pour(base_prete, monkeypatch, "nord")
    assert (reglages.nombre_creneaux, reglages.repartition, reglages.fenetre_equite_jours) == (
        DEFAUTS.nombre_creneaux, DEFAUTS.repartition, DEFAUTS.fenetre_equite_jours)  # the defaults, not 2 / tour_de_role / 45
    assert types == []  # never the organization's
    reglages, types = await _lire_pour(base_prete, monkeypatch, "sud")
    assert (reglages.nombre_creneaux, reglages.repartition, reglages.fenetre_equite_jours) == (4, DEFAUTS.repartition, 7)
    assert types == ["visite"]
    reglages, types = await _lire_pour(base_prete, monkeypatch, None)  # no establishment: as before
    assert (reglages.nombre_creneaux, reglages.repartition, reglages.fenetre_equite_jours) == (2, "tour_de_role", 45)
    assert types == ["examen", "visite"]


async def test_la_021_complete_les_lieux_existants_sans_toucher_une_valeur_posee_et_se_rejoue_sans_effet(base_prete):  # noqa: F811
    from api.db.bases_clients import connexion as schema

    connexion = await schema.connecter_proprietaire(base_prete)
    try:
        # Back to version 20 (what a client database not yet upgraded is), with the common values.
        await connexion.execute("DROP FUNCTION mark.preremplir_etablissement(bigint)")
        await connexion.execute("DELETE FROM mark.schema_version WHERE version >= 21")
        assert await schema.version_de(connexion) == 20
        await _valeurs_communes(connexion)
        await connexion.execute("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'nord', 'Nord' FROM mark.entreprise")
        await connexion.execute("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'sud', 'Sud' FROM mark.entreprise")
        sud = await connexion.fetchval("SELECT id FROM mark.site WHERE cle = 'sud'")
        await connexion.execute("INSERT INTO mark.reglage_planificateur (site_id, nombre_creneaux) VALUES ($1, 4)", sud)
        await connexion.execute(
            "INSERT INTO mark.type_rendez_vous (code, site_id, libelle, duree_min) VALUES ('visite', $1, 'Visite longue', 90)", sud)
        await connexion.execute("INSERT INTO mark.phrase_site (variable, site_id, contenu) VALUES ('phrase_acces', $1, 'Derrière la gare.')", sud)
        await connexion.execute("INSERT INTO mark.module_reglage (module_code, site_id, cle, valeur) VALUES ('essai', $1, 'seuil', '9')", sud)

        assert await schema.appliquer_migrations(connexion) == [21]
        assert await schema.version_de(connexion) == schema.version_attendue() == 21
        nord = await _du_lieu(connexion, "nord")
        assert (nord["reglages"]["nombre_creneaux"], nord["reglages"]["repartition"], nord["reglages"]["fenetre_equite_jours"]) == (
            2, "tour_de_role", 45)
        assert nord["types"] == {"visite": 60, "examen": 30}
        assert nord["modules"] == {"seuil": 5} and nord["phrases"] == {"phrase_acces": "En centre-ville."}
        sud_lu = await _du_lieu(connexion, "sud")
        assert (sud_lu["reglages"]["nombre_creneaux"], sud_lu["reglages"]["repartition"]) == (4, "tour_de_role")  # its 4 kept
        assert sud_lu["types"] == {"visite": 90, "examen": 30}  # its own « visite » kept, the missing one added
        assert sud_lu["phrases"] == {"phrase_acces": "Derrière la gare."} and sud_lu["modules"] == {"seuil": 9}
        journal = await connexion.fetchval(
            "SELECT count(*) FROM mark.journal_modif WHERE auteur = 'migration 021-etablissements-complets'")
        # Journalled as usual, the migration as author: nord (rules, two types, a sentence), sud (rules, a type).
        assert journal == 6
        assert await connexion.fetchval(
            "SELECT count(*) FROM mark.module_reglage_historique WHERE auteur = 'migration 021-etablissements-complets'") == 1

        # A second pass (the whole file replayed) writes nothing.
        avant = {c: await _du_lieu(connexion, c) for c in ("nord", "sud")}
        lignes = await connexion.fetchval("SELECT count(*) FROM mark.journal_modif")
        sql = next(m.sql for m in schema.migrations() if m.version == 21)
        async with connexion.transaction():
            await connexion.execute(sql)
        assert {c: await _du_lieu(connexion, c) for c in ("nord", "sud")} == avant
        assert await connexion.fetchval("SELECT count(*) FROM mark.journal_modif") == lignes
        assert await connexion.fetchval(
            "SELECT sum(mark.preremplir_etablissement(id)) FROM mark.site WHERE cle IS NOT NULL") == 0
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# Le script de Dograh : à blanc, réel, second passage ; zéro changement au téléphone
# --------------------------------------------------------------------------- #


class _Organisation:
    """Le stockage d'une organisation, en mémoire : le catalogue qu'on lit, ce qu'on écrit."""

    def __init__(self, catalogue, agents):
        self.catalogue = catalogue
        self.agents = agents
        self.ecrits = []

    async def _enregistrer(self, _org, catalogue, auteur="dograh", **_options):
        self.ecrits.append((catalogue, auteur))
        self.catalogue = catalogue
        return catalogue

    async def traiter(self, ecrire: bool):
        from api.scripts.mark import etablissements_complets as script

        async def lire(_org):
            return self.catalogue

        async def agents(_org):
            return self.agents

        with (
            patch.object(module_stockage, "lire_etablissements_strict", lire),
            patch.object(module_stockage, "lire_phrases_strict", AsyncMock(return_value=PHRASES)),
            patch.object(module_stockage, "enregistrer_etablissements", self._enregistrer),
            patch.object(module_reprise, "lire_agents", agents),
            patch("api.services.annonce.stockage.lire_annonce_ouverture_strict", AsyncMock(return_value=ANNONCE_ORG)),
            patch(
                "api.services.organization_preferences.get_organization_preferences",
                AsyncMock(return_value=OrganizationPreferences(adresse_etablissement=ADRESSE_ORG)),
            ),
        ):
            return await script.traiter_organisation(ORGANISATION, ecrire)


def _monde():
    return _Organisation(
        CatalogueEtablissements(etablissements=[NORD, SUD]),
        [
            _agent(6, "Accueil nord", [NUMERO_NORD], horaires_ouverture=HORAIRES_AGENT),
            _agent(7, "Accueil sud", [NUMERO_SUD]),
        ],
    )


@pytest.mark.asyncio
async def test_le_script_a_blanc_compte_sans_ecrire_puis_ecrit_puis_ne_trouve_plus_rien():
    monde = _monde()
    a_blanc = await monde.traiter(ecrire=False)
    assert a_blanc.erreur is None and not a_blanc.ecrit and monde.ecrits == []
    # nord: hours, address, two announcements, a sentence; sud: its empty break announcement only.
    assert a_blanc.etablissements == 2 and a_blanc.valeurs == 6 == len(a_blanc.actions)
    assert "nord · horaires_ouverture" in a_blanc.actions and "nord · phrases.phrase_acces" in a_blanc.actions
    assert "sud · annonce_pause" in a_blanc.actions

    reel = await monde.traiter(ecrire=True)
    assert reel.ecrit and len(monde.ecrits) == 1 and monde.ecrits[0][1] == "script etablissements-complets"
    nord, sud = monde.catalogue.etablissements
    assert nord.horaires_ouverture == HORAIRES_AGENT  # what its agent made it say before the rule
    assert nord.adresse == ADRESSE_ORG and nord.phrases == {"phrase_acces": "En centre-ville."}
    assert (nord.annonce_fermeture, nord.annonce_pause) == (ANNONCE_ORG.annonce_fermeture, ANNONCE_ORG.annonce_pause)
    assert sud.annonce_fermeture == "Sud est fermé." and sud.phrases == {"phrase_acces": "Derrière la gare."}  # untouched
    assert sud.horaires_ouverture == HORAIRES_CREIL and sud.adresse.commune == "Creil"

    second = await monde.traiter(ecrire=True)
    assert second.valeurs == 0 and not second.ecrit and len(monde.ecrits) == 1


def _avant_la_regle(configurations, fiche, phrases=PHRASES):
    """L'oracle d'AVANT F-8, en clair : un agent sans fiche joint par ses numéros passe devant
    l'établissement, qui passe devant l'organisation ; annonces et phrases vides = celles de l'organisation."""
    adresse = _adresse_de(configurations.get("adresse_etablissement"), "Agent") or fiche.adresse or ADRESSE_ORG
    contenu = {p.variable: p.contenu for p in phrases.phrases}
    return {
        "horaires": configurations.get("horaires_ouverture") or fiche.horaires_ouverture,
        "adresse": AdresseEtablissement.model_validate(adresse).model_dump(),
        "fermeture": fiche.annonce_fermeture or ANNONCE_ORG.annonce_fermeture,
        "pause": fiche.annonce_pause or ANNONCE_ORG.annonce_pause,
        "phrase_acces": fiche.phrases.get("phrase_acces") or contenu["phrase_acces"],
    }


def _apres_la_regle(configurations, fiche):
    """Ce que l'appel lit aujourd'hui, avec les VRAIES fonctions de l'appel."""
    effectives, _ = configuration_heritee(configurations, fiche)
    annonces = annonce_heritee(ANNONCE_ORG, fiche)
    adresse = resoudre_adresse(effectives, OrganizationPreferences(adresse_etablissement=ADRESSE_ORG))
    return {
        "horaires": effectives.get("horaires_ouverture"),
        "adresse": adresse.model_dump() if adresse else None,
        "fermeture": annonces.annonce_fermeture,
        "pause": annonces.annonce_pause,
        "phrase_acces": valeurs_des_phrases(PHRASES, fiche).get("phrase_acces"),
    }


@pytest.mark.parametrize(
    "configurations",
    [{}, {"horaires_ouverture": HORAIRES_AGENT}, {"adresse_etablissement": ADRESSE_AGENT},
     {"horaires_ouverture": HORAIRES_AGENT, "adresse_etablissement": ADRESSE_AGENT}],
)
@pytest.mark.asyncio
async def test_zero_changement_au_telephone_apres_le_script(configurations):
    """⛔ Un client existant : son agent (sans fiche) est joint par le numéro de « nord », vide. Avant la
    règle il entendait l'agent puis l'organisation ; après le script, la règle nouvelle lit « nord » seul :
    la même chose."""
    monde = _Organisation(CatalogueEtablissements(etablissements=[NORD]), [_agent(6, "Accueil", [NUMERO_NORD], **configurations)])
    avant = _avant_la_regle(configurations, NORD)
    assert avant["fermeture"] and avant["phrase_acces"], "le test doit voir des valeurs, sinon il ne prouve rien"
    await monde.traiter(ecrire=True)
    (nord,) = monde.catalogue.etablissements
    assert _apres_la_regle(configurations, nord) == avant


@pytest.mark.asyncio
async def test_le_script_ne_tranche_pas_un_desaccord_et_signale_un_agent_de_fiche():
    sud_sans_horaires = SUD.model_copy(update={"horaires_ouverture": None})
    monde = _Organisation(
        CatalogueEtablissements(etablissements=[NORD, sud_sans_horaires]),
        [
            _agent(6, "Accueil A", [NUMERO_SUD], horaires_ouverture=HORAIRES_AGENT),
            _agent(7, "Accueil B", [NUMERO_SUD], horaires_ouverture=HORAIRES_CREIL),
            _agent(8, "Fiche nord", [], etablissement_id="nord"),
        ],
    )
    bilan = await monde.traiter(ecrire=True)
    assert any("sud" in a and "horaires" in a for a in bilan.a_decider)
    assert monde.catalogue.etablissements[1].horaires_ouverture is None  # not decided alone
    assert any("Fiche nord" in a and "nord" in a for a in bilan.a_signaler)


def test_le_plan_est_pur_et_rejoue_vide():
    catalogue = CatalogueEtablissements(etablissements=[CREIL])
    plan = plan_complets(catalogue, [], ADRESSE_ORG, ANNONCE_ORG, PHRASES)
    rempli = CatalogueEtablissements(
        etablissements=[Etablissement.model_validate({**CREIL.model_dump(), **plan.fiches["creil"]})]
    )
    second = plan_complets(rempli, [], ADRESSE_ORG, ANNONCE_ORG, PHRASES)
    assert second.fiches == {} and second.actions == []


def test_le_rendu_dit_a_blanc_et_ne_contient_aucun_secret():
    from api.scripts.mark.etablissements_complets import Bilan, rendre

    texte = rendre([Bilan(ORGANISATION, etablissements=1, valeurs=2, actions=["nord · adresse"])], ecrire=False)
    assert texte.startswith("À blanc") and "nord · adresse" in texte and "Total : 2" in texte
