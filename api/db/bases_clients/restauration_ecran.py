"""[.mark] Module Restauration, lot 12 : ce que les écrans du fork (Entreprise › Carte, Livraison, Réglages restaurant) lisent et écrivent.

Même règle que le reste du module : seuls les fichiers ``restauration*.py`` ouvrent une requête sur les tables ``resto_*``. Ce fichier est le
côté « écran » : il ne décide rien que le comptoir ne décide déjà (la carte vient de ``carte_du_restaurant``, la zone d'une adresse de
``zones_de_service``), il range, valide et journalise ce qu'une personne change.

- le module : allumé quand ``resto_module.actif`` (état de la base, 035, vrai même sans établissement) ; le retirer ne supprime AUCUNE donnée ;
- la carte pour l'écran (portée de chaque objet, ruptures) et les deux surcouches que l'écran tient (étoile, synonymes) ;
- les zones de livraison et les communes trouvées avec leur distance ;
- les réglages d'un établissement (types de commande, paiement, envois, seuils de la liaison, imprimante) et l'historique des changements.

Montants en centimes. L'auteur et la source vont au journal par ``poser_session`` (déclencheurs de la 028).
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients import zones_de_service as zs
from api.db.bases_clients.restauration_carte import carte_du_restaurant
from api.db.bases_clients.restauration_commun import (
    TYPES,
    fuseau_de,
    maintenant,
    poser_session,
)
from api.db.bases_clients.horaires_caisse import notifier_le_referentiel
from api.db.bases_clients.restauration_liaison import horaires_de_l_etablissement
from api.db.bases_clients.restauration_synonymes import LONGUEUR_SYNONYME, MAX_SYNONYMES
from api.db.bases_clients.restauration_zone import centre_de_l_etablissement
from api.services.actions_communes.moyens_de_paiement import MOYENS_PAR_DEFAUT
from api.services.communes.base import obtenir_base

MAX_ZONES = 5  # les jetons de couleur ``--zone-1`` à ``--zone-5``
MAX_COMMUNES_PAR_ZONE = 400
DECLENCHEUR_HEURE_CHANGEE = "heure_changee"


class ZoneInconnue(LookupError):
    """Une zone nommée par son identifiant n'est pas une zone de cet établissement."""


# --------------------------------------------------------------------------- le module


async def module_allume(connexion: asyncpg.Connection) -> bool:
    """L'état est tenu au niveau de la base (``resto_module``, migration 035) : il existe même sans établissement. Une base sans cette ligne
    (jamais touchée depuis la 035) retombe sur ses lignes de réglage, comme avant."""
    etat = await connexion.fetchval("SELECT actif FROM mark.resto_module")
    if etat is not None:
        return bool(etat)
    return bool(await connexion.fetchval("SELECT EXISTS (SELECT 1 FROM mark.resto_reglage WHERE module_actif)"))


async def poser_le_module(connexion: asyncpg.Connection, actif: bool, auteur: str) -> bool:
    """Allumer = l'état de la base passe à allumé, plus une ligne de réglage par établissement existant, allumée (celles qui existent gardent leurs
    valeurs) ; un établissement créé ensuite reçoit la sienne d'office (déclencheur 035). Retirer = éteindre l'état et toutes les lignes : la carte,
    les salles, les commandes, les zones restent. Rend l'état d'après, relu en base (jamais celui qu'on a demandé)."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await connexion.execute(
            "INSERT INTO mark.resto_module (actif) VALUES ($1) ON CONFLICT (seule) DO UPDATE SET actif = EXCLUDED.actif", actif
        )
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


ABSENT: Any = object()  # « ce champ n'est pas dans la demande » : différent de ``None`` (allergènes inconnus)


async def ecrire_le_produit(
    connexion: asyncpg.Connection, etablissement_id: int, ref: str, ingredients: Any, allergenes: Any, auteur: str, alcool: Any = ABSENT
) -> bool:
    """Ingrédients et allergènes d'un produit, écrits depuis l'onglet Carte. Un champ ``ABSENT`` reste intact ; ``allergenes`` ``None`` = inconnu et ``[]`` =
    aucun (jamais confondus). Quand la caisse (ou un fichier importé) porte le produit, ou qu'il vient de l'enseigne, l'écrit va en SURCOUCHE de
    l'établissement (un réimport ne l'écrase pas, W31) ; sinon la ligne propre de l'établissement est écrite en direct. Source et date mises à jour.
    ``False`` : ce produit n'est pas à la carte de cet établissement."""
    lignes = await connexion.fetch("SELECT site_id, source FROM mark.resto_produit WHERE ref = $2 AND (site_id IS NULL OR site_id = $1)", etablissement_id, ref)
    if not lignes:
        return False
    propre = next((r for r in lignes if r["site_id"] == etablissement_id), None)
    en_direct = propre is not None and propre["source"] not in ("caisse", "import")
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        if alcool is not ABSENT:
            await connexion.execute(
                "INSERT INTO mark.resto_surcouche (site_id, objet, ref, alcool) VALUES ($1, 'produit', $2, $3) "
                "ON CONFLICT (site_id, objet, ref) DO UPDATE SET alcool = EXCLUDED.alcool", etablissement_id, ref, alcool,
            )
        if en_direct and (ingredients is not ABSENT or allergenes is not ABSENT):
            sets, valeurs = ["source = 'mark'"], []
            if ingredients is not ABSENT:
                valeurs.append(json.dumps(ingredients))
                sets.append(f"ingredients = ${len(valeurs) + 2}::jsonb")
            if allergenes is not ABSENT:
                valeurs.append(allergenes)
                sets.append(f"allergenes = ${len(valeurs) + 2}::text[]")
                sets.extend(["allergenes_etat = 'valide'", "allergenes_source = 'restaurateur'"])  # lot 15 (D22) : écrit par une personne = validé
            await connexion.execute(f"UPDATE mark.resto_produit SET {', '.join(sets)} WHERE site_id = $1 AND ref = $2", etablissement_id, ref, *valeurs)
        elif not en_direct and (ingredients is not ABSENT or allergenes is not ABSENT):
            await connexion.execute(
                "INSERT INTO mark.resto_surcouche (site_id, objet, ref) VALUES ($1, 'produit', $2) ON CONFLICT (site_id, objet, ref) DO NOTHING", etablissement_id, ref
            )
            # L'heure vient de la source d'heure de l'organisation (D6), jamais de l'horloge du serveur de base.
            sets, valeurs = ["produit_source = 'mark'", "produit_maj_le = $3"], [await maintenant(connexion)]
            if ingredients is not ABSENT:
                valeurs.append(json.dumps(ingredients))
                sets.append(f"ingredients = ${len(valeurs) + 2}::jsonb")
            if allergenes is not ABSENT:
                valeurs.append(allergenes)
                sets.append(f"allergenes = ${len(valeurs) + 2}::text[]")
                sets.append("allergenes_ecrits = true")
            await connexion.execute(
                f"UPDATE mark.resto_surcouche SET {', '.join(sets)} WHERE site_id = $1 AND objet = 'produit' AND ref = $2", etablissement_id, ref, *valeurs
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
    """La liste des synonymes d'un produit, ou d'une OPTION d'un groupe de choix (SA-52 : « poulet » pour la viande « Chicken »), écrite par une
    personne : elle est active tout de suite (plus rien « à relire »). Le produit passe d'abord quand une ref nomme les deux. ``False`` : ni l'un
    ni l'autre n'est à la carte de cet établissement."""
    objet = None
    for table, nom in (("resto_produit", "produit"), ("resto_option", "option")):
        if await connexion.fetchval(f"SELECT 1 FROM mark.{table} WHERE ref = $2 AND (site_id IS NULL OR site_id = $1) LIMIT 1", etablissement_id, ref):
            objet = nom
            break
    if objet is None:
        return False
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await connexion.execute(
            "INSERT INTO mark.resto_surcouche (site_id, objet, ref, synonymes, synonymes_a_relire) VALUES ($1, $2, $3, $4, false) "
            "ON CONFLICT (site_id, objet, ref) DO UPDATE SET synonymes = EXCLUDED.synonymes, synonymes_a_relire = false",
            etablissement_id, objet, ref, synonymes_nets(synonymes),
        )
    return True


async def poser_l_accord_du_produit(connexion: asyncpg.Connection, etablissement_id: int, ref: str, genre: str | None, nom_commun: bool | None, auteur: str) -> bool:
    """Le genre (``m`` ou ``f``) et le nom commun d'un produit, écrits par une personne (lot 8, E17) : ce qui accorde ce que l'agent dit (« une
    Napoli », « deux tiramisus »). Jamais deviné : sans cette ligne, « un » et pas de pluriel. Une surcouche que l'import ne touche pas. ``False`` :
    ce produit n'est pas à la carte de cet établissement."""
    if genre not in (None, "m", "f"):
        raise ValueError(f"Genre inconnu : {genre!r}")
    if not await connexion.fetchval("SELECT 1 FROM mark.resto_produit WHERE ref = $2 AND (site_id IS NULL OR site_id = $1) LIMIT 1", etablissement_id, ref):
        return False
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await connexion.execute(
            "INSERT INTO mark.resto_surcouche (site_id, objet, ref, genre, nom_commun) VALUES ($1, 'produit', $2, $3, $4) "
            "ON CONFLICT (site_id, objet, ref) DO UPDATE SET genre = EXCLUDED.genre, nom_commun = EXCLUDED.nom_commun",
            etablissement_id, ref, genre, nom_commun,
        )
    return True


async def poser_le_produit_du_moment(connexion: asyncpg.Connection, etablissement_id: int, ref: str, texte: str | None, auteur: str) -> bool:
    """Le produit « du moment » (le plat du jour, ART3) : son texte tel que la personne l'écrit, changé en un geste chaque matin. ``texte`` vide ou
    ``None`` : le produit n'est plus du moment. ``False`` : ce produit n'est pas à la carte de cet établissement."""
    texte = " ".join((texte or "").split()) or None
    if not await connexion.fetchval("SELECT 1 FROM mark.resto_produit WHERE ref = $2 AND (site_id IS NULL OR site_id = $1) LIMIT 1", etablissement_id, ref):
        return False
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await connexion.execute(
            "INSERT INTO mark.resto_surcouche (site_id, objet, ref, du_moment, texte_du_jour) VALUES ($1, 'produit', $2, $3, $4) "
            "ON CONFLICT (site_id, objet, ref) DO UPDATE SET du_moment = EXCLUDED.du_moment, texte_du_jour = EXCLUDED.texte_du_jour",
            etablissement_id, ref, texte is not None, texte,
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
        "prefixe_numero_court": r["prefixe_numero_court"] if r else "", "moyens_paiement": list(r["moyens_paiement"]) if r else list(MOYENS_PAR_DEFAUT),
        "plafond_titre_restaurant": r["plafond_titre_restaurant"] if r else None, "conservation_client_mois": r["conservation_client_mois"] if r else 12,
        "numero_mode": r["numero_mode"] if r else "aucun", "prefixe_mixte": r["prefixe_mixte"] if r else "MIX", "notes_libres": r["notes_libres"] if r else True,
        "titre_alcool_exclu": r["titre_alcool_exclu"] if r else True, "titre_sans_rendu": r["titre_sans_rendu"] if r else True,
        "pause_caisse_pause_telephone": r["pause_caisse_pause_telephone"] if r else True,
    }
    recurrents = [
        {"id": x["id"], "type": x["type"], "jours": sorted(x["jours"]), "debut": x["debut"].strftime("%H:%M"), "fin": x["fin"].strftime("%H:%M"), "minutes_ajoutees": x["minutes_ajoutees"]}
        for x in await connexion.fetch("SELECT * FROM mark.resto_temps_recurrent WHERE site_id = $1 ORDER BY type, debut, id", etablissement_id)
    ]
    envoi = await connexion.fetchrow(
        "SELECT texte, actif FROM mark.resto_envoi WHERE site_id = $1 AND type = 'sms' AND declencheur = $2 ORDER BY id LIMIT 1", etablissement_id, DECLENCHEUR_HEURE_CHANGEE
    )
    liaison = await connexion.fetchrow("SELECT alerte_sans_reponse_min, releve_messages_min FROM mark.resto_liaison WHERE site_id = $1", etablissement_id)
    imprimante = await connexion.fetchrow("SELECT mode_planifiee, minutes_avant FROM mark.resto_imprimante WHERE site_id = $1", etablissement_id)
    horaires_fiche = await horaires_de_l_etablissement(connexion, etablissement_id)
    horaires_caisse = await connexion.fetchval("SELECT horaires FROM mark.resto_etat_caisse WHERE site_id = $1", etablissement_id)
    return {
        "types": types, "reglage": reglage, "recurrents": recurrents, "fermetures": await _fermetures_a_venir(connexion, etablissement_id),
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
        reglage = dict(changements.get("reglage") or {})
        sources = reglage.pop("sources", None)
        if sources:
            await connexion.execute("INSERT INTO mark.resto_reglage (site_id) VALUES ($1) ON CONFLICT DO NOTHING", etablissement_id)
            await connexion.execute("UPDATE mark.resto_reglage SET sources = sources || $2::jsonb WHERE site_id = $1", etablissement_id, json.dumps(sources))
            if "horaires" in sources:
                await notifier_le_referentiel(connexion, "sources_horaires")  # M57 : la fiche et l'agent lisent la caisse, ou ne la lisent plus
        if reglage:
            await connexion.execute("INSERT INTO mark.resto_reglage (site_id) VALUES ($1) ON CONFLICT DO NOTHING", etablissement_id)
            sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(reglage))
            await connexion.execute(f"UPDATE mark.resto_reglage SET {sets} WHERE site_id = $1", etablissement_id, *reglage.values())
        if changements.get("recurrents") is not None:
            await _ecrire_les_recurrents(connexion, etablissement_id, changements["recurrents"])
        if changements.get("fermetures") is not None:
            await _ecrire_les_fermetures(connexion, etablissement_id, changements["fermetures"])
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


async def _fermetures_a_venir(connexion: asyncpg.Connection, etablissement_id: int) -> list[dict[str, Any]]:
    """Les fermetures exceptionnelles en cours ou à venir (jour de début et de fin INCLUS, heure locale de l'établissement)."""
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    lignes = await connexion.fetch(
        "SELECT id, du, au, motif FROM mark.fermeture WHERE site_id = $1 AND au > $2 ORDER BY du, id", etablissement_id, await maintenant(connexion)
    )
    return [
        {"id": r["id"], "du": r["du"].astimezone(fuseau).date(), "au": (r["au"].astimezone(fuseau) - timedelta(seconds=1)).date(), "motif": r["motif"]}
        for r in lignes
    ]


async def _ecrire_les_fermetures(connexion: asyncpg.Connection, etablissement_id: int, fermetures: list[dict[str, Any]]) -> None:
    """Remplace la liste des fermetures exceptionnelles en cours ou à venir : avec ``id`` mise à jour, sans ``id`` créée, une absente retirée. Les passées
    ne bougent pas. Un jour de début et de fin (inclus) devient minuit local à minuit local du lendemain de la fin : ``etat_combine`` les lit tel quel."""
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    en_cours = {r["id"] for r in await connexion.fetch("SELECT id FROM mark.fermeture WHERE site_id = $1 AND au > $2", etablissement_id, await maintenant(connexion))}
    gardees = {f["id"] for f in fermetures if f.get("id") is not None}
    if gardees - en_cours:
        raise ZoneInconnue(sorted(gardees - en_cours))
    await connexion.execute("DELETE FROM mark.fermeture WHERE site_id = $1 AND id = ANY($2::bigint[]) AND id <> ALL($3::bigint[])", etablissement_id, sorted(en_cours), sorted(gardees))
    for f in fermetures:
        debut = datetime.combine(f["du"], time.min, tzinfo=fuseau)
        fin = datetime.combine(f["au"] + timedelta(days=1), time.min, tzinfo=fuseau)
        if f.get("id") is None:
            await connexion.execute("INSERT INTO mark.fermeture (site_id, du, au, motif) VALUES ($1, $2, $3, $4)", etablissement_id, debut, fin, f.get("motif"))
        else:
            await connexion.execute("UPDATE mark.fermeture SET du = $3, au = $4, motif = $5 WHERE site_id = $1 AND id = $2", etablissement_id, f["id"], debut, fin, f.get("motif"))


async def _ecrire_les_recurrents(connexion: asyncpg.Connection, etablissement_id: int, recurrents: list[dict[str, Any]]) -> None:
    """Remplace la liste des soirs toujours chargés : une ligne avec son ``id`` est mise à jour, sans ``id`` créée, une absente retirée."""
    gardees = {r["id"] for r in recurrents if r.get("id") is not None}
    existantes = {x["id"] for x in await connexion.fetch("SELECT id FROM mark.resto_temps_recurrent WHERE site_id = $1", etablissement_id)}
    if gardees - existantes:
        raise ZoneInconnue(sorted(gardees - existantes))
    await connexion.execute("DELETE FROM mark.resto_temps_recurrent WHERE site_id = $1 AND id <> ALL($2::bigint[])", etablissement_id, list(gardees))
    for r in recurrents:
        valeurs = (r["type"], sorted(set(r["jours"])), time.fromisoformat(r["debut"]), time.fromisoformat(r["fin"]), r["minutes_ajoutees"])
        if r.get("id") is None:
            await connexion.execute(
                "INSERT INTO mark.resto_temps_recurrent (site_id, type, jours, debut, fin, minutes_ajoutees) VALUES ($1, $2, $3, $4, $5, $6)", etablissement_id, *valeurs
            )
        else:
            await connexion.execute(
                "UPDATE mark.resto_temps_recurrent SET type = $3, jours = $4, debut = $5, fin = $6, minutes_ajoutees = $7 WHERE site_id = $1 AND id = $2",
                etablissement_id, r["id"], *valeurs,
            )


_OBJETS_DITS = {
    "resto_temps_recurrent": "Temps d'attente récurrent",
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
    sortie = []
    for r in lignes:
        avant, apres = _json(r["avant"]), _json(r["apres"])
        sortie.append(
            {"id": r["id"], "objet": r["objet"], "objet_dit": _OBJETS_DITS.get(r["objet"], r["objet"].removeprefix("resto_")), "ligne_id": r["ligne_id"], "operation": r["operation"],
             "avant": _resume(avant, apres), "apres": _resume(apres, avant), "source": r["source"], "auteur": r["auteur"], "le": r["le"]}
        )
    return sortie


def _resume(ligne: dict | None, autre: dict | None) -> str | None:
    """Une ligne de journal en une phrase courte. Un changement ne montre que les champs qui ont bougé ; une création ou un retrait, les premiers champs
    renseignés. Jamais de secret : aucune table du journal n'en porte."""
    if not ligne:
        return None
    ignores = {"site_id", "id", "maj_le"}
    if autre:
        gardes = [f"{k} {v}" for k, v in ligne.items() if k not in ignores and v != autre.get(k)]
    else:
        gardes = [f"{k} {v}" for k, v in ligne.items() if k not in ignores and v not in (None, [], {}, "")][:4]
    return ", ".join(gardes[:4])[:160] or None

