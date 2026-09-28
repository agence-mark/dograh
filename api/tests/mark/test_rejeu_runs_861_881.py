"""[.mark] Zéro perte par rapport à la production sur les tours réels des runs 861 à 881.

La question : rejoués par la vraie route (processeurs du lexique et de la lecture de
l'appelant, gestionnaire de ``noter_information``, passe de fin d'appel), les champs cibles
de chaque run sont-ils rangés au moins aussi bien que sur le code de production
(``c9d22a18``, mesure figée dans ``donnees/rejeu_reference_production_c9d22a18.json``) ?

Rang, du meilleur au pire : juste et sûr, juste à confirmer, vide, faux (``rejeu_corpus``).
⛔ Ne jamais modifier la référence pour faire passer ce test : une cible moins bien rangée
est une perte. Chantier correctifs-modules, règle d'Evan du 17/09 (« zéro perte »).
"""

import json
from pathlib import Path

import pytest

from api.tests.mark.boucle_isolee import executer_sans_toucher_la_boucle_courante
from api.tests.mark.rejeu_corpus import (
    NOMS_DES_RANGS,
    charger,
    mesurer,
    rejouer_run,
)

REFERENCE = json.loads(
    (Path(__file__).parent / "donnees" / "rejeu_reference_production_c9d22a18.json").read_text(
        encoding="utf-8"
    )
)
RANG = {nom: rang for rang, nom in NOMS_DES_RANGS.items()}
CORPUS = charger()


@pytest.fixture(scope="module")
def mesures():
    async def tout():
        return {
            str(run["id"]): mesurer(await rejouer_run(run, CORPUS), run) for run in CORPUS["runs"]
        }

    return executer_sans_toucher_la_boucle_courante(tout())


def test_le_corpus_couvre_les_runs_861_a_881():
    assert [r["id"] for r in CORPUS["runs"]] == list(range(861, 882))
    assert "0778527349" not in json.dumps(CORPUS)


@pytest.mark.parametrize("run", [str(i) for i in range(861, 882)])
def test_aucune_cible_moins_bien_rangee_qu_en_production(mesures, run):
    avant = REFERENCE["mesures"][run]["cibles"]
    apres = mesures[run]["cibles"]
    pertes = {
        champ: f"{avant[champ]} -> {apres[champ]}"
        for champ in avant
        if RANG[apres[champ]] < RANG[avant[champ]]
    }
    assert not pertes, pertes
