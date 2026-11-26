"""[.mark] Lot 8, PE-3 (Q8, point d'étape 7b-C du 26/11) : la lecture d'une liste de noms (rubrique, « sans », par ingrédient) porte une consigne « quelques noms, puis propose d'en dire plus ».

Décision d'Evan et Pierre : ``bilan-point-d-etape-7b-c.md:276`` (Q8 : une limite, en consigne au modèle). Le code ne dit rien : la liste complète reste dans les faits, la consigne est un
fait ``a_faire`` que ``lire`` passe au modèle ; aucun nombre n'y est écrit (le modèle choisit « quelques »).
Client « Qu'est-ce que vous avez comme pizzas ? » / avant : le modèle recevait toute la liste, sans consigne, et pouvait la lire en entier / après : « On a la Reine, la Margherita
et la Veggie, entre autres : je vous en dis plus ? ».
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from api.services.actions_communes import phrases_d_information as INFO
from api.services.commande.moteur import lecture
from api.services.restauration.carte_et_allergenes import voir_un_article as V
from api.tests.mark.partie_1.aides_signal import Carte, article_de_carte as article

REGLES = SimpleNamespace()
SEPT = [f"Pizza {c}" for c in "ABCDEFG"]
PANIER = {"mode": "emporter", "lignes": []}


def _carte(*, signalements: list[str] | None = None, ingredients: list[str] | None = None) -> Carte:
    return Carte([article(nom, signalements, ingredients) for nom in SEPT])


async def test_la_rubrique_lue_porte_la_consigne_et_garde_la_liste_complete():
    """Rubrique de la carte (``lire`` sujet carte, sans article) : tous les noms restent dans les faits, la consigne les accompagne."""
    async def carte_a_lire(_mode):
        return {"rubriques": [{"nom": "Pizzas", "articles": SEPT}]}
    r = await lecture.voir_la_carte(SimpleNamespace(carte_a_lire=carte_a_lire), dict(PANIER), REGLES)
    assert r.faits["rubriques"][0]["articles"] == SEPT, r
    assert r.faits.get("a_faire"), r


async def test_le_sans_d_une_rubrique_porte_la_consigne_et_garde_la_liste_complete():
    r = await V._chercher_ce_qui_est_sans(_carte(signalements=[]), {}, REGLES, "pizzas sans lait", None)
    assert r.faits["sans"] == SEPT, r
    assert r.faits.get("a_faire"), r


async def test_la_recherche_par_ingredient_porte_la_consigne_et_garde_la_liste_complete():
    r = await V.chercher_par_ingredient(_carte(ingredients=["thon"]), {}, REGLES, "thon", contient=True)
    assert r.faits["articles"] == SEPT, r
    assert r.faits.get("a_faire"), r


async def test_la_consigne_ne_porte_aucun_nombre_ecrit():
    """Aucun chiffre du métier en dur (refus 10) : ni chiffre, ni nombre dit en lettres dans la consigne."""
    r = await V.chercher_par_ingredient(_carte(ingredients=["thon"]), {}, REGLES, "thon", contient=True)
    consigne = str(r.faits["a_faire"])
    assert not re.search(r"\d|\b(un|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\b", consigne.casefold()), consigne


# ── voisins : ce qui ne liste aucun nom n'a pas bougé (refus 15) ────────────────────────────────────────────────────────────────


async def test_voisin_une_carte_sans_rubrique_n_a_pas_de_consigne():
    async def carte_a_lire(_mode):
        return {"rubriques": [], "du_moment": [{"article": "Plat du jour", "renseigne": False}]}
    r = await lecture.voir_la_carte(SimpleNamespace(carte_a_lire=carte_a_lire), dict(PANIER), REGLES)
    assert "a_faire" not in r.faits, r


async def test_voisin_rien_de_prouve_sans_la_chose_garde_sa_consigne_de_non_garanti():
    """« Sans lait » quand rien n'est prouvé : la consigne reste celle du module commun, inchangée."""
    carte = Carte([article("Reine", None), article("Maison", None)])
    r = await V._chercher_ce_qui_est_sans(carte, {}, REGLES, "pizzas sans lait", None)
    assert r.faits["a_faire"] == INFO.CONSIGNE_NON_GARANTI, r


async def test_voisin_la_recherche_par_ingredient_sans_article_n_a_pas_de_consigne():
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"])]), {}, REGLES, "thon", contient=True)
    assert r.faits["articles"] == [] and "a_faire" not in r.faits, r


async def test_voisin_un_seul_article_lu_n_a_pas_de_consigne():
    reine = {"nom": "Reine", "ingredients": ["jambon"], "signalements": [], "declinaisons": [], "groupes": [], "regimes": []}
    r = await V.voir_produit(Carte([article("Reine", [])], fiche=reine), {"mode": "sur_place", "lignes": []}, lecture.Reglages(), "Reine")
    assert "a_faire" not in r.faits, r
