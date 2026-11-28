"""[.mark] Lot 8, 8c-2 (112) : les issues qu'une fiche de connecteur pose elle-même (donc réservées, jamais offertes au classement final) sont DÉCLARÉES par le
connecteur (``Connecteur.issues_reservees``), plus écrites en dur dans ``workflow/issue_reservee.py`` (``("commande", "service")``). Un connecteur de test qui déclare
``("x",)`` voit ``x`` réservé sans que ``issue_reservee.py`` change ; les trois connecteurs du métier gardent exactement leurs issues d'avant."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.integrations.connectors import catalogue as CAT
from api.services.workflow.issue_reservee import codes_reserves


def _outil(connecteur: str, action: str = "fiche", reglages: dict | None = None):
    return SimpleNamespace(category="integration", definition={"config": {"connecteur": connecteur, "action": action, "reglages": reglages or {}}})


def test_un_connecteur_de_test_reserve_son_issue_sans_toucher_issue_reservee(monkeypatch):
    essai = CAT.Connecteur(nom="essai_8c2", libelle="Essai", integration="interne", actions=(), porte_la_fiche="fiche",
                           issues_reservees=lambda reglages: ("x",))
    monkeypatch.setitem(CAT._CATALOGUE, "essai_8c2", essai)
    assert codes_reserves([_outil("essai_8c2")]) == {"x"}
    assert codes_reserves([_outil("essai_8c2", action="lire")]) == set()  # seule la fiche pose ses issues


def test_les_issues_des_connecteurs_du_metier_sont_celles_d_avant():
    assert codes_reserves([_outil("commande")]) == {"commande_enregistree", "commande_annulee", "message_a_transmettre", "commande_abandonnee"}
    assert codes_reserves([_outil("commande", reglages={"issues": {"commande_annulee": "Annulee"}})]) >= {"annulee", "commande_enregistree"}
    assert codes_reserves([_outil("service", reglages={"issues": {"message_a_transmettre": "Message_Transmis"}})]) == {"message_transmis"}
    assert codes_reserves([_outil("reservation")]) == set()
