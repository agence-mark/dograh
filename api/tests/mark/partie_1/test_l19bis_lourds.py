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
