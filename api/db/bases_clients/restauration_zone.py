"""[.mark] Module Restauration, lot 6 : les zones de livraison et la vérification d'une adresse (couche d'accès, lecture seule).

Hors des 17 fonctions du contrat. ``verifier_adresse`` lit les zones de CET établissement (jamais d'un autre), reconnaît la commune dans ce que l'appelant a
dit grâce à la liste nationale des communes (``communes.analyse``), et rend un statut fermé : ``RETENU`` (la zone), ``HORS_ZONE``, ``AMBIGU`` (à confirmer,
avec les candidats) ou ``INTROUVABLE`` (demander la commune). La règle de décision est pure et vit dans ``zones_de_service`` : zéro faux sûr.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import asyncpg

from api.db.bases_clients import zones_de_service as zs
from api.db.bases_clients.restauration_commun import Resultat
from api.services.communes.analyse import SURE, analyser
from api.services.communes.base import BaseCommunes, normaliser, obtenir_base
from api.services.mots_dits import liste_dite_et

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


_VOIES = frozenset({"rue", "avenue", "av", "boulevard", "bd", "place", "chemin", "impasse", "allee", "route", "quai", "cours", "square", "de", "du", "des", "d", "la", "le", "les", "l", "saint", "sainte"})
_MARQUEURS = frozenset({"a", "au", "aux", "sur", "vers", "dans", "en"})
NGRAMME_MAX = 6
NOM_COURT = 5  # un nom de moins de cinq lettres ne se prend jamais pour une commune sans repère (« Gare », « Mont »)


def _commune_nommee(base: BaseCommunes, texte: str):
    """Une commune dite en toutes lettres que l'analyse n'a pas relevée : la liste nationale, cherchée par nom EXACT. ``Commune`` quand le nom n'en désigne qu'une ;
    liste de communes quand plusieurs portent le nom (à confirmer) ; ``None`` sinon. Le nom doit finir l'adresse ou suivre « à » : jamais un nom de rue
    (« rue de Creil ») pris pour une commune : un nom précédé d'une voie, d'un article ou d'une préposition est écarté."""
    segments = [s for s in re.split(r"[,;]", texte) if s.strip()]
    morceau = normaliser(segments[-1]).split()
    # un code postal en fin de segment ne fait pas partie du nom
    morceau = [m for m in morceau if not re.fullmatch(r"\d{5}", m)]
    for taille in range(min(NGRAMME_MAX, len(morceau)), 0, -1):
        for debut in range(len(morceau) - taille, -1, -1):
            nom = " ".join(morceau[debut : debut + taille])
            avant = morceau[debut - 1] if debut else None
            if debut + taille != len(morceau) or nom not in base.par_nom or len(nom) < NOM_COURT:
                continue
            if avant is not None and avant not in _MARQUEURS and avant in _VOIES:
                continue
            trouvees = [base.communes[i] for i in base.par_nom[nom]]
            return trouvees[0] if len(trouvees) == 1 else trouvees[:3]
    return None


def _livrees(base: BaseCommunes, lignes: list[dict], centre: tuple[float, float] | None) -> list[str]:
    """Les noms des communes que l'établissement livre (listes de communes et rayons), les plus proches d'abord, au plus huit."""
    noms: list[str] = []
    for r in lignes:
        zone = _zone_pure(r)
        if zone.forme == "communes":
            noms += [c.nom for c in (base.commune(i) for i in zone.communes if i not in zone.exclues) if c is not None]
        elif zone.forme == "rayon" and zone.rayon_km is not None and centre is not None:
            noms += [c.nom for c in zs.communes_autour(base, centre[0], centre[1], zone.rayon_km) if c.insee not in zone.exclues]
    vus: list[str] = []
    for n in noms:
        if n not in vus:
            vus.append(n)
    return vus[:8]


def _hors_zone(base: BaseCommunes, commune: zs.Commune, lignes: list[dict], centre: tuple[float, float] | None) -> Resultat:
    livrees = _livrees(base, lignes, centre)
    phrase = f"Nous ne livrons pas à {commune.nom}." + (f" Nous livrons {liste_dite_et(livrees)}." if livrees else "")
    return Resultat("HORS_ZONE", {"commune": _commune_dite(base, commune), "communes_livrees": livrees}, phrase)


def commune_et_departement_dits(base: BaseCommunes, texte: str) -> zs.Commune | None:
    """Chantier Partie 1, lot 4 (cas de Pierre, « oui, le Val-d'Oise ») : une commune nommée AVEC son département (« Nointel, Val-d'Oise »,
    « Nointel dans l'Oise ») : le nom du département dit départage les homonymes, jamais lu comme une autre commune. Rend la commune quand le nom
    restant en désigne une seule dans ce département ; ``None`` sinon (l'analyse habituelle décide)."""
    dit = normaliser(texte)
    for code, nom in sorted(base.departements.items(), key=lambda d: -len(d[1])):
        motif = rf"(?:^|\s)(?:(?:dans|en)\s+)?(?:(?:le|la|les|l)\s+)?{re.escape(normaliser(nom))}$"
        m = re.search(motif, dit)
        if m is None or not dit[: m.start()].strip():
            continue
        reste = dit[: m.start()].strip().split()
        for taille in range(min(NGRAMME_MAX, len(reste)), 0, -1):
            nom_commune = " ".join(reste[-taille:])
            dans = [base.communes[i] for i in base.par_nom.get(nom_commune, []) if base.communes[i].dep == code]
            if len(dans) == 1:
                return dans[0]
        return None
    return None


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
    nommee = commune_et_departement_dits(base, texte)
    if nommee is not None:
        zone = zs.zone_de_la_commune([_zone_pure(r) for r in lignes], nommee, centre)
        if zone is None:
            return _hors_zone(base, nommee, lignes, centre)
        return Resultat("RETENU", {"zone": _zone_dite(par_id[zone.id]), "commune": _commune_dite(base, nommee), "adresse": texte.strip()}, "")
    detections = await asyncio.to_thread(analyser, texte, base, centre)
    verdict = zs.verdict_de_l_adresse([_zone_pure(r) for r in lignes], detections, centre, SURE)
    if verdict.statut == zs.INTROUVABLE:
        # M28 : une commune réelle, nommée seule, que l'analyse n'a pas relevée (hors des communes proches) : cherchée dans la liste nationale.
        voisine = _commune_nommee(base, texte)
        if isinstance(voisine, list):
            noms = " ou ".join(_libelle(base, c) for c in voisine)
            return Resultat("AMBIGU", {"candidats": [{**_commune_dite(base, c), "dans_une_zone": zs.zone_de_la_commune([_zone_pure(r) for r in lignes], c, centre) is not None} for c in voisine]}, f"Est-ce {noms} ?", "commune")
        if voisine is not None and zs.zone_de_la_commune([_zone_pure(r) for r in lignes], voisine, centre) is None:
            return _hors_zone(base, voisine, lignes, centre)
        return Resultat("INTROUVABLE", {}, "Dans quelle commune se trouve l'adresse ?", "commune")
    if verdict.statut == zs.AMBIGU:
        candidats = [{**_commune_dite(base, c.commune), "dans_une_zone": c.zone is not None} for c in verdict.candidats]
        noms = " ou ".join(_libelle(base, c.commune) for c in verdict.candidats)
        return Resultat("AMBIGU", {"candidats": candidats}, f"Est-ce {noms} ?", "commune")
    commune = _commune_dite(base, verdict.commune)
    if verdict.statut == zs.HORS_ZONE:
        return _hors_zone(base, verdict.commune, lignes, centre)
    return Resultat("RETENU", {"zone": _zone_dite(par_id[verdict.zone.id]), "commune": commune, "adresse": texte.strip()}, "")
