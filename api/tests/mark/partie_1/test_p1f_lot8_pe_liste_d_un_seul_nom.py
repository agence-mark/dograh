"""[.mark] Lot 8, PE-3, reprise R2 (Q8) : la consigne « quelques noms, puis propose d'en dire plus » n'est posée que si la liste a PLUS D'UN nom.

Règle de structure, aucun chiffre du métier : avec un seul nom, il n'y a rien à « dire en plus ».
Client « Des pizzas sans gluten ? » (une seule pizza sûre) / avant : « On a la Veggie : je vous en dis plus ? » / après : « Oui, la Veggie. ».
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.commande.moteur import lecture
from api.services.restauration.carte_et_allergenes import voir_un_article as V
from api.tests.mark.partie_1.aides_signal import Carte, article_de_carte as article

REGLES = SimpleNamespace()
PANIER = {"mode": "emporter", "lignes": []}


async def test_un_sans_avec_un_seul_article_sur_n_a_pas_de_consigne():
    r = await V._chercher_ce_qui_est_sans(Carte([article("Veggie", [])]), {}, REGLES, "pizzas sans lait", None)
    assert r.faits["sans"] == ["Veggie"] and "a_faire" not in r.faits, r


async def test_une_recherche_par_ingredient_qui_trouve_un_seul_article_n_a_pas_de_consigne():
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["thon"]), article("Veggie", None, ["poivron"])]), {}, REGLES, "thon", contient=True)
    assert r.faits["articles"] == ["Reine"] and "a_faire" not in r.faits, r


async def test_une_rubrique_d_un_seul_article_n_a_pas_de_consigne():
    async def carte_a_lire(_mode):
        return {"rubriques": [{"nom": "Desserts", "articles": ["Tiramisu"]}]}
    r = await lecture.voir_la_carte(SimpleNamespace(carte_a_lire=carte_a_lire), dict(PANIER), REGLES)
    assert r.faits["rubriques"][0]["articles"] == ["Tiramisu"] and "a_faire" not in r.faits, r
