"""[.mark] Le Postscript : la note écrite en prose et lue à voix haute (B6, chantier postscriptum-et-communes).

Constat (run 1051, 3 tours sur 11) : le modèle écrit sa note sans séparateur, en prose
(« Je note : … »), et elle part à la voix. Une réponse qui COMMENCE par « je note »
(texte normalisé : casse, accents, ponctuation) est retenue ; si elle se termine sans séparateur,
elle n'est pas dite et le modèle est relancé UNE fois (même mécanisme que C3). Un séparateur qui
arrive libère la partie retenue : « Je note votre nom. Et votre numéro ? » n'est jamais perdue.

| Test | Ce qu'il prouve |
|---|---|
| prose sans séparateur | rien à la voix, une relance, trace `relance_prose` (deux ordres, case des portes éteinte ou allumée) |
| forme de « je note » | casse, accents, ponctuation, guillemets, JSON dans la prose : même geste |
| avec séparateur | la phrase est dite en entier, aucune relance |
| note d'abord | la phrase qui suit une note lue n'est jamais prise pour une prose |
| deuxième prose | pas de seconde relance (une par tour) : la phrase est dite, jamais un tour muet |
| pas de moteur | rien à relancer : la phrase est dite |
| autres débuts | « Je ne sais pas », « Je notera » : dits, même coupés en morceaux |
| autres modes | outil et greffier : le processeur n'existe pas |

Chaque cas rouge a été vu rouge avant le correctif.
"""

import pytest

from api.services.pipecat.post_scriptum import TRACE_POST_SCRIPTUM, creer_post_scriptum
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.tests.mark.test_porte_parlee_processeur import ALLUMEE, _MontagePortes
from api.tests.mark.test_post_scriptum import FICHE_SIMPLE, _Montage
from api.tests.mark.test_postscriptum_note_d_abord import NOTE_D_ABORD


class _MoteurQuiRelance:
    """Comme le vrai moteur : une seule relance par réplique de l'appelant."""

    def __init__(self):
        self.relances = 0
        self.demandes = 0

    def phrase_de_transition_ecrite(self, nom):
        return None

    async def relancer_une_reponse_muette(self):
        self.demandes += 1
        if self.relances:
            return False
        self.relances += 1
        return True


def _montage(config):
    montage = _MontagePortes(config)
    montage.moteur = _MoteurQuiRelance()
    montage.processeur._portes = montage.moteur if montage.reglages.portes_dans_la_reponse else None
    montage.processeur._moteur = montage.moteur
    return montage


def _trace(montage):
    return montage.fiche[TRACE_POST_SCRIPTUM][-1]


# Les deux ordres, la case des portes éteinte ou allumée : « toujours actif en Postscript ».
CONFIGS = [FICHE_SIMPLE, ALLUMEE, NOTE_D_ABORD]


def _pas_de_portes(config):
    return {k: v for k, v in config.items() if k != "portes_dans_la_reponse"}


@pytest.mark.asyncio
@pytest.mark.parametrize("config", CONFIGS + [_pas_de_portes(NOTE_D_ABORD)], ids=["avant", "portes", "note", "note-sans-portes"])
@pytest.mark.parametrize(
    "morceaux",
    [
        ["Je note : nom Dupont, motif entretien."],
        ["Je no", "te : nom Dupont, ", "motif entretien."],
    ],
    ids=["entiere", "coupee"],
)
async def test_la_prose_sans_separateur_n_est_pas_dite_et_relance_une_fois(config, morceaux):
    montage = _montage(config)
    ordre = await montage.reponse(*morceaux)
    assert not ordre.dit.strip()
    assert montage.moteur.relances == 1
    assert _trace(montage).get("relance_prose") is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["JE NOTE Dupont."],
        ["  je   note, Dupont."],
        ["« Je note : Dupont. »"],
        ["Je note"],
        ['Je note : {"nom": "Dupont"}'],
    ],
)
async def test_la_forme_de_je_note_est_normalisee(morceaux):
    montage = _montage(FICHE_SIMPLE)
    ordre = await montage.reponse(*morceaux)
    assert not ordre.dit.strip()
    assert montage.moteur.relances == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["Je note votre nom. Et votre numéro ?\n|||\n", '{"nom": "Dupont"}'],
        ["Je no", "te votre nom. Et votre ", "numéro ?\n|||\n", '{"nom": "Dupont"}'],
    ],
)
async def test_avec_un_separateur_la_phrase_est_dite_en_entier(morceaux):
    montage = _montage(FICHE_SIMPLE)
    ordre = await montage.reponse(*morceaux)
    assert ordre.dit.strip() == "Je note votre nom. Et votre numéro ?"
    assert montage.moteur.relances == 0
    assert montage.fiche.get("nom") == "Dupont"
    assert "relance_prose" not in _trace(montage)


@pytest.mark.asyncio
async def test_en_note_d_abord_la_phrase_apres_la_note_n_est_pas_une_prose():
    montage = _montage(NOTE_D_ABORD)
    ordre = await montage.reponse(
        '{"nom": "Dupont"}\n|||\n', "Je note votre nom. Et votre numéro ?"
    )
    assert ordre.dit.strip() == "Je note votre nom. Et votre numéro ?"
    assert montage.moteur.relances == 0


@pytest.mark.asyncio
async def test_une_deuxieme_prose_dans_le_meme_tour_ne_relance_pas_et_reste_dite():
    montage = _montage(NOTE_D_ABORD)
    premiere = await montage.reponse("Je note : nom Dupont.")
    assert not premiere.dit.strip()
    seconde = await montage.reponse("Je note : nom Dupont.")
    assert seconde.dit.strip() == "Je note : nom Dupont."
    assert montage.moteur.relances == 1
    assert "relance_prose" not in _trace(montage)


@pytest.mark.asyncio
async def test_sans_moteur_la_phrase_est_dite_jamais_un_tour_muet():
    montage = _Montage(FICHE_SIMPLE)
    ordre = await montage.reponse("Je note : nom Dupont.")
    assert "Je note : nom Dupont." in "".join(ordre.textes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["Je ne sais pas."],
        ["Je ", "ne sais pas."],
        ["Je", " no", "tera", " votre nom."],
        ["Je notera votre nom."],
        ["Bonjour, je note votre nom."],
    ],
)
async def test_les_autres_debuts_partent_a_la_voix(morceaux):
    montage = _montage(FICHE_SIMPLE)
    ordre = await montage.reponse(*morceaux)
    assert ordre.dit == "".join(morceaux)
    assert montage.moteur.relances == 0


def test_outil_et_greffier_n_ont_pas_de_processeur():
    for mode in ("outil", "greffier"):
        reglages = ReglagesFiche.depuis({**FICHE_SIMPLE, "fiche_mode_de_note": mode})
        assert (
            creer_post_scriptum(
                reglages,
                fiche=dict,
                messages=list,
                notices=None,
                portes=_MoteurQuiRelance(),
            )
            is None
        )
