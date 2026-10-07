"""[.mark] Non-regression test of the lock by name (revue du 07/10, seconde relecture).

Does a protected write (``garder``) end BEFORE the lock goes back, even when the caller is
cancelled by the tool's deadline? Does a cancellation that falls while the lock is being given
back still reach the caller? The lock is the REAL one; only Redis is a stand-in.
"""

from __future__ import annotations

import asyncio

import pytest

from api.services import verrou as modele


class FauxRedis:
    def __init__(self):
        self.valeurs: dict[str, str] = {}
        self.liberation_lente = 0.0

    async def set(self, cle, valeur, nx=False, px=None):
        if nx and cle in self.valeurs:
            return None
        self.valeurs[cle] = valeur
        return True

    async def eval(self, script, nb, cle, jeton):
        if self.liberation_lente:
            await asyncio.sleep(self.liberation_lente)
        if self.valeurs.get(cle) == jeton:
            del self.valeurs[cle]
            return 1
        return 0


@pytest.fixture
def redis(monkeypatch):
    faux = FauxRedis()

    async def _faux():
        return faux

    monkeypatch.setattr(modele, "_redis", _faux)
    return faux


async def test_le_verrou_n_est_rendu_qu_apres_l_ecriture_protegee_meme_annulee(redis):
    etat = {"v": "ancien"}

    async def ecriture():
        await asyncio.sleep(0.3)
        etat["v"] = "echec"

    async def appel_qui_tombe():
        async with modele.verrou("t:1"):
            await modele.garder(ecriture())

    premier = asyncio.ensure_future(appel_qui_tombe())
    await asyncio.sleep(0.05)
    premier.cancel()  # the deadline of the tool

    async def suivant():
        async with modele.verrou("t:1"):
            return etat["v"]

    lu = await suivant()
    assert lu == "echec", "a waiting call read the old state: the lock went back before the write"
    with pytest.raises(asyncio.CancelledError):
        await premier


async def test_une_annulation_pendant_la_liberation_n_est_pas_avalee(redis):
    redis.liberation_lente = 0.5

    async def appel():
        async with modele.verrou("t:2"):
            pass

    tache = asyncio.ensure_future(appel())
    await asyncio.sleep(0.1)  # in the release of the Redis lock
    tache.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tache
    # The local lock was given back: the name can be taken again.
    redis.liberation_lente = 0
    async with modele.verrou("t:2", attente_s=1.0):
        pass
    assert "t:2" not in modele._locaux
