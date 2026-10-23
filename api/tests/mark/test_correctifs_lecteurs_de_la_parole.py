"""[.mark] Chantier correctifs-apres-banc-commun, lot 4 : lecteurs de la parole (K3, K12, K9).

| Test | La garantie |
|---|---|
| K3 chiffres | un passage qui contient un chiffre n'est jamais lu comme une marque (« Moreau, 07 55… » → Morso, run 1498) |
| K3 mot courant | un mot courant n'est proposé que s'il est écrit exactement comme le nom (« devis » → Deville, runs 1498 et 1502) ; une marque qui est elle-même un mot courant, dite telle quelle, reste proposée |
| K3 zéro perte | une marque mal transcrite (« Edilcamin ») est lue comme avant |
| K12 jours et mois | un jour, un mois ou un mot de date n'est jamais une commune (« Vendredi » → Vendrest, run 1511) ; une commune dite avec « commune » ou « habite » garde sa lecture ; une vraie commune à côté d'un jour est lue |
| K9 « un neuf » | « un/une neuf » reste en lettres, sauf dans une suite de nombres ou avant une unité ; « à neuf », « tout neuf » inchangés |
| K9 balayage | sur les phrases du corpus de non-régression qui contiennent « neuf », la lecture est la même avec et sans la règle |
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

from api.schemas.lexique_metier import LexiqueMetier
from api.services.communes.analyse import analyser as analyser_communes
from api.services.communes.base import charger_base
from api.services.lexique.analyse import SURE, A_CONFIRMER, analyser
from api.services.nombres import lecture
from api.services.nombres.lecture import lire_nombres, reecrire
from api.services.pipecat.reconnaissance_lexique import construire_index

# --------------------------------------------------------------------------- #
# K3
# --------------------------------------------------------------------------- #

LEXIQUE = LexiqueMetier.model_validate(
    {
        "termes": [
            {"terme": t, "type": "nom", "categorie": "marque"}
            for t in ("Morso", "Nobis", "Deville", "Edilkamin", "Rika", "Hark")
        ]
    }
)


@pytest.fixture(scope="module")
def index():
    charger_base()
    return construire_index(LEXIQUE, avec_sons=True)


def _lues(texte, index):
    return [(d.entendu, d.terme, d.statut) for d in analyser(texte, index)]


@pytest.mark.parametrize(
    "texte",
    ["Moreau, 07 55 12 34 56", "mon nom c'est Moreau 07 55", "c'est le 07 55 Moreau 12 34"],
)
def test_k3_un_passage_avec_un_chiffre_n_est_jamais_une_marque(index, texte):
    """Run 1498 : « Moreau, 07 55… » lu Morso (88,9, sûr), l'agent demandait « Nobis ou Morso ? »."""
    assert not [t for _, t, _ in _lues(texte, index) if t in ("Morso", "Nobis")], _lues(texte, index)


def test_k3_un_mot_courant_n_est_pas_propose_s_il_n_est_pas_ecrit_comme_le_nom(index):
    """Runs 1498, 1502 : « devis » lu Deville (88,9)."""
    assert _lues("c'est pour un devis", index) == []
    assert _lues("mon poêle à granulés Rica fait un bruit", index) == []


def test_k3_une_marque_qui_est_un_mot_courant_dite_telle_quelle_reste_proposee():
    charger_base()
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "Rica", "type": "nom", "categorie": "marque"}]}
    )
    lues = analyser("mon poêle à granulés Rica fait un bruit", construire_index(lexique, avec_sons=True))
    assert [(d.terme, d.statut) for d in lues] == [("Rica", A_CONFIRMER)], lues


def test_k3_zero_perte_une_marque_mal_transcrite_est_lue_comme_avant(index):
    assert [(t, s) for _, t, s in _lues("c'est un Edilcamin", index)] == [("Edilkamin", SURE)]
    assert [(t, s) for _, t, s in _lues("un Edil camin à granulés", index)] == [("Edilkamin", SURE)]


# --------------------------------------------------------------------------- #
# K12
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def base():
    return charger_base()


def _communes(texte, base):
    magasin = base.coordonnees("60589")
    return [(d.statut, d.lectures[0].commune.nom) for d in analyser_communes(texte, base, magasin)]


@pytest.mark.parametrize(
    "texte",
    [
        "Vendredi",
        "oui vendredi",
        "c'est vendredi",
        "le jeudi",
        "je suis disponible vendredi",
        "vendredi matin",
        "c'est pour mercredi prochain",
        "ce serait jeudi matin",
    ],
)
def test_k12_un_jour_n_est_jamais_une_commune(base, texte):
    """Run 1511 : « Vendredi » lu Vendrest, à confirmer."""
    assert _communes(texte, base) == []


def test_k12_une_vraie_commune_a_cote_d_un_jour_est_lue(base):
    assert ("sure", "Beauvais") in _communes("vendredi, j'habite à Beauvais", base)
    assert ("sure", "Beauvais") in _communes("j'habite à Beauvais, plutôt vendredi", base)


def test_k12_zero_perte_la_commune_dite_comme_une_commune_reste_lue(base):
    """Une commune qui porte un nom de mois (« Mars ») reste lue quand la personne dit que c'en est une."""
    assert any(nom == "Mars" for _, nom in _communes("j'habite la commune de Mars", base))
    assert any(nom == "Mars" for _, nom in _communes("la ville de Mars", base))


# --------------------------------------------------------------------------- #
# K9
# --------------------------------------------------------------------------- #


def _ecrit(texte, base):
    return reecrire(texte, lire_nombres(texte, base.par_cp, base.departements))


@pytest.mark.parametrize(
    "texte",
    [
        "j'ai un neuf",
        "j'ai pris une neuf",
        "un poêle neuf, pas d'occasion",
        "il y a un neuf et un ancien",
        "un vieux et un neuf",
        "j'en veux un neuf, pas un d'occasion",
    ],
)
def test_k9_un_neuf_reste_en_lettres(base, texte):
    """Run 1505 : « un neuf » (un poêle neuf) devenu « 1 9 », le greffier notait « 9 poêles »."""
    assert _ecrit(texte, base) == texte


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("zéro six un neuf quatre", "06 1 9 4"),  # suite de nombres : un numéro
        ("zéro six douze un neuf", "06 12 1 9"),
        ("c'est remis à neuf, venez à neuf heures", "c'est remis à neuf, venez à 9 heures"),
        ("un poêle tout neuf", "un poêle tout neuf"),
    ],
)
def test_k9_une_suite_de_nombres_et_les_figees_d_avant_sont_inchangees(base, texte, attendu):
    assert _ecrit(texte, base) == attendu


def _phrases_du_corpus():
    phrases: set[str] = set()

    def parcourir(o):
        if isinstance(o, dict):
            for v in o.values():
                parcourir(v)
        elif isinstance(o, list):
            for v in o:
                parcourir(v)
        elif isinstance(o, str) and 6 <= len(o) <= 400 and " " in o:
            phrases.add(o)

    for chemin in glob.glob(str(Path(__file__).parent / "donnees" / "*.json")):
        try:
            parcourir(json.loads(Path(chemin).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(p for p in phrases if " neuf" in p.lower() or "neuf " in p.lower())


def test_k9_balayage_du_corpus_de_non_regression_la_lecture_ne_change_pas(base):
    """Balayage K9 : toutes les phrases du corpus (``donnees/*.json``) qui contiennent « neuf » sont lues
    pareil avec et sans la règle « un/une neuf » : rien de ce que le corpus attend n'est perdu."""
    phrases = _phrases_du_corpus()
    assert len(phrases) > 30, len(phrases)
    avec = {p: _ecrit(p, base) for p in phrases}
    sauve = lecture._FIGEES
    lecture._FIGEES = tuple(e for e in sauve if e not in (("un", "neuf"), ("une", "neuf")))
    try:
        sans = {p: _ecrit(p, base) for p in phrases}
    finally:
        lecture._FIGEES = sauve
    assert [p for p in phrases if avec[p] != sans[p]] == []
