"""[.mark] Module Restauration, lot SA-22 (C18) : une action commencée et pas aboutie bloque la fin de l'appel, une fois.

Par le vrai journal des actions (``envelopper_l_action``) et le vrai contrôle des répliques, sur le banc de la vérité des actions.

| Test | Ce qu'il prouve |
|---|---|
| appel sain | aucune action ratée : la fin passe, rien d'écrit (G1) ; un outil jamais appelé n'est pas concerné |
| refus une fois | une action écrite échoue puis fin demandée : refus neutre ; second essai : la fin passe (G2) |
| dernier résultat | un échec suivi d'un succès : la fin passe ; un appel encore en cours : refus |
| statuts | ENREGISTREE / DEJA_FAIT / OK / TRANSMISE aboutissent ; REFUSEE / INCOMPLETE / échec n'aboutissent pas |
| case par outil | cochée par défaut sur un outil qui écrit, décochée sur un qui lit, la case posée décide |
| interrupteur | éteint : aucun effet |
| alerte | l'option allumée écrit UNE alerte quand la fin passe quand même ; éteinte : rien |
| vérité des actions | « c'est fait » dit après une action non aboutie est retenu même si une autre action a réussi ; nœud de fin contrôlé seulement quand une action n'a pas abouti |
| vocabulaire | aucun mot de métier dans le mécanisme |
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from api.services.interventions_du_moteur import CLE_FIN_APRES_ACTION_NON_ABOUTIE
from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE
from api.services.workflow import action_non_aboutie as fin
from api.services.workflow.verite_des_actions import (
    RAISON_ACTION,
    VerificateurDeFin,
    VerificateurDeReplique,
    brancher_la_verite_des_actions,
)
from api.tests.mark.test_verite_des_actions import ANNULER, CHERCHER, RESERVER, Banc


def _outil(methode="POST", **config):
    return SimpleNamespace(category="http_api", definition={"config": {"method": methode, **config}})


def _banc(reglages=None, outils=(RESERVER, ANNULER)):
    banc = Banc()
    banc.moteur.active_agent = SimpleNamespace(reglages=dict(reglages or {}), current_node=None, llm=None)
    banc.moteur.reglages_appel = dict(reglages or {})
    for nom in outils:
        fin.inscrire_l_outil(banc.moteur, nom, _outil())
    return banc


async def test_appel_sain_la_fin_passe_sans_rien_ecrire():
    banc = _banc()
    assert fin.verifier_la_fin(banc.moteur) is None  # rien appelé
    await banc.appeler(RESERVER, nom="Durand")
    assert fin.verifier_la_fin(banc.moteur) is None
    assert CLE_FICHE not in banc.fiche and "alertes" not in banc.fiche


CLE_FICHE = fin.CLE_FICHE_REFUS


async def test_action_ratee_puis_fin_refus_une_fois_puis_la_fin_passe():
    banc = _banc()
    banc.reponses[RESERVER] = {"statut": "echec", "error": "indisponible"}
    await banc.appeler(RESERVER, nom="Durand")
    refus = fin.verifier_la_fin(banc.moteur)
    assert refus["status"] == fin.STATUT_REFUS and refus["actions"] == [RESERVER]
    assert "n'a pas abouti" in refus["message"]
    assert fin.verifier_la_fin(banc.moteur) is None  # G2 : jamais coincé


async def test_dernier_resultat_decide_et_un_appel_en_cours_compte():
    banc = _banc()
    banc.reponses[RESERVER] = {"statut": "echec", "error": "x"}
    await banc.appeler(RESERVER, nom="Durand")
    banc.reponses[RESERVER] = {"statut": "ENREGISTREE"}
    await banc.appeler(RESERVER, nom="Durand 2")
    assert fin.actions_non_abouties(banc.moteur) == []
    fin.noter_l_appel_en_cours(banc.moteur, ANNULER, 1)
    assert fin.verifier_la_fin(banc.moteur)["actions"] == [ANNULER]


def test_statuts_abouti_ou_non():
    for statut in ("ENREGISTREE", "DEJA_FAIT", "OK", "TRANSMISE"):
        assert fin.a_abouti({"statut": statut}), statut
    for statut in ("REFUSEE", "INCOMPLETE", "echec", "refused"):
        assert not fin.a_abouti({"statut": statut}), statut
    assert not fin.a_abouti({"status": "error", "error": "boom"})
    assert fin.a_abouti({"status": "success", "status_code": 200, "data": {"statut": "ENREGISTREE"}})


async def test_outil_non_coche_aucun_effet_et_la_case_par_outil_decide():
    # Un outil qui lit n'est pas coché par défaut ; un outil qui écrit l'est ; la case posée décide dans les deux sens.
    assert fin.outil_doit_aboutir(_outil("POST")) and not fin.outil_doit_aboutir(_outil("GET"))
    assert not fin.outil_doit_aboutir(_outil("POST", doit_aboutir_avant_la_fin=False))
    assert fin.outil_doit_aboutir(_outil("GET", doit_aboutir_avant_la_fin=True))
    banc = _banc(outils=())
    fin.inscrire_l_outil(banc.moteur, RESERVER, _outil("POST", doit_aboutir_avant_la_fin=False))
    banc.reponses[RESERVER] = {"statut": "echec", "error": "x"}
    await banc.appeler(RESERVER, nom="Durand")
    assert fin.verifier_la_fin(banc.moteur) is None


async def test_interrupteur_eteint_aucun_effet():
    banc = _banc({CLE_FIN_APRES_ACTION_NON_ABOUTIE: False})
    banc.reponses[RESERVER] = {"statut": "echec", "error": "x"}
    await banc.appeler(RESERVER, nom="Durand")
    assert fin.verifier_la_fin(banc.moteur) is None
    assert CLE_FICHE not in banc.fiche


async def test_alerte_une_seule_fois_si_l_option_est_allumee_sinon_rien():
    banc = _banc({fin.CLE_PREVENIR: True})
    banc.reponses[RESERVER] = {"statut": "echec", "error": "x"}
    await banc.appeler(RESERVER, nom="Durand")
    assert fin.verifier_la_fin(banc.moteur) is not None  # le refus : pas d'alerte encore
    assert "alertes" not in banc.fiche
    assert fin.verifier_la_fin(banc.moteur) is None and fin.verifier_la_fin(banc.moteur) is None
    [alerte] = banc.fiche["alertes"]
    assert alerte["outil"] == RESERVER
    sans = _banc()
    sans.reponses[RESERVER] = {"statut": "echec", "error": "x"}
    await sans.appeler(RESERVER, nom="Durand")
    fin.verifier_la_fin(sans.moteur)
    fin.verifier_la_fin(sans.moteur)
    assert "alertes" not in sans.fiche


async def test_porte_ecrite_jamais_refusee_seulement_signalee():
    banc = _banc({fin.CLE_PREVENIR: True})
    banc.reponses[RESERVER] = {"statut": "echec", "error": "x"}
    await banc.appeler(RESERVER, nom="Durand")
    assert fin.verifier_la_fin(banc.moteur, refuser=False) is None
    assert len(banc.fiche["alertes"]) == 1 and CLE_FICHE not in banc.fiche


async def test_c_est_fait_apres_une_action_non_aboutie_est_retenu_meme_si_une_autre_a_reussi():
    banc = _banc()
    await banc.appeler(RESERVER, nom="Durand")  # réussie : « une action a réussi » fonde d'ordinaire « c'est réservé »
    banc.reponses[ANNULER] = {"statut": "echec", "error": "x"}
    await banc.appeler(ANNULER, rendez_vous="x")
    retenue = VerificateurDeReplique(banc.moteur, banc.agent).controler("C'est réservé.", [])
    assert retenue is not None and retenue.raison == RAISON_ACTION
    # appel sain : la même phrase passe
    sain = _banc()
    await sain.appeler(RESERVER, nom="Durand")
    assert VerificateurDeReplique(sain.moteur, sain.agent).controler("C'est réservé.", []) is None
    # interrupteur éteint : passe
    eteint = _banc({CLE_FIN_APRES_ACTION_NON_ABOUTIE: False})
    await eteint.appeler(RESERVER, nom="Durand")
    eteint.reponses[ANNULER] = {"statut": "echec", "error": "x"}
    await eteint.appeler(ANNULER, rendez_vous="x")
    assert VerificateurDeReplique(eteint.moteur, eteint.agent).controler("C'est réservé.", []) is None


async def test_noeud_de_fin_controle_seulement_quand_une_action_n_a_pas_abouti():
    noeud_de_fin = SimpleNamespace(is_end=True, verite_des_actions=None)
    sain = _banc()
    await sain.appeler(RESERVER, nom="Durand")
    llm = SimpleNamespace()
    brancher_la_verite_des_actions(sain.moteur, SimpleNamespace(llm=llm, current_node=noeud_de_fin), noeud_de_fin, False)
    assert getattr(llm, ATTRIBUT_VERITE) is None  # appel sain : le flux d'avant
    rate = _banc()
    rate.reponses[RESERVER] = {"statut": "echec", "error": "x"}
    await rate.appeler(RESERVER, nom="Durand")
    llm = SimpleNamespace()
    brancher_la_verite_des_actions(rate.moteur, SimpleNamespace(llm=llm, current_node=noeud_de_fin), noeud_de_fin, False)
    verificateur = getattr(llm, ATTRIBUT_VERITE)
    assert isinstance(verificateur, VerificateurDeFin)
    assert verificateur.controler("Parfait, c'est réservé, bonne soirée.", []).raison == RAISON_ACTION
    assert verificateur.controler("Je n'ai pas pu terminer, désolé. Bonne soirée.", []) is None
    assert verificateur.controler("Le 9 novembre à 20 h 45, bonne soirée.", []) is None  # ni dates ni chiffres ici


def test_aucun_mot_de_metier_dans_le_mecanisme():
    source = Path(fin.__file__).read_text(encoding="utf-8").casefold()
    for mot in ("pizza", "restaurant", "commande", "panier", "réservation", "reservation", "caisse", "hubrise", "devis", "rendez-vous"):
        assert mot not in source, mot


async def test_l_outil_de_fin_refuse_une_fois_le_modele_repond_puis_raccroche():
    from unittest.mock import AsyncMock

    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

    banc = _banc()
    banc.reponses[RESERVER] = {"statut": "echec", "error": "x"}
    await banc.appeler(RESERVER, nom="Durand")
    banc.moteur.end_call_with_reason = AsyncMock()
    gestionnaire = CustomToolManager(banc.moteur, banc.agent)._create_end_call_handler(
        SimpleNamespace(definition={"config": {}}), "fin_d_appel"
    )

    async def jouer():
        rendus = []

        async def rendre(resultat, **kwargs):
            rendus.append((resultat, kwargs.get("properties")))

        await gestionnaire(SimpleNamespace(arguments={}, result_callback=rendre))
        return rendus

    [(refus, proprietes)] = await jouer()
    assert refus["status"] == fin.STATUT_REFUS and proprietes.run_llm is True
    banc.moteur.end_call_with_reason.assert_not_called()  # l'appel continue
    [(accepte, _)] = await jouer()
    assert accepte["status"] == "success"
    banc.moteur.end_call_with_reason.assert_awaited()  # second essai : l'appel finit
