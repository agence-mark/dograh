"""[.mark] Brique PRX7 : la consigne, l'emballage, les couverts (inventaire, famille 6 ; aucune carte lue, modèles HubRise et Deliveroo).

Un article porte ses frais (``frais`` : ``[{"nom", "prix", "code_caisse"?}]``). Chaque frais s'ajoute au prix de la ligne, par unité, et part à la caisse comme une option de la
liste « Frais » (nom, prix, code) : la somme des options est notre prix, la caisse retrouve le total. Code seulement, aucune case nouvelle ; « avec couverts », dit par le
client, reste une note de ligne.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

LISTE_DES_FRAIS = "Frais"


def brique_prx7_ligne_de_frais(produit: dict[str, Any]) -> list[dict[str, Any]]:
    """Les frais d'une unité de ``produit``, au format d'un choix enregistré (nom, prix, liste, code), ou ``[]``."""
    return [
        {"option_code": f.get("code_caisse"), "nom": f["nom"], "prix": int(f["prix"]), "groupe": LISTE_DES_FRAIS, "quantite": 1, "choix": []}
        for f in produit.get("frais") or []
    ]


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["frais"] = None
    return carte


enregistrer(Brique(
    "PRX7", "prix_et_conditions", "C", (("produits", "frais"),), brique_prx7_ligne_de_frais,
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=_sans, carte_d_essai="briques/PRX7",
    phrase="les frais d'un article s'ajoutent à sa ligne et partent à la caisse en option ; aucune case nouvelle",
))
