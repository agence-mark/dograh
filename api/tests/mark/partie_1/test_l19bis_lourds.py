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
