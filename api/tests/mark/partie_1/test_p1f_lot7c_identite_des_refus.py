"""[.mark] Lot 7b-C0, reprise R1 : deux refus DIFFÉRENTS n'ont jamais la même identité (``journal_du_dit.identite_du_refus``).

Avant la reprise, l'identité jetait les listes, les dictionnaires, les nombres à virgule et les vrai/faux : « enlevez le tiramisu et le coca » (aucun des deux au panier) rendait deux fois
le même refus, le second disparaissait des refus à dire, et un troisième refus d'un autre article partait tout de suite en issue puis en sortie. Collisions relevées par l'audit :
``articles.py`` (ligne introuvable par son nom, par son numéro, panier vide) et ``reglement.py`` (« Quel montant exactement ? » contre « Sur quel règlement le billet ? »).
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import journal_du_dit as J
from api.services.commande import porte
from api.services.commande.moteur import articles, reglement
from api.services.commande.resultat import Resultat


def _identite(r: Resultat) -> str:
    return J.identite_du_refus(r)


def test_l_identite_garde_les_vrai_faux_et_le_nom_de_chaque_fait_meme_quand_sa_valeur_est_une_liste():
    base = Resultat("INTROUVABLE", {}, "x")
    assert _identite(base) != _identite(Resultat("INTROUVABLE", {"lignes": ["a"]}, "x")), "un fait liste a son nom dans l'identité"
    assert _identite(Resultat("INTROUVABLE", {"lignes": ["a"]}, "x")) == _identite(Resultat("INTROUVABLE", {"lignes": ["b", "c"]}, "autre texte")), "mais pas ses valeurs"
    assert _identite(Resultat("INTROUVABLE", {"ouvert": True}, "x")) != _identite(Resultat("INTROUVABLE", {"ouvert": False}, "x")), "un vrai/faux est une valeur"
    assert _identite(Resultat("INTROUVABLE", {"prix": 1.5}, "x")) != _identite(Resultat("INTROUVABLE", {"prix": 2.5}, "x"))


async def test_deux_lignes_absentes_dites_dans_la_meme_fiche_sont_deux_refusants(essai_de):
    """Client « enlevez la sept et la huit » (le panier n'a qu'une ligne) : deux refus, deux refusants, les deux à dire."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    r = await e.tour("enlevez la sept et la huit", retirer_article=[7, 8])
    refus = r["faits"]["refus_de_la_fiche"]
    assert len(refus) == 2 and {x["faits"]["ligne"] for x in refus} == {7, 8}, refus


async def test_retirer_une_ligne_absente_puis_une_autre_se_dit_au_second_tour_sans_passer_a_l_issue(essai_de):
    """Client « enlevez la sept » puis « enlevez la huit » : deux faits différents, le second est dit comme un fait neuf (jamais l'issue)."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    premier = await e.tour("enlevez la sept", retirer_article=[7])
    second = await e.tour("enlevez la huit", retirer_article=[8])
    assert porte.A_FAIRE_DES_REFUS_A_DIRE in premier["a_faire"], premier["a_faire"]
    assert porte.A_FAIRE_DES_REFUS_A_DIRE in second["a_faire"] and J.A_FAIRE_ISSUE not in second["a_faire"], second["a_faire"]


def _panier(noms: list[str]) -> dict:
    return {"lignes": [{"n": i + 1, "nom": n, "choix": []} for i, n in enumerate(noms)]}


async def test_collision_articles_deux_noms_absents_ont_deux_identites():
    """``articles.py`` (ligne introuvable par son nom) : « le tiramisu » et « le coca » ne sont pas le même refus."""
    p = _panier(["Regina"])
    _, a = await articles._trouver_la_ligne(p, "tiramisu")
    _, b = await articles._trouver_la_ligne(p, "coca")
    assert a.statut == b.statut == "INTROUVABLE" and _identite(a) != _identite(b)


async def test_collision_articles_panier_vide_contre_nom_absent():
    """``articles.py`` : « il n'y a encore rien dans la commande » n'est pas « je ne trouve pas X dans la commande »."""
    _, vide = await articles._trouver_la_ligne(_panier([]), "tiramisu")
    _, absent = await articles._trouver_la_ligne(_panier(["Regina"]), "tiramisu")
    assert vide.statut == absent.statut == "INTROUVABLE" and _identite(vide) != _identite(absent)


async def test_collision_articles_numero_absent_contre_nom_absent_et_deux_numeros_entre_eux():
    p = _panier(["Regina"])
    _, sept = await articles._trouver_la_ligne(p, "7")
    _, huit = await articles._trouver_la_ligne(p, "8")
    _, nom = await articles._trouver_la_ligne(p, "tiramisu")
    assert len({_identite(sept), _identite(huit), _identite(nom)}) == 3


async def test_collision_reglement_montant_exact_contre_billet():
    """``reglement.py`` : « Quel montant exactement ? » et « Sur quel règlement le billet ? » sont deux refus de paiement différents."""
    async def reglages():
        return {"moyens_paiement": ["especes", "cheque"]}

    source = SimpleNamespace(reglages=reglages, libelles_des_moyens={})
    p = {"mode": "emporter"}
    _, montant = await reglement._le_reglement(source, p, 1000, {"moyen": "especes", "part": -1})
    _, billet = await reglement._le_reglement(source, p, 1000, {"moyen": "especes", "rendu_sur": 2000, "moyen_du_billet": "cheque"})
    assert montant.statut == billet.statut == "ARGUMENT_INVALIDE" and montant.manque == billet.manque == "paiement"
    assert _identite(montant) != _identite(billet)


async def test_deux_quantites_changees_sur_des_lignes_absentes_sont_deux_refusants(essai_de):
    """Le voisin de « retirer » (même boucle sur plusieurs lignes) : « mettez-en deux à la sept et trois à la huit » rend deux refus à dire."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    r = await e.tour("deux à la sept et trois à la huit", changer_quantite=[{"ligne": 7, "quantite": 2}, {"ligne": 8, "quantite": 3}])
    assert len(r["faits"]["refus_de_la_fiche"]) == 2, r["faits"].get("refus_de_la_fiche")
