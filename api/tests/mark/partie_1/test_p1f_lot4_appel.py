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


async def _termine_en_base(cle):
    return True  # par défaut dans ces essais, l'appel est fini ; ``test_un_appel_a_la_voix_vivant...`` dit le contraire


async def test_un_appel_a_la_voix_inactif_est_ferme_et_un_appel_vivant_reste():
    _vider()
    try:
        perdu = _appel(1, M.INACTIVITE_A_LA_VOIX_S + 5, au_clavier=False)
        silencieux = _appel(2, M.INACTIVITE_AU_CLAVIER_S + 5, au_clavier=False)  # se tait depuis 65 s : un appel à la voix peut
        clavier = _appel(3, M.INACTIVITE_AU_CLAVIER_S + 5, au_clavier=True)
        assert await M.fermer_les_appels_inactifs(appel_termine=_termine_en_base) == 2
        assert perdu.fermee and clavier.fermee and not silencieux.fermee and M.appel_ouvert(2) is not None
    finally:
        _vider()


async def test_un_appel_a_la_voix_encore_vivant_n_est_jamais_ferme_meme_sans_aucun_geste_d_outil():
    """Un appel long à la voix sans outil (la personne parle, le modèle répond) n'a aucun geste : il n'est pas pour autant inactif ; seul un appel terminé est fermé."""
    _vider()
    try:
        vivant = _appel(1, M.INACTIVITE_A_LA_VOIX_S * 3, au_clavier=False)

        async def en_cours(_cle):
            return False

        # lot 8a (157) : l'état d'un appel à la voix est un paramètre du balayage, plus un réglage global
        assert await M.fermer_les_appels_inactifs(appel_termine=en_cours) == 0 and not vivant.fermee and M.appel_ouvert(1) is not None
        assert await M.fermer_les_appels_inactifs(appel_termine=_termine_en_base) == 1 and vivant.fermee
    finally:
        _vider()


async def test_un_appel_dont_un_geste_tient_le_verrou_n_est_pas_ferme():
    _vider()
    try:
        c = _appel(1, M.INACTIVITE_A_LA_VOIX_S + 5, au_clavier=False)
        async with M._APPELS["1"].verrou:
            assert await M.fermer_les_appels_inactifs(appel_termine=_termine_en_base) == 0
        assert not c.fermee
    finally:
        _vider()


async def test_le_balayage_lance_au_demarrage_ferme_seul_l_appel_inactif():
    _vider()
    tache = M.demarrer_le_balayage(intervalle_s=0.01, appel_termine=_termine_en_base)
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



def test_la_reouverture_se_dit_a_l_heure_du_restaurant_et_selon_l_horloge_donnee():
    """N° 117 : ni l'heure réelle ni Paris en dur ; la phrase suit l'horloge du module et le fuseau de l'établissement."""
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from api.services.pipecat.etat_ouverture import CLE_REOUVERTURE, etat_de_la_caisse_au_decroche

    maintenant, reprise = datetime(2020, 1, 15, 10, 0, tzinfo=UTC), datetime(2020, 1, 15, 19, 0, tzinfo=UTC)  # une date très ancienne : l'heure réelle n'est pas lue
    ouverture = {"ouvert": False, "etat": "PAUSE", "reprise": reprise}
    paris = etat_de_la_caisse_au_decroche({}, ouverture, None, None, maintenant, ZoneInfo("Europe/Paris"))
    auckland = etat_de_la_caisse_au_decroche({}, ouverture, None, None, maintenant, ZoneInfo("Pacific/Auckland"))
    assert paris[CLE_REOUVERTURE] == "aujourd'hui à 20 heures"
    assert auckland[CLE_REOUVERTURE] == "demain à 8 heures"
