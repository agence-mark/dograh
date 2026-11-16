"""[.mark] Vérité des actions et chiffres sans source dans un SPÉCIALISTE (vu en production, appel 2554).

Le spécialiste 300, appelé par passation depuis l'accueil 299, a dit à l'étape de finalisation, sans aucun appel de ``finaliser`` ni aucun panier :
« Votre commande est bien enregistrée, elle sera prête à emporter pour vingt-deux heures trente et le total est de douze euros. »
Les réglages de l'agent (``garde_fait_avant_outil``, ``garde_chiffre_sans_source``) sont posés sur le principal. Deux causes :

1. l'étape de finalisation n'écrit aucun champ de la fiche (``rempli_par_outil``) : sans case cochée, le contrôle des répliques n'y était pas branché ;
2. les réglages de l'agent qui a la main (``agent.reglages``, non vides) cachaient ceux de l'appel : les gardes posées sur le principal restaient éteintes.

| Test | Ce qu'il prouve |
|---|---|
| branché | une étape qui n'écrit pas est contrôlée dès que les gardes de chiffres sont allumées sur l'appel |
| retenue | la phrase du cas de production est retenue, un total et une heure sans source |
| réglages du spécialiste | des réglages propres au spécialiste ne cachent pas ceux du principal ; ils les surchargent quand ils les disent |
| sains | gardes éteintes : rien n'est branché ; case décochée : rien n'est branché ; un appel sain (résultat d'outil) : la phrase passe |
| pas de date | une étape branchée seulement par les chiffres ne contrôle pas les dates (celles d'une réservation) |
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE
from api.services.workflow import chiffres_sans_source as c
from api.services.workflow.verite_des_actions import brancher_la_verite_des_actions
from api.tests.mark.test_verite_des_actions import Banc

PHRASE = "Votre commande est bien enregistrée, elle sera prête à emporter pour vingt-deux heures trente et le total est de douze euros."
GARDES = {c.CLE_CHIFFRE_SANS_SOURCE: True, c.CLE_FAIT_AVANT_OUTIL: True}


def _specialiste(principal: dict, propres: dict, case=None):
    banc = Banc(case=case)
    banc.moteur.reglages_appel = dict(principal)
    banc.agent.reglages = dict(propres)
    banc.agent.llm = SimpleNamespace()
    noeud = SimpleNamespace(is_end=False, verite_des_actions=case, champs_etape=())
    banc.agent.current_node = noeud
    return banc, noeud


def test_une_etape_qui_n_ecrit_pas_est_controlee_quand_les_gardes_de_chiffres_sont_allumees():
    banc, noeud = _specialiste(GARDES, {"groupe": True})  # des réglages propres, non vides, SANS les gardes
    assert brancher_la_verite_des_actions(banc.moteur, banc.agent, noeud, offre_une_action=False) is True
    verificateur = getattr(banc.agent.llm, ATTRIBUT_VERITE)
    assert verificateur is not None
    retenue = verificateur.controler(PHRASE, [])
    assert retenue is not None, retenue
    avant = verificateur.controler_avant_outil(PHRASE, [])
    assert avant is not None


def test_les_reglages_du_specialiste_ne_cachent_pas_ceux_du_principal_mais_les_surchargent():
    banc, noeud = _specialiste(GARDES, {"groupe": True})
    brancher_la_verite_des_actions(banc.moteur, banc.agent, noeud, offre_une_action=False)
    v = getattr(banc.agent.llm, ATTRIBUT_VERITE)
    assert v._chiffre_sans_source("Cela fait douze euros.", [], c.CLE_CHIFFRE_SANS_SOURCE, c.RAISON_CHIFFRE, c.CONSIGNE_CHIFFRE) is not None
    banc.agent.reglages = {c.CLE_CHIFFRE_SANS_SOURCE: False}  # le spécialiste l'éteint lui-même : c'est lui qui décide
    assert v._chiffre_sans_source("Cela fait douze euros.", [], c.CLE_CHIFFRE_SANS_SOURCE, c.RAISON_CHIFFRE, c.CONSIGNE_CHIFFRE) is None


def test_gardes_eteintes_ou_case_decochee_rien_n_est_branche_et_un_appel_sain_passe():
    banc, noeud = _specialiste({}, {"groupe": True})
    assert brancher_la_verite_des_actions(banc.moteur, banc.agent, noeud, offre_une_action=False) is False
    assert getattr(banc.agent.llm, ATTRIBUT_VERITE) is None
    banc, noeud = _specialiste(GARDES, {}, case=False)
    assert brancher_la_verite_des_actions(banc.moteur, banc.agent, noeud, offre_une_action=False) is False
    banc, noeud = _specialiste(GARDES, {})
    brancher_la_verite_des_actions(banc.moteur, banc.agent, noeud, offre_une_action=False)
    v = getattr(banc.agent.llm, ATTRIBUT_VERITE)
    messages = [{"role": "tool", "content": '{"statut": "ENREGISTREE", "faits": {"total": 1200, "heure_voulue": "2026-11-12T22:30:00+01:00"}}'}]
    assert v._chiffre_sans_source(PHRASE, messages, c.CLE_CHIFFRE_SANS_SOURCE, c.RAISON_CHIFFRE, c.CONSIGNE_CHIFFRE) is None


def test_une_etape_branchee_par_les_chiffres_ne_controle_pas_les_dates():
    banc, noeud = _specialiste(GARDES, {})
    brancher_la_verite_des_actions(banc.moteur, banc.agent, noeud, offre_une_action=False)
    v = getattr(banc.agent.llm, ATTRIBUT_VERITE)
    assert v.controler("Nous serons ouverts le 14 novembre.", []) is None
