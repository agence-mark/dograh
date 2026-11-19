"""[.mark] Banc A, famille C2 : des articles repassés par le modèle sont rajoutés par le code (bilan du 18/11 § 5, étude § 4 E6, aucune idempotence).

| Test | Run, tour | Ce que le client voulait |
|---|---|---|
| c2_1 | 2638 t1 | « une reine normale en livraison au 12 rue… » : UNE Regina (le code en a mis deux) |
| c2_1b | 2638 (mécanisme) | article gardé avant la zone, puis redit avec le mode : une seule ligne |
| c2_2 | 2644 t3 | « deux reines », mode changé en emporter : DEUX Regina (le code en a mis quatre) |
| c2_3 | 2668 t3-t4 | « plutôt 9 heures » : toujours TROIS Margherita (le code en a mis six puis neuf) |
| c2_4 | 2653 t8 | « enlevez la Regina normale et mettez une Regina mega à la place » : une Regina Mega, pas de Normale |
| c2_5 | 2653 t10 | même demande, autre tournure : une seule Regina, Mega |
| a2_* | idem | l'enchaînement qu'un bon modèle aurait fait : doit passer |

Lot 3 (D48) : rejoué en fiches (``fiches_des_runs.py``). Les runs qui repassent les articles dans ``type_de_commande`` (2644, 2668) ne s'écrivent
pas sans choix : la fiche n'a pas de case « article déjà dit », seulement ``ajouter`` (qui additionne, E3) ; ``xfail(strict=True)``, a-trancher.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.tests.mark.banc_a.commun import (  # noqa: F401
    TranscriptionManquante,
    appel_de,
    base_essai,
    base_prete,
    faire_monde,
    trace,
)
from api.tests.mark.banc_a.fiches_des_runs import SANS_TRANSCRIPTION

pytestmark = pytest.mark.banc_a


def sans_fiches(run: int):
    return pytest.mark.xfail(strict=True, raises=TranscriptionManquante, reason=f"run {run} sans fiches (a-trancher) : {SANS_TRANSCRIPTION[run]}")
NUIT_DU_18 = datetime(2026, 11, 18, 2, 40, tzinfo=ZoneInfo("Europe/Paris"))  # l'heure des essais de la nuit : Casa fermé, les heures voulues sont à venir


async def test_c2_1_2638_une_reine_dite_une_au_panier(appel_de):
    a = await appel_de()
    await a.rejouer(2638, jusqu_au_tour=1)
    assert a.quantite_de("Regina") == 1, "une reine dite, le panier en porte autre chose" + trace(a)


@pytest.mark.xfail(strict=True, raises=TranscriptionManquante, reason="le second appel repasse l'article dans type_de_commande : sans case « article déjà dit » (a-trancher)")
async def test_c2_1b_un_article_garde_puis_redit_avec_le_mode_n_est_pas_double(appel_de):
    a = await appel_de()
    # Le modèle dit l'article avant d'avoir le mode (gardé), puis le redonne avec le mode et l'adresse : même demande, une seule ligne.
    phrase = "je voudrais une reine normale en livraison au 12 rue de la République à Senlis"
    await a.jouer_la_fiche(phrase, {"ajouter": [{"article": "reine", "quantite": 1, "variante": "Normale"}]})
    raise TranscriptionManquante("type_de_commande {articles, mode} : l'article repassé n'a pas de case dans la fiche (seulement ajouter, qui additionne)")


@sans_fiches(2644)
async def test_c2_2_2644_deux_reines_au_changement_de_mode(appel_de):
    a = await appel_de()
    await a.rejouer(2644, jusqu_au_tour=3)
    assert a.quantite_de("Regina") == 2, "deux reines dites, le changement de mode les a multipliées" + trace(a)


@sans_fiches(2668)
@pytest.mark.parametrize("faire_monde", [NUIT_DU_18], indirect=True)
async def test_c2_3_2668_changer_l_heure_ne_change_pas_les_articles(appel_de):
    a = await appel_de()
    await a.rejouer(2668, jusqu_au_tour=4)
    assert a.quantite_de("Margherita") == 3, "3 Margherita dites, l'heure changée deux fois, le panier en porte autre chose" + trace(a)


async def test_c2_4_2653_remplacer_la_taille_par_enlever_et_remettre(appel_de):
    a = await appel_de()
    await a.rejouer(2653, jusqu_au_tour=8)
    assert a.quantite_de("Regina") == 1 and a.quantite_de("Regina Mega") == 1, "« enlevez la normale, mettez une mega à la place » : une seule Regina Mega attendue" + trace(a)


async def test_c2_5_2653_une_seule_regina_en_mega(appel_de):
    a = await appel_de()
    await a.rejouer(2653, jusqu_au_tour=10)
    assert a.quantite_de("Regina") == 1 and a.quantite_de("Regina Mega") == 1, "une seule Regina, en Mega, attendue" + trace(a)


# A2 : l'enchaînement qu'un bon modèle aurait fait


async def test_a2_2638_le_mode_et_l_adresse_puis_l_article(appel_de):
    a = await appel_de()
    await a.jouer_la_fiche("en livraison au 12 rue de la République, 60300 Senlis", {"mode_de_retrait": "livraison", "adresse": "12 rue de la République", "commune": "Senlis"})
    await a.jouer_la_fiche("une reine normale", {"ajouter": [{"article": "reine", "quantite": 1, "variante": "Normale"}]})
    assert a.quantite_de("Regina") == 1, trace(a)


@pytest.mark.parametrize("faire_monde", [NUIT_DU_18], indirect=True)
async def test_a2_2668_l_heure_seule_ne_touche_pas_au_panier(appel_de):
    a = await appel_de()
    await a.rejouer(2668, jusqu_au_tour=2)
    await a.jouer_la_fiche("plutôt 9 heures", {"heure": "vingt et une heures", "mode_de_retrait": "emporter"})
    assert a.quantite_de("Margherita") == 3, trace(a)


async def test_a2_2653_retirer_puis_ajouter(appel_de):
    a = await appel_de()
    await a.rejouer(2653, jusqu_au_tour=7)
    await a.jouer_la_fiche("enlevez la Regina normale et mettez une Regina mega", {"retirer_article": ["Regina Normale"], "ajouter": [{"article": "Regina", "quantite": 1, "variante": "Mega"}]})
    assert a.quantite_de("Regina") == 1 and a.quantite_de("Regina Mega") == 1, trace(a)
