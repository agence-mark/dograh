"""[.mark] K3 : un mois nommé suivi de « dernier » devient mois et année (« janvier dernier » → 01/2026).

Chantier correctifs-apres-figeage (30/09/2026). Run 910 : « Janvier dernier, je crois. » ; la fiche a gardé les
mots seuls (« janvier dernier »), sans date, alors que « l'année dernière » est écrite « 2025 » (908) et « novembre de
l'an dernier » « 11/2025 » (C4). Le mois nommé suivi de « dernier » ou « passé » est le dernier mois de ce nom
AVANT le mois de l'appel : le 30/09/2026, janvier → 01/2026, septembre → 09/2025, octobre → 10/2025.

| Test | Ce qu'il prouve |
|---|---|
| l'expression | les mois avant, pendant et après le mois de l'appel, « passé » compris |
| déjà couvert | « novembre de l'an dernier » garde sa règle (C4) |
| outil (run 910) | par le vrai point d'écriture : « janvier dernier » écrit 01/2026, mots gardés |
"""

from datetime import datetime

import pytest

from api.services.workflow.dates_relatives import lire_expression
from api.services.workflow.fiche_au_fil_de_leau import cle_dit, ecrire_dans_la_fiche
from api.tests.mark.test_fiche_correctifs_modules import _reglages

JOUR = datetime(2026, 9, 30, 15, 0)
DATE = {"nom": "dernier_entretien", "origine": "dicte", "description": "Date du dernier entretien"}


@pytest.mark.parametrize(
    "texte, dit, attendu",
    [
        ("Janvier dernier, je crois.", "Janvier dernier", "01/2026"),
        ("en mars dernier", "mars dernier", "03/2026"),  # refusé jusqu'au 30/09 (limite de D46)
        ("en août dernier", "août dernier", "08/2026"),
        ("septembre dernier", "septembre dernier", "09/2025"),
        ("c'était en octobre passé", "octobre passé", "10/2025"),
        ("en décembre dernier", "décembre dernier", "12/2025"),
    ],
)
def test_K3_un_mois_suivi_de_dernier_devient_mois_et_annee(texte, dit, attendu):
    assert lire_expression(texte, JOUR) == (dit, attendu)


@pytest.mark.parametrize(
    "texte",
    ["le 3 mars dernier", "Le 12 janvier dernier.", "le premier mars dernier", "le 1er mars dernier",
     "le vingt-trois janvier dernier", "le trente et un mars dernier", "le douze mai dernier"],
)
def test_K3_relecture_un_jour_devant_le_mois_laisse_la_phrase_telle_quelle(texte):
    """Relecture du 30/09 : « le 3 mars dernier » aurait été écrit 03/2026, jour perdu ; avant K3 la fiche
    gardait la phrase entière. Avec un jour, la tournure ne joue pas (comportement d'avant)."""
    assert lire_expression(texte, JOUR) is None


def test_K3_la_regle_C4_ne_change_pas():
    assert lire_expression("En novembre de l'an dernier.", JOUR) == ("novembre de l'an dernier", "11/2025")


def test_K3_run_910_par_l_outil():
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche,
        _reglages(DATE),
        "dernier_entretien",
        "janvier dernier",
        paroles=["Janvier dernier, je crois."],
        jour=JOUR,
    )
    assert verdict.statut == "ecrit", verdict
    assert fiche["dernier_entretien"] == "01/2026"
    assert "janvier dernier" in fiche[cle_dit("dernier_entretien")].lower()
