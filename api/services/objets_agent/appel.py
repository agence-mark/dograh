"""[.mark] Lot F7 : les objets dans l'appel (D107, D113).

Lus UNE fois au décroché, avec la fiche (``lire_lappel`` : la même copie, la même lecture de la base),
puis posés dans le contexte de l'appel sous leur nom : l'injection existante les rend partout où
``{{nom}}`` apparaît (prompts de toutes les étapes, phrases, consignes), pour tout l'appel et tous les
agents du groupe, qui partagent ce contexte.

- base lue : chaque objet = son texte (``rendu.py``) ; une valeur déjà dans le contexte (un rejeu, le
  pré-appel) est gardée, comme pour la fiche ;
- base rattachée mais injoignable (ou illisible) : chaque nom connu reçoit ``{{nom}}`` lui-même, la variable
  reste donc écrite telle quelle au lieu d'être rendue vide ; l'estampille ``injoignable`` donne un
  incident après l'appel (``incidents_des_objets``) ; l'appel continue ;
- sans base, ou aucun objet : rien ne change, pas même l'estampille (R1, X2).

⛔ Ne lève jamais.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from api.services.objets_agent.rendu import rendre

BRIQUE_INCIDENT = "objets_agent"
CAUSE_INJOIGNABLE = "objets_non_lus_au_decroche"


def _vide(valeur: Any) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def injecter_objets(contexte: dict, lecture) -> tuple[dict, dict | None]:
    """The context with the objects, and the stamp for ``runtime_configuration["objets"]`` (``None``:
    nothing to say, the call of before)."""
    try:
        etat = getattr(lecture, "objets_etat", "sans_base")
        if etat == "lu":
            objets = list(getattr(lecture, "objets", None) or [])
            if not objets:
                return contexte, None
            enrichi = dict(contexte)
            poses, gardes = [], []
            for objet in objets:
                if _vide(enrichi.get(objet.nom)):
                    enrichi[objet.nom] = rendre(objet)
                    poses.append(objet.nom)
                else:
                    gardes.append(objet.nom)
            estampille: dict = {"etat": "lu", "poses": poses}
            if gardes:
                estampille["gardes"] = gardes
            return enrichi, estampille
        if etat == "injoignable":
            enrichi = dict(contexte)
            noms = [n for n in getattr(lecture, "objets_noms", None) or [] if isinstance(n, str)]
            for nom in noms:
                if _vide(enrichi.get(nom)):
                    enrichi[nom] = "{{" + nom + "}}"
            return enrichi, {"etat": "injoignable", "noms": noms}
        return contexte, None
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.error(f"[.mark] Objects not injected, the call goes on without them: {erreur!r}")
        return contexte, None


def incidents_des_objets(runtime: dict | None, debut: datetime) -> list[dict]:
    """The incident of a call whose objects could not be read at pick-up (as ``mark.noter_incident``
    files them: a brick and a cause). None otherwise."""
    estampille = (runtime or {}).get("objets") if isinstance(runtime, dict) else None
    if isinstance(estampille, dict) and estampille.get("etat") == "injoignable":
        return [{"brique": BRIQUE_INCIDENT, "cause": CAUSE_INJOIGNABLE, "debut": debut.isoformat()}]
    return []
