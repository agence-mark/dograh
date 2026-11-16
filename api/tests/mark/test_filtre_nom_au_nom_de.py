"""[.mark] SA-18, lot B (C9) : le prénom retiré d'une relecture emporte son lien (« au nom de »).

Avant : « Je vous relis : une Regina à emporter, au nom de Paul. » devenait « …à emporter, au nom de. » (essais du 17/11).
"""

import pytest

from api.services.pipecat.filtre_nom_civilite import retirer_nom_et_civilite


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("Je vous relis : une Regina à emporter, au nom de Paul.", "Je vous relis : une Regina à emporter."),
        ("Votre commande au nom de Paul est prête.", "Votre commande est prête."),
        ("C'est noté pour un retrait au nom d'Alice. À tout à l'heure.", "C'est noté pour un retrait. À tout à l'heure."),
        ("Je mets la réservation sous le nom de Paul, pour quatre personnes.", "Je mets la réservation, pour quatre personnes."),
    ],
)
def test_le_lien_part_avec_le_prenom(texte, attendu):
    prenom = "Alice" if "Alice" in texte else "Paul"
    assert retirer_nom_et_civilite(texte, prenom, retirer_nom=True) == attendu


def test_sans_prenom_a_retirer_rien_ne_change():
    texte = "Votre commande au nom de la maison est prête."
    assert retirer_nom_et_civilite(texte, "Paul", retirer_nom=True) == texte


def test_un_autre_nom_propre_garde_son_lien():
    texte = "Je note au nom de Marc."
    assert retirer_nom_et_civilite(texte, "Paul", retirer_nom=True) == texte
