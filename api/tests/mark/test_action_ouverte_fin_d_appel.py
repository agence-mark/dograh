"""[.mark] Une action OUVERTE bloque la fin de l'appel, une fois (vu en production, appel 2553).

Un panier avec des articles, jamais enregistré : « Non, ce sera tout », l'agent dit au revoir et appelle la sortie fin, ``finaliser`` n'est jamais appelé.
Le garde C18 (``action_non_aboutie``) ne le voyait pas : il ne lit que le dernier résultat d'un outil « doit aboutir », et ``ajouter`` avait rendu OK.
Un connecteur déclare maintenant son ACTION OUVERTE (``Connecteur.action_ouverte``, lue sur la fiche de l'appel) ; le garde la traite comme une
action non aboutie, sans mot de métier dans le mécanisme.

| Test | Ce qu'il prouve |
|---|---|
| panier ouvert | un panier avec une ligne, non enregistré : la fin est refusée une fois, le résultat nomme l'outil (``fiche``, contrat du lot 2), la seconde passe (G2) |
| enregistré | un panier enregistré : la fin passe tout de suite |
| rien d'ouvert | aucun panier, ou un panier vidé : rien ne change |
| réservation | une réservation relue et pas confirmée : refusée une fois, nomme ``reserver`` ; une fois enregistrée (relecture effacée), la fin passe |
| interrupteur | l'interrupteur de l'agent éteint : la fin passe |
| vocabulaire | aucun mot de métier dans le mécanisme (``action_non_aboutie.py``) |
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from api.services.commande import etape, panier
from api.services.interventions_du_moteur import CLE_FIN_APRES_ACTION_NON_ABOUTIE
from api.services.workflow import action_non_aboutie as fin


def _moteur(fiche: dict, reglages: dict | None = None):
    return SimpleNamespace(
        _gathered_context=fiche, reglages_appel=dict(reglages or {}), active_agent=SimpleNamespace(reglages=dict(reglages or {}), current_node=None, llm=None)
    )


def _panier(lignes: int = 1, enregistree=None) -> dict:
    p = panier.nouveau()
    p["lignes"] = [{"code": f"A{i}", "quantite": 1} for i in range(lignes)]
    if enregistree:
        etape.transition(p, etape.ENREGISTREE_EN_CAISSE, faits=enregistree, empreinte="e")  # lot 2 : l'étape est la seule à écrire « enregistrée »
    return p


def test_un_panier_ouvert_refuse_la_fin_une_fois_nomme_l_outil_puis_la_fin_passe():
    fiche = {panier.CLE: _panier()}
    moteur = _moteur(fiche)
    refus = fin.verifier_la_fin(moteur)
    assert refus is not None and refus["status"] == fin.STATUT_REFUS and refus["outils_a_appeler"] == ["fiche"], refus
    assert "ouverte" in refus["message"] and "commande" not in refus["message"].casefold()
    assert fin.verifier_la_fin(moteur) is None  # G2 : jamais coincé


def test_un_panier_enregistre_la_fin_passe_tout_de_suite():
    moteur = _moteur({panier.CLE: _panier(enregistree={"numero_court": "C1"})})
    assert fin.verifier_la_fin(moteur) is None


def test_aucun_panier_ou_un_panier_vide_rien_ne_change():
    assert fin.verifier_la_fin(_moteur({})) is None
    assert fin.verifier_la_fin(_moteur({panier.CLE: _panier(lignes=0)})) is None


def test_une_reservation_relue_et_pas_confirmee_ouvre_une_action():
    from api.services.actions_communes import conversation as CONV
    from api.services.reservation.moteur import CLE

    fiche = {CLE: {CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "recapitulatif", "texte": "Je vous réserve ... C'est bon ?"}}}}  # lot 7 (D49) : le récapitulatif est la question en attente
    moteur = _moteur(fiche)
    refus = fin.verifier_la_fin(moteur)
    assert refus is not None and refus["outils_a_appeler"] == ["fiche"], refus
    assert fin.verifier_la_fin(moteur) is None
    assert fin.verifier_la_fin(_moteur({CLE: {"derniere": "R1"}})) is None  # enregistrée : la relecture est effacée


def test_l_interrupteur_de_l_agent_eteint_la_fin_passe():
    moteur = _moteur({panier.CLE: _panier()}, {CLE_FIN_APRES_ACTION_NON_ABOUTIE: False})
    assert fin.verifier_la_fin(moteur) is None


def test_aucun_mot_de_metier_dans_le_mecanisme_de_l_action_ouverte():
    corps = (Path(fin.__file__)).read_text(encoding="utf-8")
    assert not re.search(r"commande|panier|r[ée]servation|restaura|pizza|caisse", corps, re.IGNORECASE)
