"""Fabrique la voix de l'appelant du banc : une capture réseau que SIPp rejoue.

L'appelant ne dit pas de mots : il alterne des silences et un son, à des heures
connues. Le faux fournisseur de transcription ne regarde que le niveau du son,
et la mesure de latence lit ces mêmes paquets sur le réseau. Tout se refabrique
à l'identique sur n'importe quel poste.

    fabriquer_voix.py <sortie.pcap> <plan>

Le plan est une suite de durées en millisecondes : « s » pour un silence, « v »
pour une voix de synthèse, « t » pour un ton pur. Exemple :
s4000,v1000,s3000,v1000,s3000.

- La voix de synthèse est une voyelle qui bouge (hauteur et timbre glissent
  d'une voyelle à l'autre). Le détecteur de voix du fork (Silero) la prend pour
  de la parole, ce que le chronomètre par tour du fork exige pour mesurer un tour.
- Le ton pur n'est pas de la parole pour ce détecteur : seul le fournisseur de
  transcription ouvre alors le tour.

SIPp envoie un paquet de 20 ms toutes les 20 ms, silences compris : sans paquet,
Asterisk ne transmet rien au fork et aucun silence ne serait vu.

Sans dépendance : le format pcap, l'en-tête RTP et la loi mu sont écrits ici.
"""

from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

FREQUENCE_ECHANTILLONNAGE = 8000
ECHANTILLONS_PAR_PAQUET = 160  # 20 ms
FREQUENCE_DU_TON_HZ = 440.0
AMPLITUDE_DU_TON = 8000
SILENCE_ULAW = 0xFF


def coder_ulaw(echantillon: int) -> int:
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


# Les trois premiers formants de quatre voyelles (Hz) et leurs largeurs.
VOYELLES = ((730, 1090, 2440), (270, 2290, 3010), (300, 870, 2240), (530, 1840, 2480))
LARGEURS_HZ = (90, 110, 170)
HAUTEUR_HZ = 120.0
DUREE_D_UNE_VOYELLE_MS = 160


def lire_plan(plan: str) -> list[tuple[str, int]]:
    """« s4000,v1000 » vers [("s", 4000), ("v", 1000)] : (genre, durée en ms)."""
    etapes = []
    for etape in plan.split(","):
        genre, duree = etape[:1], etape[1:]
        if genre not in ("s", "t", "v") or not duree.isdigit() or int(duree) % 20:
            raise ValueError(
                f"étape illisible (s, t ou v, durée multiple de 20 ms) : {etape}"
            )
        etapes.append((genre, int(duree)))
    return etapes


def ton(nombre: int) -> list[int]:
    pas = 2 * math.pi * FREQUENCE_DU_TON_HZ / FREQUENCE_ECHANTILLONNAGE
    return [int(AMPLITUDE_DU_TON * math.sin(pas * rang)) for rang in range(nombre)]


def voix(nombre: int) -> list[int]:
    """Une voyelle qui bouge : un train d'impulsions à la hauteur d'une voix,
    passé dans trois résonateurs dont les fréquences glissent d'une voyelle à la
    suivante. Niveau constant : aucun creux ne peut passer pour un silence."""
    par_voyelle = FREQUENCE_ECHANTILLONNAGE * DUREE_D_UNE_VOYELLE_MS // 1000
    memoires = [[0.0, 0.0] for _ in LARGEURS_HZ]
    phase = 0.0
    brut = []
    for rang in range(nombre):
        numero, reste = divmod(rang, par_voyelle)
        depart = VOYELLES[numero % len(VOYELLES)]
        arrivee = VOYELLES[(numero + 1) % len(VOYELLES)]
        glissement = reste / par_voyelle
        hauteur = HAUTEUR_HZ * (
            1 + 0.12 * math.sin(2 * math.pi * 3.1 * rang / FREQUENCE_ECHANTILLONNAGE)
        )
        phase += hauteur / FREQUENCE_ECHANTILLONNAGE
        impulsion = 0.0
        if phase >= 1.0:
            phase -= 1.0
            impulsion = 1.0
        valeur = 0.0
        for formant, largeur in enumerate(LARGEURS_HZ):
            frequence = (
                depart[formant] + (arrivee[formant] - depart[formant]) * glissement
            )
            rayon = math.exp(-math.pi * largeur / FREQUENCE_ECHANTILLONNAGE)
            sortie = (
                (1 - rayon) * impulsion
                + 2
                * rayon
                * math.cos(2 * math.pi * frequence / FREQUENCE_ECHANTILLONNAGE)
                * memoires[formant][0]
                - rayon * rayon * memoires[formant][1]
            )
            memoires[formant][1], memoires[formant][0] = memoires[formant][0], sortie
            valeur += sortie
        brut.append(valeur)
    crete = max((abs(valeur) for valeur in brut), default=1.0) or 1.0
    return [int(AMPLITUDE_DU_TON * valeur / crete) for valeur in brut]


def charges(plan: list[tuple[str, int]]) -> list[bytes]:
    """Le son de chaque paquet de 20 ms. Chaque prise de parole repart de zéro :
    deux prises de parole de même durée portent les mêmes octets."""
    paquets = []
    for genre, duree_ms in plan:
        nombre = duree_ms // 20
        if genre == "s":
            paquets.extend([bytes([SILENCE_ULAW]) * ECHANTILLONS_PAR_PAQUET] * nombre)
            continue
        son = (ton if genre == "t" else voix)(nombre * ECHANTILLONS_PAR_PAQUET)
        paquets.extend(
            bytes(
                coder_ulaw(echantillon)
                for echantillon in son[debut : debut + ECHANTILLONS_PAR_PAQUET]
            )
            for debut in range(0, len(son), ECHANTILLONS_PAR_PAQUET)
        )
    return paquets


def somme_ip(entete: bytes) -> int:
    total = sum(struct.unpack(f"!{len(entete) // 2}H", entete))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def trame(charge: bytes, rang: int) -> bytes:
    """Un paquet Ethernet, IPv4, UDP, RTP (PCMU). SIPp ne garde que le RTP : les
    adresses et les ports écrits ici sont remplacés par ceux de l'appel."""
    rtp = struct.pack(
        "!BBHII",
        0x80,  # version 2
        0x80 if rang == 0 else 0x00,  # type 0 (PCMU), marqueur sur le premier paquet
        rang & 0xFFFF,
        (rang * ECHANTILLONS_PAR_PAQUET) & 0xFFFFFFFF,
        0x42414E43,  # source : « BANC »
    )
    udp = struct.pack("!HHHH", 6000, 6000, 8 + len(rtp) + len(charge), 0)
    longueur_ip = 20 + len(udp) + len(rtp) + len(charge)
    ip = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, longueur_ip, rang & 0xFFFF, 0, 64, 17, 0,
        bytes([10, 0, 0, 1]), bytes([10, 0, 0, 2]),
    )  # fmt: skip
    ip = ip[:10] + struct.pack("!H", somme_ip(ip)) + ip[12:]
    ethernet = bytes(6) + bytes(6) + struct.pack("!H", 0x0800)
    return ethernet + ip + udp + rtp + charge


def ecrire(sortie: Path, paquets: list[bytes]) -> None:
    sortie.parent.mkdir(parents=True, exist_ok=True)
    with sortie.open("wb") as fichier:
        # En-tête pcap : microsecondes, Ethernet.
        fichier.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for rang, charge in enumerate(paquets):
            contenu = trame(charge, rang)
            instant_us = rang * 20_000
            fichier.write(
                struct.pack(
                    "<IIII",
                    instant_us // 1_000_000,
                    instant_us % 1_000_000,
                    len(contenu),
                    len(contenu),
                )
            )
            fichier.write(contenu)


def principal(arguments: list[str]) -> int:
    if len(arguments) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    sortie, plan = Path(arguments[0]), lire_plan(arguments[1])
    paquets = charges(plan)
    ecrire(sortie, paquets)
    print(f"{sortie} : {len(paquets)} paquets, {len(paquets) * 20} ms")
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
