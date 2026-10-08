"""[.mark] Règle de standardisation (Evan, 08/10) : chaque mécanisme du Postscript vaut pour
n'importe quel champ, de n'importe quel métier, par simple réglage, sans nom de champ dans le code.

Plan `Labo-agent-vocal/plans/postscriptum-note-d-abord/`. La preuve : une fiche factice d'un
autre secteur (un garage), aucun code qui la connaisse.

| Test | Ce qu'il prouve |
|---|---|
| consigne | en note d'abord, un champ cumulatif dit « écris seulement ce qui est nouveau » ; un champ recopié dit « = » ; rien de cela dans l'ordre d'avant pour le cumulatif |
| recopie | Postscript : le code recopie la réplique ; hors Postscript : la valeur notée reste |
| cumulatif | deux notes courtes s'ajoutent, rien n'est écrasé |
| indices | une valeur de la liste du garage, dite, est un indice |
"""

import pytest

from api.services.workflow.fiche_au_fil_de_leau import (
    CUMULATIF_EN_POST_SCRIPTUM,
    ReglagesFiche,
    consigne_du_mode,
    noter,
)
from api.services.workflow.indices_des_modules import indices_des_modules

GARAGE = {
    "fiche_au_fil_de_leau": True,
    "fiche_mode_de_note": "post_scriptum",
    "fiche_champs": [
        {
            "nom": "intervention",
            "origine": "deduit",
            "description": "Ce que le client demande au garage",
            "valeurs": ["vidange", "freinage", "contrôle technique"],
        },
        {
            "nom": "bruit_signale",
            "origine": "deduit",
            "description": "Ce que le client entend ou constate",
            "cumulatif": True,
        },
        {
            "nom": "demande_du_client",
            "origine": "dicte",
            "description": "Sa demande, mot pour mot",
            "copie_de_la_parole": True,
        },
    ],
}
NOTE_D_ABORD = {**GARAGE, "ordre_de_la_reponse": "porte_note_phrase"}


def _ligne(consigne: str, champ: str) -> str:
    return next(ligne for ligne in consigne.splitlines() if ligne.startswith(f"- {champ} :"))


def test_la_consigne_des_champs_par_reglage_seulement():
    consigne = consigne_du_mode(ReglagesFiche.depuis(NOTE_D_ABORD))
    assert CUMULATIF_EN_POST_SCRIPTUM in _ligne(consigne, "bruit_signale")
    assert CUMULATIF_EN_POST_SCRIPTUM not in _ligne(consigne, "intervention")
    assert 'écris seulement "="' in _ligne(consigne, "demande_du_client")
    # L'ordre d'avant ne change pas (comportement d'avant par défaut).
    assert CUMULATIF_EN_POST_SCRIPTUM not in consigne_du_mode(ReglagesFiche.depuis(GARAGE))


@pytest.mark.asyncio
async def test_la_recopie_en_postscript_seulement():
    parole = "Bonjour, j'ai un bruit de frottement à l'avant quand je freine."
    fiche: dict = {}
    await noter(
        lambda: fiche,
        ReglagesFiche.depuis(GARAGE),
        {"demande_du_client": "="},
        paroles=[parole],
        question=None,
        source="post_scriptum",
    )
    assert fiche.get("demande_du_client") == parole

    hors_postscript = {**GARAGE, "fiche_mode_de_note": "outil"}
    fiche = {}
    await noter(
        lambda: fiche,
        ReglagesFiche.depuis(hors_postscript),
        {"demande_du_client": "un bruit de frottement à l'avant"},
        paroles=[parole],
        question=None,
        source="outil",
    )
    assert fiche.get("demande_du_client") == "un bruit de frottement à l'avant"


@pytest.mark.asyncio
async def test_le_cumulatif_ajoute_les_notes_courtes():
    reglages = ReglagesFiche.depuis(NOTE_D_ABORD)
    fiche: dict = {}
    for note, parole in [
        ("frottement à l'avant", "un frottement à l'avant"),
        ("seulement au freinage", "et seulement au freinage"),
    ]:
        await noter(
            lambda: fiche,
            reglages,
            {"bruit_signale": note},
            paroles=[parole],
            question=None,
            source="post_scriptum",
        )
    assert fiche.get("bruit_signale") == "frottement à l'avant ; seulement au freinage"


def test_les_indices_lisent_les_listes_du_garage():
    ligne = indices_des_modules(
        ReglagesFiche.depuis(GARAGE),
        "c'est pour le contrôle technique et une vidange",
        {},
    )
    assert ligne is not None and "intervention = contrôle technique ou vidange" in ligne
