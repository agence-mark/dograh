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
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.tests.mark.banc_a.commun import appel_de, faire_monde, base_essai, base_prete, jouer_reel, trace  # noqa: F401

pytestmark = pytest.mark.banc_a
NUIT_DU_18 = datetime(2026, 11, 18, 2, 40, tzinfo=ZoneInfo("Europe/Paris"))  # l'heure des essais de la nuit : Casa fermé, les heures voulues sont à venir


async def test_c2_1_2638_une_reine_dite_une_au_panier(appel_de):
    a = await appel_de()
    await a.rejouer(2638, jusqu_au_tour=1)
    assert a.quantite_de("Regina") == 1, "une reine dite, le panier en porte autre chose" + trace(a)


async def test_c2_1b_un_article_garde_puis_redit_avec_le_mode_n_est_pas_double(appel_de):
    a = await appel_de()
    # Le modèle dit l'article avant d'avoir le mode (gardé), puis le redonne avec le mode et l'adresse : même demande, une seule ligne.
    await a.jouer("ajouter_au_panier", {"articles": "une pizza reine normale", "mots": "je voudrais une reine normale en livraison au 12 rue de la République à Senlis"})
    a.greffier(type_de_commande="en livraison", adresse_livraison="12 rue de la République", commune="Senlis")
    await a.jouer("type_de_commande", {"articles": "une pizza reine normale", "mode": "en livraison", "mots": "je voudrais une reine normale en livraison au 12 rue de la République à Senlis"})
    assert a.quantite_de("Regina") == 1, "article redit = article rajouté" + trace(a)


async def test_c2_2_2644_deux_reines_au_changement_de_mode(appel_de):
    a = await appel_de()
    await a.rejouer(2644, jusqu_au_tour=3)
    assert a.quantite_de("Regina") == 2, "deux reines dites, le changement de mode les a multipliées" + trace(a)


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
    a.greffier(type_de_commande="en livraison", adresse_livraison="12 rue de la République", commune="Senlis")
    await a.jouer("type_de_commande", {"mode": "livraison", "adresse": "12 rue de la République, 60300 Senlis"})
    await a.jouer("ajouter_au_panier", {"articles": "une pizza reine normale", "mots": "une reine normale"})
    assert a.quantite_de("Regina") == 1, trace(a)


@pytest.mark.parametrize("faire_monde", [NUIT_DU_18], indirect=True)
async def test_a2_2668_l_heure_seule_ne_touche_pas_au_panier(appel_de):
    a = await appel_de()
    await a.rejouer(2668, jusqu_au_tour=2)
    await a.jouer("type_de_commande", {"heure": "vingt et une heures", "mode": "emporter", "mots": "plutôt 9 heures"})
    assert a.quantite_de("Margherita") == 3, trace(a)


async def test_a2_2653_retirer_puis_ajouter(appel_de):
    a = await appel_de()
    await a.rejouer(2653, jusqu_au_tour=7)
    await a.jouer("modifier", {"ligne": "Regina Normale", "quantite": 0, "mots": "enlevez la Regina normale"})
    await a.jouer("ajouter_au_panier", {"articles": "une Regina mega", "mots": "mettez une Regina mega"})
    assert a.quantite_de("Regina") == 1 and a.quantite_de("Regina Mega") == 1, trace(a)
