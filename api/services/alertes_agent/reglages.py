"""[.mark] Les réglages d'alerte d'un agent et les alertes levées, dans ``organization_configurations`` (aucune migration).

* ``MARK_ALERTES:<agent>`` : ``{"types": {code: {"actif", "seuils"}}, "mail": bool, "levees": [alerte, ...]}`` ;
* défauts : chaque type actif avec ses seuils par défaut (une alerte LIT des chiffres déjà rangés, elle ne dépense rien) ; le mail
  est éteint (il part vers les adresses de notification de l'organisation et de .mark).

Les alertes levées gardent les ``LEVEES_MAX`` dernières, la plus récente d'abord. Une alerte a un identifiant stable
(type, agent, version) : l'évaluer deux fois ne la lève qu'une fois.
"""

from __future__ import annotations

from typing import Any

from api.services.alertes_agent import types
from api.services.builder import stock

PREFIXE = "MARK_ALERTES:"
LEVEES_MAX = 20


def cle(workflow_id: int) -> str:
    return f"{PREFIXE}{workflow_id}"


def _un_type(brut: Any, code: str) -> dict[str, Any]:
    brut = brut if isinstance(brut, dict) else {}
    return {"actif": brut.get("actif") is not False, "seuils": types.seuils_valides(code, brut.get("seuils"))}


def _propres(ligne: dict[str, Any] | None) -> dict[str, Any]:
    ligne = ligne if isinstance(ligne, dict) else {}
    bruts = ligne.get("types") if isinstance(ligne.get("types"), dict) else {}
    return {
        "types": {code: _un_type(bruts.get(code), code) for code in types.TYPES},
        "mail": ligne.get("mail") is True,
        "levees": [a for a in ligne.get("levees") or [] if isinstance(a, dict)][:LEVEES_MAX],
    }


async def lire(organization_id: int, workflow_id: int) -> dict[str, Any]:
    return _propres(await stock.lire(organization_id, cle(workflow_id)))


async def regler(organization_id: int, workflow_id: int, *, mail: bool | None = None, par_type: dict[str, Any] | None = None) -> dict[str, Any]:
    """Change le mail et/ou les types (``actif``, ``seuils``) ; ce qui n'est pas dit ne bouge pas. Un type inconnu est refusé."""
    inconnus = [c for c in (par_type or {}) if c not in types.TYPES]
    if inconnus:
        raise ValueError(f"Unknown alert type: {inconnus[0]}.")

    def transformer(ligne):
        courant = _propres(ligne)
        if mail is not None:
            courant["mail"] = bool(mail)
        for code, voulu in (par_type or {}).items():
            voulu = voulu if isinstance(voulu, dict) else {}
            if voulu.get("actif") is not None:
                courant["types"][code]["actif"] = bool(voulu["actif"])
            if voulu.get("seuils") is not None:
                courant["types"][code]["seuils"] = types.seuils_valides(code, {**courant["types"][code]["seuils"], **voulu["seuils"]})
        return courant

    return _propres(await stock.modifier(organization_id, cle(workflow_id), transformer))


async def lever(organization_id: int, workflow_id: int, alerte: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Range l'alerte. Rend ``(alerte rangée, nouvelle)`` : une alerte au même identifiant est mise à jour (ses chiffres), jamais doublée."""
    nouvelle = True

    def transformer(ligne):
        nonlocal nouvelle
        nouvelle = True
        courant = _propres(ligne)
        reste = []
        for a in courant["levees"]:
            if a.get("id") == alerte["id"]:
                nouvelle = False
                alerte["levee_le"] = a.get("levee_le") or alerte.get("levee_le")
                alerte["notifiee"] = bool(a.get("notifiee")) or bool(alerte.get("notifiee"))
            else:
                reste.append(a)
        courant["levees"] = [alerte, *reste][:LEVEES_MAX]
        return courant

    await stock.modifier(organization_id, cle(workflow_id), transformer)
    return alerte, nouvelle


async def marquer_notifiee(organization_id: int, workflow_id: int, identifiant: str) -> None:
    def transformer(ligne):
        courant = _propres(ligne)
        for a in courant["levees"]:
            if a.get("id") == identifiant:
                a["notifiee"] = True
        return courant

    await stock.modifier(organization_id, cle(workflow_id), transformer)
