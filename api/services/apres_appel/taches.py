"""[.mark] The scheduled after-call tasks (A4, A8), on arq's cron like the resync (L3).

- ``nuit`` (every night): for each attached client database, ``mark.nuit()``: the purge
  table by table (``politique_conservation``: transcript 6 months by default, contacts
  3 years after their last activity), the day's counters refreshed, and the proof kept
  in ``mark.execution_tache``. A failure is mailed to the notification addresses.
- ``recapitulatif`` (every hour): for each organization whose recap leaves at this hour
  (its timezone), the mail « what still waits for a call-back » (``v_a_rappeler``) to the
  default recipients of its team. Sent once per hour and organization (a Redis mark).
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from loguru import logger

from api.db import db_client
from api.db.bases_clients import apres_appel as sql
from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.enums import OrganizationConfigurationKey
from api.services.apres_appel import mail as service_mail
from api.services.apres_appel.notification import notifier
from api.services.apres_appel.reglages import CLE, lire_reglages
from api.services.base_client.rattachement import organisations_rattachees


async def nuit_d_une_base(organization_id: int, nom_base: str) -> dict:
    """The night task of ONE client database. Never raises: a failure is returned and
    notified."""
    try:
        connexion = await connecter(nom_base)
        try:
            resultat = await sql.nuit(connexion)
        finally:
            await connexion.close()
        logger.info(f"[.mark] Night task of organization {organization_id}: {resultat}")
        return {"statut": "faite", **resultat}
    except Exception as erreur:  # noqa: BLE001
        message = (
            str(erreur)
            if isinstance(erreur, BaseClientIndisponible)
            else f"{type(erreur).__name__}: {erreur}"
        )
        logger.error(
            f"[.mark] Night task of organization {organization_id} failed: {message}"
        )
        await notifier(
            organization_id,
            "Purge de nuit en échec",
            f"La tâche de nuit (purge et compteurs) de la base « {nom_base} » a échoué.\nCause : {message}\n"
            "Rien n'a été effacé à moitié : la purge se rejoue la nuit suivante, ou depuis « Client data ».",
        )
        return {"statut": "echec", "erreur": message}


async def nuit(_ctx=None) -> dict[int, dict]:
    sortie = {}
    for organization_id, nom_base in await organisations_rattachees():
        sortie[organization_id] = await nuit_d_une_base(organization_id, nom_base)
    return sortie


async def _fuseau(organization_id: int) -> ZoneInfo:
    try:
        ligne = await db_client.get_configuration(
            organization_id, OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value
        )
        return ZoneInfo(
            ((ligne.value if ligne else None) or {}).get("timezone") or "Europe/Paris"
        )
    except Exception:  # noqa: BLE001
        return ZoneInfo("Europe/Paris")


def texte_du_recapitulatif(lignes: list[dict]) -> str:
    if not lignes:
        return "Aucune demande n'attend de rappel."
    sortie = [f"{len(lignes)} demande(s) attendent un rappel :", ""]
    for l in lignes:
        quand = l["creee_le"].strftime("%d/%m %H:%M") if l.get("creee_le") else ""
        morceaux = [
            f"n° {l['id']}",
            quand,
            l.get("type") or "",
            l.get("site") or "",
            l.get("contact_nom") or "",
            l.get("telephone") or "",
        ]
        sortie.append("- " + " · ".join(m for m in morceaux if m))
        if l.get("resume"):
            sortie.append(f"  {l['resume']}")
        if l.get("autre_demande_ouverte_id"):
            sortie.append(
                f"  ⚠ autre demande ouverte du même numéro : n° {l['autre_demande_ouverte_id']}"
            )
    return "\n".join(sortie)


async def recapitulatif_d_une_organisation(
    organization_id: int, nom_base: str, force: bool = False
) -> dict:
    reglages = await lire_reglages(organization_id)
    if not reglages.recapitulatif.actif and not force:
        return {"statut": "eteint"}
    connexion = await connecter(nom_base)
    try:
        lignes = await sql.a_rappeler(connexion)
        destinataires = [
            d["mail"] for d in await sql.destinataires_de(connexion, None, None)
        ]
    finally:
        await connexion.close()
    if not destinataires:
        return {"statut": "sans_destinataire"}
    await service_mail.envoyer(
        reglages.smtp,
        organization_id,
        destinataires,
        f"Récapitulatif : {len(lignes)} demande(s) à rappeler",
        texte_du_recapitulatif(lignes),
    )
    return {"statut": "envoye", "demandes": len(lignes), "destinataires": destinataires}


async def recapitulatif(
    _ctx=None, maintenant: datetime | None = None
) -> dict[int, dict]:
    """Every hour: the organizations whose recap leaves now."""
    from api.services.etablissements.copie import _redis

    maintenant = maintenant or datetime.now(UTC)
    sortie: dict[int, dict] = {}
    lignes = {
        l["organization_id"]: l["value"]
        for l in await db_client.get_all_configurations_by_key(CLE)
    }
    for organization_id, nom_base in await organisations_rattachees():
        valeur = (lignes.get(organization_id) or {}).get("recapitulatif") or {}
        if not valeur.get("actif"):
            continue
        locale = maintenant.astimezone(await _fuseau(organization_id))
        if locale.hour not in (valeur.get("heures") or []):
            continue
        marque = f"mark:recapitulatif:{organization_id}:{locale.strftime('%Y%m%d%H')}"
        try:
            redis = await _redis()
            if not await redis.set(marque, "1", nx=True, ex=7200):
                continue
        except Exception:  # noqa: BLE001 -- without Redis, sent anyway (at most twice an hour)
            pass
        try:
            sortie[organization_id] = await recapitulatif_d_une_organisation(
                organization_id, nom_base
            )
        except Exception as erreur:  # noqa: BLE001
            message = str(erreur)
            sortie[organization_id] = {"statut": "echec", "erreur": message}
            await notifier(
                organization_id,
                "Récapitulatif non envoyé",
                f"Le récapitulatif de {locale:%H} h n'est pas parti.\nCause : {message}",
            )
    return sortie
