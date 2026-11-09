"""[.mark] RA-B (R6, audit 06) : quels vrais appels le juge regarde (repris du « Contrôle qualité » de Dograh).

Trois filtres par agent, rangés avec le réglage « juge des vrais appels » (``file.py``) :

* **part jugée** (``part``, 1 à 100 %) : l'échantillonnage borne la dépense ; 100 = tous les appels, comme avant ;
* **durée minimale** (``duree_min_s``, 0 = aucune) : un raccroché de 3 s n'est pas jugé (évite les faux « raté ») ;
* **répondeurs exclus** (``repondeurs_exclus``) : un appel qui a fini sur un répondeur n'est pas jugé.

Défauts = comportement d'avant (tout est jugé). Pur : aucune lecture de base. Le tirage de la part est un hachage de
l'identifiant de l'appel : le même appel donne toujours la même réponse (rejuger ne change pas d'avis).
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Any

DUREE_MIN_MAX_S = 600
ETAT_TROP_COURT = "trop_court"
ETAT_REPONDEUR = "repondeur"
ETAT_NON_ECHANTILLONNE = "non_echantillonne"


@dataclass(frozen=True)
class ReglagesTri:
    part: int = 100
    duree_min_s: int = 0
    repondeurs_exclus: bool = False
    # Clôture, lot C : les critères du vécu que ce juge ne regarde PAS (tous regardés par défaut, comme avant).
    vecu_eteints: tuple[str, ...] = ()


def _entier(valeur: Any, defaut: int, bas: int, haut: int) -> int:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return defaut
    return max(bas, min(haut, int(valeur)))


def vecu_eteints_de(brut: Any) -> tuple[str, ...]:
    """Les identifiants connus d'une liste (l'ordre des critères, sans doublon) ; un identifiant inconnu ou une valeur illisible est ignoré."""
    from api.services.juge.verdicts import IDS_DU_VECU

    if not isinstance(brut, (list, tuple)):
        return ()
    demandes = {x for x in brut if isinstance(x, str)}
    return tuple(i for i in IDS_DU_VECU if i in demandes)


def lire(ligne: dict | None) -> ReglagesTri:
    """Les filtres d'une ligne de réglage ; une valeur illisible redonne le défaut, une valeur hors bornes est ramenée aux bornes."""
    ligne = ligne if isinstance(ligne, dict) else {}
    return ReglagesTri(
        part=_entier(ligne.get("part"), 100, 1, 100),
        duree_min_s=_entier(ligne.get("duree_min_s"), 0, 0, DUREE_MIN_MAX_S),
        repondeurs_exclus=ligne.get("repondeurs_exclus") is True,
        vecu_eteints=vecu_eteints_de(ligne.get("vecu_eteints")),
    )


def _est_un_repondeur(run: Any) -> bool:
    fiche = getattr(run, "gathered_context", None) or {}
    for cle in ("mapped_call_disposition", "call_disposition"):
        valeur = fiche.get(cle)
        if isinstance(valeur, str) and valeur.strip().lower().startswith("voicemail"):
            return True
    return False


def decision(run: Any, reglages: ReglagesTri) -> tuple[bool, str | None]:
    """``(juger, etat)`` : ``etat`` dit pourquoi l'appel n'est pas jugé. ⛔ Ne lève jamais (dans le doute : juger)."""
    try:
        if reglages.repondeurs_exclus and _est_un_repondeur(run):
            return False, ETAT_REPONDEUR
        duree = (getattr(run, "usage_info", None) or {}).get("call_duration_seconds")
        if reglages.duree_min_s and isinstance(duree, (int, float)) and duree < reglages.duree_min_s:
            return False, ETAT_TROP_COURT
        if reglages.part < 100 and zlib.crc32(str(run.id).encode()) % 100 >= reglages.part:
            return False, ETAT_NON_ECHANTILLONNE
    except Exception:  # noqa: BLE001
        return True, None
    return True, None
