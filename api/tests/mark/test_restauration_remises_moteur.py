"""[.mark] Module Restauration, lot 7, étape 1 : le moteur commun de remises (``remises_moteur.py``), les familles au centime.

| Test | Ce qu'il prouve |
|---|---|
| pourcentage, montant | arrondi au centime, jamais au-delà du dû, périmètre respecté |
| lot offert | « 3 achetés, 1 offert » : le moins cher du groupe ; « 2 achetés dans A, 1 offert dans B » |
| rang réduit | un sur deux à moitié prix, le moins cher du groupe |
| prix fixe, écart de rang | l'écart seulement, jamais négatif |
| composition | un ensemble à prix d'ensemble, répété ; aucun gain : aucune remise |
| tous les N | la Nième commande du client reconnu seulement |
| article offert | part à son prix avec une remise du même montant |
| choix au mieux | exclusive contre cumulables, plafond au sous-total |
"""

from __future__ import annotations

from api.db.bases_clients.remises_moteur import Contexte, Unite, choisir_au_mieux, dans_le_perimetre, evaluer, part_en_centimes

PIZZA, BOISSON = "cat_pizza", "cat_boisson"


def U(ligne, code, prix, categorie=None, produit=None):
    return Unite(ligne, code, prix, produit, categorie)


def ctx(sous_total, **plus):
    return Contexte(mode="emporter", sous_total=sous_total, **plus)


def test_pourcentage_arrondi_au_centime_et_jamais_au_dela():
    assert part_en_centimes(1050, 10) == 105
    assert part_en_centimes(1005, 10) == 101       # 100,5 → la moitié vers le haut
    assert part_en_centimes(500, 100) == 500
    unites = [U(1, "a", 1050)]
    e = evaluer({"famille": "pourcentage", "effet": {"pourcentage": 10}}, unites, ctx(1050))
    assert e.montant == 105
    e = evaluer({"famille": "montant", "effet": {"montant": 5000}}, unites, ctx(1050))
    assert e.montant == 1050                        # jamais plus que le dû
    assert evaluer({"famille": "pourcentage", "effet": {"pourcentage": 150}}, unites, ctx(1050)) is None
    assert evaluer({"famille": "montant", "effet": {"montant": -5}}, unites, ctx(1050)) is None


def test_pourcentage_sur_un_perimetre_seulement():
    unites = [U(1, "p", 1000, PIZZA), U(2, "b", 300, BOISSON)]
    e = evaluer({"famille": "pourcentage", "perimetre": {"categories": [PIZZA]}, "effet": {"pourcentage": 20}}, unites, ctx(1300))
    assert e.montant == 200 and e.unites == (1,)
    assert evaluer({"famille": "pourcentage", "perimetre": {"modes": ["livraison"]}, "effet": {"pourcentage": 20}}, unites, ctx(1300)) is None


def test_seuil_exige_son_minimum():
    unites = [U(1, "p", 1000)]
    regle = {"famille": "pourcentage", "exige_un_minimum": True, "declencheur": {"minimum": 2000}, "effet": {"pourcentage": 10}}
    assert evaluer(regle, unites, ctx(1000)) is None
    assert evaluer(regle, unites + [U(2, "p", 1000)], ctx(2000)).montant == 200
    assert evaluer({**regle, "declencheur": {}}, unites, ctx(1000)) is None   # un seuil sans minimum ne s'applique à rien


def test_lot_offert_meme_perimetre_le_moins_cher_du_groupe():
    unites = [U(1, "a", 1200), U(2, "b", 1000), U(3, "c", 900)]
    e = evaluer({"famille": "lot_offert", "declencheur": {"achetes": 2}, "effet": {"offerts": 1}}, unites, ctx(3100))
    assert e.montant == 900 and e.unites == (3,)
    assert evaluer({"famille": "lot_offert", "declencheur": {"achetes": 2}, "effet": {"offerts": 1}}, unites[:2], ctx(2200)) is None


def test_lot_offert_deux_pizzas_une_boisson_dite_une_fois():
    unites = [U(1, "p", 1100, PIZZA), U(2, "p", 1000, PIZZA), U(3, "b", 300, BOISSON), U(4, "b", 250, BOISSON)]
    regle = {"famille": "lot_offert", "perimetre": {"categories": [PIZZA]}, "declencheur": {"achetes": 2},
             "effet": {"offerts": 1, "perimetre_offert": {"categories": [BOISSON]}}}
    e = evaluer(regle, unites, ctx(2650))
    assert e.montant == 250                         # la moins chère des boissons : une seule fois pour deux pizzas
    assert evaluer(regle, unites[:3], ctx(2400)).montant == 300
    assert evaluer(regle, unites[:1] + unites[2:], ctx(1650)) is None   # une seule pizza


def test_lot_offert_plafond():
    unites = [U(i, "a", 500) for i in range(1, 7)]
    regle = {"famille": "lot_offert", "declencheur": {"achetes": 1}, "effet": {"offerts": 1}, "limite": {"max_par_achat": 1}}
    assert evaluer(regle, unites, ctx(3000)).montant == 500
    assert evaluer({**regle, "limite": None}, unites, ctx(3000)).montant == 1500


def test_deuxieme_a_moitie_prix():
    unites = [U(1, "a", 1000), U(2, "a", 900), U(3, "a", 800)]
    e = evaluer({"famille": "rang_reduit", "declencheur": {"rang": 2}, "effet": {"pourcentage": 50}}, unites, ctx(2700))
    assert e.montant == 450 and e.unites == (2,)
    quatre = unites + [U(4, "a", 700)]
    assert evaluer({"famille": "rang_reduit", "declencheur": {"rang": 2}, "effet": {"pourcentage": 50}}, quatre, ctx(3400)).montant == 450 + 350
    assert evaluer({"famille": "rang_reduit", "declencheur": {"rang": 2}, "effet": {"pourcentage": 50}}, unites[:1], ctx(1000)) is None


def test_prix_fixe_ecart_seulement():
    unites = [U(1, "p", 1200, produit="du_jour"), U(2, "x", 900)]
    e = evaluer({"famille": "prix_fixe", "perimetre": {"produits": ["du_jour"]}, "effet": {"prix": 1000}}, unites, ctx(2100))
    assert e.montant == 200
    assert evaluer({"famille": "prix_fixe", "perimetre": {"produits": ["du_jour"]}, "effet": {"prix": 1500}}, unites, ctx(2100)) is None


def test_ecart_de_rang_taille_superieure():
    unites = [U(1, "grande", 1400), U(2, "grande", 1400)]
    c = ctx(2800, prix_par_code={"moyenne": 1100})
    regle = {"famille": "ecart_de_rang", "perimetre": {"codes": ["grande"]}, "effet": {"prix_de": "moyenne"}}
    assert evaluer(regle, unites, c).montant == 600
    assert evaluer({**regle, "limite": {"max_par_achat": 1}}, unites, c).montant == 300
    assert evaluer({**regle, "effet": {"prix_de": "inconnue"}}, unites, c) is None


def test_composition_menu_et_offre_famille():
    unites = [U(1, "burger", 1000, "b"), U(2, "frites", 350, "f"), U(3, "coca", 300, "d")]
    menu = {"famille": "composition", "effet": {"prix": 1400},
            "declencheur": {"composition": [{"perimetre": {"categories": ["b"]}}, {"perimetre": {"categories": ["f"]}}, {"perimetre": {"categories": ["d"]}}]}}
    assert evaluer(menu, unites, ctx(1650)).montant == 250
    assert evaluer(menu, unites[:2], ctx(1350)) is None                      # il manque la boisson
    assert evaluer({**menu, "effet": {"prix": 1700}}, unites, ctx(1650)) is None   # aucun gain : pas de remise
    famille = {"famille": "composition", "declencheur": {"composition": [{"perimetre": {"categories": ["p"]}, "quantite": 4}]}, "effet": {"prix": 3600}}
    quatre = [U(i, "p", 1000, "p") for i in range(1, 5)]
    assert evaluer(famille, quatre, ctx(4000)).montant == 400
    assert evaluer(famille, quatre + [U(5, "p", 1000, "p")], ctx(5000)).montant == 400     # le cinquième reste au prix
    huit = [U(i, "p", 1000, "p") for i in range(1, 9)]
    assert evaluer(famille, huit, ctx(8000)).montant == 800


def test_fidelite_a_la_nieme_commande_du_client_reconnu():
    unites = [U(1, "a", 1000)]
    regle = {"famille": "tous_les", "declencheur": {"tous_les": 10}, "effet": {"pourcentage": 50}}
    assert evaluer(regle, unites, ctx(1000, rang_du_client=10)).montant == 500
    assert evaluer(regle, unites, ctx(1000, rang_du_client=9)) is None
    assert evaluer(regle, unites, ctx(1000, rang_du_client=None)) is None   # client inconnu
    offert = {**regle, "effet": {"offert": {"codes": ["cafe"]}}}
    e = evaluer(offert, unites, ctx(1000, rang_du_client=20, prix_par_code={"cafe": 200}))
    assert e.montant == 200 and e.ajout == (("cafe", 1),)


def test_article_offert_sur_seuil():
    unites = [U(1, "p", 2500)]
    regle = {"famille": "pourcentage", "exige_un_minimum": True, "declencheur": {"minimum": 2000}, "effet": {"offert": {"codes": ["dessert"]}}}
    e = evaluer(regle, unites, ctx(2500, prix_par_code={"dessert": 400}))
    assert (e.montant, e.ajout) == (400, (("dessert", 1),))
    assert evaluer(regle, unites, ctx(2500)) is None                         # l'article offert n'est pas à la carte


def test_choix_au_mieux():
    c = [
        {"ref": "a", "cumul": "exclusive", "montant": 300}, {"ref": "b", "cumul": "exclusive", "montant": 500},
        {"ref": "c", "cumul": "cumulable", "montant": 150}, {"ref": "d", "cumul": "cumulable", "montant": 100}, {"ref": "e", "cumul": "exclusive", "montant": None},
    ]
    assert [r["ref"] for r in choisir_au_mieux(c, 5000)] == ["b"]
    assert [r["ref"] for r in choisir_au_mieux(c[:1] + c[2:4], 5000)] == ["a"]
    plafonnees = choisir_au_mieux([{"ref": "c", "cumul": "cumulable", "montant": 150}, {"ref": "d", "cumul": "cumulable", "montant": 100}], 200)
    assert [(r["ref"], r["montant"]) for r in plafonnees] == [("c", 150), ("d", 50)]
    assert choisir_au_mieux([], 100) == []


def test_perimetre_vide_est_tout():
    assert dans_le_perimetre(U(1, "a", 1), None) and dans_le_perimetre(U(1, "a", 1), {})
    assert not dans_le_perimetre(U(1, "a", 1, "c"), {"categories": ["autre"]})
