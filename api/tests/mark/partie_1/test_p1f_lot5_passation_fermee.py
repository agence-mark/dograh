"""[.mark] Plan final Partie 1, lot 5 (P, n° 118 et 121) : la passation est FERMÉE sur toutes les sorties, le routage est celui du code.

CHANGEMENT DE COMPORTEMENT (commit à part, validé ensuite par le banc des 72, plan § 2) :

* n° 118 : une porte fermée par la fiche l'est pour tous. La règle vit dans ``prendre_porte_ecrite``, une seule fois ; le filet de fin n'a plus de garde à lui. Le filet qui
  trouve sa sortie fermée ne fait rien et ne laisse aucune trace de passage.
* n° 121 : la garde ``meme_agent`` (la cible vient de rendre la main pour la même raison) n'a plus d'exception « une action est ouverte quelque part ». La reprise d'une
  action ouverte est routée par le code : seule la passation vers l'agent qui la TIENT (noté à chaque fiche, ``CLE_PORTEURS``) n'est jamais refusée ; toute autre l'est.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest

from api.services.commande import panier as P
from api.services.groupe import passations as G
from api.services.workflow.pipecat_engine import PipecatEngine
from api.tests.mark.test_filet_de_fin import _monter

RAISON = "passer_a_l_agent_commande"
ACCUEIL, COMMANDE, RESERVATION = 299, 300, 301


def _trace(vers):
    return [{"de": ACCUEIL, "vers": vers, "raison": RAISON, "issue": "completed"}, {"de": vers, "vers": ACCUEIL, "raison": "retour", "issue": "completed"}]


def _commande_ouverte():
    p = P.nouveau()
    p.update(mode="emporter", lignes=[{"n": 1, "quantite": 1, "nom": "Reine", "variante": "Normale"}])
    return p


def test_la_passation_vers_l_agent_qui_tient_l_action_ouverte_n_est_jamais_un_va_et_vient():
    fiche = {P.CLE: _commande_ouverte(), "passations": _trace(COMMANDE), G.CLE_PORTEURS: {"commande": COMMANDE}}
    assert G.refus_de_passation(fiche, {}, de=ACCUEIL, vers=COMMANDE, raison=RAISON) is None


def test_une_action_ouverte_ailleurs_ne_leve_pas_la_garde_meme_agent():
    """Avant : « une action est ouverte quelque part » suffisait ; maintenant la cible doit être celle qui la tient. Rouge si l'ancienne exception revient."""
    fiche = {P.CLE: _commande_ouverte(), "passations": _trace(RESERVATION), G.CLE_PORTEURS: {"commande": COMMANDE}}
    assert G.refus_de_passation(fiche, {}, de=ACCUEIL, vers=RESERVATION, raison=RAISON) == "meme_agent"


def test_sans_porteur_note_la_garde_meme_agent_tient():
    fiche = {P.CLE: _commande_ouverte(), "passations": _trace(COMMANDE)}
    assert G.refus_de_passation(fiche, {}, de=ACCUEIL, vers=COMMANDE, raison=RAISON) == "meme_agent"


def test_il_n_existe_plus_d_exception_une_action_est_ouverte_dans_la_passation():
    assert not hasattr(G, "rendre_a_l_action_ouverte") and "rendre_a_l_action_ouverte" not in inspect.getsource(G)


@pytest.mark.asyncio
async def test_une_porte_fermee_par_la_fiche_est_fermee_pour_le_code_comme_pour_le_modele():
    harness = await _monter()
    try:
        engine = harness.engine
        engine.end_call_with_reason = AsyncMock()
        engine.queue_node_opening = AsyncMock()
        engine.porte_fermee_par_la_fiche = lambda *a, **k: {"type": "champ", "champ": "action_ouverte"}
        nom = next(iter(engine.active_agent.current_node.out_edges)).get_function_name()
        assert await engine.prendre_porte_ecrite(nom, choisie_par_le_code=True) == "fermee"  # la règle est dans la prise de la porte
        assert await engine.prendre_porte_ecrite(nom) == "fermee"
        depart = engine.etat_pour_le_filet()
        assert await engine.filet_de_fin("Très bien, je vous souhaite une bonne soirée.", depart) is False
        assert not engine._gathered_context.get("porte_reecrite")  # le filet n'a rien pris, il ne laisse pas de trace de passage
        assert not engine.transfer_coordinator.in_progress
    finally:
        await harness.stop()


def test_le_filet_de_fin_n_a_plus_de_garde_a_lui():
    """n° 118 : la garde « le filet ne passe pas par-dessus une porte fermée » n'est plus écrite dans le filet : elle est dans la prise de porte."""
    assert "porte_fermee_par_la_fiche" not in inspect.getsource(PipecatEngine.filet_de_fin)
    assert "porte_fermee_par_la_fiche" in inspect.getsource(PipecatEngine.prendre_porte_ecrite)
