"""[.mark] Lot F7 : le texte qu'un objet donne à l'agent (D107, D113).

Une valeur simple = sa valeur. Une liste = un tableau texte, toutes ses colonnes (posées par .mark et
ajoutées par le client, D108) : une ligne d'en-tête, puis une ligne par ligne du tableau, cellules séparées
par « | ». Une seule passe, rien d'interprété : le texte saisi part tel quel. Sa longueur est ce que
mesure le plafond (D112).
"""

from __future__ import annotations

from api.schemas.objets_agent import ObjetEnvoye

SEPARATEUR = " | "


def _rang(element) -> tuple[int, int]:
    identifiant = getattr(element, "id", None)
    return (element.ordre, identifiant if identifiant is not None else 1 << 62)


def rendre(objet: ObjetEnvoye) -> str:
    if objet.forme == "valeur":
        return objet.valeur or ""
    colonnes = sorted(objet.colonnes, key=_rang)
    if not colonnes:
        return ""
    entete = SEPARATEUR.join(c.libelle for c in colonnes)
    lignes = [
        SEPARATEUR.join(ligne.valeurs.get(c.libelle, "") for c in colonnes)
        for ligne in sorted(objet.lignes, key=_rang)
    ]
    return "\n".join([entete, *lignes])


def taille(objet: ObjetEnvoye) -> int:
    return len(rendre(objet))
