"""[.mark] Lot 7b-C3, commit 8 : ``voir_un_article`` (composition, « sans », par ingrédient, article inconnu) et le choix de la porte de la réservation rendent le texte d'avant, au caractère près,
ET ce texte se refait des faits du retour (``carte_et_allergenes/textes_de_secours``, ``reservation/textes_de_secours``). Fait ajouté : ``mot`` (la chose évitée, au retour « sans »).
La source est un double qui ne connaît que sa carte."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from api.services.actions_communes import phrases_d_information as INFO
from api.services.reservation import textes_de_secours as TSR
from api.services.restauration.carte_et_allergenes import textes_de_secours as TS
from api.services.restauration.carte_et_allergenes import voir_un_article as V

NG = INFO.NON_GARANTI
LIBELLES = {"gluten": "le gluten", "lait": "le lait", "oeufs": "l'œuf"}
REGLES = SimpleNamespace()
PANIER = {"mode": "sur_place", "lignes": []}


class Carte:
    """Une carte d'essai : ses articles (``nom``, ``categorie``, ``signalements``, ``ingredients``, ``obligatoires``), sans réseau."""

    modes = ["sur_place"]

    def __init__(self, articles: list[dict[str, Any]], fiche: dict[str, Any] | None = None):
        self.articles, self._fiche = articles, fiche

    async def catalogue(self, mode):
        return {"articles": self.articles, "libelles": LIBELLES}

    def signalement_dit(self, texte):
        return next((c for c, libelle in LIBELLES.items() if texte.strip() in (c, libelle, libelle.split(" ", 1)[-1], libelle.lstrip("l'"))), None)

    def signalements_dits(self, texte):
        code = self.signalement_dit(texte)
        return ([code] if code else []), code is None

    def codes_d_un_nom(self, nom):
        return []

    async def chercher(self, texte):
        trouve = next((a for a in self.articles if a["nom"].casefold() == texte.casefold()), None)
        return SimpleNamespace(statut="RETENU" if trouve else "INTROUVABLE", faits={"retenu": trouve["nom"]} if trouve else {}, suggestion="", manque=None)

    async def article(self, nom, mode):
        return self._fiche


def article(nom: str, signalements: list[str] | None, ingredients: list[str] | None = None, categorie: str = "pizzas") -> dict[str, Any]:
    return {"nom": nom, "categorie": categorie, "signalements": None if signalements is None else [{"code": c} for c in signalements], "ingredients": ingredients, "obligatoires": []}


async def test_la_recherche_sans_une_chose_dit_les_articles_et_la_chose_evitee():
    carte = Carte([article("Reine", ["lait"]), article("Margherita", ["gluten"]), article("Veggie", []), article("Marinara", [])])
    r = await V._chercher_ce_qui_est_sans(carte, {}, REGLES, "pizzas sans lait", None)
    assert r.faits["mot"] == "lait" and r.faits["sans"] == ["Margherita", "Veggie", "Marinara"], r
    assert r.suggestion == "D'après la fiche, Margherita, Veggie et Marinara ne contiennent pas de lait.", r
    assert r.suggestion == TS.article_sans_une_chose(r.faits)


async def test_sans_dit_un_seul_article_entre_autres_ce_qui_depend_du_choix_et_ce_qui_reste_inconnu():
    sept = [article(f"Pizza {c}", []) for c in "ABCDEFG"]
    r = await V._chercher_ce_qui_est_sans(Carte(sept), {}, REGLES, "pizzas sans œuf", None)
    assert r.suggestion == "D'après la fiche, Pizza A, Pizza B, Pizza C, Pizza D et Pizza E, entre autres, ne contiennent pas d'œuf.", r
    assert r.suggestion == TS.article_sans_une_chose(r.faits)
    inconnu = [article("Reine", []), article("Maison", None)]
    r = await V._chercher_ce_qui_est_sans(Carte(inconnu), {}, REGLES, "pizzas sans gluten", None)
    assert r.suggestion == f"D'après la fiche, Reine ne contient pas de gluten. {INFO.POUR_LES_AUTRES_NON_GARANTI}", r
    assert r.suggestion == TS.article_sans_une_chose(r.faits)
    selon = {**article("Burger", []), "obligatoires": [[{"nom": "pain", "signalements": [{"code": "gluten"}]}, {"nom": "salade", "signalements": []}]]}
    r = await V._chercher_ce_qui_est_sans(Carte([article("Reine", []), selon]), {}, REGLES, "sans gluten", None)
    assert r.suggestion == f"D'après la fiche, Reine ne contient pas de gluten. Pour Burger, {INFO.CA_DEPEND_DU_CHOIX_NON_GARANTI}", r
    assert r.suggestion == TS.article_sans_une_chose(r.faits)


async def test_la_recherche_par_ingredient_dit_ceux_qui_en_ont_ceux_qui_n_en_ont_pas_et_le_doute():
    carte = Carte([article("Reine", None, ["jambon", "champignons"]), article("Marine", None, ["thon", "olives"]), article("Maison", None, None)])
    r = await V.chercher_par_ingredient(carte, {}, REGLES, "thon", contient=True)
    assert r.suggestion == f"D'après nos articles, Marine contient de thon. {INFO.POUR_LES_AUTRES_NON_CONFIRMABLE}", r
    assert r.suggestion == TS.articles_par_ingredient(r.faits) and r.faits["articles"] == ["Marine"]
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"])]), {}, REGLES, "thon", contient=True)
    assert r.suggestion == "D'après nos articles, aucun ne contient de thon." and r.suggestion == TS.articles_par_ingredient(r.faits), r
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"])]), {}, REGLES, "thon", contient=False)
    assert r.suggestion == "D'après nos articles, Reine ne contient pas de thon." and r.suggestion == TS.articles_par_ingredient(r.faits), r
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"]), article("Marine", None, ["thon"])]), {}, REGLES, "thon", contient=False)
    assert r.suggestion == "D'après nos articles, Reine ne contient pas de thon." and r.suggestion == TS.articles_par_ingredient(r.faits), r
    r = await V.chercher_par_ingredient(Carte([article("Maison", None, None)]), {}, REGLES, "thon", contient=True)
    assert r.suggestion == INFO.NON_CONFIRMABLE and r.suggestion == TS.articles_par_ingredient(r.faits), r
    r = await V.chercher_par_ingredient(Carte([article("Reine", None, ["jambon"]), article("Marine", None, ["thon"])]), {}, REGLES, "thon", contient=True)
    assert r.suggestion == "D'après nos articles, Marine contient de thon.", r
    assert r.suggestion == TS.articles_par_ingredient(r.faits)


async def test_tous_en_contiennent_quand_la_chose_est_partout():
    r = await V.chercher_par_ingredient(Carte([article("Marine", None, ["thon"])]), {}, REGLES, "thon", contient=False)
    assert r.suggestion == "D'après nos articles, tous en contiennent." and r.suggestion == TS.articles_par_ingredient(r.faits), r


async def test_composition_article_inconnu_et_article_a_preciser():
    reine = {"nom": "Reine", "ingredients": ["jambon", "champignons"], "signalements": [], "declinaisons": [], "groupes": [], "regimes": []}
    carte = Carte([article("Reine", [], ["jambon", "champignons"])], fiche=reine)
    r = await V.voir_produit(carte, PANIER, REGLES, "Reine")
    assert r.suggestion == "Dans Reine, il y a jambon et champignons." and r.suggestion == TS.composition_d_un_article(r.faits), r
    r = await V.voir_produit(carte, PANIER, REGLES, "")
    assert (r.statut, r.manque, r.suggestion) == ("ARGUMENT_INVALIDE", "produit", "De quel article parlez-vous ?") and r.suggestion == TS.de_quel_article(r.faits), r
    r = await V.voir_produit(Carte([article("Reine", [])], fiche=None), PANIER, REGLES, "Reine")
    assert (r.statut, r.suggestion) == ("INTROUVABLE", "Je ne trouve pas cet article.") and r.suggestion == TS.article_introuvable(r.faits), r


def test_l_equipe_le_confirme_et_le_choix_de_la_reservation():
    assert TS.l_equipe_le_confirme({}) == "L'équipe vous le confirme."
    assert TSR.laquelle({}) == "Laquelle ?"


def test_les_deux_petites_aides_de_la_feuille_font_comme_avant():
    assert [TS.sans_article(m) for m in ("le gluten", "la crème", "l'ail", "gluten")] == ["gluten", "crème", "ail", "gluten"]
    assert [TS.de(m) for m in ("gluten", "ail", "œufs", "huile", "yaourt", "hareng", "thon")] == ["de gluten", "d'ail", "d'œufs", "d'huile", "d'yaourt", "d'hareng", "de thon"]
