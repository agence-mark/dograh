"""[.mark] Le code ne fait confirmer que le critique (chantier greffier-conversation, lot D).

Plan `Labo-agent-vocal/plans/greffier-conversation/`, lot D (C3, D5 du 13/10) : tout secteur,
tout mode de note, le code ne fait confirmer que le **nom**, le **téléphone**, l'**adresse e-mail**
et les **références**, reconnus par les réglages de l'agent (champ de nom, ``variables_telephone``,
``variables_courriel``, ``variables_reference``), plus, comme avant (Evan, 13/10), une **adresse non
reconnue** et **toute valeur ambiguë** (deux marques possibles = une question, règle du 28/09). Le
reste « à confirmer » (une marque d'un seul son, un appareil) est noté tel qu'entendu, sans question
(runs 1123, 1124 : « la marque est Edilcama, c'est bien cela ? »).

| Test | Ce qu'il prouve |
|---|---|
| critiques | nom, téléphone, e-mail, référence reconnus par les réglages, y compris un nom réglé à la main |
| adresse | commune ou rue non reconnue : toujours une question, comme avant (notice et état) |
| ambigu | deux possibilités, quel que soit le champ (une marque aussi) : une question |
| reste | une marque d'un seul son, un appareil : pas de question, mais toujours non sûrs dans la fiche |
| outil (R1) | par le vrai gestionnaire de l'outil : une marque hors lexique n'est plus « à confirmer » ; un nom non cité, lui, est refusé comme avant |
| greffier | la notice d'une passe du greffier ne porte que le critique |
"""

import pytest

from api.schemas.lexique_metier import LexiqueMetier
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    INCOHERENT,
    Note,
    ReglagesFiche,
    a_faire_confirmer,
    champ_critique,
    confirmation_critique,
    etat_de_la_fiche,
    reponse_de_l_outil,
)
from api.tests.mark.test_fiche_correctifs_modules import Appel, _a_faire_confirmer

LEXIQUE = LexiqueMetier.model_validate(
    {"termes": [{"terme": "Nordica", "type": "nom"}]}
)
CHAMPS = [
    {"nom": "nom", "origine": "dicte"},
    {"nom": "prenom", "origine": "dicte"},
    {"nom": "telephone", "origine": "dicte"},
    {"nom": "courriel", "origine": "dicte"},
    {"nom": "reference_facture", "origine": "dicte"},
    {"nom": "plaque", "origine": "dicte"},
    {"nom": "commune", "origine": "dicte"},
    {"nom": "adresse_intervention", "origine": "dicte"},
    {"nom": "marque", "origine": "dicte", "lecteur": "lexique"},
    {"nom": "appareil", "origine": "dicte"},
]


def _reglages(**reglages) -> ReglagesFiche:
    return ReglagesFiche.depuis(
        {"fiche_au_fil_de_leau": True, "fiche_champs": CHAMPS, **reglages},
        lexique=LEXIQUE,
    )


# --------------------------------------------------------------------------- #
# 1. Ce qui est critique, par les réglages de l'agent
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "nom", ["nom", "prenom", "telephone", "courriel", "reference_facture"]
)
def test_les_champs_critiques_sont_reconnus_par_les_reglages(nom):
    assert champ_critique(_reglages(), nom)


@pytest.mark.parametrize("nom", ["marque", "appareil", "plaque", "commune", "inconnu"])
def test_le_reste_n_est_pas_critique(nom):
    assert not champ_critique(_reglages(), nom)


def test_une_reference_reglee_a_la_main_est_critique():
    """Tout secteur : le garage déclare sa plaque comme une référence, à l'écran."""
    reglages = _reglages(variables_reference="reference*, plaque")
    assert champ_critique(reglages, "plaque")


# --------------------------------------------------------------------------- #
# 2. L'adresse : seulement ambiguë, ou contredite
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nom", ["commune", "adresse_intervention"])
def test_une_adresse_non_reconnue_reste_une_question_comme_avant(nom):
    reglages = _reglages()
    assert confirmation_critique(reglages, {"champ": nom, "options": ["A", "B"]})
    assert confirmation_critique(reglages, {"champ": nom, "valeur": "A"})
    assert a_faire_confirmer(reglages, nom, {"sure": False, INCOHERENT: True})
    assert a_faire_confirmer(reglages, nom, {"sure": False})


def test_une_marque_ambigue_reste_une_question_regle_du_28_09():
    reglages = _reglages()
    assert confirmation_critique(
        reglages, {"champ": "marque", "options": ["Rika", "Scan"]}
    )
    assert not confirmation_critique(reglages, {"champ": "marque", "valeur": "Zorvex"})


def test_la_reponse_de_l_outil_ne_porte_que_ce_qui_reste():
    note = Note(ecrits=["marque"], a_confirmer=[])
    assert reponse_de_l_outil(note) == {"statut": "note", "ecrits": ["marque"]}


def test_l_etat_montre_le_reste_note_et_le_critique_a_confirmer():
    fiche = {
        "nom": "Lefevre",
        "marque": "Zorvex",
        "appareil": "insert",
        CLE_ETAT: {
            "nom": {"sure": False},
            "marque": {"sure": False},
            "appareil": {"sure": False},
        },
    }
    lignes = etat_de_la_fiche(_reglages(), fiche).splitlines()
    assert lignes[1] == "Noté : marque = « Zorvex » ; appareil = « insert »"
    assert lignes[2] == "À confirmer : nom = « Lefevre »"


# --------------------------------------------------------------------------- #
# 3. Par le vrai gestionnaire de l'outil (R1)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_par_l_outil_une_marque_hors_lexique_n_est_plus_a_confirmer():
    appel = Appel(_reglages())
    appel.dit("c'est un poêle Zorvex")
    r = await appel.note(marque="Zorvex")
    assert "marque" not in _a_faire_confirmer(r), r
    assert "Noté, mais pas vérifié" not in (r.get("consigne") or "")
    assert appel.fiche["marque"] == "Zorvex"
    assert not appel.sure("marque")  # notée telle qu'entendue, jamais dite sûre


@pytest.mark.asyncio
async def test_par_l_outil_une_commune_ambigue_reste_une_question():
    appel = Appel(_reglages())
    appel.dit("j'habite à ponce")
    appel.trace(
        "communes_verifiees",
        entendu="ponce",
        statut="a_confirmer",
        commune_retenue=None,
        propositions=[
            {
                "nom": "Pont-Sainte-Maxence",
                "code_insee": "60509",
                "departement": "Oise",
                "codes_postaux": ["60700"],
            },
            {
                "nom": "Ponthion",
                "code_insee": "51441",
                "departement": "Marne",
                "codes_postaux": ["51300"],
            },
        ],
    )
    r = await appel.note(commune="ponce")
    assert "commune" in _a_faire_confirmer(r), r


# --------------------------------------------------------------------------- #
# 4. Le greffier : la même règle (D5, tous modes)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_notice_du_greffier_ne_porte_que_le_critique():
    from api.services.pipecat.greffier import Greffier
    from api.services.workflow.fiche_au_fil_de_leau import Notices, attendre_les_notes
    from api.tests.mark.test_greffier import _Modele

    reglages = _reglages(fiche_mode_de_note="greffier")
    fiche: dict = {}
    notices = Notices()
    notes: set = set()
    greffier = Greffier(
        service=_Modele({"marque": "Zorvex"}),
        reglages=reglages,
        fiche=lambda: fiche,
        messages=lambda: [{"role": "user", "content": "c'est un poêle Zorvex"}],
        notices=notices,
        notes_en_cours=notes,
    )
    greffier.declencher()
    await attendre_les_notes(notes, delai=5)
    assert fiche["marque"] == "Zorvex"
    assert "a_confirmer" not in (notices.derniere or {}), notices.derniere
