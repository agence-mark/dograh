"""Lot 20 (banc final, constat 2) puis clôture A5 (IC1, audit de la latence § 4) : la connexion d'une partie au clavier à la base du client.

Lot 20 : une partie au clavier laissait UNE connexion ouverte par appel (97 sur 100). Le correctif fermait l'appel à la fin de CHAQUE tour : chaque tour
relisait alors la carte entière (14 requêtes), 40 ms par fiche au jeu 3 contre 5. Règle (clôture A5) : l'appel est GARDÉ entre deux tours, comme
à la voix ; il est fermé à la fin de la partie (appel terminé, ou tour en échec) et après ``INACTIVITE_AU_CLAVIER_S`` sans geste. La connexion du
chargement devient celle de l'appel (le premier geste ne rouvre rien).
"""

import time
from types import SimpleNamespace

import pytest

from api.services.restauration.appel_et_memoire import memoire_de_l_appel as M
from api.services.workflow import text_chat_runner as T


class _FausseConnexion:
    def __init__(self):
        self.fermee = False
        self.instantane = None

    def is_closed(self):
        return self.fermee

    def is_in_transaction(self):
        return False

    async def close(self):
        self.fermee = True


def _appel_ouvert(run_id, il_y_a_s: float = 0.0, au_clavier: bool = True):
    c = _FausseConnexion()
    M._APPELS[str(run_id)] = M.AppelOuvert("base_essai", connexion=c, dernier_geste=time.monotonic() - il_y_a_s, au_clavier=au_clavier)
    return c


@pytest.fixture(autouse=True)
def _appels_propres():
    M._APPELS.clear()
    yield
    M._APPELS.clear()


async def _un_tour(monkeypatch, run_id, *, termine=None, leve=False):
    connexion = None

    async def tour(**kwargs):
        nonlocal connexion
        connexion = M._APPELS[str(kwargs["workflow_run_id"])].connexion if str(kwargs["workflow_run_id"]) in M._APPELS else _appel_ouvert(kwargs["workflow_run_id"])
        if leve:
            raise RuntimeError("tour en échec")
        return SimpleNamespace(is_completed=termine)

    monkeypatch.setattr(T, "_executer_le_tour", tour)
    if leve:
        with pytest.raises(RuntimeError):
            await T.execute_text_chat_pending_turn(workflow_run_id=run_id, workflow_id=1, session_data={}, checkpoint=None)
    else:
        await T.execute_text_chat_pending_turn(workflow_run_id=run_id, workflow_id=1, session_data={}, checkpoint=None)
    return connexion


async def test_le_tour_au_clavier_garde_l_appel_pour_le_tour_suivant(monkeypatch):
    connexion = await _un_tour(monkeypatch, 4242, termine=False)
    appel = M.appel_ouvert(4242)
    assert appel is not None and not connexion.fermee, "le tour suivant retrouve l'appel : la carte n'est pas relue"
    seconde = await _un_tour(monkeypatch, 4242, termine=False)
    assert seconde is connexion and M.appel_ouvert(4242) is appel, "deux tours de suite : la même connexion, le même appel"


@pytest.mark.parametrize("termine, leve", [(True, False), (None, True)])
async def test_la_fin_de_la_partie_ferme_l_appel(monkeypatch, termine, leve):
    connexion = await _un_tour(monkeypatch, 4243, termine=termine, leve=leve)
    assert connexion.fermee and M.appel_ouvert(4243) is None


async def test_un_appel_inactif_est_ferme_au_tour_suivant_d_une_autre_partie(monkeypatch):
    oublie = _appel_ouvert(1, il_y_a_s=M.INACTIVITE_AU_CLAVIER_S + 5)
    vivant = _appel_ouvert(2, il_y_a_s=5)
    await _un_tour(monkeypatch, 3, termine=False)
    assert oublie.fermee and M.appel_ouvert(1) is None, "la fuite du lot 20 ne revient pas"
    assert not vivant.fermee and M.appel_ouvert(2) is not None


async def test_un_appel_a_la_voix_silencieux_n_est_jamais_balaye(monkeypatch):
    """Pierre 12 : le balayage d'inactivité ne vise que les appels au clavier ; un appel à la voix qui se tait plus de 60 s garde sa connexion."""
    voix = _appel_ouvert(1, il_y_a_s=M.INACTIVITE_AU_CLAVIER_S + 5, au_clavier=False)
    await _un_tour(monkeypatch, 3, termine=False)
    assert not voix.fermee and M.appel_ouvert(1) is not None


async def test_la_connexion_du_chargement_devient_celle_de_l_appel(monkeypatch):
    from api.services.restauration import source_commande

    ouvertes: list[_FausseConnexion] = []

    async def connecter(nom):
        c = _FausseConnexion()
        ouvertes.append(c)
        return c

    async def charger_pour_l_appel(self):
        return {}, {}

    monkeypatch.setattr(source_commande.SourceClasseur, "charger_pour_l_appel", charger_pour_l_appel)
    appel = M.AppelOuvert("base_essai", lieu=SimpleNamespace(etablissement_id=1), connecter=connecter)
    await M._charger(appel, SimpleNamespace(organization_id=1), {}, {})
    assert len(ouvertes) == 1 and appel.connexion is ouvertes[0] and not ouvertes[0].fermee, "le premier geste ne rouvre rien"
    assert await M._connexion_prete(appel) is ouvertes[0] and len(ouvertes) == 1
