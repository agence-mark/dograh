"""[.mark] Plan final Partie 1, lot 4 (n° 101) : un balayage périodique ferme les appels inactifs du processus, à la voix comme au clavier."""

from __future__ import annotations

import asyncio
import time

from api.services.restauration.appel_et_memoire import memoire_de_l_appel as M


class _Connexion:
    def __init__(self):
        self.fermee = False

    def is_closed(self):
        return self.fermee

    async def close(self):
        self.fermee = True


def _appel(run_id, il_y_a_s, au_clavier):
    c = _Connexion()
    M._APPELS[str(run_id)] = M.AppelOuvert("base_essai", connexion=c, dernier_geste=time.perf_counter() - il_y_a_s, au_clavier=au_clavier)
    return c


def _vider():
    M._APPELS.clear()


async def test_un_appel_a_la_voix_inactif_est_ferme_et_un_appel_vivant_reste():
    _vider()
    try:
        perdu = _appel(1, M.INACTIVITE_A_LA_VOIX_S + 5, au_clavier=False)
        silencieux = _appel(2, M.INACTIVITE_AU_CLAVIER_S + 5, au_clavier=False)  # se tait depuis 65 s : un appel à la voix peut
        clavier = _appel(3, M.INACTIVITE_AU_CLAVIER_S + 5, au_clavier=True)
        assert await M.fermer_les_appels_inactifs() == 2
        assert perdu.fermee and clavier.fermee and not silencieux.fermee and M.appel_ouvert(2) is not None
    finally:
        _vider()


async def test_un_appel_dont_un_geste_tient_le_verrou_n_est_pas_ferme():
    _vider()
    try:
        c = _appel(1, M.INACTIVITE_A_LA_VOIX_S + 5, au_clavier=False)
        async with M._APPELS["1"].verrou:
            assert await M.fermer_les_appels_inactifs() == 0
        assert not c.fermee
    finally:
        _vider()


async def test_le_balayage_lance_au_demarrage_ferme_seul_l_appel_inactif():
    _vider()
    tache = M.demarrer_le_balayage(intervalle_s=0.01)
    try:
        c = _appel(1, M.INACTIVITE_A_LA_VOIX_S + 5, au_clavier=False)
        for _ in range(100):
            if c.fermee:
                break
            await asyncio.sleep(0.01)
        assert c.fermee and M.appel_ouvert(1) is None
    finally:
        tache.cancel()
        _vider()

