"""[.mark] Module Restauration, lot 24 : le nom d'outil abîmé, rattaché sans ambiguïté ou refusé en clair, au niveau du fork (Pipecat n'est pas touché, R9).

| Test | Ce qu'il prouve |
|---|---|
| rattachement | la casse, les accents, un préfixe ``functions.``, un séparateur, une lettre de travers : rattaché à l'outil qu'on voit ; un nom exact reste tel quel |
| refus fermé | un nom sans rapport, un nom qui ressemble à DEUX outils, deux outils qui s'écrivent pareil : ``None``, jamais un outil deviné |
| éteint par défaut | sans la clé, rien n'est posé |
| attrape-tout | allumé : un nom abîmé exécute le vrai gestionnaire de l'outil avec ses arguments, sous le bon nom ; un nom inconnu rend le refus fermé avec la liste des outils ; chaque cas est mesuré |
| Pipecat | l'attrape-tout est la voie PRÉVUE par Pipecat (``register_function(None, …)``), aucune ligne de Pipecat n'est modifiée |
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.integrations.connectors import mesures
from api.services.workflow import nom_d_outil_abime as n

OUTILS = ["ajouter", "modifier", "retirer", "voir_commande", "finaliser", "voir_produit", "retrouver_commande", "reserver", "annuler_reservation"]


def test_un_nom_abime_sans_ambiguite_est_rattache_a_l_outil_qu_on_voit():
    for abime, voulu in {
        "Ajouter": "ajouter", "AJOUTER": "ajouter", "functions.ajouter": "ajouter", "commande:ajouter": "ajouter", "ajouter_": "ajouter", "ajoutér": "ajouter",
        "voir-commande": "voir_commande", "voircommande": "voir_commande", "voir_comande": "voir_commande", "finalise": "finaliser", "retrouver_comande": "retrouver_commande",
        "annuler_reservatoin": "annuler_reservation",
    }.items():
        assert n.rattacher(abime, OUTILS) == voulu, abime
    assert n.rattacher("ajouter", OUTILS) == "ajouter"


def test_un_nom_sans_rapport_ou_ambigu_n_est_jamais_devine():
    for refuse in ("supprimer_le_monde", "voir", "annuler", "retirer_et_ajouter", "", None, "   ", "...", "res"):
        assert n.rattacher(refuse, OUTILS) is None, refuse
    # deux outils très proches : l'écart n'est pas net
    assert n.rattacher("voir_produi", ["voir_produit", "voir_produits"]) is None
    # deux outils qui s'écrivent pareil une fois normalisés
    assert n.rattacher("Ajouter", ["ajouter", "Ajouter_"]) is None
    assert n.rattacher("x", []) is None


def test_la_cle_est_au_schema_eteinte_par_defaut_et_sans_elle_rien_n_est_pose():
    assert WorkflowConfigurationDefaults.model_fields[n.CLE].default is False
    assert not n.allumee({}) and not n.allumee(None) and not n.allumee({n.CLE: "oui"}) and n.allumee({n.CLE: True})
    poses: list = []
    llm = SimpleNamespace(register_function=lambda *a, **k: poses.append(a), _functions={})
    assert n.installer(SimpleNamespace(reglages_appel={}), llm) is False and poses == []


class FauxLlm:
    def __init__(self):
        self._functions: dict = {}
        self.attrape = None

    def register_function(self, nom, handler, **options):
        if nom is None:
            self.attrape = handler
        else:
            self._functions[nom] = SimpleNamespace(handler=handler)


@pytest.fixture
def banc():
    llm = FauxLlm()
    appels: list = []

    async def gestionnaire(params):
        appels.append((params.function_name, params.arguments))
        await params.result_callback({"statut": "OK"})

    for nom in OUTILS:
        llm.register_function(nom, gestionnaire)
    fiche: dict = {}
    moteur = SimpleNamespace(reglages_appel={n.CLE: True}, _gathered_context=fiche)
    assert n.installer(moteur, llm) is True and llm.attrape is not None
    return SimpleNamespace(llm=llm, appels=appels, fiche=fiche)


async def _appeler(banc, nom, **arguments):
    rendus: list = []

    async def rendre(valeur, *a, **k):
        rendus.append(valeur)

    from dataclasses import dataclass

    @dataclass
    class Params:
        function_name: str
        arguments: dict
        result_callback: object

    await banc.llm.attrape(Params(nom, arguments, rendre))
    return rendus[0]


async def test_l_attrape_tout_execute_le_vrai_outil_sous_le_bon_nom_ou_refuse_en_clair(banc):
    r = await _appeler(banc, "functions.Ajouter", articles="une regina")
    assert r == {"statut": "OK"} and banc.appels == [("ajouter", {"articles": "une regina"})]
    refus = await _appeler(banc, "supprimer_le_monde")
    assert refus["status"] == "outil_inconnu" and refus["outils"] == sorted(OUTILS) and "ajouter" in refus["consigne"] and len(banc.appels) == 1   # aucun outil n'a tourné
    assert mesures.compte(banc.fiche) == {"outil.nom_rattache": 1, "outil.nom_refuse": 1}


def test_l_attrape_tout_est_la_voie_prevue_par_pipecat_et_pipecat_n_est_pas_touche():
    from pipecat.services.llm_service import LLMService

    assert "str | None" in str(inspect.signature(LLMService.register_function).parameters["function_name"].annotation) or "None" in str(
        inspect.signature(LLMService.register_function).parameters["function_name"].annotation
    )
    assert "Use None to handle" in inspect.getsource(LLMService.register_function)
