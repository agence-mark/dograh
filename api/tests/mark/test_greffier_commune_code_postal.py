"""[.mark] La commune du greffier recoupée avec le code postal (chantier greffier-conversation, lot F).

Plan `Labo-agent-vocal/plans/greffier-conversation/`, lot F (C6, runs 1121 et 1122) : le
greffier écrit « Abreteuil », la personne a dit 60120 ; parmi les communes de ce code, une seule
ressemble au son (Breteuil) : la fiche porte Breteuil, sûre, avec son code INSEE.

| Test | Ce qu'il prouve |
|---|---|
| recoupée | par le champ de code postal ou par le dernier code lu par le module des nombres |
| rien | aucune commune proche, ou un code postal absent : rien ne change |
| autres modes | l'outil et le Post-scriptum gardent leur comportement (lot du greffier) |
| greffier | par une vraie passe du greffier, la commune écrite est Breteuil |
"""

import pytest

from api.services.communes.base import charger_base
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    MODE_GREFFIER,
    TRACE_NOMBRES,
    ReglagesFiche,
    attendre_les_notes,
    cle_insee,
    ecrire_dans_la_fiche,
)

CHAMPS = [
    {"nom": "commune", "origine": "dicte"},
    {"nom": "code_postal", "origine": "dicte"},
]
PAROLES = ["j'habite à Abreteuil, 60120"]


@pytest.fixture(scope="module", autouse=True)
def base():
    return charger_base()


def _reglages(mode: str = MODE_GREFFIER) -> ReglagesFiche:
    return ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": CHAMPS,
            "fiche_mode_de_note": mode,
        }
    )


def _ecrire(fiche: dict, valeur="Abreteuil", source=MODE_GREFFIER, mode=MODE_GREFFIER):
    return ecrire_dans_la_fiche(
        fiche, _reglages(mode), "commune", valeur, source=source, paroles=PAROLES
    )


def test_recoupee_par_le_champ_de_code_postal():
    fiche = {"code_postal": "60120"}
    verdict = _ecrire(fiche)
    assert verdict.statut == "ecrit", verdict
    assert fiche["commune"] == "Breteuil"
    assert fiche[CLE_ETAT]["commune"]["sure"] is True
    assert fiche[cle_insee("commune")]


def test_recoupee_par_le_dernier_code_lu_par_le_module():
    fiche = {TRACE_NOMBRES: [{"type": "code_postal", "ecrit": "60120"}]}
    _ecrire(fiche)
    assert fiche["commune"] == "Breteuil"


@pytest.mark.parametrize(
    "fiche",
    [{}, {"code_postal": "60600"}],
    ids=["sans-code-postal", "aucune-commune-proche"],
)
def test_rien_ne_change_sans_recoupement(fiche):
    _ecrire(fiche)
    assert fiche.get("commune") == "Abreteuil"
    assert not fiche[CLE_ETAT]["commune"]["sure"]


@pytest.mark.parametrize("mode", ["outil", "post_scriptum"])
def test_les_autres_modes_gardent_leur_comportement(mode):
    fiche = {"code_postal": "60120"}
    _ecrire(fiche, source=mode, mode=mode)
    assert fiche.get("commune") != "Breteuil"


@pytest.mark.asyncio
async def test_par_une_passe_du_greffier():
    from api.services.pipecat.greffier import Greffier
    from api.services.workflow.fiche_au_fil_de_leau import Notices
    from api.tests.mark.test_greffier import _Modele

    fiche: dict = {}
    notes: set = set()
    greffier = Greffier(
        service=_Modele({"commune": "Abreteuil", "code_postal": "60120"}),
        reglages=_reglages(),
        fiche=lambda: fiche,
        messages=lambda: [{"role": "user", "content": PAROLES[0]}],
        notices=Notices(),
        notes_en_cours=notes,
    )
    greffier.declencher()
    await attendre_les_notes(notes, delai=5)
    # Le greffier rend la commune AVANT le code postal : elle est relue une fois le code
    # postal écrit, dans la même passe.
    assert fiche["code_postal"] == "60120"
    assert fiche["commune"] == "Breteuil"
    assert fiche[CLE_ETAT]["commune"]["sure"] is True


@pytest.mark.asyncio
async def test_le_code_postal_d_une_passe_suivante_fait_relire_la_commune():
    from api.services.workflow.fiche_au_fil_de_leau import noter

    reglages = _reglages()
    fiche: dict = {}
    await noter(
        lambda: fiche,
        reglages,
        {"commune": "Abreteuil"},
        paroles=PAROLES,
        question=None,
        source=MODE_GREFFIER,
    )
    assert fiche["commune"] == "Abreteuil"
    note = await noter(
        lambda: fiche,
        reglages,
        {"code_postal": "60120"},
        paroles=PAROLES,
        question=None,
        source=MODE_GREFFIER,
    )
    assert fiche["commune"] == "Breteuil", fiche
    assert "commune" in note.ecrits and note.retenus["commune"] == "Breteuil"
