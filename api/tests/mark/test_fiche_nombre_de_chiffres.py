"""[.mark] C1 : un nombre de chiffres déclarable sur un champ de la fiche.

Chantier correctifs-banc-34 (29/09/2026), décision D-C1. Run 887 : le modèle a écrit
« 06298450107 » (11 chiffres) pour un numéro de rappel, `noter_information` l'a accepté ;
la relecture et la reconfirmation l'ont rattrapé, rien ne l'empêchait d'entrer dans la fiche.

⛔ Aucun mot de métier dans le code : ce n'est pas « le numéro de téléphone » qui est
contrôlé, c'est tout champ qui DÉCLARE `chiffres` (vide = aucun contrôle, le défaut).

| Test | Ce qu'il prouve |
|---|---|
| déclaré, trop ou pas assez | refusé au point d'écriture unique, raison `nombre_de_chiffres`, consigne « fais redonner en entier » |
| déclaré, le bon compte | écrit tel quel, espaces compris |
| non déclaré | 11 chiffres acceptés : rien ne change pour un agent qui ne déclare rien |
| passe de fin d'appel | la même règle : le balayage ne fait pas entrer ce que l'outil refuse |
| schéma de l'outil | le modèle voit le nombre attendu dans la description du paramètre |
| déclaration | 0 ou plus de 30 refusé à l'enregistrement |
| clavier (traversant) | par les vraies routes du clavier, un numéro à 11 chiffres ne reste pas dans la fiche |
"""

import pytest
from pydantic import ValidationError

from api.schemas.fiche_agent import ChampFiche
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    ecrire_dans_la_fiche,
    schema_outil,
)
from api.tests.mark.test_clavier_porte_la_fiche import _converser, _monter, _noter
from api.tests.mark.test_fiche_correctifs_modules import Appel, _reglages
from pipecat.tests import MockLLMService

NUMERO = {"nom": "numero_rappel", "origine": "dicte", "description": "Numéro de rappel", "chiffres": 10}


@pytest.mark.asyncio
@pytest.mark.parametrize("valeur", ["06298450107", "062984510", "06 29 84 51 07 7"])
async def test_C1_trop_ou_pas_assez_de_chiffres_refuse_avec_consigne(valeur):
    appel = Appel(_reglages(NUMERO))
    appel.dit(f"c'est le {valeur}")
    resultat = await appel.note(numero_rappel=valeur)
    assert "numero_rappel" not in appel.fiche
    assert resultat["statut"] == "rien_note", resultat
    assert resultat["refuses"] == [
        {"champ": "numero_rappel", "raison": "nombre_de_chiffres", "chiffres_attendus": 10}
    ], resultat
    assert "chiffres" in resultat["consigne"] and "en entier" in resultat["consigne"], resultat
    # Le refus ne dit pas « pas dit tel quel » : ce serait faux, et il pousserait à relire.
    assert "dit tel quel" not in resultat["consigne"], resultat
    assert appel.fiche[CLE_JOURNAL][-1]["raison"] == "nombre_de_chiffres"


@pytest.mark.asyncio
@pytest.mark.parametrize("valeur", ["0629845107", "06 29 84 51 07"])
async def test_C1_le_bon_compte_est_ecrit_tel_quel(valeur):
    appel = Appel(_reglages(NUMERO))
    appel.dit(f"c'est le {valeur}")
    resultat = await appel.note(numero_rappel=valeur)
    assert appel.fiche["numero_rappel"] == valeur, resultat


@pytest.mark.asyncio
async def test_C1_non_declare_rien_ne_change():
    appel = Appel(_reglages({**NUMERO, "chiffres": None}))
    appel.dit("c'est le 06298450107")
    await appel.note(numero_rappel="06298450107")
    assert appel.fiche["numero_rappel"] == "06298450107"


def test_C1_la_passe_de_fin_d_appel_suit_la_meme_regle():
    reglages = _reglages(NUMERO)
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche,
        reglages,
        "numero_rappel",
        "06298450107",
        source="balayage",
        paroles=["c'est le 06298450107"],
        seulement_si_vide=True,
    )
    assert (verdict.statut, verdict.raison) == ("refuse", "nombre_de_chiffres")
    assert "numero_rappel" not in fiche


def test_C1_le_modele_voit_le_nombre_attendu():
    proprietes = schema_outil(_reglages(NUMERO, {"nom": "nom", "origine": "dicte"})).properties
    assert "10 chiffres" in proprietes["numero_rappel"]["description"]
    assert "chiffres" not in proprietes["nom"]["description"]


@pytest.mark.parametrize("chiffres", [0, 31, -2])
def test_C1_declaration_hors_bornes_refusee(chiffres):
    with pytest.raises(ValidationError):
        ChampFiche.model_validate({**NUMERO, "chiffres": chiffres})


@pytest.mark.asyncio
async def test_C1_au_clavier_un_numero_a_11_chiffres_ne_reste_pas_dans_la_fiche(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(
        db_session, async_session, {"fiche_au_fil_de_leau": True, "fiche_champs": [NUMERO]}
    )
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            _noter({"numero_rappel": "06298450107"}, "note_1"),
            MockLLMService.create_text_chunks("Pouvez-vous me redonner le numéro en entier ?"),
        ],
        "c'est le 06 29 84 50 107",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert "numero_rappel" not in fiche, fiche
    assert fiche[CLE_JOURNAL][-1]["raison"] == "nombre_de_chiffres", fiche[CLE_JOURNAL]
