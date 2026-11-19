"""[.mark] Module Restauration, lot 2 : la carte, les ruptures, l'état d'ouverture (contrat § 4).

``carte_du_restaurant``, ``version_carte``, ``ruptures_du_restaurant``, ``etat_caisse``, ``etat_combine``,
``importer_carte``, ``poser_rupture``. Montants en centimes. Allergènes : ``None`` = inconnu, ``[]`` = aucun.
Tout filtre par établissement est DANS la requête ; toute référence est relue avec l'établissement de l'appelant.
Aucun mot de restaurant dans la logique de disponibilité et d'heure : elle lit des jours, des heures, des dates.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients.horaires_caisse import horaires_du_classeur
from api.db.bases_clients.instantane import instantane_de, stable, vivant
from api.db.bases_clients.plages import dans_la_plage
from api.db.bases_clients.plages import heure as _heure
from api.db.bases_clients.restauration_commun import (
    SOURCES,
    TYPES,
    EtablissementInconnu,
    Resultat,
    fuseau_de,
    maintenant,
    minutes_recurrentes,
    poser_session,
)
from api.db.bases_clients.recherche_liste_numero import cle_ecrite
from api.db.bases_clients.restauration_reglage import reglages_du_module

FORMAT_CARTE = "mark-carte-commune/1"


class CarteInvalide(ValueError):
    """Le fichier de carte n'est pas au format commun : rien n'a été écrit."""


# --------------------------------------------------------------------------- #
# Disponibilité : des jours, des heures, des dates (aucune notion de métier)
# --------------------------------------------------------------------------- #


def disponible_a(disponibilite: dict | None, local: datetime) -> bool:
    """Une plage de jours, d'heures et de dates (``plages.py``) ; ``local`` : l'heure dans le fuseau de l'établissement."""
    return dans_la_plage(disponibilite, local)


def accord_du_produit(produit: dict) -> tuple[str, bool]:
    """``(genre, nom_commun)`` d'un produit d'après sa surcouche (lot 8, E17) : ``("m", False)`` quand la personne ne l'a pas dit (« un », jamais
    deviné d'après un mot écrit dans le code)."""
    return produit.get("genre") or "m", bool(produit.get("nom_commun"))


def _json(valeur: Any) -> Any:
    return json.loads(valeur) if isinstance(valeur, str) else valeur


# --------------------------------------------------------------------------- #
# Lecture
# --------------------------------------------------------------------------- #


def _fusion(lignes) -> dict[str, asyncpg.Record]:
    """Par ``ref`` : la ligne de l'établissement (propre ou exception) remplace celle de l'enseigne ; masquée, elle disparaît."""
    retenues: dict[str, asyncpg.Record] = {}
    for ligne in sorted(lignes, key=lambda r: r["site_id"] is not None):  # l'enseigne d'abord
        retenues[ligne["ref"]] = ligne
    return {ref: l for ref, l in retenues.items() if not l["masque"]}


async def version_carte(connexion: asyncpg.Connection, etablissement_id: int) -> int:
    """Le numéro de version de la carte, augmenté par déclencheur à tout changement, toute source (D10). 0 : aucune carte. Pendant un appel :
    la version de la carte chargée au décroché (lot 5, D61 point 3 : la carte de l'appel ne change pas en route)."""
    inst = instantane_de(connexion)
    if inst is not None and ("tables_de_la_carte", etablissement_id) in inst.stables:
        return inst.stables[("tables_de_la_carte", etablissement_id)]["version"]
    return await connexion.fetchval("SELECT version FROM mark.resto_version_carte WHERE site_id = $1", etablissement_id) or 0


async def carte_du_restaurant(connexion: asyncpg.Connection, etablissement_id: int, moment: datetime | None = None) -> dict:
    """La carte complète au moment donné (disponibilité des déclinaisons), exceptions de l'établissement appliquées sur la
    carte d'enseigne, + ``version``. Lue d'un seul tenant : la version rendue n'est jamais plus récente que les lignes."""
    if moment is None:
        moment = await maintenant(connexion)
    local = moment.astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id)))
    tables = await stable(connexion, ("tables_de_la_carte", etablissement_id), lambda: _lire_les_tables_de_la_carte(connexion, etablissement_id))
    inst = instantane_de(connexion)
    if inst is None:
        return _assembler_la_carte(tables, moment, local)
    # Lot 5 : pendant un appel, la carte assemblée est gardée pour la minute (la disponibilité se lit à la minute) : aucun calcul refait par geste
    cle = ("carte_assemblee", etablissement_id, local.replace(second=0, microsecond=0))
    if cle not in inst.stables:
        inst.stables = {k: v for k, v in inst.stables.items() if not (isinstance(k, tuple) and k[:2] == cle[:2])}
        inst.stables[cle] = _assembler_la_carte(tables, moment, local)
    return inst.stables[cle]


async def _lire_les_tables_de_la_carte(connexion: asyncpg.Connection, etablissement_id: int) -> dict[str, Any]:
    """Les lignes de la carte, d'un seul tenant (la version rendue n'est jamais plus récente que les lignes) : huit requêtes, une par table."""
    async with connexion.transaction(isolation="repeatable_read", readonly=True):
        version = await connexion.fetchval("SELECT version FROM mark.resto_version_carte WHERE site_id = $1", etablissement_id) or 0
        pos = "WHERE site_id IS NULL OR site_id = $1"
        categories = _fusion(await connexion.fetch(f"SELECT * FROM mark.resto_categorie {pos}", etablissement_id))
        produits = _fusion(await connexion.fetch(f"SELECT * FROM mark.resto_produit {pos}", etablissement_id))
        declinaisons = _fusion(await connexion.fetch(f"SELECT * FROM mark.resto_declinaison {pos}", etablissement_id))
        groupes = _fusion(await connexion.fetch(f"SELECT * FROM mark.resto_groupe_choix {pos}", etablissement_id))
        options = _fusion(await connexion.fetch(f"SELECT * FROM mark.resto_option {pos}", etablissement_id))
        formules = _fusion(await connexion.fetch(f"SELECT * FROM mark.resto_formule {pos}", etablissement_id))
        surcouches = {
            (s["objet"], s["ref"]): s
            for s in sorted(
                await connexion.fetch(f"SELECT * FROM mark.resto_surcouche {pos}", etablissement_id),
                key=lambda r: r["site_id"] is not None,
            )
        }
    return {"version": version, "categories": categories, "produits": produits, "declinaisons": declinaisons, "groupes": groupes,
            "options": options, "formules": formules, "surcouches": surcouches}


def _assembler_la_carte(tables: dict[str, Any], moment: datetime, local: datetime) -> dict:
    """La carte au moment donné, depuis ses lignes : la disponibilité des déclinaisons et des formules lue à ``local``."""
    version, categories, produits, declinaisons = tables["version"], tables["categories"], tables["produits"], tables["declinaisons"]
    groupes, options, formules, surcouches = tables["groupes"], tables["options"], tables["formules"], tables["surcouches"]

    def surcouche(objet: str, ref: str) -> dict:
        s = surcouches.get((objet, ref))
        if s is None:
            return {"synonymes": [], "synonymes_a_relire": [], "etoile": False, "lexique": [], "phrase": None, "alcool": False,
                    "genre": None, "nom_commun": None, "du_moment": False, "texte_du_jour": None}
        # Un synonyme proposé à l'import ne sert qu'après relecture (T-14).
        a_relire = list(s["synonymes"]) if s["synonymes_a_relire"] else []
        return {
            "synonymes": [] if s["synonymes_a_relire"] else list(s["synonymes"]),
            "synonymes_a_relire": a_relire,
            "etoile": s["etoile"],
            "lexique": list(s["lexique"]),
            "phrase": s["phrase"],
            "alcool": bool(dict(s).get("alcool")),
            # Lot 8 : ce qu'une personne écrit sur le produit (accord de ce que l'agent dit, plat du jour) ; ``None`` = non dit, jamais deviné
            "genre": dict(s).get("genre"), "nom_commun": dict(s).get("nom_commun"),
            "du_moment": bool(dict(s).get("du_moment")), "texte_du_jour": dict(s).get("texte_du_jour"),
        }

    options_par_groupe: dict[str, list] = {}
    for o in sorted(options.values(), key=lambda r: (r["ordre"], r["id"])):
        options_par_groupe.setdefault(o["groupe_ref"], []).append(
            {
                "id": o["ref"], "groupe_id": o["groupe_ref"], "nom": o["nom"], "code_caisse": o["code_caisse"],
                "prix": o["prix"], "par_defaut": o["par_defaut"], "retirable": o["retirable"],
                # Lot 10 (RET2, RET5) : le prix de l'option par déclinaison de la ligne, le prix de son retrait ; ``None`` = non dit
                "prix_par_declinaison": _json(o["prix_par_declinaison"]), "prix_retrait": o["prix_retrait"],
                "vendable": bool(o["code_caisse"]),
                "synonymes": surcouche("option", o["ref"])["synonymes"],  # SA-52 : une option se cherche aussi par ses synonymes
            }
        )
    declinaisons_par_produit: dict[str, list] = {}
    for d in sorted(declinaisons.values(), key=lambda r: (r["ordre"], r["id"])):
        dispo = _json(d["disponibilite"])
        if not disponible_a(dispo, local):
            continue
        declinaisons_par_produit.setdefault(d["produit_ref"], []).append(
            {
                "id": d["ref"], "produit_id": d["produit_ref"], "nom": d["nom"], "code_caisse": d["code_caisse"],
                "prix": d["prix"], "prix_par_mode": _json(d["prix_par_mode"]), "disponibilite": dispo,
                "vendable": bool(d["code_caisse"]),
                # Lot 8 (DEC1 à DEC5) : ce que la déclinaison distingue, le mot de sa question, les quotas qu'elle fixe par groupe ; ``None`` = non dit
                "type": d["type"], "libelle_question": d["libelle_question"], "quotas": _json(d["quotas"]),
            }
        )
    total_declinaisons: dict[str, int] = {}
    for d in declinaisons.values():
        total_declinaisons[d["produit_ref"]] = total_declinaisons.get(d["produit_ref"], 0) + 1

    carte_produits = []
    for p in sorted(produits.values(), key=lambda r: (r["ordre"], r["id"])):
        decl = declinaisons_par_produit.get(p["ref"], [])
        if total_declinaisons.get(p["ref"]) and not decl:
            continue  # toutes ses déclinaisons sont hors de leur plage à ce moment : le produit n'est pas à la carte
        ingredients, allergenes, source, maj_le = _json(p["ingredients"]), p["allergenes"], p["source"], p["maj_le"]
        ecrit = dict(surcouches.get(("produit", p["ref"])) or {})
        # Ce qu'une personne a écrit sur la carte d'une caisse (surcouche) passe devant le fichier ; None = inconnu et [] = aucun restent distincts.
        if ecrit.get("ingredients") is not None:
            ingredients = _json(ecrit["ingredients"])
        if ecrit.get("allergenes_ecrits"):
            allergenes = ecrit["allergenes"]
        if (ecrit.get("ingredients") is not None or ecrit.get("allergenes_ecrits")) and ecrit.get("produit_source"):
            source, maj_le = ecrit["produit_source"], ecrit["produit_maj_le"] or maj_le
        carte_produits.append(
            {
                "id": p["ref"], "nom": p["nom"], "description": p["description"], "categorie_id": p["categorie_ref"], "numero": p["numero"],
                "ingredients": ingredients,
                "allergenes": None if allergenes is None else list(allergenes),
                "origine": p["origine"], "tva_par_mode": _json(p["tva_par_mode"]),
                "declinaisons": decl, "groupes": list(p["groupes_refs"]),
                "source": source, "maj_le": maj_le, **surcouche("produit", p["ref"]),
            }
        )
    return {
        "version": version,
        "moment": moment,
        "categories": [
            {"id": c["ref"], "nom": c["nom"], "parent_id": c["parent_ref"], "ordre": c["ordre"], "portee": c["portee"], "role": c["role"],
             "inclus": list(c.get("inclus") or []),  # lot 11 (FOR13) : ce qui est servi avec chaque produit de la rubrique
             **surcouche("categorie", c["ref"])}
            for c in sorted(categories.values(), key=lambda r: (r["ordre"], r["id"]))
        ],
        "produits": carte_produits,
        "groupes": [
            {"id": g["ref"], "nom": g["nom"], "min": g["min"], "max": g["max"], "max_par_option": g["max_par_option"],
             "defaut": list(g["defaut_refs"]), "parent_option_id": g["parent_option_ref"], "role": g["role"],
             # Lot 9 (OPT3, OPT6) : le nombre d'éléments compris, le prix de chacun au-delà, l'option qui fait apparaître le groupe ; ``None`` = non dit
             "inclus": g["inclus"], "prix_au_dela": g["prix_au_dela"], "si_option": g["si_option"],
             "options": options_par_groupe.get(g["ref"], [])}
            for g in sorted(groupes.values(), key=lambda r: (r["ordre"], r["id"]))
        ],
        "formules": [
            {"id": f["ref"], "nom": f["nom"], "code_caisse": f["code_caisse"], "prix": f["prix"],
             "categorie_id": f["categorie_ref"], "numero": f["numero"], "lignes": _json(f["lignes"]), "supplement": f["supplement"], "disponibilite": _json(f["disponibilite"]),
             "vendable": bool(f["code_caisse"]),
             # Lot 11 (FOR6, FOR7, FOR9, FOR10, FOR11) : ``None`` = non dit (jamais deviné)
             "modes": list(f["modes"]) if f.get("modes") is not None else None, "age_max": f.get("age_max"), "public": f.get("public"),
             "personnes": _json(f.get("personnes")), "tailles": _json(f.get("tailles")), "par_lot": bool(f.get("par_lot"))}
            for f in sorted(formules.values(), key=lambda r: r["id"])
            if disponible_a(_json(f["disponibilite"]), local)
        ],
    }


def _rupture(r: asyncpg.Record) -> dict:
    return {
        "code_caisse": r["code_caisse"], "disponible": r["disponible"], "stock": r["stock"], "debut": r["debut"],
        "fin": r["fin"], "source": r["source"], "maj_le": r["maj_le"],
    }


async def ruptures_du_restaurant(
    connexion: asyncpg.Connection, etablissement_id: int, moment: datetime | None = None, *, relire: bool = False
) -> list[dict]:
    """Les ruptures ACTIVES au moment donné : commencées, pas finies, produit ou option indisponible (ou stock nul).
    Une rupture qui ne couvre pas le jour d'une commande planifiée ne la bloque pas. Pendant un appel (lot 5) : celles connues au chargement ;
    ``relire`` : lues à la base maintenant (l'enregistrement, qui refuse une rupture posée pendant l'appel)."""
    if moment is None:
        moment = await maintenant(connexion)
    if relire or instantane_de(connexion) is None:
        lignes = await connexion.fetch(
            "SELECT * FROM mark.resto_rupture WHERE site_id = $1 AND debut <= $2 AND (fin IS NULL OR fin > $2) "
            "AND (NOT disponible OR stock = 0) ORDER BY code_caisse",
            etablissement_id,
            moment,
        )
        return [_rupture(r) for r in lignes]

    async def lire() -> list:
        return list(await connexion.fetch(
            "SELECT * FROM mark.resto_rupture WHERE site_id = $1 AND (NOT disponible OR stock = 0) ORDER BY code_caisse", etablissement_id
        ))

    connues = await stable(connexion, ("ruptures", etablissement_id), lire)
    return [_rupture(r) for r in connues if r["debut"] <= moment and (r["fin"] is None or r["fin"] > moment)]


async def etat_caisse(connexion: asyncpg.Connection, etablissement_id: int) -> dict | None:
    """L'état que la caisse porte, ou ``None`` : aucune caisse ne le porte (la fiche et le portail font foi)."""
    r = (await vivant(connexion, etablissement_id, await maintenant(connexion))).caisse  # lot 5 : l'état vivant, une requête par geste
    if r is None:
        return None
    return {
        "mode": r["mode"], "minutes_en_plus": r["minutes_en_plus"], "reprise": r["reprise"], "motif": r["motif"],
        "temps_preparation": r["temps_preparation"], "horaires": _json(r["horaires"]), "fuseau": r["fuseau"],
        "source": r["source"], "maj_le": r["maj_le"],
    }


# --------------------------------------------------------------------------- #
# L'état combiné : fiche de l'établissement + caisse + réglages par type ; le plus prudent gagne
# --------------------------------------------------------------------------- #

# Du plus au moins parlant, quand plusieurs causes ferment en même temps.
_PRIORITE_RAISONS = (
    "etablissement_inactif", "ferme_force", "caisse_pause", "fermeture_exceptionnelle", "ferme_horaires",
    "type_ferme", "pause_type", "pause_force", "fin_du_jour", "livraison_terminee", "sur_rendez_vous",
)


def _local_naif(naif: datetime, fuseau: ZoneInfo) -> datetime:
    return naif.replace(tzinfo=fuseau)


def _prochaine_ouverture(horaires, apres: datetime, fuseau: ZoneInfo) -> datetime | None:
    """La première ouverture régulière à partir de ``apres`` dans les 8 jours (heure du fuseau), ou ``None``."""
    local = apres.astimezone(fuseau)
    for decalage in range(0, 9):
        jour = local.date() + timedelta(days=decalage)
        for h in sorted((h for h in horaires if h["jour"] == jour.isoweekday()), key=lambda h: h["ouverture"]):
            debut = datetime.combine(jour, h["ouverture"], tzinfo=fuseau)
            if debut > apres:
                return debut
    return None


async def etat_combine(connexion: asyncpg.Connection, etablissement_id: int, type_: str, moment: datetime) -> dict:
    """``{ouvert, raison, reprise, delai_minutes, prochaine_ouverture}`` pour un type (emporter, livraison, sur_place,
    reservation). Le plus prudent gagne ; la caisse prime pour ce qu'elle porte (E-49). ``delai_minutes`` : le délai
    annoncé du type (la caisse si elle le porte) + les minutes ajoutées ; pour la livraison, le délai de la ZONE s'y
    ajoute chez l'appelant (E-42)."""
    if type_ not in TYPES:
        raise ValueError(f"Type inconnu : {type_!r}")
    if moment.tzinfo is None:
        raise ValueError("Le moment doit être aware.")
    # Lot 5 (E23) : ce qui peut changer pendant l'appel (forçage, fermeture exceptionnelle, réglage du type, caisse) en UNE requête par geste ;
    # le reste (fuseau, horaires de la fiche, réglages du module, soirs chargés) lu une fois par appel.
    etat_vivant = await vivant(connexion, etablissement_id, moment)
    site = etat_vivant.site
    if site is None:
        raise EtablissementInconnu(etablissement_id)
    fuseau = ZoneInfo(site["fuseau"])
    local = moment.astimezone(fuseau)
    horaires = await horaires_du_classeur(connexion, etablissement_id)  # M57 : ceux de la caisse quand elle est branchée et fait foi (E-49), sinon ceux du classeur
    fermetures = [f for f in etat_vivant.fermetures if f["du"] <= moment < f["au"]]
    reglage = etat_vivant.types.get(type_)
    module = await reglages_du_module(connexion, etablissement_id)
    # F4 : un état tenu ici ne lit plus celui de la caisse (ni sa pause, ni son temps de préparation).
    caisse = None if module["sources"].get("etat") == "ici" else await etat_caisse(connexion, etablissement_id)

    fermes: dict[str, datetime | None] = {}  # raison -> reprise connue
    force = site["etat_force"]
    fin_force = _local_naif(site["etat_force_jusqu_a"], fuseau) if site["etat_force_jusqu_a"] else None
    force_actif = force is not None and (fin_force is None or fin_force > moment)
    if not site["actif"]:
        fermes["etablissement_inactif"] = None
    if force_actif and force == "FERME":
        fermes["ferme_force"] = fin_force
    elif force_actif and force == "PAUSE":
        fermes["pause_force"] = fin_force
    elif force_actif and force == "SUR_RENDEZ_VOUS":
        fermes["sur_rendez_vous"] = fin_force
    ouvert_force = force_actif and force == "OUVERT"
    for f in fermetures:
        fermes["fermeture_exceptionnelle"] = f["au"]
    # Des horaires connus ferment hors plage ; sans horaire écrit, l'établissement n'est pas fermé par les horaires.
    if horaires and not ouvert_force and not any(
        h["jour"] == local.isoweekday() and h["ouverture"] <= local.time() < h["fermeture"] for h in horaires
    ):
        fermes["ferme_horaires"] = None
    if reglage is not None:
        if not reglage["ouvert"]:
            fermes["type_ferme"] = None
        if reglage["pause_jusqu_a"] and reglage["pause_jusqu_a"] > moment:
            fermes["pause_type"] = reglage["pause_jusqu_a"]
        fin_jour = _json(reglage["fin_par_jour"]).get(str(local.isoweekday()))
        if fin_jour and local.time() >= _heure(fin_jour):
            fermes["livraison_terminee" if type_ == "livraison" else "fin_du_jour"] = None
    # T-05 : la pause de la caisse met aussi le téléphone en pause, sauf si le restaurant a décoché « mettre le téléphone en pause avec la caisse ».
    if module["pause_caisse_pause_telephone"] and caisse is not None and caisse["mode"] == "pause" and (caisse["reprise"] is None or caisse["reprise"] > moment):
        fermes["caisse_pause"] = caisse["reprise"]

    delai = 0
    if reglage is not None and reglage["delai_annonce"] is not None and type_ != "livraison":
        delai = reglage["delai_annonce"]
    if caisse is not None and caisse["temps_preparation"] is not None and type_ not in ("livraison", "reservation"):
        delai = caisse["temps_preparation"]  # la caisse prime pour ce qu'elle porte
    if reglage is not None and reglage["minutes_ajoutees"] and (reglage["ajout_jusqu_a"] is None or reglage["ajout_jusqu_a"] > moment):
        delai += reglage["minutes_ajoutees"]
    if caisse is not None and caisse["mode"] == "deborde" and (caisse["reprise"] is None or caisse["reprise"] > moment):
        delai += caisse["minutes_en_plus"]
    if type_ not in ("reservation",):
        delai += await minutes_recurrentes(connexion, etablissement_id, type_, moment)  # un soir toujours chargé (lot 12)

    if not fermes:
        return {"ouvert": True, "raison": None, "reprise": None, "delai_minutes": delai, "prochaine_ouverture": None}
    raison = next(r for r in _PRIORITE_RAISONS if r in fermes)
    reprises = list(fermes.values())
    reprise = None if any(r is None for r in reprises) else max(reprises)
    base = max(moment, reprise) if reprise else moment
    return {
        "ouvert": False, "raison": raison, "reprise": reprise, "delai_minutes": delai,
        "prochaine_ouverture": _prochaine_ouverture(horaires, base, fuseau) if horaires else None,
    }


# --------------------------------------------------------------------------- #
# Écriture : poser une rupture, importer une carte
# --------------------------------------------------------------------------- #


async def poser_rupture(
    connexion: asyncpg.Connection, etablissement_id: int, code_caisse: str, disponible: bool, fin: datetime | None, source: str
) -> Resultat:
    """Pose (ou lève) une rupture sur un code de caisse de CET établissement. Toujours possible, même quand la caisse
    est maître (E-44). Un code inconnu ici : ``INTROUVABLE`` ; une fin passée : ``ARGUMENT_INVALIDE``."""
    if source not in SOURCES or not isinstance(code_caisse, str) or not code_caisse.strip():
        return Resultat("ARGUMENT_INVALIDE", manque="code_caisse")
    maintenant_ = await maintenant(connexion)
    if fin is not None and (fin.tzinfo is None or fin <= maintenant_):
        return Resultat("ARGUMENT_INVALIDE", manque="fin")
    connu = await connexion.fetchval(
        "SELECT EXISTS (SELECT 1 FROM mark.resto_declinaison WHERE (site_id IS NULL OR site_id = $1) AND code_caisse = $2) "
        "OR EXISTS (SELECT 1 FROM mark.resto_option WHERE (site_id IS NULL OR site_id = $1) AND code_caisse = $2) "
        "OR EXISTS (SELECT 1 FROM mark.resto_formule WHERE (site_id IS NULL OR site_id = $1) AND code_caisse = $2)",
        etablissement_id,
        code_caisse,
    )
    if not connu:
        return Resultat("INTROUVABLE", {"code_caisse": code_caisse}, "Ce produit n'est pas dans la carte.")
    async with connexion.transaction():
        await poser_session(connexion, source, f"rupture:{source}")
        await connexion.execute(
            "INSERT INTO mark.resto_rupture (site_id, code_caisse, disponible, debut, fin, source, maj_le) "
            "VALUES ($1, $2, $3, $4, $5, $6, $4) "
            "ON CONFLICT (site_id, code_caisse) DO UPDATE SET disponible = EXCLUDED.disponible, debut = EXCLUDED.debut, "
            "fin = EXCLUDED.fin, source = EXCLUDED.source, maj_le = EXCLUDED.maj_le",
            etablissement_id, code_caisse, disponible, maintenant_, fin, source,
        )
    return Resultat("OK", {"code_caisse": code_caisse, "disponible": disponible, "fin": fin})


# Les colonnes écrites par l'import, table par table : (colonnes simples, colonnes jsonb, colonnes de listes).
_TABLES = {
    "resto_categorie": (("portee", "nom", "parent_ref", "ordre", "role"), (), ("inclus",)),
    "resto_produit": (("portee", "nom", "description", "categorie_ref", "origine", "ordre", "numero"), ("ingredients", "tva_par_mode"), ("allergenes", "groupes_refs")),
    "resto_declinaison": (("portee", "produit_ref", "nom", "code_caisse", "prix", "ordre", "type", "libelle_question"), ("prix_par_mode", "disponibilite", "quotas"), ()),
    "resto_groupe_choix": (("portee", "nom", "min", "max", "max_par_option", "parent_option_ref", "role", "ordre", "inclus", "prix_au_dela", "si_option"), (), ("defaut_refs",)),
    "resto_option": (("portee", "groupe_ref", "nom", "code_caisse", "prix", "par_defaut", "retirable", "ordre", "prix_retrait"), ("prix_par_declinaison",), ()),
    # Lot 11 (FOR6, FOR7, FOR9, FOR10, FOR11) : modes, âge, public, personnes, tailles, lot ; les clés des lignes vivent dans ``lignes``.
    "resto_formule": (("portee", "nom", "code_caisse", "prix", "categorie_ref", "supplement", "numero", "age_max", "public", "par_lot"),
                      ("lignes", "disponibilite", "personnes", "tailles"), ("modes",)),
}


def _numero(valeur: Any, ref: Any) -> str | None:
    """Le numéro de carte facultatif d'un produit ou d'une formule (C2) : un texte lisible (« 46 », « J24 », « 16b »), sinon la carte est refusée."""
    if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
        return None
    if not isinstance(valeur, (str, int)) or isinstance(valeur, bool) or cle_ecrite(str(valeur)) is None:
        raise CarteInvalide(f"Numéro illisible pour {ref} : {valeur!r} (attendu : des chiffres, avec au plus deux lettres devant et une lettre derrière).")
    return str(valeur).strip()


# Lot 11 : les clés d'une ligne de formule et leur type (une clé inconnue est gardée telle quelle, une clé connue de mauvais type refuse la carte).
_CLES_DE_LIGNE = {
    "quantite": int, "obligatoire": bool, "inclus": list, "exclus": list, "prix_max": int, "supplements": dict, "alternatives": list, "a_volonte": bool,
}


def _lignes_de_formule_lisibles(f: dict) -> None:
    """Les lignes d'une formule (FOR2 à FOR15) : chaque clé connue a son type, sinon la carte est refusée (jamais deviné)."""
    for ligne in f.get("lignes") or []:
        for cle, type_ in _CLES_DE_LIGNE.items():
            valeur = ligne.get(cle)
            if valeur is not None and (not isinstance(valeur, type_) or (type_ is int and isinstance(valeur, bool))):
                raise CarteInvalide(f"Formule {f.get('id')} : la ligne {ligne.get('nom')!r} a {cle} illisible ({valeur!r}).")


def _lignes_de_la_carte(carte: dict) -> dict[str, dict[str, dict]]:
    """Le format commun, aplati par table : ``{table: {ref: colonnes}}``."""
    if not isinstance(carte, dict) or carte.get("format") != FORMAT_CARTE:
        raise CarteInvalide(f"Format attendu : {FORMAT_CARTE}")
    sortie: dict[str, dict[str, dict]] = {t: {} for t in _TABLES}

    def poser(table: str, ref: Any, colonnes: dict) -> None:
        if not isinstance(ref, str) or not ref.strip():
            raise CarteInvalide(f"Un objet de {table} n'a pas d'identifiant.")
        if ref in sortie[table]:
            raise CarteInvalide(f"Identifiant en double dans {table} : {ref}")
        colonnes.setdefault("portee", "etablissement")
        sortie[table][ref] = colonnes

    def portee(valeur: str | None) -> str:
        # La carte d'enseigne n'existe que si elle est déclarée à la main : un import écrit pour l'établissement.
        return "exception" if valeur == "exception" else "etablissement"

    for i, c in enumerate(carte.get("categories", [])):
        poser("resto_categorie", c.get("id"), {"nom": c["nom"], "parent_ref": c.get("parent_id"), "ordre": c.get("ordre", i), "portee": portee(c.get("portee")), "role": c.get("role"),
                                                "inclus": [str(x) for x in c.get("inclus") or []]})
    for i, p in enumerate(carte.get("produits", [])):
        tva = p.get("tva_par_mode") or {}
        poser(
            "resto_produit", p.get("id"),
            {"nom": p["nom"], "description": p.get("description"), "categorie_ref": p.get("categorie_id"), "origine": p.get("origine"),
             "ordre": i, "numero": _numero(p.get("numero"), p.get("id")), "ingredients": p.get("ingredients") or [], "tva_par_mode": tva, "portee": portee(p.get("portee")),
             "allergenes": p.get("allergenes"), "groupes_refs": list(p.get("groupes") or [])},
        )
        for j, d in enumerate(p.get("declinaisons") or []):
            poser(
                "resto_declinaison", d.get("id"),
                {"produit_ref": p["id"], "nom": d["nom"], "code_caisse": (d.get("code_caisse") or None), "prix": int(d["prix"]), "ordre": j, "portee": portee(d.get("portee") or p.get("portee")),
                 "prix_par_mode": d.get("prix_par_mode"), "disponibilite": d.get("disponibilite"),
                 "type": d.get("type"), "libelle_question": d.get("libelle_question") or None, "quotas": d.get("quotas")},
            )
    for i, g in enumerate(carte.get("groupes", [])):
        poser(
            "resto_groupe_choix", g.get("id"),
            {"nom": g["nom"], "min": g.get("min", 0), "max": g.get("max", 1), "max_par_option": g.get("max_par_option", 1),
             "parent_option_ref": g.get("parent_option_id"), "role": g.get("role", "choix"), "ordre": i, "portee": portee(g.get("portee")),
             "defaut_refs": list(g.get("defaut") or []), "inclus": g.get("inclus"), "prix_au_dela": g.get("prix_au_dela"), "si_option": g.get("si_option") or None},
        )
        for j, o in enumerate(g.get("options") or []):
            poser(
                "resto_option", o.get("id"),
                {"groupe_ref": g["id"], "nom": o["nom"], "code_caisse": (o.get("code_caisse") or None), "prix": int(o.get("prix", 0)),
                 "par_defaut": bool(o.get("par_defaut", False)), "retirable": bool(o.get("retirable", False)), "ordre": j,
                 "prix_retrait": o.get("prix_retrait"), "prix_par_declinaison": o.get("prix_par_declinaison"),
                 "portee": portee(o.get("portee") or g.get("portee"))},
            )
    for f in carte.get("formules", []):
        poser(
            "resto_formule", f.get("id"),
            {"nom": f["nom"], "code_caisse": (f.get("code_caisse") or None), "prix": int(f["prix"]),
             "categorie_ref": f.get("categorie_id"), "supplement": f.get("supplement"), "numero": _numero(f.get("numero"), f.get("id")), "lignes": f.get("lignes") or [], "portee": portee(f.get("portee")),
             "disponibilite": f.get("disponibilite"), "modes": f.get("modes"), "age_max": f.get("age_max"), "public": f.get("public"),
             "personnes": f.get("personnes"), "tailles": f.get("tailles"), "par_lot": bool(f.get("par_lot", False))},
        )
        _lignes_de_formule_lisibles(f)
    return sortie


async def refs_d_enseigne(connexion: asyncpg.Connection) -> dict[str, set[str]]:
    """[.mark] Lot 3 : les ``ref`` de la carte d'enseigne (déclarée à la main), par rubrique du format commun. Elle sert à la règle d'import des
    cartes vers la portée (``services/restauration/prises/import_carte.py``). Vide quand aucune enseigne n'est déclarée."""
    rubriques = {
        "resto_categorie": "categories", "resto_produit": "produits", "resto_declinaison": "declinaisons",
        "resto_groupe_choix": "groupes", "resto_option": "options", "resto_formule": "formules",
    }
    sortie: dict[str, set[str]] = {}
    for table, rubrique in rubriques.items():
        lignes = await connexion.fetch(f"SELECT ref FROM mark.{table} WHERE site_id IS NULL AND portee = 'enseigne'")
        sortie[rubrique] = {r["ref"] for r in lignes}
    return sortie


def _comparable(table: str, colonnes: dict) -> dict:
    simples, jsonb, listes = _TABLES[table]
    return {c: colonnes.get(c) for c in (*simples, *jsonb, *listes)}


async def importer_carte(connexion: asyncpg.Connection, etablissement_id: int, carte_commune: dict, source: str) -> dict:
    """Écrit la carte d'un établissement d'après le format commun. IDEMPOTENT : le même fichier rejoué ne change rien.
    N'écrase JAMAIS une surcouche (synonymes, étoile, lexique, phrase : table à part) ni une ligne qu'une personne a
    écrite (source portail, mark ou agent). Une ligne de la même source absente du fichier est retirée. Une transaction :
    un fichier invalide n'écrit rien. Rend le bilan ``{ajoutes, changes, retires, conserves, sans_code_caisse}``."""
    if source not in SOURCES:
        raise ValueError(f"Source inconnue : {source!r}")
    voulues = _lignes_de_la_carte(carte_commune)
    maintenant_ = await maintenant(connexion)
    bilan = {"ajoutes": 0, "changes": 0, "retires": 0, "conserves": 0, "sans_code_caisse": []}
    ecrasables = {source, "import"}
    async with connexion.transaction():
        await fuseau_de(connexion, etablissement_id)  # l'établissement existe
        await poser_session(connexion, source, f"import:{source}")
        for table, (simples, jsonb, listes) in _TABLES.items():
            colonnes_toutes = (*simples, *jsonb, *listes)
            existantes = {
                r["ref"]: r
                for r in await connexion.fetch(f"SELECT * FROM mark.{table} WHERE site_id = $1", etablissement_id)
            }
            for ref, colonnes in voulues[table].items():
                if "code_caisse" in colonnes and not colonnes["code_caisse"]:
                    bilan["sans_code_caisse"].append(ref)
                avant = existantes.get(ref)
                valeurs = [json.dumps(colonnes[c]) if c in jsonb and colonnes.get(c) is not None else colonnes.get(c) for c in colonnes_toutes]
                if avant is None:
                    marques = ", ".join(
                        f"${i + 5}::jsonb" if c in jsonb else f"${i + 5}" for i, c in enumerate(colonnes_toutes)
                    )
                    await connexion.execute(
                        f"INSERT INTO mark.{table} (site_id, ref, source, maj_le, {', '.join(colonnes_toutes)}) "
                        f"VALUES ($1, $2, $3, $4, {marques})",
                        etablissement_id, ref, source, maintenant_, *valeurs,
                    )
                    bilan["ajoutes"] += 1
                    continue
                if avant["source"] not in ecrasables:
                    bilan["conserves"] += 1  # écrit par une personne : jamais écrasé
                    continue
                actuel = {
                    c: (_json(avant[c]) if c in jsonb else (list(avant[c]) if c in listes and avant[c] is not None else avant[c]))
                    for c in colonnes_toutes
                }
                if actuel == _comparable(table, colonnes):
                    continue
                affectations = ", ".join(
                    f"{c} = ${i + 4}::jsonb" if c in jsonb else f"{c} = ${i + 4}" for i, c in enumerate(colonnes_toutes)
                )
                await connexion.execute(
                    f"UPDATE mark.{table} SET maj_le = $3, {affectations} WHERE site_id = $1 AND ref = $2",
                    etablissement_id, ref, maintenant_, *valeurs,
                )
                bilan["changes"] += 1
            a_retirer = [r for r, l in existantes.items() if r not in voulues[table] and l["source"] in ecrasables]
            if a_retirer:
                await connexion.execute(
                    f"DELETE FROM mark.{table} WHERE site_id = $1 AND ref = ANY($2::text[])", etablissement_id, a_retirer
                )
                bilan["retires"] += len(a_retirer)
        # L'étoile d'un produit du fichier ne devient une surcouche que si rien n'existe : jamais écrasée.
        for p in carte_commune.get("produits", []):
            if p.get("etoile"):
                await connexion.execute(
                    "INSERT INTO mark.resto_surcouche (site_id, objet, ref, etoile, maj_le) VALUES ($1, 'produit', $2, true, $3) "
                    "ON CONFLICT (site_id, objet, ref) DO NOTHING",
                    etablissement_id, p["id"], maintenant_,
                )
    return bilan
