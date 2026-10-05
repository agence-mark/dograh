"""[.mark] Le processeur lit la porte écrite dans la réponse (plan porte-parlee, lot 4).

Plan `Labo-agent-vocal/plans/porte-parlee/`, D4, D6, D9, D10, D16. Le moteur est remplacé par un
témoin qui dit ce qu'il a reçu ; le moteur réel est joué dans `test_porte_parlee_moteur.py` et
au clavier. Chaque cas a été vu ROUGE avant d'être vert (R7).

| Test | Ce qu'il prouve |
|---|---|
| ligne entière, coupée en 2 et 3 morceaux | la ligne « → » n'est jamais dite, la porte part au moteur à la fin de la réponse |
| où qu'elle soit | après la phrase, après le séparateur : retenue, prise |
| nom inconnu, « → » sans nom, deux lignes | rien de dit, la trace le dit, seule la première porte compte |
| sans « → » | le moteur n'est pas appelé, la trace est celle d'avant |
| `||` | D9 : lu comme séparateur, jamais dit |
| phrase après la note | D10 : dite à la fin, tracée |
| porte seule | le moteur relance le modèle (rien n'a été dit) |
| interruption | ligne complète : porte prise (D6) ; ligne coupée : jamais prise |
| phrase de transition | D16 : écrite, elle part AVANT la phrase du modèle, une fois |
| filtre du nom | combiné : le nom part, la ligne de porte n'arrive jamais au filtre |
| case éteinte | une ligne « → » part à la voix comme avant (comportement d'avant, à l'octet) |
"""

import pytest
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests.utils import SleepFrame

from api.services.pipecat.filtre_nom_civilite import FiltreNomCiviliteProcessor
from api.services.pipecat.post_scriptum import (
    INTERROMPU,
    PRESENT,
    VIDE,
    creer_post_scriptum,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_PORTES_DANS_LA_REPONSE,
    attendre_les_notes,
)
from api.tests.mark.test_post_scriptum import DEMARRAGE_S, FICHE_SIMPLE, _Montage
from pipecat.tests import run_test

ALLUMEE = {**FICHE_SIMPLE, CLE_PORTES_DANS_LA_REPONSE: True}
PORTES = {"vers_fin", "vers_panne"}


class _Moteur:
    """Le témoin du moteur : ce que le processeur lui a donné."""

    def __init__(self, transition: str | None = None):
        self.prises: list[dict] = []
        self.transition = transition

    def phrase_de_transition_ecrite(self, nom: str):
        return self.transition if nom in PORTES else None

    async def prendre_porte_ecrite(self, nom, **options):
        self.prises.append({"nom": nom, **options})
        return "prise" if nom in PORTES else "inconnue"


class _Ordre(FrameProcessor):
    """Tout ce qui part à la voix, dans l'ordre : (figée|dite, texte)."""

    def __init__(self):
        super().__init__()
        self.suite: list[tuple[str, str]] = []

    @property
    def dit(self) -> str:
        return "".join(t for genre, t in self.suite if genre == "dite")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSSpeakFrame):
            self.suite.append(("figee", frame.text))
        elif isinstance(frame, LLMTextFrame) and not frame.skip_tts:
            self.suite.append(("dite", frame.text))
        await self.push_frame(frame, direction)


class _MontagePortes(_Montage):
    def __init__(self, config: dict = ALLUMEE, transition: str | None = None, **kw):
        super().__init__(config, **kw)
        self.moteur = _Moteur(transition)
        self.processeur = creer_post_scriptum(
            self.reglages,
            fiche=lambda: self.fiche,
            messages=lambda: self.messages,
            notices=self.notices,
            attendu=lambda: True,
            notes_en_cours=self.notes,
            portes=self.moteur,
        )

    async def jouer(self, *frames: Frame, avant=()) -> _Ordre:
        ordre = _Ordre()
        await run_test(
            Pipeline([*avant, self.processeur, ordre]),
            frames_to_send=[*frames, SleepFrame(sleep=0.3)],
            start_timeout=DEMARRAGE_S,
        )
        await attendre_les_notes(self.notes)
        return ordre

    async def reponse(self, *morceaux: str) -> _Ordre:
        return await self.jouer(
            LLMFullResponseStartFrame(),
            *[LLMTextFrame(m) for m in morceaux],
            LLMFullResponseEndFrame(),
        )


# --------------------------------------------------------------------------- #
# 1. La ligne « → », entière ou coupée
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["→ vers_panne\nQuelle marque ?\n|||\n", '{"motif": "entretien"}'],
        ["→ vers_pa", "nne\nQuelle marque ?", "|||", '{"motif": "entretien"}'],
        ["→", " vers_", "panne\n", "Quelle marque ?|||", '{"motif": "entretien"}'],
        ["  →  « vers_panne »\nQuelle marque ?|||", '{"motif": "entretien"}'],
    ],
    ids=["entiere", "coupee-en-deux", "coupee-en-trois", "guillemets-et-blancs"],
)
async def test_la_ligne_n_est_jamais_dite_la_porte_part_au_moteur(morceaux):
    montage = _MontagePortes()
    ordre = await montage.reponse(*morceaux)
    assert ordre.dit.strip() == "Quelle marque ?"
    assert "→" not in ordre.dit and "vers_panne" not in ordre.dit
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]
    assert montage.moteur.prises[0]["relancer"] is False
    assert montage.fiche.get("motif") == "entretien"
    assert montage.traces == [
        {
            "tour": None,
            "etat": PRESENT,
            "champs": ["motif"],
            "porte": "vers_panne",
            "porte_etat": "prise",
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["Quelle marque ?\n→ vers_panne\n|||", '{"motif": "entretien"}'],
        ["Quelle marque ?|||", '{"motif": "entretien"}\n→ vers_panne'],
        ["Quelle marque ?\n|||\n→ vers_panne\n", '{"motif": "entretien"}'],
    ],
    ids=["apres-la-phrase", "apres-la-note", "apres-le-separateur"],
)
async def test_la_ligne_est_retenue_ou_qu_elle_soit(morceaux):
    montage = _MontagePortes()
    ordre = await montage.reponse(*morceaux)
    assert ordre.dit.strip() == "Quelle marque ?"
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]
    assert montage.fiche.get("motif") == "entretien"


# --------------------------------------------------------------------------- #
# 2. Les lignes mal formées
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_un_nom_inconnu_est_trace_et_l_appel_continue():
    montage = _MontagePortes()
    ordre = await montage.reponse("→ porte_inventee\nQuelle marque ?|||{}")
    assert ordre.dit.strip() == "Quelle marque ?"
    assert montage.traces[-1]["porte"] == "porte_inventee"
    assert montage.traces[-1]["porte_etat"] == "inconnue"


@pytest.mark.asyncio
async def test_une_fleche_sans_nom_n_appelle_pas_le_moteur():
    montage = _MontagePortes()
    ordre = await montage.reponse("→\nQuelle marque ?|||{}")
    assert ordre.dit.strip() == "Quelle marque ?"
    assert montage.moteur.prises == []
    assert montage.traces[-1]["porte_etat"] == "sans_nom"


@pytest.mark.asyncio
async def test_deux_lignes_seule_la_premiere_porte_compte():
    montage = _MontagePortes()
    await montage.reponse("→ vers_panne\n→ vers_fin\nQuelle marque ?|||{}")
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]
    assert montage.traces[-1]["portes_en_trop"] == 1


@pytest.mark.asyncio
async def test_sans_fleche_rien_ne_change():
    montage = _MontagePortes()
    ordre = await montage.reponse('Quelle marque ?|||{"motif": "entretien"}')
    assert ordre.dit == "Quelle marque ?"
    assert montage.moteur.prises == []
    assert montage.traces == [{"tour": None, "etat": PRESENT, "champs": ["motif"]}]


@pytest.mark.asyncio
async def test_une_fleche_au_milieu_d_une_ligne_n_est_pas_une_porte():
    montage = _MontagePortes()
    ordre = await montage.reponse("Du salon → à la cuisine ?|||{}")
    assert ordre.dit == "Du salon → à la cuisine ?"
    assert montage.moteur.prises == []


# --------------------------------------------------------------------------- #
# 3. Séparateur toléré (D9), phrase après la note (D10), porte seule
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ['Quelle marque ? || {"motif": "entretien"}'],
        ["Quelle marque ? |", '| {"motif": "entretien"}'],
    ],
    ids=["entier", "coupe"],
)
async def test_deux_barres_valent_separateur(morceaux):
    montage = _MontagePortes()
    ordre = await montage.reponse(*morceaux)
    assert ordre.dit.strip() == "Quelle marque ?"
    assert "|" not in ordre.dit
    assert montage.fiche.get("motif") == "entretien"


@pytest.mark.asyncio
async def test_la_phrase_ecrite_apres_la_note_est_dite():
    montage = _MontagePortes()
    ordre = await montage.reponse(
        '→ vers_panne\n|||\n{"motif": "entretien"}\nQuelle marque ?'
    )
    assert ordre.dit.strip() == "Quelle marque ?"
    assert montage.fiche.get("motif") == "entretien"
    assert montage.traces[-1]["phrase_apres_note"] is True
    # Quelque chose a été dit : pas de relance.
    assert montage.moteur.prises[0]["relancer"] is False


@pytest.mark.asyncio
async def test_une_porte_seule_fait_reparler_le_modele():
    montage = _MontagePortes()
    ordre = await montage.reponse("→ vers_panne\n|||\n{}")
    assert ordre.dit.strip() == ""
    assert montage.moteur.prises[0]["relancer"] is True
    assert montage.traces[-1]["etat"] == VIDE


# --------------------------------------------------------------------------- #
# 4. L'interruption (D6)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_coupee_apres_la_ligne_la_porte_est_prise_quand_meme():
    montage = _MontagePortes()
    await montage.jouer(
        LLMFullResponseStartFrame(),
        LLMTextFrame("→ vers_panne\nQuelle"),
        # Le texte d'abord : une frame système passerait avant lui dans le banc.
        SleepFrame(sleep=0.1),
        InterruptionFrame(),
    )
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]
    assert montage.moteur.prises[0]["relancer"] is False
    assert montage.traces[-1]["etat"] == INTERROMPU
    assert montage.traces[-1]["porte_etat"] == "prise"


@pytest.mark.asyncio
async def test_coupee_dans_la_ligne_la_porte_n_est_jamais_prise():
    montage = _MontagePortes()
    ordre = await montage.jouer(
        LLMFullResponseStartFrame(),
        LLMTextFrame("→ vers_pa"),
        SleepFrame(sleep=0.1),
        InterruptionFrame(),
    )
    assert montage.moteur.prises == []
    assert ordre.dit == ""


# --------------------------------------------------------------------------- #
# 5. La phrase de transition écrite (D16)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_transition_ecrite_part_avant_la_phrase_une_fois():
    montage = _MontagePortes(transition="Un petit instant.")
    ordre = await montage.reponse("→ vers_panne\n", "Quelle ", "marque ?|||{}")
    assert ordre.suite[0] == ("figee", "Un petit instant.")
    assert [g for g, _ in ordre.suite].count("figee") == 1
    assert ordre.dit.strip() == "Quelle marque ?"
    assert montage.moteur.prises[0]["transition_dite"] is True


@pytest.mark.asyncio
async def test_porte_apres_la_phrase_la_transition_reste_au_moteur():
    montage = _MontagePortes(transition="Un petit instant.")
    ordre = await montage.reponse("Quelle marque ?", "\n→ vers_panne\n|||{}")
    assert ("figee", "Un petit instant.") not in ordre.suite
    assert montage.moteur.prises[0]["transition_dite"] is False


# --------------------------------------------------------------------------- #
# 6. Le filtre du nom, et la case éteinte
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_combine_au_filtre_du_nom():
    montage = _MontagePortes(fiche={"nom": "Dupont"})
    filtre = FiltreNomCiviliteProcessor(
        retirer_nom=True, retirer_civilite=True, variables=lambda: montage.fiche
    )
    ordre = _Ordre()
    await run_test(
        Pipeline([montage.processeur, filtre, ordre]),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame("→ vers_panne\nC'est noté, monsieur"),
            LLMTextFrame(" Dupont."),
            LLMTextFrame(" Quelle marque ?\n||"),
            LLMTextFrame('|\n{"motif": "entretien"}'),
            LLMFullResponseEndFrame(),
            SleepFrame(sleep=0.3),
        ],
        start_timeout=DEMARRAGE_S,
    )
    await attendre_les_notes(montage.notes)
    assert ordre.dit.strip() == "C'est noté. Quelle marque ?"
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]


@pytest.mark.asyncio
async def test_case_eteinte_la_fleche_part_a_la_voix_comme_avant():
    montage = _MontagePortes(config=FICHE_SIMPLE)
    ordre = await montage.reponse("→ vers_panne\nQuelle marque ?|||{}")
    assert "→ vers_panne" in ordre.dit
    assert montage.moteur.prises == []
    assert "porte" not in montage.traces[-1]
