"""[.mark] Lot 7b-B, reprise 1 (audit, § 2 : le modèle parle) : la règle d'une ligne limitée par un prix et les règles d'un article ajouté sont donnés au modèle en FAITS BRUTS, jamais en
phrases finies.

Client « Le tiramisu en dessert. » (formule complète) : avant, le retour portait la phrase « Dans la formule complète, le dessert se choisit parmi ceux à deux euros. » ;
après, il porte ``{formule, etape, prix_max}`` et le modèle écrit la phrase. Idem ``condition`` / ``justificatif`` / ``servi_avec`` d'un article.
"""

from __future__ import annotations

from api.tests.mark.partie_1.aides_briques import brique, fait


def _sans_phrase(valeur) -> bool:
    """Aucune phrase finie dans le fait : pas de chaîne qui finit par un point ou contient « C'est » / « Dans la »."""
    if isinstance(valeur, dict):
        return all(_sans_phrase(v) for v in valeur.values())
    if isinstance(valeur, list):
        return all(_sans_phrase(v) for v in valeur)
    return not (isinstance(valeur, str) and (valeur.rstrip().endswith(".") or valeur.startswith(("C'est", "Dans la"))))


async def test_la_regle_de_la_ligne_est_un_fait_brut(essai_de):
    e = await brique(essai_de, "FOR3")
    r = await e.tour("la formule complète avec un tiramisu", ajouter=[{"article": "formule complète", "quantite": 1, "composition": ["tacos", "tiramisu"]}])
    regle = r["faits"]["regle_de_la_ligne"]
    assert isinstance(regle, dict) and set(regle) == {"formule", "etape", "prix_max"}, regle
    assert regle["prix_max"] == 200 and regle["etape"].casefold() == "dessert" and "complète" in regle["formule"].casefold(), regle
    assert _sans_phrase(regle), regle


async def test_les_regles_de_l_article_sont_des_faits_bruts(essai_de):
    e13 = await brique(essai_de, "FOR13")
    r = await e13.tour("des brochettes yakitori", ajouter=[{"article": "brochettes yakitori", "quantite": 1}])
    assert r["faits"]["regles_a_dire"] == [{"servi_avec": ["1 soupe", "1 salade", "1 riz"]}], r["faits"]
    e9 = await brique(essai_de, "FOR9")
    r9 = await e9.tour("un menu étudiant", ajouter=[{"article": "menu étudiant", "quantite": 1, "composition": ["panini", "coca"]}])
    assert r9["faits"]["regles_a_dire"] == [{"justificatif": "présentation de la carte étudiante ou d'identité"}], fait(r9)
    e7 = await brique(essai_de, "FOR7")
    await e7.tour("sur place", mode_de_retrait="sur_place")
    r7 = await e7.tour("un menu enfant", ajouter=[{"article": "menu enfant", "quantite": 1, "composition": ["ailes de poulet", "jus de fruit"]}])
    assert r7["faits"]["regles_a_dire"] == [{"condition": {"age_max": 10}}], fait(r7)
    assert all(_sans_phrase(x) for x in (r["faits"]["regles_a_dire"], r9["faits"]["regles_a_dire"], r7["faits"]["regles_a_dire"]))
