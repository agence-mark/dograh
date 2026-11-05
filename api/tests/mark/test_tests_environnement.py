"""[.mark] builder partie 3, sous-lot 5 (SE-11, C-3) : Tests, onglet Environnement, critères d'ordre et d'unicité, test depuis une
conversation entière, scénarios « Nombres en français » et « Outil en panne ».

Aucun appel réel : cerveau factice, réponses d'outils écrites dans le test, base en mémoire (ou celle des tests).

| Test | La garantie |
|---|---|
| critères | « dans cet ordre » (d'autres outils peuvent s'intercaler, jamais l'inverse) et « une seule fois » (0, 1 et 2 appels) |
| validation | l'environnement refuse une date fausse, une heure sans date, un nom réservé, du JSON invalide ; « masqué » vide le numéro |
| simulation | les appels d'un outil reçoivent leurs réponses DANS L'ORDRE (panne puis réponse) ; « * » vaut pour tout outil ; le compte est par outil |
| horloge | la date et l'heure du test sont celles que lisent le gabarit, les dates relatives et le greffier ; hors du test, la vraie |
| de bout en bout | un rejeu réel : le numéro, les variables et la panne simulée arrivent au run d'essai, la requête ne part pas |
| conversation entière | l'appel devient un scénario (paroles dans l'ordre), ses critères viennent de l'appel, l'organisation et l'agent sont contrôlés |
| scénarios types | « Nombres en français » et « Outil en panne » existent, leurs critères sont valides, l'environnement est copié dans le test |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import builder_tests as route
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import versement
from api.services.builder.bibliotheque import scenarios_types
from api.services.builder.tests_agent import creation, stockage, verdict
from api.services.builder.tests_agent.verdict import ObservationConversation
from api.services.tests_rejouables import environnement as env
from api.services.tests_rejouables.modele import ErreurTestRejouable, depuis_json
from api.services.tests_rejouables.rejeu import rejouer
from api.services.tests_rejouables.simulation import CLE_NOTES, CLE_REJEU, RESULTAT_NEUTRE, simuler_si_rejeu
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, utilisateur
from api.tests.mark.test_builder_tests_agent import banc, faux_run  # noqa: F401 -- la fixture et les aides du lot
from api.tests.mark.test_rejeu_outils_sortants_simules import (
    MODULE_HTTP,
    _appeler,
    _cerveau_qui_envoie,
    _monter,
    _requete_http,
    _test,
)
from api.tests.mark.test_tests_rejouables import _brancher
from api.utils.template_renderer import HORLOGE_SIMULEE, render_template

EQUIPE = utilisateur(1, ORG_CLIENT)


def obs(*outils, **plus):
    return ObservationConversation(outils=[{"nom": n, "arguments": {}, "rang": i} for i, n in enumerate(outils)], lignes=[("agent", "ok")], **plus)


# --- les deux critères ------------------------------------------------------------------------------------------------------


def test_dans_cet_ordre_tolere_un_outil_intercale_et_refuse_l_inverse_ou_l_absent():
    critere = {"type": "outils_dans_l_ordre", "noms": ["chercher", "reserver"]}
    assert verdict.evaluer_un(critere, obs("chercher", "reserver")).reussi
    assert verdict.evaluer_un(critere, obs("chercher", "noter", "reserver")).reussi
    inverse = verdict.evaluer_un(critere, obs("reserver", "chercher"))
    assert not inverse.reussi and "reserver" in inverse.detail and inverse.rang is not None and inverse.raison
    absent = verdict.evaluer_un(critere, obs("chercher"))
    assert not absent.reussi and "jamais appelé" in absent.detail
    # un outil appelé deux fois : la seconde place peut tenir l'ordre
    assert verdict.evaluer_un(critere, obs("reserver", "chercher", "reserver")).reussi


def test_une_seule_fois_compte_les_appels_et_montre_la_replique_du_deuxieme():
    critere = {"type": "outil_une_seule_fois", "nom": "envoyer_sms"}
    assert verdict.evaluer_un(critere, obs("noter", "envoyer_sms")).reussi
    deux = verdict.evaluer_un(critere, obs("envoyer_sms", "noter", "envoyer_sms"))
    assert not deux.reussi and "2 fois" in deux.detail and deux.rang == 2
    zero = verdict.evaluer_un(critere, obs("noter"))
    assert not zero.reussi and "0 fois" in zero.detail


def test_les_deux_criteres_se_valident_et_se_lisent_dans_la_liste_des_types():
    assert {"outils_dans_l_ordre", "outil_une_seule_fois"} <= set(verdict.TYPES)
    (propre,) = verdict.valider_criteres([{"type": "outils_dans_l_ordre", "noms": [" a ", "b"], "inutile": 1}])
    assert propre == {"type": "outils_dans_l_ordre", "noms": ["a", "b"]}
    assert verdict.valider_criteres([{"type": "outil_une_seule_fois", "nom": "x"}])
    for mauvais in ({"type": "outils_dans_l_ordre", "noms": ["a"]}, {"type": "outil_une_seule_fois", "nom": " "}):
        with pytest.raises(ErreurTestRejouable):
            verdict.valider_criteres([mauvais])


# --- la validation de l'environnement ---------------------------------------------------------------------------------------


def test_un_environnement_vide_n_existe_pas_et_un_bon_est_garde_propre():
    assert env.valider(None) is None and env.valider({}) is None and env.valider({"variables": {}, "simulations": []}) is None
    propre = env.valider(
        {
            "date": "2026-11-08",
            "heure": "19:40",
            "numero": "06 39 98 00 01",
            "variables": {"etablissement": "Beauvais"},
            "simulations": [{"outil": "chercher", "appels": [{"sorte": "delai"}, {"sorte": "reponse", "corps": '{"creneaux": ["lundi"]}'}]}],
        }
    )
    assert propre["simulations"][0]["appels"] == [{"sorte": "delai", "corps": None}, {"sorte": "reponse", "corps": {"creneaux": ["lundi"]}}]
    assert propre["variables"] == {"etablissement": "Beauvais"} and propre["masque"] is False


def test_masque_vide_le_numero_et_les_valeurs_fausses_sont_refusees_avec_la_raison():
    assert env.valider({"numero": "06 39 98 00 01", "masque": True})["numero"] == ""
    assert env.contexte_initial(env.valider({"numero": "06 39 98 00 01", "variables": {"a": "1"}})) == {"a": "1", "caller_number": "06 39 98 00 01"}
    assert "caller_number" not in env.contexte_initial(env.valider({"numero": "06 39 98 00 01", "masque": True}))
    mauvais = [
        {"date": "08/11/2026"},
        {"heure": "19:40"},
        {"date": "2026-11-08", "heure": "25:00"},
        {"variables": {"caller_number": "x"}},
        {"variables": {"Nom Faux": "x"}},
        {"simulations": [{"outil": "a", "appels": []}]},
        {"simulations": [{"outil": "a", "appels": [{"sorte": "bizarre"}]}]},
        {"simulations": [{"outil": "a", "appels": [{"sorte": "reponse", "corps": "{pas du json"}]}]},
        {"simulations": [{"outil": "a", "appels": [{"sorte": "erreur"}]}, {"outil": "A", "appels": [{"sorte": "erreur"}]}]},
        "texte",
    ]
    for brut in mauvais:
        with pytest.raises(ErreurTestRejouable):
            env.valider(brut)


# --- les réponses d'outils simulées -----------------------------------------------------------------------------------------


def _moteur(environnement):
    return SimpleNamespace(_gathered_context={CLE_REJEU: True, **env.fiche_du_rejeu(env.valider(environnement))}, _fiche=SimpleNamespace(champs=()))


async def _vrai(params):  # pragma: no cover
    raise AssertionError("l'outil ne doit jamais s'exécuter au rejeu")


@pytest.mark.asyncio
async def test_en_panne_au_premier_appel_puis_la_reponse_puis_la_derniere_se_repete():
    moteur = _moteur({"simulations": [{"outil": "chercher", "appels": [{"sorte": "delai"}, {"sorte": "reponse", "corps": {"creneaux": ["lundi"]}}]}]})
    simule = simuler_si_rejeu(moteur, "http_api", "chercher", _vrai)
    rendus = [(await _appeler(simule, jour="lundi"))[0] for _ in range(3)]
    assert rendus[0]["status"] == "error" and "in time" in rendus[0]["error"]
    assert rendus[1] == rendus[2] == {"creneaux": ["lundi"]}
    assert [n["nom"] for n in moteur._gathered_context[CLE_NOTES]] == ["chercher"] * 3


@pytest.mark.asyncio
async def test_une_etoile_vaut_pour_tout_autre_outil_et_le_compte_est_par_outil():
    moteur = _moteur({"simulations": [{"outil": "*", "appels": [{"sorte": "erreur"}, {"sorte": "reponse", "corps": {}}]}]})
    a = simuler_si_rejeu(moteur, "http_api", "alpha", _vrai)
    b = simuler_si_rejeu(moteur, "mcp", "beta", _vrai)
    premiers = [(await _appeler(a))[0], (await _appeler(b))[0]]
    assert all(r["status"] == "error" for r in premiers)  # chaque outil a SON premier appel en panne
    assert (await _appeler(a))[0] == {} and (await _appeler(b))[0] == {}
    precis = _moteur({"simulations": [{"outil": "*", "appels": [{"sorte": "refus"}]}, {"outil": "alpha", "appels": [{"sorte": "reponse", "corps": {"ok": 1}}]}]})
    assert (await _appeler(simuler_si_rejeu(precis, "http_api", "alpha", _vrai)))[0] == {"ok": 1}  # la réponse du nom prime sur « * »
    assert "refused" in (await _appeler(simuler_si_rejeu(precis, "http_api", "gamma", _vrai)))[0]["error"]


@pytest.mark.asyncio
async def test_sans_simulation_pour_l_outil_la_reponse_neutre_s_applique():
    moteur = _moteur({"simulations": [{"outil": "chercher", "appels": [{"sorte": "erreur"}]}]})
    assert await _appeler(simuler_si_rejeu(moteur, "http_api", "envoyer", _vrai)) == [RESULTAT_NEUTRE]
    assert await _appeler(simuler_si_rejeu(_moteur(None), "http_api", "envoyer", _vrai)) == [RESULTAT_NEUTRE]


# --- l'horloge --------------------------------------------------------------------------------------------------------------


def test_la_date_et_l_heure_du_test_sont_lues_par_le_gabarit_les_dates_relatives_et_le_greffier():
    from api.services.pipecat.greffier import date_du_jour
    from api.services.workflow.dates_relatives import aujourd_hui

    avant = render_template("{{current_time_Europe/Paris}}", {})
    fixe = env.valider({"date": "2026-11-08", "heure": "19:40"})
    with env.horloge(fixe):
        assert render_template("{{current_time_Europe/Paris}}", {}).startswith("2026-11-08 19:40")
        assert render_template("{{current_weekday_Europe/Paris}}", {}) == "Sunday"
        assert aujourd_hui().isoformat().startswith("2026-11-08T19:40")
        assert date_du_jour() == "Nous sommes le dimanche 8 novembre 2026."
    assert render_template("{{current_time_Europe/Paris}}", {}) != "2026-11-08 19:40:00 CET"
    assert render_template("{{current_time_Europe/Paris}}", {}).startswith(avant[:10])  # la vraie horloge est revenue
    with env.horloge(env.valider({"numero": "06 39 98 00 01"})):  # sans date : rien n'est posé
        assert HORLOGE_SIMULEE.get() is None
    assert HORLOGE_SIMULEE.get() is None


# --- de bout en bout : un rejeu qui reçoit l'environnement ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_un_rejeu_recoit_le_numero_les_variables_et_la_panne_simulee_sans_envoyer_de_requete(db_session, async_session):
    org, copie, outil = await _monter(db_session, async_session)
    client, session = _requete_http()
    _, enregistrements = _brancher(["inutile"])
    test = _test(org.id)
    test.environnement = env.valider(
        {
            "date": "2026-11-08",
            "heure": "19:40",
            "numero": "06 39 98 00 01",
            "variables": {"etablissement": "Beauvais"},
            "simulations": [{"outil": "envoyer_sms", "appels": [{"sorte": "erreur"}]}],
        }
    )
    with (
        patch("api.services.workflow.text_chat_runner.create_llm_service", side_effect=_cerveau_qui_envoie("envoyer_sms")),
        enregistrements,
        patch(f"{MODULE_HTTP}.httpx.AsyncClient", client),
    ):
        resultat = await rejouer(test, copie.id, 1)
    essai = resultat.essais[0]
    assert essai.erreur is None, essai.erreur
    assert session.request.call_count == 0
    run = await db_session.get_workflow_run_by_id(essai.run_id)
    assert run.initial_context["caller_number"] == "06 39 98 00 01" and run.initial_context["etablissement"] == "Beauvais"
    assert run.gathered_context[env.CLE_COMPTEURS] == {"envoyer_sms": 1}  # la réponse écrite a bien été servie, une fois


def test_l_environnement_fait_l_aller_retour_du_format_de_test():
    brut = {
        "version": 1,
        "nom": "t",
        "replique": "bonjour",
        "critere": {"type": "texte_present", "texte": "x"},
        "environnement": {"date": "2026-11-08", "heure": "19:40", "masque": True},
    }
    test = depuis_json(brut)
    assert test.environnement["masque"] is True and test.en_json()["environnement"]["date"] == "2026-11-08"
    assert depuis_json({**brut, "environnement": None}).environnement is None
    with pytest.raises(ErreurTestRejouable):
        depuis_json({**brut, "environnement": {"date": "demain"}})


# --- l'environnement dans un test de l'agent --------------------------------------------------------------------------------


async def test_un_test_garde_son_environnement_se_modifie_et_se_retire(banc):
    cree = await creation.creer(
        ORG_CLIENT,
        AGENT,
        nom="Avec environnement",
        criteres=[{"type": "sans_rigidite"}],
        scenario="Veut un rendez-vous.",
        environnement={"date": "2026-11-08", "heure": "19:40", "simulations": [{"outil": "chercher", "appels": [{"sorte": "delai"}]}]},
    )
    assert cree["environnement"]["heure"] == "19:40" and creation.en_resume(cree)["avec_environnement"] is True
    change = await creation.modifier(ORG_CLIENT, AGENT, cree["slug"], environnement={"masque": True})
    assert change["environnement"]["masque"] is True and "simulations" in change["environnement"] and change["environnement"]["simulations"] == []
    retire = await creation.modifier(ORG_CLIENT, AGENT, cree["slug"], environnement={})
    assert "environnement" not in retire and creation.en_resume(retire)["avec_environnement"] is False
    with pytest.raises(ErreurTestRejouable):
        await creation.creer(ORG_CLIENT, AGENT, nom="Faux", criteres=[{"type": "sans_rigidite"}], scenario="x", environnement={"date": "faux"})


async def test_un_test_de_conversation_joue_son_environnement_dans_la_session(banc):
    """``jouer_une_conversation`` passe le test entier au moteur : l'environnement y est, tel que rangé."""
    from api.services.builder.tests_agent import jeu

    cree = await creation.creer(
        ORG_CLIENT, AGENT, nom="Joué", criteres=[{"type": "sans_rigidite"}], scenario="Veut un rendez-vous.", environnement={"numero": "06 39 98 00 01"}
    )
    vus = []

    async def ouvrir(workflow, test):
        vus.append(test.get("environnement"))
        return jeu.Session(1), jeu.TourAgent("Bonjour", True)

    moteur = jeu.Moteur(ouvrir, AsyncMock(), AsyncMock(return_value=ObservationConversation()), AsyncMock())
    await jeu.jouer_une_conversation(SimpleNamespace(), cree, SimpleNamespace(repondre=AsyncMock(return_value="oui")), moteur, adieux=("au revoir",))
    assert vus == [{"date": "", "heure": "", "numero": "06 39 98 00 01", "masque": False, "variables": {}, "simulations": []}]


# --- depuis une conversation entière ----------------------------------------------------------------------------------------


def un_run_entier(agent=AGENT):
    t = iter(f"2026-11-02T10:00:{i:02d}+00:00" for i in range(60))

    def ev(genre, payload):
        return {"type": genre, "payload": payload, "timestamp": next(t)}

    return SimpleNamespace(
        logs={
            "realtime_feedback_events": [
                ev("rtf-bot-text", {"text": "Bonjour, que puis-je faire ?"}),
                ev("rtf-user-transcription", {"text": "Je voudrais un créneau mardi.", "final": True}),
                ev("rtf-function-call-start", {"function_name": "chercher", "arguments": {}}),
                ev("rtf-function-call-start", {"function_name": "chercher", "arguments": {}}),
                ev("rtf-bot-text", {"text": "Mardi à 14 h, cela vous va ?"}),
                ev("rtf-user-transcription", {"text": "Oui, au nom de Marie Dupont, marie.dupont@gmail.com.", "final": True}),
                ev("rtf-function-call-start", {"function_name": "reserver", "arguments": {}}),
                ev("rtf-bot-text", {"text": "C'est noté."}),
            ]
        },
        gathered_context={"call_disposition": "rdv_pris", "nom_client": "Marie Dupont"},
        workflow=SimpleNamespace(name="agent"),
        workflow_id=agent,
    )


async def test_une_conversation_entiere_devient_un_scenario_dont_les_criteres_viennent_de_l_appel(banc, monkeypatch):
    from api.services.tests_rejouables import creation as amont

    monkeypatch.setattr(amont, "db_client", banc)
    banc.get_workflow_run_with_context = AsyncMock(return_value=(un_run_entier(), ORG_CLIENT))
    test = await creation.creer_depuis_une_conversation(ORG_CLIENT, AGENT, 77, nom="Rendez-vous entier")
    assert test["origine"] == "client" and test["source"] == {"run_id": 77, "conversation_entiere": True}
    assert "1. Je voudrais un créneau mardi." in test["scenario"]["but"] and test["scenario"]["ouverture"] == "Je voudrais un créneau mardi."
    assert test["scenario"]["tours_max"] == 4
    assert test["criteres"] == [{"type": "issue", "attendue": "rdv_pris"}, {"type": "outils_dans_l_ordre", "noms": ["chercher", "reserver"]}]
    brut = str(test)
    assert "Marie Dupont" not in brut and "gmail" not in brut  # données personnelles rendues fictives
    assert creation.en_resume(test)["genre"] == "conversation"


async def test_une_conversation_d_une_autre_organisation_ou_d_un_autre_agent_est_refusee(banc, monkeypatch):
    from api.services.tests_rejouables import creation as amont

    monkeypatch.setattr(amont, "db_client", banc)
    banc.get_workflow_run_with_context = AsyncMock(return_value=(un_run_entier(), 999))
    with pytest.raises(ErreurTestRejouable, match="introuvable"):
        await creation.creer_depuis_une_conversation(ORG_CLIENT, AGENT, 77, nom="x")
    banc.get_workflow_run_with_context = AsyncMock(return_value=(un_run_entier(agent=AGENT + 1), ORG_CLIENT))
    with pytest.raises(stockage.ErreurTest, match="another agent"):
        await creation.creer_depuis_une_conversation(ORG_CLIENT, AGENT, 77, nom="x")
    banc.get_workflow_run_with_context = AsyncMock(return_value=(None, ORG_CLIENT))
    with pytest.raises(ErreurTestRejouable, match="introuvable"):
        await creation.creer_depuis_une_conversation(ORG_CLIENT, AGENT, 77, nom="x")


async def test_un_appel_sans_rien_a_juger_demande_un_critere(banc, monkeypatch):
    from api.services.tests_rejouables import creation as amont

    run = un_run_entier()
    run.gathered_context = {}
    run.logs["realtime_feedback_events"] = [e for e in run.logs["realtime_feedback_events"] if e["type"] != "rtf-function-call-start"]
    monkeypatch.setattr(amont, "db_client", banc)
    banc.get_workflow_run_with_context = AsyncMock(return_value=(run, ORG_CLIENT))
    with pytest.raises(stockage.ErreurTest, match="Nothing to check"):
        await creation.creer_depuis_une_conversation(ORG_CLIENT, AGENT, 77, nom="x")
    test = await creation.creer_depuis_une_conversation(ORG_CLIENT, AGENT, 77, nom="x", criteres=[{"type": "sans_redite"}])
    assert test["criteres"] == [{"type": "sans_redite"}]


def test_la_route_depuis_une_conversation_cree_et_repond_404_pour_un_autre_client(banc, monkeypatch):
    from api.services.tests_rejouables import creation as amont

    monkeypatch.setattr(route, "db_client", banc)
    monkeypatch.setattr(amont, "db_client", banc)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: EQUIPE
    c = TestClient(app)
    banc.get_workflow_run_with_context = AsyncMock(return_value=(un_run_entier(), ORG_CLIENT))
    ok = c.post(f"/builder/tests/{AGENT}/depuis-une-conversation", json={"run_id": 77, "nom": "Entier"})
    assert ok.status_code == 200 and ok.json()["test"]["genre"] == "conversation"
    banc.get_workflow_run_with_context = AsyncMock(return_value=(un_run_entier(), 999))
    autre = c.post(f"/builder/tests/{AGENT}/depuis-une-conversation", json={"run_id": 78, "nom": "Autre"})
    assert autre.status_code == 404
    assert c.post(f"/builder/tests/{AGENT}/depuis-une-conversation", json={"run_id": 0, "nom": "x"}).status_code == 422


# --- les deux scénarios types -----------------------------------------------------------------------------------------------


@pytest.fixture
async def verse(monde):
    rapport = await versement.verser()
    assert rapport.erreurs == [], rapport.erreurs
    return rapport


async def test_les_scenarios_nombres_en_francais_et_outil_en_panne_existent_et_se_copient_avec_leur_environnement(verse, monde):
    from api.services.builder.bibliotheque import service

    nombres = await service.lire_element("scenarios-test", "nombres-en-francais")
    panne = await service.lire_element("scenarios-test", "outil-en-panne")
    for element in (nombres, panne):
        verdict.valider_criteres(element.courante.contenu["criteres"])
        assert (await service.element_ou_none("personnages-appelant", element.courante.contenu["personnage"])) is not None
    workflow = monde.workflows[AGENT]
    rendu = await scenarios_types.copier(workflow, ORG_CLIENT, "outil-en-panne", "evan", copier_quand_meme=True)
    assert rendu["copie"] is True
    (test,) = [t for t in await stockage.lister(ORG_CLIENT, AGENT) if t["nom"] == panne.titre]
    assert test["environnement"]["simulations"][0]["outil"] == "*"
    assert [a["sorte"] for a in test["environnement"]["simulations"][0]["appels"]] == ["delai", "reponse"]
    rendu = await scenarios_types.copier(workflow, ORG_CLIENT, "nombres-en-francais", "evan", copier_quand_meme=True)
    assert rendu["copie"] is True and "environnement" not in [t for t in await stockage.lister(ORG_CLIENT, AGENT) if t["nom"] == nombres.titre][0]


@pytest.mark.asyncio
async def test_une_conversation_libre_joue_sur_la_vraie_session_avec_son_environnement(db_session, async_session):
    """Le chemin d'une conversation simulée (``jeu.moteur_texte``) : numéro, variables et panne simulée arrivent au run d'essai."""
    from api.services.builder.tests_agent import jeu

    org, copie, outil = await _monter(db_session, async_session)
    client, session = _requete_http()
    _, enregistrements = _brancher(["inutile"])
    reel = jeu.moteur_texte()
    runs = []

    async def ouvrir(workflow, test):
        ouverte, tour = await reel.ouvrir(workflow, test)
        runs.append(ouverte.run_id)
        return ouverte, tour

    moteur = jeu.Moteur(ouvrir, reel.tour, reel.lire, reel.clore)
    test = {
        "slug": "libre",
        "scenario": {"but": "Veut un SMS", "ouverture": "Envoyez-moi un SMS", "tours_max": 2},
        "environnement": env.valider(
            {"numero": "06 39 98 00 01", "variables": {"etablissement": "Beauvais"}, "simulations": [{"outil": "*", "appels": [{"sorte": "refus"}]}]}
        ),
    }
    with (
        patch("api.services.workflow.text_chat_runner.create_llm_service", side_effect=_cerveau_qui_envoie("envoyer_sms")),
        enregistrements,
        patch(f"{MODULE_HTTP}.httpx.AsyncClient", client),
    ):
        workflow = await db_session.get_workflow_by_id(copie.id)
        await jeu.jouer_une_conversation(workflow, test, SimpleNamespace(repondre=AsyncMock(return_value="au revoir")), moteur, tours_max=1, adieux=("au revoir",))
    assert session.request.call_count == 0
    run = await db_session.get_workflow_run_by_id(runs[0])
    assert run.initial_context["caller_number"] == "06 39 98 00 01" and run.initial_context["etablissement"] == "Beauvais"
    assert run.gathered_context[env.CLE_COMPTEURS] == {"envoyer_sms": 1}
