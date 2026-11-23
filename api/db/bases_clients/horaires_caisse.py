"""[.mark] Module Restauration, M57 (E-49) : les horaires que la caisse porte, quand elle est branchée, sont ceux de l'établissement.

Une seule source par donnée : avec une caisse branchée qui envoie ses horaires (``resto_etat_caisse.horaires``) et un restaurant qui ne les tient pas
ici (réglage ``sources.horaires`` différent de ``ici``), la fiche de l'établissement, la variable ``{{horaires_ouverture}}`` de l'agent et l'état
d'ouverture du comptoir LISENT ceux de la caisse. Sans caisse, ou quand le restaurant les tient ici, la fiche reste la source. Rien n'est jamais
recopié dans la fiche : débrancher la caisse rend ses horaires à la fiche, intacts.

Générique : aucun nom de fournisseur ni de métier. La caisse dit ses plages par jour (``{"monday": [{"from": "11:00", "to": "14:00"}]}`` ; les
jours en trois lettres et les numéros 1 à 7 sont lus aussi).
"""

from __future__ import annotations

import json
import unicodedata
from datetime import time
from typing import Any

import asyncpg
from loguru import logger

from api.db.bases_clients.instantane import stable, vivant
from api.db.bases_clients.restauration_commun import maintenant
from api.db.bases_clients.restauration_reglage import source_tenue_ici

JOURS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_JOURS_EN = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
CLE_DU_REFERENTIEL = "mark_referentiel"  # le canal que l'écoute des bases de clients suit : une copie se reconstruit à chaque notification


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def _numero_du_jour(cle: Any) -> int | None:
    """1 (lundi) à 7 (dimanche), ou ``None`` pour une clé qui n'est pas un jour."""
    texte = str(cle).strip().lower()
    if texte.isdigit():
        return int(texte) if 1 <= int(texte) <= 7 else None
    texte = _sans_accents(texte)
    for i, (en, fr) in enumerate(zip(_JOURS_EN, JOURS_FR, strict=True), start=1):
        if texte in (en, fr) or texte == en[:3]:
            return i
    return None


MINUIT = time(0, 0)
FIN_DE_JOURNEE = time(23, 59, 59, 999999)  # la fin d'un jour qui continue après minuit (``time`` ne sait pas dire 24:00)
CUTOFF_PAR_DEFAUT = time(6, 0)  # ``cutoff_time`` du point de vente HubRise (05a : « 06:00 ») : jusqu'à cette heure, une fin plus petite que le début est celle du lendemain


def _heure(valeur: Any) -> time | None:
    texte = str(valeur).strip()
    if texte == "24:00":  # que HubRise refuse (05c) mais qu'une autre caisse peut écrire : la fin du jour
        return FIN_DE_JOURNEE
    try:
        return time.fromisoformat(texte)
    except ValueError:
        return None


def jours_de_la_caisse(horaires: Any, *, cutoff: time = CUTOFF_PAR_DEFAUT) -> dict[int, list[tuple[time, time]]]:
    """Les plages de la caisse par jour (1 = lundi), triées. Une clé qui n'est pas un jour ou une plage illisible est ignorée : jamais une horaire inventée.
    Lot 19 bis (K6, prouvé en 05) : une fin plus petite ou égale au début (« 18:00 -> 01:00 », « 18:00 -> 00:00 ») est celle du LENDEMAIN, à condition d'être avant ``cutoff``
    (HubRise refuse « 18:00 -> 07:00 », 05d) : la plage est coupée en deux jours, la fin du jour puis le début du suivant. Aucune plage valide : ``{}``."""
    if isinstance(horaires, str):
        try:
            horaires = json.loads(horaires)
        except ValueError:
            return {}
    if not isinstance(horaires, dict):
        return {}
    sortie: dict[int, list[tuple[time, time]]] = {}
    for cle, liste in horaires.items():
        jour = _numero_du_jour(cle)
        if jour is None or not isinstance(liste, list):
            continue
        for plage in liste:
            if not isinstance(plage, dict):
                continue
            debut, fin = _heure(plage.get("from")), _heure(plage.get("to"))
            if debut is None or fin is None:
                continue
            if fin > debut:
                sortie.setdefault(jour, []).append((debut, fin))
            elif fin <= cutoff:  # passe minuit : la fin du jour, puis le lendemain depuis minuit jusqu'à ``fin`` (rien si la plage finit à minuit pile)
                sortie.setdefault(jour, []).append((debut, FIN_DE_JOURNEE))
                if fin > MINUIT:
                    sortie.setdefault(jour % 7 + 1, []).append((MINUIT, fin))
    return {jour: sorted(plages) for jour, plages in sortie.items()}


def lignes_du_classeur(jours: dict[int, list[tuple[time, time]]]) -> list[dict[str, Any]]:
    """Les horaires de la caisse sous la forme des lignes de ``mark.horaire`` (``jour``, ``ouverture``, ``fermeture``)."""
    return [{"jour": jour, "ouverture": debut, "fermeture": fin} for jour, plages in sorted(jours.items()) for debut, fin in plages]


def _ligne_du_jour(numero: int, plages: list[tuple[time, time]]) -> str:
    if not plages:
        return f"{JOURS_FR[numero - 1]} : fermé"
    return f"{JOURS_FR[numero - 1]} : " + " et ".join(f"{d.strftime('%H:%M')}-{'00:00' if f == FIN_DE_JOURNEE else f.strftime('%H:%M')}" for d, f in plages)


def _plages_a_dire(jours: dict[int, list[tuple[time, time]]]) -> dict[int, list[tuple[time, time]]]:
    """Pierre 13 : la plage que le classeur coupe à minuit (vendredi 18:00 -> 01:00 devient vendredi jusqu'à la fin du jour + samedi depuis minuit) se DIT d'un seul tenant,
    sur le jour où elle ouvre (« vendredi : 18:00-01:00 ») ; avant, le texte lu par l'agent donnait « vendredi : 18:00-23:59 » et « samedi : 00:00-01:00 »."""
    dites = {n: list(p) for n, p in jours.items()}
    for jour in range(1, 8):
        suite = jour % 7 + 1
        for i, (debut, fin) in enumerate(dites.get(jour, [])):
            lendemain = dites.get(suite, [])
            if fin == FIN_DE_JOURNEE and lendemain and lendemain[0][0] == MINUIT:
                dites[jour][i] = (debut, lendemain[0][1])
                dites[suite] = lendemain[1:]
                break
    return dites


def texte_de_la_fiche(jours: dict[int, list[tuple[time, time]]], texte_de_la_fiche: str | None = None) -> str:
    """Le format lisible d'une fiche (celui de l'écran et de ``{{horaires_ouverture}}``) : les sept jours de la caisse, puis ce que la fiche garde de
    PLUS que les sept jours (jours fériés, fermetures datées, exceptions), que la caisse ne porte pas. Les lignes de jour de la fiche sont remplacées."""
    dites = _plages_a_dire(jours)
    lignes = [_ligne_du_jour(n, dites.get(n, [])) for n in range(1, 8)]
    for ligne in (texte_de_la_fiche or "").splitlines():
        cle = _sans_accents(ligne.partition(":")[0].strip().lower())
        if ligne.strip() and cle not in JOURS_FR:
            lignes.append(ligne.rstrip())
    return "\n".join(lignes)


async def horaires_de_la_caisse(connexion: asyncpg.Connection, etablissement_id: int) -> dict[int, list[tuple[time, time]]]:
    """Les horaires que la caisse porte pour cet établissement ET qui font foi (caisse branchée qui en a envoyé, restaurant qui ne les tient pas ici),
    sinon ``{}`` : la fiche reste la source. Toute requête porte l'établissement."""
    caisse = (await vivant(connexion, etablissement_id, await maintenant(connexion))).caisse  # lot 5 : l'état vivant, une requête par geste
    jours = jours_de_la_caisse(caisse["horaires"] if caisse is not None else None, cutoff=(caisse["cutoff_time"] if caisse is not None else None) or CUTOFF_PAR_DEFAUT)  # K6 : le cutoff du point de vente
    if not jours or await source_tenue_ici(connexion, etablissement_id, "horaires"):
        return {}
    return jours


async def horaires_du_classeur(connexion: asyncpg.Connection, etablissement_id: int) -> list[dict[str, Any]]:
    """Les lignes d'horaires que lit le comptoir (état d'ouverture, fin du service) : celles de la caisse quand elle fait foi, sinon ``mark.horaire``."""
    jours = await horaires_de_la_caisse(connexion, etablissement_id)
    if jours:
        return lignes_du_classeur(jours)
    async def lire() -> list[dict[str, Any]]:
        return [dict(r) for r in await connexion.fetch("SELECT jour, ouverture, fermeture FROM mark.horaire WHERE site_id = $1", etablissement_id)]

    return list(await stable(connexion, ("horaires_de_la_fiche", etablissement_id), lire))  # lot 5 : lus une fois par appel


async def horaires_des_caisses(connexion: asyncpg.Connection) -> dict[int, dict[int, list[tuple[time, time]]]]:
    """Pour la copie que lisent les appels : site -> horaires de la caisse qui font foi. Une base sans le module Restauration (tables absentes, base
    pas encore montée) : ``{}``, la fiche fait foi ; jamais une copie vide à cause d'elle."""
    try:
        sites = [r["site_id"] for r in await connexion.fetch("SELECT site_id FROM mark.resto_etat_caisse WHERE horaires IS NOT NULL")]
        return {s: jours for s in sites if (jours := await horaires_de_la_caisse(connexion, s))}
    except asyncpg.PostgresError as erreur:
        logger.debug(f"[.mark] Horaires de la caisse non lus ({type(erreur).__name__}) : la fiche fait foi")
        return {}


async def notifier_le_referentiel(connexion: asyncpg.Connection, motif: str) -> None:
    """Les horaires que lisent les appels ont changé sans qu'une fiche soit écrite (la caisse en a envoyé d'autres, le restaurant les tient ici ou
    plus, la caisse est débranchée) : la copie des appels se reconstruit, comme à chaque écriture d'une fiche."""
    await connexion.execute("SELECT pg_notify($1, $2)", CLE_DU_REFERENTIEL, motif[:60])
