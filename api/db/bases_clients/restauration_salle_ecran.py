"""[.mark] Module Restauration, lot 13 (F6) : ce que l'onglet Salle du fork lit et écrit (plan de salle, créneaux, durées, règles, réservations à venir).

Même règle que le reste du module : seuls les fichiers ``restauration*.py`` ouvrent une requête sur les tables ``resto_*``. Ce fichier est le côté « écran » :
il ne décide rien que le comptoir ne décide déjà (la place d'une réservation est revérifiée par ``restauration_reservation.py``), il range, valide et journalise.

- le plan : des salles (``resto_salle``) et leurs tables (``resto_table``) ; la forme, la taille et les éléments de décor (bar, entrée) vivent dans la colonne
  ``plan`` de la salle (``{"elements": [...], "tables": {"<id>": {"forme", "l", "h"}}}``), le reste dans les colonnes de la table ;
- les créneaux (``resto_service``), les durées par taille de groupe (``resto_duree_groupe``) et les règles (``resto_regle_reservation``) ;
- les réservations du jour et à venir, avec le nom de leurs tables et leur heure locale ; le statut « arrivée » (``honoree``) ou « absente ».

L'auteur et la source vont au journal par ``poser_session`` (déclencheurs de la 028).
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from api.services.actions_communes.moyens_de_paiement import ABREGES
from api.services.actions_communes.euros import en_euros
from api.db.bases_clients.restauration_commun import fuseau_de, maintenant, poser_session, json_lu

GRILLE_COLONNES = 20
GRILLE_LIGNES = 12
MAX_SALLES = 12
MAX_TABLES_PAR_SALLE = 80
FORMES = ("ronde", "carree", "rectangle")
STATUTS_CHOISIS = ("confirmee", "honoree", "absente")


class PlanRefuse(ValueError):
    """Le plan demandé ne peut pas s'écrire : ``code`` fermé (``table_reservee``, ``table_inconnue``, ``salle_inconnue``)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code, self.detail = code, detail


def _hm(t) -> str:
    return t.strftime("%H:%M")


async def salle_pour_l_ecran(connexion: asyncpg.Connection, etablissement_id: int, jours: int) -> dict[str, Any]:
    """Tout ce que l'onglet Salle montre, d'une lecture : le plan, les créneaux, les durées, les règles et les réservations d'aujourd'hui à ``jours`` jours."""
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    maintenant_ = (await maintenant(connexion)).astimezone(fuseau)
    debut_jour = datetime(maintenant_.year, maintenant_.month, maintenant_.day, tzinfo=fuseau)
    fin = debut_jour + timedelta(days=jours + 1)
    salles = []
    tables = await connexion.fetch("SELECT * FROM mark.resto_table WHERE site_id = $1 ORDER BY id", etablissement_id)
    noms = {t["id"]: t["nom"] for t in tables}
    for s in await connexion.fetch("SELECT * FROM mark.resto_salle WHERE site_id = $1 ORDER BY ordre, id", etablissement_id):
        plan = json_lu(s["plan"]) or {}
        formes = plan.get("tables") or {}
        salles.append({
            "id": s["id"], "nom": s["nom"], "elements": list(plan.get("elements") or []),
            "tables": [
                {
                    "id": t["id"], "nom": t["nom"], "forme": (formes.get(str(t["id"])) or {}).get("forme", "carree"),
                    "x": float(t["x"] if t["x"] is not None else 0), "y": float(t["y"] if t["y"] is not None else 0),
                    "l": int((formes.get(str(t["id"])) or {}).get("l", 2)), "h": int((formes.get(str(t["id"])) or {}).get("h", 2)),
                    "couverts_min": t["couverts_min"], "couverts_max": t["couverts_max"], "assemblable_avec": list(t["assemblable_avec"]), "actif": t["actif"],
                }
                for t in tables if t["salle_id"] == s["id"]
            ],
        })
    services = [
        {"id": r["id"], "nom": r["nom"], "jours": sorted(r["jours"]), "debut": _hm(r["debut"]), "fin": _hm(r["fin"]), "pas_minutes": r["pas_minutes"]}
        for r in await connexion.fetch("SELECT * FROM mark.resto_service WHERE site_id = $1 ORDER BY debut, id", etablissement_id)
    ]
    durees = [
        {"id": r["id"], "couverts_min": r["couverts_min"], "couverts_max": r["couverts_max"], "duree_minutes": r["duree_minutes"]}
        for r in await connexion.fetch("SELECT * FROM mark.resto_duree_groupe WHERE site_id = $1 ORDER BY couverts_min, id", etablissement_id)
    ]
    r = await connexion.fetchrow("SELECT * FROM mark.resto_regle_reservation WHERE site_id = $1", etablissement_id)
    regles = {
        "delai_minimal": r["delai_minimal"] if r else 60, "jours_a_l_avance": r["jours_a_l_avance"] if r else 30,
        "couverts_max_groupe": r["couverts_max_groupe"] if r else None, "couverts_max_creneau": r["couverts_max_creneau"] if r else None,
    }
    reservations = []
    for x in await connexion.fetch(
        "SELECT * FROM mark.resto_reservation WHERE site_id = $1 AND statut <> 'annulee' AND debut >= $2 AND debut < $3 ORDER BY debut, id",
        etablissement_id, debut_jour, fin,
    ):
        local = x["debut"].astimezone(fuseau)
        reservations.append({
            "numero": str(x["numero"]), "jour": local.date().isoformat(), "debut_min": local.hour * 60 + local.minute, "duree_minutes": x["duree_minutes"],
            "couverts": x["couverts"], "prenom": x["prenom"], "telephone": x["telephone"], "note": x["note"], "table_ids": list(x["table_ids"]),
            "tables": [noms.get(i, str(i)) for i in x["table_ids"]], "statut": x["statut"], "cree_par": x["cree_par"],
        })
    return {
        "fuseau": str(fuseau), "aujourd_hui": maintenant_.date().isoformat(), "maintenant_min": maintenant_.hour * 60 + maintenant_.minute,
        "salles": salles, "services": services, "durees": durees, "regles": regles, "reservations": reservations,
    }


async def ecrire_le_plan(connexion: asyncpg.Connection, etablissement_id: int, salles: list[dict[str, Any]], auteur: str) -> None:
    """Remplace le plan par celui de l'écran (salles et tables, en une transaction). Une salle ou une table absente est retirée ; une table tenue par une
    réservation à venir ne se retire pas (``PlanRefuse('table_reservee')``). Les identifiants nouveaux de l'écran (``nouveau-…``) deviennent de vrais identifiants."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await connexion.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"resto_plan:{etablissement_id}")
        existantes = {r["id"] for r in await connexion.fetch("SELECT id FROM mark.resto_salle WHERE site_id = $1", etablissement_id)}
        tables_existantes = {r["id"] for r in await connexion.fetch("SELECT id FROM mark.resto_table WHERE site_id = $1", etablissement_id)}
        gardees_salles: set[int] = set()
        gardees_tables: set[int] = set()
        correspondance: dict[str, int] = {}
        assemblages: list[tuple[int, list[str]]] = []
        for ordre, s in enumerate(salles):
            sid = int(s["id"]) if str(s["id"]).isdigit() else None
            if sid is not None and sid not in existantes:
                raise PlanRefuse("salle_inconnue")
            plan: dict[str, Any] = {"elements": s["elements"], "tables": {}}
            if sid is None:
                sid = await connexion.fetchval(
                    "INSERT INTO mark.resto_salle (site_id, nom, ordre, plan) VALUES ($1, $2, $3, '{}'::jsonb) RETURNING id", etablissement_id, s["nom"], ordre
                )
            gardees_salles.add(sid)
            for t in s["tables"]:
                tid = int(t["id"]) if str(t["id"]).isdigit() else None
                if tid is not None and tid not in tables_existantes:
                    raise PlanRefuse("table_inconnue")
                if tid is None:
                    tid = await connexion.fetchval(
                        "INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_min, couverts_max, x, y) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
                        etablissement_id, sid, t["nom"], t["couverts_min"], t["couverts_max"], t["x"], t["y"],
                    )
                else:
                    await connexion.execute(
                        "UPDATE mark.resto_table SET salle_id = $3, nom = $4, couverts_min = $5, couverts_max = $6, x = $7, y = $8, actif = true, maj_le = $9 WHERE id = $1 AND site_id = $2",
                        tid, etablissement_id, sid, t["nom"], t["couverts_min"], t["couverts_max"], t["x"], t["y"], await maintenant(connexion),
                    )
                correspondance[str(t["id"])] = tid
                gardees_tables.add(tid)
                plan["tables"][str(tid)] = {"forme": t["forme"], "l": t["l"], "h": t["h"]}
                assemblages.append((tid, [str(a) for a in t["assemblable_avec"]]))
            await connexion.execute(
                "UPDATE mark.resto_salle SET nom = $3, ordre = $4, plan = $5::jsonb, maj_le = $6 WHERE id = $1 AND site_id = $2",
                sid, etablissement_id, s["nom"], ordre, json.dumps(plan), await maintenant(connexion),
            )
        for tid, autres in assemblages:
            liees = sorted({correspondance[a] for a in autres if a in correspondance and correspondance[a] != tid})
            await connexion.execute("UPDATE mark.resto_table SET assemblable_avec = $3::bigint[] WHERE id = $1 AND site_id = $2", tid, etablissement_id, liees)
        retirees = sorted(tables_existantes - gardees_tables)
        if retirees:
            tenue = await connexion.fetchval(
                "SELECT EXISTS (SELECT 1 FROM mark.resto_reservation WHERE site_id = $1 AND statut = 'confirmee' AND table_ids && $2::bigint[] "
                "AND debut + duree_minutes * interval '1 minute' > $3)",
                etablissement_id, retirees, await maintenant(connexion),
            )
            if tenue:
                raise PlanRefuse("table_reservee")
            await connexion.execute("DELETE FROM mark.resto_table WHERE site_id = $1 AND id = ANY($2::bigint[])", etablissement_id, retirees)
        sans = sorted(existantes - gardees_salles)
        if sans:
            await connexion.execute("DELETE FROM mark.resto_salle WHERE site_id = $1 AND id = ANY($2::bigint[])", etablissement_id, sans)


async def ecrire_des_tables(connexion: asyncpg.Connection, etablissement_id: int, tables: list[dict[str, Any]], auteur: str) -> list[int]:
    """Ajoute une liste de tables SANS position ni salle (le niveau 2 de la salle, lot 7). Une table exige une salle : la salle par défaut
    (la première, sinon « Salle » créée ici) les reçoit. Une seule salle par défaut, même rejouée ; rien d'existant n'est touché. Rend les identifiants."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await connexion.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"resto_plan:{etablissement_id}")
        salle_id = await connexion.fetchval("SELECT id FROM mark.resto_salle WHERE site_id = $1 ORDER BY ordre, id LIMIT 1", etablissement_id)
        if salle_id is None:
            salle_id = await connexion.fetchval(
                "INSERT INTO mark.resto_salle (site_id, nom, ordre, plan) VALUES ($1, 'Salle', 0, '{}'::jsonb) RETURNING id", etablissement_id
            )
        return [
            await connexion.fetchval(
                "INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_min, couverts_max) VALUES ($1, $2, $3, $4, $5) RETURNING id",
                etablissement_id, salle_id, t["nom"], t["couverts_min"], t["couverts_max"],
            )
            for t in tables
        ]


async def ecrire_les_creneaux(connexion: asyncpg.Connection, etablissement_id: int, changements: dict[str, Any], auteur: str) -> None:
    """Remplace les créneaux et les durées (quand ils sont donnés) et met à jour les règles (champs donnés seulement), en une transaction."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        services = changements.get("services")
        if services is not None:
            await connexion.execute("DELETE FROM mark.resto_service WHERE site_id = $1", etablissement_id)
            for s in services:
                await connexion.execute(
                    "INSERT INTO mark.resto_service (site_id, nom, jours, debut, fin, pas_minutes) VALUES ($1, $2, $3::smallint[], $4, $5, $6)",
                    etablissement_id, s["nom"], sorted(set(s["jours"])), time.fromisoformat(s["debut"]), time.fromisoformat(s["fin"]), s["pas_minutes"],
                )
        durees = changements.get("durees")
        if durees is not None:
            await connexion.execute("DELETE FROM mark.resto_duree_groupe WHERE site_id = $1", etablissement_id)
            for d in durees:
                await connexion.execute(
                    "INSERT INTO mark.resto_duree_groupe (site_id, couverts_min, couverts_max, duree_minutes) VALUES ($1, $2, $3, $4)",
                    etablissement_id, d["couverts_min"], d["couverts_max"], d["duree_minutes"],
                )
        regles = changements.get("regles")
        if regles:
            await connexion.execute("INSERT INTO mark.resto_regle_reservation (site_id) VALUES ($1) ON CONFLICT DO NOTHING", etablissement_id)
            sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(regles))
            await connexion.execute(f"UPDATE mark.resto_regle_reservation SET {sets} WHERE site_id = $1", etablissement_id, *regles.values())


async def poser_le_statut(connexion: asyncpg.Connection, etablissement_id: int, numero: str, statut: str, auteur: str) -> bool:
    """Marque une réservation arrivée (``honoree``), absente, ou la remet à confirmée. Une réservation annulée ne change plus. Faux : introuvable ou annulée."""
    if statut not in STATUTS_CHOISIS:
        raise ValueError(f"Statut hors liste : {statut!r}")
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        r = await connexion.execute(
            "UPDATE mark.resto_reservation SET statut = $3, maj_le = $4 WHERE numero = $1::uuid AND site_id = $2 AND statut <> 'annulee'",
            numero, etablissement_id, statut, await maintenant(connexion),
        )
    return r.endswith("1")


async def commandes_de_l_appel(connexion: asyncpg.Connection, etablissement_id: int, appel_id: str) -> list[dict[str, Any]]:
    """Les commandes de CET établissement prises dans cet appel (la plus ancienne d'abord ; plusieurs si l'une a été annulée puis refaite), avec leurs lignes :
    ce que le banc C compare à l'attendu. Lecture seule ; ``resto_commande`` et ``resto_commande_ligne``, jamais le panier en mémoire."""
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    lues = await connexion.fetch(
        "SELECT numero, numero_court, statut, mode, heure_voulue, heure_annoncee, adresse, consigne_livreur, paiement, note, sous_total, frais, total, telephone, prenom "
        "FROM mark.resto_commande WHERE site_id = $1 AND appel_id = $2 ORDER BY cree_le, numero", etablissement_id, appel_id,
    )
    lignes_par_commande: dict[Any, list[Any]] = {r["numero"]: [] for r in lues}
    if lues:  # toutes les lignes en UNE requête, jamais une par commande
        for l in await connexion.fetch(
            "SELECT numero, rang, code_caisse, nom, quantite, prix_unitaire, note, choix, retires, formule_ref FROM mark.resto_commande_ligne "
            "WHERE site_id = $1 AND numero = ANY($2::uuid[]) ORDER BY rang", etablissement_id, list(lignes_par_commande),
        ):
            lignes_par_commande[l["numero"]].append(l)
    commandes = []
    for r in lues:
        lignes = lignes_par_commande[r["numero"]]
        commandes.append({
            "numero": str(r["numero"]), "numero_court": r["numero_court"], "statut": r["statut"], "mode": r["mode"],
            "heure_voulue": r["heure_voulue"].astimezone(fuseau).isoformat() if r["heure_voulue"] else None,
            "heure_annoncee": r["heure_annoncee"].astimezone(fuseau).isoformat() if r["heure_annoncee"] else None,
            "adresse": json_lu(r["adresse"]), "consigne_livreur": r["consigne_livreur"], "paiement": json_lu(r["paiement"]) or {}, "note": r["note"],
            "sous_total": r["sous_total"], "frais": r["frais"], "total": r["total"], "telephone": r["telephone"], "prenom": r["prenom"],
            "lignes": [
                {"rang": l["rang"], "code_caisse": l["code_caisse"], "nom": l["nom"], "quantite": l["quantite"], "prix_unitaire": l["prix_unitaire"], "note": l["note"],
                 "choix": json_lu(l["choix"]) or [], "retires": list(l["retires"] or []), "formule_ref": l["formule_ref"]}
                for l in lignes
            ],
        })
    return commandes


def texte_du_paiement(paiement: dict[str, Any] | None) -> str | None:
    """Le règlement noté sur la commande, comme le ticket le dit : « CB 27,50 € », « TR 20,00 € + ESP 4,50 € (rendre sur 50,00 €) » ; ``None`` tant que rien n'est noté."""
    moyens = (paiement or {}).get("moyens") or []
    if not moyens:
        return None
    ligne = " + ".join(f"{ABREGES.get(m['moyen'], str(m['moyen']).upper())} {en_euros(m['montant'])}" for m in moyens)
    rendu = (paiement or {}).get("rendu_sur")
    return ligne + (f" (rendre sur {en_euros(rendu)})" if isinstance(rendu, int) and rendu > 0 else "")


async def dernieres_commandes(connexion: asyncpg.Connection, etablissement_id: int, limite: int) -> list[dict[str, Any]]:
    """Les dernières commandes de l'établissement (celles que la fiche de la caisse montre) : numéro court, heure locale, total, statut, référence chez la caisse."""
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    return [
        {
            "numero": str(r["numero"]), "numero_court": r["numero_court"], "mode": r["mode"], "statut": r["statut"], "total": r["total"],
            "ref_caisse": r["ref_fournisseur"], "le": r["cree_le"].astimezone(fuseau).strftime("%d/%m %H:%M"), "paiement": texte_du_paiement(json_lu(r["paiement"])),
        }
        for r in await connexion.fetch(
            "SELECT numero, numero_court, mode, statut, total, ref_fournisseur, cree_le, paiement FROM mark.resto_commande WHERE site_id = $1 ORDER BY cree_le DESC, numero LIMIT $2",
            etablissement_id, limite,
        )
    ]
