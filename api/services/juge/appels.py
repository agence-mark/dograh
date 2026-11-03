"""[.mark] Le juge des VRAIS appels (J3) : le dossier d'un appel, la grille, et l'après-appel.

Quand l'agent a « juge des vrais appels » allumé (``file.regler``), l'après-appel (``tasks/run_integrations.py``) appelle
``apres_appel`` : sans nœud à poser, avec les réglages du juge du Labo.

* source **clé d'API** : l'appel est jugé tout de suite (``passes.juger``), le résultat est ÉCRIT FUSIONNÉ dans
  ``workflow_runs.annotations`` sous la clé ``juge`` (``update_workflow_run`` fusionne par clé : QA et « À trier » gardent la leur) ;
* source **Claude Code** : l'appel est rangé dans « À juger » (``file``) et reste « à juger » tant qu'une session ne l'a pas jugé ;
* indépendance (D9) : un juge sur clé du modèle de l'agent ou du builder est refusé, l'appel n'est pas jugé et la raison est écrite.

⛔ Un juge en panne n'abîme ni l'appel ni l'après-appel : ``apres_appel`` ne lève jamais.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db import db_client
from api.services.builder import consignes
from api.services.builder.cerveau import independance, simules
from api.services.builder.cerveau import reglages as reglages_cerveau
from api.services.builder.tests_agent import verdict as verdict_code
from api.services.juge import file, note, passes
from api.services.juge import verdicts as v


async def grille() -> list[str]:
    """Les critères d'un appel : la grille versée en bibliothèque, les 6 critères du code en secours."""
    contenu = await consignes.contenu_de("criteres-types", "grille-du-juge-v1")
    brut = (contenu.get("critere") or {}).get("grille") if isinstance(contenu.get("critere"), dict) else None
    criteres = [str(c) for c in brut if str(c).strip()] if isinstance(brut, list) else []
    return criteres or list(v.GRILLE_SECOURS)


def dossier_d_un_run(run: Any) -> dict[str, Any]:
    """Transcription (lignes), outils et fiche d'un run, relus dans son journal : le même regard que le verdict du code."""
    journal = (getattr(run, "logs", None) or {}).get("realtime_feedback_events") or []
    fiche = dict(getattr(run, "gathered_context", None) or {})
    obs = verdict_code.observation_depuis_un_run(journal, fiche)
    return {"lignes": list(obs.lignes), "outils": list(obs.outils), "fiche": fiche}


def est_un_appel_d_essai(run: Any) -> bool:
    from api.services.tests_rejouables.simulation import CLE_REJEU

    annotations = getattr(run, "annotations", None) or {}
    contexte = getattr(run, "gathered_context", None) or {}
    return bool(annotations.get("tester") or contexte.get(CLE_REJEU))


async def ecrire_dans_le_run(run_id: int, resultat: dict[str, Any]) -> None:
    """Le résultat du juge ET sa note (C4), au même endroit pour les deux portes ; rejuger remplace les deux."""
    await db_client.update_workflow_run(run_id, annotations={"juge": resultat})
    await db_client.ecrire_note_juge(run_id, note.de_un_resultat(resultat))


async def _modele_de_l_agent(run: Any, organisation: int) -> str | None:
    from api.services.configuration.ai_model_configuration import get_effective_ai_model_configuration_for_workflow

    try:
        definition = getattr(run, "definition", None)
        effective = await get_effective_ai_model_configuration_for_workflow(
            organization_id=organisation, workflow_configurations=dict(getattr(definition, "workflow_configurations", None) or {})
        )
        return getattr(effective.llm, "model", None) if effective.llm is not None else None
    except Exception:  # noqa: BLE001
        return None


async def apres_appel(run: Any, organisation: int) -> None:
    """Juge (ou range à juger) un vrai appel si l'agent le demande. Ne lève jamais."""
    try:
        if est_un_appel_d_essai(run) or not await file.juge_des_vrais_appels(organisation, run.workflow_id):
            return
        from api.services.appel_simule import reglages as appel_simule

        from api.services import sources_cerveaux

        roles = await appel_simule.lire_reglages(organisation)
        # U12 : la source du juge des vrais appels est celle de sa brique (Claude Code au départ).
        juge = roles.juge.model_copy(update={"source": await sources_cerveaux.source_de(organisation, "juge_appels", roles.juge.source)})
        base = await reglages_cerveau.lire(organisation)
        controle = independance.controler(
            source_juge=juge.source,
            modele_juge=juge.modele,
            modele_builder=base.modele or None,
            modele_agent=await _modele_de_l_agent(run, organisation),
        )
        mention = {"mention": controle.mention} if controle.mention else {}
        if controle.refuse:
            await ecrire_dans_le_run(run.id, {"etat": "refuse", "raison": controle.refus})
            return
        if juge.source == "claude_code":
            await file.ajouter(organisation, {"id": f"appel-{run.id}", "type": "appel", "workflow_id": run.workflow_id, "run_id": run.id})
            await ecrire_dans_le_run(run.id, {"etat": "a_juger", "source": "claude_code", **mention})
            return
        cerveau = await simules.cerveau_du_role(organisation, juge, base)
        if cerveau is None:
            await ecrire_dans_le_run(run.id, {"etat": "non_regle", "raison": "No key set for the judge (Labo settings)."})
            return
        dossier = dossier_d_un_run(run)
        if not dossier["lignes"]:
            await ecrire_dans_le_run(run.id, {"etat": "sans_transcription"})
            return
        rendu = await passes.juger(cerveau, dossier["lignes"], await grille(), outils=dossier["outils"], fiche=dossier["fiche"])
        await ecrire_dans_le_run(
            run.id, {"etat": "juge", "source": "cle_api", "modele": juge.modele, "juge_le": file.maintenant(), **rendu, **mention}
        )
        # U8 (B) : un critère raté entre dans « À améliorer » avec sa réplique fautive (ne lève jamais).
        from api.services.boucle import ingestion

        await ingestion.ingerer_un_appel_juge(run, organisation, rendu.get("verdicts") or [], dossier["lignes"])
    except Exception as erreur:  # noqa: BLE001 -- un juge en panne n'abîme ni l'appel ni l'après-appel
        logger.warning(f"[juge] appel {getattr(run, 'id', '?')} non jugé : {type(erreur).__name__}")
