"""[.mark] Module Restauration, lot 3 : l'adresse de chaque prise est en LISTE FERMÉE (D4, faille SSRF).

Jamais un champ libre : une adresse sortante n'est appelée que si elle commence exactement par une adresse de la fiche de la
prise (même schéma, même machine, même port, chemin dans le même dossier). Une adresse interne (la caisse de démo du lot 20)
n'est permise qu'au Labo (``labo=True``) ; ``ADRESSES_DE_DEMO`` est remplie par le lot 20 (``caisse_demo/adresse.py``).
"""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

from api.services.restauration.caisse_demo.adresse import adresse_de_la_caisse
from api.services.restauration.prises.fiches import FICHES

# Prise -> adresses internes de sa caisse de démo (lot 20). Jamais permises hors Labo (``labo=True`` seulement, posé par le branchement après contrôle).
# Seule la prise HubRise a une caisse de démo ; l'adresse est celle de CE serveur (la caisse de démo y est montée si l'interrupteur est allumé).
ADRESSES_DE_DEMO: dict[str, tuple[str, ...]] = {"hubrise": (adresse_de_la_caisse(),)}


class AdresseRefusee(ValueError):
    """L'adresse n'est pas dans la liste fermée de la prise."""


def adresses_permises(prise: str, *, labo: bool = False) -> tuple[str, ...]:
    return FICHES[prise].adresses_permises + (ADRESSES_DE_DEMO.get(prise, ()) if labo else ())


def _decouper(adresse: str):
    if not isinstance(adresse, str) or any(c in adresse for c in ("\\", "\r", "\n", "\t", " ")) or "@" in adresse.split("?", 1)[0]:
        raise AdresseRefusee("Adresse malformée.")
    morceaux = urlsplit(adresse)
    if morceaux.scheme not in ("http", "https") or not morceaux.hostname or morceaux.hostname.endswith("."):
        raise AdresseRefusee("Adresse malformée.")
    return morceaux


def _chemin_sur(chemin: str) -> bool:
    return not any(segment in ("..", ".") for segment in unquote(unquote(chemin)).split("/"))


def verifier_adresse(prise: str, adresse: str, *, labo: bool = False) -> str:
    """L'adresse, si et seulement si elle est dans la liste fermée de la prise ; sinon ``AdresseRefusee``."""
    voulue = _decouper(adresse)
    if voulue.fragment or voulue.username or voulue.password or not _chemin_sur(voulue.path):
        raise AdresseRefusee("Adresse refusée.")
    for permise in adresses_permises(prise, labo=labo):
        ok = _decouper(permise)
        dossier = ok.path.rstrip("/")
        if (
            (voulue.scheme, voulue.hostname, voulue.port) == (ok.scheme, ok.hostname, ok.port)
            and (voulue.path.rstrip("/") == dossier or voulue.path.startswith(dossier + "/"))
        ):
            return adresse
    raise AdresseRefusee(f"Adresse hors de la liste fermée de la prise {prise}.")
