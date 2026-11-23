"""[.mark] Brique ART3 : le produit « du moment » (inventaire, famille 1).

Un produit dont le contenu change chaque jour à prix fixe (le plat du jour). Le texte est écrit par une personne, en un geste, sur la surcouche du produit
(``du_moment``, ``texte_du_jour``) : un import de caisse ne l'écrase jamais. Le code le lit tel que saisi, jamais inventé ni reformulé ; absent, la lecture dit
qu'il n'est pas renseigné (le modèle ne le confirme pas).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_art3_texte_du_jour(article: dict[str, Any]) -> dict[str, Any] | None:
    """Les faits d'un produit du moment, ou ``None`` : ce n'est pas un produit du moment. ``renseigne`` faux : aucun texte n'a été saisi."""
    if not article.get("du_moment"):
        return None
    texte = " ".join(str(article.get("texte_du_jour") or "").split())
    return {"du_moment": True, "renseigne": bool(texte), **({"texte_du_jour": texte} if texte else {})}


enregistrer(Brique(
    "ART3", "article", "C", (("produits", "du_moment"), ("produits", "texte_du_jour")), brique_art3_texte_du_jour,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/ART3",
    phrase="la lecture du produit du moment rend son texte du jour, tel que saisi, ou renseigne: false",
))
