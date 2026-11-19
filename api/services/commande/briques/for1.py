"""[.mark] Brique FOR1 : le menu à composition fixe, prix unique (inventaire, famille 5 ; 35 cartes sur 44).

Le prix d'une formule est le SIEN (celui de sa déclinaison : taille FOR6, nombre de personnes FOR10), plus les suppléments de ses lignes (FOR4) et ceux des choix du plat
(un supplément payant du plat reste payant) ; jamais la somme des produits choisis. « le menu » quand la carte en a plusieurs : la seule formule dont les étapes
acceptent tous les mots de ``composition`` (règle de valeur ; zéro ou plusieurs : le doute reste, rien n'est choisi). Sans composition, quand la recherche rend
une formule et des choix certains de ses étapes (« menu avec un burger, des frites et un coca » écrit dans ``article``) : ce ne sont pas des possibilités, la
formule est retenue et les autres candidats sont ses choix (conversation FOR1-A du lot 11).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_for1_prix_de_la_formule(prix_de_la_declinaison: int, supplements: int) -> int:
    """Le prix d'une unité de la formule : le prix de sa déclinaison et les suppléments choisis."""
    return int(prix_de_la_declinaison) + int(supplements)


def brique_for1_departager_par_la_composition(candidats: list[tuple[str, dict[str, Any] | None]], mots: list[str]) -> str | None:
    """Parmi les articles candidats ``(id, article)``, la seule formule dont chaque mot de ``composition`` est le choix certain d'une de ses étapes ; ``None`` sinon."""
    from api.services.commande.briques.formule import _le_mot_est_un_choix, est_une_etape

    if not mots:
        return None
    gardes = [
        cid for cid, article in candidats
        if article and article.get("formule") and all(any(est_une_etape(g) and _le_mot_est_un_choix(g, m) for g in article["groupes"]) for m in mots)
    ]
    return gardes[0] if len(gardes) == 1 else None


def brique_for1_formule_des_candidats(candidats: list[tuple[str, dict[str, Any] | None]], libelles: dict[str, str]) -> tuple[str, list[str]] | None:
    """Parmi les candidats d'une recherche ``(id, article)``, la seule formule dont chaque AUTRE candidat est le choix certain d'une de ses étapes : son id et le
    libellé des autres (sa composition) ; ``None`` sinon (aucune, plusieurs, ou un candidat qui n'est le choix d'aucune étape : le doute reste)."""
    from api.services.commande.briques.formule import _le_mot_est_un_choix, est_une_etape

    formules = [(cid, a) for cid, a in candidats if a and a.get("formule")]
    if len(formules) != 1 or len(candidats) < 2:
        return None
    cid, article = formules[0]
    autres = [libelles[i] for i, _ in candidats if i != cid]
    if all(any(est_une_etape(g) and _le_mot_est_un_choix(g, m) for g in article["groupes"]) for m in autres):
        return cid, autres
    return None


def _sans(carte: dict) -> dict:
    carte["formules"] = []
    return carte


enregistrer(Brique(
    "FOR1", "formules", "C", (("formules", "lignes"), ("formules", "prix")), brique_for1_prix_de_la_formule,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR1",
    phrase="une formule se compose dans composition ; la question d'une étape ou d'un choix du plat est numérotée",
))
