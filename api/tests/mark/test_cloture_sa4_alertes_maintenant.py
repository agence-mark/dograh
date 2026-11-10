"""[.mark] Clôture D2 (É63) : la colonne « Maintenant » des seuils d'alerte : où en est chaque signal, sans le comparer au seuil.

| Test | La garantie |
|---|---|
| hausse chiffrée | un signal qui monte de 0 % à 40 % contre une période précédente à 10 % donne la hausse relative ; sous le seuil aussi (rien n'est caché) |
| pas assez d'appels | sous ``appels_min`` d'un côté : ``None`` (jamais un 0 inventé) |
| période précédente nulle | des cas aujourd'hui sans cas avant : ``None`` (jamais « infini »), aucun cas des deux côtés : 0 |
| latence | la médiane aujourd'hui contre la médiane d'avant |
"""

from __future__ import annotations

from api.services.alertes_agent import appels, types
from api.tests.mark.test_l3e_alertes_appels import MAINTENANT, SEUILS, cas, periode


def test_la_hausse_est_chiffree_meme_sous_le_seuil():
    # avant : 1 appel sur 10 concerné ; maintenant : 2 sur 10 -> +100 %
    lignes = periode(100, 10, 9) + periode(150, 10, 1, transfert=True) + periode(200, 2, 8) + periode(300, 2, 2, transfert=True)
    r = appels.mesure_actuelle(types.HAUSSE_TRANSFERTS, lignes, SEUILS[types.HAUSSE_TRANSFERTS], MAINTENANT)
    assert r == {"hausse": 100.0, "appels": 10}


def test_pas_assez_d_appels_rien_d_invente():
    lignes = periode(100, 10, 3) + periode(200, 2, 3)
    r = appels.mesure_actuelle(types.HAUSSE_PANNES, lignes, SEUILS[types.HAUSSE_PANNES], MAINTENANT)
    assert r["hausse"] is None and r["appels"] == 3


def test_periode_precedente_nulle_jamais_infini():
    avec_cas = appels.mesure_actuelle(types.HAUSSE_PANNES, cas(4, panne=True), SEUILS[types.HAUSSE_PANNES], MAINTENANT)
    assert avec_cas["hausse"] is None
    sans_cas = appels.mesure_actuelle(types.HAUSSE_PANNES, periode(100, 10, 10) + periode(200, 2, 10), SEUILS[types.HAUSSE_PANNES], MAINTENANT)
    assert sans_cas["hausse"] == 0.0


def test_la_latence_compare_les_medianes():
    lignes = periode(100, 10, 10, latence=1.0) + periode(200, 2, 10, latence=1.5)
    r = appels.mesure_actuelle(types.HAUSSE_LATENCE, lignes, SEUILS[types.HAUSSE_LATENCE], MAINTENANT)
    assert r == {"hausse": 50.0, "appels": 10}
