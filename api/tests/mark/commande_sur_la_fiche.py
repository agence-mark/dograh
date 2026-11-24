"""[.mark] Chantier Partie 1, lot 4 (D49) : les gestes du moteur tels que la porte les fait, pour les anciens tests de la cuisine réécrits sur la fiche.

Le modèle remplit la fiche ; le code ne relit jamais les mots pour trouver un article (D1, M19). Un article se donne donc structuré, comme dans la
case ``ajouter`` (nom, quantité, variante, suppléments, retraits, moitiés, précision), et une réponse à la question ouverte passe par la même
fonction que la porte (``porte.repondre_a_la_question`` mène à ``moteur.repondre_a_un_choix`` pour une variante ou un choix).
"""

from __future__ import annotations

from typing import Any

from api.services.commande import moteur
from api.services.commande.resultat import Resultat


def article(nom: str, quantite: int = 1, variante: str | None = None, *, supplements: list[str] | None = None, sans: list[str] | None = None,
            moities: list[str] | None = None, precision: str | None = None) -> dict[str, Any]:
    """Un objet de la case ``ajouter`` de la fiche."""
    a: dict[str, Any] = {"article": nom, "quantite": quantite}
    if variante:
        a["variante"] = variante
    if supplements:
        a["supplements"] = supplements
    if sans:
        a["sans"] = sans
    if moities:
        a["moities"] = moities
    if precision:
        a["precision_article"] = precision
    return a


async def ajouter(source, p: dict[str, Any], regles: moteur.Reglages, *articles: dict[str, Any] | str) -> Resultat:
    """La case ``ajouter`` comme la porte l'exécute : chaque article par ``moteur.ajouter_un_article``, puis l'état du panier (sa question d'abord)."""
    r: Resultat | None = None
    for a in articles:
        r = await moteur.ajouter_un_article(source, p, regles, article(a) if isinstance(a, str) else a)
    assert r is not None, "aucun article"
    if r.statut == "OK" and "garde" not in (r.faits or {}):
        etat = await moteur.etat_apres_ajout(source, p, regles, dict(r.faits or {}))
        r = Resultat(etat.statut, etat.faits, etat.suggestion, etat.manque)
    return r


async def repondre(source, p: dict[str, Any], regles: moteur.Reglages, choix: str | None = None, *, sans: str | None = None, note: str | None = None,
                   moities: str | None = None) -> Resultat:
    """La réponse à la question ouverte (une variante, un choix obligatoire), comme la porte la range."""
    return await moteur.repondre_a_un_choix(source, p, regles, choix=choix, sans=sans, note=note, moities=moities)
