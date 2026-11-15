"""[.mark] Module Restauration, lot 12 : ce que les écrans du fork (Entreprise › Carte, Livraison, Réglages restaurant) lisent et écrivent.

Même règle que le reste du module : seuls les fichiers ``restauration*.py`` ouvrent une requête sur les tables ``resto_*``. Ce fichier est le
côté « écran » : il ne décide rien que le comptoir ne décide déjà (la carte vient de ``carte_du_restaurant``, la zone d'une adresse de
``zones_de_service``), il range, valide et journalise ce qu'une personne change.

- le module : allumé quand une ligne de ``resto_reglage`` porte ``module_actif`` ; le retirer ne supprime AUCUNE donnée ;
- la carte pour l'écran (portée de chaque objet, ruptures) et les deux surcouches que l'écran tient (étoile, synonymes) ;
- les zones de livraison et les communes trouvées avec leur distance ;
- les réglages d'un établissement (types de commande, paiement, envois, seuils de la liaison, imprimante) et l'historique des changements.

Montants en centimes. L'auteur et la source vont au journal par ``poser_session`` (déclencheurs de la 028).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import asyncpg

from api.db.bases_clients import zones_de_service as zs
from api.db.bases_clients.restauration_carte import carte_du_restaurant
from api.db.bases_clients.restauration_commun import TYPES, poser_session
from api.db.bases_clients.restauration_liaison import horaires_de_l_etablissement
from api.db.bases_clients.restauration_synonymes import LONGUEUR_SYNONYME, MAX_SYNONYMES
from api.db.bases_clients.restauration_zone import centre_de_l_etablissement
from api.services.communes.base import obtenir_base

MAX_ZONES = 5  # les jetons de couleur ``--zone-1`` à ``--zone-5``
MAX_COMMUNES_PAR_ZONE = 400
DECLENCHEUR_HEURE_CHANGEE = "heure_changee"


class ZoneInconnue(LookupError):
    """Une zone nommée par son identifiant n'est pas une zone de cet établissement."""


# --------------------------------------------------------------------------- le module


async def module_allume(connexion: asyncpg.Connection) -> bool:
    return bool(await connexion.fetchval("SELECT EXISTS (SELECT 1 FROM mark.resto_reglage WHERE module_actif)"))


async def poser_le_module(connexion: asyncpg.Connection, actif: bool, auteur: str) -> bool:
    """Allumer = une ligne de réglage par établissement, allumée (celles qui existent gardent leurs valeurs). Retirer = éteindre toutes les lignes :
    la carte, les salles, les commandes, les zones restent. Rend l'état d'après."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        if actif:
            await connexion.execute(
                "INSERT INTO mark.resto_reglage (site_id, module_actif) SELECT id, true FROM mark.site "
                "ON CONFLICT (site_id) DO UPDATE SET module_actif = true"
            )
        else:
            await connexion.execute("UPDATE mark.resto_reglage SET module_actif = false WHERE module_actif")
    return await module_allume(connexion)


# --------------------------------------------------------------------------- la carte pour l'écran


async def carte_pour_l_ecran(connexion: asyncpg.Connection, etablissement_id: int) -> dict[str, Any]:
    """La carte de l'établissement (exceptions appliquées), chaque objet avec sa portée, plus toutes les ruptures posées et la source de la carte."""
    carte = await carte_du_restaurant(connexion, etablissement_id)
    portees: dict[str, dict[str, str]] = {}
    for rubrique, table in (("produits", "resto_produit"), ("groupes", "resto_groupe_choix"), ("formules", "resto_formule"), ("categories", "resto_categorie")):
        lignes = await connexion.fetch(
            f"SELECT ref, portee, site_id, source, maj_le FROM mark.{table} WHERE site_id IS NULL OR site_id = $1 ORDER BY site_id NULLS FIRST", etablissement_id
        )
        # Une exception de l'établissement remplace la ligne d'enseigne : la dernière lue (celle de l'établissement) gagne.
        portees[rubrique] = {r["ref"]: r["portee"] for r in lignes}
    for rubrique in ("produits", "groupes", "formules", "categories"):
        for objet in carte[rubrique]:
            objet["portee"] = portees[rubrique].get(objet["id"], "etablissement")
    ruptures = await connexion.fetch("SELECT code_caisse, disponible, stock, debut, fin, source FROM mark.resto_rupture WHERE site_id = $1 ORDER BY code_caisse", etablissement_id)
    carte["ruptures"] = [dict(r) for r in ruptures]
    carte["derniere_maj"] = await connexion.fetchval(
        "SELECT max(maj_le) FROM (SELECT maj_le FROM mark.resto_produit WHERE site_id IS NULL OR site_id = $1 "
        "UNION ALL SELECT maj_le FROM mark.resto_declinaison WHERE site_id IS NULL OR site_id = $1) t",
        etablissement_id,
    )
    return carte


async def poser_l_etoile(connexion: asyncpg.Connection, etablissement_id: int, ref: str, etoile: bool, auteur: str) -> bool:
    """« Plus demandé » : surcouche d'un produit de la carte de l'établissement. ``False`` : ce produit n'est pas à sa carte."""
    existe = await connexion.fetchval(
        "SELECT 1 FROM mark.resto_produit WHERE ref = $2 AND (site_id IS NULL OR site_id = $1) LIMIT 1", etablissement_id, ref
    )
    if not existe:
        return False
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await connexion.execute(
            "INSERT INTO mark.resto_surcouche (site_id, objet, ref, etoile) VALUES ($1, 'produit', $2, $3) "
            "ON CONFLICT (site_id, objet, ref) DO UPDATE SET etoile = EXCLUDED.etoile",
            etablissement_id, ref, etoile,
        )
    return True


def synonymes_nets(synonymes: list[str]) -> list[str]:
    """Sans blanc ni doublon (à la casse près), dans la limite de la carte."""
    vus: set[str] = set()
    sortie: list[str] = []
    for s in synonymes:
        s = " ".join((s or "").split())[:LONGUEUR_SYNONYME]
        if s and s.casefold() not in vus:
            vus.add(s.casefold())
            sortie.append(s)
    return sortie[:MAX_SYNONYMES]


async def poser_les_synonymes(connexion: asyncpg.Connection, etablissement_id: int, ref: str, synonymes: list[str], auteur: str) -> bool:
    """La liste des synonymes d'un produit, écrite par une personne : elle est active tout de suite (plus rien « à relire »)."""
    existe = await connexion.fetchval(
        "SELECT 1 FROM mark.resto_produit WHERE ref = $2 AND (site_id IS NULL OR site_id = $1) LIMIT 1", etablissement_id, ref
    )
    if not existe:
        return False
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await connexion.execute(
            "INSERT INTO mark.resto_surcouche (site_id, objet, ref, synonymes, synonymes_a_relire) VALUES ($1, 'produit', $2, $3, false) "
            "ON CONFLICT (site_id, objet, ref) DO UPDATE SET synonymes = EXCLUDED.synonymes, synonymes_a_relire = false",
            etablissement_id, ref, synonymes_nets(synonymes),
        )
    return True


# --------------------------------------------------------------------------- la livraison


def _zone_ecran(r: asyncpg.Record) -> dict[str, Any]:
    forme = r["forme"]
    cercle = r["cercle_km"] if r["cercle_km"] is not None else r["rayon_km"]
    return {
        "id": r["id"], "nom": r["nom"], "forme": forme, "cercle_km": float(cercle) if cercle is not None else None,
        "rayon_km": float(r["rayon_km"]) if r["rayon_km"] is not None else None, "communes": list(r["communes"] or []),
        "exclues": list(r["exclues"] or []), "frais": r["frais"], "minimum": r["minimum"], "gratuite_des": r["gratuite_des"],
        "delai": r["delai"], "ordre": r["ordre"],
    }


async def livraison_pour_l_ecran(connexion: asyncpg.Connection, etablissement_id: int, rayon_km: float) -> dict[str, Any]:
    """Les zones de l'établissement et les communes à ``rayon_km`` ou moins, chacune avec sa distance, la zone qui la contient et son exception."""
    lignes = await connexion.fetch("SELECT * FROM mark.resto_zone WHERE site_id = $1 ORDER BY ordre, id", etablissement_id)
    zones = [_zone_ecran(r) for r in lignes]
    site = await connexion.fetchrow("SELECT nom, adresse_insee FROM mark.site WHERE id = $1", etablissement_id)
    base = await obtenir_base()
    centre = await centre_de_l_etablissement(connexion, etablissement_id, base)
    communes: list[dict[str, Any]] = []
    if centre is not None:
        pures = [zs.Zone(id=z["id"], nom=z["nom"], forme=z["forme"], communes=tuple(z["communes"]), rayon_km=z["rayon_km"], exclues=(), ordre=z["ordre"]) for z in zones]
        for c in zs.communes_autour(base, centre[0], centre[1], rayon_km):
            dans = zs.zone_de_la_commune(pures, c, centre)
            refusee = any(c.insee in z["exclues"] for z in zones)
            communes.append(
                {"insee": c.insee, "nom": c.nom, "code_postal": c.cps[0] if c.cps else None,
                 "km": round(zs.distance_km(c, centre[0], centre[1]), 1), "zone_id": dans.id if dans else None, "refusee": refusee}
            )
    commune_etablissement = None
    if site and site["adresse_insee"] and (c := base.commune(site["adresse_insee"].strip())) is not None:
        commune_etablissement = c.nom
    return {"centre_connu": centre is not None, "commune": commune_etablissement, "zones": zones, "communes": communes}


async def ecrire_les_zones(connexion: asyncpg.Connection, etablissement_id: int, zones: list[dict[str, Any]], auteur: str) -> None:
    """Remplace l'ensemble des zones de l'établissement par la liste donnée (au plus ``MAX_ZONES``). Une zone qui garde son ``id`` est mise à jour (les
    commandes passées gardent leur zone), les autres sont créées, celles qui ne figurent plus sont retirées. L'ordre de la liste est l'ordre des
    cercles ; la couleur est son rang."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        gardees = {z["id"] for z in zones if z.get("id") is not None}
        existantes = {r["id"] for r in await connexion.fetch("SELECT id FROM mark.resto_zone WHERE site_id = $1", etablissement_id)}
        if gardees - existantes:
            raise ZoneInconnue(sorted(gardees - existantes))
        await connexion.execute("DELETE FROM mark.resto_zone WHERE site_id = $1 AND id <> ALL($2::bigint[])", etablissement_id, list(gardees))
        for rang, z in enumerate(zones):
            valeurs = (
                z["nom"], z["forme"], list(z["communes"]) if z["forme"] == "communes" else [], z["cercle_km"] if z["forme"] == "rayon" else None,
                list(z["exclues"]), z["frais"], z["minimum"], z["gratuite_des"], z["delai"], z["cercle_km"], min(rang + 1, MAX_ZONES), rang,
            )
            if z.get("id") is None:
                await connexion.execute(
                    "INSERT INTO mark.resto_zone (site_id, nom, forme, communes, rayon_km, exclues, frais, minimum, gratuite_des, delai, cercle_km, couleur, ordre) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)", etablissement_id, *valeurs,
                )
            else:
                await connexion.execute(
                    "UPDATE mark.resto_zone SET nom = $3, forme = $4, communes = $5, rayon_km = $6, exclues = $7, frais = $8, minimum = $9, gratuite_des = $10, "
                    "delai = $11, cercle_km = $12, couleur = $13, ordre = $14 WHERE site_id = $1 AND id = $2", etablissement_id, z["id"], *valeurs,
                )


# --------------------------------------------------------------------------- les réglages


_TYPE_PAR_DEFAUT = {
    "ouvert": True, "pause_jusqu_a": None, "fin_par_jour": {}, "planifiee_permise": False, "delai_minimal": 0, "jours_a_l_avance": 0,
    "delai_annonce": None, "minutes_ajoutees": 0, "ajout_jusqu_a": None, "annonce": "duree",
}
_COLONNES_TYPE = ("ouvert", "fin_par_jour", "planifiee_permise", "delai_minimal", "jours_a_l_avance", "delai_annonce", "annonce")


def _json(valeur: Any) -> Any:
    return json.loads(valeur) if isinstance(valeur, str) else valeur


async def reglages_pour_l_ecran(connexion: asyncpg.Connection, etablissement_id: int) -> dict[str, Any]:
    """Tout ce que l'onglet « Réglages restaurant » montre d'un établissement, d'une lecture."""
    par_type = {r["type"]: r for r in await connexion.fetch("SELECT * FROM mark.resto_reglage_type WHERE site_id = $1", etablissement_id)}
    types = []
    for nom in sorted(TYPES, key=("emporter", "livraison", "sur_place", "reservation").index):
        r = par_type.get(nom)
        valeurs = dict(_TYPE_PAR_DEFAUT) if r is None else {k: (_json(r[k]) if k == "fin_par_jour" else r[k]) for k in _TYPE_PAR_DEFAUT}
        types.append({"type": nom, **valeurs})
    r = await connexion.fetchrow("SELECT * FROM mark.resto_reglage WHERE site_id = $1", etablissement_id)
    reglage = {
        "prefixe_numero_court": r["prefixe_numero_court"] if r else "", "moyens_paiement": list(r["moyens_paiement"]) if r else ["carte", "especes"],
        "plafond_titre_restaurant": r["plafond_titre_restaurant"] if r else None, "conservation_client_mois": r["conservation_client_mois"] if r else 12,
    }
    envoi = await connexion.fetchrow(
        "SELECT texte, actif FROM mark.resto_envoi WHERE site_id = $1 AND type = 'sms' AND declencheur = $2 ORDER BY id LIMIT 1", etablissement_id, DECLENCHEUR_HEURE_CHANGEE
    )
    liaison = await connexion.fetchrow("SELECT alerte_sans_reponse_min, releve_messages_min FROM mark.resto_liaison WHERE site_id = $1", etablissement_id)
    imprimante = await connexion.fetchrow("SELECT mode_planifiee, minutes_avant FROM mark.resto_imprimante WHERE site_id = $1", etablissement_id)
    horaires_fiche = await horaires_de_l_etablissement(connexion, etablissement_id)
    horaires_caisse = await connexion.fetchval("SELECT horaires FROM mark.resto_etat_caisse WHERE site_id = $1", etablissement_id)
    return {
        "types": types, "reglage": reglage,
        "envoi_heure_changee": {"texte": envoi["texte"] if envoi else None, "actif": bool(envoi and envoi["actif"])},
        "seuils": dict(liaison) if liaison else None, "imprimante": dict(imprimante) if imprimante else None,
        "horaires_fiche": horaires_fiche, "horaires_caisse": _json(horaires_caisse),
    }


async def ecrire_les_reglages(connexion: asyncpg.Connection, etablissement_id: int, changements: dict[str, Any], auteur: str) -> None:
    """Applique ce que l'écran a changé (``types``, ``reglage``, ``envoi_heure_changee``, ``seuils``, ``imprimante``), seulement les champs donnés, en
    une transaction. L'état de la caisse (temps ajouté, pause) n'est pas ici : il passe par la puce du temps."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        for t in changements.get("types") or []:
            champs = {k: t[k] for k in _COLONNES_TYPE if k in t}
            await connexion.execute("INSERT INTO mark.resto_reglage_type (site_id, type) VALUES ($1, $2) ON CONFLICT DO NOTHING", etablissement_id, t["type"])
            if champs:
                if "fin_par_jour" in champs:
                    champs["fin_par_jour"] = json.dumps(champs["fin_par_jour"])
                sets = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(champs))
                await connexion.execute(f"UPDATE mark.resto_reglage_type SET {sets} WHERE site_id = $1 AND type = $2", etablissement_id, t["type"], *champs.values())
        reglage = changements.get("reglage")
        if reglage:
            await connexion.execute("INSERT INTO mark.resto_reglage (site_id) VALUES ($1) ON CONFLICT DO NOTHING", etablissement_id)
            sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(reglage))
            await connexion.execute(f"UPDATE mark.resto_reglage SET {sets} WHERE site_id = $1", etablissement_id, *reglage.values())
        envoi = changements.get("envoi_heure_changee")
        if envoi:
            existe = await connexion.fetchval(
                "SELECT id FROM mark.resto_envoi WHERE site_id = $1 AND type = 'sms' AND declencheur = $2 ORDER BY id LIMIT 1", etablissement_id, DECLENCHEUR_HEURE_CHANGEE
            )
            if existe is None:
                if envoi.get("texte"):
                    await connexion.execute(
                        "INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte, actif) VALUES ($1, 'sms', $2, $3, $4)",
                        etablissement_id, DECLENCHEUR_HEURE_CHANGEE, envoi["texte"], bool(envoi.get("actif")),
                    )
            else:
                champs = {k: envoi[k] for k in ("texte", "actif") if envoi.get(k) is not None}
                if champs:
                    sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(champs))
                    await connexion.execute(f"UPDATE mark.resto_envoi SET {sets} WHERE id = $1", existe, *champs.values())
        seuils = changements.get("seuils")
        if seuils:
            sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(seuils))
            await connexion.execute(f"UPDATE mark.resto_liaison SET {sets} WHERE site_id = $1", etablissement_id, *seuils.values())
        imprimante = changements.get("imprimante")
        if imprimante:
            sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(imprimante))
            await connexion.execute(f"UPDATE mark.resto_imprimante SET {sets} WHERE site_id = $1", etablissement_id, *imprimante.values())


_OBJETS_DITS = {
    "resto_reglage_type": "Type de commande", "resto_reglage": "Réglages du module", "resto_zone": "Livraison · zone", "resto_envoi": "Envoi SMS",
    "resto_rupture": "Rupture", "resto_surcouche": "Carte · surcouche", "resto_produit": "Carte · produit", "resto_declinaison": "Carte · prix",
    "resto_etat_caisse": "État de la caisse", "resto_liaison": "Liaison à la caisse", "resto_remise": "Remise", "resto_table": "Salle · table",
}


async def historique_des_changements(connexion: asyncpg.Connection, etablissement_id: int, limite: int, avant_id: int | None) -> list[dict[str, Any]]:
    """Le journal tenu par les déclencheurs : quoi, avant, après, source, qui, quand. Paginé (les plus récents d'abord, ``avant_id`` pour la suite)."""
    lignes = await connexion.fetch(
        "SELECT id, objet, ligne_id, operation, avant, apres, source, auteur, le FROM mark.resto_journal "
        "WHERE site_id = $1 AND ($3::bigint IS NULL OR id < $3) ORDER BY id DESC LIMIT $2",
        etablissement_id, limite, avant_id,
    )
    return [
        {"id": r["id"], "objet": r["objet"], "objet_dit": _OBJETS_DITS.get(r["objet"], r["objet"].removeprefix("resto_")), "ligne_id": r["ligne_id"], "operation": r["operation"],
         "avant": _resume(_json(r["avant"])), "apres": _resume(_json(r["apres"])), "source": r["source"], "auteur": r["auteur"], "le": r["le"]}
        for r in lignes
    ]


def _resume(ligne: dict | None) -> str | None:
    """Une ligne de journal en une phrase courte : jamais plus de quelques champs, jamais de secret (aucune table du journal n'en porte)."""
    if not ligne:
        return None
    gardes = [f"{k} {v}" for k, v in ligne.items() if k not in {"site_id", "id", "maj_le"} and v not in (None, [], {}, "")][:4]
    return ", ".join(gardes)[:160] or None


def maintenant_iso(moment: datetime) -> str:  # petit aide d'affichage des tests
    return moment.isoformat()
