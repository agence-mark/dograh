"""[.mark] Module Restauration, lot 6 : le temps annoncé, la puce du temps (coup de feu, pause par type), l'état par type (contrat § 4, E-04 à E-06, E-42, E-49).

Hors des 17 fonctions du contrat (elles lisent et écrivent ce que le comptoir, la route du temps et le portail réclament) :

- ``annonce_pour``    : l'heure que le code annoncerait MAINTENANT pour un type (et une zone) : délai en entier, durée ajoutée, attente de capacité
- ``temps_par_type``  : l'état de chaque type (ouvert, pause, ajout) et ce que l'agent annonce, par zone pour la livraison (lu par la puce)
- ``ecrire_temps``    : la puce : durée ajoutée, « jusqu'à », pause par type ; refusée quand la caisse porte l'état (E-49) ; journalisée
- ``fin_du_service``  : la fin du service du jour, lue dans les horaires de l'établissement (une seule source, T-02)

L'heure vient de la source d'heure de l'organisation (D6). Le calcul est dans ``annonce_heure.py`` (mécanisme commun, pur).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients import annonce_heure
from api.db.bases_clients.annonce_heure import Annonce
from api.db.bases_clients.restauration_carte import etat_caisse, etat_combine
from api.db.bases_clients.restauration_commun import TYPES, Resultat, fuseau_de, maintenant, poser_session
from api.db.bases_clients.restauration_reglage import reglage_du_type

AJOUT_MAX_MINUTES = 240
PAUSE_MAX_MINUTES = 720
ETATS_FINAUX = ("annulee", "refusee", "echec")
ORDRE_DES_TYPES = ("emporter", "livraison", "sur_place", "reservation")
PAS_DE_CHANGEMENT = object()  # ``pause`` absente de la demande : la pause n'est pas touchée


def _ajout_actif(reglage: dict | None, moment: datetime) -> int:
    """Les minutes ajoutées par-dessus qui comptent à cet instant (la durée ajoutée s'éteint à son heure)."""
    if not reglage or not reglage["minutes_ajoutees"]:
        return 0
    jusqu_a = reglage["ajout_jusqu_a"]
    return reglage["minutes_ajoutees"] if jusqu_a is None or jusqu_a > moment else 0


async def _charges_par_quart(connexion: asyncpg.Connection, etablissement_id: int, type_: str, prete: datetime) -> dict[datetime, int]:
    """Ce qui est déjà annoncé dans chaque quart d'heure qui suit ``prete`` (les demandes de CE type et de CET établissement, encore vivantes)."""
    debut = annonce_heure.quart_de(prete)
    fin = debut + timedelta(minutes=annonce_heure.QUART * annonce_heure.QUARTS_MAX)
    lignes = await connexion.fetch(
        "SELECT heure_annoncee FROM mark.resto_commande WHERE site_id = $1 AND mode = $2 AND heure_annoncee >= $3 AND heure_annoncee < $4 "
        "AND statut <> ALL($5::text[])",
        etablissement_id, type_, debut, fin, list(ETATS_FINAUX),
    )
    charges: dict[datetime, int] = {}
    for ligne in lignes:
        quart = annonce_heure.quart_de(ligne["heure_annoncee"].astimezone(prete.tzinfo))
        charges[quart] = charges.get(quart, 0) + 1
    return charges


async def annonce_pour(
    connexion: asyncpg.Connection, etablissement_id: int, type_: str, moment: datetime | None = None, zone_id: int | None = None,
    *, etat: dict | None = None,
) -> dict[str, Any]:
    """Ce que le code annonce maintenant pour ce type (et cette zone pour la livraison) : ``{annonce, format, delai_minutes, ajout_minutes,
    attente_minutes}``. Le délai est celui du type, ou celui de la ZONE, EN ENTIER (E-42) ; la durée ajoutée vient par-dessus ; l'attente vient de la
    capacité par quart d'heure. Une zone d'un autre établissement : ``LookupError`` (jamais le délai d'une autre)."""
    if type_ not in TYPES or type_ == "reservation":
        raise ValueError(f"Pas d'heure annoncée pour le type {type_!r}")
    moment = moment or await maintenant(connexion)
    etat = etat or await etat_combine(connexion, etablissement_id, type_, moment)
    reglage = await reglage_du_type(connexion, etablissement_id, type_)
    ajout = _ajout_actif(reglage, moment)
    delai_zone = 0
    if type_ == "livraison" and zone_id:
        zone = await connexion.fetchrow("SELECT delai FROM mark.resto_zone WHERE id = $1 AND site_id = $2", zone_id, etablissement_id)
        if zone is None:
            raise LookupError("Zone inconnue de cet établissement.")
        delai_zone = zone["delai"]
    base = etat["delai_minutes"] - ajout + delai_zone  # ``etat_combine`` compte déjà l'ajout : on le met à part
    format_ = reglage["annonce"] if reglage else "duree"
    capacite = reglage["capacite_quart_heure"] if reglage else None
    attente = 0
    if capacite:
        prete = moment + timedelta(minutes=base + ajout)
        attente = annonce_heure.attente_par_quart(prete, await _charges_par_quart(connexion, etablissement_id, type_, prete), capacite)
    return {
        "annonce": annonce_heure.annoncer(moment, base, ajout, attente, format_),
        "format": format_, "delai_minutes": base, "ajout_minutes": ajout, "attente_minutes": attente,
    }


def _rendre(annonce: Annonce, fuseau: ZoneInfo) -> dict[str, Any]:
    return {
        "format": annonce.format, "minutes": annonce.minutes, "prete": annonce.prete, "debut": annonce.debut, "fin": annonce.fin,
        "phrase": annonce_heure.dite(annonce, fuseau),
    }


async def temps_par_type(connexion: asyncpg.Connection, etablissement_id: int, moment: datetime | None = None) -> dict[str, Any]:
    """L'état de chaque type et ce que l'agent annonce maintenant (par zone pour la livraison). La caisse qui porte l'état le rend en lecture seule
    (E-49) : la puce l'affiche et ne le modifie pas."""
    moment = moment or await maintenant(connexion)
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    caisse = await etat_caisse(connexion, etablissement_id)
    zones = await connexion.fetch("SELECT id, nom, delai FROM mark.resto_zone WHERE site_id = $1 ORDER BY ordre, id", etablissement_id)
    types = []
    for type_ in ORDRE_DES_TYPES:
        etat = await etat_combine(connexion, etablissement_id, type_, moment)
        reglage = await reglage_du_type(connexion, etablissement_id, type_)
        ajout = _ajout_actif(reglage, moment)
        ligne: dict[str, Any] = {
            "type": type_, "ouvert": etat["ouvert"], "raison": etat["raison"], "reprise": etat["reprise"],
            "pause_jusqu_a": reglage["pause_jusqu_a"] if reglage and reglage["pause_jusqu_a"] and reglage["pause_jusqu_a"] > moment else None,
            "minutes_ajoutees": reglage["minutes_ajoutees"] if reglage else 0, "ajout_jusqu_a": reglage["ajout_jusqu_a"] if reglage else None,
            "ajout_actif": ajout, "format": reglage["annonce"] if reglage else "duree", "delai_minutes": None, "annonce": None, "par_zone": [],
        }
        if type_ == "livraison":
            for zone in zones:
                a = await annonce_pour(connexion, etablissement_id, type_, moment, zone["id"], etat=etat)
                ligne["par_zone"].append({"zone_id": zone["id"], "nom": zone["nom"], "delai_zone": zone["delai"], "annonce": _rendre(a["annonce"], fuseau)})
        elif type_ != "reservation":
            a = await annonce_pour(connexion, etablissement_id, type_, moment, None, etat=etat)
            ligne["delai_minutes"], ligne["annonce"] = a["delai_minutes"], _rendre(a["annonce"], fuseau)
        types.append(ligne)
    return {
        "types": types,
        "source_de_l_etat": "caisse" if caisse is not None else "portail",
        "lecture_seule": caisse is not None,
        "etat_caisse": None if caisse is None else {
            "mode": caisse["mode"], "minutes_en_plus": caisse["minutes_en_plus"], "reprise": caisse["reprise"], "temps_preparation": caisse["temps_preparation"],
        },
        "moment": moment,
    }


async def fin_du_service(connexion: asyncpg.Connection, etablissement_id: int, moment: datetime | None = None) -> datetime:
    """La fin du service de ce jour dans les horaires de l'établissement : la fermeture de la plage en cours (ou la dernière du jour), sinon la fin
    de la journée locale. Aware."""
    moment = moment or await maintenant(connexion)
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    local = moment.astimezone(fuseau)
    plages = await connexion.fetch(
        "SELECT fermeture FROM mark.horaire WHERE site_id = $1 AND jour = $2 ORDER BY fermeture", etablissement_id, local.isoweekday()
    )
    fermetures = [datetime.combine(local.date(), p["fermeture"], tzinfo=fuseau) for p in plages]
    a_venir = [f for f in fermetures if f > local]
    if a_venir:
        return a_venir[0].astimezone(moment.tzinfo)
    return datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=fuseau).astimezone(moment.tzinfo)


async def ecrire_temps(
    connexion: asyncpg.Connection, etablissement_id: int, type_: str, minutes_ajoutees: int, jusqu_a: datetime | None = None,
    pause: Any = PAS_DE_CHANGEMENT, *, source: str = "portail", auteur: str | None = None,
) -> Resultat:
    """La puce du temps : la durée ajoutée (``minutes_ajoutees``, jusqu'à ``jusqu_a`` ou jusqu'à nouvel ordre) et la pause du type.

    ``pause`` : absente = pas touchée ; ``None`` = levée ; ``{"jusqu_a": dt}`` ou ``{"minutes": n}`` = en pause jusqu'à là ; ``{}`` = en pause
    jusqu'à la fin de la journée (une pause oubliée ne dure jamais plus d'un jour). Refusée (``REFUSEE``, ``caisse_maitre``) quand la caisse porte
    l'état (E-49) : le portail l'affiche, la caisse le change. Un changement d'ajout n'affecte jamais une heure déjà annoncée (elle est écrite sur
    sa demande). Journalisée par les déclencheurs (``source``, ``auteur``)."""
    if type_ not in TYPES:
        return Resultat("ARGUMENT_INVALIDE", manque="type")
    if not isinstance(minutes_ajoutees, int) or isinstance(minutes_ajoutees, bool) or not 0 <= minutes_ajoutees <= AJOUT_MAX_MINUTES:
        return Resultat("ARGUMENT_INVALIDE", {"maximum": AJOUT_MAX_MINUTES}, manque="minutes_ajoutees")
    if type_ == "reservation" and minutes_ajoutees:
        return Resultat("ARGUMENT_INVALIDE", {"raison": "pas_de_temps_pour_une_reservation"}, manque="minutes_ajoutees")
    moment = await maintenant(connexion)
    if jusqu_a is not None and (jusqu_a.tzinfo is None or jusqu_a <= moment):
        return Resultat("ARGUMENT_INVALIDE", manque="jusqu_a")
    if await etat_caisse(connexion, etablissement_id) is not None:
        return Resultat("REFUSEE", {"raison": "autre", "detail": "caisse_maitre"}, "L'état est géré par la caisse : on ne le change pas d'ici.")
    fin_pause: datetime | None = None
    changer_la_pause = pause is not PAS_DE_CHANGEMENT
    if changer_la_pause and pause is not None:
        if not isinstance(pause, dict):
            return Resultat("ARGUMENT_INVALIDE", manque="pause")
        if pause.get("jusqu_a") is not None:
            fin_pause = pause["jusqu_a"]
            if fin_pause.tzinfo is None or fin_pause <= moment:
                return Resultat("ARGUMENT_INVALIDE", manque="pause")
        elif pause.get("minutes") is not None:
            minutes = pause["minutes"]
            if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= PAUSE_MAX_MINUTES:
                return Resultat("ARGUMENT_INVALIDE", {"maximum": PAUSE_MAX_MINUTES}, manque="pause")
            fin_pause = moment + timedelta(minutes=minutes)
        else:
            fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
            fin_pause = datetime.combine(moment.astimezone(fuseau).date() + timedelta(days=1), datetime.min.time(), tzinfo=fuseau)
    async with connexion.transaction():
        await poser_session(connexion, source, auteur or f"puce:{source}")
        await connexion.execute(
            "INSERT INTO mark.resto_reglage_type (site_id, type, minutes_ajoutees, ajout_jusqu_a, maj_le) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (site_id, type) DO UPDATE SET minutes_ajoutees = EXCLUDED.minutes_ajoutees, ajout_jusqu_a = EXCLUDED.ajout_jusqu_a, maj_le = EXCLUDED.maj_le",
            etablissement_id, type_, minutes_ajoutees, jusqu_a if minutes_ajoutees else None, moment,
        )
        if changer_la_pause:
            await connexion.execute(
                "UPDATE mark.resto_reglage_type SET pause_jusqu_a = $3, maj_le = $4 WHERE site_id = $1 AND type = $2", etablissement_id, type_, fin_pause, moment
            )
    return Resultat("OK", {"type": type_, "minutes_ajoutees": minutes_ajoutees, "jusqu_a": jusqu_a if minutes_ajoutees else None,
                           "pause_jusqu_a": fin_pause if changer_la_pause else None, "pause_changee": changer_la_pause})
