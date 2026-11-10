"""[.mark] Correctifs d'écran, point 15 : lire le TYPE RÉEL et les dimensions d'une image de logo, d'après ses octets.

Jamais d'après l'extension ni le ``Content-Type`` envoyé (le client les écrit comme il veut). PNG, JPEG et WebP seulement : un
SVG (du texte qui peut porter du script), un GIF renommé ou un faux PNG sont refusés. Pillow n'est pas une dépendance du projet :
on lit les signatures et les en-têtes à la main (octets bornés, aucune boucle sans fin).

Les règles (décision d'Evan, 10/11) : 1 Mo au plus, côté de 128 à 1024 px, presque carré (largeur/hauteur et hauteur/largeur
au plus 1,25 ; 512 px conseillé).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

OCTETS_MAX = 1_048_576
COTE_MIN = 128
COTE_MAX = 1024
RATIO_MAX = 1.25

TYPES = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}
EXTENSIONS = {"png": "png", "jpeg": "jpg", "webp": "webp"}

# Les marqueurs JPEG « début de trame » qui portent les dimensions (tous sauf DHT C4, JPG C8, DAC CC).
_SOF = frozenset({0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})


class ErreurLogo(Exception):
    """Un logo refusé : ``statut`` HTTP, ``code`` stable (l'écran le traduit), ``message`` court pour le journal."""

    def __init__(self, statut: int, code: str, message: str):
        super().__init__(message)
        self.statut = statut
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ImageLue:
    format: str  # "png" | "jpeg" | "webp"
    largeur: int
    hauteur: int

    @property
    def type_mime(self) -> str:
        return TYPES[self.format]

    @property
    def extension(self) -> str:
        return EXTENSIONS[self.format]


def _png(d: bytes) -> tuple[int, int] | None:
    if len(d) < 24 or d[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", d[16:24])


def _jpeg(d: bytes) -> tuple[int, int] | None:
    i, n = 2, len(d)
    while i + 4 <= n:
        if d[i] != 0xFF:
            return None
        while i < n and d[i] == 0xFF:  # octets de remplissage
            i += 1
        if i >= n:
            return None
        marqueur = d[i]
        i += 1
        if marqueur in (0x01, 0xD8) or 0xD0 <= marqueur <= 0xD7:
            continue  # marqueurs sans longueur
        if marqueur in (0xD9, 0xDA):
            return None  # fin d'image ou début des données : pas de trame lue
        if i + 2 > n:
            return None
        longueur = struct.unpack(">H", d[i : i + 2])[0]
        if marqueur in _SOF:
            if i + 7 > n:
                return None
            hauteur, largeur = struct.unpack(">HH", d[i + 3 : i + 7])
            return largeur, hauteur
        if longueur < 2:
            return None
        i += longueur
    return None


def _webp(d: bytes) -> tuple[int, int] | None:
    if len(d) < 30:
        return None
    morceau = d[12:16]
    if morceau == b"VP8 ":  # avec pertes
        if d[23:26] != b"\x9d\x01\x2a":
            return None
        return struct.unpack("<HH", d[26:30])[0] & 0x3FFF, struct.unpack("<HH", d[26:30])[1] & 0x3FFF
    if morceau == b"VP8L":  # sans perte
        if d[20] != 0x2F:
            return None
        bits = struct.unpack("<I", d[21:25])[0]
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if morceau == b"VP8X":  # étendu
        largeur = int.from_bytes(d[24:27], "little") + 1
        hauteur = int.from_bytes(d[27:30], "little") + 1
        return largeur, hauteur
    return None


def lire_image(octets: bytes) -> ImageLue:
    """Le format réel et les dimensions, ou une ``ErreurLogo`` (415 type, 422 dimensions, 400 vide, 413 trop lourd)."""
    if not octets:
        raise ErreurLogo(400, "logo_vide", "The file is empty.")
    if len(octets) > OCTETS_MAX:
        raise ErreurLogo(413, "logo_trop_lourd", "The logo is larger than 1 MB.")
    if octets[:8] == b"\x89PNG\r\n\x1a\n":
        format_, dimensions = "png", _png(octets)
    elif octets[:3] == b"\xff\xd8\xff":
        format_, dimensions = "jpeg", _jpeg(octets)
    elif octets[:4] == b"RIFF" and octets[8:12] == b"WEBP":
        format_, dimensions = "webp", _webp(octets)
    else:
        raise ErreurLogo(415, "logo_format", "Only PNG, JPEG and WebP images are accepted.")
    if dimensions is None or dimensions[0] < 1 or dimensions[1] < 1:
        raise ErreurLogo(415, "logo_illisible", "The image could not be read.")
    largeur, hauteur = dimensions
    if not (COTE_MIN <= largeur <= COTE_MAX and COTE_MIN <= hauteur <= COTE_MAX):
        raise ErreurLogo(422, "logo_dimensions", f"Each side must be between {COTE_MIN} and {COTE_MAX} px.")
    if largeur / hauteur > RATIO_MAX or hauteur / largeur > RATIO_MAX:
        raise ErreurLogo(422, "logo_ratio", "The logo must be almost square (ratio of 1.25 at most).")
    return ImageLue(format_, largeur, hauteur)
