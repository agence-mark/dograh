"""Lot 20 (banc final, constat 2) : une partie au clavier laissait UNE connexion ouverte à la base du client par appel.

Source : ``memoire_de_l_appel.fermer`` n'était appelé qu'à la fin d'un appel à la voix (``run_pipeline``) ; le chemin du clavier
(``execute_text_chat_pending_turn``) ne le faisait jamais. Garde sur l'état : à la fin de chaque tour au clavier, qu'il réussisse ou lève,
l'appel est oublié et sa connexion fermée.
"""

import pytest

from api.services.restauration import memoire_de_l_appel as M
from api.services.workflow import text_chat_runner as T


class _FausseConnexion:
    def __init__(self):
        self.fermee = False

    def is_closed(self):
        return self.fermee

    async def close(self):
        self.fermee = True


def _appel_ouvert(run_id):
    c = _FausseConnexion()
    M._APPELS[str(run_id)] = M.AppelOuvert("base_essai", connexion=c)
    return c


@pytest.mark.parametrize("leve", [False, True])
async def test_le_tour_au_clavier_ferme_la_connexion_de_l_appel(monkeypatch, leve):
    connexion = None

    async def tour(**kwargs):
        nonlocal connexion
        connexion = _appel_ouvert(kwargs["workflow_run_id"])
        if leve:
            raise RuntimeError("tour en échec")
        return "fait"

    monkeypatch.setattr(T, "_executer_le_tour", tour)
    if leve:
        with pytest.raises(RuntimeError):
            await T.execute_text_chat_pending_turn(workflow_run_id=4242, workflow_id=1, session_data={}, checkpoint=None)
    else:
        assert await T.execute_text_chat_pending_turn(workflow_run_id=4242, workflow_id=1, session_data={}, checkpoint=None) == "fait"
    assert connexion.fermee and M.appel_ouvert(4242) is None
