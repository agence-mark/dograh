"""[.mark] Sous-lot 6 (D-3) : le REJEU PLANIFIÉ de la suite de tests d'un agent.

Il DÉPENSE (chaque rejeu d'une conversation joue un appelant simulé et un juge) : il est **éteint par défaut**, réglé agent par agent.
Réglage dans ``organization_configurations`` (aucune migration) : ``MARK_REJEU_PLANIFIE:<agent>`` =
``{"actif", "frequence" (quotidien | hebdomadaire), "jour" (0 lundi à 6 dimanche, pour l'hebdomadaire), "heure" (0 à 23, heure de Paris),
"repetitions" (1 à 3), "derniere", "historique" (les 5 derniers résultats), "en_cours"}``.

* **Idempotent** : une PÉRIODE (un jour, une semaine) ne se joue qu'une fois. La période est réservée par une écriture
  conditionnelle (``stock.modifier``) avant de jouer : deux tâches en même temps, une seule joue ; une tâche rejouée après coup ne
  rejoue pas la période déjà faite.
* **Arrêtable** : un délai dur (``DELAI_S``) coupe le rejeu ; éteindre le réglage retire la réservation ; une réservation oubliée
  (tâche morte) se libère d'elle-même après le délai.
* **Borné** : au plus ``PAR_PASSAGE_MAX`` rejeux par passage de la tâche ; le plafond du mois des rôles simulés (juge, appelant) coupe
  le rejeu comme à la main.
* **Aucune bascule automatique** : le rejeu range ses résultats et ses problèmes dans « À améliorer », il ne publie ni ne retire rien.

La fonction de rejeu est injectable (``rejouer``) : les tests ne jouent jamais un vrai appelant.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger

from api.services.builder import stock

PREFIXE = "MARK_REJEU_PLANIFIE:"
FREQUENCES = ("quotidien", "hebdomadaire")
HEURE_PAR_DEFAUT = 3
HISTORIQUE_MAX = 5
REPETITIONS_PAR_DEFAUT = 1
REPETITIONS_MAX = 3
DELAI_S = 1800
PAR_PASSAGE_MAX = 5
FUSEAU = ZoneInfo("Europe/Paris")

Rejouer = Callable[..., Awaitable[dict[str, Any]]]


def cle(workflow_id: int) -> str:
    return f"{PREFIXE}{workflow_id}"


def _entier(valeur: Any, defaut: int, bas: int, haut: int) -> int:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return defaut
    return max(bas, min(haut, int(valeur)))


def propres(ligne: dict[str, Any] | None) -> dict[str, Any]:
    """Le réglage tel que le code le lit : éteint, quotidien, 3 h, un essai par test tant que rien n'est dit."""
    ligne = ligne if isinstance(ligne, dict) else {}
    return {
        "actif": ligne.get("actif") is True,
        "frequence": ligne.get("frequence") if ligne.get("frequence") in FREQUENCES else "quotidien",
        "jour": _entier(ligne.get("jour"), 0, 0, 6),
        "heure": _entier(ligne.get("heure"), HEURE_PAR_DEFAUT, 0, 23),
        "repetitions": _entier(ligne.get("repetitions"), REPETITIONS_PAR_DEFAUT, 1, REPETITIONS_MAX),
        "derniere": ligne.get("derniere") if isinstance(ligne.get("derniere"), dict) else None,
        "historique": [h for h in ligne.get("historique") or [] if isinstance(h, dict)][:HISTORIQUE_MAX],
        "en_cours": ligne.get("en_cours") if isinstance(ligne.get("en_cours"), dict) else None,
    }


async def lire(organisation_id: int, workflow_id: int) -> dict[str, Any]:
    return propres(await stock.lire(organisation_id, cle(workflow_id)))


async def regler(
    organisation_id: int,
    workflow_id: int,
    *,
    actif: bool | None = None,
    frequence: str | None = None,
    jour: int | None = None,
    heure: int | None = None,
    repetitions: int | None = None,
) -> dict[str, Any]:
    """Change le réglage. Éteindre libère aussi une réservation en cours (arrêt). ``ValueError`` si la fréquence est inconnue."""
    if frequence is not None and frequence not in FREQUENCES:
        raise ValueError(f"Unknown frequency (expected: {', '.join(FREQUENCES)}).")

    def transformer(ligne):
        courant = propres(ligne)
        if actif is not None:
            courant["actif"] = bool(actif)
            if not actif:
                courant["en_cours"] = None
        if frequence is not None:
            courant["frequence"] = frequence
        if jour is not None:
            courant["jour"] = _entier(jour, 0, 0, 6)
        if heure is not None:
            courant["heure"] = _entier(heure, HEURE_PAR_DEFAUT, 0, 23)
        if repetitions is not None:
            courant["repetitions"] = _entier(repetitions, REPETITIONS_PAR_DEFAUT, 1, REPETITIONS_MAX)
        return courant

    return propres(await stock.modifier(organisation_id, cle(workflow_id), transformer))


def periode(frequence: str, maintenant: datetime) -> str:
    """La période d'un instant (heure de Paris) : le jour (``2026-11-05``) ou la semaine ISO (``2026-W45``)."""
    local = maintenant.astimezone(FUSEAU)
    if frequence == "hebdomadaire":
        annee, semaine, _ = local.isocalendar()
        return f"{annee}-W{semaine:02d}"
    return local.date().isoformat()


def _reservation_vivante(en_cours: dict[str, Any] | None, maintenant: datetime) -> bool:
    try:
        depuis = datetime.fromisoformat(str((en_cours or {}).get("depuis")))
    except ValueError:
        return False
    return maintenant - depuis < timedelta(seconds=DELAI_S + 300)


def instant_prevu(reglage: dict[str, Any], maintenant: datetime) -> datetime:
    """L'instant où la période courante devient due : aujourd'hui à l'heure réglée, ou, pour l'hebdomadaire, le jour réglé de la semaine
    ISO courante à l'heure réglée (heure de Paris). Une tâche qui passe plus tard rattrape la période, jamais deux fois."""
    local = maintenant.astimezone(FUSEAU)
    jour = local - timedelta(days=local.weekday() - reglage["jour"]) if reglage["frequence"] == "hebdomadaire" else local
    return jour.replace(hour=reglage["heure"], minute=0, second=0, microsecond=0)


def echu(reglage: dict[str, Any], maintenant: datetime) -> bool:
    """Le rejeu est-il dû ? Allumé, heure atteinte, période pas déjà faite ni déjà prise par une tâche vivante."""
    if not reglage["actif"] or maintenant.astimezone(FUSEAU) < instant_prevu(reglage, maintenant):
        return False
    courante = periode(reglage["frequence"], maintenant)
    if (reglage["derniere"] or {}).get("periode") == courante:
        return False
    en_cours = reglage["en_cours"]
    return not (en_cours and en_cours.get("periode") == courante and _reservation_vivante(en_cours, maintenant))


async def _reserver(organisation_id: int, workflow_id: int, maintenant: datetime) -> dict[str, Any] | None:
    """Réserve la période courante par une écriture conditionnelle. ``None`` : pas dû, éteint, ou déjà pris (une autre tâche joue)."""
    pris: dict[str, Any] | None = None

    def transformer(ligne):
        nonlocal pris
        pris = None
        courant = propres(ligne)
        if not echu(courant, maintenant):
            return None  # rien à écrire
        pris = courant
        courant["en_cours"] = {"periode": periode(courant["frequence"], maintenant), "depuis": maintenant.isoformat()}
        return courant

    await stock.modifier(organisation_id, cle(workflow_id), transformer)
    return pris


async def _rendre(organisation_id: int, workflow_id: int, nom_de_periode: str, resultat: dict[str, Any]) -> None:
    def transformer(ligne):
        courant = propres(ligne)
        if (courant["en_cours"] or {}).get("periode") == nom_de_periode:
            courant["en_cours"] = None
        courant["derniere"] = {"periode": nom_de_periode, **resultat}
        courant["historique"] = [courant["derniere"], *[h for h in courant["historique"] if h.get("periode") != nom_de_periode]][:HISTORIQUE_MAX]
        return courant

    await stock.modifier(organisation_id, cle(workflow_id), transformer)


async def jouer_si_du(
    organisation_id: int, workflow_id: int, *, rejouer: Rejouer | None = None, maintenant: datetime | None = None
) -> dict[str, Any]:
    """Joue la suite de l'agent si la période est due, une seule fois. ``{"statut": "pas_du" | "joue" | "interrompu" | "echec" | "sans_tests"}``.
    ⛔ Ne lève jamais : un échec est rangé comme résultat de la période (la période est faite, la suivante repart)."""
    from api.db import db_client

    maintenant = maintenant or datetime.now(UTC)
    reglage = await _reserver(organisation_id, workflow_id, maintenant)
    if reglage is None:
        return {"statut": "pas_du"}
    nom_de_periode = periode(reglage["frequence"], maintenant)
    debut = datetime.now(UTC)
    resultat: dict[str, Any] = {"debut": debut.isoformat()}
    try:
        workflow = await db_client.get_workflow(workflow_id, organization_id=organisation_id)
        if workflow is None:
            resultat |= {"statut": "echec", "erreur": "agent introuvable"}
        else:
            if rejouer is None:
                from api.services.builder.tests_agent import execution

                rejouer = execution.rejouer_la_suite
            utilisateur = SimpleNamespace(selected_organization_id=organisation_id, id=getattr(workflow, "user_id", None), email=None)
            rendu = await asyncio.wait_for(rejouer(utilisateur, workflow, repetitions=reglage["repetitions"]), timeout=DELAI_S)
            if rendu.get("disponible") is False:
                resultat |= {"statut": "sans_tests"}
            else:
                resultat |= {
                    "statut": "joue",
                    "ok": bool(rendu.get("ok")),
                    "reussis": rendu.get("reussis"),
                    "total": rendu.get("total"),
                    "plafond": rendu.get("plafond"),
                    "version": rendu.get("version"),
                }
    except asyncio.TimeoutError:
        resultat |= {"statut": "interrompu", "erreur": f"délai de {DELAI_S} s dépassé"}
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[rejeu-planifie] agent {workflow_id} : {type(erreur).__name__}")
        resultat |= {"statut": "echec", "erreur": type(erreur).__name__}
    resultat["fin"] = datetime.now(UTC).isoformat()
    await _rendre(organisation_id, workflow_id, nom_de_periode, resultat)
    return resultat
