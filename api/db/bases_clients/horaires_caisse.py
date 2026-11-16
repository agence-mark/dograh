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


def _heure(valeur: Any) -> time | None:
    try:
        return time.fromisoformat(str(valeur).strip())
    except ValueError:
        return None


def jours_de_la_caisse(horaires: Any) -> dict[int, list[tuple[time, time]]]:
    """Les plages de la caisse par jour (1 = lundi), triées. Une clé qui n'est pas un jour, une plage illisible ou qui finit avant de commencer est
    ignorée : jamais une horaire inventée. Aucune plage valide : ``{}`` (la caisse n'a pas posé d'horaires)."""
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
            if debut is not None and fin is not None and fin > debut:
                sortie.setdefault(jour, []).append((debut, fin))
    return {jour: sorted(plages) for jour, plages in sortie.items()}


def lignes_du_classeur(jours: dict[int, list[tuple[time, time]]]) -> list[dict[str, Any]]:
    """Les horaires de la caisse sous la forme des lignes de ``mark.horaire`` (``jour``, ``ouverture``, ``fermeture``)."""
    return [{"jour": jour, "ouverture": debut, "fermeture": fin} for jour, plages in sorted(jours.items()) for debut, fin in plages]


def _ligne_du_jour(numero: int, plages: list[tuple[time, time]]) -> str:
    if not plages:
        return f"{JOURS_FR[numero - 1]} : fermé"
    return f"{JOURS_FR[numero - 1]} : " + " et ".join(f"{d.strftime('%H:%M')}-{f.strftime('%H:%M')}" for d, f in plages)


def texte_de_la_fiche(jours: dict[int, list[tuple[time, time]]], texte_de_la_fiche: str | None = None) -> str:
    """Le format lisible d'une fiche (celui de l'écran et de ``{{horaires_ouverture}}``) : les sept jours de la caisse, puis ce que la fiche garde de
    PLUS que les sept jours (jours fériés, fermetures datées, exceptions), que la caisse ne porte pas. Les lignes de jour de la fiche sont remplacées."""
    lignes = [_ligne_du_jour(n, jours.get(n, [])) for n in range(1, 8)]
    for ligne in (texte_de_la_fiche or "").splitlines():
        cle = _sans_accents(ligne.partition(":")[0].strip().lower())
        if ligne.strip() and cle not in JOURS_FR:
            lignes.append(ligne.rstrip())
    return "\n".join(lignes)


async def horaires_de_la_caisse(connexion: asyncpg.Connection, etablissement_id: int) -> dict[int, list[tuple[time, time]]]:
    """Les horaires que la caisse porte pour cet établissement ET qui font foi (caisse branchée qui en a envoyé, restaurant qui ne les tient pas ici),
    sinon ``{}`` : la fiche reste la source. Toute requête porte l'établissement."""
    ligne = await connexion.fetchval("SELECT horaires FROM mark.resto_etat_caisse WHERE site_id = $1", etablissement_id)
    jours = jours_de_la_caisse(ligne)
    if not jours or await source_tenue_ici(connexion, etablissement_id, "horaires"):
        return {}
    return jours


async def horaires_du_classeur(connexion: asyncpg.Connection, etablissement_id: int) -> list[dict[str, Any]]:
    """Les lignes d'horaires que lit le comptoir (état d'ouverture, fin du service) : celles de la caisse quand elle fait foi, sinon ``mark.horaire``."""
    jours = await horaires_de_la_caisse(connexion, etablissement_id)
    if jours:
        return lignes_du_classeur(jours)
    return [dict(r) for r in await connexion.fetch("SELECT jour, ouverture, fermeture FROM mark.horaire WHERE site_id = $1", etablissement_id)]


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
