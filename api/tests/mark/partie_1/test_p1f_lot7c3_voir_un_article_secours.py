"""[.mark] Lot 7b-C3, commit 8 : ``voir_un_article`` (composition, « sans », par ingrédient, article inconnu) et le choix de la porte de la réservation rendent le texte d'avant, au caractère près,
ET ce texte se refait des faits du retour (``carte_et_allergenes/textes_de_secours``, ``reservation/textes_de_secours``). Fait ajouté : ``mot`` (la chose évitée, au retour « sans »).
La source est un double qui ne connaît que sa carte."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import phrases_d_information as INFO
from api.services.reservation import textes_de_secours as TSR
from api.services.restauration.carte_et_allergenes import textes_de_secours as TS
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
    assert TS.article_sans_une_chose(r.faits) == "D'après la fiche, Margherita, Veggie et Marinara ne contiennent pas de lait.", r


async def test_sans_dit_un_seul_article_entre_autres_ce_qui_depend_du_choix_et_ce_qui_reste_inconnu():
    sept = [article(f"Pizza {c}", []) for c in "ABCDEFG"]
    r = await V._chercher_ce_qui_est_sans(Carte(sept), {}, REGLES, "pizzas sans œuf", None)
    assert r.suggestion == "", r
    assert TS.article_sans_une_chose(r.faits) == "D'après la fiche, Pizza A, Pizza B, Pizza C, Pizza D et Pizza E, entre autres, ne contiennent pas d'œuf.", r
    inconnu = [article("Reine", []), article("Maison", None)]
    r = await V._chercher_ce_qui_est_sans(Carte(inconnu), {}, REGLES, "pizzas sans gluten", None)
    assert r.suggestion == "", r
    assert TS.article_sans_une_chose(r.faits) == f"D'après la fiche, Reine ne contient pas de gluten. {INFO.POUR_LES_AUTRES_NON_GARANTI}", r
    selon = {**article("Burger", []), "obligatoires": [[{"nom": "pain", "signalements": [{"code": "gluten"}]}, {"nom": "salade", "signalements": []}]]}
    r = await V._chercher_ce_qui_est_sans(Carte([article("Reine", []), selon]), {}, REGLES, "sans gluten", None)
    assert r.suggestion == "", r
    assert TS.article_sans_une_chose(r.faits) == f"D'après la fiche, Reine ne contient pas de gluten. Pour Burger, {INFO.CA_DEPEND_DU_CHOIX_NON_GARANTI}", r


async def test_la_recherche_par_ingredient_dit_ceux_qui_en_ont_ceux_qui_n_en_ont_pas_et_le_doute():
    carte = Carte([article("Reine", None, ["jambon", "champignons"]), article("Marine", None, ["thon", "olives"]), article("Maison", None, None)])
    r = await V.chercher_par_ingredient(carte, {}, REGLES, "thon", contient=True)
    assert r.suggestion == "", r
    assert TS.articles_par_ingredient(r.faits) == f"D'après nos articles, Marine contient de thon. {INFO.POUR_LES_AUTRES_NON_CONFIRMABLE}", r and r.faits["articles"] == ["Marine"]
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"])]), {}, REGLES, "thon", contient=True)
    assert r.suggestion == "" and TS.articles_par_ingredient(r.faits) == "D'après nos articles, aucun ne contient de thon.", r
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"])]), {}, REGLES, "thon", contient=False)
    assert r.suggestion == "" and TS.articles_par_ingredient(r.faits) == "D'après nos articles, Reine ne contient pas de thon.", r
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"]), article("Marine", None, ["thon"])]), {}, REGLES, "thon", contient=False)
    assert r.suggestion == "" and TS.articles_par_ingredient(r.faits) == "D'après nos articles, Reine ne contient pas de thon.", r
    r = await V.chercher_par_ingredient(Carte([article("Maison", None, None)]), {}, REGLES, "thon", contient=True)
    assert r.suggestion == "" and TS.articles_par_ingredient(r.faits) == INFO.NON_CONFIRMABLE, r
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"]), article("Marine", None, ["thon"])]), {}, REGLES, "thon", contient=True)
    assert r.suggestion == "", r
    assert TS.articles_par_ingredient(r.faits) == "D'après nos articles, Marine contient de thon.", r


async def test_tous_en_contiennent_quand_la_chose_est_partout():
    r = await V.chercher_par_ingredient(Carte([article("Marine", None, ["thon"])]), {}, REGLES, "thon", contient=False)
    assert r.suggestion == "" and TS.articles_par_ingredient(r.faits) == "D'après nos articles, tous en contiennent.", r


async def test_composition_article_inconnu_et_article_a_preciser():
    reine = {"nom": "Reine", "ingredients": ["jambon", "champignons"], "signalements": [], "declinaisons": [], "groupes": [], "regimes": []}
    carte = Carte([article("Reine", [], ["jambon", "champignons"])], fiche=reine)
    r = await V.voir_produit(carte, PANIER, REGLES, "Reine")
    # C7 B5 (Evan 25/11 8 h 45) : plus de texte au retour ; les faits (l'article, ses ingrédients) refont celui d'avant
    assert r.suggestion == "" and TS.composition_d_un_article(r.faits) == "Dans Reine, il y a jambon et champignons.", r
    r = await V.voir_produit(carte, PANIER, REGLES, "")
    assert (r.statut, r.manque, r.suggestion) == ("ARGUMENT_INVALIDE", "produit", "") and TS.de_quel_article(r.faits) == "De quel article parlez-vous ?", r
    r = await V.voir_produit(Carte([article("Reine", [])], fiche=None), PANIER, REGLES, "Reine")
    assert (r.statut, r.suggestion) == ("INTROUVABLE", "") and TS.article_introuvable(r.faits) == "Je ne trouve pas cet article.", r


def test_l_equipe_le_confirme_et_le_choix_de_la_reservation():
    assert TS.l_equipe_le_confirme({}) == "L'équipe vous le confirme."
    assert TSR.laquelle({}) == "Laquelle ?"


def test_les_deux_petites_aides_de_la_feuille_font_comme_avant():
    assert [TS.sans_article(m) for m in ("le gluten", "la crème", "l'ail", "gluten")] == ["gluten", "crème", "ail", "gluten"]
    assert [TS.de(m) for m in ("gluten", "ail", "œufs", "huile", "yaourt", "hareng", "thon")] == ["de gluten", "d'ail", "d'œufs", "d'huile", "d'yaourt", "d'hareng", "de thon"]
