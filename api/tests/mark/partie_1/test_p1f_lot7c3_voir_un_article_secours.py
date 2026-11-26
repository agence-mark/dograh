"""[.mark] Lot 7b-C3, commit 8 : ``voir_un_article`` (composition, « sans », par ingrédient, article inconnu) et le choix de la porte de la réservation ne rendent plus de texte ;
C7 B9 : les catalogues supprimés, ce que disait le texte d'avant est vérifié dans les faits du retour. Fait ajouté : ``mot`` (la chose évitée, au retour « sans »).
La source est un double qui ne connaît que sa carte."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import phrases_d_information as INFO
from api.services.restauration.carte_et_allergenes import voir_un_article as V
from api.tests.mark.partie_1.aides_signal import Carte, article_de_carte as article

NG = INFO.NON_GARANTI
REGLES = SimpleNamespace()
PANIER = {"mode": "sur_place", "lignes": []}


async def test_la_recherche_sans_une_chose_dit_les_articles_et_la_chose_evitee():
    carte = Carte([article("Reine", ["lait"]), article("Margherita", ["gluten"]), article("Veggie", []), article("Marinara", [])])
    r = await V._chercher_ce_qui_est_sans(carte, {}, REGLES, "pizzas sans lait", None)
    assert r.faits["mot"] == "lait" and r.faits["sans"] == ["Margherita", "Veggie", "Marinara"], r
    assert r.suggestion == "", r
    assert {k: r.faits.get(k) for k in ('sans', 'selon_le_choix', 'mot', 'inconnus')} == {'sans': ['Margherita', 'Veggie', 'Marinara'], 'selon_le_choix': None, 'mot': 'lait', 'inconnus': 0}, r


async def test_sans_dit_un_seul_article_entre_autres_ce_qui_depend_du_choix_et_ce_qui_reste_inconnu():
    sept = [article(f"Pizza {c}", []) for c in "ABCDEFG"]
    r = await V._chercher_ce_qui_est_sans(Carte(sept), {}, REGLES, "pizzas sans œuf", None)
    assert r.suggestion == "", r
    assert {k: r.faits.get(k) for k in ('sans', 'selon_le_choix', 'mot', 'inconnus')} == {'sans': ['Pizza A', 'Pizza B', 'Pizza C', 'Pizza D', 'Pizza E', 'Pizza F', 'Pizza G'], 'selon_le_choix': None, 'mot': 'œuf', 'inconnus': 0}, r
    inconnu = [article("Reine", []), article("Maison", None)]
    r = await V._chercher_ce_qui_est_sans(Carte(inconnu), {}, REGLES, "pizzas sans gluten", None)
    assert r.suggestion == "", r
    assert {k: r.faits.get(k) for k in ('sans', 'selon_le_choix', 'mot', 'inconnus')} == {'sans': ['Reine'], 'selon_le_choix': None, 'mot': 'gluten', 'inconnus': 1}, r
    selon = {**article("Burger", []), "obligatoires": [[{"nom": "pain", "signalements": [{"code": "gluten"}]}, {"nom": "salade", "signalements": []}]]}
    r = await V._chercher_ce_qui_est_sans(Carte([article("Reine", []), selon]), {}, REGLES, "sans gluten", None)
    assert r.suggestion == "", r
    assert {k: r.faits.get(k) for k in ('sans', 'selon_le_choix', 'mot', 'inconnus')} == {'sans': ['Reine'], 'selon_le_choix': ['Burger'], 'mot': 'gluten', 'inconnus': 0}, r


async def test_la_recherche_par_ingredient_dit_ceux_qui_en_ont_ceux_qui_n_en_ont_pas_et_le_doute():
    carte = Carte([article("Reine", None, ["jambon", "champignons"]), article("Marine", None, ["thon", "olives"]), article("Maison", None, None)])
    r = await V.chercher_par_ingredient(carte, {}, REGLES, "thon", contient=True)
    assert r.suggestion == "", r
    assert {k: r.faits.get(k) for k in ('articles', 'chose', 'contient', 'inconnus')} == {'articles': ['Marine'], 'chose': 'thon', 'contient': True, 'inconnus': 1}, r and r.faits["articles"] == ["Marine"]
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"])]), {}, REGLES, "thon", contient=True)
    assert r.suggestion == "" and {k: r.faits.get(k) for k in ('articles', 'chose', 'inconnus', 'contient')} == {'articles': [], 'chose': 'thon', 'inconnus': 0, 'contient': True}, r
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"])]), {}, REGLES, "thon", contient=False)
    assert r.suggestion == "" and {k: r.faits.get(k) for k in ('articles', 'chose', 'contient', 'inconnus')} == {'articles': ['Reine'], 'chose': 'thon', 'contient': False, 'inconnus': 0}, r
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"]), article("Marine", None, ["thon"])]), {}, REGLES, "thon", contient=False)
    assert r.suggestion == "" and {k: r.faits.get(k) for k in ('articles', 'chose', 'contient', 'inconnus')} == {'articles': ['Reine'], 'chose': 'thon', 'contient': False, 'inconnus': 0}, r
    r = await V.chercher_par_ingredient(Carte([article("Maison", None, None)]), {}, REGLES, "thon", contient=True)
    assert r.suggestion == "" and {k: r.faits.get(k) for k in ('articles', 'chose', 'inconnus')} == {'articles': [], 'chose': 'thon', 'inconnus': 1}, r
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"]), article("Marine", None, ["thon"])]), {}, REGLES, "thon", contient=True)
    assert r.suggestion == "", r
    assert {k: r.faits.get(k) for k in ('articles', 'chose', 'contient', 'inconnus')} == {'articles': ['Marine'], 'chose': 'thon', 'contient': True, 'inconnus': 0}, r


async def test_tous_en_contiennent_quand_la_chose_est_partout():
    r = await V.chercher_par_ingredient(Carte([article("Marine", None, ["thon"])]), {}, REGLES, "thon", contient=False)
    assert r.suggestion == "" and {k: r.faits.get(k) for k in ('articles', 'chose', 'inconnus', 'contient')} == {'articles': [], 'chose': 'thon', 'inconnus': 0, 'contient': False}, r


async def test_composition_article_inconnu_et_article_a_preciser():
    reine = {"nom": "Reine", "ingredients": ["jambon", "champignons"], "signalements": [], "declinaisons": [], "groupes": [], "regimes": []}
    carte = Carte([article("Reine", [], ["jambon", "champignons"])], fiche=reine)
    r = await V.voir_produit(carte, PANIER, REGLES, "Reine")
    # C7 B5 (Evan 25/11 8 h 45) : plus de texte au retour ; les faits (l'article, ses ingrédients) refont celui d'avant
    assert r.suggestion == "" and {k: r.faits.get(k) for k in ('article', 'ingredients')} == {'article': 'Reine', 'ingredients': ['jambon', 'champignons']}, r
    r = await V.voir_produit(carte, PANIER, REGLES, "")
    assert (r.statut, r.manque, r.suggestion) == ("ARGUMENT_INVALIDE", "produit", "") and dict(r.faits) == {}, r
    r = await V.voir_produit(Carte([article("Reine", [])], fiche=None), PANIER, REGLES, "Reine")
    assert (r.statut, r.suggestion) == ("INTROUVABLE", ""), r  # « je ne trouve pas cet article » : le statut


def test_la_petite_aide_du_mot_fait_comme_avant():
    """C7 B9 : ``sans_article`` (qui fabrique le fait ``mot``) vit dans ``mots_dits`` ; ``de`` ne servait qu'au catalogue, parti avec lui."""
    from api.services.mots_dits import sans_article

    assert [sans_article(m) for m in ("le gluten", "la crème", "l'ail", "gluten")] == ["gluten", "crème", "ail", "gluten"]
