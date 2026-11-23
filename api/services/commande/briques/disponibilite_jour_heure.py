"""[.mark] Brique PRX1 : la disponibilité par jour et heure (inventaire, famille 6 ; 12 cartes sur 44).

Un produit, une rubrique, une option, une déclinaison ou une formule se sert à certains jours, à certaines heures, entre deux dates (``plages.py``, aucune notion de métier).
La carte est assemblée AU MOMENT que le geste regarde : l'instant de l'appel, ou l'heure voulue d'une précommande (« pour demain midi ») ; ce qui est hors de sa plage à ce
moment n'est pas supprimé, il est marqué (``indisponible``, avec la plage de la donnée) pour que la cuisine le refuse avec la raison et que le modèle dise quand il se sert.
Le refus rend la plage telle que la donnée la porte : jamais une phrase écrite par le code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api.db.bases_clients.plages import dans_la_plage
from api.services.commande.briques.registre import Brique, enregistrer

RAISON = "indisponible_a_ce_moment"
CLES_DE_LA_PLAGE = ("jours", "heures", "dates")


def plage_dite(disponibilite: dict[str, Any] | None) -> dict[str, Any]:
    """La plage que la donnée porte (jamais ``hors_feries``, qui est une règle inconnue de PRX2)."""
    return {cle: disponibilite[cle] for cle in CLES_DE_LA_PLAGE if disponibilite and disponibilite.get(cle)}


def brique_prx1_servi_a_l_instant(objet: dict[str, Any], local: datetime) -> dict[str, Any] | None:
    """``None`` : servi à ``local`` (heure du fuseau de l'établissement) ; sinon la plage où il se sert."""
    disponibilite = objet.get("disponibilite")
    return None if dans_la_plage(disponibilite, local) else plage_dite(disponibilite)


def refus_de_l_article(article: dict[str, Any]) -> dict[str, Any] | None:
    """Le refus d'un article (produit ou formule) hors de sa plage à ce moment, ou ``None`` : ses faits, ``raison`` et ``plage``."""
    plage = article.get("indisponible")
    if plage is None:
        return None
    return {"raison": RAISON, "article": article["nom"], "plage": plage}


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["disponibilite"] = None
        for d in p["declinaisons"]:
            d["disponibilite"] = None
    for c in carte["categories"]:
        c["disponibilite"] = None
    for g in carte["groupes"]:
        for o in g["options"]:
            o["disponibilite"] = None
    for f in carte["formules"]:
        f["disponibilite"] = None
    return carte


enregistrer(Brique(
    "PRX1", "prix_et_conditions", "C",
    (("produits", "disponibilite"), ("categories", "disponibilite"), ("declinaisons", "disponibilite"), ("options", "disponibilite"), ("formules", "disponibilite")),
    brique_prx1_servi_a_l_instant, change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/PRX1",
    phrase="un article hors de sa plage est refusé avec la plage de la donnée ; une précommande se lit à l'heure voulue",
))
