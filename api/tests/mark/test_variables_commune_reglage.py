"""[.mark] Non-regression test for the setting that names the town variables.

The question this file answers, and only this one:

    Do the steps that get the town check follow the agent's ``variables_commune``
    setting -- on the phone AND on the keyboard -- with today's rule when the
    setting is absent, empty or unreadable, and is a bad name refused on save?

Why it exists
-------------
Until 2026-09-17 the rule was written in the code: a step was checked when it
extracted ``commune``, ``commune_…`` or ``adresse…``. A client whose variable is
called ``ville`` or ``lieu_chantier`` got no check at all, without a word, and
only a patch could fix it. The names are now a setting of the agent (decision
of Evan, 2026-09-17), default ``commune, commune_*, adresse*``.

⛔ Tested at the level of the feature: the step built by the SAME factory the
pipeline calls (``creer_lecture_appelant``, asserted on the pipeline's source
in ``test_verification_communes_branchement.py``), and the keyboard path RUN
through ``text_chat_runner`` up to the model's queue. A test of the pure
function alone would stay green if the setting were never read.

⚠️ What this file does NOT prove: that the town recognised is right
(``test_analyse_communes.py``), nor that the screen shows the field
(``ui/src/components/mark/section-reglages-pipecat-montee.test.tsx``).
"""

from types import SimpleNamespace

import pytest
from loguru import logger
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests import run_test

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat.lecture_appelant import creer_lecture_appelant
from api.services.pipecat.service_factory import stamp_pipeline_settings
from api.services.pipecat.verification_communes import (
    CLE_TRACE,
    consigner_dans,
    etape_concernee,
    variables_commune,
)
from api.tests.mark.test_horaires_ouverture_reglage import _application, _enregistrer
from api.tests.mark.test_verification_communes_branchement import (
    DEMARRAGE_S,
    MAGASIN,
    MENTION_BEAUVAIS,
    NOEUD_COORDONNEES,
    STT_FRANCAIS,
    _message_tape_jusquau_modele,
)

DEFAUT = ("commune", "commune_*", "adresse*")
PERSONNALISEE = "ville, lieu_chantier, adresse*"


def _noeud(*noms: str, nom_etape: str = "coordonnees"):
    return SimpleNamespace(
        name=nom_etape, extraction_variables=[SimpleNamespace(name=n) for n in noms]
    )


NOEUD_VILLE = _noeud("numero", "ville")


# --------------------------------------------------------------------------- #
# 1. The rule, by default and customised
# --------------------------------------------------------------------------- #


def test_le_defaut_est_la_regle_davant():
    assert WorkflowConfigurationDefaults().variables_commune == "commune, commune_*, adresse*"
    # Absent, null or blank in the stored configuration: the default.
    for configuration in ({}, None, {"variables_commune": None}, {"variables_commune": ""},
                          {"variables_commune": "   "}):
        assert variables_commune(configuration) == DEFAUT


@pytest.mark.parametrize(
    "nom,attendu",
    [
        ("commune", True),
        ("commune_intervention", True),
        ("adresse", True),
        ("adresse_intervention", True),
        ("Commune", True),
        ("ville", False),
        ("communes", False),
        ("lieu_chantier", False),
    ],
)
def test_par_defaut_les_memes_etapes_quavant(nom, attendu):
    assert etape_concernee(_noeud(nom), variables_commune({})) is attendu


@pytest.mark.parametrize(
    "nom,attendu",
    [
        ("ville", True),
        ("Ville", True),
        ("lieu_chantier", True),
        ("adresse_chantier", True),
        # Replaced, not added: the default names no longer count.
        ("commune", False),
        ("commune_intervention", False),
        ("villes", False),
        ("lieu_chantier_bis", False),
    ],
)
def test_une_liste_personnalisee_remplace_la_regle(nom, attendu):
    variables = variables_commune({"variables_commune": PERSONNALISEE})
    assert variables == ("ville", "lieu_chantier", "adresse*")
    assert etape_concernee(_noeud(nom), variables) is attendu


def test_casse_espaces_et_virgule_finale_ne_comptent_pas():
    assert variables_commune({"variables_commune": "  VILLE ,Lieu_Chantier,  "}) == ("ville", "lieu_chantier")


@pytest.mark.parametrize(
    "illisible",
    ["ville chantier", "*", "adr*esse", "ville;adresse", 12, ["ville"]],
)
def test_une_valeur_illisible_rend_le_defaut_avec_un_avertissement(illisible):
    avertissements: list[str] = []
    puits = logger.add(lambda m: avertissements.append(m), level="WARNING")
    try:
        assert variables_commune({"variables_commune": illisible}) == DEFAUT
    finally:
        logger.remove(puits)
    assert any("default used" in a for a in avertissements), avertissements


def test_la_valeur_illisible_ne_relit_que_sa_cle():
    """⛔ Another setting stored out of bounds must not change the names here."""
    assert variables_commune({"max_call_duration": 0, "variables_commune": "ville"}) == ("ville",)


# --------------------------------------------------------------------------- #
# 2. The phone path: the step built by the pipeline's factory
# --------------------------------------------------------------------------- #


async def _lu_par_le_modele(configuration: dict, noeud) -> tuple[str, dict]:
    recueilli: dict = {}
    etape = creer_lecture_appelant(
        configuration, STT_FRANCAIS, MAGASIN, lambda: noeud, consigner_dans(lambda: recueilli)
    )
    contexte = LLMContext(messages=[{"role": "user", "content": "c'est à Beauvet"}])
    await run_test(etape, frames_to_send=[LLMContextFrame(context=contexte)], start_timeout=DEMARRAGE_S)
    return contexte.messages[-1]["content"], recueilli


@pytest.mark.asyncio
async def test_appel_la_variable_ville_declenche_avec_le_reglage():
    lu, recueilli = await _lu_par_le_modele({"variables_commune": PERSONNALISEE}, NOEUD_VILLE)
    assert lu == f"c'est à Beauvet {MENTION_BEAUVAIS}"
    assert len(recueilli[CLE_TRACE]) == 1


@pytest.mark.asyncio
async def test_appel_la_variable_commune_ne_declenche_plus_avec_le_reglage():
    lu, recueilli = await _lu_par_le_modele({"variables_commune": PERSONNALISEE}, NOEUD_COORDONNEES)
    assert lu == "c'est à Beauvet"
    assert CLE_TRACE not in recueilli


@pytest.mark.asyncio
async def test_appel_sans_reglage_la_regle_davant():
    """Both ways: ``commune`` still triggers, ``ville`` still does not."""
    lu, _ = await _lu_par_le_modele({}, NOEUD_COORDONNEES)
    assert lu == f"c'est à Beauvet {MENTION_BEAUVAIS}"
    lu, _ = await _lu_par_le_modele({}, NOEUD_VILLE)
    assert lu == "c'est à Beauvet"


@pytest.mark.asyncio
async def test_appel_valeur_illisible_la_regle_davant_et_lappel_continue():
    lu, _ = await _lu_par_le_modele({"variables_commune": "ville chantier"}, NOEUD_COORDONNEES)
    assert lu == f"c'est à Beauvet {MENTION_BEAUVAIS}"


# --------------------------------------------------------------------------- #
# 3. The keyboard path, RUN through text_chat_runner
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_clavier_suit_le_reglage_de_lagent():
    contexte, recueilli = await _message_tape_jusquau_modele(
        "c'est à Beauvet", {"variables_commune": PERSONNALISEE}, noeud=NOEUD_VILLE
    )
    assert contexte.messages[-1]["content"] == f"c'est à Beauvet {MENTION_BEAUVAIS}"
    assert len(recueilli[CLE_TRACE]) == 1

    contexte, recueilli = await _message_tape_jusquau_modele(
        "c'est à Beauvet", {"variables_commune": PERSONNALISEE}, noeud=NOEUD_COORDONNEES
    )
    assert contexte.messages[-1]["content"] == "c'est à Beauvet"
    assert CLE_TRACE not in recueilli


@pytest.mark.asyncio
async def test_clavier_sans_reglage_la_variable_ville_ne_declenche_pas():
    contexte, _ = await _message_tape_jusquau_modele("c'est à Beauvet", {}, noeud=NOEUD_VILLE)
    assert contexte.messages[-1]["content"] == "c'est à Beauvet"


# --------------------------------------------------------------------------- #
# 4. Saved through the route, stamped on the call
# --------------------------------------------------------------------------- #


def test_la_route_ecrit_une_liste_valide():
    reponse, ecrit = _enregistrer({"variables_commune": PERSONNALISEE})
    assert reponse.status_code == 200, reponse.text
    assert ecrit["variables_commune"] == PERSONNALISEE


@pytest.mark.parametrize("fautive", ["ville chantier", "*", "adr*esse"])
def test_la_route_refuse_un_nom_invalide_et_necrit_rien(fautive):
    reponse, ecrit = _enregistrer({"variables_commune": fautive})
    assert reponse.status_code == 422
    assert "is not a variable name" in reponse.text
    assert ecrit is None


def test_la_route_ecrit_le_defaut_pour_un_champ_vide():
    reponse, ecrit = _enregistrer({"variables_commune": "  "})
    assert reponse.status_code == 200, reponse.text
    assert ecrit["variables_commune"] == "commune, commune_*, adresse*"


def test_le_champ_figure_dans_la_spec_publiee():
    proprietes = _application().openapi()["components"]["schemas"][
        "WorkflowConfigurationDefaults"
    ]["properties"]
    assert proprietes["variables_commune"]["default"] == "commune, commune_*, adresse*"
    assert proprietes["variables_commune"]["maxLength"] == 500


def test_lappel_estampille_les_noms_avec_lesquels_il_a_ete_joue():
    assert stamp_pipeline_settings({}, {})["pipeline_settings"]["variables_commune"] == (
        "commune, commune_*, adresse*"
    )
    assert stamp_pipeline_settings({}, {"variables_commune": "ville"})["pipeline_settings"][
        "variables_commune"
    ] == "ville"
