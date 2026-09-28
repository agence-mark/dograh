"""[.mark] Non-regression test for the box « the business offers it » (L3).

The questions this file answers:

    Are « listen for it » and « the business offers it » two boxes, each read by
    its own use? Does a vocabulary saved BEFORE the second box existed read
    exactly as it did (the offered names are the ones that were ticked)? Does an
    imported template arrive with both boxes unticked? And does the agent get
    ``{{lexique_propose}}`` -- and its former name ``{{lexique_a_ecouter}}``,
    same content -- on the keyboard as on a call, from the second box only?

Why it exists
-------------
Plan « le lexique » (2026-09-26), L3 / Q4, question 182 of the labo: one box
served both uses; unticking it to shorten the transcription's list made the
agent say « on distribue bien la marque Rika », a brand the business does not
sell (run 400).

⚠️ The call's own route is proven in ``test_traversants_appel.py``
(``test_l_agent_recoit_les_noms_proposes_et_seulement_eux``).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from api.schemas.lexique_metier import LexiqueMetier
from api.services.configuration.plafond_lexique import plafond_du_lexique
from api.services.lexique.ecoute import (
    CLE_A_ECOUTER,
    CLE_PROPOSE,
    construire_liste_ecoutee,
    termes_proposes,
)
from api.services.lexique.stockage import fusionner_import

LEXIQUE = LexiqueMetier.model_validate(
    {
        "termes": [
            # Listened for AND offered.
            {"terme": "Edilkamin", "categorie": "marque", "a_ecouter": True, "propose": True},
            # Listened for, NOT offered: the business repairs it, it does not sell it.
            {"terme": "Rika", "categorie": "marque", "a_ecouter": True, "propose": False},
            # Offered, not listened for (the list is kept short).
            {"terme": "Jøtul", "categorie": "marque", "a_ecouter": False, "propose": True},
        ]
    }
)


def test_les_deux_cases_sont_lues_chacune_par_son_usage():
    ecoutee = construire_liste_ecoutee(None, LEXIQUE, plafond_du_lexique("deepgram", "nova-3"))
    assert ecoutee.termes == ["Edilkamin", "Rika"]
    assert termes_proposes(LEXIQUE) == ["Edilkamin", "Jøtul"]


def test_un_lexique_enregistre_avant_la_seconde_case_se_relit_a_lidentique():
    """No migration: the offered names are the ones that were ticked, exactly."""
    ancien = {
        "format": "lexique-mark",
        "version": 1,
        "termes": [
            {"terme": "Edilkamin", "a_ecouter": True},
            {"terme": "Supra", "a_ecouter": False},
            {"terme": "MCZ", "a_ecouter": True, "propose": None},
        ],
    }
    relu = LexiqueMetier.model_validate(ancien)
    assert [(t.terme, t.a_ecouter, t.propose) for t in relu.termes] == [
        ("Edilkamin", True, True),
        ("Supra", False, False),
        ("MCZ", True, True),
    ]
    # What the agent read before (the ticked names) is what it reads now.
    assert termes_proposes(relu) == ["Edilkamin", "MCZ"]
    # Saved again, the second box is written and read back as it is.
    assert LexiqueMetier.model_validate(relu.model_dump(mode="json")) == relu


def test_decocher_ecouter_ne_retire_plus_la_marque_proposee():
    """The very move of 2026-09-18: untick « listen for » everywhere."""
    decoche = LexiqueMetier.model_validate(
        {"termes": [{**t.model_dump(), "a_ecouter": False} for t in LEXIQUE.termes]}
    )
    assert termes_proposes(decoche) == ["Edilkamin", "Jøtul"]


def test_un_modele_importe_arrive_les_deux_cases_decochees():
    modele = LexiqueMetier.model_validate(
        {"termes": [{"terme": "Palazzetti", "a_ecouter": True, "propose": True}]}
    )
    fusion, ajoutes, _ = fusionner_import(LEXIQUE, modele)
    assert ajoutes == 1
    importe = fusion.termes[-1]
    assert (importe.terme, importe.a_ecouter, importe.propose) == ("Palazzetti", False, False)


@pytest.mark.asyncio
async def test_au_clavier_lagent_recoit_les_noms_proposes_sous_les_deux_noms():
    from api.services.workflow import text_chat_runner
    from api.tests.mark.test_date_heure_appel import _jouer_au_clavier

    with patch.object(text_chat_runner, "lire_lexique_de_lappel", AsyncMock(return_value=LEXIQUE)):
        persiste, _ = await _jouer_au_clavier(
            {}, {"direction": "inbound"}, datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
        )
    assert persiste[CLE_PROPOSE] == "Edilkamin, Jøtul"
    assert persiste[CLE_A_ECOUTER] == "Edilkamin, Jøtul"
