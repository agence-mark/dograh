"""[.mark] Module Restauration, lot 5, étape 1 (T-01) : le réglage commun « dit mot pour mot » ou « reformulé » sur tout outil.

Mécanisme commun du fork, aucun mot de métier : un outil qui rend une phrase proposée (``suggestion``) la voit arriver au modèle
avec le mode choisi dans la fiche de l'outil (``restitution``) et la consigne qui va avec.

| Test | Ce qu'il prouve |
|---|---|
| mot pour mot | la phrase arrive intacte dans ``texte_a_dire`` avec la consigne de la dire telle quelle |
| reformulé | la même phrase, avec la consigne de la reformuler sans changer les faits |
| réglage vide | rien n'est ajouté (le comportement d'avant) ; une valeur inconnue non plus |
| échec | jamais de consigne de restitution sur un échec |
| ``data`` | la phrase d'un outil HTTP (dans ``data``) est reprise de la même façon |
| outil de connecteur | par le VRAI gestionnaire d'un outil ``integration`` : le réglage de l'outil gagne, à défaut le conseil de l'action |
| schémas | le champ existe sur les trois configurations d'outil et refuse une valeur hors liste |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.schemas.tool import ComportementOutil, IntegrationToolConfig
from api.services.integrations.connectors import catalogue
from api.services.integrations.connectors.catalogue import Action, Connecteur, declarer
from api.services.integrations.connectors.outil import CLE_RESTITUTION_PAR_DEFAUT, creer_gestionnaire
from api.services.outils_mark.pour_la_voix import avec_restitution

PHRASE = "Je vous relis : deux Margherita et un Coca, vingt-trois euros quatre-vingts. C'est bon ?"


def test_mot_pour_mot_la_phrase_arrive_intacte_avec_la_consigne_de_la_dire():
    sortie = avec_restitution({"statut": "OK", "suggestion": PHRASE}, {"restitution": "mot_pour_mot"})
    assert sortie["texte_a_dire"] == PHRASE
    assert sortie["restitution"] == "mot_pour_mot"
    assert "mot pour mot" in sortie["consigne_de_restitution"]
    assert sortie["suggestion"] == PHRASE


def test_reformule_meme_phrase_consigne_de_garder_les_faits():
    sortie = avec_restitution({"statut": "OK", "suggestion": PHRASE}, {"restitution": "reformule"})
    assert sortie["texte_a_dire"] == PHRASE
    assert sortie["restitution"] == "reformule"
    assert "mêmes faits" in sortie["consigne_de_restitution"]


@pytest.mark.parametrize("config", [None, {}, {"restitution": None}, {"restitution": "au_hasard"}])
def test_reglage_vide_ou_inconnu_ne_change_rien(config):
    resultat = {"statut": "OK", "suggestion": PHRASE}
    assert avec_restitution(resultat, config) == resultat


def test_sans_phrase_proposee_rien_n_est_ajoute():
    resultat = {"statut": "OK", "faits": {"total": 2380}}
    assert avec_restitution(resultat, {"restitution": "mot_pour_mot"}) == resultat


def test_jamais_sur_un_echec():
    echec = {"status": "error", "error": "500", "suggestion": PHRASE}
    assert avec_restitution(echec, {"restitution": "mot_pour_mot"}) == echec


def test_la_phrase_d_un_outil_http_dans_data_est_reprise():
    sortie = avec_restitution({"status": "success", "data": {"suggestion": PHRASE}}, {"restitution": "mot_pour_mot"})
    assert sortie["texte_a_dire"] == PHRASE


def test_le_conseil_de_l_action_sert_quand_le_reglage_est_vide_et_le_reglage_gagne():
    resultat = {"statut": "OK", "suggestion": PHRASE}
    assert avec_restitution(resultat, {}, "mot_pour_mot")["restitution"] == "mot_pour_mot"
    assert avec_restitution(resultat, {"restitution": "reformule"}, "mot_pour_mot")["restitution"] == "reformule"


def test_les_schemas_portent_le_champ_et_refusent_une_valeur_hors_liste():
    assert ComportementOutil(restitution="mot_pour_mot").restitution == "mot_pour_mot"
    assert IntegrationToolConfig(connecteur="equipe", action="diriger_vers_personne", restitution="reformule").restitution == "reformule"
    assert ComportementOutil().restitution is None
    with pytest.raises(ValidationError):
        ComportementOutil(restitution="en_chantant")


# --------------------------------------------------------------------------- #
# Par le vrai gestionnaire d'un outil de connecteur
# --------------------------------------------------------------------------- #


async def _executer_interne(action, arguments, ctx, delai_s):
    return {"statut": "OK", "suggestion": PHRASE, CLE_RESTITUTION_PAR_DEFAUT: "mot_pour_mot"}


@pytest.fixture
def connecteur_de_test():
    c = declarer(
        Connecteur(
            nom="essai_restitution", libelle="Essai", integration="interne", interne=True, executer_interne=_executer_interne,
            actions=(Action(nom="relire", description="Relit.", parametres=(), ecrit=False, preparer=lambda *a: None, resultat=lambda *a: {}),),
        )
    )
    yield c
    catalogue.retirer("essai_restitution")


async def _jouer(config_outil: dict) -> dict:
    rendus: list[dict] = []

    async def rendre(valeur, *a, **k):
        rendus.append(valeur)

    async def organisation():
        return 7

    moteur = SimpleNamespace(_gathered_context={}, _call_context_vars={}, _workflow_run_id=1)
    manager = SimpleNamespace(_engine=moteur, get_organization_id=organisation)
    outil = SimpleNamespace(
        name="relire", description=None,
        definition={"type": "integration", "config": {"connecteur": "essai_restitution", "action": "relire", **config_outil}},
    )
    await creer_gestionnaire(manager, outil, "relire")(SimpleNamespace(arguments={}, result_callback=rendre))
    assert len(rendus) == 1
    return rendus[0]


async def test_le_vrai_gestionnaire_pose_le_conseil_de_l_action_quand_le_reglage_est_vide(connecteur_de_test):
    rendu = await _jouer({})
    assert rendu["restitution"] == "mot_pour_mot" and rendu["texte_a_dire"] == PHRASE
    assert CLE_RESTITUTION_PAR_DEFAUT not in rendu  # le conseil est consommé, jamais montré au modèle


async def test_le_vrai_gestionnaire_le_reglage_de_l_outil_gagne(connecteur_de_test):
    rendu = await _jouer({"restitution": "reformule"})
    assert rendu["restitution"] == "reformule"
    assert "mêmes faits" in rendu["consigne_de_restitution"]
