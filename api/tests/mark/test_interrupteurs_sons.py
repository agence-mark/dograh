"""[.mark] Non-regression test for the two switches of the pronounced sounds.

The questions this file answers:

    Are both switches on by default, so nothing changes for an agent nobody
    touched? With one off, is the pronunciation library NEVER called for that
    use -- and does the OTHER use keep it? Is the result then exactly the one
    of the mode already used when the library is absent? Is the variant that
    ran readable afterwards (stamp and records)?

Why it exists
-------------
Decision L18 of Evan, 2026-09-17: measure what the sounds bring, with two
copies of an agent, without touching the code or deploying between two calls.
🔴 Constat of the same day: the constant ``POIDS_ESP`` cut only ONE of the two
places the town check uses the sounds (``ville_par_code`` called them
unconditionally), so a measure « sounds off » would have used them anyway and
said nothing.

⚠️ What this file does NOT prove: that the sounds help or not. That is the A/B
measure, in volume.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.schemas.lexique_metier import LexiqueMetier
from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.communes import analyse as analyse_communes
from api.services.communes.base import charger_base
from api.services.lexique import analyse as analyse_lexique
from api.services.lexique.analyse import SURE, Index, analyser
from api.services.nombres.lecture import analyser_message
from api.services.pipecat.lecture_appelant import (
    creer_lecture_appelant,
    lire_message_tape,
)
from api.services.pipecat.reconnaissance_lexique import creer_reconnaissance_lexique
from api.services.pipecat.service_factory import REGLAGES_PIPECAT_ESTAMPILLES
from api.services.pipecat.verification_communes import (
    CLE_TRACE,
    consigner_dans,
    sons_allumes,
)

MAGASIN = AdresseEtablissement(code_postal="60740", code_insee="60589", commune="Saint-Maximin")
STT_FRANCAIS = SimpleNamespace(language="fr", language_hints=None)
NOEUD = SimpleNamespace(
    name="coordonnees", extraction_variables=[SimpleNamespace(name="commune")]
)
LEXIQUE = LexiqueMetier.model_validate(
    {"termes": [{"terme": "Edilkamin", "variantes": ["Edil Kamin"], "categorie": "marque"},
                {"terme": "Termatech", "categorie": "marque"}]}
)
# Measured on 2026-09-17: the sounds alone find this one (fiche C, run 271);
# the spelling keys find nothing in it.
PAR_LE_SON = "c'est un poêle et dilcama"
# Found either way, but the sounds raise its score: the record says which decided.
PAR_LES_DEUX = "C'est un poêle thermatec."
# The towns: this one passes through BOTH places that use the sounds -- the
# analysis of the sentence, and the town decided by the postal code said.
COMMUNE_PAR_LE_CODE = "Bouvé, soixante mille"
COMMUNE_PAR_LE_SON = "j'habite à monte à terre"


@pytest.fixture(scope="module")
def base():
    return charger_base()


# --------------------------------------------------------------------------- #
# 1. The defaults
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("cle", ["sons_communes", "sons_lexique"])
def test_les_deux_interrupteurs_sont_allumes_par_defaut(cle):
    defauts = WorkflowConfigurationDefaults()
    assert getattr(defauts, cle) is True
    for configuration in ({}, None, {cle: None}):
        assert sons_allumes(configuration, cle) is True
    assert sons_allumes({cle: False}, cle) is False
    champ = WorkflowConfigurationDefaults.model_json_schema()["properties"][cle]
    assert champ["default"] is True and "sound" in champ["description"].lower()


@pytest.mark.parametrize("cle", ["sons_communes", "sons_lexique"])
def test_une_valeur_illisible_laisse_les_sons_allumes(cle):
    assert sons_allumes({cle: "n'importe quoi"}, cle) is True


@pytest.mark.parametrize("cle", ["sons_communes", "sons_lexique"])
def test_les_deux_cles_sont_estampillees(cle):
    assert cle in REGLAGES_PIPECAT_ESTAMPILLES


def test_les_interrupteurs_arrivent_aux_deux_etapes():
    etape = lambda: NOEUD  # noqa: E731
    assert creer_lecture_appelant({}, STT_FRANCAIS, MAGASIN, etape)._avec_sons is True
    assert (
        creer_lecture_appelant({"sons_communes": False}, STT_FRANCAIS, MAGASIN, etape)._avec_sons is False
    )
    assert creer_reconnaissance_lexique({}, LEXIQUE, etape)._avec_sons is True
    assert creer_reconnaissance_lexique({"sons_lexique": False}, LEXIQUE, etape)._avec_sons is False
    # Independent: one off leaves the other on.
    assert creer_lecture_appelant({"sons_lexique": False}, STT_FRANCAIS, MAGASIN, etape)._avec_sons is True
    assert creer_reconnaissance_lexique({"sons_communes": False}, LEXIQUE, etape)._avec_sons is True


# --------------------------------------------------------------------------- #
# 2. The towns: the library is never called, in BOTH places
# --------------------------------------------------------------------------- #


def _compter_les_appels():
    """Counts the calls to the pronunciation library, wherever they come from."""
    appels = []
    vrai = analyse_communes.sons

    def espion(textes):
        appels.append(list(textes))
        return vrai(textes)

    return appels, espion


@pytest.mark.parametrize("etape_adresse", [True, False], ids=["etape-adresse", "autre-etape"])
def test_communes_sons_eteints_la_bibliotheque_nest_jamais_appelee(base, etape_adresse):
    appels, espion = _compter_les_appels()
    magasin = base.coordonnees("60589")
    with patch.object(analyse_communes, "sons", espion):
        analyser_message(
            "j'habite à monte à terre, soixante mille",
            base, magasin, [], etape_adresse=etape_adresse, avec_sons=False,
        )
    assert appels == []


def test_avec_les_sons_les_deux_endroits_appellent_bien_la_bibliotheque(base):
    """The counts above mean something only if the sounds ARE called otherwise.

    « Bouvé, soixante mille » passes through both: the analysis of the sentence,
    then the town decided by the postal code.
    """
    appels, espion = _compter_les_appels()
    magasin = base.coordonnees("60589")
    with patch.object(analyse_communes, "sons", espion):
        analyser_message(COMMUNE_PAR_LE_CODE, base, magasin, [], avec_sons=True)
    assert len(appels) == 2, appels


def test_la_ville_par_le_code_nappelle_plus_les_sons_non_plus(base):
    """🔴 ``POIDS_ESP`` cut only ``analyser``: this second place stayed."""
    appels, espion = _compter_les_appels()
    magasin = base.coordonnees("60589")
    with patch.object(analyse_communes, "sons", espion):
        analyser_message(COMMUNE_PAR_LE_CODE, base, magasin, [], avec_sons=False)
    assert appels == []


def test_eteints_le_resultat_est_celui_du_mode_sans_bibliotheque(base):
    """Off must be exactly « library absent », not a third behaviour."""
    magasin = base.coordonnees("60589")
    lues = 0
    for texte in [COMMUNE_PAR_LE_SON, COMMUNE_PAR_LE_CODE, "c'est à Beauvet", "Sanlis"]:
        lues += 1
        eteint = analyser_message(texte, base, magasin, [], avec_sons=False).detections
        with patch.object(analyse_communes, "sons", lambda textes: None):
            absent = analyser_message(texte, base, magasin, []).detections
        assert [(d.entendu, d.statut, d.lectures[0].commune.nom) for d in eteint] == [
            (d.entendu, d.statut, d.lectures[0].commune.nom) for d in absent
        ], texte
    assert lues == 4


@pytest.mark.asyncio
async def test_au_clavier_aussi_les_sons_sont_coupes(base):
    appels, espion = _compter_les_appels()
    with patch.object(analyse_communes, "sons", espion):
        await lire_message_tape(
            COMMUNE_PAR_LE_SON, {"sons_communes": False}, STT_FRANCAIS, MAGASIN, NOEUD, None
        )
    assert appels == []


@pytest.mark.asyncio
async def test_la_trace_dune_commune_dit_si_le_son_a_decide(base):
    recueilli: dict = {}
    await lire_message_tape(
        COMMUNE_PAR_LE_SON, {}, STT_FRANCAIS, MAGASIN, NOEUD, consigner_dans(lambda: recueilli)
    )
    entrees = recueilli.get(CLE_TRACE) or []
    assert entrees and "par_son" in entrees[0]


# --------------------------------------------------------------------------- #
# 3. The trade vocabulary
# --------------------------------------------------------------------------- #


def test_lexique_sons_eteints_la_bibliotheque_nest_jamais_appelee(base):
    appels = []
    vrai = analyse_lexique.sons

    def espion(textes):
        appels.append(list(textes))
        return vrai(textes)

    with patch.object(analyse_lexique, "sons", espion):
        index = Index.construire(LEXIQUE, base.par_nom, avec_sons=False)
        analyser(PAR_LE_SON, index, avec_sons=False)
    assert appels == []
    with patch.object(analyse_lexique, "sons", espion):
        index = Index.construire(LEXIQUE, base.par_nom, avec_sons=True)
        analyser(PAR_LE_SON, index, avec_sons=True)
    assert appels != []


def test_lexique_sons_eteints_le_nom_trouve_par_le_son_nest_plus_lu(base):
    avec = Index.construire(LEXIQUE, base.par_nom, avec_sons=True)
    sans = Index.construire(LEXIQUE, base.par_nom, avec_sons=False)
    if not avec.sons_disponibles:
        pytest.skip("pronunciation library unavailable")
    assert [(d.terme, d.statut, d.par_son) for d in analyser(PAR_LE_SON, avec)] == [
        ("Edilkamin", "a_confirmer", True)
    ]
    assert analyser(PAR_LE_SON, sans, avec_sons=False) == []
    # Found either way, but the record says the sounds decided the score.
    assert [d.par_son for d in analyser(PAR_LES_DEUX, avec)] == [True]
    assert [d.par_son for d in analyser(PAR_LES_DEUX, sans, avec_sons=False)] == [False]
    # A name well spelled is read either way.
    assert [d.statut for d in analyser("c'est un Edilcamin", sans, avec_sons=False)] == [SURE]


def test_les_deux_usages_sont_independants(base):
    """One switch off leaves the other use of the library untouched."""
    appels_communes, espion_communes = _compter_les_appels()
    magasin = base.coordonnees("60589")
    with patch.object(analyse_communes, "sons", espion_communes):
        index = Index.construire(LEXIQUE, base.par_nom, avec_sons=False)
        assert analyser(PAR_LE_SON, index, avec_sons=False) == []
        analyser_message(COMMUNE_PAR_LE_CODE, base, magasin, [], avec_sons=True)
    assert len(appels_communes) == 2, appels_communes
