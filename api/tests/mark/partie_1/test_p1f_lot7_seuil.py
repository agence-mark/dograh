"""[.mark] Lot 7a, M6 : UN seuil de sortie, donné par l'appelant, pour la même chose redite : un refus ou un fait bloquant (``fait_redit``) comme une boucle (``boucle``)."""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J


def _rythme(dossier: dict, cle: str, fois: int, seuil: int) -> list[str]:
    return [J.fait_redit(dossier, cle, tour, seuil) for tour in range(1, fois + 1)]


def test_le_refus_redit_sort_au_seuil_lu():
    assert _rythme({}, "refus", 3, 3) == [J.PREMIERE, J.ISSUE, J.SORTIE]


def test_changer_le_seuil_change_le_rythme_du_refus_comme_celui_de_la_boucle():
    assert _rythme({}, "refus", 4, 4) == [J.PREMIERE, J.ISSUE, J.ISSUE, J.SORTIE]
    d: dict = {}
    assert [J.boucle(d, ("sig",), True, 4) for _ in range(4)] == [False, False, False, True]
