"""[.mark] Non-regression test for the sentences catalogue and the modules read at the right level (L2).

The questions this file answers (chantier l-agent-travaille, L2, E5, E6, R1):

    Does every sentence of the catalogue reach the call context as ``{{variable}}``,
    the establishment's content first when the sentence is placed at its level? Are
    the names Dograh already uses refused? Does an establishment's term reach the
    vocabulary the agent reads (``{{lexique_propose}}``), and only when the agent's
    switch is on? Do the modules -- towns, trade names, numbers, the record -- read
    EXACTLY what they read before when the same address and vocabulary come from an
    establishment instead of the organization (zero loss, replay of the recorded runs)?

⚠️ What this file does NOT prove: that the screen shows the catalogue
(``ui/src/components/mark/``).
"""

import inspect
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.routes import etablissements as route_etablissements
from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.schemas.lexique_metier import LexiqueMetier, TermeLexique
from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.phrases import CataloguePhrases, Phrase
from api.services.communes.adresse import resoudre_adresse
from api.services.etablissements.appel import configuration_heritee
from api.services.etablissements.phrases import (
    injecter_phrases,
    lexique_avec_etablissement,
    valeurs_des_phrases,
)
from api.services.workflow import text_chat_runner
from api.tests.mark.boucle_isolee import executer_sans_toucher_la_boucle_courante
from api.tests.mark.rejeu_corpus import charger, mesurer, rejouer_run
from api.tests.mark.test_etablissements_heritage import (
    CREIL,
    _application,
    _clavier,
)

PHRASES = CataloguePhrases(
    phrases=[
        Phrase(variable="phrase_rgpd", description="Mention", contenu="Vos données restent chez nous.", niveau="organisation"),
        Phrase(variable="phrase_acces", description="Accès", contenu="Le magasin est en centre-ville.", niveau="etablissement"),
        Phrase(variable="phrase_vide", description="Rien", contenu="", niveau="organisation"),
    ]
)
CREIL_AVEC = CREIL.model_copy(
    update={
        "phrases": {"phrase_acces": "Le magasin de Creil est derrière la gare."},
        "termes_lexique": [TermeLexique(terme="Jøtul", propose=True)],
    }
)


# --------------------------------------------------------------------------- #
# 1. The catalogue's format
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("variable", ["annonce_fermeture", "etat_ouverture", "numero_transfert", "etablissement"])
def test_un_nom_deja_donne_par_dograh_est_refuse(variable):
    with pytest.raises(ValidationError, match="already given to the agents"):
        Phrase(variable=variable, contenu="x")


@pytest.mark.parametrize("variable", ["Phrase", "1phrase", "a", "phrase-acces", "é"])
def test_un_nom_de_variable_mal_forme_est_refuse(variable):
    with pytest.raises(ValidationError):
        Phrase(variable=variable, contenu="x")


def test_deux_phrases_ne_partagent_pas_une_variable():
    with pytest.raises(ValidationError, match="share the variable"):
        CataloguePhrases(phrases=[Phrase(variable="ab"), Phrase(variable="ab")])


def test_le_contenu_dune_phrase_detablissement_vide_est_herite():
    assert Etablissement(id="a", nom="A", phrases={"phrase_acces": "  "}).phrases == {}


# --------------------------------------------------------------------------- #
# 2. The injection (E5), pure
# --------------------------------------------------------------------------- #


def test_chaque_phrase_au_bon_niveau():
    assert valeurs_des_phrases(PHRASES, CREIL_AVEC) == {
        "phrase_rgpd": "Vos données restent chez nous.",
        "phrase_acces": "Le magasin de Creil est derrière la gare.",
    }
    assert valeurs_des_phrases(PHRASES, None)["phrase_acces"] == "Le magasin est en centre-ville."
    # A sentence at the organization's level ignores an establishment's content.
    organisation = CataloguePhrases(phrases=[Phrase(variable="phrase_acces", contenu="Org.", niveau="organisation")])
    assert valeurs_des_phrases(organisation, CREIL_AVEC) == {"phrase_acces": "Org."}


def test_une_valeur_deja_fournie_est_gardee_et_rien_sans_catalogue():
    assert injecter_phrases({"phrase_rgpd": "fourni"}, PHRASES, None)["phrase_rgpd"] == "fourni"
    contexte = {"a": 1}
    assert injecter_phrases(contexte, CataloguePhrases(), CREIL_AVEC) is contexte
    assert injecter_phrases(contexte, None, CREIL_AVEC) is contexte


def test_les_termes_de_letablissement_sajoutent_sans_toucher_ceux_de_lorganisation():
    organisation = LexiqueMetier(termes=[TermeLexique(terme="Godin", propose=True)])
    retour = lexique_avec_etablissement(organisation, CREIL_AVEC)
    assert [t.terme for t in retour.termes] == ["Godin", "Jøtul"]
    assert [t.terme for t in organisation.termes] == ["Godin"]
    deja = CREIL.model_copy(update={"termes_lexique": [TermeLexique(terme="godin")]})
    assert lexique_avec_etablissement(organisation, deja) is organisation
    assert lexique_avec_etablissement(organisation, CREIL) is organisation


# --------------------------------------------------------------------------- #
# 3. The routes
# --------------------------------------------------------------------------- #


def test_une_phrase_detablissement_doit_etre_placee_a_ce_niveau():
    app, lignes = _application()
    corps = CatalogueEtablissements(etablissements=[CREIL_AVEC.model_copy(update={"phrases": {"phrase_rgpd": "x"}})])
    with (
        patch.object(route_etablissements, "db_client") as base,
        patch.object(route_etablissements, "lire_phrases_strict", AsyncMock(return_value=PHRASES)),
        patch.object(route_etablissements, "enregistrer_etablissements", AsyncMock(side_effect=lambda _o, c: c)) as ecrit,
    ):
        base.lister_numeros_de_lorganisation = AsyncMock(return_value=lignes)
        reponse = TestClient(app).put("/organizations/etablissements", json=corps.model_dump(mode="json"))
        assert reponse.status_code == 422 and "not a sentence placed at the establishment" in reponse.text
        assert ecrit.await_count == 0
        bon = CatalogueEtablissements(etablissements=[CREIL_AVEC])
        assert TestClient(app).put("/organizations/etablissements", json=bon.model_dump(mode="json")).status_code == 200


def test_le_catalogue_senregistre_et_refuse_un_nom_reserve():
    app, _ = _application()
    app.include_router(route_etablissements.routeur_phrases)
    with patch.object(route_etablissements, "enregistrer_phrases", AsyncMock(side_effect=lambda _o, c: c)) as ecrit:
        client = TestClient(app)
        assert client.put("/organizations/phrases", json=PHRASES.model_dump(mode="json")).status_code == 200
        refuse = client.put("/organizations/phrases", json={"phrases": [{"variable": "annonce_pause", "contenu": "x"}]})
        assert refuse.status_code == 422
        assert ecrit.await_count == 1


def test_les_routes_des_phrases_figurent_dans_la_spec_publiee():
    from api.app import app

    assert "/api/v1/organizations/phrases" in app.openapi()["paths"]


# --------------------------------------------------------------------------- #
# 4. Branched: the keyboard RUN up to the engine (R1)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_clavier_les_phrases_arrivent_dans_le_contexte_de_lappel():
    catalogue = CatalogueEtablissements(etablissements=[CREIL_AVEC])
    persiste = await _clavier(catalogue, contexte={"direction": "inbound", "etablissement_id": "creil"}, phrases=PHRASES)
    assert persiste["phrase_rgpd"] == "Vos données restent chez nous."
    assert persiste["phrase_acces"] == "Le magasin de Creil est derrière la gare."
    assert "phrase_vide" not in persiste


@pytest.mark.asyncio
async def test_clavier_les_phrases_de_lorganisation_sans_etablissement():
    persiste = await _clavier(CatalogueEtablissements(), phrases=PHRASES)
    assert persiste["phrase_acces"] == "Le magasin est en centre-ville."
    assert "etablissement" not in persiste


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupteur, attendu", [(True, True), (False, False)])
async def test_clavier_le_terme_de_letablissement_arrive_au_lexique_propose(interrupteur, attendu):
    catalogue = CatalogueEtablissements(etablissements=[CREIL_AVEC])
    organisation = LexiqueMetier(termes=[TermeLexique(terme="Godin", propose=True)])

    async def lexique(run_configs, _org):
        return organisation if interrupteur else LexiqueMetier()

    with patch.object(text_chat_runner, "lire_lexique_de_lappel", lexique):
        persiste = await _clavier(
            catalogue,
            configurations={"lexique_metier": interrupteur},
            contexte={"direction": "inbound", "etablissement_id": "creil"},
        )
    propose = str(persiste.get("lexique_propose") or "")
    assert ("Jøtul" in propose) is attendu
    assert ("Godin" in propose) is interrupteur


def test_clavier_les_modules_lisent_ladresse_et_le_lexique_resolus():
    """The reading step and the trade names on the keyboard take the SAME variables the
    inheritance produced: the address read from ``configs_heritees``, the vocabulary
    after the establishment's terms (asserted in order on the source)."""
    source = inspect.getsource(text_chat_runner)
    termes = re.search(r"lexique_metier = lexique_avec_etablissement\(", source).start()
    annote = re.search(r"annoter_message_tape\(\s*pending_user_message,\s*run_configs,\s*lexique_metier", source).start()
    lit = re.search(r"lire_message_tape\(\s*message_pour_le_modele,\s*run_configs,\s*getattr\(user_config, \"stt\", None\),\s*adresse_etablissement", source).start()
    assert termes < annote < lit


# --------------------------------------------------------------------------- #
# 5. Zero loss: the recorded runs replayed with the address and the vocabulary
#    coming from an ESTABLISHMENT instead of the organization
# --------------------------------------------------------------------------- #

CORPUS_ENREGISTRES = [
    "rejeu_runs_861_881.json",
    "rejeu_runs_882_895.json",
    "rejeu_runs_899_904.json",
    "rejeu_runs_963_967.json",
]


def _par_letablissement(corpus: dict) -> dict:
    """The same corpus, but its address and vocabulary resolved through the inheritance:
    the organization has none, ONE establishment carries them."""
    adresse = AdresseEtablissement(**corpus["adresse_etablissement"])
    lexique = LexiqueMetier.model_validate(corpus["lexique"])
    etablissement = Etablissement(id="magasin", nom="Magasin", adresse=adresse, termes_lexique=lexique.termes)
    configs, _ = configuration_heritee({}, etablissement)
    resolue = resoudre_adresse(configs, SimpleNamespace(adresse_etablissement=None))
    lexique_resolu = lexique_avec_etablissement(LexiqueMetier(), etablissement)
    return {
        **corpus,
        "adresse_etablissement": resolue.model_dump(mode="json"),
        "lexique": {**corpus["lexique"], "termes": [t.model_dump(mode="json") for t in lexique_resolu.termes]},
    }


@pytest.mark.parametrize("fichier", CORPUS_ENREGISTRES)
def test_rejeu_zero_perte_quand_ladresse_et_le_lexique_viennent_dun_etablissement(fichier):
    from pathlib import Path

    corpus = charger(Path(__file__).parent / "donnees" / fichier)
    par_etablissement = _par_letablissement(corpus)
    assert par_etablissement["adresse_etablissement"] == AdresseEtablissement(**corpus["adresse_etablissement"]).model_dump(mode="json")

    async def tout(c):
        return {str(run["id"]): mesurer(await rejouer_run(run, c), run) for run in c["runs"]}

    avant = executer_sans_toucher_la_boucle_courante(tout(corpus))
    apres = executer_sans_toucher_la_boucle_courante(tout(par_etablissement))
    assert len(avant) == len(corpus["runs"]) > 0
    assert apres == avant


def test_le_telephone_injecte_les_phrases_et_les_termes_avant_la_persistance():
    from api.services.pipecat import run_pipeline

    source = inspect.getsource(run_pipeline)
    position = lambda motif: re.search(motif, source).start()
    etablissement = position(r"merged_call_context_vars = injecter_etablissement\(")
    phrases = position(r"merged_call_context_vars = injecter_phrases\(")
    termes = position(r"lexique_metier = lexique_avec_etablissement\(")
    ecoute = position(r"liste_ecoutee = construire_liste_ecoutee\(")
    persistance = position(r"await db_client\.update_workflow_run\(\s*workflow_run_id, initial_context")
    assert etablissement < phrases < termes < ecoute < persistance


def test_lessai_au_navigateur_porte_letablissement_choisi():
    """E3: the browser test window sends the chosen establishment; the run creation puts
    it in the context, where the call set-up reads it (``choisir_etablissement``)."""
    from api.routes import workflow as route_agent

    assert route_agent.CreateWorkflowRunRequest(mode="smallwebrtc", name="x").etablissement_id is None
    assert route_agent.CreateWorkflowRunRequest(mode="smallwebrtc", name="x", etablissement_id="creil").etablissement_id == "creil"
    source = inspect.getsource(route_agent.create_workflow_run)
    assert re.search(r'initial_context\["etablissement_id"\] = request\.etablissement_id', source)
    assert source.index('initial_context["etablissement_id"]') < source.index("db_client.create_workflow_run(")
