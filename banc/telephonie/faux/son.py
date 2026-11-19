"""Le son des faux fournisseurs : un ton pur de durée connue, et le niveau d'un bloc reçu.

Sans dépendance : le son est du PCM 16 bits petit-boutiste, un seul canal, et la
loi mu est codée ici pour le cas où une voix la demanderait.
"""

from __future__ import annotations

import array
import math
import sys

FREQUENCE_DU_TON_HZ = 660.0
AMPLITUDE_DU_TON = 8000


def _echantillons(duree_ms: int, frequence_echantillonnage: int) -> array.array[int]:
    nombre = frequence_echantillonnage * duree_ms // 1000
    pas = 2 * math.pi * FREQUENCE_DU_TON_HZ / frequence_echantillonnage
    return array.array(
        "h", (int(AMPLITUDE_DU_TON * math.sin(pas * rang)) for rang in range(nombre))
    )


def fabriquer_ton_pcm(duree_ms: int, frequence_echantillonnage: int) -> bytes:
    """Un ton pur en PCM 16 bits. Même durée et même fréquence : mêmes octets."""
    echantillons = _echantillons(duree_ms, frequence_echantillonnage)
    if sys.byteorder == "big":
        echantillons.byteswap()
    return echantillons.tobytes()


def _coder_ulaw(echantillon: int) -> int:
    """Un échantillon 16 bits vers un octet en loi mu (G.711)."""
    biais, plafond = 0x84, 32635
    signe = 0x80 if echantillon < 0 else 0x00
    valeur = min(abs(echantillon), plafond) + biais
    exposant = 7
    masque = 0x4000
    while exposant > 0 and not valeur & masque:
        exposant -= 1
        masque >>= 1
    mantisse = (valeur >> (exposant + 3)) & 0x0F
    return ~(signe | (exposant << 4) | mantisse) & 0xFF


def fabriquer_ton_ulaw(duree_ms: int) -> bytes:
    """Le même ton en loi mu à 8 000 Hz."""
    return bytes(
        _coder_ulaw(echantillon) for echantillon in _echantillons(duree_ms, 8000)
    )


def niveau(bloc: bytes) -> float:
    """Niveau moyen (racine de la moyenne des carrés) d'un bloc PCM 16 bits."""
    utile = len(bloc) - len(bloc) % 2
    if utile == 0:
        return 0.0
    echantillons = array.array("h")
    echantillons.frombytes(bloc[:utile])
    if sys.byteorder == "big":
        echantillons.byteswap()
    return math.sqrt(
        sum(valeur * valeur for valeur in echantillons) / len(echantillons)
    )
