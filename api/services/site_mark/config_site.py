"""[.mark] S2 / D175 / D181 : la configuration que le script d'un site reçoit pour une page.

``GET /public/embed/site/{cle}/config?chemin=...`` rend la configuration de l'agent dont le chemin est le PLUS LONG
préfixe (par segments) du chemin demandé, sinon celle de l'agent « tout le site », sinon rien (le widget ne
s'affiche pas). Un cache de cinq minutes (serveur) et un ETag (navigateur) tiennent la charge ; il est vidé à
l'enregistrement d'une apparence ou d'un emplacement. Le contrôle du domaine se fait AVANT le cache, à chaque requête.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any

from api.schemas.apparence_widget import ApparenceWidget, TEXTES_DEFAUT
from api.services.site_mark import chemins as lib_chemins

DUREE_CACHE_S = 300.0
CHARGEMENT_TOUS_LES_S = 60.0

_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_dernier_chargement_ecrit: dict[int, float] = {}


def vider_le_cache(cle_du_site: str | None = None) -> None:
    for k in [k for k in _cache if cle_du_site is None or k[0] == cle_du_site]:
        _cache.pop(k, None)


def apparence_du_jeton(jeton) -> ApparenceWidget:
    """L'apparence enregistrée ; illisible : le bleu .mark par défaut (jamais une erreur côté visiteur)."""
    brut = ((getattr(jeton, "settings", None) or {}).get("apparence")) or {}
    try:
        return ApparenceWidget.model_validate(brut)
    except Exception:  # noqa: BLE001
        return ApparenceWidget()


def charge_utile(jeton, *, tour_active: bool, relais_force: bool) -> dict[str, Any]:
    apparence = apparence_du_jeton(jeton)
    return {
        "actif": True,
        "token": jeton.token,
        "widget_type": "chat" if ((jeton.settings or {}).get("widgetType") == "chat") else "voice",
        "apparence": apparence.model_dump(mode="json"),
        "couleurs": apparence.couleurs_resolues(),
        "turn_enabled": tour_active,
        "force_turn_relay": relais_force,
    }


def etag_de(charge: dict) -> str:
    return '"' + hashlib.sha1(json.dumps(charge, sort_keys=True).encode()).hexdigest()[:20] + '"'


def jeton_valide(jeton, maintenant: datetime | None = None) -> bool:
    if jeton is None or not jeton.is_active:
        return False
    if jeton.expires_at is not None and jeton.expires_at < (maintenant or datetime.now(UTC)):
        return False
    return True


async def configuration_pour(db, site, chemin: str, *, tour_active: bool, relais_force: bool) -> dict:
    """La charge utile pour une page (cache de cinq minutes) ; ``{"actif": False}`` quand aucun agent ne la sert."""
    page = lib_chemins.normaliser(chemin)
    cle = (site.cle, page)
    en_cache = _cache.get(cle)
    if en_cache and en_cache[0] > time.monotonic():
        return en_cache[1]
    lignes = await db.lire_chemins_du_site(site.id)
    jetons = await db.lire_jetons(sorted({ligne.embed_token_id for ligne in lignes}))
    candidats = {ligne.chemin: jetons.get(ligne.embed_token_id) for ligne in lignes if jeton_valide(jetons.get(ligne.embed_token_id))}
    jeton = lib_chemins.plus_long_prefixe(candidats, page)
    charge = (
        charge_utile(jeton, tour_active=tour_active, relais_force=relais_force) if jeton is not None else {"actif": False}
    )
    _cache[cle] = (time.monotonic() + DUREE_CACHE_S, charge)
    return charge


async def jeton_pour(db, site, chemin: str):
    """Le jeton (valide) de l'agent qui sert ``chemin`` sur ce site, ou ``None`` : la même règle que la configuration."""
    page = lib_chemins.normaliser(chemin)
    lignes = await db.lire_chemins_du_site(site.id)
    jetons = await db.lire_jetons(sorted({ligne.embed_token_id for ligne in lignes}))
    candidats = {
        ligne.chemin: jetons.get(ligne.embed_token_id)
        for ligne in lignes
        if jeton_valide(jetons.get(ligne.embed_token_id))
    }
    return lib_chemins.plus_long_prefixe(candidats, page)


async def domaines_du_jeton(db, jeton) -> list:
    """Les domaines du jeton ; vides et rattaché à un site : ceux du site (les domaines du jeton priment)."""
    if jeton.allowed_domains:
        return list(jeton.allowed_domains)
    site_id = getattr(jeton, "site_id", None)
    if site_id:
        site = await db.lire_site(site_id, jeton.organization_id)
        if site is not None and site.allowed_domains:
            return list(site.allowed_domains)
    return []


async def noter_le_chargement(db, site_id: int) -> bool:
    """Écrit la date du dernier chargement vu, au plus une fois par minute et par site."""
    maintenant = time.monotonic()
    if maintenant - _dernier_chargement_ecrit.get(site_id, -1e9) < CHARGEMENT_TOUS_LES_S:
        return False
    _dernier_chargement_ecrit[site_id] = maintenant
    await db.noter_chargement(site_id)
    return True


__all__ = ["TEXTES_DEFAUT"]
