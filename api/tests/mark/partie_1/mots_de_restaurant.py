"""[.mark] Chantier Partie 1, lot 8 : les mots de restaurant qu'AUCUN code générique ne doit contenir (E17, M1 du registre des modules).

Relevé des constantes retirées du code au lot 8 (``services/restauration/mots_du_metier.py``, ``db/bases_clients/restauration_en_plus.py``) : le genre et
le nom commun d'un produit viennent de sa surcouche, le rôle d'une catégorie de sa fiche, jamais d'une liste écrite dans le code. Ce relevé ne sert
qu'à vérifier qu'ils n'y reviennent pas (``test_l08_briques.py::test_aucun_mot_de_restaurant_dans_le_code``) et aux gardes des noms d'outils.
"""

COMMUNS: dict[str, str] = {
    "pizza": "f", "salade": "f", "bruschetta": "f", "pate": "f", "pates": "f", "boisson": "f", "biere": "f", "eau": "f", "limonade": "f", "glace": "f",
    "tarte": "f", "mousse": "f", "creme": "f", "entree": "f", "assiette": "f", "formule": "f", "soupe": "f", "frite": "f", "frites": "f", "crepe": "f",
    "tiramisu": "m", "burger": "m", "cheeseburger": "m", "dessert": "m", "jus": "m", "vin": "m", "cafe": "m", "the": "m", "flan": "m", "gateau": "m",
    "fondant": "m", "menu": "m", "panini": "m", "calamars": "m", "sandwich": "m", "cocktail": "m", "soda": "m", "verre": "m",
}
PROPRES: dict[str, str] = {"cristaline": "f", "felicite": "f", "orangina": "m", "perrier": "m"}
CATEGORIES_DE_PLATS: dict[str, str] = {"pizza": "f", "pate": "f", "salade": "f", "bruschetta": "f", "entree": "f", "burger": "m"}
# La vente en plus lisait le nom de la catégorie : « boisson », « dessert », et « alcool » jamais proposé.
FAMILLES_DE_LA_VENTE_EN_PLUS = ("boisson", "dessert", "alcool")
