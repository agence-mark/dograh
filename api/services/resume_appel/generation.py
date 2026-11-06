"""[.mark] Partie 3, N3b : le résumé d'un appel écrit par un modèle (rôle « resume » de la fenêtre de l'appelant simulé).

Appelé par l'après-appel (``tasks/run_integrations.py``) après le juge. Un réglage qui DÉPENSE : **éteint par défaut** (``actif``), avec
son budget du mois dans la dépense des rôles (``budget_roles``, rôle ``resume``) ; le budget atteint refuse l'appel AVANT le
fournisseur. Le résumé ne se fait JAMAIS :

* pour un appel d'essai (``juge.appels.est_un_appel_d_essai``) ;
* quand l'appel a déjà sa synthèse d'après-appel, ou que son agent la fait (la synthèse est le résumé, ``resume_appel.lire``) ;
* quand il existe déjà (rejouable sans effet double : le texte écrit n'est jamais remplacé) ;
* sans parole dans la transcription.

⛔ Ne lève jamais : un résumé en panne n'abîme ni l'appel ni l'après-appel. Aucun secret ici (la clé reste dans ``simules``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from api.db import db_client
from api.services import resume_appel as lecture
from api.services.builder.cerveau import budget_roles, simules
from api.services.builder.cerveau import reglages as reglages_cerveau
from api.services.builder.cerveau.appel import ErreurCerveau
from api.services.builder.tests_agent.jeu import completer

TRANSCRIPTION_MAX = 12000


def _transcription(lignes: list[tuple[str, str]]) -> str:
    texte = "\n".join(f"{'Agent' if role == 'agent' else 'Appelant'} : {parole}" for role, parole in lignes)
    return texte[:TRANSCRIPTION_MAX]


def _agent_fait_sa_synthese(run: Any) -> bool:
    from api.services.apres_appel.reglages import reglages_de_lagent

    definition = getattr(run, "definition", None)
    agent = reglages_de_lagent(getattr(definition, "workflow_configurations", None))
    return bool(agent.actif and agent.synthese)  # la synthèse est allumée par défaut, mais ne se fait que si l'après-appel est actif


async def apres_appel(run: Any, organisation: int) -> str | None:
    """Écrit le résumé de l'appel s'il y a lieu et le rend ; ``None`` sinon. Ne lève jamais."""
    try:
        from api.services.appel_simule import reglages as appel_simule
        from api.services.juge import appels as juge_appels

        if juge_appels.est_un_appel_d_essai(run) or lecture.lire(getattr(run, "annotations", None)):
            return None
        roles = await appel_simule.lire_reglages(organisation)
        role = roles.resume
        if not role.actif or _agent_fait_sa_synthese(run):
            return None
        base = await reglages_cerveau.lire(organisation)
        cerveau = await simules.cerveau_du_role(organisation, role, base)
        if cerveau is None:
            logger.warning(f"[resume] appel {run.id} : pas de clé pour le résumé")
            return None
        dossier = juge_appels.dossier_d_un_run(run)
        if not dossier["lignes"]:
            return None
        try:
            if role.budget_mois > 0:  # le budget du mois atteint refuse avant tout appel au fournisseur
                await budget_roles.verifier(
                    organisation, "resume", role.budget_mois, prix_connus=any(await simules.prix_du_role(organisation, role, base))
                )
            texte = await completer(
                cerveau, role.consigne, [{"role": "user", "content": f"La conversation :\n{_transcription(dossier['lignes'])}"}]
            )
        except budget_roles.BudgetDuRole as budget:
            logger.warning(f"[resume] appel {run.id} non résumé : {budget.message}")
            return None
        except ErreurCerveau as erreur:
            logger.warning(f"[resume] appel {run.id} non résumé : {erreur.code}")
            return None
        court = lecture.resume_court(texte)
        if not court:
            return None
        conso = {"jetons": cerveau.jetons, "cout": cerveau.cout} if isinstance(cerveau, budget_roles.CerveauBudgete) else {}
        await db_client.update_workflow_run(
            run.id,
            annotations={lecture.CLE_ANNOTATION: {"texte": court, "modele": role.modele, "le": datetime.now(UTC).isoformat(), **conso}},
        )
        return court
    except Exception as erreur:  # noqa: BLE001 -- un résumé en panne n'abîme ni l'appel ni l'après-appel
        logger.warning(f"[resume] appel {getattr(run, 'id', '?')} non résumé : {type(erreur).__name__}")
        return None
