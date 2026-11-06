"""[.mark] U11 (§ 17) : la liste de contrôle vocale « Contrôles avant publication ».

Les points sont de la DONNÉE (famille ``controles-avant-publication`` de la bibliothèque, élément ``liste-vocale``) : chaque
valeur est traduite en réglage de notre fork, ou marquée « sans équivalent chez nous » avec sa raison. Le fichier versé sert de
secours si la bibliothèque n'est pas lisible. Ce module ne connaît aucun mot du métier.

⛔ Simulation d'abord : ``evaluer`` ne lit que, ``corrections`` propose, rien n'est écrit ici. L'écriture passe par l'action de
réglage du builder, seulement sur accord (``ids`` choisis), puis un nouveau contrôle complet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

FAMILLE = "controles-avant-publication"
ELEMENT = "liste-vocale"
FICHIER = Path(__file__).resolve().parents[1] / "builder" / "versement" / "contenu" / FAMILLE / f"{ELEMENT}.json"

OK = "ok"
ECART = "ecart"
SANS_EQUIVALENT = "sans_equivalent"


def _points_du_fichier() -> list[dict[str, Any]]:
    try:
        return list(json.loads(FICHIER.read_text(encoding="utf-8"))["contenu"]["points"])
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[publication] liste vocale non lue ({type(erreur).__name__})")
        return []


async def points() -> list[dict[str, Any]]:
    """Les points de la bibliothèque (version courante), sinon ceux du fichier versé."""
    try:
        from api.services.builder.bibliotheque import service

        element = await service.element_ou_none(FAMILLE, ELEMENT)
        lus = (element.courante.contenu or {}).get("points") if element else None
        if isinstance(lus, list) and lus:
            return [p for p in lus if isinstance(p, dict)]
    except Exception as erreur:  # noqa: BLE001 -- bibliothèque illisible : le fichier versé, jamais une panne
        logger.warning(f"[publication] bibliothèque non lue pour la liste vocale ({type(erreur).__name__})")
    return _points_du_fichier()


def _defaut_du_fork(cle: str) -> Any:
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

    champ = WorkflowConfigurationDefaults.model_fields.get(cle)
    return champ.get_default(call_default_factory=True) if champ is not None else None


def _valeur(configurations: dict[str, Any], regle: dict[str, Any]) -> Any:
    cle = regle["cle"]
    valeur = configurations.get(cle)
    if valeur is None:
        valeur = _defaut_du_fork(cle)
    if valeur is None:
        valeur = regle.get("defaut_effectif")
    return valeur


def _non_vide(valeur: Any) -> bool:
    return bool(valeur) if not isinstance(valeur, str) else bool(valeur.strip())


def _regle_de_motif(configurations: dict[str, Any], regle: dict[str, Any]) -> tuple[bool, Any, str]:
    from api.services.phrases.catalogue import MOTIFS
    from api.services.phrases.regles import regles_de

    motif = MOTIFS.get(regle["motif"])
    if motif is None:
        return True, None, ""
    posees = [r for r in regles_de(configurations) if r.motif == motif.id]
    if regle["type"] == "motif_actif":
        actif = any(r.active for r in posees) if posees else motif.actif_par_defaut
        return actif, "on" if actif else "off", f"the sentence « {motif.id} » is said by the code"
    vides = [r for r in posees if r.active and not [v for v in r.variantes if str(v).strip()]]
    return not vides, f"{len(vides)} empty", f"the sentence « {motif.id} » is never empty"


def _evaluer_une_regle(configurations: dict[str, Any], regle: dict[str, Any]) -> tuple[bool, Any, str, dict[str, Any] | None]:
    """(conforme, valeur actuelle, ce qui est attendu, correction proposée)."""
    genre = regle.get("type")
    if genre in ("motif_actif", "motif_non_vide"):
        ok, actuel, attendu = _regle_de_motif(configurations, regle)
        return ok, actuel, attendu, None
    valeur = _valeur(configurations, regle)
    cle = regle["cle"]
    correction = {cle: regle["correction"]} if "correction" in regle else None
    if genre == "plage":
        borne = f"{regle['min']} to {regle['max']} {regle.get('unite', '')}".strip()
        ok = isinstance(valeur, (int, float)) and not isinstance(valeur, bool) and regle["min"] <= valeur <= regle["max"]
        return ok, valeur, f"{cle} from {borne}", correction
    if genre == "min":
        ok = isinstance(valeur, (int, float)) and not isinstance(valeur, bool) and valeur >= regle["min"]
        return ok, valeur, f"{cle} at least {regle['min']}", correction
    if genre == "vrai":
        ok = valeur is True
        if not ok and regle.get("ou_non_vide"):
            ok = _non_vide(configurations.get(regle["ou_non_vide"]))
        return ok, valeur, f"{cle} on", correction
    if genre == "non_vide":
        return _non_vide(valeur), "set" if _non_vide(valeur) else "empty", f"{cle} filled", correction
    return True, valeur, "", None


def evaluer(liste: list[dict[str, Any]], configurations: dict[str, Any]) -> list[dict[str, Any]]:
    """Un résultat par point : ``ok`` / ``ecart`` / ``sans_equivalent`` (jamais un point muet). Aucune écriture."""
    resultats: list[dict[str, Any]] = []
    for point in liste:
        base = {"id": point.get("id"), "libelle": point.get("libelle"), "raison": point.get("raison") or ""}
        regles = point.get("regles")
        if not regles:
            resultats.append({**base, "statut": SANS_EQUIVALENT, "ecarts": [], "corrections": None, "corrige_seul": False})
            continue
        ecarts: list[dict[str, Any]] = []
        corrections: dict[str, Any] = {}
        for regle in regles:
            ok, actuel, attendu, correction = _evaluer_une_regle(configurations, regle)
            if not ok:
                ecarts.append({"reglage": regle.get("cle") or regle.get("motif"), "actuel": actuel, "attendu": attendu})
                if correction:
                    corrections.update(correction)
        resultats.append(
            {
                **base,
                "statut": ECART if ecarts else OK,
                "ecarts": ecarts,
                # Une correction n'est proposée que si le point se corrige seul (sinon : conseil, une personne choisit).
                "corrections": corrections or None if point.get("corrige_seul") else None,
                "corrige_seul": bool(point.get("corrige_seul")),
            }
        )
    return resultats


def corrections_acceptees(resultats: list[dict[str, Any]], ids: list[str]) -> dict[str, Any]:
    """Les valeurs à écrire pour les points ACCEPTÉS (ids choisis par une personne). Rien d'autre."""
    valeurs: dict[str, Any] = {}
    for r in resultats:
        if r["id"] in ids and r["statut"] == ECART and r.get("corrections"):
            valeurs.update(r["corrections"])
    return valeurs
