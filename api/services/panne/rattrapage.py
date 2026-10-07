"""[.mark] The calls lost while our server was down (L7, PN5, limit 2 of constat § 6).

When the server is dead, Twilio plays the emergency instruction (the TwiML Bin) and Dograh writes
nothing: no request « to call back », no alert. Back up, this reads the client's Twilio call log
for the numbers of its accounts and, for each inbound call that has no run, or whose run never
finished, writes the request « to call back » in the client's database (``recevoir_appel_perdu``,
ONCE per Twilio call: a replay returns the request already made) and sends one alert listing them.

Runs every hour for the organizations that set an emergency address, and from the screen.
⛔ Reads the call log only; writes nothing at Twilio.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.panne import twilio as client_twilio

FENETRE_H = 24  # how far back the call log is read
DELAI_RUN_FINI_MIN = 10  # a run younger than this may still be finishing
STATUTS_FINIS = {"completed", "no-answer", "busy", "failed", "canceled"}


def _date(brut: Any) -> datetime | None:
    if not brut:
        return None
    try:
        return parsedate_to_datetime(str(brut))
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(brut))
        except ValueError:
            return None


async def _comptes(organization_id: int) -> list[tuple[str, str, list[str]]]:
    """(account sid, token, numbers) of the organization's active Twilio accounts."""
    comptes = []
    for config in await db_client.list_telephony_configurations_by_provider(
        organization_id, "twilio", active_only=True
    ):
        if getattr(config, "inactive", False):
            continue
        cred = config.credentials or {}
        if cred.get("account_sid") and cred.get("auth_token"):
            numeros = await db_client.list_active_normalized_addresses_for_config(
                config.id
            )
            comptes.append(
                (
                    cred["account_sid"],
                    cred["auth_token"],
                    [n for n in numeros if n.startswith("+")],
                )
            )
    return comptes


async def _perdu(organization_id: int, appel: dict, maintenant: datetime) -> bool:
    if appel.get("direction") != "inbound" or appel.get("status") not in STATUTS_FINIS:
        return False
    run = await db_client.run_par_appel(organization_id, appel.get("sid") or "")
    if run is None:
        return True  # our server never answered: the Bin did
    if run.is_completed or getattr(run, "state", None) == "completed":
        return False
    cree = getattr(run, "created_at", None)
    return bool(
        cree
        and (maintenant - cree.replace(tzinfo=cree.tzinfo or UTC))
        > timedelta(minutes=DELAI_RUN_FINI_MIN)
    )


async def _premiere_alerte(organization_id: int, appel: dict) -> bool:
    """Revue 8: one alert per lost Twilio call, whatever the number of hourly passes (a mark
    in Redis, kept a little longer than the window read). Without Redis: alerted anyway."""
    from api.services.etablissements.copie import _redis

    marque = f"mark:panne:alerte:{organization_id}:{appel.get('sid') or ''}"
    try:
        redis = await _redis()
        return bool(await redis.set(marque, "1", nx=True, ex=(FENETRE_H + 1) * 3600))
    except Exception:  # noqa: BLE001
        return True


async def rattraper(organization_id: int, maintenant: datetime | None = None) -> dict:
    """``{appels_lus, demandes_creees, deja_connus, erreurs}``. Never raises."""
    from api.db.bases_clients import apres_appel as sql
    from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
    from api.services.apres_appel.notification import notifier
    from api.services.base_client.rattachement import nom_de_la_base

    maintenant = maintenant or datetime.now(UTC)
    bilan: dict[str, Any] = {
        "appels_lus": 0,
        "demandes_creees": 0,
        "deja_connus": 0,
        "erreurs": [],
    }
    perdus: list[dict] = []
    try:
        for sid, jeton, numeros in await _comptes(organization_id):
            for numero in numeros:
                try:
                    appels = await client_twilio.appels_entrants(
                        sid, jeton, numero, maintenant - timedelta(hours=FENETRE_H)
                    )
                except client_twilio.TwilioIndisponible as erreur:
                    bilan["erreurs"].append(f"{numero}: {erreur}")
                    continue
                bilan["appels_lus"] += len(appels)
                for appel in appels:
                    if await _perdu(organization_id, appel, maintenant):
                        perdus.append(appel)
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] Catch-up of lost calls failed (org {organization_id}): {erreur!r}"
        )
        bilan["erreurs"].append(repr(erreur))
        return bilan
    if not perdus:
        return bilan

    nouveaux: list[dict] = []
    nom = await nom_de_la_base(organization_id)
    if not nom:
        bilan["erreurs"].append(
            "No client database attached: the lost calls are only alerted."
        )
        nouveaux = perdus
    else:
        try:
            connexion = await connecter(nom)
        except BaseClientIndisponible as erreur:
            bilan["erreurs"].append(str(erreur))
            return bilan
        try:
            for appel in perdus:
                resultat = await sql.recevoir_appel_perdu(
                    connexion,
                    appel.get("sid"),
                    appel.get("from"),
                    appel.get("to"),
                    _date(appel.get("start_time")) or maintenant,
                    appel.get("status"),
                )
                if resultat.get("doublon"):
                    bilan["deja_connus"] += 1
                else:
                    bilan["demandes_creees"] += 1
                    nouveaux.append(appel)
        finally:
            await connexion.close()
    nouveaux = [a for a in nouveaux if await _premiere_alerte(organization_id, a)]
    if nouveaux:
        lignes = [
            f"{len(nouveaux)} appel(s) perdu(s) pendant une panne, à rappeler :"
        ] + [
            f"- {a.get('from') or 'numéro masqué'} le {(_date(a.get('start_time')) or maintenant).strftime('%d/%m à %H:%M')} (vers {a.get('to')})"
            for a in nouveaux
        ]
        await notifier(
            organization_id,
            "Appels perdus pendant une panne, à rappeler",
            "\n".join(lignes),
        )
    return bilan


async def rattrapage_horaire(_ctx=None) -> dict[int, dict]:
    """Every hour: the organizations that set an emergency address (PN5)."""
    from api.enums import OrganizationConfigurationKey

    sortie: dict[int, dict] = {}
    for ligne in await db_client.get_all_configurations_by_key(
        OrganizationConfigurationKey.PANNE.value
    ):
        if (ligne.get("value") or {}).get("url_secours"):
            sortie[ligne["organization_id"]] = await rattraper(ligne["organization_id"])
    return sortie
