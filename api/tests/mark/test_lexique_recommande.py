"""[.mark] Chantier correctifs-modules, lot 2 : le lexique recommande, il ne réécrit plus.

Plan : ``Labo-agent-vocal/plans/correctifs-modules/2026-09-28-plan-correctifs-modules.md``.

| Test | Décision | Preuve (runs) |
|---|---|---|
| les mots de l'appelant restent intacts | D2 | pause du 27/09 |
| la note recommande, jamais lue, sans « fais confirmer » | D3 | 862, 873, 875 |
| un mot courant n'est jamais lu comme une marque, quel que soit ce qui le précède | D2 (amorces abandonnées) | 862, 873, 875, 880 |
| aucune liste de mots de métier dans le module | règle d'Evan | 26/09 |
| un mot courant plus rare est recommandé, jamais sûr ; le seuil est un réglage | décision d'Evan, 28/09 | 871 |
| une marque dite lettre par lettre est lue | lot 2 | 869 |
| la fiche retient la marque recommandée, sans question | D3 | 875, 881 |
| deux marques possibles : une seule question | D3 | — |
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.schemas.lexique_metier import (
    SEUIL_MOTS_COURANTS_DEFAUT,
    SEUIL_MOTS_COURANTS_MAX,
    LexiqueMetier,
)
from api.services.communes.base import charger_base
from api.services.lexique import analyse
from api.services.lexique.analyse import SURE, analyser
from api.services.pipecat.reconnaissance_lexique import (
    construire_index,
    corriger_texte,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_TOUR,
    ReglagesFiche,
    creer_gestionnaire,
)

LEXIQUE = LexiqueMetier.model_validate(
    {
        "termes": [
            {"terme": t, "type": "nom", "categorie": "marque"}
            for t in ("Edilkamin", "Palazzetti", "Hark", "Scan", "MCZ", "Invicta", "Rika", "Jøtul")
        ]
    }
)


@pytest.fixture(scope="module")
def index():
    charger_base()
    return construire_index(LEXIQUE, avec_sons=True)


async def _lu(texte, index, traces=None):
    def consigner(entree, cle=None):
        if traces is not None:
            traces.append(entree)

    return await corriger_texte(texte, index, consigner=consigner)


# --- D2 : les mots de l'appelant restent intacts -------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "texte, terme",
    [
        ("j'ai un poêle et dit le camain", "Edilkamin"),  # 861, 881
        ("c'est un poêle Palatzetti", "Palazzetti"),  # 873 : lu SÛR, réécrit en production
    ],
)
async def test_les_mots_de_l_appelant_restent_intacts(index, texte, terme):
    lu = await _lu(texte, index)
    assert lu.startswith(texte), lu
    assert terme in lu[len(texte):], lu


# --- D3 : la forme de la note --------------------------------------------------


@pytest.mark.asyncio
async def test_la_note_recommande_sans_faire_confirmer_et_n_est_jamais_lue(index):
    lu = await _lu("j'ai un poêle et dit le camain", index)
    note = lu[lu.index("[Lexique"):]
    assert "peut-être dit" in note or "a dit" in note, note
    assert "confirm" not in note.lower(), note
    assert "jamais" in note and "voix haute" in note, note


@pytest.mark.asyncio
async def test_un_nom_entendu_tel_quel_n_ajoute_aucune_note(index):
    texte = "c'est un poêle Palazzetti"
    assert await _lu(texte, index) == texte


# --- Un mot courant n'est jamais lu comme une marque ----------------------------


@pytest.mark.parametrize(
    "texte",
    [
        "C'est un poêle à granulés de la marque Palazzetti.",  # 873 : « marque » → Hark
        "de la marque joue tulle",  # 862
        "Oui, mon poêle à granulés, je sais pas quand il a été fait.",  # 875 : « quand » → Scan
    ],
)
def test_un_mot_courant_n_est_jamais_lu_comme_une_marque(index, texte):
    lues = {d.entendu.lower() for d in analyser(texte, index)}
    assert "marque" not in lues and "quand" not in lues, lues


def test_ce_qui_precede_un_mot_ne_change_pas_sa_lecture(index):
    """Sans amorces : le même passage se lit de même quel que soit le mot d'avant."""
    un = [(d.entendu, d.terme, d.statut) for d in analyser("un poêle scan", index)]
    deux = [(d.entendu, d.terme, d.statut) for d in analyser("un truc scan", index)]
    assert un == deux


def test_aucune_liste_de_mots_de_metier_dans_le_module():
    assert not hasattr(analyse, "AMORCES_FORTES")
    with open(analyse.__file__, encoding="utf-8") as fichier:
        source = fichier.read().lower()
    for mot in ("poele", "granules", "insert", "chaudiere", "cuisiniere", "foyer"):
        assert f'"{mot}"' not in source, mot


# --- Le seuil des mots courants : un réglage de l'organisation ------------------


def test_un_mot_courant_plus_rare_est_recommande_jamais_sur(index):
    """Run 871 : « Rica » (pour Rika) est dans la liste des mots courants, loin
    des plus fréquents : recommandé, jamais sûr."""
    lues = [(d.terme, d.statut) for d in analyser("mon poêle à granulés Rica fait un bruit", index)]
    assert lues == [("Rika", "a_confirmer")], lues


def test_le_seuil_est_un_reglage_de_l_organisation():
    charger_base()
    toute_la_liste = LEXIQUE.model_copy(update={"seuil_mots_courants": SEUIL_MOTS_COURANTS_MAX})
    index = construire_index(toute_la_liste, avec_sons=True)
    assert analyser("mon poêle à granulés Rica fait un bruit", index) == []


def test_le_seuil_a_un_defaut_et_des_bornes():
    assert LexiqueMetier().seuil_mots_courants == SEUIL_MOTS_COURANTS_DEFAUT == 10_000
    with pytest.raises(ValidationError):
        LexiqueMetier(seuil_mots_courants=10)
    with pytest.raises(ValidationError):
        LexiqueMetier(seuil_mots_courants=SEUIL_MOTS_COURANTS_MAX + 1)


def test_le_plafond_du_seuil_est_la_taille_de_la_liste():
    lignes = [
        m for m in analyse.FICHIER_MOTS_COURANTS.read_text(encoding="utf-8").splitlines()
        if m and not m.startswith("#")
    ]
    assert len(lignes) == SEUIL_MOTS_COURANTS_MAX


# --- Une marque dite lettre par lettre ------------------------------------------


def test_une_marque_dite_lettre_par_lettre_est_lue(index):
    lues = analyser("mon poêle à granulés m c z affiche un code", index)
    assert [(d.terme, d.statut) for d in lues] == [("MCZ", SURE)], lues


def test_des_lettres_qui_ne_font_pas_un_terme_ne_sont_pas_lues(index):
    assert analyser("c'est l a m b e r t", index) == []


# --- D3 côté fiche --------------------------------------------------------------


MARQUE = {"nom": "marque", "origine": "dicte", "lecteur": "lexique"}


async def _noter(fiche, messages, **arguments):
    reglages = ReglagesFiche.depuis(
        {"fiche_au_fil_de_leau": True, "fiche_champs": [MARQUE]}, lexique=LEXIQUE
    )
    recu = {}

    async def rappel(resultat, properties=None):
        recu["r"] = resultat

    await creer_gestionnaire(reglages, lambda: fiche, lambda: messages)(
        SimpleNamespace(arguments=arguments, tool_call_id="n", result_callback=rappel)
    )
    return recu["r"]


@pytest.mark.asyncio
async def test_la_fiche_retient_la_marque_recommandee_sans_question():
    fiche = {
        CLE_TOUR: 1,
        "lexique_reconnu": [
            {
                "entendu": "Victa",
                "statut": "a_confirmer",
                "terme": "Invicta",
                "propositions": [{"terme": "Invicta", "score": 84.0}],
                "tour": 1,
            }
        ],
    }
    r = await _noter(fiche, [{"role": "user", "content": "c'est une Victa"}], marque="Invicta")
    assert not r.get("a_confirmer"), r
    assert fiche["marque"] == "Invicta" and fiche[CLE_ETAT]["marque"]["sure"]


@pytest.mark.asyncio
async def test_deux_marques_possibles_une_seule_question():
    fiche = {
        CLE_TOUR: 1,
        "lexique_reconnu": [
            {
                "entendu": "rica",
                "statut": "a_confirmer",
                "terme": "Rika",
                "propositions": [{"terme": "Rika", "score": 84.0}, {"terme": "Scan", "score": 80.0}],
                "tour": 1,
            }
        ],
    }
    r = await _noter(fiche, [{"role": "user", "content": "c'est une rica"}], marque="rica")
    assert r["statut"] == "ambigu", r
    assert r["a_confirmer"][0]["options"] == ["Rika", "Scan"], r
