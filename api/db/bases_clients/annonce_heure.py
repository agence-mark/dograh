"""[.mark] Mécanisme commun : annoncer une heure (lot 6, E-05, E-06, E-42, T-25). Pur : ni base, ni réseau, aucun métier.

Ce que le code annonce à quelqu'un qui attend : une heure fixe (« à 20 h 15 »), une tranche (« entre 20 h 15 et 20 h 30 ») ou une durée
(« dans 30 minutes »), au choix de celui qui règle. Trois entrées :

- le DÉLAI, en entier : celui du type d'attente (ou celui de la zone), jamais une addition « base + zone » ;
- la durée AJOUTÉE (coup de feu), par-dessus ; elle ne joue qu'à l'instant où l'heure est annoncée (une heure déjà annoncée garde la sienne) ;
- l'ATTENTE due à la capacité par quart d'heure : quand un quart d'heure est plein, on passe au suivant.

L'heure annoncée est toujours arrondie VERS LE HAUT : jamais une promesse plus tôt que le calcul. Toutes les heures sont aware ; le fuseau
sert seulement à dire l'heure du lieu.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

FORMATS = ("heure_fixe", "tranche", "duree")
PAS_HEURE_FIXE = 5  # minutes : une heure fixe se dit au multiple de 5 au-dessus
LARGEUR_TRANCHE = 15  # minutes : une tranche tient sur un quart d'heure, alignée sur le quart
QUART = 15
QUARTS_MAX = 16  # on ne cherche pas plus de quatre heures plus loin : au-delà, la capacité est dite pleine


@dataclass(frozen=True)
class Annonce:
    """Ce qui est annoncé. ``prete`` : l'heure retenue (arrondie vers le haut) ; ``debut`` et ``fin`` : la tranche (format ``tranche``)."""

    format: str
    prete: datetime
    minutes: int  # la durée annoncée à partir de maintenant, entière, arrondie vers le haut
    debut: datetime | None = None
    fin: datetime | None = None


def _vers_le_haut(instant: datetime, pas_minutes: int) -> datetime:
    """``instant`` arrondi au multiple de ``pas_minutes`` au-dessus (sur l'heure UTC : les pas de 5 et 15 divisent l'heure, tous les fuseaux
    de minutes entières donnent le même résultat)."""
    sans_reste = instant.replace(second=0, microsecond=0)
    if sans_reste < instant:
        sans_reste += timedelta(minutes=1)
    reste = sans_reste.minute % pas_minutes
    return sans_reste + timedelta(minutes=pas_minutes - reste) if reste else sans_reste


def quart_de(instant: datetime) -> datetime:
    """Le début du quart d'heure qui contient ``instant``."""
    return instant.replace(minute=instant.minute - instant.minute % QUART, second=0, microsecond=0)


def attente_par_quart(prete: datetime, charges: Mapping[datetime, int], capacite: int | None) -> int:
    """Les minutes à attendre parce que des quarts d'heure sont pleins. ``charges`` : le nombre déjà annoncé dans chaque quart (clé : son début).
    Sans capacité réglée (``None`` ou zéro) : aucune attente. Un quart est plein quand il a déjà ``capacite`` éléments ; on passe alors au début du
    quart suivant, jusqu'à en trouver un qui ne l'est pas (``QUARTS_MAX`` au plus : au-delà, on s'arrête là, la capacité est dite pleine)."""
    if not capacite:
        return 0
    quart = quart_de(prete)
    retenue = prete
    for _ in range(QUARTS_MAX):
        if charges.get(quart, 0) < capacite:
            break
        quart += timedelta(minutes=QUART)
        retenue = quart
    return max(0, round((retenue - prete).total_seconds() / 60))


def annoncer(maintenant: datetime, delai_minutes: int, ajout_minutes: int, attente_minutes: int, format_: str) -> Annonce:
    """L'annonce d'une demande faite ``maintenant`` : le délai en entier, plus la durée ajoutée, plus l'attente de capacité."""
    if format_ not in FORMATS:
        raise ValueError(f"Format d'annonce inconnu : {format_!r}")
    if maintenant.tzinfo is None:
        raise ValueError("L'instant doit être aware.")
    brute = maintenant + timedelta(minutes=delai_minutes + ajout_minutes + attente_minutes)
    if format_ == "duree":
        prete = _vers_le_haut(brute, 1)
        return Annonce("duree", prete, max(0, round((prete - maintenant).total_seconds() / 60)))
    if format_ == "heure_fixe":
        prete = _vers_le_haut(brute, PAS_HEURE_FIXE)
        return Annonce("heure_fixe", prete, max(0, round((prete - maintenant).total_seconds() / 60)))
    debut = _vers_le_haut(brute, QUART)
    return Annonce("tranche", debut, max(0, round((debut - maintenant).total_seconds() / 60)), debut, debut + timedelta(minutes=LARGEUR_TRANCHE))


def _heure_dite(instant: datetime, fuseau: ZoneInfo) -> str:
    local = instant.astimezone(fuseau)
    return f"{local.hour} h {local.minute:02d}" if local.minute else f"{local.hour} h"


def dite(annonce: Annonce, fuseau: ZoneInfo) -> str:
    """L'annonce en français, prête à être dite : « dans 30 minutes », « à 20 h 15 », « entre 20 h 15 et 20 h 30 »."""
    if annonce.format == "tranche" and annonce.debut and annonce.fin:
        return f"entre {_heure_dite(annonce.debut, fuseau)} et {_heure_dite(annonce.fin, fuseau)}"
    if annonce.format == "heure_fixe":
        return f"à {_heure_dite(annonce.prete, fuseau)}"
    if annonce.minutes >= 60:
        heures, minutes = divmod(annonce.minutes, 60)
        return f"dans {heures} h {minutes:02d}" if minutes else f"dans {heures} h"
    return f"dans {annonce.minutes} minute{'s' if annonce.minutes > 1 else ''}"
