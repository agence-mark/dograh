"""[.mark] Chantier Partie 1, lot 19 bis, étape C : les lourds de l'audit de Pierre (ce que l'appelant entend), un test vu rouge chacun.

Allergie (A2), vente par lot (C4), poids en lettres (C5), parole (P3, P5), numéro affiché (C7), partage du règlement (C2 bis), réservation (C6 bis), essai hors Labo (T5 bis).
Tests sur la vraie porte et le vrai moteur (``essai_de``).
"""

from __future__ import annotations

from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import brique, fait  # noqa: F401


# --------------------------------------------------------------------------- A2


async def test_article_ajoute_apres_l_allergie_reverifie(essai_de):
    """A2 : allergie au lait dite avec une salade au panier (faits donnés), puis « ajoutez une pizza reine » (lait validé) : les faits de CETTE ligne sont redonnés (``present``),
    l'enregistrement est bloqué ce tour-là (source : ``allergie_donnee`` ne comparait que le texte de l'allergie, jamais le panier) ; un article sans le lait ne rebloque rien."""
    carte = carte_de("briques/INF1")
    for p in carte["produits"]:
        if p["id"] == "P-REINE":
            p["allergenes"] = ["lait", "gluten"]
        if p["id"] == "P-SALADE":
            p["allergenes"] = ["gluten"]
    e = await essai_de("briques/INF1", carte=carte)
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salade", ajouter=[{"article": "salade verte", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "lait"
    premier = await e.tour("je suis allergique au lait", note_generale="allergique au lait")
    assert premier["faits"]["allergie"]["articles"] == [{"article": "Salade verte", "etat": "absent_de_la_fiche"}], premier
    suivant = await e.tour("et la salade ?", note_generale="allergique au lait")
    assert "allergie" not in (suivant.get("faits") or {})  # donnés une fois
    r = await e.tour("ajoutez une pizza reine", ajouter=[{"article": "pizza reine", "quantite": 1}], note_generale="allergique au lait")
    redonnes = (r.get("faits") or {}).get("allergie") or {}
    assert redonnes.get("articles") == [{"article": "Pizza reine", "etat": "present"}], r  # SES faits, pas ceux de la salade
    # le « oui » du même tour ne vaut pas : le tour suivant seulement
    assert not e.p.get("enregistree")


async def _jusqu_a_la_relecture(e) -> dict:
    """Mène la commande jusqu'à sa relecture posée (refuse ce que le code propose en route) et rend la question."""
    for _ in range(4):
        q = e.p.get("question") or {}
        if q.get("type") == "relecture":
            return q
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = e.p.get("question") or {}
    assert q.get("type") == "relecture", e.retours[-1]
    return q


# --------------------------------------------------------------------------- C4


async def test_correction_de_quantite_d_un_lot_en_pieces(essai_de):
    """C4 : un article vendu par lot de 6 (maki) : « douze maki » = 2 lots, DIT et MONTRÉ en pièces (état, relecture) ; « non, douze ! » (``changer_quantite``) reste 12 pièces = 2 lots, jamais 12 lots
    (source : ``modifier`` posait la quantité dite sans passer par QTE2) ; 24 pièces = 4 lots passe (source : le plafond de 20 était testé avant la conversion en lots, à la fiche et à l'ajout) ;
    hors multiple : refus avec les voisins."""
    from api.services.commande import etat_pour_le_modele as etat
    from api.services.commande import panier as P

    e = await brique(essai_de, "QTE2")
    await e.tour("douze maki", ajouter=[{"article": "maki", "quantite": 12}])
    n = e.p["lignes"][-1]["n"]
    assert e.p["lignes"][-1]["quantite"] == 2 and P.pieces(e.p["lignes"][-1]) == 12
    assert "12 × Maki" in (etat.texte(e.fiche_de_l_appel) or ""), etat.texte(e.fiche_de_l_appel)  # l'état dit des pièces, jamais « 2 × »
    await e.tour("non, douze !", changer_quantite=[{"ligne": n, "quantite": 12}])
    assert e.p["lignes"][-1]["quantite"] == 2, e.p["lignes"]  # avant : 12 lots (72 pièces, 72 €)
    await e.tour("vingt-quatre", changer_quantite=[{"ligne": n, "quantite": 24}])
    assert e.p["lignes"][-1]["quantite"] == 4, e.p["lignes"]  # avant : refusé, le plafond de 20 était testé sur les pièces
    r = await e.tour("sept", changer_quantite=[{"ligne": n, "quantite": 7}])
    assert "multiple_du_lot" in fait(r) and e.p["lignes"][-1]["quantite"] == 4, r
    q = await _jusqu_a_la_relecture(e)
    assert "vingt-quatre Maki" in q["texte"], q  # la relecture dit les pièces


# --------------------------------------------------------------------------- C5


def test_poids_en_lettres():
    """C5 : les cinq phrases de l'audit (avant : 500 g, 100,2 kg, 300 kg, 3 kg, 300 g), lues par le lecteur de nombres commun (``forme``) : « kilo + reste », « et demi », fractions, « N x M g » ;
    ce qui reste ambigu est refusé (``None``), jamais deviné."""
    from api.services.commande.briques.qte1 import lire_poids

    assert lire_poids("un kilo et demi") == 1500
    assert lire_poids("mille deux cents grammes") == 1200
    assert lire_poids("un kilo deux cents") == 1200
    assert lire_poids("trois quarts de kilo") == 750
    assert lire_poids("2 x 300 g") == 600
    assert lire_poids("deux kilos et demi") == 2500 and lire_poids("un quart de kilo") == 250 and lire_poids("quatre-vingt-dix grammes") == 90
    assert lire_poids("1 kg 2") is None and lire_poids("kilo") is None and lire_poids("un kilo des") is None


async def test_poids_au_dessus_du_maximum_redemande(essai_de):
    """C5 : un poids au-delà du maximum d'un article (cent kilos de houmous : 900 €) n'est jamais pris : refus ``poids_au_dessus_du_maximum`` avec le maximum, la question reste au modèle."""
    from api.services.commande import contrat

    e = await brique(essai_de, "QTE1")
    e.fiche_de_l_appel[contrat.CLE_DES_OBJETS] = (await e.source.charger_pour_l_appel())[1]  # la sous-case ``poids`` existe sur une carte qui vend au poids
    r = await e.tour("cent kilos de houmous", ajouter=[{"article": "houmous", "quantite": 1, "poids": "cent kilos"}])
    assert "poids_au_dessus_du_maximum" in fait(r) and not e.p["lignes"], r
    r = await e.tour("un kilo et demi de houmous", ajouter=[{"article": "houmous", "quantite": 1, "poids": "un kilo et demi"}])
    assert e.p["lignes"][-1]["poids_g"] == 1500, r
