"""[.mark] Correctifs d'écran, point 15 : le logo d'une organisation cliente.

* **La référence** : ``MARK_LOGO`` = ``{"cle", "version", "type", "octets", "largeur", "hauteur"}`` dans
  ``organization_configurations`` (même table que le nom d'affichage, aucune migration).
* **Le fichier** : le stockage de fichiers du projet (``services/storage.py``, MinIO ou S3), sous
  ``mark/logos/<organisation>/<version>.<ext>``. Une clé NEUVE à chaque remplacement : le navigateur ne garde jamais l'ancien
  logo en cache, et un échec en route laisse l'ancien intact.
* **Servi** : jamais par un seau public ni par un lien non signé (le lien MinIO du projet n'est pas signé) ; la route
  ``GET /espaces/{id}/logo`` lit le fichier et le rend, derrière la session et le contrôle d'organisation. ``GET /espaces``
  ne donne que la ``logo_version`` (de quoi savoir s'il y a un logo et quand il a changé).
* Le type réel et les dimensions sont lus dans les octets (``image_logo``), jamais d'après l'extension ou le Content-Type.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from pathlib import Path

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.services.equipe_mark.image_logo import ErreurLogo, lire_image
from api.services.storage import storage_fs

_cle_logo = OrganizationConfigurationKey.MARK_LOGO.value


# --- le stockage de fichiers (une couture : les tests la remplacent par une mémoire) -----------------------------

# Bonnes pratiques du serveur : chaque appel externe a un délai, jamais d'attente infinie (un stockage injoignable rend un 503 net).
DELAI_STOCKAGE_S = 15.0


async def _avec_delai(appel):
    try:
        return await asyncio.wait_for(appel, DELAI_STOCKAGE_S)
    except ErreurLogo:
        raise
    except Exception as erreur:  # noqa: BLE001 -- délai, connexion refusée, refus du stockage : un seul message pour l'écran
        logger.warning(f"[espaces] stockage du logo indisponible ({type(erreur).__name__})")
        raise ErreurLogo(503, "logo_stockage", "The file storage did not answer.") from None


async def ecrire_octets(cle: str, donnees: bytes) -> None:
    if not await _avec_delai(storage_fs.acreate_file_from_bytes(cle, donnees)):
        raise ErreurLogo(503, "logo_stockage", "The file could not be stored.")


def _effacer_le_temporaire(chemin: str) -> None:
    try:
        os.unlink(chemin)
    except OSError:
        pass


async def _telecharger(cle: str) -> bytes | None:
    """Télécharge dans un fichier temporaire, lu puis effacé.

    Le délai de ``_avec_delai`` annule CETTE attente, pas le téléchargement (``shield``) : le fichier est donc encore ouvert en
    écriture par la tâche de fond au moment de la coupure. Effacé tout de suite il pourrait être recréé par elle ; on le
    supprime donc quand la tâche finit (rappel), jamais avant.
    """
    descripteur, chemin = tempfile.mkstemp()
    os.close(descripteur)
    tache = asyncio.ensure_future(storage_fs.adownload_file(cle, chemin))
    try:
        trouve = await asyncio.shield(tache)
        octets = await asyncio.to_thread(Path(chemin).read_bytes) if trouve else None
    except BaseException:  # délai, annulation, stockage en erreur
        if tache.done():
            if not tache.cancelled():
                tache.exception()  # lu, pour qu'aucune erreur ne reste « jamais récupérée »
            _effacer_le_temporaire(chemin)
        else:
            tache.add_done_callback(lambda t: (t.cancelled() or t.exception(), _effacer_le_temporaire(chemin)))
        raise
    _effacer_le_temporaire(chemin)
    return octets


async def lire_octets(cle: str) -> bytes | None:
    return await _avec_delai(_telecharger(cle))


async def supprimer_octets(cle: str) -> None:
    try:
        await asyncio.wait_for(storage_fs.adelete_file(cle), DELAI_STOCKAGE_S)
    except Exception:  # noqa: BLE001 -- un fichier déjà parti, ou un stockage qui ne répond pas, ne bloque pas le retrait
        logger.info("[espaces] fichier de logo non supprimé (absent ou stockage injoignable)")


# --- le geste ----------------------------------------------------------------------------------------------------


def _cle_de_stockage(organization_id: int, version: str, extension: str) -> str:
    return f"mark/logos/{organization_id}/{version}.{extension}"


async def _lire_reference(organization_id: int) -> dict | None:
    ligne = await db_client.get_configuration(organization_id, _cle_logo)
    valeur = getattr(ligne, "value", None)
    return valeur if isinstance(valeur, dict) and valeur.get("cle") else None


async def versions(organisations: list[int]) -> dict[int, str]:
    """La version du logo de chacune des organisations qui en ont un (une seule lecture, filtrée par la base)."""
    brut = await db_client.valeurs_de_configuration(_cle_logo, organisations)
    return {i: v["version"] for i, v in brut.items() if v.get("cle") and v.get("version")}


# Un verrou par organisation : deux poses ou un retrait simultanés (même processus) passent l'un après l'autre.
_verrous: dict[int, asyncio.Lock] = {}


def _verrou(organization_id: int) -> asyncio.Lock:
    return _verrous.setdefault(organization_id, asyncio.Lock())


async def remplacer(organization_id: int, octets: bytes) -> dict:
    """Contrôle l'image puis la range ; rend la référence posée. ``ErreurLogo`` si l'image est refusée.

    Jamais de fichier orphelin : la référence remplacée est relue **juste avant** d'écrire la nôtre (c'est elle dont on efface le
    fichier), et si une autre pose, d'un autre processus, nous a dépassés, c'est notre fichier qu'on efface.
    """
    image = lire_image(octets)
    version = uuid.uuid4().hex[:16]
    cle = _cle_de_stockage(organization_id, version, image.extension)
    await ecrire_octets(cle, octets)
    reference = {
        "cle": cle,
        "version": version,
        "type": image.type_mime,
        "octets": len(octets),
        "largeur": image.largeur,
        "hauteur": image.hauteur,
    }
    async with _verrou(organization_id):
        en_place = await _lire_reference(organization_id)
        try:
            await db_client.upsert_configuration(organization_id, _cle_logo, reference)
        except Exception:
            await supprimer_octets(cle)  # la référence n'a pas été posée : on ne laisse pas un fichier orphelin
            raise
    if en_place and en_place["cle"] != cle:
        await supprimer_octets(en_place["cle"])
    finale = await _lire_reference(organization_id)
    if finale is None or finale["cle"] != cle:
        await supprimer_octets(cle)  # une autre pose a gagné la course (ou le logo a été retiré entre-temps)
    return reference


async def retirer(organization_id: int) -> bool:
    """Retire la référence ET le fichier ; ``False`` s'il n'y avait pas de logo."""
    async with _verrou(organization_id):
        ancienne = await _lire_reference(organization_id)
        if ancienne is None:
            return False
        await db_client.delete_configuration(organization_id, _cle_logo)
    await supprimer_octets(ancienne["cle"])
    return True


async def lire(organization_id: int) -> tuple[bytes, dict] | None:
    """Le fichier et sa référence, ou ``None`` (pas de logo, ou fichier absent du stockage)."""
    reference = await _lire_reference(organization_id)
    if reference is None:
        return None
    octets = await lire_octets(reference["cle"])
    return (octets, reference) if octets else None
