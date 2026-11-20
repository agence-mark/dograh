"""[.mark] Module Restauration, lot 15 (D22) : les allergènes proposés depuis les ingrédients, puis validés (couche d'accès).

Seuls les fichiers ``restauration*.py`` ouvrent une requête sur les tables ``resto_*``. Une suggestion s'écrit sur la ligne du produit ou de l'option de
l'établissement (``allergenes_etat`` = ``propose``, ``allergenes_source`` = ``suggestion``) ; l'agent ne la lit jamais (la carte ne rend que les validés). Une
valeur qu'une personne a écrite (surcouche, ou ligne validée) n'est JAMAIS écrasée par une suggestion. Valider = une écriture de personne, journalisée (qui, quoi, quand)
par les déclencheurs de la 028 : en surcouche quand la caisse ou un fichier porte la ligne (un réimport ne l'efface pas), en direct sinon.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from api.db.bases_clients.restauration_commun import poser_session
from api.db.bases_clients.restauration_ecran import ABSENT, ecrire_le_produit
from api.services.restauration.allergenes_suggeres import suggerer_les_allergenes
from api.services.restauration.signalements import LES_QUATORZE

OBJETS = ("produit", "option")
_TABLES = {"produit": "resto_produit", "option": "resto_option"}


async def proposer_les_allergenes(connexion: asyncpg.Connection, etablissement_id: int, auteur: str) -> dict[str, Any]:
    """Propose les allergènes des produits (d'après leurs ingrédients) et des options (d'après leur nom) de l'établissement dont la donnée est inconnue ou déjà seulement
    proposée. ``{"proposes": [{objet, ref, nom, allergenes}], "a_preciser": [{objet, ref, nom, ingredients}], "deja_ecrits": n}`` ; rien n'est affirmé, rien de validé n'est touché."""
    produits = await connexion.fetch(
        "SELECT p.ref, p.nom, p.ingredients, p.allergenes, p.allergenes_etat, s.allergenes_ecrits FROM mark.resto_produit p "
        "LEFT JOIN mark.resto_surcouche s ON s.site_id = p.site_id AND s.objet = 'produit' AND s.ref = p.ref WHERE p.site_id = $1 AND NOT p.masque", etablissement_id)
    options = await connexion.fetch(
        "SELECT o.ref, o.nom, o.allergenes, o.allergenes_etat, s.allergenes_ecrits FROM mark.resto_option o "
        "LEFT JOIN mark.resto_surcouche s ON s.site_id = o.site_id AND s.objet = 'option' AND s.ref = o.ref WHERE o.site_id = $1 AND NOT o.masque", etablissement_id)
    bilan: dict[str, Any] = {"proposes": [], "a_preciser": [], "deja_ecrits": 0}
    ecritures: dict[str, list[tuple]] = {"produit": [], "option": []}
    for objet, lignes in (("produit", produits), ("option", options)):
        for r in lignes:
            if r["allergenes_ecrits"] or (r["allergenes"] is not None and r["allergenes_etat"] == "valide"):
                bilan["deja_ecrits"] += 1  # une personne (ou la caisse) l'a dit : jamais écrasé
                continue
            noms = [r["nom"]] if objet == "option" else (json.loads(r["ingredients"]) if isinstance(r["ingredients"], str) else r["ingredients"])
            suggestion = suggerer_les_allergenes(noms)
            if suggestion["a_preciser"]:
                bilan["a_preciser"].append({"objet": objet, "ref": r["ref"], "nom": r["nom"], "ingredients": suggestion["a_preciser"]})
            if not suggestion["proposable"]:
                continue  # jamais un « aucun » proposé
            bilan["proposes"].append({"objet": objet, "ref": r["ref"], "nom": r["nom"], "allergenes": suggestion["codes"]})
            if not (r["allergenes_etat"] == "propose" and list(r["allergenes"] or []) == suggestion["codes"]):
                ecritures[objet].append((etablissement_id, r["ref"], suggestion["codes"]))
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        for objet, lot in ecritures.items():
            if lot:
                await connexion.executemany(
                    f"UPDATE mark.{_TABLES[objet]} SET allergenes = $3::text[], allergenes_etat = 'propose', allergenes_source = 'suggestion' WHERE site_id = $1 AND ref = $2", lot)
    return bilan


async def allergenes_en_place(connexion: asyncpg.Connection, etablissement_id: int) -> dict[tuple[str, str], dict[str, Any]]:
    """Les allergènes que l'agent LIT aujourd'hui (validés seulement, surcouche comprise) pour chaque produit et chaque option de l'établissement : la base de « Vérifier depuis ma caisse »."""
    from api.db.bases_clients.restauration_carte import carte_du_restaurant
    from api.services.restauration.allergenes_suggeres import objets_a_comparer

    return objets_a_comparer(await carte_du_restaurant(connexion, etablissement_id))


async def valider_les_allergenes(connexion: asyncpg.Connection, etablissement_id: int, objet: str, ref: str, auteur: str, allergenes: list[str] | None = None) -> str:
    """Une personne valide les allergènes d'un produit ou d'une option : ceux qu'elle donne, sinon la suggestion en attente. Rend ``ok``, ``introuvable`` (pas à la
    carte de cet établissement) ou ``rien_a_valider`` (aucune suggestion en attente et aucune liste donnée). Journalisé par les déclencheurs de la 028."""
    if objet not in OBJETS:
        raise ValueError(f"Objet inconnu : {objet!r}")
    table = _TABLES[objet]
    ligne = await connexion.fetchrow(
        f"SELECT allergenes, allergenes_etat FROM mark.{table} WHERE ref = $2 AND (site_id IS NULL OR site_id = $1) ORDER BY site_id NULLS LAST LIMIT 1", etablissement_id, ref)
    if ligne is None:
        return "introuvable"
    if allergenes is None:
        if ligne["allergenes_etat"] != "propose" or ligne["allergenes"] is None:
            return "rien_a_valider"
        allergenes = list(ligne["allergenes"])
    allergenes = [c for c in LES_QUATORZE if c in set(allergenes)]
    if objet == "produit":
        return "ok" if await ecrire_le_produit(connexion, etablissement_id, ref, ABSENT, allergenes, auteur) else "introuvable"
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await connexion.execute(
            "INSERT INTO mark.resto_surcouche (site_id, objet, ref, allergenes, allergenes_ecrits) VALUES ($1, 'option', $2, $3::text[], true) "
            "ON CONFLICT (site_id, objet, ref) DO UPDATE SET allergenes = EXCLUDED.allergenes, allergenes_ecrits = true", etablissement_id, ref, allergenes)
    return "ok"
