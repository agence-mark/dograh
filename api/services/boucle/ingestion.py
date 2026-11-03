"""[.mark] U8 (lots B, C, D, E) : après chaque appel, le bilan de la boucle et les problèmes qui entrent dans « À améliorer ».

Un seul passage, après l'appel (``tasks/run_integrations.py``) et après chaque verdict du juge :

* ``bilan_de_l_appel`` : la version estampillée (D), les indicateurs (C) et le motif classé (E) rangés dans
  ``annotations['boucle']`` ; puis les traces du code et les signalements de l'agent, qui entrent dans la file ;
* ``ingerer_les_verdicts`` (B) : un critère raté (ou non vérifiable) du juge entre dans la file avec sa gravité, sa réplique fautive
  (la ligne citée, vérifiée par le schéma du juge), sa confiance et sa cause probable ;
* ``ingerer_un_test`` (F) : un test qui échoue, ou « réussi, à revoir », entre avec sa raison.

Les cas identiques (même agent, même critère ou contrôle, même étape) se REGROUPENT dans un seul problème ; un même appel n'est jamais
compté deux fois. Les appels d'essai (rejeu d'un test, appel simulé) n'entrent jamais : seuls les vrais appels disent la qualité.
⛔ Ne lève jamais : une panne d'ici n'abîme ni l'appel ni l'après-appel. ⛔ Zéro vocabulaire métier (le titre est celui du critère).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db import db_client
from api.services.boucle import indicateurs, version
from api.services.tri import donnees

RELEVE_PAR_JUGE = "juge"
RELEVE_PAR_CODE = "code"
RELEVE_PAR_TEST = "test"
CAUSES = ("prompt", "outil", "donnee", "voix", "moteur")
TITRE_MAX = 300

# La gravité de départ d'une trace du code (1 faible, 2 à surveiller, 3 grave) et la cause qu'elle désigne.
TRACES_DU_CODE: dict[str, tuple[int, str]] = {
    donnees.TYPE_IMPASSE: (3, "moteur"),
    donnees.TYPE_RETENUE: (3, "donnee"),
    donnees.TYPE_SECURITE: (3, "prompt"),
    donnees.TYPE_PORTE_INCONNUE: (2, "moteur"),
    donnees.TYPE_PASSAGE: (2, "moteur"),
    donnees.TYPE_GARDE_MODELE: (2, "moteur"),
    donnees.TYPE_DESACCORD: (1, "moteur"),
    donnees.TYPE_AGENT: (2, "prompt"),
}
TITRES_DU_CODE: dict[str, str] = {
    donnees.TYPE_IMPASSE: "La conversation tourne en rond",
    donnees.TYPE_PORTE_INCONNUE: "L'arbitre a choisi une sortie que l'étape n'a pas",
    donnees.TYPE_DESACCORD: "L'agent et l'arbitre sont en désaccord",
    donnees.TYPE_PASSAGE: "Un passage par le code n'a pas abouti",
    donnees.TYPE_GARDE_MODELE: "Le modèle dépasse son délai plusieurs fois",
    donnees.TYPE_RETENUE: "Une action a été retenue par la vérité des actions",
    donnees.TYPE_SECURITE: "Un garde-fou de sécurité s'est déclenché",
}


def normaliser(texte: str | None) -> str:
    from api.services.juge.verdicts import normaliser as _normaliser

    return _normaliser(texte or "")[:120]


def cle_de(releve_par: str, critere: str, etape: str | None) -> str:
    return f"{releve_par}:{normaliser(critere)}:{normaliser(etape)}"[:240]


def cause_d_un_cas(indicateur: dict[str, Any], contexte: dict[str, Any]) -> str:
    """La cause probable, déduite des traces de l'appel (jamais devinée) : un outil en échec, une retenue de la vérité des actions
    ou une impasse parlent d'eux-mêmes ; sinon la consigne de l'agent."""
    if indicateur.get("outils_en_echec"):
        return "outil"
    if contexte.get(donnees.CLE_RETENUES):
        return "donnee"
    if indicateur.get("impasses"):
        return "moteur"
    return "prompt"


def rang_de_l_appelant(lignes: list[tuple[str, str]], rang_de_la_ligne: Any) -> int | None:
    """Le rang (à partir de 1) de la réplique de l'APPELANT à laquelle se rattache la ligne citée : c'est le rang qu'attend la création
    d'un test depuis un appel. Une ligne de l'agent se rattache à la dernière réplique de l'appelant avant elle (au moins la première)."""
    if not isinstance(rang_de_la_ligne, int) or not 1 <= rang_de_la_ligne <= len(lignes):
        return None
    return max(1, sum(1 for role, _ in lignes[:rang_de_la_ligne] if role != "agent"))


def gravite_d_un_verdict(verdict: dict[str, Any]) -> int:
    if verdict.get("verdict") == "non_verifiable":
        return 1
    confiance = float(verdict.get("confiance") or 0)
    return 3 if confiance >= 0.85 else 2 if confiance >= 0.6 else 1


async def _ajouter(organisation_id: int, workflow_id: int, cle: str, valeurs: dict[str, Any], cas: dict[str, Any]) -> None:
    await db_client.ajouter_un_cas_d_amelioration(organisation_id, workflow_id, cle, valeurs, cas)


# --- B : le juge -------------------------------------------------------------------------------------------------------------


async def ingerer_les_verdicts(
    organisation_id: int,
    workflow_id: int,
    run_id: int,
    verdicts: list[dict[str, Any]],
    lignes: list[tuple[str, str]],
    *,
    cause: str = "prompt",
    version_numero: int | None = None,
    etape: str | None = None,
) -> int:
    """Les critères ratés d'un appel jugé entrent dans la file. Rend le nombre de problèmes touchés. Ne lève jamais."""
    touches = 0
    try:
        for v in verdicts or []:
            if v.get("verdict") == "reussi":
                continue
            rang = v.get("replique")
            citation = lignes[rang - 1][1] if isinstance(rang, int) and 1 <= rang <= len(lignes) else None
            critere = str(v.get("critere") or "")[:240]
            await _ajouter(
                organisation_id,
                workflow_id,
                cle_de(RELEVE_PAR_JUGE, critere, etape),
                {
                    "releve_par": RELEVE_PAR_JUGE,
                    "titre": critere[:TITRE_MAX],
                    "critere": critere,
                    "etape": etape,
                    "gravite": gravite_d_un_verdict(v),
                    "cause": cause if cause in CAUSES else "prompt",
                    "replique": (citation or "")[:600] or None,
                    "confiance": float(v.get("confiance") or 0),
                    "version_numero": version_numero,
                },
                {
                    "run_id": run_id,
                    "tour": rang if isinstance(rang, int) else None,
                    "rang": rang_de_l_appelant(lignes, rang),
                    "citation": str(v.get("preuve") or "")[:300],
                },
            )
            touches += 1
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] verdicts de l'appel {run_id} non rangés : {type(erreur).__name__}")
    return touches


# --- le code et l'agent ------------------------------------------------------------------------------------------------------


async def ingerer_les_traces(
    organisation_id: int, workflow_id: int, run_id: int, contexte: dict[str, Any], indicateur: dict[str, Any], version_numero: int | None
) -> int:
    touches = 0
    try:
        for s in donnees.lire_les_signalements(contexte):
            gravite, cause = TRACES_DU_CODE.get(s["type"], (2, "prompt"))
            critere = s["type"] if s["type"] != donnees.TYPE_AGENT else f"{donnees.TYPE_AGENT}:{s.get('categorie') or ''}"
            titre = TITRES_DU_CODE.get(s["type"]) or str(s.get("motif") or "Signalé par l'agent")[:TITRE_MAX]
            await _ajouter(
                organisation_id,
                workflow_id,
                cle_de(RELEVE_PAR_CODE, critere, s.get("etape")),
                {
                    "releve_par": RELEVE_PAR_CODE,
                    "titre": titre,
                    "critere": critere,
                    "etape": s.get("etape"),
                    "gravite": gravite,
                    "cause": cause,
                    "replique": (str(s.get("motif") or "")[:600] or None) if s["type"] != donnees.TYPE_AGENT else None,
                    "version_numero": version_numero,
                },
                {"run_id": run_id, "tour": s.get("tour"), "rang": s.get("tour"), "citation": str(s.get("motif") or "")[:300]},
            )
            touches += 1
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] traces de l'appel {run_id} non rangées : {type(erreur).__name__}")
    return touches


# --- F : les tests -----------------------------------------------------------------------------------------------------------


async def ingerer_un_test(
    organisation_id: int,
    workflow_id: int,
    test: dict[str, Any],
    *,
    reussis: int,
    total: int,
    a_revoir: str | None = None,
    raison: str | None = None,
    version_numero: int | None = None,
) -> bool:
    """Un test qui échoue (au moins un essai raté) ou « réussi, à revoir » entre dans la file ; un test qui réussit pleinement et
    dont la relecture n'a rien dit n'y entre pas. Ne lève jamais."""
    try:
        echoue = total > 0 and reussis < total
        slug = str(test.get("slug") or test.get("nom") or "")
        if not echoue and not a_revoir:
            # Un test qui réussit de nouveau règle SON problème (il passe « Testée »).
            from api.services.boucle import avancement

            if total > 0:
                await avancement.un_test_reussit_de_nouveau(organisation_id, workflow_id, cle_de(RELEVE_PAR_TEST, f"echec:{slug}", None))
            return False
        critere = f"{'a_revoir' if a_revoir and not echoue else 'echec'}:{slug}"
        await _ajouter(
            organisation_id,
            workflow_id,
            cle_de(RELEVE_PAR_TEST, critere, None),
            {
                "releve_par": RELEVE_PAR_TEST,
                "titre": str(test.get("nom") or slug)[:TITRE_MAX],
                "critere": critere,
                "gravite": 3 if test.get("obligatoire") and echoue else 2,
                "cause": "prompt",
                "replique": (raison or a_revoir or None) and str(raison or a_revoir)[:600],
                "version_numero": version_numero,
            },
            {"test": slug, "reussis": reussis, "total": total, "a_revoir": bool(a_revoir and not echoue)},
        )
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] test {test.get('slug')} non rangé : {type(erreur).__name__}")
        return False


# --- l'après-appel -----------------------------------------------------------------------------------------------------------


async def bilan_de_l_appel(run: Any, organisation_id: int) -> dict[str, Any] | None:
    """Version, indicateurs et motif de l'appel dans ``annotations['boucle']``, puis les traces dans la file. Ne lève jamais."""
    try:
        from api.services.juge.appels import est_un_appel_d_essai

        if est_un_appel_d_essai(run):
            return None
        contexte = dict(getattr(run, "gathered_context", None) or {})
        journal = (getattr(run, "logs", None) or {}).get("realtime_feedback_events") or []
        usage = getattr(run, "usage_info", None) or {}
        cout_info = getattr(run, "cost_info", None) or {}
        estampille = await version.estampiller(run, organisation_id)
        indicateur = indicateurs.calculer(
            journal, contexte, duree=usage.get("call_duration_seconds"), cout=cout_info.get("total_cost_usd")
        )
        bilan = {"version": estampille, "indicateurs": indicateur}
        await db_client.update_workflow_run(run.id, annotations={"boucle": bilan})
        await ingerer_les_traces(organisation_id, run.workflow_id, run.id, contexte, indicateur, estampille.get("version"))
        return bilan
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] bilan de l'appel {getattr(run, 'id', '?')} non rangé : {type(erreur).__name__}")
        return None


async def ingerer_un_appel_juge(run: Any, organisation_id: int, verdicts: list[dict[str, Any]], lignes: list[tuple[str, str]]) -> int:
    """Les critères ratés d'un vrai appel jugé (sur clé d'API par l'après-appel, ou par Claude Code par ``juge_ecrire``) entrent dans
    la file, avec la cause lue sur les traces de CET appel et la version qui l'a mené. Ne lève jamais."""
    try:
        contexte = dict(getattr(run, "gathered_context", None) or {})
        journal = (getattr(run, "logs", None) or {}).get("realtime_feedback_events") or []
        indicateur = indicateurs.calculer(journal, contexte)
        definition = getattr(run, "definition", None)
        return await ingerer_les_verdicts(
            organisation_id,
            run.workflow_id,
            run.id,
            verdicts,
            lignes,
            cause=cause_d_un_cas(indicateur, contexte),
            version_numero=getattr(definition, "version_number", None),
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] appel jugé {getattr(run, 'id', '?')} non rangé : {type(erreur).__name__}")
        return 0
