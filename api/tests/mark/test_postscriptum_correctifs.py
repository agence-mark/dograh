"""[.mark] Le Postscript, note d'abord : les correctifs du lot 3 (C3, C9, C10).

Plan `Labo-agent-vocal/plans/postscriptum-note-d-abord/`, lot 3.

| Test | Ce qu'il prouve |
|---|---|
| C3 réponse muette | une note seule (ni phrase ni porte) fait reparler le modèle ; une phrase, non |
| C3 une fois | le moteur ne relance qu'une fois par réplique de l'appelant |
"""

from types import SimpleNamespace

import pytest

from api.services.workflow.pipecat_engine import PipecatEngine
from api.tests.mark.test_porte_parlee_processeur import ALLUMEE, _Moteur, _MontagePortes
from api.tests.mark.test_postscriptum_note_d_abord import NOTE_D_ABORD


class _MoteurQuiRelance(_Moteur):
    def __init__(self):
        super().__init__()
        self.relances = 0

    async def relancer_une_reponse_muette(self):
        self.relances += 1
        return True


def _montage(config):
    montage = _MontagePortes(config)
    montage.moteur = _MoteurQuiRelance()
    montage.processeur._portes = montage.moteur
    return montage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config, morceaux",
    [
        (NOTE_D_ABORD, ['{"motif": "entretien"}\n|||\n']),
        (NOTE_D_ABORD, ['{"motif": "entretien"}']),
        (ALLUMEE, ['|||\n{"motif": "entretien"}']),
    ],
)
async def test_c3_une_note_seule_fait_reparler_le_modele(config, morceaux):
    montage = _montage(config)
    ordre = await montage.reponse(*morceaux)
    assert not ordre.dit.strip()
    assert montage.moteur.relances == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ['{"motif": "entretien"}\n|||\nQuelle marque ?'],
        ["→ vers_panne\n", '{"motif": "entretien"}\n|||\n'],
    ],
)
async def test_c3_une_phrase_ou_une_porte_ne_relance_pas(morceaux):
    montage = _montage(NOTE_D_ABORD)
    await montage.reponse(*morceaux)
    assert montage.moteur.relances == 0


@pytest.mark.asyncio
async def test_c3_le_moteur_ne_relance_qu_une_fois_par_replique():
    envoyees = []

    async def queue_frame(frame):
        envoyees.append(frame)

    moteur = SimpleNamespace(
        _gathered_context={"tour_appelant": 3},
        context=None,
        _replique_relancee=None,
        active_agent=SimpleNamespace(queue_frame=queue_frame),
    )
    assert await PipecatEngine.relancer_une_reponse_muette(moteur) is True
    assert await PipecatEngine.relancer_une_reponse_muette(moteur) is False
    moteur._gathered_context["tour_appelant"] = 4
    assert await PipecatEngine.relancer_une_reponse_muette(moteur) is True
    assert len(envoyees) == 2


def _moteur_sur(etape_courante, aretes, etapes):
    """Un moteur réduit à ce que `_porte_de_l_etape` lit."""
    noeud = SimpleNamespace(is_end=False, out_edges=aretes)
    return SimpleNamespace(
        active_agent=SimpleNamespace(
            current_node=noeud,
            workflow=SimpleNamespace(nodes={k: SimpleNamespace(name=v) for k, v in etapes.items()}),
        )
    )


def _arete(nom, cible):
    return SimpleNamespace(get_function_name=lambda: nom, target=cible)


def test_c9_le_nom_de_l_etape_joignable_par_une_seule_porte_prend_cette_porte():
    a = _arete("nom_numero_et_adresse_notes", "n2")
    b = _arete("demande_une_personne", "n3")
    moteur = _moteur_sur("panne", [a, b], {"n2": "coordonnees", "n3": "transfert"})
    assert PipecatEngine._porte_de_l_etape(moteur, "coordonnees") is a
    assert PipecatEngine._porte_de_l_etape(moteur, "nom_numero_et_adresse_notes") is a
    assert PipecatEngine._porte_de_l_etape(moteur, "inconnue") is None


def test_c9_deux_portes_vers_la_meme_etape_le_code_ne_choisit_pas():
    a = _arete("panne_decrite", "n2")
    b = _arete("panne_sans_marque", "n2")
    moteur = _moteur_sur("panne", [a, b], {"n2": "coordonnees"})
    assert PipecatEngine._porte_de_l_etape(moteur, "coordonnees") is None


# --------------------------------------------------------------------------- #
# C10 : la relecture d'un numéro, corrigée par le code avant la voix
# --------------------------------------------------------------------------- #

from api.services.pipecat.relecture_numeros import corriger_relecture, numero_de_reference  # noqa: E402

DICTE = {"nombres_lus": [{"type": "telephone", "ecrit": "07 47 21 93 58"}, {"type": "autre", "ecrit": "2"}]}


@pytest.mark.parametrize(
    "relu, attendu",
    [
        (
            "Le zéro six, quarante-sept, vingt et un, quatre-vingt-treize, cinquante-huit, c'est bien ça ?",
            "Le zéro sept, quarante-sept, vingt et un, quatre-vingt-treize, cinquante-huit, c'est bien ça ?",
        ),
        ("Je relis : 06 47 21 93 58, c'est correct ?", "Je relis : 07 47 21 93 58, c'est correct ?"),
    ],
)
def test_c10_un_numero_relu_faux_prend_les_chiffres_de_l_appelant(relu, attendu):
    assert corriger_relecture(relu, numero_de_reference(DICTE)) == attendu


@pytest.mark.parametrize(
    "phrase",
    [
        "Je relis : 07 47 21 93 58, c'est correct ?",
        "Votre budget est de cinq mille euros ?",
        "Vous êtes dans quelle commune, et quel est le code postal ?",
    ],
)
def test_c10_rien_d_autre_ne_change(phrase):
    assert corriger_relecture(phrase, numero_de_reference(DICTE)) == phrase


def test_c10_sans_numero_dicte_rien_ne_change():
    assert numero_de_reference({}) is None
    assert corriger_relecture("Je relis : 06 47 21 93 58 ?", None) == "Je relis : 06 47 21 93 58 ?"


def test_c10_eteinte_par_defaut():
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
    from api.services.pipecat.filtre_nom_civilite import creer_filtre_nom_civilite

    assert WorkflowConfigurationDefaults().relecture_des_numeros is False
    assert creer_filtre_nom_civilite({}, lambda: {}) is None
    assert creer_filtre_nom_civilite({"relecture_des_numeros": True}, lambda: {}) is not None


@pytest.mark.asyncio
async def test_c10_le_filtre_corrige_la_phrase_avant_la_voix():
    from pipecat.frames.frames import LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.tests import run_test
    from pipecat.tests.utils import SleepFrame

    from api.services.pipecat.filtre_nom_civilite import creer_filtre_nom_civilite
    from api.tests.mark.test_porte_parlee_processeur import DEMARRAGE_S, _Ordre

    filtre = creer_filtre_nom_civilite({"relecture_des_numeros": True}, lambda: {}, lambda: DICTE)
    ordre = _Ordre()
    await run_test(
        Pipeline([filtre, ordre]),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame("Je relis : zéro six, quarante-sept,"),
            LLMTextFrame(" vingt et un, quatre-vingt-treize, cinquante-huit. C'est bien ça ?"),
            LLMFullResponseEndFrame(),
            SleepFrame(sleep=0.2),
        ],
        start_timeout=DEMARRAGE_S,
    )
    assert "zéro sept" in ordre.dit and "zéro six" not in ordre.dit


# --------------------------------------------------------------------------- #
# C4 : l'outil de l'étape d'arrivée, appelé dès l'arrivée (porte parlée)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_c4_au_clavier_l_etape_d_arrivee_avec_un_outil_fait_reparler_le_modele(
    db_session, async_session, test_client_factory
):
    """Run 1034 : arrivée sur « transfert » à 22,6 s, outil appelé à 36,2 s, après une
    relance d'inactivité. L'étape d'arrivée porte un outil : le modèle reparle tout
    de suite dans cette étape (ici, sa seconde réponse est dite dans le même tour)."""
    from pipecat.tests import MockLLMService

    from api.tests.mark.test_clavier_porte_la_fiche import _monter
    from api.tests.mark.test_porte_parlee_clavier import ALLUMEE, _affiche
    from api.tests.mark.test_porte_parlee_consigne import _definition, _noeud
    from api.tests.mark.test_portes_souples import _messages

    definition = _definition()
    _noeud(definition, "etape")["data"]["tool_uuids"] = ["outil-de-transfert"]
    user, workflow = await _monter(db_session, async_session, ALLUMEE, definition)
    tour = (
        "je veux parler à quelqu'un",
        [
            MockLLMService.create_text_chunks("→ vers_etape\nJe vous mets en relation.\n|||\n{}"),
            MockLLMService.create_text_chunks("Un instant, je transfère.\n|||\n{}"),
        ],
    )
    charge = await _messages(test_client_factory, user, workflow, [tour])
    affiche = _affiche(charge)
    assert "Je vous mets en relation." in affiche, affiche
    assert "Un instant, je transfère." in affiche, affiche
