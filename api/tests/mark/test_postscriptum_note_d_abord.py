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

from api.services.pipecat.post_scriptum import (
    ABSENT,
    PRESENT,
    TRACE_POST_SCRIPTUM,
    VIDE,
)
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
        ['{"motif": "entre', 'tien"}\n||', "|\nQuelle est ", "la marque ?"],
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
    ordre = await montage.reponse(
        "Quelle est ", "la marque ?\n|||\n", '{"motif": "entretien"}'
    )
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


def test_consigne_note_d_abord_porte_en_tete_et_note_avant_la_relecture():
    from api.services.workflow.fiche_au_fil_de_leau import consigne_du_mode

    texte = consigne_du_mode(ReglagesFiche.depuis(NOTE_D_ABORD))
    assert "0. Si tu prends une porte" in texte
    assert "la relecture vient après la note" in texte
    assert "|||" in texte and "{}" in texte
    avant = consigne_du_mode(ReglagesFiche.depuis(ALLUMEE))
    assert "0. Si tu prends une porte" not in avant


def test_une_date_dite_en_chiffres_notee_en_lettres_est_dite():
    """Rejeu du 08/10 (runs 1044, 1046) : « il y a 2 ans » transcrit, « il y a deux
    ans » noté : refusé « non dit », la porte partait sans la date."""
    from api.services.workflow.fiche_au_fil_de_leau import est_cite, est_dit_tel_quel

    paroles = ["Euh... il y a 2 ans."]
    assert est_cite("il y a deux ans", paroles)
    assert est_dit_tel_quel("il y a deux ans", paroles)
    assert not est_dit_tel_quel("il y a trois ans", paroles)


@pytest.mark.asyncio
async def test_c8_le_filtre_du_nom_lit_le_nom_de_la_note_avant_la_voix(monkeypatch):
    """C8 (banc du 07/10, run 1038) : en note d'abord, le nom noté dans la réponse
    est dans la fiche avant que la phrase n'arrive au filtre : il n'est pas dit.
    `noter` ralenti (0,1 s, une commune relue) : sans l'attente, le nom passait (R7)."""
    import asyncio

    import api.services.pipecat.post_scriptum as module

    noter_vrai = module.noter

    async def noter_lent(*args, **kwargs):
        await asyncio.sleep(0.1)
        return await noter_vrai(*args, **kwargs)

    monkeypatch.setattr(module, "noter", noter_lent)
    from pipecat.frames.frames import (
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.tests.utils import SleepFrame

    from api.services.pipecat.filtre_nom_civilite import FiltreNomCiviliteProcessor
    from api.services.workflow.fiche_au_fil_de_leau import attendre_les_notes
    from api.tests.mark.test_porte_parlee_processeur import DEMARRAGE_S, _Ordre
    from pipecat.tests import run_test

    montage = _MontagePortes(NOTE_D_ABORD)
    montage.messages = [{"role": "user", "content": "C'est Dupont, D-U-P-O-N-T."}]
    filtre = FiltreNomCiviliteProcessor(
        retirer_nom=True, retirer_civilite=True, variables=lambda: montage.fiche
    )
    ordre = _Ordre()
    await run_test(
        Pipeline([montage.processeur, filtre, ordre]),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame('{"nom": "Dupont"}\n|||\n'),
            LLMTextFrame("Merci, monsieur"),
            LLMTextFrame(" Dupont. Votre numéro ?"),
            LLMFullResponseEndFrame(),
            SleepFrame(sleep=0.3),
        ],
        start_timeout=DEMARRAGE_S,
    )
    await attendre_les_notes(montage.notes)
    assert montage.fiche.get("nom") == "Dupont"
    assert "Dupont" not in ordre.dit and "monsieur" not in ordre.dit
    assert "Votre numéro ?" in ordre.dit
