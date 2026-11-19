"""[.mark] Brique DEC5 : le grammage ou le nombre de steaks (inventaire, famille 2).

« Un double » est un produit (une déclinaison de type ``grammage``) ou un supplément : les deux écritures sont acceptées, jamais comptées deux fois (une ligne
identique s'ajoute à sa quantité, ``moteur._fusionner``).
"""

from __future__ import annotations

from api.services.commande.briques.registre import Brique, enregistrer

TYPE = "grammage"


def brique_dec5_double_produit_ou_supplement(declinaisons: list[dict]) -> bool:
    """Vrai quand le « double » de cet article est une déclinaison (le produit au grammage), faux quand il est un supplément."""
    return any(d.get("type") == TYPE for d in declinaisons)


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        for d in p["declinaisons"]:
            if d.get("type") == TYPE:
                d["type"] = None
    return carte


enregistrer(Brique(
    "DEC5", "declinaison", "C", (("declinaisons", "type"),), brique_dec5_double_produit_ou_supplement,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/DEC5",
    phrase="la question d'un grammage absent parle de grammage ; un double en supplément est une option",
))
