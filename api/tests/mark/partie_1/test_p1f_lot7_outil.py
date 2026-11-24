"""[.mark] Lot 7a, lignes 110, 122 et 129 (l'outil) : l'outil d'un connecteur ne teste plus le NOM « fiche » ; il lit ce que son connecteur déclare (``Connecteur.porte_la_fiche``) et passe par la
parole commune (``parole_de_la_fiche.dire_le_retour``), qui note aussi le porteur de l'action, un fait de la conversation de l'appel."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.groupe import passations as PA
from api.services.integrations.connectors import catalogue as CAT
from api.services.integrations.connectors import outil
from api.services.integrations.connectors.catalogue import Action, Connecteur
from api.services.integrations.connectors.execution import Resultat as ResultatDeLAction


async def _jamais(*_a, **_k):
    raise AssertionError("jamais appelé : le retour est celui de l'exécuteur de l'essai")


def _connecteur_d_essai(nom: str, action: str, *, porte: str | None):
    return CAT.declarer(Connecteur(
        nom=nom, libelle="Essai", integration="interne", interne=True, executer_interne=_jamais, porte_la_fiche=porte,
        dossier_de_la_parole=lambda _fiche: {}, objet_en_cours=lambda _dossier: False, texte_du_manque=lambda _dossier, _fiche: None,
        actions=(Action(nom=action, description="essai", parametres=(), ecrit=False, local=True, preparer=_jamais, resultat=_jamais),)))


async def _jouer(monkeypatch, nom: str, action: str) -> dict:
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
    tool = SimpleNamespace(name=action, definition={"config": {"connecteur": nom, "action": action}})
    gestionnaire = outil.creer_gestionnaire(manager, tool, action)

    async def rappel(resultat, *, properties=None): ...

    await gestionnaire(SimpleNamespace(arguments={"a_dire": "Très bien."}, tool_call_id="t", result_callback=rappel))
    return fiche


async def test_un_connecteur_a_fiche_nomme_autrement_passe_par_la_parole_commune(monkeypatch):
    CAT.retirer("essai_poser")
    _connecteur_d_essai("essai_poser", "poser_la_fiche", porte="poser_la_fiche")
    try:
        fiche = await _jouer(monkeypatch, "essai_poser", "poser_la_fiche")
    finally:
        CAT.retirer("essai_poser")
    assert PAROLE.CLE_ETAT_DU_TOUR in fiche, fiche  # la parole a jugé le retour (``PAROLE.garder``)
    assert fiche[CONV.CLE][PA.CLE_PORTEURS] == {"essai_poser": 10}, fiche  # lot 7a (122) : le porteur est un fait de la conversation


async def test_une_action_nommee_fiche_que_son_connecteur_ne_declare_pas_n_est_pas_jugee(monkeypatch):
    CAT.retirer("essai_muet")
    _connecteur_d_essai("essai_muet", "fiche", porte=None)
    try:
        fiche = await _jouer(monkeypatch, "essai_muet", "fiche")
    finally:
        CAT.retirer("essai_muet")
    assert PAROLE.CLE_ETAT_DU_TOUR not in fiche and CONV.CLE not in fiche, fiche  # le nom ne décide plus de rien : la déclaration seule
