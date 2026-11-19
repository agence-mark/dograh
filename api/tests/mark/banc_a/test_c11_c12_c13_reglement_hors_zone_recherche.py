"""[.mark] Banc A, familles C11 (règlement et numéro), C12 (hors zone) et C13 (recherche).

| Test | Run, tour | Ce que le client voulait |
|---|---|---|
| c11_1 | 2639 t4 | « en carte » dit dès la première phrase (noté par le greffier) : le règlement n'est pas redemandé |
| c11_2 | 2652 t6 | billet de 50 dit d'emblée : le rendu calculé est DIT dans la confirmation |
| c11_3 | 2652 t6 | numéro dicté alors que le prénom est connu : le numéro est relu avant l'enregistrement |
| c12_1 | 2645 t1 | livraison refusée (Compiègne) : l'emporter est proposé |
| c12_2 | 2644 t2 | idem, autre run |
| c13_1 | 2663 t2 | « moitié reine moitié 4 fromages » : la moitié-moitié est prise (les noms courants valent aussi dans les moitiés) |
| c13_2 | 2640 t3 | « une pizza avec des sardines » : jamais la Regina proposée par ressemblance de lettres |
| c13_3 | 2640 / 2641 | « du poisson, du thon, des anchois » : les pizzas qui contiennent l'ingrédient sont trouvées (Neptune, Napoli) |
| c13_4 | 2670 t5 | « base tomate » départage deux homonymes de catégories différentes : 4 Formaggi pizza x2 |

Lot 3 (D48) : rejoué en fiches (``fiches_des_runs.py``) ; la recherche passe par ``lire`` (sujet ``article``).
"""

import json

import pytest

from api.tests.mark.banc_a.commun import TranscriptionManquante, appel_de, base_essai, base_prete, faire_monde, jouer_tour, statuts_du_module, trace  # noqa: F401
from api.tests.mark.banc_a.fiches_des_runs import SANS_TRANSCRIPTION

pytestmark = pytest.mark.banc_a


def sans_fiches(run: int):
    return pytest.mark.xfail(strict=True, raises=TranscriptionManquante, reason=f"run {run} sans fiches (a-trancher) : {SANS_TRANSCRIPTION[run]}")


async def test_c11_1_2639_le_reglement_dit_d_emblee_n_est_pas_redemande(appel_de):
    a = await appel_de()
    await a.rejouer(2639, jusqu_au_tour=3)
    r = await jouer_tour(a, 2639, 4)  # « Impeccable » : accord sur la relecture ; « en carte » dit au tour 1
    manques = [x.get("manque") for x in r.get("resultats") or []]
    assert "paiement" not in manques, "« en carte » dit d'emblée, le règlement est redemandé" + trace(a)


@sans_fiches(2652)
async def test_c11_2_2652_le_rendu_sur_50_est_dit(appel_de):
    a = await appel_de()
    await a.rejouer(2652, jusqu_au_tour=6)
    dernier = a.journal[-1]["retour"]
    assert dernier["statut"] == "ENREGISTREE" and "rendu" in json.dumps(dernier, ensure_ascii=False).lower(), trace(a)


@sans_fiches(2652)
async def test_c11_3_2652_le_numero_est_relu_meme_quand_le_prenom_est_connu(appel_de):
    a = await appel_de()
    await a.rejouer(2652, jusqu_au_tour=6)
    dernier = a.journal[-1]["retour"]
    assert dernier["statut"] != "ENREGISTREE" or "numero_retenu_dit" in json.dumps(dernier), "enregistrée sans relire le numéro dicté" + trace(a)


@pytest.mark.parametrize("run,tour", [(2645, 1), pytest.param(2644, 2, marks=sans_fiches(2644))])
async def test_c12_hors_zone_propose_l_emporter(appel_de, run, tour):
    a = await appel_de()
    r = await a.rejouer(run, jusqu_au_tour=tour)
    assert "HORS_ZONE" in statuts_du_module(r), "précondition : hors zone" + trace(a)
    assert "emporter" in json.dumps(r, ensure_ascii=False).lower(), "hors zone : l'emporter n'est jamais proposé" + trace(a)


async def test_c13_1_2663_moitie_moitie_avec_les_noms_courants(appel_de):
    a = await appel_de()
    await a.rejouer(2663, jusqu_au_tour=1)
    r = await jouer_tour(a, 2663, 2)
    assert "HORS_CARTE" not in statuts_du_module(r) and a.quantite_de("Pizza moitié") == 1, "les moitiés « reine » et « 4 fromages » ne sont pas reconnues" + trace(a)


async def test_c13_2_2640_pas_de_sardines_jamais_la_regina(appel_de):
    a = await appel_de()
    r = await a.jouer_la_fiche("une pizza avec des sardines", {"_lire": {"sujet": "article", "article": "pizza avec des sardines"}})
    assert "regina" not in str(r).lower(), "des sardines : la Regina est proposée par ressemblance de lettres : " + str(r)[:300]


@pytest.mark.parametrize("ingredient,attendu", [("thon", "Neptune"), ("anchois", "Napoli"), ("poisson", "Neptune")])
async def test_c13_3_recherche_par_ingredient(appel_de, ingredient, attendu):
    a = await appel_de()
    r = await a.jouer_la_fiche(f"une pizza avec du {ingredient}", {"_lire": {"sujet": "article", "article": f"pizza avec du {ingredient}"}})
    assert attendu in str(r), f"« {ingredient} » : {attendu} n'est pas trouvée (pas de recherche par ingrédient) : " + str(r)[:300]


@sans_fiches(2670)
async def test_c13_4_2670_base_tomate_departage_les_homonymes(appel_de):
    a = await appel_de()
    await a.rejouer(2670, jusqu_au_tour=4)
    await jouer_tour(a, 2670, 5)
    assert a.quantite_de("4 Formaggi") == 2, "« base tomate » ne départage pas la pizza des pâtes" + trace(a)
