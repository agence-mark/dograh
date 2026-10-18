"""[.mark] Chantier modules-et-cerveaux, lot 1 (M1, M2) : la phrase que le modèle lit donne
un numéro de téléphone de dix chiffres par paires, quelle que soit la forme entendue.

Pourquoi : run vocal 1462 (18/10). Soniox écrit « 07/50/857872 », le module lit juste dix
chiffres, mais le modèle de conversation recevait la phrase telle quelle et relisait
« quatre-vingt-cinq, sept-huit, deux ». La détection (``lire_nombres``) ne change pas ;
seule la phrase réécrite (``reecrire``) donne la forme par paires.

🔑 Testé par la vraie lecture de l'appelant (``_lire``) en plus de ``reecrire`` seule : un
branchement qui s'éteindrait en silence ferait rougir le premier test (R1).
"""

import pytest

from api.services.nombres.lecture import (
    TELEPHONE,
    decoller_les_chiffres,
    lire_nombres,
    reecrire,
    telephone_par_paires,
)
from api.services.pipecat.lecture_appelant import _lire


def _reecrit(texte: str) -> str:
    texte = decoller_les_chiffres(texte)
    return reecrire(texte, lire_nombres(texte))


@pytest.mark.parametrize(
    "entendu, attendu",
    [
        ("Le 07/50/857872.", "Le 07 50 85 78 72."),
        ("06.12.34.56.78", "06 12 34 56 78"),
        ("0612345678", "06 12 34 56 78"),
        ("c'est le 0612 345 678 voilà", "c'est le 06 12 34 56 78 voilà"),
        (
            "mon numéro c'est zéro six douze trente-quatre cinquante-six soixante-dix-huit",
            "mon numéro c'est 06 12 34 56 78",
        ),
    ],
)
def test_un_telephone_de_dix_chiffres_arrive_par_paires(entendu, attendu):
    assert _reecrit(entendu) == attendu


def test_la_detection_et_lecrit_du_module_ne_changent_pas():
    (n,) = lire_nombres("Le 07/50/857872.")
    assert n.type == TELEPHONE
    assert n.ecrit == "07/50/857872"  # M2 : le module lit comme avant


@pytest.mark.parametrize(
    "texte",
    [
        "061234567",  # neuf chiffres : incomplet, tel quel
        "ça fait 3500 euros",
        "60200 Compiègne",
        "référence AB 1234",
        "plus 33 6 12 34 56 78",
    ],
)
def test_ni_incomplet_ni_montant_ni_code_postal_ni_reference_ne_sont_touches(texte):
    texte = decoller_les_chiffres(texte)
    nombres = lire_nombres(texte)
    sans_paires = [n for n in nombres if n.type != TELEPHONE or telephone_par_paires(n.ecrit) is None]
    assert len(sans_paires) == len(nombres)


def test_telephone_par_paires_refuse_ce_qui_nest_pas_un_numero_national():
    assert telephone_par_paires("+33612345678") is None
    assert telephone_par_paires("1234567890") is None
    assert telephone_par_paires("061234567") is None
    assert telephone_par_paires("07/50/857872") == "07 50 85 78 72"


def test_la_lecture_de_lappelant_donne_la_phrase_par_paires_au_modele():
    lu, lecture, *_ = _lire(
        "Le 07/50/857872.",
        adresse=None,
        trace_communes=[],
        conversion=True,
        communes=False,
        references=False,
        annoter=False,
    )
    assert "07 50 85 78 72" in lu
    assert "07/50/857872" not in lu


def test_sans_conversion_la_phrase_reste_telle_quelle():
    lu, *_ = _lire(
        "Le 07/50/857872.",
        adresse=None,
        trace_communes=[],
        conversion=False,
        communes=False,
        references=False,
        annoter=False,
    )
    assert lu == "Le 07/50/857872."
