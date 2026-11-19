"""[.mark] Module Restauration, lot 26 (M25) : la vente en plus PRÉCISE, lue dans la carte et les remises de l'établissement (couche d'accès, lecture seule).

Hors des 17 fonctions du contrat. Deux questions, chacune à réponse fermée :

- ``offres_a_portee`` : parmi les remises « X achetés, Y offerts d'une autre catégorie », lesquelles sont atteintes (le panier a de quoi les déclencher mais
  l'article offert n'y est pas) ou presque atteintes (il manque un exemplaire) ; avec l'article à proposer ;
- ``proposition_en_plus`` : UN produit précis de la carte à proposer, par une règle simple et dite, dans cet ordre :
  1. une offre atteinte : un article de la catégorie offerte (« avec deux pizzas, la boisson est offerte ») ;
  2. la boisson quand le panier n'en a pas, puis le dessert quand il n'en a pas (catégorie manquante) ;
  3. dans la catégorie, la meilleure vente si la carte en marque une (l'étoile), sinon le premier de la catégorie à l'ordre de la carte.
  Un article qui exige un choix obligatoire passe après ceux qui n'en exigent pas ; l'alcool, les ruptures et ce qui n'est pas servi à ce moment ne sont jamais
  proposés. Rien à proposer : ``None`` (jamais une phrase générique).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients import remises_moteur as moteur
from api.db.bases_clients.restauration_carte import _json, accord_du_produit, carte_du_restaurant, disponible_a, ruptures_du_restaurant
from api.db.bases_clients.restauration_commun import fuseau_de, maintenant
from api.db.bases_clients.restauration_remise import FAMILLE_DU_MECANISME, remises_actives_a

# Lot 8 (E17) : le rôle que la fiche de la catégorie donne (``resto_categorie.role``, liste fermée du format commun) décide de la vente en plus ; aucun mot de
# restaurant n'est lu dans un nom. Les rôles qui complètent un panier, dans l'ordre où on les propose ; ``jamais_propose`` n'est jamais proposé (l'alcool, par
# exemple, selon ce que le restaurateur a écrit). Une catégorie sans rôle (carte ancienne) : rien n'est proposé d'elle, jamais deviné.
COMPLEMENTS = ("boisson", "dessert")
JAMAIS_PROPOSE = "jamais_propose"


def _roles_de_la_lignee(categories: dict[str, dict], ref: str | None) -> list[str]:
    """Les rôles (non vides) de la catégorie puis de ses parents, du plus proche au plus lointain."""
    roles, vues = [], set()
    while ref and ref in categories and ref not in vues:
        vues.add(ref)
        if categories[ref].get("role"):
            roles.append(categories[ref]["role"])
        ref = categories[ref].get("parent_id")
    return roles


def _famille(categories: dict[str, dict], ref: str | None) -> str | None:
    roles = _roles_de_la_lignee(categories, ref)
    if JAMAIS_PROPOSE in roles:
        return None
    return next((r for r in roles if r in COMPLEMENTS), None)


def _sous_arbre(categories: dict[str, dict], racine: str) -> set[str]:
    ids = {racine}
    changement = True
    while changement:
        changement = False
        for c in categories.values():
            if c.get("parent_id") in ids and c["id"] not in ids:
                ids.add(c["id"])
                changement = True
    return ids


def _candidats(carte: dict, ruptures: set[str], mode: str, dans: set[str]) -> list[dict[str, Any]]:
    """Les produits de ces catégories qu'on peut ajouter tout de suite : une déclinaison vendable, pas en rupture, pas d'alcool."""
    groupes = {g["id"]: g for g in carte["groupes"]}
    noms_des_categories = {c["id"]: c["nom"] for c in carte["categories"]}
    sortie = []
    for rang, p in enumerate(carte["produits"]):
        if p["categorie_id"] not in dans or p.get("alcool"):
            continue
        decl = [d for d in p["declinaisons"] if d["vendable"] and d["code_caisse"] not in ruptures]
        if not decl:
            continue
        d = min(decl, key=lambda d: (d.get("prix_par_mode") or {}).get(mode, d["prix"]))
        choix_obligatoire = any(groupes[g]["min"] >= 1 for g in p["groupes"] if g in groupes and groupes[g]["parent_option_id"] is None)
        sortie.append(
            {
                "ref": p["id"], "nom": p["nom"], "code": d["code_caisse"], "declinaison": d["nom"], "etoile": bool(p.get("etoile")),
                "prix": (d.get("prix_par_mode") or {}).get(mode, d["prix"]), "categorie_id": p["categorie_id"], "categorie": noms_des_categories.get(p["categorie_id"]),
                "phrase": p.get("phrase"), "genre": accord_du_produit(p)[0], "commun": accord_du_produit(p)[1],
                "choix_obligatoire": choix_obligatoire, "rang": rang, "plusieurs_tailles": len(p["declinaisons"]) > 1,
            }
        )
    return sorted(sortie, key=lambda c: (c["choix_obligatoire"], not c["etoile"], c["rang"]))


def _unites(lignes: list[dict]) -> list[moteur.Unite]:
    return [
        moteur.Unite(rang, l["code_caisse"], int(l["prix_unitaire"]), l.get("produit_id"), l.get("categorie_id"))
        for rang, l in enumerate(lignes, start=1) for _ in range(int(l.get("quantite", 1)))
    ]


async def _remises_actives(connexion: asyncpg.Connection, etablissement_id: int, moment: datetime) -> list[asyncpg.Record]:
    local = moment.astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id)))
    lignes = await remises_actives_a(connexion, etablissement_id, moment)
    return [r for r in lignes if r["mecanisme"] in FAMILLE_DU_MECANISME and disponible_a(_json(r["moment"]), local)]


def _cible(perimetre: dict, carte: dict) -> set[str]:
    """Les catégories (avec leurs sous-catégories) que désigne un périmètre ``{categories: [...]}`` ; vide quand il n'en désigne pas."""
    categories = {c["id"]: c for c in carte["categories"]}
    ids: set[str] = set()
    for ref in perimetre.get("categories") or []:
        if ref in categories:
            ids |= _sous_arbre(categories, ref)
    return ids


async def offres_a_portee(
    connexion: asyncpg.Connection, etablissement_id: int, mode: str, lignes: list[dict], moment: datetime | None = None
) -> list[dict[str, Any]]:
    """Les offres « X achetés, Y offerts d'une autre catégorie » atteintes ou presque atteintes par ce panier (``lignes`` : les lignes chiffrées).

    ``[{ref, nom, phrase, etat: "atteinte"|"presque", manque, offerts_a_prendre, proposition, choix}]`` ; ``manque`` : combien d'exemplaires achetés il reste
    à prendre (zéro quand elle est atteinte) ; ``offerts_a_prendre`` : combien d'articles offerts le panier ne contient pas encore ; ``proposition`` : l'article
    offert à proposer (``None`` si la catégorie n'a rien de servi à ce moment). Une offre déjà appliquée en entier n'y figure pas."""
    if not lignes:
        return []
    moment = moment or await maintenant(connexion)
    carte = await carte_du_restaurant(connexion, etablissement_id, moment)
    ruptures = {r["code_caisse"] for r in await ruptures_du_restaurant(connexion, etablissement_id, moment)}
    unites = _unites(lignes)
    sortie = []
    for r in await _remises_actives(connexion, etablissement_id, moment):
        if r["mecanisme"] != "x_achetes_y_offert":
            continue
        declencheur, effet, perimetre = _json(r["declencheur"]) or {}, _json(r["effet"]) or {}, _json(r["perimetre"]) or {}
        x, y = declencheur.get("achetes"), effet.get("offerts")
        offert = effet.get("perimetre_offert") or {}
        if not (isinstance(x, int) and isinstance(y, int) and x > 0 and y > 0) or not offert:
            continue
        if perimetre.get("modes") and mode not in perimetre["modes"]:
            continue
        achetees = [u for u in unites if moteur.dans_le_perimetre(u, perimetre)]
        presentes = [u for u in unites if moteur.dans_le_perimetre(u, offert)]
        lots = len(achetees) // x
        plafond = ((_json(r["limite"]) or {}).get("max_par_achat")) or lots
        a_prendre = max(0, min(lots, plafond) * y - len(presentes))
        if lots >= 1 and a_prendre > 0:
            etat, manque = "atteinte", 0
        elif lots == 0 and len(achetees) == x - 1 and achetees:
            etat, manque = "presque", 1
        else:
            continue
        dans = _cible(offert, carte)
        propositions = _candidats(carte, ruptures, mode, dans) if dans else []
        sortie.append(
            {
                "ref": r["ref"] or str(r["id"]), "nom": r["nom"], "phrase": r["phrase"], "etat": etat, "manque": manque,
                "offerts_a_prendre": a_prendre if etat == "atteinte" else y,
                "proposition": propositions[0] if propositions else None, "choix": [p["nom"] for p in propositions[:3]],
            }
        )
    return sortie


async def proposition_en_plus(
    connexion: asyncpg.Connection, etablissement_id: int, mode: str, lignes: list[dict], moment: datetime | None = None, avec_offre: bool = True
) -> dict[str, Any] | None:
    """UN produit précis à proposer en plus de ce panier, ou ``None``. ``avec_offre`` faux : sans passer par une offre (l'appelant a déjà entendu parler
    d'une remise, ou l'a refusée : la règle des mentions)."""
    moment = moment or await maintenant(connexion)
    if avec_offre:
        for offre in await offres_a_portee(connexion, etablissement_id, mode, lignes, moment):
            if offre["etat"] == "atteinte" and offre["proposition"]:
                return {
                    **offre["proposition"], "raison": "offre", "choix": offre["choix"],
                    "offre": {"ref": offre["ref"], "nom": offre["nom"], "phrase": offre["phrase"]},
                }
    carte = await carte_du_restaurant(connexion, etablissement_id, moment)
    ruptures = {r["code_caisse"] for r in await ruptures_du_restaurant(connexion, etablissement_id, moment)}
    categories = {c["id"]: c for c in carte["categories"]}
    presentes = {_famille(categories, l.get("categorie_id")) for l in lignes}
    for famille in COMPLEMENTS:
        if famille in presentes:
            continue
        dans = {c["id"] for c in carte["categories"] if _famille(categories, c["id"]) == famille}
        choix = _candidats(carte, ruptures, mode, dans)
        if choix:
            return {**choix[0], "raison": "categorie_manquante", "famille": famille, "choix": [c["nom"] for c in choix[:3]]}
    return None
