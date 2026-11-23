"""[.mark] Brique INF5 : l'épice en descripteur (inventaire, famille 9 ; A32 : « c'est fort ? »).

Un texte écrit par une personne (``epice`` : « fort, piment d'Espelette »), repris tel quel ; jamais un niveau chiffré ni un avis du code. Sans texte : « je ne peux pas vous le confirmer ».
"""

from __future__ import annotations

from api.services.commande.briques.registre import Brique, enregistrer


def brique_inf5_depuis_le_texte(epice: str | None) -> str | None:
    """Le texte de l'épice, espaces nettoyés ; ``None`` quand rien n'est écrit."""
    texte = " ".join((epice or "").split())
    return texte or None


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["epice"] = None
    return carte


enregistrer(Brique(
    "INF5", "informations", "C", (("produits", "epice"),), brique_inf5_depuis_le_texte,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/INF5",
    phrase="l'épice est dite comme elle est écrite ; sans texte : « je ne peux pas vous le confirmer »",
))
