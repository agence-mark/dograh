"""[.mark] Chantier Partie 1 : la garde des noms sur la réservation, propriété du lot 7 (sa fiche).

Séparée de ``test_l00_glossaire.py::test_noms_du_fork`` au lot 2 : la réservation garde ses outils de production jusqu'au lot 7 (D18 : rien de ce
qui marche n'est chamboulé avant son lot) ; ses trois paires proches (« reservation ») sont rouges jusque-là, le lot 7 la rend verte.
"""

import pytest

from api.tests.mark.partie_1.controle_noms import controler, inventaire_du_fork


@pytest.mark.garde_noms
def test_noms_de_la_reservation():
    r1, r2, r3 = controler(inventaire_du_fork(("reservation",)))
    assert (r1, r2, r3) == ([], [], []), f"manquent : {r1[:8]} ; deux sens : {r2[:5]} ; proches : {r3[:5]}"
