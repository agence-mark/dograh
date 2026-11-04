"""[.mark] RA-B, R4 (c) : un outil qui échoue ne fait dire qu'UNE phrase (audit 02 B4, 🔴 4, test de preuve).

Le constat disait : le repli de l'outil, puis la règle « un outil échoue » : « désolé » deux fois. Ces tests passent par le
gestionnaire de l'outil HTTP (``executer_avec_comportement``) enveloppé comme le moteur l'enveloppe, la règle posée."""

from types import SimpleNamespace

import pytest

from api.services.outils_mark.comportement import executer_avec_comportement
from api.services.phrases.catalogue import OUTIL_ECHOUE
from api.services.workflow.enveloppe_des_actions import envelopper_l_action
from api.tests.mark.test_phrases_branchements_v4 import _moteur_outils, _regle

pytestmark = pytest.mark.asyncio


async def _jouer(moteur, config, resultat):
    moteur.queue_text_message = _enregistrer(moteur)
    rendus = []

    async def rendre(valeur, *a, **k):
        rendus.append(valeur)

    async def appel():
        return resultat

    async def action(params):
        await params.result_callback(await executer_avec_comportement(moteur, config, "reserver", appel))

    params = SimpleNamespace(result_callback=rendre, llm=moteur.active_agent.llm, arguments={})
    await envelopper_l_action(moteur, "reserver", action, moteur.active_agent, garde=False)(params)
    await moteur.phrases.attendre_la_fin()
    return rendus


def _enregistrer(moteur):
    async def queue_text_message(texte, **_):
        moteur.dites.append(texte)

    return queue_text_message


async def test_outil_http_en_echec_avec_repli_et_regle_une_seule_parole():
    moteur = _moteur_outils([_regle(OUTIL_ECHOUE, ["Désolé, un souci."], outils=["reserver"])])
    await _jouer(moteur, {"phrase_repli": "Je ne peux pas réserver."}, {"status": "error", "error": "500"})
    assert len(moteur.dites) == 1, moteur.dites


async def test_outil_http_en_echec_sans_repli_la_regle_parle_une_fois():
    moteur = _moteur_outils([_regle(OUTIL_ECHOUE, ["Désolé, un souci."])])
    await _jouer(moteur, {}, {"status": "error", "error": "500"})
    assert moteur.dites == ["Désolé, un souci."]


async def test_connecteur_en_echec_une_seule_parole():
    # Le gestionnaire d'un connecteur dit déjà le repli via la règle, puis rend ``passed_on`` à l'enveloppe.
    moteur = _moteur_outils([_regle(OUTIL_ECHOUE, ["Désolé, un souci."])])
    rendus = []

    async def rendre(valeur, *a, **k):
        rendus.append(valeur)

    from api.services.integrations.connectors.outil import _signaler_le_repli

    async def action(params):
        probleme = await _signaler_le_repli(moteur, "Phrase du connecteur.", "reserver")
        await params.result_callback({"status": "passed_on", "said_to_caller": probleme.dit})

    params = SimpleNamespace(result_callback=rendre, llm=moteur.active_agent.llm, arguments={})
    await envelopper_l_action(moteur, "reserver", action, moteur.active_agent, garde=False)(params)
    await moteur.phrases.attendre_la_fin()
    assert len(moteur.dites) == 1, moteur.dites
