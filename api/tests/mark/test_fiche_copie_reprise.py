"""[.mark] Chantier agents-specialises, lot 4 (= lot 2 du plan fiche-etablissement) :
copie d'une fiche (F2), reprise des fiches et des agents (R7), variables dans les phrases (F6).

| Test | Ce qu'il prouve |
|---|---|
| copie, vraie route | la copie reprend le lieu (adresse, horaires, annonces, phrases), jamais les numéros ni la fermeture ; la fiche part à l'enregistrement |
| copie refusée | source inconnue (404), identifiant pris (422), phrase mal placée (422) : rien n'est écrit |
| copie, rendez-vous | avec une base du client : réglages et types de la source recopiés sous la nouvelle fiche |
| reprise en essai | liste ce qu'elle ferait, zéro écriture (ni fiches, ni agents) |
| reprise réelle | écrit ce que la fiche héritait et l'agent à numéro unique ; rien d'une valeur déjà posée ; rejouée = rien à faire |
| reprise, zéro perte | ce que l'agent lit APRÈS (fiche sans héritage) = ce qu'il lisait AVANT (horaires, adresse, annonces) |
| reprise, cas ambigus | agent à plusieurs fiches, horaires qui divergent : signalés, jamais écrits |
| rattachement | ``etablissement_id`` posé dans la version publiée et le brouillon, jamais dans une archive, jamais sur une valeur existante |
| F6, clavier | ``{{etablissement}}`` écrit dans une phrase dit le nom de la fiche, dans le contexte de l'appel |
| F6, pure | une passe ; inconnu laissé tel quel ; pas de remplissage en chaîne ; sans accolades = mêmes objets |
"""

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
from api.schemas.planificateur import Planificateur, ReglagesPlanificateur, TypeRendezVous
from api.services.auth.depends import get_user_with_selected_organization
from api.services.communes.adresse import resoudre_adresse
from api.services.etablissements import reprise as module_reprise
from api.services.etablissements.appel import annonce_heritee, configuration_heritee
from api.services.etablissements.phrases import injecter_phrases, remplir_une_fois
from api.services.etablissements.reprise import AgentVu, preparer_reprise
from api.tests.mark.test_adresse_etablissement import ORGANISATION
from api.tests.mark.test_etablissements_heritage import (
    CREIL,
    HORAIRES_AGENT,
    HORAIRES_CREIL,
    SENLIS,
    _clavier,
)

ADRESSE_ORG = AdresseEtablissement(code_postal="60300", code_insee="60612", commune="Senlis")
ADRESSE_AGENT = {"code_postal": "60100", "code_insee": "60175", "commune": "Creil"}
PHRASES = CataloguePhrases(
    phrases=[
        Phrase(variable="phrase_acces", description="Accès", contenu="Le magasin est en centre-ville.", niveau="etablissement"),
    ]
)
SOURCE = CREIL.model_copy(
    update={
        "second_numero": "+33344000055",
        "etat_force": "FERME",
        "phrases": {"phrase_acces": "Derrière la gare."},
    }
)
AUTRE = Etablissement(id="senlis", nom="Magasin de Senlis", numeros=["+33344000002"])


# --------------------------------------------------------------------------- #
# La route : application de test et simulacres de stockage
# --------------------------------------------------------------------------- #


def _application():
    app = FastAPI()
    app.include_router(route_etablissements.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, provider_id="p", selected_organization_id=ORGANISATION, email="evan@exemple.invalid"
    )
    return app


class _Banc:
    """Les simulacres d'une route : un catalogue lisible, un enregistrement qui se souvient."""

    def __init__(self, catalogue, phrases=PHRASES, planificateur=None, agents=None):
        self.catalogue = catalogue
        self.phrases = phrases
        self.planificateur = planificateur
        self.agents = agents or []
        self.enregistre = []
        self.planificateur_ecrit = []
        self.rattachements = []

    async def _enregistrer(self, _org, catalogue, _auteur="dograh", **_options):
        self.enregistre.append(catalogue)
        self.catalogue = catalogue
        return catalogue

    async def _ecrire_planificateur(self, _connexion, planificateur, _auteur):
        self.planificateur_ecrit.append(planificateur)
        self.planificateur = planificateur

    async def _rattacher(self, _org, agents):
        self.rattachements.append(dict(agents))
        for agent in self.agents:
            if agent.id in agents:
                agent.configurations = {**agent.configurations, "etablissement_id": agents[agent.id]}

    def poste(self, chemin, corps, avec_base=False, adresse_org=ADRESSE_ORG, planificateur_en_panne=False):
        base_attachee = "base-test" if avec_base else None

        async def lire_agents(_org):
            return self.agents

        connexion = SimpleNamespace(close=AsyncMock())

        async def lire_planificateur(_connexion):
            if planificateur_en_panne:
                raise OSError("base absente")
            return self.planificateur

        with (
            patch.object(route_etablissements, "db_client") as db,
            patch.object(route_etablissements, "lire_etablissements_strict", AsyncMock(side_effect=lambda _o: self.catalogue)),
            patch.object(route_etablissements, "lire_phrases_strict", AsyncMock(return_value=self.phrases)),
            patch.object(route_etablissements, "enregistrer_etablissements", self._enregistrer),
            patch("api.services.etablissements.stockage.nom_de_la_base_strict", AsyncMock(return_value=base_attachee)),
            patch("api.db.bases_clients.connexion.connecter", AsyncMock(return_value=connexion)),
            patch("api.db.bases_clients.planificateur.lire_planificateur", lire_planificateur),
            patch("api.db.bases_clients.planificateur.ecrire_planificateur", self._ecrire_planificateur),
            patch.object(module_reprise, "lire_agents", lire_agents),
            patch.object(module_reprise, "ecrire_rattachements", self._rattacher),
            patch(
                "api.services.organization_preferences.get_organization_preferences",
                AsyncMock(return_value=OrganizationPreferences(adresse_etablissement=adresse_org)),
            ),
            patch("api.services.annonce.stockage.lire_annonce_ouverture", AsyncMock(return_value=ReglagesAnnonceOuverture())),
        ):
            db.lister_numeros_de_lorganisation = AsyncMock(
                return_value=[(n, None, None, None, True) for e in self.catalogue.etablissements for n in e.numeros]
            )
            return TestClient(_application()).post(f"/organizations/etablissements{chemin}", json=corps)


# --------------------------------------------------------------------------- #
# F2 : la copie
# --------------------------------------------------------------------------- #


def test_la_copie_reprend_le_lieu_jamais_les_numeros_ni_la_fermeture():
    banc = _Banc(CatalogueEtablissements(etablissements=[SOURCE, AUTRE]))
    reponse = banc.poste("/copier", {"source": "creil", "id": "creil-bis", "nom": "Magasin de Creil Nord"})
    assert reponse.status_code == 200, reponse.text
    # Le lieu est copié.
    nouvelle = reponse.json()["etablissement"]
    assert nouvelle["id"] == "creil-bis" and nouvelle["nom"] == "Magasin de Creil Nord"
    assert nouvelle["horaires_ouverture"] == HORAIRES_CREIL
    assert nouvelle["adresse"]["commune"] == "Senlis"
    assert nouvelle["annonce_fermeture"] == SOURCE.annonce_fermeture
    assert nouvelle["phrases"] == {"phrase_acces": "Derrière la gare."}
    # Ce qui tient à la ligne ne l'est pas.
    assert nouvelle["numeros"] == [] and nouvelle["second_numero"] is None and nouvelle["numero_transfert"] is None
    assert nouvelle["etat_force"] is None and nouvelle["etat_force_jusqu_a"] is None
    assert "numeros" in reponse.json()["non_copie"] and "etat_force" in reponse.json()["non_copie"]
    # La fiche est PARTIE à l'enregistrement, la source intacte.
    assert len(banc.enregistre) == 1
    ids = [e.id for e in banc.enregistre[0].etablissements]
    assert ids == ["creil", "senlis", "creil-bis"]
    source = banc.enregistre[0].etablissements[0]
    assert source.numeros == SOURCE.numeros and source.etat_force == "FERME"


def test_une_copie_refusee_n_ecrit_rien():
    banc = _Banc(CatalogueEtablissements(etablissements=[SOURCE, AUTRE]))
    inconnue = banc.poste("/copier", {"source": "nulle-part", "id": "x1", "nom": "X"})
    assert inconnue.status_code == 404
    prise = banc.poste("/copier", {"source": "creil", "id": "senlis", "nom": "X"})
    assert prise.status_code == 422 and "already belongs" in prise.text
    mal_forme = banc.poste("/copier", {"source": "creil", "id": "Pas Valide", "nom": "X"})
    assert mal_forme.status_code == 422
    # Les mêmes contrôles qu'un enregistrement : une phrase qui n'est plus placée au niveau de la fiche.
    sans_niveau = _Banc(
        CatalogueEtablissements(etablissements=[SOURCE]),
        phrases=CataloguePhrases(phrases=[Phrase(variable="phrase_acces", contenu="x", niveau="organisation")]),
    )
    controle = sans_niveau.poste("/copier", {"source": "creil", "id": "creil-bis", "nom": "Bis"})
    assert controle.status_code == 422 and "not a sentence placed at the establishment" in controle.text
    assert banc.enregistre == [] and sans_niveau.enregistre == []


def test_la_copie_emporte_les_reglages_de_rendez_vous_avec_une_base_du_client():
    planificateur = Planificateur(
        reglages=ReglagesPlanificateur(nombre_creneaux=2),
        par_etablissement={"creil": ReglagesPlanificateur(zone_rayon_km=25, pas_min=15)},
        types=[
            TypeRendezVous(code="visite", etablissement="creil", libelle="Visite", duree_min=60),
            TypeRendezVous(code="general", etablissement=None, libelle="Général", duree_min=30),
        ],
    )
    banc = _Banc(CatalogueEtablissements(etablissements=[SOURCE]), planificateur=planificateur)
    reponse = banc.poste("/copier", {"source": "creil", "id": "creil-bis", "nom": "Bis"}, avec_base=True)
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["reglages_rendez_vous_copies"] is True and corps["types_rendez_vous_copies"] == 1
    assert len(banc.planificateur_ecrit) == 1
    ecrit = banc.planificateur_ecrit[0]
    assert ecrit.par_etablissement["creil-bis"].zone_rayon_km == 25
    assert ecrit.par_etablissement["creil"].zone_rayon_km == 25  # la source ne bouge pas
    assert sorted((t.code, t.etablissement) for t in ecrit.types) == [
        ("general", None),
        ("visite", "creil"),
        ("visite", "creil-bis"),
    ]


def test_sans_base_du_client_la_copie_ne_touche_pas_au_planificateur():
    banc = _Banc(CatalogueEtablissements(etablissements=[SOURCE]))
    reponse = banc.poste("/copier", {"source": "creil", "id": "creil-bis", "nom": "Bis"})
    assert reponse.status_code == 200
    assert reponse.json()["reglages_rendez_vous_copies"] is False and banc.planificateur_ecrit == []


# --------------------------------------------------------------------------- #
# La reprise : le plan (pur)
# --------------------------------------------------------------------------- #

NUMERO_CREIL = "+33344000001"
NUMERO_SENLIS = "+33344000002"
VIDE = Etablissement(id="creil", nom="Magasin de Creil", numeros=[NUMERO_CREIL])
VIDE_2 = Etablissement(id="senlis", nom="Magasin de Senlis", numeros=[NUMERO_SENLIS])
ORG_ANNONCE = ReglagesAnnonceOuverture()


def _agent(identifiant, nom, numeros, **configurations):
    return AgentVu(id=identifiant, nom=nom, numeros=numeros, configurations=dict(configurations))


def test_la_reprise_ecrit_ce_que_la_fiche_heritait():
    catalogue = CatalogueEtablissements(etablissements=[VIDE])
    agent = _agent(6, "Accueil", [NUMERO_CREIL], horaires_ouverture=HORAIRES_AGENT, adresse_etablissement=ADRESSE_AGENT)
    plan = preparer_reprise(catalogue, [agent], ADRESSE_ORG, ORG_ANNONCE, None)
    ecrits = plan.fiches["creil"]
    assert ecrits["horaires_ouverture"] == HORAIRES_AGENT  # l'agent passait devant la fiche
    assert ecrits["adresse"].commune == "Creil"  # idem pour l'adresse
    assert ecrits["annonce_fermeture"] == ORG_ANNONCE.annonce_fermeture
    assert ecrits["annonce_pause"] == ORG_ANNONCE.annonce_pause
    assert plan.agents == {6: "creil"}
    assert plan.a_decider == []


def test_sans_agent_l_adresse_de_l_organisation_et_pas_d_horaires_inventes():
    plan = preparer_reprise(CatalogueEtablissements(etablissements=[VIDE]), [], ADRESSE_ORG, ORG_ANNONCE, None)
    assert plan.fiches["creil"]["adresse"] == ADRESSE_ORG
    assert "horaires_ouverture" not in plan.fiches["creil"]


def test_une_valeur_deja_posee_n_est_jamais_remplacee():
    catalogue = CatalogueEtablissements(etablissements=[CREIL])  # horaires, adresse, annonce_fermeture posés
    agent = _agent(6, "Accueil", [NUMERO_CREIL], horaires_ouverture=HORAIRES_AGENT, adresse_etablissement=ADRESSE_AGENT)
    plan = preparer_reprise(catalogue, [agent], ADRESSE_ORG, ORG_ANNONCE, None)
    assert "horaires_ouverture" not in plan.fiches.get("creil", {})
    assert "adresse" not in plan.fiches.get("creil", {})
    assert "annonce_fermeture" not in plan.fiches.get("creil", {})
    # L'agent disait autre chose que la fiche : à décider, rien d'écrit.
    assert any("horaires" in ligne for ligne in plan.a_decider)
    assert any("adresse" in ligne for ligne in plan.a_decider)


def test_des_agents_qui_se_contredisent_ne_sont_pas_departages():
    catalogue = CatalogueEtablissements(etablissements=[VIDE])
    a = _agent(6, "Accueil", [NUMERO_CREIL], horaires_ouverture=HORAIRES_AGENT)
    b = _agent(7, "Standard", [NUMERO_CREIL], horaires_ouverture=HORAIRES_CREIL)
    plan = preparer_reprise(catalogue, [a, b], None, ORG_ANNONCE, None)
    assert "horaires_ouverture" not in plan.fiches.get("creil", {})
    assert any("horaires différents" in ligne for ligne in plan.a_decider)


def test_un_agent_a_plusieurs_fiches_n_est_pas_rattache():
    catalogue = CatalogueEtablissements(etablissements=[VIDE, VIDE_2])
    deux = _agent(6, "Accueil", [NUMERO_CREIL, NUMERO_SENLIS])
    une_et_aucune = _agent(7, "Standard", [NUMERO_CREIL, "+33100000000"])
    sans_fiche = _agent(8, "Hors fiches", ["+33100000001"])
    plan = preparer_reprise(catalogue, [deux, une_et_aucune, sans_fiche], None, ORG_ANNONCE, None)
    assert plan.agents == {}
    assert len(plan.a_decider) == 2
    assert any("plusieurs fiches" in ligne for ligne in plan.a_decider)
    assert any("aucune autre" in ligne for ligne in plan.a_decider)


def test_la_reprise_complete_les_reglages_de_rendez_vous_de_la_fiche_avec_ceux_de_l_organisation():
    planificateur = Planificateur(
        reglages=ReglagesPlanificateur(nombre_creneaux=2, horizon_jours=20, zone_rayon_km=30),
        par_etablissement={"creil": ReglagesPlanificateur(horizon_jours=7)},
    )
    plan = preparer_reprise(CatalogueEtablissements(etablissements=[VIDE]), [], None, ORG_ANNONCE, planificateur)
    complets = plan.reglages["creil"]
    assert complets.horizon_jours == 7  # la fiche gardait déjà le sien
    assert (complets.nombre_creneaux, complets.zone_rayon_km) == (2, 30)


def test_un_agent_deja_rattache_n_est_pas_retouche():
    catalogue = CatalogueEtablissements(etablissements=[VIDE])
    deja = _agent(6, "Accueil", [NUMERO_CREIL], etablissement_id="creil")
    assert preparer_reprise(catalogue, [deja], None, ORG_ANNONCE, None).agents == {}


def test_rejouee_la_reprise_ne_trouve_plus_rien_a_faire():
    """Idempotente : on applique le plan, on rejoue sur le résultat, plus aucune action."""
    planificateur = Planificateur(reglages=ReglagesPlanificateur(nombre_creneaux=2))
    catalogue = CatalogueEtablissements(etablissements=[VIDE, VIDE_2])
    agents = [
        _agent(6, "Accueil", [NUMERO_CREIL], horaires_ouverture=HORAIRES_AGENT),
        _agent(7, "Standard", [NUMERO_SENLIS], horaires_ouverture=HORAIRES_CREIL, adresse_etablissement=ADRESSE_AGENT),
    ]
    premier = preparer_reprise(catalogue, agents, ADRESSE_ORG, ORG_ANNONCE, planificateur)
    assert premier.actions
    # On applique.
    ecrits = CatalogueEtablissements(
        etablissements=[e.model_copy(update=premier.fiches.get(e.id, {})) for e in catalogue.etablissements]
    )
    apres = Planificateur(
        reglages=planificateur.reglages,
        par_etablissement={**planificateur.par_etablissement, **premier.reglages},
    )
    for agent in agents:
        if agent.id in premier.agents:
            agent.configurations["etablissement_id"] = premier.agents[agent.id]
    second = preparer_reprise(ecrits, agents, ADRESSE_ORG, ORG_ANNONCE, apres)
    assert second.actions == [] and second.fiches == {} and second.reglages == {} and second.agents == {}
    assert second.a_decider == []


# --------------------------------------------------------------------------- #
# La reprise : zéro perte (R7), ce que l'agent lit avant et après
# --------------------------------------------------------------------------- #


def _ce_que_l_agent_lit(configurations, fiche):
    """Ce que l'appel lit aujourd'hui (F-8 : l'établissement servi seul), avec les VRAIES fonctions."""
    effectives, _origines = configuration_heritee(configurations, fiche)
    annonces = annonce_heritee(ReglagesAnnonceOuverture(), fiche)
    adresse = resoudre_adresse(effectives, OrganizationPreferences(adresse_etablissement=ADRESSE_ORG))
    return {
        "horaires": (effectives or {}).get("horaires_ouverture"),
        "adresse": adresse.model_dump() if adresse else None,
        "annonce_fermeture": annonces.annonce_fermeture,
        "annonce_pause": annonces.annonce_pause,
    }


def _ce_qu_il_lisait_avant_la_regle(configurations, fiche):
    """L'oracle d'AVANT (règle E2 d'avant C3 et F-8), écrit ici en clair : l'agent passe devant, puis
    l'établissement, puis l'organisation ; une annonce vide de l'établissement prend celle de l'organisation."""
    from api.services.communes.adresse import _adresse_de

    organisation = ReglagesAnnonceOuverture()
    adresse = _adresse_de(configurations.get("adresse_etablissement"), "Agent") or fiche.adresse or ADRESSE_ORG
    return {
        "horaires": configurations.get("horaires_ouverture") or fiche.horaires_ouverture,
        "adresse": AdresseEtablissement.model_validate(adresse).model_dump() if adresse else None,
        "annonce_fermeture": fiche.annonce_fermeture or organisation.annonce_fermeture,
        "annonce_pause": fiche.annonce_pause or organisation.annonce_pause,
    }


@pytest.mark.parametrize(
    "configurations",
    [
        {},
        {"horaires_ouverture": HORAIRES_AGENT},
        {"adresse_etablissement": ADRESSE_AGENT},
        {"horaires_ouverture": HORAIRES_AGENT, "adresse_etablissement": ADRESSE_AGENT},
    ],
)
def test_apres_la_reprise_l_agent_dit_exactement_ce_qu_il_disait_avant(configurations):
    """⛔ La preuve du zéro perte, avec les VRAIES fonctions de l'appel : avant (fiche qui hérite,
    l'agent passe devant), après (fiche remplie, sans héritage, l'agent rattaché)."""
    catalogue = CatalogueEtablissements(etablissements=[VIDE])
    avant = _ce_qu_il_lisait_avant_la_regle(configurations, VIDE)
    plan = preparer_reprise(catalogue, [_agent(6, "Accueil", [NUMERO_CREIL], **configurations)], ADRESSE_ORG, ORG_ANNONCE, None)
    repris = VIDE.model_copy(update=plan.fiches.get("creil", {}))
    apres = _ce_que_l_agent_lit({**configurations, "etablissement_id": "creil"}, repris)
    assert apres == avant, (avant, apres)
    assert avant["annonce_fermeture"], "le test doit voir une annonce, sinon il ne prouve rien"
    assert avant["adresse"] is not None


# --------------------------------------------------------------------------- #
# La reprise : la vraie route
# --------------------------------------------------------------------------- #


def _banc_de_reprise():
    agents = [
        _agent(6, "Accueil", [NUMERO_CREIL], horaires_ouverture=HORAIRES_AGENT),
        _agent(7, "Deux lieux", [NUMERO_SENLIS, "+33100000000"]),
    ]
    return _Banc(CatalogueEtablissements(etablissements=[VIDE, VIDE_2]), agents=agents)


def test_la_reprise_en_essai_n_ecrit_rien():
    banc = _banc_de_reprise()
    reponse = banc.poste("/reprise", {})
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["ecrit"] is False
    champs = {(a["sujet"], a["cible"], a["champ"]) for a in corps["actions"]}
    assert ("fiche", "creil", "horaires_ouverture") in champs  # le test voit ce qu'elle ferait
    assert ("agent", "Accueil (6)", "etablissement_id") in champs
    assert len(corps["a_decider"]) == 1 and "Deux lieux" in corps["a_decider"][0]
    assert banc.enregistre == [] and banc.rattachements == [] and banc.planificateur_ecrit == []


def test_la_reprise_ecrit_les_fiches_et_les_agents_puis_se_rejoue_sans_effet():
    planificateur = Planificateur(reglages=ReglagesPlanificateur(nombre_creneaux=2))
    banc = _banc_de_reprise()
    banc.planificateur = planificateur
    reponse = banc.poste("/reprise", {"ecrire": True}, avec_base=True)
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["ecrit"] is True
    # Les fiches : ce qu'elles héritaient est écrit.
    assert len(banc.enregistre) == 1
    creil = next(e for e in banc.enregistre[0].etablissements if e.id == "creil")
    assert creil.horaires_ouverture == HORAIRES_AGENT
    assert creil.adresse.commune == "Senlis"
    assert creil.annonce_fermeture == ReglagesAnnonceOuverture().annonce_fermeture
    # Les rendez-vous, l'agent à numéro unique, et pas l'autre.
    assert banc.planificateur_ecrit[0].par_etablissement["creil"].nombre_creneaux == 2
    assert banc.rattachements == [{6: "creil"}]
    # Rejouée sur le résultat : plus rien à faire.
    rejeu = banc.poste("/reprise", {"ecrire": True}, avec_base=True)
    assert rejeu.status_code == 200
    assert rejeu.json()["actions"] == [] and len(banc.enregistre) == 1 and banc.rattachements == [{6: "creil"}]


def test_la_reprise_ne_fait_rien_quand_la_base_du_client_ne_repond_pas():
    banc = _banc_de_reprise()
    reponse = banc.poste("/reprise", {"ecrire": True}, avec_base=True, planificateur_en_panne=True)
    assert reponse.status_code == 503 and "Nothing was changed" in reponse.text
    assert banc.enregistre == [] and banc.rattachements == []


# --------------------------------------------------------------------------- #
# Le rattachement des agents (la base de Dograh)
# --------------------------------------------------------------------------- #


def _definition(identifiant, statut, configurations):
    return SimpleNamespace(id=identifiant, status=statut, workflow_configurations=configurations)


@pytest.mark.asyncio
async def test_le_rattachement_pose_la_fiche_sur_le_publie_et_le_brouillon_jamais_sur_une_archive():
    agent = SimpleNamespace(
        id=6,
        status="active",
        name="Accueil",
        workflow_configurations={"horaires_ouverture": "x"},
        definitions=[
            _definition(10, "archived", {"vieux": 1}),
            _definition(11, "published", {"a": 1}),
            _definition(12, "draft", {"a": 2, "etablissement_id": "deja-la"}),
        ],
    )
    autre = SimpleNamespace(
        id=9, status="active", name="Autre", workflow_configurations={}, definitions=[_definition(20, "published", {})]
    )
    with patch("api.db.db_client") as base:
        base.list_workflows_for_model_configuration_migration = AsyncMock(return_value=[agent, autre])
        base.bulk_update_workflow_model_configurations = AsyncMock()
        await module_reprise.ecrire_rattachements(ORGANISATION, {6: "creil"})
    envoi = base.bulk_update_workflow_model_configurations.await_args.kwargs
    assert envoi["organization_id"] == ORGANISATION
    assert envoi["workflow_updates"] == [(6, {"horaires_ouverture": "x", "etablissement_id": "creil"})]
    # Publiée : posée. Brouillon qui a déjà SA fiche : intacte. Archive : jamais. Un agent hors liste : jamais.
    assert envoi["definition_updates"] == [(11, {"a": 1, "etablissement_id": "creil"})]


@pytest.mark.asyncio
async def test_la_lecture_des_agents_prend_la_version_publiee_et_les_numeros_actifs():
    agent = SimpleNamespace(
        id=6,
        status="active",
        name="Accueil",
        workflow_configurations={"horaires_ouverture": "brouillon"},
        definitions=[_definition(11, "published", {"horaires_ouverture": "publie"})],
    )
    archive = SimpleNamespace(id=7, status="archived", name="Vieux", workflow_configurations={}, definitions=[])
    lignes = [
        ("+33344000001", None, 6, "Accueil", True),
        ("+33344000009", None, 6, "Accueil", False),
        ("+33344000002", None, None, None, True),
    ]
    with patch("api.db.db_client") as base:
        base.lister_numeros_de_lorganisation = AsyncMock(return_value=lignes)
        base.list_workflows_for_model_configuration_migration = AsyncMock(return_value=[agent, archive])
        vus = await module_reprise.lire_agents(ORGANISATION)
    assert len(vus) == 1
    assert vus[0].numeros == ["+33344000001"]
    assert vus[0].configurations == {"horaires_ouverture": "publie"}


# --------------------------------------------------------------------------- #
# F6 : les variables de l'appel dans une phrase
# --------------------------------------------------------------------------- #


def test_une_variable_de_l_appel_dans_une_phrase_est_remplie_une_fois():
    contexte = {"etablissement": "Magasin de Creil", "numero_transfert": "+33344000099"}
    assert remplir_une_fois("Bienvenue au {{etablissement}} !", contexte) == "Bienvenue au Magasin de Creil !"
    assert remplir_une_fois("{{ etablissement }} puis {{etablissement}}", contexte) == "Magasin de Creil puis Magasin de Creil"


def test_une_variable_inconnue_reste_telle_quelle_comme_aujourd_hui():
    contexte = {"etablissement": "Magasin de Creil"}
    assert remplir_une_fois("Ici {{inconnue}} et {{etablissement}}", contexte) == "Ici {{inconnue}} et Magasin de Creil"
    # L'horloge se rend au moment du prompt, pas avant : elle reste écrite.
    assert remplir_une_fois("Il est {{current_time}}", contexte) == "Il est {{current_time}}"
    # Une variable vide aussi.
    assert remplir_une_fois("{{vide}}", {"vide": ""}) == "{{vide}}"


def test_sans_accolades_la_phrase_n_est_pas_touchee_et_les_phrases_ne_se_remplissent_pas_en_chaine():
    texte = "Le magasin est en centre-ville."
    assert remplir_une_fois(texte, {"a": "b"}) is texte
    catalogue = CataloguePhrases(
        phrases=[
            Phrase(variable="phrase_a", contenu="A dit {{phrase_b}}."),
            Phrase(variable="phrase_b", contenu="B dit {{etablissement}}."),
        ]
    )
    sortie = injecter_phrases({"etablissement": "Creil"}, catalogue, None)
    assert sortie["phrase_b"] == "B dit Creil."
    assert sortie["phrase_a"] == "A dit {{phrase_b}}."  # une seule passe : pas de chaîne


def test_une_valeur_deja_fournie_reste_ce_qu_elle_etait():
    catalogue = CataloguePhrases(phrases=[Phrase(variable="phrase_a", contenu="A dit {{etablissement}}.")])
    sortie = injecter_phrases({"etablissement": "Creil", "phrase_a": "fournie {{etablissement}}"}, catalogue, None)
    assert sortie["phrase_a"] == "fournie {{etablissement}}"


@pytest.mark.asyncio
async def test_clavier_le_nom_de_la_fiche_dit_dans_une_phrase():
    """R1 : par la vraie route du clavier jusqu'au moteur. Échoue si la phrase garde ses accolades."""
    phrases = CataloguePhrases(
        phrases=[
            Phrase(variable="phrase_accueil", contenu="Bonjour, vous êtes au {{etablissement}}.", niveau="organisation"),
            Phrase(variable="phrase_inconnue", contenu="Voir {{variable_que_personne_ne_donne}}.", niveau="organisation"),
        ]
    )
    persiste = await _clavier(
        CatalogueEtablissements(etablissements=[CREIL]),
        contexte={"direction": "inbound", "etablissement_id": "creil"},
        phrases=phrases,
    )
    assert persiste["phrase_accueil"] == "Bonjour, vous êtes au Magasin de Creil."
    assert persiste["phrase_inconnue"] == "Voir {{variable_que_personne_ne_donne}}."
    # Sans fiche, rien à remplir : la phrase est celle d'avant.
    sans_fiche = await _clavier(CatalogueEtablissements(), phrases=phrases)
    assert sans_fiche["phrase_accueil"] == "Bonjour, vous êtes au {{etablissement}}."


def test_les_routes_de_copie_et_de_reprise_figurent_dans_la_spec_publiee():
    from api.app import app

    chemins = app.openapi()["paths"]
    for chemin in ("/copier", "/reprise"):
        assert f"/api/v1/organizations/etablissements{chemin}" in chemins
