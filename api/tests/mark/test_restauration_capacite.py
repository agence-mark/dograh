"""[.mark] Module Restauration, lot 8, étape 1 : la capacité (``capacite.py``) : attribution des unités, règles puis capacité, créneaux proches.

| Test | Ce qu'il prouve |
|---|---|
| attribution | la plus petite unité qui convient ; sinon la paire assemblable la plus juste ; rien si rien ne tient ; déterministe |
| règles d'abord | passé, délai minimal, jour trop lointain, hors de la grille, groupe trop grand, pause : chacun sa raison fermée, avant toute capacité |
| capacité | une unité prise sur le créneau n'est plus libre ; un créneau qui chevauche compte ; complet quand plus rien ne tient |
| modifier | en retirant sa propre occupation, ses unités comptent comme libres |
| créneaux proches | les plus proches de l'heure souhaitée, avant ou après, dans l'ordre du temps |
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.db.bases_clients.capacite import (
    COMPLET, FERME, GROUPE_TROP_GRAND, HORS_SERVICE, PASSE, TROP_LOIN, TROP_TOT,
    Occupation, Regles, Service, Unite, attribuer, creneaux_libres, les_plus_proches, placer, unites_libres, verifier_les_regles,
)

PARIS = ZoneInfo("Europe/Paris")
MAINTENANT = datetime(2026, 11, 12, 12, 0, tzinfo=PARIS)     # un jeudi
SOIR = datetime(2026, 11, 14, 20, 0, tzinfo=PARIS)           # samedi 20 h
SERVICES = [Service("soir", [1, 2, 3, 4, 5, 6, 7], "19:00", "22:00", 15)]
T2A, T2B, T4, T6 = Unite(1, 1, 2), Unite(2, 1, 2, frozenset({1})), Unite(3, 2, 4), Unite(4, 4, 6)
UNITES = [Unite(1, 1, 2, frozenset({2})), Unite(2, 1, 2, frozenset({1})), Unite(3, 2, 4), Unite(4, 4, 6)]


def occ(debut, effectif, *unites, minutes=90):
    return Occupation(debut, debut + timedelta(minutes=minutes), effectif, frozenset(unites))


def test_attribution_la_plus_juste_puis_la_paire_puis_rien_deterministe():
    assert attribuer(2, UNITES) == (1,)                       # la plus petite capacité maximale, puis le plus petit identifiant
    assert attribuer(3, UNITES) == (3,)
    assert attribuer(5, UNITES) == (4,)
    assert attribuer(4, [UNITES[0], UNITES[1]]) == (1, 2)      # deux tables de deux, assemblables
    assert attribuer(4, [Unite(1, 1, 2), Unite(2, 1, 2)]) is None   # non assemblables : rien
    assert attribuer(9, UNITES) is None
    assert attribuer(2, list(reversed(UNITES))) == attribuer(2, UNITES)


def test_les_regles_passent_avant_la_capacite_chacune_sa_raison():
    regles = Regles(delai_minimal=60, jours_a_l_avance=30, effectif_max=8)
    f = lambda debut, eff=2, r=regles: verifier_les_regles(debut, eff, SERVICES, PARIS, MAINTENANT, r)  # noqa: E731
    assert f(MAINTENANT - timedelta(hours=3)) == PASSE
    assert verifier_les_regles(datetime(2026, 11, 12, 12, 30, tzinfo=PARIS), 2, SERVICES, PARIS, MAINTENANT, regles) == TROP_TOT
    assert f(datetime(2026, 12, 20, 20, 0, tzinfo=PARIS)) == TROP_LOIN
    assert f(SOIR, 9) == GROUPE_TROP_GRAND
    assert f(datetime(2026, 11, 14, 20, 10, tzinfo=PARIS)) == HORS_SERVICE     # pas de 15 minutes : 20 h 10 n'est pas sur la grille
    assert f(datetime(2026, 11, 14, 15, 0, tzinfo=PARIS)) == HORS_SERVICE
    assert f(SOIR, r=Regles(pause_jusqu_a=SOIR + timedelta(hours=1))) == FERME
    assert f(SOIR) is None


def test_capacite_un_creneau_pris_n_est_plus_libre_et_complet_quand_rien_ne_tient():
    regles = Regles()
    p = lambda eff, occs: placer(SOIR, 90, eff, UNITES, occs, SERVICES, PARIS, MAINTENANT, regles)  # noqa: E731
    assert p(2, []) == ("ok", (1,))
    assert p(2, [occ(SOIR, 2, 1)]) == ("ok", (2,))
    assert p(2, [occ(SOIR - timedelta(minutes=60), 2, 1)]) == ("ok", (2,))                   # une occupation qui chevauche prend sa table
    assert p(2, [occ(SOIR - timedelta(minutes=90), 2, 1)]) == ("ok", (1,))                   # celle qui finit à 20 h ne gêne pas
    plein = [occ(SOIR, 2, 1), occ(SOIR, 2, 2), occ(SOIR, 4, 3), occ(SOIR, 6, 4)]
    assert p(2, plein) == (COMPLET, ())
    assert p(7, []) == (COMPLET, ())   # 7 > 6 : aucune unité ni paire ne l'accueille
    assert placer(SOIR, 90, 2, UNITES, [], SERVICES, PARIS, MAINTENANT, Regles(effectif_max_par_creneau=3))[0] == "ok"
    assert placer(SOIR, 90, 2, UNITES, [occ(SOIR, 2, 1)], SERVICES, PARIS, MAINTENANT, Regles(effectif_max_par_creneau=3))[0] == COMPLET


def test_modifier_ses_propres_unites_comptent_comme_libres():
    seule = [Unite(1, 1, 4)]
    sa_resa = occ(SOIR, 4, 1)
    # avec sa propre occupation, la table est prise : complet ; retirée de la liste, elle redevient libre
    assert placer(SOIR, 90, 3, seule, [sa_resa], SERVICES, PARIS, MAINTENANT, Regles())[0] == COMPLET
    assert placer(SOIR, 90, 3, seule, [], SERVICES, PARIS, MAINTENANT, Regles()) == ("ok", (1,))
    assert [u.id for u in unites_libres(SOIR, SOIR + timedelta(minutes=90), UNITES, [occ(SOIR, 2, 1)])] == [2, 3, 4]


def test_les_creneaux_les_plus_proches_avant_ou_apres_dans_l_ordre_du_temps():
    libres = creneaux_libres(SOIR.date(), 2, 90, UNITES, [], SERVICES, PARIS, MAINTENANT, Regles())
    assert libres[0]["debut"] == datetime(2026, 11, 14, 19, 0, tzinfo=PARIS)
    proches = les_plus_proches(datetime(2026, 11, 14, 21, 15, tzinfo=PARIS), libres, 3)
    assert [c["debut"].strftime("%H:%M") for c in proches] == ["21:00", "21:15", "21:30"]
    # à égalité d'écart, le plus tôt : 21 h 00 et 21 h 30 pour 21 h 15 exact n'a pas d'égalité ; test à 21 h 07 : 21 h 00 (7) puis 21 h 15 (8)
    assert [c["debut"].strftime("%H:%M") for c in les_plus_proches(datetime(2026, 11, 14, 21, 7, tzinfo=PARIS), libres, 2)] == ["21:00", "21:15"]
    assert les_plus_proches(SOIR, [], 3) == []
