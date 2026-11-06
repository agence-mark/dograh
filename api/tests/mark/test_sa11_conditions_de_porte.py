"""[.mark] Partie 3, sous-lot 21 : les conditions complètes d'une porte (étude ``05-etude-conditions-du-graphe.md``).

La condition d'une porte (``ConditionDePorteDTO``) s'étend : règles (fiche, étape, résultat d'un outil, heure et jour,
établissement, variable de l'appel), « toutes » ou « au moins une », « toujours », « sinon ». Tout éteint par défaut, la
forme d'avant lue comme avant. Les tests du moteur passent par le VRAI moteur (banc fendu de ``test_agent_transfer.py``).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from api.services.pipecat.etat_ouverture import PARIS
from api.services.workflow import conditions_de_porte as cp
from api.services.workflow import decideur_de_fin_de_tour as decideur
from api.services.workflow import passage_sur_la_fiche as passage
from api.services.workflow.dto import (
    ConditionDePorteDTO,
    EdgeDataDTO,
    ReactFlowDTO,
    RegleDePorteDTO,
    RFEdgeDTO,
    sanitize_workflow_definition,
)
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_passages_fiables_fiche import GreffierFactice, _etape, _fin_de_reponse, _noeud, monter
from api.tests.mark.test_ra_b_r4_porte_fermee import _appeler_la_porte

# --------------------------------------------------------------------------- #
# Le banc
# --------------------------------------------------------------------------- #


def _arete(source, cible, nom, condition=None):
    return RFEdgeDTO(
        id=f"{source}-{cible}",
        source=source,
        target=cible,
        data=EdgeDataDTO(
            label=nom,
            condition=f"Quand {nom}.",
            condition_sur_la_fiche=ConditionDePorteDTO(**condition) if condition else None,
        ),
    )


def graphe(refus=None, suite=None, autre=None, *, etape=None, autre_vers_la_fin=False) -> WorkflowGraph:
    """Une étape (« la fiche puis l'arbitre » par défaut) et trois portes, dans l'ordre de l'écran : Refus, Suite, Autre."""
    reglages = {"champs_etape": "nom,objet", **({"qui_decide_du_passage": "choix"} if etape is None else etape)}
    noeuds = [
        _noeud("etape", "startCall", "Accueil", **reglages),
        _noeud("refus", "agentNode", "Refus"),
        _noeud("suite", "agentNode", "Suite"),
        *([] if autre_vers_la_fin else [_noeud("autre", "agentNode", "Autre")]),
        _noeud("fin", "endCall", "Fin"),
    ]
    aretes = [
        _arete("etape", "refus", "Refus", refus),
        _arete("etape", "suite", "Suite", suite),
        _arete("etape", "fin" if autre_vers_la_fin else "autre", "Autre", autre),
        _arete("refus", "fin", "Fin du refus"),
        _arete("suite", "fin", "Fin de la suite"),
        *([] if autre_vers_la_fin else [_arete("autre", "fin", "Fin de l'autre")]),
    ]
    return WorkflowGraph(ReactFlowDTO(nodes=noeuds, edges=aretes))


def regle(source, champ, comparaison, valeur=""):
    return {"source": source, "champ": champ, "comparaison": comparaison, "valeur": valeur}


def outil_ok(nom="reserver_creneau", statut="completed", resultat=None):
    return {"function_name": nom, "status": statut, "result": resultat if resultat is not None else {"status": "ok"}}


def _parole():
    from pipecat.processors.aggregators.llm_context import LLMContext

    return LLMContext(messages=[{"role": "assistant", "content": "Que souhaitez-vous ?"}, {"role": "user", "content": "Euh."}])


def _moteur(fiche=None, contexte=None):
    return SimpleNamespace(_gathered_context=dict(fiche or {}), _call_context_vars=dict(contexte or {}), _fiche=None)


# --------------------------------------------------------------------------- #
# La lecture : la forme d'avant ne change pas
# --------------------------------------------------------------------------- #


def test_la_forme_d_avant_se_lit_comme_avant():
    assert cp.lecture_de(None) is None
    assert cp.lecture_de(ConditionDePorteDTO()) is None
    assert cp.lecture_de(ConditionDePorteDTO(etape_complete=True)) == {"type": "etape_complete"}
    assert cp.lecture_de(ConditionDePorteDTO(champ="objet", vaut="refusé")) == {"type": "champ", "champ": "objet", "vaut": "refusé"}
    assert cp.lecture_de(ConditionDePorteDTO(champ="objet")) == {"type": "champ", "champ": "objet", "vaut": ""}


def test_le_json_d_un_agent_d_avant_ne_change_pas():
    definition = {
        "nodes": [],
        "edges": [
            {"id": "a", "source": "1", "target": "2", "data": {"label": "A", "condition": "a", "condition_sur_la_fiche": {"champ": "objet", "vaut": "refusé"}}},
            {"id": "b", "source": "1", "target": "3", "data": {"label": "B", "condition": "b", "condition_sur_la_fiche": {"etape_complete": False}}},
        ],
    }
    propre = sanitize_workflow_definition(json.loads(json.dumps(definition)))
    assert propre["edges"][0]["data"]["condition_sur_la_fiche"] == {"champ": "objet", "vaut": "refusé"}
    assert "condition_sur_la_fiche" not in propre["edges"][1]["data"]


def test_les_conditions_nouvelles_sont_gardees_et_les_cles_vides_retirees():
    definition = {
        "nodes": [],
        "edges": [
            {"id": "a", "source": "1", "target": "2", "data": {"label": "A", "condition": "a", "condition_sur_la_fiche": {"regles": [regle("outil", "reserver", "a_reussi")], "combien": "toutes", "sinon": None}}},
            {"id": "b", "source": "1", "target": "3", "data": {"label": "B", "condition": "b", "condition_sur_la_fiche": {"sinon": True, "regles": []}}},
            {"id": "c", "source": "1", "target": "4", "data": {"label": "C", "condition": "c", "condition_sur_la_fiche": {"toujours": True}}},
        ],
    }
    e = sanitize_workflow_definition(definition)["edges"]
    assert e[0]["data"]["condition_sur_la_fiche"] == {"regles": [regle("outil", "reserver", "a_reussi")], "combien": "toutes"}
    assert e[1]["data"]["condition_sur_la_fiche"] == {"sinon": True}
    assert e[2]["data"]["condition_sur_la_fiche"] == {"toujours": True}


@pytest.mark.parametrize(
    "mauvaise",
    [
        {"source": "inconnue", "champ": "x", "comparaison": "est"},
        {"source": "outil", "champ": "x", "comparaison": "est"},  # comparaison d'une autre source
        {"source": "fiche", "champ": "", "comparaison": "est"},  # sans champ
    ],
)
def test_une_regle_hors_des_listes_est_refusee(mauvaise):
    with pytest.raises(ValidationError):
        RegleDePorteDTO(**mauvaise)


def test_combien_et_sinon_toujours_sont_controles():
    with pytest.raises(ValidationError):
        ConditionDePorteDTO(combien="la_plupart")
    with pytest.raises(ValidationError):
        ConditionDePorteDTO(sinon=True, toujours=True)
    assert RegleDePorteDTO(source="etape", comparaison="est_complete").champ is None


# --------------------------------------------------------------------------- #
# Chaque source, chaque comparaison
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "r, fiche, attendu",
    [
        (regle("fiche", "objet", "est", "Devis"), {"objet": "devis"}, True),
        (regle("fiche", "objet", "est", "devis"), {"objet": "autre"}, False),
        (regle("fiche", "objet", "n_est_pas", "devis"), {"objet": "autre"}, True),
        (regle("fiche", "objet", "n_est_pas", "devis"), {}, False),  # absente : on ne sait pas
        (regle("fiche", "objet", "contient", "chaud"), {"objet": "Chaudière en panne"}, True),
        (regle("fiche", "objet", "contient", "eau"), {"objet": "Chaudière"}, False),
        (regle("fiche", "objet", "est_rempli"), {"objet": "x"}, True),
        (regle("fiche", "objet", "est_rempli"), {"objet": "  "}, False),
        (regle("fiche", "objet", "est_vide"), {}, True),
        (regle("fiche", "objet", "est_vide"), {"objet": "x"}, False),
        (regle("fiche", "age", "plus_grand", "18"), {"age": "21"}, True),
        (regle("fiche", "age", "plus_grand", "18"), {"age": 12}, False),
        (regle("fiche", "age", "plus_petit", "2,5"), {"age": "1,5"}, True),
        (regle("fiche", "age", "plus_petit", "2"), {"age": "deux"}, False),  # illisible : fausse
        (regle("fiche", "objet", "est", "devis"), {"objet": "devis", "fiche_etat": {"objet": {"sure": False}}}, False),
        (regle("fiche", "options", "est", "b"), {"options": ["a", "B"]}, True),
    ],
)
def test_la_fiche(r, fiche, attendu):
    assert cp.regle_vraie(_moteur(fiche), None, r) is attendu


@pytest.mark.parametrize(
    "r, contexte, attendu",
    [
        (regle("variable", "canal", "est", "site"), {"canal": "Site"}, True),
        (regle("variable", "canal", "n_est_pas", "site"), {"canal": "téléphone"}, True),
        (regle("variable", "canal", "est_vide"), {}, True),
        (regle("variable", "score", "plus_grand", "3"), {"score": 4}, True),
        (regle("etablissement", "ouvert", "est_vrai"), {"etat_ouverture": "OUVERT"}, True),
        (regle("etablissement", "ouvert", "est_faux"), {"etat_ouverture": "FERME"}, True),
        (regle("etablissement", "ouvert", "est_faux"), {"etat_ouverture": "OUVERT"}, False),
        (regle("etablissement", "ouvert", "est_vrai"), {}, False),  # sans horaires : on ne sait pas
        (regle("etablissement", "ouvert", "est_faux"), {}, False),
        (regle("etablissement", "etat", "est", "pause"), {"etat_ouverture": "PAUSE"}, True),
        (regle("etablissement", "nom", "est", "Beauvais"), {"etablissement": "beauvais"}, True),
        (regle("etablissement", "nom", "contient", "Paris"), {"etablissement": "Beauvais"}, False),
    ],
)
def test_la_variable_et_l_etablissement(r, contexte, attendu):
    assert cp.regle_vraie(_moteur(contexte=contexte), None, r) is attendu


@pytest.mark.parametrize(
    "r, resultats, attendu",
    [
        (regle("outil", "reserver", "a_reussi"), [outil_ok("reserver")], True),
        (regle("outil", "reserver", "a_reussi"), [outil_ok("reserver", resultat={"status": "error"})], False),
        (regle("outil", "reserver", "a_reussi"), [outil_ok("reserver", statut="timeout")], False),
        (regle("outil", "reserver", "a_reussi"), [outil_ok("reserver", resultat={"success": False})], False),
        (regle("outil", "reserver", "a_echoue"), [outil_ok("reserver", statut="failed")], True),
        (regle("outil", "reserver", "a_echoue"), [], False),  # jamais appelé : ni réussi ni échoué
        # Le DERNIER résultat de l'outil compte.
        (regle("outil", "reserver", "a_reussi"), [outil_ok("reserver", statut="failed"), outil_ok("reserver")], True),
        (regle("outil", "reserver", "a_repondu"), [outil_ok("reserver")], True),
        (regle("outil", "reserver", "a_repondu"), [outil_ok("autre")], False),
        (regle("outil", "reserver", "n_a_pas_repondu"), [outil_ok("autre")], True),
        (regle("outil", "reserver", "n_a_pas_repondu"), [outil_ok("reserver")], False),
    ],
)
def test_le_resultat_d_un_outil(r, resultats, attendu):
    assert cp.regle_vraie(_moteur({"tool_results": resultats}), None, r) is attendu


@pytest.mark.parametrize(
    "r, instant, attendu",
    [
        (regle("heure", "heure", "apres", "18:00"), datetime(2026, 11, 5, 18, 0, tzinfo=PARIS), True),
        (regle("heure", "heure", "apres", "18h"), datetime(2026, 11, 5, 17, 59, tzinfo=PARIS), False),
        (regle("heure", "heure", "avant", "9:30"), datetime(2026, 11, 5, 9, 29, tzinfo=PARIS), True),
        (regle("heure", "heure", "avant", "midi"), datetime(2026, 11, 5, 9, 0, tzinfo=PARIS), False),  # illisible
        (regle("heure", "heure", "est", "12:00"), datetime(2026, 11, 5, 12, 0, tzinfo=PARIS), True),
        (regle("heure", "heure", "n_est_pas", "12:00"), datetime(2026, 11, 5, 12, 0, tzinfo=PARIS), False),
        # Le 07/11/2026 est un samedi.
        (regle("heure", "jour", "est", "samedi, dimanche"), datetime(2026, 11, 7, 10, 0, tzinfo=PARIS), True),
        (regle("heure", "jour", "est", "Lundi"), datetime(2026, 11, 7, 10, 0, tzinfo=PARIS), False),
        (regle("heure", "jour", "n_est_pas", "samedi,dimanche"), datetime(2026, 11, 5, 10, 0, tzinfo=PARIS), True),
    ],
)
def test_l_heure_et_le_jour(r, instant, attendu, monkeypatch):
    monkeypatch.setattr(cp, "_maintenant", lambda: instant)
    assert cp.regle_vraie(_moteur(), None, r) is attendu


def test_l_etape_complete_en_regle():
    # Sans fiche, une étape n'est jamais complète (même lecture que la forme d'avant).
    assert cp.regle_vraie(_moteur(), None, regle("etape", "", "est_complete")) is False
    assert cp.regle_vraie(_moteur(), None, regle("etape", "", "n_est_pas_complete")) is True


def test_toutes_ou_au_moins_une():
    m = _moteur({"objet": "devis"}, {"canal": "site"})
    vraie, fausse = regle("fiche", "objet", "est", "devis"), regle("variable", "canal", "est", "téléphone")
    toutes = cp.lecture_de({"regles": [vraie, fausse]})
    une = cp.lecture_de({"regles": [vraie, fausse], "combien": "au_moins_une"})
    assert toutes["combien"] == "toutes" and cp.condition_vraie(m, None, toutes) is False
    assert cp.condition_vraie(m, None, une) is True
    # L'ancienne forme, quand des règles s'y ajoutent, devient une règle de plus (rien n'est oublié).
    mixte = cp.lecture_de({"champ": "objet", "vaut": "autre", "regles": [vraie], "combien": "toutes"})
    assert cp.condition_vraie(m, None, mixte) is False


def test_une_regle_illisible_rend_la_condition_fausse():
    lecture = cp.lecture_de({"regles": [{"source": "fiche", "champ": "objet", "comparaison": "inventee"}], "combien": "au_moins_une"})
    assert lecture["illisible"] is True
    assert cp.condition_vraie(_moteur({"objet": "x"}), None, lecture) is False


# --------------------------------------------------------------------------- #
# Le vrai moteur
# --------------------------------------------------------------------------- #

RESERVATION_OK = {"regles": [regle("outil", "reserver_creneau", "a_reussi")]}


@pytest.mark.asyncio
async def test_une_regle_vraie_le_code_prend_la_porte_a_la_fin_de_la_reponse():
    harness = await monter(graphe(suite=RESERVATION_OK), fiche={"tool_results": [outil_ok()]}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche" and _etape(engine) == "suite"
        trace = engine._gathered_context[passage.CLE_PASSAGES][-1]
        assert trace["porte"] == "suite" and trace["resultat"] == "prise"
        assert trace["condition"]["type"] == "regles" and trace["condition"]["regles"][0]["source"] == "outil"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_regle_fausse_ferme_la_porte_au_modele_et_vraie_l_ouvre():
    harness = await monter(graphe(suite=RESERVATION_OK), fiche={"tool_results": [outil_ok(statut="failed")]})
    try:
        engine = harness.engine
        resultat = await _appeler_la_porte(engine, "suite")
        assert resultat["status"] == "closed" and _etape(engine) == "etape"
        assert engine._gathered_context[passage.CLE_PASSAGES][-1]["resultat"] == "fermee"
        engine._gathered_context["tool_results"].append(outil_ok())
        resultat = await _appeler_la_porte(engine, "suite")
        assert resultat["status"] == "done" and _etape(engine) == "suite"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_sur_une_etape_ou_le_modele_decide_rien_n_est_lu():
    # Nouveautés éteintes : en mode « agent », la règle ne ferme rien et ne prend rien, comme la forme d'avant.
    harness = await monter(
        graphe(suite=RESERVATION_OK, autre={"sinon": True}, refus={"toujours": True}, etape={"champs_etape": "nom,objet"}),
        fiche={}, greffier=GreffierFactice(),
    )
    try:
        engine = harness.engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui is None and _etape(engine) == "etape"
        assert await passage.sinon_avant_la_requete(engine, engine.active_agent.llm, _parole()) is False
        assert passage.CLE_PASSAGES not in engine._gathered_context
        assert engine.greffier.appels == []
        resultat = await _appeler_la_porte(engine, "suite")
        assert resultat["status"] == "done" and _etape(engine) == "suite"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_sinon_est_pris_apres_la_parole_quand_aucune_autre_porte_ne_passe():
    harness = await monter(graphe(suite=RESERVATION_OK, autre={"sinon": True}), fiche={}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        # À la fin de la réplique (d'arrivée), « sinon » n'est jamais pris : on n'a pas encore répondu à l'étape.
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui is None and _etape(engine) == "etape"
        # Après la parole de l'appelant, rien ne passe : « sinon » passe, avant la requête, sans relance.
        assert await passage.sinon_avant_la_requete(engine, engine.active_agent.llm, _parole()) is True
        assert _etape(engine) == "autre"
        engine.active_agent.queue_frame.assert_not_awaited()
        trace = engine._gathered_context[passage.CLE_PASSAGES][-1]
        assert trace["raison"] == "sinon" and trace["porte"] == "autre" and trace["option"] == 2
        assert trace["condition"] == {"type": "sinon"}
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_sinon_par_la_route_de_la_requete_apres_la_fiche_et_l_arbitre():
    # La route réelle d'une requête (téléphone et clavier) : option 2, fiche déjà vraie, arbitre, puis « sinon ».
    from api.services.pipecat.avant_la_requete import preparer_la_requete
    from pipecat.frames.frames import LLMContextFrame

    harness = await monter(graphe(suite=RESERVATION_OK, autre={"sinon": True}), fiche={}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        await preparer_la_requete(engine, engine.active_agent.llm, LLMContextFrame(context=_parole()))
        assert _etape(engine) == "autre"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_sinon_n_est_pas_pris_et_reste_ferme_quand_une_autre_porte_passe():
    harness = await monter(graphe(suite=RESERVATION_OK, autre={"sinon": True}), fiche={"tool_results": [outil_ok()]}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        assert await passage.sinon_avant_la_requete(engine, engine.active_agent.llm, _parole()) is False
        assert _etape(engine) == "etape"
        resultat = await _appeler_la_porte(engine, "autre")
        assert resultat["status"] == "closed" and _etape(engine) == "etape"
        # La porte vraie, elle, passe par son chemin (la fiche déjà vraie, avant la requête).
        assert await passage.fiche_deja_vraie_avant_la_requete(engine, engine.active_agent.llm, _parole()) is True
        assert _etape(engine) == "suite"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_sinon_vers_une_fin_se_prend_a_la_fin_de_la_reponse_avec_relance():
    harness = await monter(graphe(suite=RESERVATION_OK, autre={"sinon": True}, autre_vers_la_fin=True), fiche={}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        assert await passage.sinon_avant_la_requete(engine, engine.active_agent.llm, _parole()) is False
        assert _etape(engine) == "etape"
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "sinon" and _etape(engine) == "fin"
        trace = engine._gathered_context[passage.CLE_PASSAGES][-1]
        assert trace["raison"] == "sinon" and trace["option"] == 1
        # Marquée pour UNE parole seulement : rien de plus au tour suivant.
        assert passage.sinon_a_prendre_apres_la_reponse(engine, engine.jeton_de_visite()) is False
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_toujours_passe_des_que_l_etape_est_finie_et_n_est_jamais_fermee():
    harness = await monter(graphe(suite={"toujours": True}), fiche={}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche" and _etape(engine) == "suite"
        assert engine._gathered_context[passage.CLE_PASSAGES][-1]["condition"] == {"type": "toujours"}
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_premiere_porte_vraie_de_l_ecran_gagne_et_l_heure_est_lue(monkeypatch):
    monkeypatch.setattr(cp, "_maintenant", lambda: datetime(2026, 11, 5, 19, 0, tzinfo=PARIS))
    apres_18h = {"regles": [regle("etablissement", "ouvert", "est_faux"), regle("heure", "heure", "apres", "18:00")], "combien": "au_moins_une"}
    harness = await monter(graphe(refus=apres_18h, suite={"toujours": True}), fiche={}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche" and _etape(engine) == "refus"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_variable_de_l_appel_est_lue_par_le_moteur():
    harness = await monter(graphe(suite={"regles": [regle("variable", "canal", "est", "site")]}), fiche={}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        engine._call_context_vars = {**(engine._call_context_vars or {}), "canal": "site"}
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche" and _etape(engine) == "suite"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_l_arbitre_ne_passe_jamais_contre_une_regle_fausse(monkeypatch):
    from api.services.workflow import arbitre as arbitre_mod
    from api.tests.mark.test_passages_fiables_arbitre import ECHANGES, Collecteur, Faux, _reponse
    from pipecat.processors.aggregators.llm_context import LLMContext

    monkeypatch.setattr("api.services.pipecat.greffier.interroger", Faux(_reponse("refus", 0.97)))
    harness = await monter(
        graphe(refus=RESERVATION_OK, etape={"qui_decide_du_passage": "libre", "champs_etape": "nom,objet"}),
        fiche={}, greffier=GreffierFactice(),
    )
    try:
        engine = harness.engine
        engine.arbitre_service = object()
        engine.collecteur_de_cout = Collecteur()
        engine.arbitre = arbitre_mod.ArbitreDuPassage(engine)
        assert engine.arbitre.lancer(engine.jeton_de_visite(), engine.active_agent.current_node, ECHANGES, delai=3.0)
        contexte = LLMContext(messages=[dict(m) for m in ECHANGES])
        assert await decideur.arbitre_avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert _etape(engine) == "etape"
        assert engine._gathered_context[arbitre_mod.CLE_ARBITRE][-1]["resultat"] == "fermee_par_la_condition"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Le contrôle « sans effet » et le builder
# --------------------------------------------------------------------------- #


def test_une_regle_sur_une_etape_ou_le_modele_decide_est_signalee_sans_effet():
    from api.services.publication import sans_effet

    for condition in (RESERVATION_OK, {"sinon": True}, {"toujours": True}):
        definition = {
            "nodes": [
                {"id": "1", "type": "startCall", "data": {"name": "Accueil"}},
                {"id": "2", "type": "agentNode", "data": {"name": "Suite"}},
            ],
            "edges": [{"id": "1-2", "source": "1", "target": "2", "data": {"label": "Suite", "condition": "c", "condition_sur_la_fiche": condition}}],
        }
        assert any(c.cle == "condition_sur_le_modele" for c in sans_effet.evaluer(definition, {})), condition


CONDITION_COMPLETE = {
    "regles": [regle("outil", "reserver_creneau", "a_reussi"), regle("heure", "jour", "est", "samedi")],
    "combien": "au_moins_une",
}


def _stocke(condition_sinon=True):
    def noeud(i, type_, x, **data):
        return {"id": i, "type": type_, "position": {"x": x, "y": 0}, "data": data}

    return {
        "nodes": [
            noeud("1", "startCall", 0, name="Accueil", prompt="Bonjour", qui_decide_du_passage="choix"),
            noeud("2", "agentNode", 400, name="Rdv", prompt="Prends le rendez-vous"),
            noeud("3", "endCall", 800, name="Fin", prompt="Au revoir"),
        ],
        "edges": [
            {"id": "1-2", "source": "1", "target": "2", "data": {"label": "Rdv", "condition": "veut un rdv", "condition_sur_la_fiche": CONDITION_COMPLETE}},
            {"id": "1-3", "source": "1", "target": "3", "data": {"label": "Sinon", "condition": "autre chose", "condition_sur_la_fiche": {"sinon": True}}},
            {"id": "2-3", "source": "2", "target": "3", "data": {"label": "Fin", "condition": "fini"}},
        ],
    }


@pytest.fixture
def banc_builder():
    from api.mcp_server.tools.get_workflow_code import get_workflow_code  # noqa: F401 -- import des routes du builder

    stocke = _stocke()
    user = MagicMock()
    user.selected_organization_id = 1
    user.id = 1
    wf = SimpleNamespace(
        id=1, organization_id=1, name="test", current_definition=None,
        released_definition=None, workflow_definition=None, workflow_configurations={},
    )
    sauve = AsyncMock(return_value=SimpleNamespace(version_number=2, status="draft"))
    draft = SimpleNamespace(workflow_json=stocke, version_number=1, workflow_configurations={})
    with (
        patch("api.mcp_server.tools.save_workflow.authenticate_mcp_write", AsyncMock(return_value=user)),
        patch("api.mcp_server.tools.get_workflow_code.authenticate_mcp_request", AsyncMock(return_value=user)),
        patch("api.mcp_server.tools.save_workflow.db_client.get_workflow", AsyncMock(return_value=wf)),
        patch("api.mcp_server.tools.get_workflow_code.db_client.get_workflow", AsyncMock(return_value=wf)),
        patch("api.mcp_server.tools.save_workflow.db_client.get_draft_version", AsyncMock(return_value=draft)),
        patch("api.mcp_server.tools.save_workflow.db_client.save_workflow_draft", sauve),
        patch("api.mcp_server.tools.save_workflow.db_client.update_workflow", AsyncMock()),
    ):
        yield stocke, sauve


def _liaison(payload, source, cible):
    return next(e for e in payload["edges"] if e["source"] == source and e["target"] == cible)


@pytest.mark.skipif(shutil.which("node") is None, reason="node binary not available")
@pytest.mark.asyncio
async def test_aller_retour_du_builder_sans_perte(banc_builder):
    from api.mcp_server.tools.get_workflow_code import get_workflow_code
    from api.mcp_server.tools.save_workflow import save_workflow

    _, sauve = banc_builder
    code = (await get_workflow_code(1))["code"]
    res = await save_workflow(1, code)
    assert res["saved"] is True, res
    ecrit = sauve.call_args.kwargs["workflow_definition"]
    assert _liaison(ecrit, "1", "2")["data"]["condition_sur_la_fiche"] == CONDITION_COMPLETE
    assert _liaison(ecrit, "1", "3")["data"]["condition_sur_la_fiche"] == {"sinon": True}


@pytest.mark.skipif(shutil.which("node") is None, reason="node binary not available")
@pytest.mark.asyncio
async def test_renommer_une_porte_dans_le_builder_garde_sa_condition(banc_builder):
    from api.mcp_server.tools.get_workflow_code import get_workflow_code
    from api.mcp_server.tools.save_workflow import save_workflow

    _, sauve = banc_builder
    code = (await get_workflow_code(1))["code"]
    assert 'label: "Rdv"' in code
    res = await save_workflow(1, code.replace('label: "Rdv"', 'label: "Prendre un rendez-vous"'))
    assert res["saved"] is True, res
    liaison = _liaison(sauve.call_args.kwargs["workflow_definition"], "1", "2")
    assert liaison["data"]["label"] == "Prendre un rendez-vous"
    assert liaison["data"]["condition_sur_la_fiche"] == CONDITION_COMPLETE
    assert liaison["data"]["identifiant"] == "rdv"  # SA-9 : le nom de la porte ne change pas
