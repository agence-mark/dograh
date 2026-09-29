"""[.mark] C4 : le mois dit est gardé (« novembre de l'an dernier » → 11/2025).

Chantier correctifs-banc-34 (29/09/2026), décision D-C4. Run 883 : la personne dit « en
novembre de l'an dernier ». Deux défauts :

1. l'expression était repérée par sa fin (« l'an dernier ») et calculée en année seule :
   la passe de fin d'appel a écrit « 2025 », le mois perdu ;
2. la valeur du modèle, « novembre 2025 », n'était pas lue comme une date écrite :
   refusée trois fois (« pas dit tel quel »), l'agent l'a fait confirmer.

| Test | Ce qu'il prouve |
|---|---|
| l'expression | « novembre de l'an dernier », « en mars de cette année »… → mois/année |
| sans mois | « l'année dernière » reste l'année seule (rien ne change) |
| valeur écrite en mots | « novembre 2025 » retrouvé dans les paroles, écrit 11/2025 avec les mots dits |
| pas le même mois | « octobre 2025 » pour « novembre de l'an dernier » : refusé |
| outil (run 883) | par le vrai point d'écriture : écrit au 1er envoi, mots gardés |
| passe de fin (run 883) | le balayage écrit 11/2025, plus 2025 |
"""

from datetime import datetime

import pytest

from api.services.workflow.dates_relatives import lire_date, lire_expression
from api.services.workflow.fiche_au_fil_de_leau import cle_dit, ecrire_dans_la_fiche
from api.tests.mark.test_fiche_correctifs_modules import _reglages

JOUR = datetime(2026, 9, 29, 10, 0)
DATE = {"nom": "dernier_entretien", "origine": "dicte", "description": "Date du dernier entretien"}


@pytest.mark.parametrize(
    "texte, dit, attendu",
    [
        ("En novembre de l'an dernier.", "novembre de l'an dernier", "11/2025"),
        ("c'était en novembre l'année dernière", "novembre l'année dernière", "11/2025"),
        ("en mars de l'année passée", "mars de l'année passée", "03/2025"),
        ("février de cette année", "février de cette année", "02/2026"),
        ("Août de l'an passé", "Août de l'an passé", "08/2025"),
    ],
)
def test_C4_le_mois_dit_est_garde(texte, dit, attendu):
    assert lire_expression(texte, JOUR) == (dit, attendu)


@pytest.mark.parametrize(
    "texte, attendu",
    [("l'année dernière", "2025"), ("il y a deux ans", "2024"), ("le mois dernier", "08/2026")],
)
def test_C4_sans_mois_rien_ne_change(texte, attendu):
    assert lire_expression(texte, JOUR)[1] == attendu


def test_C4_une_valeur_ecrite_en_mots_est_retrouvee_dans_les_paroles():
    date = lire_date("novembre 2025", ["En novembre de l'an dernier."], JOUR)
    assert date is not None
    assert (date.valeur, date.dit, date.depuis_les_paroles) == (
        "11/2025",
        "En novembre de l'an dernier.",
        True,
    )


def test_C4_pas_le_meme_mois_pas_retenue():
    assert lire_date("octobre 2025", ["En novembre de l'an dernier."], JOUR) is None


def test_C4_run_883_par_l_outil_ecrit_au_premier_envoi():
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche,
        _reglages(DATE),
        "dernier_entretien",
        "novembre 2025",
        paroles=["En novembre de l'an dernier."],
        jour=JOUR,
    )
    assert verdict.statut == "ecrit", verdict
    assert fiche["dernier_entretien"] == "11/2025"
    assert fiche[cle_dit("dernier_entretien")] == "En novembre de l'an dernier."


def test_C4_run_883_la_passe_de_fin_garde_le_mois():
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche,
        _reglages(DATE),
        "dernier_entretien",
        "novembre de l'an dernier",
        source="balayage",
        paroles=["En novembre de l'an dernier."],
        seulement_si_vide=True,
        jour=JOUR,
    )
    assert verdict.statut == "ecrit", verdict
    assert fiche["dernier_entretien"] == "11/2025"
