"""[.mark] Module Restauration, lot 6 : les zones de livraison et la vérification d'une adresse (couche d'accès, lecture seule).

Hors des 17 fonctions du contrat. ``verifier_adresse`` lit les zones de CET établissement (jamais d'un autre), reconnaît la commune dans ce que l'appelant a
dit grâce à la liste nationale des communes (``communes.analyse``), et rend un statut fermé : ``RETENU`` (la zone), ``HORS_ZONE``, ``AMBIGU`` (à confirmer,
avec les candidats) ou ``INTROUVABLE`` (demander la commune). La règle de décision est pure et vit dans ``zones_de_service`` : zéro faux sûr.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg

from api.db.bases_clients import zones_de_service as zs
from api.db.bases_clients.restauration_commun import Resultat
from api.services.communes.analyse import SURE, analyser
from api.services.communes.base import BaseCommunes, obtenir_base

MOT_LONG_MIN = 3  # une adresse de moins de trois lettres n'est jamais analysée


async def zones_de_l_etablissement(connexion: asyncpg.Connection, etablissement_id: int) -> list[dict]:
    lignes = await connexion.fetch("SELECT * FROM mark.resto_zone WHERE site_id = $1 ORDER BY ordre, id", etablissement_id)
    return [dict(r) for r in lignes]


def _zone_pure(r: dict) -> zs.Zone:
    return zs.Zone(
        id=r["id"], nom=r["nom"], forme=r["forme"], communes=tuple(r["communes"] or ()),
        rayon_km=float(r["rayon_km"]) if r["rayon_km"] is not None else None, exclues=tuple(r["exclues"] or ()), ordre=r["ordre"],
    )


async def centre_de_l_etablissement(connexion: asyncpg.Connection, etablissement_id: int, base: BaseCommunes) -> tuple[float, float] | None:
    """Le (longitude, latitude) du centre de la commune de l'établissement ; ``None`` quand elle est inconnue."""
    insee = await connexion.fetchval("SELECT adresse_insee FROM mark.site WHERE id = $1", etablissement_id)
    return base.coordonnees(insee.strip()) if insee else None


async def communes_autour_de_l_etablissement(connexion: asyncpg.Connection, etablissement_id: int, rayon_km: float) -> list[dict]:
    """Les communes à ``rayon_km`` ou moins de l'établissement, les plus proches d'abord : ``[{insee, nom, code_postal}]``. Sert à régler une zone."""
    base = await obtenir_base()
    centre = await centre_de_l_etablissement(connexion, etablissement_id, base)
    if centre is None:
        return []
    return [{"insee": c.insee, "nom": c.nom, "code_postal": c.cps[0] if c.cps else None} for c in zs.communes_autour(base, centre[0], centre[1], rayon_km)]


def _zone_dite(zone_ligne: dict) -> dict[str, Any]:
    return {
        "id": zone_ligne["id"], "nom": zone_ligne["nom"], "frais": zone_ligne["frais"], "minimum": zone_ligne["minimum"],
        "gratuite_des": zone_ligne["gratuite_des"], "delai": zone_ligne["delai"],
    }


def _commune_dite(base: BaseCommunes, commune: zs.Commune) -> dict[str, Any]:
    return {"insee": commune.insee, "nom": commune.nom, "code_postal": commune.cps[0] if commune.cps else None, "departement": base.nom_departement(commune.dep)}


def _libelle(base: BaseCommunes, commune: zs.Commune) -> str:
    return f"{commune.nom} ({base.nom_departement(commune.dep)})"


async def verifier_adresse(connexion: asyncpg.Connection, etablissement_id: int, texte: str, *, base: BaseCommunes | None = None) -> Resultat:
    """La zone de l'adresse dite. ``RETENU`` quand UNE commune est entendue avec certitude et qu'une zone la contient (``faits.zone``, ``faits.commune``) ;
    ``HORS_ZONE`` quand elle est sûre mais hors de toutes les zones ; ``AMBIGU`` pour tout ce qui est à confirmer (jamais une zone) ; ``INTROUVABLE`` sans
    commune entendue. Rend ``ARGUMENT_INVALIDE`` pour un texte vide."""
    if len((texte or "").strip()) < MOT_LONG_MIN:
        return Resultat("ARGUMENT_INVALIDE", {}, "Je n'ai pas compris l'adresse, pouvez-vous la répéter ?", "adresse")
    base = base or await obtenir_base()
    lignes = await zones_de_l_etablissement(connexion, etablissement_id)
    if not lignes:
        return Resultat("HORS_ZONE", {"raison": "aucune_zone"}, "Nous ne livrons pas à cette adresse.")
    par_id = {r["id"]: r for r in lignes}
    centre = await centre_de_l_etablissement(connexion, etablissement_id, base)
    detections = await asyncio.to_thread(analyser, texte, base, centre)
    verdict = zs.verdict_de_l_adresse([_zone_pure(r) for r in lignes], detections, centre, SURE)
    if verdict.statut == zs.INTROUVABLE:
        return Resultat("INTROUVABLE", {}, "Dans quelle commune se trouve l'adresse ?", "commune")
    if verdict.statut == zs.AMBIGU:
        candidats = [{**_commune_dite(base, c.commune), "dans_une_zone": c.zone is not None} for c in verdict.candidats]
        noms = " ou ".join(_libelle(base, c.commune) for c in verdict.candidats)
        return Resultat("AMBIGU", {"candidats": candidats}, f"Est-ce {noms} ?", "commune")
    commune = _commune_dite(base, verdict.commune)
    if verdict.statut == zs.HORS_ZONE:
        return Resultat("HORS_ZONE", {"commune": commune}, f"Nous ne livrons pas à {verdict.commune.nom}.")
    return Resultat("RETENU", {"zone": _zone_dite(par_id[verdict.zone.id]), "commune": commune, "adresse": texte.strip()}, "")
