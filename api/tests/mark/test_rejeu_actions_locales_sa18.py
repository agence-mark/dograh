"""[.mark] SA-18, lot C (C15) : un essai rejoué joue pour de vrai les actions locales du fork et simule le reste.

Avant : toute action d'un connecteur interne (commande, réservation, service) rendait « Fait. » au rejeu d'un test : aucun test de restaurant n'était jouable.
Maintenant : une action qui reste dans le fork (``Action.local``) est jouée ; celle qui écrit, envoie un message ou transfère reste simulée.
"""

from types import SimpleNamespace

import pytest

from api.services.integrations.connectors import catalogue, outil
from api.services.tests_rejouables.simulation import CLE_REJEU, simuler_si_rejeu


def _outil(connecteur: str, action: str):
    return SimpleNamespace(definition={"config": {"connecteur": connecteur, "action": action}}, category="integration")


@pytest.mark.parametrize(
    "connecteur, action, local",
    [
        ("commande", "ajouter", True),
        ("commande", "choisir_mode", True),
        ("commande", "voir_commande", True),
        ("commande", "finaliser", False),          # écrit : simulée
        ("commande", "envoyer_un_message", False),  # un message part chez l'appelant : simulé
        ("reservation", "disponibilites", True),
        ("reservation", "reserver", False),
        ("service", "infos_pratiques", True),
        ("equipe", "diriger_vers_personne", False),  # transfère l'appel
    ],
)
def test_seule_une_action_locale_est_jouee_pour_de_vrai(connecteur, action, local):
    if catalogue.trouver(connecteur, action) is None:
        pytest.skip(f"{connecteur}.{action} absent du catalogue")
    assert outil.action_locale(_outil(connecteur, action)) is local


def _moteur_en_rejeu():
    return SimpleNamespace(_gathered_context={CLE_REJEU: True}, _fiche=None)


async def _jouer(gestionnaire, **argument):
    rendus = []

    async def rendre(resultat, **_):
        rendus.append(resultat)

    await gestionnaire(SimpleNamespace(arguments=argument, result_callback=rendre))
    return rendus[0]


async def test_au_rejeu_une_action_locale_s_execute_et_une_autre_est_simulee():
    appels = []

    async def reel(params):
        appels.append(params.arguments)
        await params.result_callback({"statut": "OK", "reel": True})

    moteur = _moteur_en_rejeu()
    local = simuler_si_rejeu(moteur, "integration", "ajouter", reel, local=True)
    assert (await _jouer(local, articles="une regina"))["reel"] is True and appels == [{"articles": "une regina"}]
    simule = simuler_si_rejeu(moteur, "integration", "finaliser", reel)
    assert (await _jouer(simule))["message"] == "Fait." and len(appels) == 1  # rien n'a été exécuté
