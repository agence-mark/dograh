"""[.mark] Lot 7b-C6, commit 3a (décision d'Evan 25/11 9 h 30, Q1 et Q3 de Pierre = A) : les motifs réglables du total, leurs variables déclarées côté serveur, leur rotation.

Le code ne dit plus le total qu'avec une phrase du catalogue : réglable, avec variantes, jamais éteinte, jamais sans sa variable ``{total}``. Aucun modèle, aucun appel.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.schemas.phrases_du_code import ReglePhrase
from api.services.actions_communes.resultat import phrase_du_code
from api.services.phrases.catalogue import MOTIFS, NUMERO_DICTE_RELU, PHRASES_DU_CODE, TOTAL_APRES_CORRECTION, TOTAL_RELECTURE, catalogue_pour_l_ecran
from api.services.phrases.regles import resoudre

TOTAUX = (TOTAL_RELECTURE, TOTAL_APRES_CORRECTION)


@pytest.mark.parametrize("motif", TOTAUX)
def test_le_motif_du_total_declare_sa_variable_et_ses_variantes(motif):
    m = MOTIFS[motif]
    assert m.variables == ("total",) and len(m.variantes_defaut) >= 2 and m.verrouille
    assert all("{total}" in v and v.rstrip().endswith("?") for v in m.variantes_defaut)
    assert motif in PHRASES_DU_CODE and NUMERO_DICTE_RELU in PHRASES_DU_CODE


@pytest.mark.parametrize("motif", TOTAUX)
def test_une_variante_qui_perd_le_total_est_refusee(motif):
    with pytest.raises(ValueError, match=r"\{total\}"):
        ReglePhrase(motif=motif, portee="agent", variantes=["Ça fait ce prix-là, c'est bon ?"])
    with pytest.raises(ValueError, match=r"\{total\}"):
        ReglePhrase(motif=motif, portee="agent", variantes=["Cela fait {total}, c'est bon ?", "Le prix, c'est bon ?"])
    assert ReglePhrase(motif=motif, portee="agent", variantes=["Ça donne {total}, d'accord ?"]).variantes == ["Ça donne {total}, d'accord ?"]


def test_le_numero_dicte_declare_aussi_sa_variable():
    assert MOTIFS[NUMERO_DICTE_RELU].variables == ("numero",)
    with pytest.raises(ValueError, match=r"\{numero\}"):
        ReglePhrase(motif=NUMERO_DICTE_RELU, portee="agent", variantes=["Je note votre numéro, c'est bon ?"])


@pytest.mark.parametrize("motif", TOTAUX)
def test_le_motif_du_total_ne_s_eteint_jamais(motif):
    """Une règle éteinte : le texte du catalogue est dit quand même (le total n'est jamais tu)."""
    eteinte = {"phrases_regles": [{"motif": motif, "portee": "agent", "variantes": [], "active": False}]}
    phrase = resoudre(motif, reglages_agent=eteinte, reglages_principal=eteinte)
    assert phrase.dite and phrase.variantes == MOTIFS[motif].variantes_defaut


def test_le_total_est_remplace_et_la_phrase_n_est_pas_composee():
    ctx = SimpleNamespace()
    assert phrase_du_code(ctx, TOTAL_RELECTURE, total="vingt-quatre euros") == "Cela fait vingt-quatre euros, c'est bon pour vous ?"
    # une variable qui n'est pas déclarée n'est pas remplacée
    assert phrase_du_code(ctx, TOTAL_RELECTURE, total="douze euros", autre="x").count("{") == 0


def test_les_variantes_tournent_selon_le_rang_donne_par_l_appelant():
    ctx = SimpleNamespace()
    dites = [phrase_du_code(ctx, TOTAL_RELECTURE, rang, total="douze euros") for rang in range(3)]
    assert dites[0] != dites[1] and dites[0] == dites[2]
    assert dites[1] == "Ça fait douze euros, c'est bon ?"


def test_la_phrase_reglee_a_l_ecran_est_dite_avec_le_total():
    ctx = SimpleNamespace(configurations={"phrases_regles": [{"motif": TOTAL_APRES_CORRECTION, "portee": "agent", "variantes": ["Au total, {total}. D'accord ?"]}]})
    assert phrase_du_code(ctx, TOTAL_APRES_CORRECTION, total="trente euros") == "Au total, trente euros. D'accord ?"


def test_l_ecran_recoit_les_variables_de_chaque_motif():
    par_id = {m["id"]: m for m in catalogue_pour_l_ecran()["motifs"]}
    assert par_id[TOTAL_RELECTURE]["variables"] == ["total"] and par_id[NUMERO_DICTE_RELU]["variables"] == ["numero"]
    assert par_id[TOTAL_APRES_CORRECTION]["verrouille"] is True
