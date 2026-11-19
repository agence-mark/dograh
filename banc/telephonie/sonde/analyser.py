"""Mesure, sur les paquets reçus par SIPp, l'instant où le son cesse.

Pour chaque mesure de la sonde (sonde.jsonl), ouvre la capture réseau du même
nom (<mesure>.pcap, prise dans le conteneur SIPp) et rend :

- retard_ms : temps entre T0 (la coupure, côté sonde) et l'arrivée chez SIPp du
  dernier paquet qui porte du son ;
- son_apres_t0_ms : durée de son arrivée chez SIPp après T0.

Les deux horloges sont celle du même noyau : les conteneurs du banc tournent sur
la même machine.

Sans dépendance : lecture du format pcap et décodage de la loi mu faits ici.
"""

from __future__ import annotations

import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

PORT_SON_SIPP = 6000
DUREE_PAQUET_MS = 20.0
# En dessous de ce niveau moyen (sur 32 768), un paquet est compté comme silence.
# Le ton de la sonde est autour de 5 600, le silence d'Asterisk à 0.
SEUIL_SON = 200.0


@dataclass(frozen=True)
class Paquet:
    t_ns: int
    sequence: int
    niveau: float


def _table_ulaw() -> list[int]:
    table = []
    for octet in range(256):
        valeur = ~octet & 0xFF
        signe = valeur & 0x80
        exposant = (valeur >> 4) & 0x07
        mantisse = valeur & 0x0F
        amplitude = ((mantisse << 3) + 0x84) << exposant
        amplitude -= 0x84
        table.append(-amplitude if signe else amplitude)
    return table


ULAW_VERS_PCM = _table_ulaw()


def niveau_moyen(charge: bytes) -> float:
    if not charge:
        return 0.0
    return (sum(ULAW_VERS_PCM[o] ** 2 for o in charge) / len(charge)) ** 0.5


def lire_paquets_son(
    chemin: Path, port_destination: int = PORT_SON_SIPP
) -> list[Paquet]:
    """Rend les paquets RTP en loi mu reçus sur le port de son de SIPp."""
    donnees = chemin.read_bytes()
    magie = donnees[:4]
    if magie in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        ordre = "<"
    elif magie in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        ordre = ">"
    else:
        raise ValueError(f"{chemin} n'est pas une capture pcap")
    en_nanosecondes = magie in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    (type_de_lien,) = struct.unpack(ordre + "I", donnees[20:24])
    if type_de_lien != 1:
        raise ValueError(f"type de lien {type_de_lien} non géré (Ethernet attendu)")

    paquets: list[Paquet] = []
    position = 24
    while position + 16 <= len(donnees):
        secondes, fraction, capture, _ = struct.unpack(
            ordre + "IIII", donnees[position : position + 16]
        )
        trame = donnees[position + 16 : position + 16 + capture]
        position += 16 + capture

        t_ns = secondes * 1_000_000_000 + (
            fraction if en_nanosecondes else fraction * 1000
        )
        if len(trame) < 14 + 20 + 8 + 12 or trame[12:14] != b"\x08\x00":
            continue
        ip = trame[14:]
        longueur_entete = (ip[0] & 0x0F) * 4
        if ip[9] != 17:  # UDP
            continue
        udp = ip[longueur_entete:]
        (port,) = struct.unpack("!H", udp[2:4])
        rtp = udp[8:]
        if port != port_destination or len(rtp) < 12 or rtp[0] >> 6 != 2:
            continue
        if rtp[1] & 0x7F != 0:  # 0 : PCMU, la loi mu
            continue
        (sequence,) = struct.unpack("!H", rtp[2:4])
        debut = 12 + (rtp[0] & 0x0F) * 4
        paquets.append(Paquet(t_ns, sequence, niveau_moyen(rtp[debut:])))
    return paquets


def mesurer(releve: dict, paquets: list[Paquet]) -> dict:
    t0 = releve["t0_ns"]
    sonores = [p for p in paquets if p.niveau >= SEUIL_SON]
    resultat: dict[str, object] = {
        "mesure": releve["mesure"],
        "extension": releve["extension"],
        "mode": releve["mode"],
        "commande": releve["commande"],
        "format_controle": releve["format_controle"],
        "paquets": len(paquets),
        "paquets_sonores": len(sonores),
    }
    if not t0 or not sonores:
        resultat["erreur"] = (
            releve.get("erreur") or "aucun son reçu chez SIPp ou T0 absent"
        )
        return resultat

    dernier = sonores[-1]
    apres_t0 = [p for p in sonores if p.t_ns > t0]
    suivants = [p for p in paquets if p.t_ns > dernier.t_ns]
    resultat.update(
        {
            "latence_aller_ms": round(
                (sonores[0].t_ns - releve["t_debut_son_ns"]) / 1e6, 1
            ),
            "retard_ms": round((dernier.t_ns - t0) / 1e6, 1),
            "son_apres_t0_ms": round(len(apres_t0) * DUREE_PAQUET_MS, 1),
            "paquets_de_silence_ensuite": len(suivants),
            "messages_asterisk": [
                m["texte"].split()[0]
                if not m["texte"].startswith("{")
                else m["texte"][:120]
                for m in releve["messages_recus"]
            ],
        }
    )
    return resultat


def principal(dossier: Path) -> int:
    fichier = dossier / "sonde.jsonl"
    if not fichier.exists():
        print(f"{fichier} absent : aucune mesure à analyser", file=sys.stderr)
        return 1
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        releve = json.loads(ligne)
        capture = dossier / f"{releve['mesure']}.pcap"
        if not capture.exists():
            print(json.dumps({"mesure": releve["mesure"], "erreur": "capture absente"}))
            continue
        print(
            json.dumps(mesurer(releve, lire_paquets_son(capture)), ensure_ascii=False)
        )
    return 0


if __name__ == "__main__":
    sys.exit(principal(Path(sys.argv[1] if len(sys.argv) > 1 else "/resultats")))
