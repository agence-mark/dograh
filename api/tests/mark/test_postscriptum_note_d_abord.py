"""[.mark] Le Postscript, note d'abord (plan postscriptum-note-d-abord, S1) : le processeur.

Ordre « porte, note, phrase » : la note n'est jamais dite, elle part à ``noter`` dès le
séparateur, la phrase va à la voix ensuite. Le moteur est le témoin de
`test_porte_parlee_processeur.py`.

| Test | Ce qu'il prouve |
|---|---|
| note, séparateur, phrase (entiers ou coupés) | seule la phrase est dite ; la note est écrite dans la fiche |
| porte, note, phrase | la ligne « → » et la note ne sont jamais dites ; la porte part au moteur |
| note fermée sans séparateur | la phrase qui suit est dite, la note écrite, la trace le dit |
| ordre d'avant | le modèle commence par sa phrase : elle part tout de suite, sa note est écrite |
| note seule | rien de technique à la voix ; la note est écrite |
| séparateur vide | « ||| » en tête : note vide, phrase dite |
| ordre d'avant réglé | sans le réglage, rien ne change (l'ordre d'avant) |
"""

import pytest

from api.services.pipecat.post_scriptum import ABSENT, PRESENT, TRACE_POST_SCRIPTUM, VIDE
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ORDRE_DE_LA_REPONSE,
    ORDRE_NOTE_PUIS_PHRASE,
    ORDRE_PHRASE_PUIS_NOTE,
    ReglagesFiche,
)
from api.tests.mark.test_porte_parlee_processeur import ALLUMEE, _MontagePortes

NOTE_D_ABORD = {**ALLUMEE, CLE_ORDRE_DE_LA_REPONSE: ORDRE_NOTE_PUIS_PHRASE}


def _trace(montage):
    return montage.fiche[TRACE_POST_SCRIPTUM][-1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ['{"motif": "entretien"}\n|||\nQuelle est la marque ?'],
        ['{"motif": "entre', 'tien"}\n||', '|\nQuelle est ', "la marque ?"],
        ["```json\n", '{"motif": "entretien"}\n```\n|||', "Quelle est la marque ?"],
    ],
)
async def test_note_puis_phrase(morceaux):
    montage = _MontagePortes(NOTE_D_ABORD)
    ordre = await montage.reponse(*morceaux)
    assert ordre.dit.strip() == "Quelle est la marque ?"
    assert montage.fiche.get("motif") == "entretien"
    assert _trace(montage)["etat"] == PRESENT


@pytest.mark.asyncio
async def test_porte_note_phrase():
    montage = _MontagePortes(NOTE_D_ABORD)
    ordre = await montage.reponse(
        "→ vers_panne\n", '{"motif": "entretien"}\n|||\n', "Quelle est la marque ?"
    )
    assert ordre.dit.strip() == "Quelle est la marque ?"
    assert "→" not in ordre.dit and "{" not in ordre.dit
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]
    assert montage.fiche.get("motif") == "entretien"


@pytest.mark.asyncio
async def test_note_fermee_sans_separateur():
    montage = _MontagePortes(NOTE_D_ABORD)
    ordre = await montage.reponse('{"motif": "entretien"}', "\nQuelle est la marque ?")
    assert ordre.dit.strip() == "Quelle est la marque ?"
    assert montage.fiche.get("motif") == "entretien"
    assert _trace(montage).get("sans_separateur") is True


@pytest.mark.asyncio
async def test_le_modele_garde_l_ordre_d_avant():
    montage = _MontagePortes(NOTE_D_ABORD)
    ordre = await montage.reponse("Quelle est ", "la marque ?\n|||\n", '{"motif": "entretien"}')
    assert ordre.dit.strip() == "Quelle est la marque ?"
    assert montage.fiche.get("motif") == "entretien"


@pytest.mark.asyncio
async def test_note_seule_rien_de_technique_a_la_voix():
    montage = _MontagePortes(NOTE_D_ABORD)
    ordre = await montage.reponse('{"motif": ', '"entretien"}')
    assert "{" not in ordre.dit and "motif" not in ordre.dit
    assert montage.fiche.get("motif") == "entretien"
    assert _trace(montage)["etat"] in (PRESENT, ABSENT)


@pytest.mark.asyncio
async def test_separateur_en_tete_note_vide():
    montage = _MontagePortes(NOTE_D_ABORD)
    ordre = await montage.reponse("|||\nQuelle est la marque ?")
    assert ordre.dit.strip() == "Quelle est la marque ?"
    assert _trace(montage)["etat"] == VIDE


def test_sans_le_reglage_l_ordre_d_avant():
    assert ReglagesFiche.depuis(ALLUMEE).ordre == ORDRE_PHRASE_PUIS_NOTE
    assert not ReglagesFiche.depuis(ALLUMEE).note_d_abord
    assert ReglagesFiche.depuis(NOTE_D_ABORD).note_d_abord
    hors_postscript = {**NOTE_D_ABORD, "fiche_mode_de_note": "outil"}
    assert not ReglagesFiche.depuis(hors_postscript).note_d_abord
