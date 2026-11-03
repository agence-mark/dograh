"""[.mark] Les réglages posés par .mark sur un jeton de widget (domaines à part) : plafonds, durée, limite par adresse.

Stockés dans ``embed_tokens.reglages_mark`` (JSON), jamais dans ``settings`` (l'apparence, que le client règle).
Une valeur absente, illisible ou hors bornes vaut sa valeur par défaut : un réglage cassé ne coupe jamais le
widget et ne le laisse jamais sans plafond. Les valeurs par défaut sont COÛTEUSES si elles sont trop larges et
RESTRICTIVES si elles sont trop serrées : elles sont écrites ici, testées, et réglables à l'écran (« Réglages .mark »).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Valeurs par défaut (décision de nuit, voir sa-etat.md) : un site ordinaire n'est pas gêné, un abus coûte peu.
PLAFOND_CONVERSATIONS_MOIS_DEFAUT = 500
PLAFOND_MINUTES_MOIS_DEFAUT = 1500
DUREE_MAX_DEFAUT_S = 600  # D179 / plan v4 : 600 s, de 60 à 3 600
DUREE_MAX_MIN_S = 60
DUREE_MAX_MAX_S = 3600
SESSIONS_PAR_HEURE_ET_IP_DEFAUT = 10  # plan v4 : 10 par défaut
SESSIONS_PAR_HEURE_ET_IP_MAX = 1000
PLAFOND_MAX = 1_000_000


def _entier(valeur: Any, defaut: int, mini: int, maxi: int) -> int:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return defaut
    n = int(valeur)
    return n if mini <= n <= maxi else defaut


@dataclass(frozen=True)
class ReglagesMark:
    plafond_conversations_mois: int = PLAFOND_CONVERSATIONS_MOIS_DEFAUT
    plafond_minutes_mois: int = PLAFOND_MINUTES_MOIS_DEFAUT
    duree_max_s: int = DUREE_MAX_DEFAUT_S
    sessions_par_heure_et_ip: int = SESSIONS_PAR_HEURE_ET_IP_DEFAUT

    @classmethod
    def depuis(cls, brut: Mapping | None) -> "ReglagesMark":
        brut = brut if isinstance(brut, Mapping) else {}
        return cls(
            plafond_conversations_mois=_entier(
                brut.get("plafond_conversations_mois"), PLAFOND_CONVERSATIONS_MOIS_DEFAUT, 1, PLAFOND_MAX
            ),
            plafond_minutes_mois=_entier(
                brut.get("plafond_minutes_mois"), PLAFOND_MINUTES_MOIS_DEFAUT, 1, PLAFOND_MAX
            ),
            duree_max_s=_entier(brut.get("duree_max_s"), DUREE_MAX_DEFAUT_S, DUREE_MAX_MIN_S, DUREE_MAX_MAX_S),
            sessions_par_heure_et_ip=_entier(
                brut.get("sessions_par_heure_et_ip"),
                SESSIONS_PAR_HEURE_ET_IP_DEFAUT,
                1,
                SESSIONS_PAR_HEURE_ET_IP_MAX,
            ),
        )

    def en_json(self) -> dict:
        return {
            "plafond_conversations_mois": self.plafond_conversations_mois,
            "plafond_minutes_mois": self.plafond_minutes_mois,
            "duree_max_s": self.duree_max_s,
            "sessions_par_heure_et_ip": self.sessions_par_heure_et_ip,
        }
