"""Le coût estimé d'un appel (.mark, langwatch-et-fenetre-du-run, lot 2, étape 5, décision L5).

Consommation du run × table de prix de l'organisation (``api/schemas/fenetre_du_run.py``), calculé
à la LECTURE (L2) : changer un prix change l'estimation de tous les runs, et la fenêtre dit à quel
tarif (date de chaque prix utilisé). Une consommation sans prix déclaré n'est jamais devinée : elle
est listée « unpriced » et le total est dit partiel.

Stockage : une ligne de ``organization_configurations``, clé ``FENETRE_DU_RUN`` (aucune migration),
comme l'annonce d'ouverture.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.fenetre_du_run import ReglagesFenetreDuRun

CLE = OrganizationConfigurationKey.FENETRE_DU_RUN.value
CANAUX_SANS_TELEPHONIE = {"smallwebrtc", "textchat"}


async def lire_reglages_fenetre(
    organization_id: int | None,
) -> ReglagesFenetreDuRun | None:
    """Pour l'analyse d'un run : ``None`` si absente ou illisible (le coût est alors « non capté »,
    jamais faux). Ne lève pas."""
    if organization_id is None:
        return None
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return None
        return ReglagesFenetreDuRun.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(
            f"[.mark] Price table of organization {organization_id} unreadable: {erreur!r}"
        )
        return None


async def lire_reglages_fenetre_stricte(organization_id: int) -> ReglagesFenetreDuRun:
    """Pour l'ÉCRAN : une ligne illisible lève, pour ne pas montrer une table vide qu'un
    enregistrement viendrait écraser (même règle que le lexique et l'annonce)."""
    ligne = await db_client.get_configuration(organization_id, CLE)
    if ligne is None or not ligne.value:
        return ReglagesFenetreDuRun()
    return ReglagesFenetreDuRun.model_validate(ligne.value)


async def enregistrer_reglages_fenetre(
    organization_id: int, table: ReglagesFenetreDuRun
) -> ReglagesFenetreDuRun:
    await db_client.upsert_configuration(
        organization_id, CLE, table.model_dump(mode="json")
    )
    return table


def _modele(cle: str) -> str:
    """``"DograhMistralLLMService#413|||mistral-large-2512"`` → ``mistral-large-2512``."""
    return str(cle).partition("|||")[2] or str(cle)


def cout_du_run(run: dict, table: ReglagesFenetreDuRun | None) -> dict:
    """Le bloc « cost » du résumé de la fenêtre."""
    if table is None or not table.lignes:
        return {"status": "not_captured", "reason": "no_price_table"}
    usage = run.get("usage_info") or {}
    if not usage:
        return {"status": "not_captured", "reason": "no_usage"}
    prix = {(ligne.brique, ligne.modele.strip()): ligne for ligne in table.lignes}
    lignes, sans_prix, dates = [], [], set()

    def compter(brique: str, modele: str, quantite: float, unite: str, montant) -> None:
        ligne = prix.get((brique, modele))
        if ligne is None:
            sans_prix.append(
                {
                    "component": brique,
                    "model": modele,
                    "quantity": quantite,
                    "unit": unite,
                }
            )
            return
        dates.add(ligne.date_du_tarif.isoformat())
        lignes.append(
            {
                "component": brique,
                "model": modele,
                "quantity": quantite,
                "unit": unite,
                "cost": round(montant(ligne), 6),
                "rate_date": ligne.date_du_tarif.isoformat(),
            }
        )

    for cle, jetons in (usage.get("llm") or {}).items():
        jetons = jetons or {}
        entree = jetons.get("prompt_tokens") or 0
        cache = jetons.get("cache_read_input_tokens") or 0
        sortie = jetons.get("completion_tokens") or 0
        compter(
            "llm",
            _modele(cle),
            entree + sortie,
            "tokens",
            lambda l, e=entree, c=cache, s=sortie: (
                (
                    (e - c) * l.entree_par_million
                    + c
                    * (
                        l.cache_par_million
                        if l.cache_par_million is not None
                        else l.entree_par_million
                    )
                    + s * l.sortie_par_million
                )
                / 1_000_000
            ),
        )
    for cle, secondes in (usage.get("stt") or {}).items():
        compter(
            "stt",
            _modele(cle),
            round(secondes or 0, 1),
            "seconds",
            lambda l, s=secondes or 0: s / 60 * l.par_minute,
        )
    for cle, caracteres in (usage.get("tts") or {}).items():
        compter(
            "tts",
            _modele(cle),
            caracteres or 0,
            "characters",
            lambda l, c=caracteres or 0: c / 1_000_000 * l.par_million_caracteres,
        )
    duree = usage.get("call_duration_seconds")
    fournisseur = (run.get("initial_context") or {}).get("provider")
    if run.get("mode") not in CANAUX_SANS_TELEPHONIE and fournisseur and duree:
        compter(
            "telephony",
            str(fournisseur),
            duree,
            "seconds",
            lambda l, d=duree: d / 60 * l.par_minute,
        )
    return {
        "status": "ok",
        "currency": table.devise,
        "total": round(sum(l["cost"] for l in lignes), 4),
        "partial": bool(sans_prix),
        "lines": lignes,
        "unpriced": sans_prix,
        "rate_dates": sorted(dates),
    }
