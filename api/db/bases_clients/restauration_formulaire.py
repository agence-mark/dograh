"""[.mark] Chantier Partie 1, lot 17 : le formulaire du restaurateur écrit dans la base du client (couche d'accès, une transaction).

Rejouable sans effet double (D10, installation reprenable) : l'établissement est retrouvé par sa clé, les horaires, les créneaux et la durée
d'une table sont remplacés par ceux du formulaire, une zone est retrouvée par son nom (son identifiant et les commandes passées qui la citent
sont gardés), les réglages par type sont posés par ``INSERT ... ON CONFLICT``. Seul ce que le formulaire DIT est écrit : une donnée absente
(niveau B ou C laissé vide) ne remplace rien de ce qui existe. La carte passe par ``importer_carte`` (idempotent, n'écrase jamais une ligne
qu'une personne a écrite).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import asyncpg

from api.db.bases_clients.restauration_carte import importer_carte
from api.db.bases_clients.restauration_commun import poser_session

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
TYPES_DES_SERVICES = ("emporter", "livraison", "sur_place")


def horaires_en_texte(horaires: Mapping[str, Any]) -> str:
    """``{"1": [["11:00", "14:00"], ["18:00", "22:30"]]}`` -> « lundi : 11:00-14:00 et 18:00-22:30 » (une ligne par jour ouvert)."""
    lignes = []
    for i, jour in enumerate(JOURS, 1):
        plages = horaires.get(str(i)) or []
        if plages:
            lignes.append(f"{jour} : " + " et ".join(f"{a}-{b}" for a, b in plages))
    return "\n".join(lignes)


async def _entreprise(connexion: asyncpg.Connection, nom: str) -> int:
    existante = await connexion.fetchval("SELECT id FROM mark.entreprise ORDER BY id LIMIT 1")
    if existante is not None:
        return existante
    return await connexion.fetchval("INSERT INTO mark.entreprise (raison_sociale) VALUES ($1) RETURNING id", nom)


async def ecrire_le_formulaire(connexion: asyncpg.Connection, cle: str, f: Mapping[str, Any], auteur: str) -> dict[str, Any]:
    """Écrit ce que le formulaire dit pour l'établissement ``cle`` ; rend ``{etablissement_id, carte}``."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        adresse = f.get("adresse") or {}
        horaires = f.get("horaires") if isinstance(f.get("horaires"), Mapping) else None
        site = await connexion.fetchval(
            """
            INSERT INTO mark.site (entreprise_id, cle, nom, actif, fuseau, adresse, adresse_voie, adresse_cp, adresse_insee, adresse_commune,
                                   horaires_texte, numero_transfert)
            VALUES ($1, $2, $3, true, 'Europe/Paris', $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (cle) DO UPDATE SET
                nom = EXCLUDED.nom, actif = true, adresse = EXCLUDED.adresse, adresse_voie = EXCLUDED.adresse_voie, adresse_cp = EXCLUDED.adresse_cp,
                adresse_insee = EXCLUDED.adresse_insee, adresse_commune = EXCLUDED.adresse_commune,
                horaires_texte = coalesce(EXCLUDED.horaires_texte, mark.site.horaires_texte),
                numero_transfert = coalesce(EXCLUDED.numero_transfert, mark.site.numero_transfert)
            RETURNING id
            """,
            await _entreprise(connexion, f["nom_etablissement"]), cle, f["nom_etablissement"],
            ", ".join(x for x in (adresse.get("voie"), f"{adresse.get('code_postal') or ''} {adresse.get('commune') or ''}".strip()) if x),
            adresse.get("voie"), adresse.get("code_postal"), adresse.get("insee"), adresse.get("commune"),
            horaires_en_texte(horaires) if horaires else None, (f.get("transfert") or {}).get("numero"),
        )
        if horaires:
            await connexion.execute("DELETE FROM mark.horaire WHERE site_id = $1", site)
            for jour, plages in horaires.items():
                for ouverture, fermeture in plages or []:
                    await connexion.execute(
                        "INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, $3::text::time, $4::text::time)",
                        site, int(jour), ouverture, fermeture,
                    )
        await connexion.execute("INSERT INTO mark.resto_reglage (site_id) VALUES ($1) ON CONFLICT DO NOTHING", site)
        if f.get("moyens_paiement"):
            await connexion.execute("UPDATE mark.resto_reglage SET moyens_paiement = $2::text[] WHERE site_id = $1", site, list(f["moyens_paiement"]))
        if f.get("allergenes") in ("renseignes", "renvoyer_vers_le_restaurant"):
            await connexion.execute(
                "UPDATE mark.resto_reglage SET allergies_renvoyees_au_restaurant = $2 WHERE site_id = $1", site, f["allergenes"] == "renvoyer_vers_le_restaurant"
            )
        services = set(f.get("services") or ())
        preparation = f.get("temps_de_preparation") or {}
        for type_ in (*TYPES_DES_SERVICES, "reservation"):
            ouvert = (type_ in services) if type_ != "reservation" else ("prise_de_reservation" in (f.get("missions") or ()))
            await connexion.execute(
                "INSERT INTO mark.resto_reglage_type (site_id, type, ouvert) VALUES ($1, $2, $3) ON CONFLICT (site_id, type) DO UPDATE SET ouvert = EXCLUDED.ouvert",
                site, type_, ouvert,
            )
            if isinstance(preparation.get(type_), int):
                await connexion.execute("UPDATE mark.resto_reglage_type SET delai_annonce = $3 WHERE site_id = $1 AND type = $2", site, type_, preparation[type_])
        zones = [z for z in f.get("zones") or [] if isinstance(z, Mapping)]
        if zones:
            gardees = []
            for rang, z in enumerate(zones):
                forme = "rayon" if z.get("rayon_km") else "communes"
                valeurs = (z["nom"], forme, list(z.get("communes") or []), z.get("rayon_km"), z["minimum"], z.get("frais"), z.get("delai"), z.get("gratuite_des"), rang)
                existante = await connexion.fetchval("SELECT id FROM mark.resto_zone WHERE site_id = $1 AND nom = $2", site, z["nom"])
                if existante is None:
                    existante = await connexion.fetchval(
                        "INSERT INTO mark.resto_zone (site_id, nom, forme, communes, rayon_km, minimum, frais, delai, gratuite_des, ordre, couleur) "
                        "VALUES ($1, $2, $3, $4::text[], $5, $6, coalesce($7, 0), $8, $9, $10, $10 + 1) RETURNING id",
                        site, *valeurs,
                    )
                else:
                    await connexion.execute(
                        "UPDATE mark.resto_zone SET forme = $3, communes = $4::text[], rayon_km = $5, minimum = $6, frais = coalesce($7, frais), "
                        "delai = coalesce($8, delai), gratuite_des = $9, ordre = $10 WHERE site_id = $1 AND id = $2",
                        site, existante, *valeurs[1:],
                    )
                gardees.append(existante)
            await connexion.execute("DELETE FROM mark.resto_zone WHERE site_id = $1 AND id <> ALL($2::bigint[])", site, gardees)
        reservation = f.get("reservation") or {}
        if isinstance(reservation.get("capacite"), int):
            await connexion.execute(
                "INSERT INTO mark.resto_regle_reservation (site_id, couverts_simultanes) VALUES ($1, $2) "
                "ON CONFLICT (site_id) DO UPDATE SET couverts_simultanes = EXCLUDED.couverts_simultanes",
                site, reservation["capacite"],
            )
        if isinstance(reservation.get("duree_minutes"), int):
            await connexion.execute("DELETE FROM mark.resto_duree_groupe WHERE site_id = $1", site)
            await connexion.execute(
                "INSERT INTO mark.resto_duree_groupe (site_id, couverts_min, couverts_max, duree_minutes) VALUES ($1, 1, $2, $3)",
                site, max(1, int(reservation.get("capacite") or 1)), reservation["duree_minutes"],
            )
        if reservation.get("creneaux"):
            await connexion.execute("DELETE FROM mark.resto_service WHERE site_id = $1", site)
            for c in reservation["creneaux"]:
                await connexion.execute(
                    "INSERT INTO mark.resto_service (site_id, nom, jours, debut, fin, pas_minutes) VALUES ($1, $2, $3::smallint[], $4::text::time, $5::text::time, $6)",
                    site, c["nom"], list(c.get("jours") or range(1, 8)), c["debut"], c["fin"], int(c.get("pas_minutes") or 15),
                )
    bilan = None
    carte = f.get("carte")
    if isinstance(carte, Mapping) and isinstance(carte.get("produits"), list):
        bilan = await importer_carte(connexion, site, json.loads(json.dumps(carte)), "import")
        await _poser_les_synonymes_du_formulaire(connexion, site, carte, auteur)
    return {"etablissement_id": site, "carte": bilan}


async def _poser_les_synonymes_du_formulaire(connexion: asyncpg.Connection, site: int, carte: Mapping[str, Any], auteur: str) -> None:
    """Lot 19 (passe de mesure : « reine » introuvable sur Casa installée par le formulaire) : les synonymes qu'une personne a écrits dans la carte
    du formulaire (``synonymes`` d'un produit ou d'une option) sont la surcouche de l'établissement, actifs tout de suite comme au portail ; ils
    ne passent pas par l'import de la caisse (une surcouche, jamais écrasée par une carte)."""
    from api.db.bases_clients.restauration_ecran import poser_les_synonymes

    lignes = [*(carte.get("produits") or []), *(o for g in carte.get("groupes") or [] if isinstance(g, Mapping) for o in g.get("options") or [])]
    for ligne in lignes:
        ref = (ligne.get("ref") or ligne.get("id")) if isinstance(ligne, Mapping) else None  # le format commun nomme la référence « id »
        if not ref:
            continue
        dits = [str(x).strip() for x in ligne.get("synonymes") or [] if str(x).strip()][:10]
        if dits:
            await poser_les_synonymes(connexion, site, str(ref), dits, auteur)


async def faits_de_l_etablissement(connexion: asyncpg.Connection, etablissement_id: int) -> dict[str, bool]:
    """Ce que la base porte déjà pour l'établissement (une donnée B présente n'est jamais redemandée) : la carte et les horaires."""
    produits = await connexion.fetchval("SELECT count(*) FROM mark.resto_produit WHERE site_id = $1 AND NOT masque", etablissement_id)
    horaires = await connexion.fetchval("SELECT count(*) FROM mark.horaire WHERE site_id = $1", etablissement_id)
    return {"carte": bool(produits), "horaires": bool(horaires)}
