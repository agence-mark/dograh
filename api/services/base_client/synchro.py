"""[.mark] Keeping the in-memory copy true to the client's database (B3).

Two mechanisms, one function:

- the NOTIFICATION: every write of the referential in the client's database fires
  ``pg_notify('mark_referentiel')`` (migration 002). The arq worker listens on every
  attached database and rebuilds that organization's copy at once;
- the RESYNC, a safety net: every few minutes, each attached organization's copy is
  rebuilt from its database and compared with what Redis held. A difference means a
  notification was missed: it is corrected and logged (R7: the safety net is proved on a
  red case, a write made with the notification switched off).

``resynchroniser`` never raises: a database that does not answer keeps the copy as it
is (the calls go on with the last known values) and the problem is logged.
"""

from __future__ import annotations

import asyncio
import json

from loguru import logger

from api.db.bases_clients.connexion import BaseClientIndisponible, connecter, ecouter

CANAL = "mark_referentiel"


async def lire_depuis_la_base(
    organization_id: int, nom_base: str, avant=None, phrases_avant=None
):
    """The copy rebuilt from the client's database (raises ``BaseClientIndisponible``)."""
    from api.db.bases_clients.referentiel import dernier_journal
    from api.services.base_client.referentiel import lire_referentiel
    from api.services.etablissements.copie import CopieOrganisation

    connexion = await connecter(nom_base)
    try:
        journal_id = await dernier_journal(connexion)
        referentiel = await lire_referentiel(connexion, avant, phrases_avant)
    finally:
        await connexion.close()
    for refus in referentiel.refus:
        logger.error(
            f"[.mark] Client database of organization {organization_id}: {refus}"
        )
    return CopieOrganisation(
        etablissements=referentiel.etablissements,
        phrases=referentiel.phrases,
        lu_depuis="stockage",
        source="base_client",
        refus=referentiel.refus,
        journal_id=journal_id,
    )


_VERROUS: dict[int, asyncio.Lock] = {}


async def resynchroniser(organization_id: int) -> str:
    """Rebuild the copy from the source. Returns ``identique``, ``corrigee``,
    ``indisponible`` or ``sans_base``. Never raises.

    Revue 9: one resync at a time per organization in this process (two notifications close
    together are played in order), and across processes the copy is never published over
    one that read a later line of the journal (``publier_copie``)."""
    verrou = _VERROUS.setdefault(organization_id, asyncio.Lock())
    async with verrou:
        return await _resynchroniser(organization_id)


async def _resynchroniser(organization_id: int) -> str:
    from api.services.base_client.rattachement import nom_de_la_base
    from api.services.etablissements.copie import _redis, cle_copie, publier_copie

    try:
        nom = await nom_de_la_base(organization_id)
        if not nom:
            return "sans_base"
        brut = await (await _redis()).get(cle_copie(organization_id))
        avant_doc = json.loads(brut) if brut else None
        from api.schemas.etablissements import CatalogueEtablissements
        from api.schemas.phrases import CataloguePhrases

        avant = (
            CatalogueEtablissements.model_validate(avant_doc["catalogue"])
            if avant_doc
            else None
        )
        phrases_avant = (
            CataloguePhrases.model_validate(avant_doc.get("phrases") or {})
            if avant_doc
            else None
        )
        try:
            copie = await lire_depuis_la_base(
                organization_id, nom, avant, phrases_avant
            )
        except BaseClientIndisponible as erreur:
            logger.error(
                f"[.mark] Resync of organization {organization_id}: {erreur}; the copy is kept"
            )
            return "indisponible"
        nouveau = {
            "catalogue": copie.etablissements.model_dump(mode="json"),
            "phrases": copie.phrases.model_dump(mode="json"),
        }
        ancien = {k: (avant_doc or {}).get(k) for k in nouveau}
        await publier_copie(organization_id, copie)
        if ancien == nouveau:
            return "identique"
        # The mirror follows (the call's fallback when the database does not answer).
        from api.services.etablissements.stockage import enregistrer_miroir

        await enregistrer_miroir(
            organization_id, etablissements=copie.etablissements, phrases=copie.phrases
        )
        logger.warning(
            f"[.mark] Resync of organization {organization_id}: the copy differed from the client's database, corrected"
        )
        return "corrigee"
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] Resync of organization {organization_id} failed: {erreur!r}"
        )
        return "indisponible"


async def resynchroniser_tout(ctx=None) -> dict[int, str]:
    """arq cron: every attached organization."""
    from api.services.base_client.rattachement import organisations_rattachees

    resultats = {}
    for organization_id, _nom in await organisations_rattachees():
        resultats[organization_id] = await resynchroniser(organization_id)
    return resultats


ECOUTE: "Ecoute | None" = None


async def tic_de_synchro(ctx=None) -> dict[int, str]:
    """arq cron, every few minutes and at the worker's start: listen to the databases
    attached since the last tick, then resync every one (the safety net)."""
    global ECOUTE
    if ECOUTE is None:
        ECOUTE = Ecoute()
    try:
        await ECOUTE.actualiser()
    except Exception as erreur:  # noqa: BLE001 -- the resync below still runs
        logger.error(f"[.mark] Listening to the client databases failed: {erreur!r}")
    return await resynchroniser_tout(ctx)


class Ecoute:
    """LISTEN on every attached database, rebuild the copy on each notification.

    Started by the arq worker. The list of databases is refreshed at each resync tick
    (an organization attached later is listened to from then on).
    """

    def __init__(self):
        self._connexions: dict[int, object] = {}
        self._taches: set[asyncio.Task] = set()  # kept referenced until done

    async def actualiser(self) -> None:
        from api.services.base_client.rattachement import organisations_rattachees

        voulues = dict(await organisations_rattachees())
        for organization_id in list(self._connexions):
            if organization_id not in voulues:
                await self._fermer(organization_id)
        for organization_id, nom in voulues.items():
            connexion = self._connexions.get(organization_id)
            if connexion is not None and not connexion.is_closed():
                continue

            def rappel(_c, _pid, _canal, _charge, organisation=organization_id):
                tache = asyncio.get_running_loop().create_task(
                    resynchroniser(organisation)
                )
                self._taches.add(tache)
                tache.add_done_callback(self._taches.discard)

            try:
                connexion = await ecouter(nom, CANAL, rappel)
            except BaseClientIndisponible as erreur:
                logger.warning(
                    f"[.mark] Not listening to organization {organization_id}: {erreur}"
                )
                continue
            self._connexions[organization_id] = connexion

    async def _fermer(self, organization_id: int) -> None:
        connexion = self._connexions.pop(organization_id, None)
        if connexion is not None:
            try:
                await connexion.close()
            except Exception:  # noqa: BLE001
                pass

    async def fermer(self) -> None:
        for organization_id in list(self._connexions):
            await self._fermer(organization_id)
