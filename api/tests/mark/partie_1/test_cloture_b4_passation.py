"""[.mark] Clôture de la Partie 1, lot B4 : la passation (audit du code M8, audit des textes § 3, inventaire C7).

* L'agent qui écrit la fiche d'un connecteur tient son action (noté par le code).
* Un détour (sortie ``garde_l_action_ouverte``) fini alors qu'une action reste ouverte chez un autre collègue : le code y ramène l'appel ; une
  sortie sans ce drapeau rend au principal, comme avant.
* Gabarit : chaque sortie d'une étape à action est fermée ou garde l'action (RC14) ; les spécialisés portent les passages vers leurs collègues.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from api.services.commande import etape
from api.services.commande import panier as P
from api.services.groupe import passations as PA
from api.tests.mark.partie_1.combinaisons import GABARIT


def _fiche_avec_une_commande_ouverte(porteur: int) -> dict:
    p = P.nouveau()
    p["lignes"] = [{"n": 1, "ref": "X", "nom": "Margherita Normale", "quantite": 1}]
    return {P.CLE: p, "conversation": {PA.CLE_PORTEURS: {"commande": porteur}}}  # lot 7a (122) : le porteur est un fait de la conversation


def test_le_porteur_d_une_action_ouverte():
    fiche = _fiche_avec_une_commande_ouverte(10)
    assert PA.porteur_de_l_action_ouverte(fiche, sauf=20) == 10
    assert PA.porteur_de_l_action_ouverte(fiche, sauf=10) is None  # l'agent qui la tient ne se rend pas à lui-même
    etape.transition(fiche[P.CLE], etape.ENREGISTREE_EN_CAISSE, faits={"numero": "n"}, empreinte="e")  # lot 2 : l'étape est la seule à écrire « enregistrée »
    assert PA.porteur_de_l_action_ouverte(fiche, sauf=20) is None  # finie : plus rien à reprendre


def _moteur(fiche: dict, *, detour: bool):
    from api.services.workflow.pipecat_engine import PipecatEngine

    arete = SimpleNamespace(target="retour", data=SimpleNamespace(garde_l_action_ouverte=True if detour else None))
    noeuds = {"reservation": SimpleNamespace(out_edges=[arete], is_end=False), "retour": SimpleNamespace(out_edges=[], is_end=False, data=SimpleNamespace(retour_au_principal=True))}
    agent = SimpleNamespace(workflow=SimpleNamespace(nodes=noeuds), reglages={PA.CLE_AGENT_PRINCIPAL: 1}, workflow_id=20)
    moteur = SimpleNamespace(_gathered_context=fiche, agent_transfer_enabled=True)
    return PipecatEngine._principal_du_retour.__get__(moteur), agent


def test_un_detour_fini_ramene_a_l_action_ouverte():
    principal_du_retour, agent = _moteur(_fiche_avec_une_commande_ouverte(10), detour=True)
    assert principal_du_retour(agent, "retour") == 10  # la réservation a fini : retour à la commande ouverte, par le code


def test_une_sortie_sans_detour_rend_au_principal():
    principal_du_retour, agent = _moteur(_fiche_avec_une_commande_ouverte(10), detour=False)
    assert principal_du_retour(agent, "retour") == 1


async def test_la_fiche_note_l_agent_qui_tient_l_action(monkeypatch):
    from api.services.integrations.connectors import outil
    from api.services.integrations.connectors.execution import Resultat as ResultatDeLAction

    async def executer(*a, **k):
        return ResultatDeLAction(statut="ok", donnees={"statut": "FAIT", "resultats": []}, duree_ms=1, message="")

    class Patience:
        def __init__(self, *a, **k): ...
        def demarrer(self): ...
        def arreter(self): ...

    monkeypatch.setattr(outil, "executer", executer)
    monkeypatch.setattr(outil, "resoudre", AsyncMock(return_value=({}, [])))
    monkeypatch.setattr(outil, "Patience", Patience)
    fiche = {"tour_de_la_personne": 2}
    engine = SimpleNamespace(_gathered_context=fiche, _call_context_vars={}, _workflow_run_id=1, greffier=None, queue_text_message=AsyncMock(return_value=True))
    manager = SimpleNamespace(_engine=engine, _agent=SimpleNamespace(workflow_id=10, reglages={}), get_organization_id=AsyncMock(return_value=1))
    tool = SimpleNamespace(name="fiche", definition={"config": {"connecteur": "commande", "action": "fiche"}})
    gestionnaire = outil.creer_gestionnaire(manager, tool, "fiche")

    async def rappel(resultat, *, properties=None): ...

    await gestionnaire(SimpleNamespace(arguments={"mode_de_retrait": "emporter", "a_dire": "Très bien."}, tool_call_id="t", result_callback=rappel))
    assert fiche["conversation"][PA.CLE_PORTEURS] == {"commande": 10}, fiche


def test_gabarit_les_specialises_portent_les_passages_et_leurs_sorties_gardent_l_action():
    g = json.loads(GABARIT.read_text(encoding="utf-8"))
    for etape in ("commande", "reservation", "service"):
        e = g["etapes"][etape]
        assert all(n.get("passages") for n in e["noeuds"] if n["type"] == "startCall"), etape
        sorties = {s["sortie"]: s for s in e["sorties"]}
        assert sorties["rendre_la_main"].get("garde_l_action_ouverte") and sorties["fin"].get("fermee_si_action_ouverte"), sorties
