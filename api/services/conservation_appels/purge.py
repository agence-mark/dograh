"""[.mark] The nightly purge of the calls' copies (chantier cloture-code-avant-migration, lot 6).

For each organization, on arq's cron (``tasks/arq.py``, at 03:43, a minute of its own, away from
``nuit_apres_appel`` at 03:17): the runs older than the organization's duration have what carries the text of
the conversation emptied and their files deleted from storage; the run's row (cost, duration, state) and its
technical ``extra`` stay. Two parts, two durations:

- ``texte`` (``duree_mois``): the transcript file, ``logs``, ``initial_context``, ``gathered_context`` (trace and
  ``tool_results`` with it), ``annotations``, the text session, the payload of the deliveries already sent;
- ``audio`` (``audio_duree_mois``): the audio files and their addresses. Applies to what was recorded before the
  audio was switched off too (the copies uploaded by default until now).

🔑 DRY RUN (``essai_a_blanc``, on by default): counts what it would empty, empties nothing, writes the result
(``CONSERVATION_APPELS_BILAN``) so the screen shows it; Evan unticks it once the count has been read.

⛔ Never raises on one run: a file that cannot be deleted leaves the run untouched (nothing emptied while its
file still stands, or its address would be lost) and it is retried the next night. A run is scoped to its
organization through its agent; a file is deleted only under the prefix the upload writes (``transcripts/``,
``recordings/``), whatever a tampered ``extra`` says.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

from api.db import db_client
from api.schemas.conservation_appels import (
    JOURS_PAR_MOIS,
    BilanDuPassage,
    ReglagesConservationAppels,
)
from api.services.conservation_appels.reglages import ecrire_bilan, lire_reglages
from api.services.storage import get_storage_for_backend

TAILLE_DU_LOT = 200
# The cron's own time limit is 1 hour; the task stops itself well before, the rest waits for the next night.
DELAI_MAX_S = 45 * 60
PREFIXE_TEXTE = "transcripts/"
PREFIXE_AUDIO = "recordings/"


def adresses_du_texte(run: dict[str, Any]) -> list[str]:
    url = run.get("transcript_url")
    return [url] if isinstance(url, str) and url.startswith(PREFIXE_TEXTE) else []


def adresses_de_l_audio(run: dict[str, Any]) -> list[str]:
    """The audio files of a run: its mixed track and the tracks listed in ``extra["recordings"]``."""
    trouvees: list[str] = []
    candidates = [run.get("recording_url")]
    pistes = (run.get("extra") or {}).get("recordings")
    if isinstance(pistes, dict):
        candidates += [p.get("storage_key") for p in pistes.values() if isinstance(p, dict)]
    for adresse in candidates:
        if isinstance(adresse, str) and adresse.startswith(PREFIXE_AUDIO) and adresse not in trouvees:
            trouvees.append(adresse)
    return trouvees


class _Stockages:
    """The storage of each backend a run names, opened once per passage."""

    def __init__(self) -> None:
        self._ouverts: dict[str, Any] = {}

    def de(self, backend: str | None) -> Any | None:
        if backend not in self._ouverts:
            try:
                self._ouverts[backend] = get_storage_for_backend(backend)
            except Exception as erreur:  # noqa: BLE001 -- a backend that is not configured here
                logger.error(f"[.mark] Retention: storage {backend!r} unavailable: {erreur!r}")
                self._ouverts[backend] = None
        return self._ouverts[backend]


async def _supprimer(stockages: _Stockages, run: dict[str, Any], adresses: list[str]) -> bool:
    """Every file gone (deleted now, or already absent). Nothing to delete is a success."""
    if not adresses:
        return True
    stockage = stockages.de(run.get("storage_backend"))
    if stockage is None:
        return False
    for adresse in adresses:
        try:
            if not await stockage.adelete_file(adresse):
                return False
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"[.mark] Retention: {adresse} of run {run['id']} not deleted: {erreur!r}")
            return False
    return True


async def purger_une_organisation(
    organization_id: int,
    *,
    maintenant: datetime | None = None,
    reglages: ReglagesConservationAppels | None = None,
    delai_max_s: float = DELAI_MAX_S,
    taille_du_lot: int = TAILLE_DU_LOT,
) -> BilanDuPassage | None:
    """One organization's passage. ``None``: the purge is switched off, nothing was done (nothing written)."""
    reglages = reglages or await lire_reglages(organization_id)
    if not reglages.purge_activee:
        return None
    maintenant = maintenant or datetime.now(UTC)
    quand = maintenant.isoformat()
    a_blanc = reglages.essai_a_blanc
    seuils = {
        "texte": maintenant - timedelta(days=JOURS_PAR_MOIS * reglages.duree_mois),
        "audio": maintenant - timedelta(days=JOURS_PAR_MOIS * reglages.audio_duree_mois),
    }
    stockages = _Stockages()
    runs = {"texte": 0, "audio": 0}
    objets = 0
    echecs = 0
    incomplet = False
    fin = time.monotonic() + delai_max_s

    for partie in ("texte", "audio"):
        apres_id = 0
        while True:
            if time.monotonic() > fin:
                incomplet = True
                break
            lot = await db_client.lister_runs_a_purger(
                organization_id,
                avant=seuils[partie],
                partie=partie,
                apres_id=apres_id,
                limite=taille_du_lot,
            )
            if not lot:
                break
            apres_id = lot[-1]["id"]
            for run in lot:
                adresses = adresses_du_texte(run) if partie == "texte" else adresses_de_l_audio(run)
                if a_blanc:
                    runs[partie] += 1
                    objets += len(adresses)
                    continue
                if not await _supprimer(stockages, run, adresses):
                    echecs += 1
                    continue
                if partie == "texte":
                    fait = await db_client.vider_les_copies_texte(run["id"], organization_id, quand)
                else:
                    fait = await db_client.marquer_audio_supprime(run["id"], organization_id, quand)
                if fait:
                    runs[partie] += 1
                    objets += len(adresses)
            if len(lot) < taille_du_lot:
                break

    bilan = BilanDuPassage(
        passe_le=maintenant,
        a_blanc=a_blanc,
        runs_texte=runs["texte"],
        runs_audio=runs["audio"],
        objets=objets,
        echecs=echecs,
        incomplet=incomplet,
        duree_mois=reglages.duree_mois,
        audio_duree_mois=reglages.audio_duree_mois,
    )
    logger.info(
        f"[.mark] Retention of organization {organization_id} ({'dry run' if a_blanc else 'real'}): "
        f"{bilan.model_dump(mode='json', exclude={'passe_le'})}"
    )
    await ecrire_bilan(organization_id, bilan)
    return bilan


async def conservation_de_nuit(_ctx=None) -> dict[int, dict]:
    """The cron task: every organization, one after the other. One organization's failure does not stop the
    others; it is told to the notification addresses like a failed night task."""
    sortie: dict[int, dict] = {}
    for organization_id in await db_client.lister_ids_organisations():
        try:
            bilan = await purger_une_organisation(organization_id)
            sortie[organization_id] = (
                {"statut": "eteinte"} if bilan is None else {"statut": "faite", **bilan.model_dump(mode="json")}
            )
        except Exception as erreur:  # noqa: BLE001
            message = f"{type(erreur).__name__}: {erreur}"
            logger.error(f"[.mark] Retention of organization {organization_id} failed: {message}")
            sortie[organization_id] = {"statut": "echec", "erreur": message}
            try:
                from api.services.apres_appel.notification import notifier

                await notifier(
                    organization_id,
                    "Purge de conservation en échec",
                    "La purge de nuit des copies d'appel a échoué.\n"
                    f"Cause : {message}\n"
                    "Rien n'a été effacé à moitié : elle se rejoue la nuit suivante.",
                )
            except Exception:  # noqa: BLE001 -- telling a failure must not make a second one
                pass
    return sortie
