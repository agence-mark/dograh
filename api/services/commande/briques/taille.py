"""[.mark] La taille collée au nom (chantier Partie 1, lot 8 ; banc B12, décision 2 d'Evan, 18/11 soir). Règle de valeur du code, nommée ``lire_la_taille_collee_au_nom``.

Un nom d'article dit sans variante qui, coupé, est exactement le nom d'un produit (lu par la recherche des noms, lexique compris) suivi ou précédé du nom d'UNE
déclinaison de CE produit se lit comme le produit plus cette déclinaison : « reine normale » -> Regina, variante Normale. Tolérance sur la valeur, jamais
sur l'intention (D1) :

- le mot doit être le nom d'une déclinaison de CE produit (au pluriel près) ; « Regina géante » ne change rien : le code redemande la taille ;
- un nom qui est déjà, tel quel, le nom d'un produit n'est jamais coupé (« Petite salade verte » reste ce produit) ;
- un reste qui mène à plusieurs produits, ou à aucun de façon certaine, ne change rien (``RETENU`` seulement : la recherche ne rend jamais un faux sûr) ;
- une variante déjà dans la fiche n'est jamais remplacée (la règle ne s'applique pas) ;
- la déclinaison peut avoir plusieurs mots (« 33 cl », « 2 viandes ») : c'est le nom de la déclinaison qui compte, pas le nombre de mots.

Les recherches sont celles de la source, en mémoire pendant un appel (lot 5) ; au plus six recherches de découpe par article dit.
"""

from __future__ import annotations

from typing import Any

from api.db.bases_clients.recherche_liste import normaliser
from api.services.commande.source import Source


def _au_singulier(mots: list[str]) -> str:
    return " ".join(m[:-1] if len(m) > 3 and m.endswith("s") else m for m in mots)


def _produit_exact(trouve: Any, texte: str) -> str | None:
    """Le produit que ce texte désigne de façon certaine, ou ``None``. ``RETENU`` : la recherche n'a jamais de faux sûr. ``AMBIGU`` : le produit dont le nom est
    EXACTEMENT ce texte (au pluriel près), s'il est seul (« kebab » est le produit Kebab même quand une assiette de kebab existe) ; sinon le doute reste."""
    if trouve.statut == "RETENU":
        return trouve.faits.get("retenu")
    if trouve.statut != "AMBIGU":
        return None
    dit = _au_singulier(normaliser(texte).split())
    exacts = [c for c in trouve.faits.get("candidats") or [] if _au_singulier(normaliser(c["libelle"]).split()) == dit]
    return exacts[0]["id"] if len(exacts) == 1 else None


def _est_le_nom_d_un_produit(trouve: Any, texte: str) -> bool:
    """La recherche mène à UN produit et ce produit se nomme exactement ainsi (au pluriel près)."""
    if trouve.statut != "RETENU":
        return False
    candidats = trouve.faits.get("candidats") or []
    if not candidats:
        return False
    return _au_singulier(normaliser(candidats[0]["libelle"]).split()) == _au_singulier(normaliser(texte).split())


def _declinaison_de(article: dict[str, Any], mots: list[str]) -> dict[str, Any] | None:
    """La déclinaison de CE produit dont le nom est exactement ces mots (au pluriel près) ; ``None`` sinon. Un produit à une seule déclinaison n'en a pas à lire."""
    declinaisons = article.get("declinaisons") or []
    if len(declinaisons) < 2:
        return None
    voulu = _au_singulier(normaliser(" ".join(mots)).split())
    trouvees = [d for d in declinaisons if _au_singulier(normaliser(d["nom"]).split()) == voulu]
    return trouvees[0] if len(trouvees) == 1 else None


async def lire_la_taille_collee_au_nom(source: Source, texte: str, mode: str) -> tuple[str, str] | None:
    """``(nom, variante)`` quand le texte dit un produit collé à sa déclinaison ; ``None`` : rien à lire (le texte reste tel quel)."""
    mots = texte.split()
    if len(mots) < 2:
        return None
    if _est_le_nom_d_un_produit(await source.chercher(texte), texte):
        return None  # un vrai nom de produit n'est jamais coupé
    for k in range(1, min(3, len(mots) - 1) + 1):  # la déclinaison après le nom, puis avant
        for reste, taille in ((mots[:-k], mots[-k:]), (mots[k:], mots[:k])):
            nom = " ".join(reste)
            ref = _produit_exact(await source.chercher(nom), nom)
            if ref is None:
                continue  # un reste qui ne mène pas à UN produit de façon certaine ne change rien
            article = await source.article(ref, mode)
            declinaison = _declinaison_de(article, taille) if article else None
            if declinaison is not None:
                return nom, declinaison["nom"]
    return None
