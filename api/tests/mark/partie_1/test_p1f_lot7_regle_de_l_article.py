"""[.mark] Lot 7b-A, ligne 81 : la règle d'un article (condition, justificatif, ce qui est servi avec) est notée au journal par son IDENTIFIANT (``regle:<id>``), jamais par son
texte : la lecture et l'ajout parlent de la même règle sans comparer des phrases. Les exemples de noms vivent ici, jamais dans le code."""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J
from api.services.commande.briques import formule as FO

from .aides_briques import brique

ARTICLE = {"nom": "Menu du petit", "categorie": "Menus", "condition": {"age_max": 10}, "servi_avec": ["des frites"]}


def test_chaque_regle_porte_son_identifiant_et_son_fait():
    """Lot 7b, reprise 1 (§ 2, le modèle parle) : le fait brut, jamais une phrase finie du code."""
    regles = FO.regle_a_dire_a_l_ajout(ARTICLE)["regle_a_dire"]
    assert [r["id"] for r in regles] == ["condition:Menu du petit", "rubrique:Menus"], regles
    assert all(r["fait"] and "texte" not in r for r in regles), regles


def test_un_article_sans_regle_n_en_rend_aucune():
    assert "regle_a_dire" not in FO.regle_a_dire_a_l_ajout({"nom": "Café", "categorie": "Boissons"})


def test_deux_articles_d_une_meme_rubrique_partagent_l_identifiant_de_la_rubrique():
    autre = {"nom": "Menu du grand", "categorie": "Menus", "servi_avec": ["des frites"]}
    a, b = (FO.regle_a_dire_a_l_ajout(x)["regle_a_dire"] for x in (ARTICLE, autre))
    assert a[-1]["id"] == b[-1]["id"] == "rubrique:Menus"


async def test_la_lecture_note_la_regle_de_la_rubrique_par_son_identifiant(essai_de):
    """Client « Les brochettes, c'est servi avec quoi ? » : la lecture note ``regle:<rubrique>`` ; l'ajout qui suit ne la redit pas."""
    e = await brique(essai_de, "FOR13")
    categorie = (await e.source.article("P-YAKITORI", "emporter"))["categorie"]
    await e.lecture(sujet="article", article="brochettes yakitori")
    assert J.une_fois(e.p, f"regle:rubrique:{categorie}") is False  # déjà noté par la lecture, sous son identifiant
