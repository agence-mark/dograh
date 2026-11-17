"""[.mark] Agent fiable (17/11, appel 2624) : l'état ouvre les portes. Une porte ``fermee_si_action_ouverte`` n'est pas offerte au modèle
tant qu'un connecteur déclare une action ouverte ; le renoncement vide la commande et rouvre la porte. Aucun mot de métier.

| Test | Ce qu'il prouve |
|---|---|
| P1 | action ouverte : la porte réglée est retirée des outils de la requête, les autres restent |
| P2 | aucune action ouverte : rien n'est retiré (``None``) |
| P3 | une porte non réglée n'est jamais fermée |
| P4 | le renoncement (sens annulation) sur finaliser vide la commande |
"""

from __future__ import annotations

from types import SimpleNamespace

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.processors.aggregators.llm_context import LLMContext

from api.services.commande import action
from api.services.workflow import portes_fermees


def _arete(nom, fermable):
    data = SimpleNamespace(fermee_si_action_ouverte=True if fermable else None)
    return SimpleNamespace(data=data, get_function_name=lambda: nom)


def _moteur(ouverte: bool, fermable=True):
    noeud = SimpleNamespace(out_edges=[_arete("fin", fermable), _arete("retour", False)])
    return SimpleNamespace(active_agent=SimpleNamespace(current_node=noeud), _ouverte=ouverte)


def _contexte():
    outils = [FunctionSchema(name=n, description="x", properties={}, required=[]) for n in ("finaliser", "fin", "retour")]
    return LLMContext(messages=[{"role": "user", "content": "oui c'est parfait"}], tools=ToolsSchema(standard_tools=outils))


def _ouvertes(monkeypatch, valeur):
    from api.services.workflow import action_non_aboutie

    monkeypatch.setattr(action_non_aboutie, "actions_ouvertes", lambda moteur: [{"connecteur": "c", "outil": "finaliser"}] if valeur else [])


def test_p1_action_ouverte_la_porte_est_retiree(monkeypatch):
    _ouvertes(monkeypatch, True)
    copie = portes_fermees.contexte_sans_les_portes_fermees(_moteur(True), _contexte())
    assert copie is not None and [t.name for t in copie.tools.standard_tools] == ["finaliser", "retour"]


def test_p2_aucune_action_ouverte_rien_n_est_retire(monkeypatch):
    _ouvertes(monkeypatch, False)
    assert portes_fermees.contexte_sans_les_portes_fermees(_moteur(False), _contexte()) is None


def test_p3_une_porte_non_reglee_n_est_jamais_fermee(monkeypatch):
    _ouvertes(monkeypatch, True)
    assert portes_fermees.contexte_sans_les_portes_fermees(_moteur(True, fermable=False), _contexte()) is None


def test_p4_le_renoncement_vide_la_commande():
    p = {"lignes": [{"nom": "x"}], "question_en_attente": "finaliser.confirmer"}
    assert action.vers_la_question_en_attente(None, p, "finaliser", {"sens": "annulation", "mots": "laissez tomber"}) == ("voir_commande", {"vider": True})
