"""[.mark] passages-fiables (lot G) : les lectures de la file de tri et des alertes.

Aucune migration : tout est lu dans les colonnes JSON existantes du run (``gathered_context`` pour ce que l'appel a noté,
``annotations["tri"]`` pour le statut de tri). Chaque requête est **bornée** (R7) : une organisation, une fenêtre de
jours, les runs qui portent quelque chose (filtre ``jsonpath`` côté base), une page de 50. Seules les clés utiles du
contexte sont lues, jamais le contexte entier (traces du modèle, résultats d'outils).

⛔ Tout passe par ``organization_id`` : un run d'une autre organisation n'est ni lu ni modifié.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, cast, func, literal, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import UserDefinedType

from api.db.base_client import BaseDBClient
from api.db.models import WorkflowModel, WorkflowRunModel
from api.services.tri.donnees import (
    CHEMIN_AVEC_IMPASSE,
    CHEMIN_AVEC_REPRISE,
    CHEMIN_PORTE_LE_COMPTEUR,
    CLE_IMPASSE,
    CLE_TRI,
    JOURS_DE_LECTURE,
    RUNS_PAR_PAGE,
    STATUTS,
    ligne_de_taux,
)


class JSONPATH(UserDefinedType):
    """Le type ``jsonpath`` de PostgreSQL, pour que la valeur du chemin soit liée comme paramètre (jamais collée dans le SQL)."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "JSONPATH"


class TriClient(BaseDBClient):
    async def runs_avec(
        self,
        organization_id: int,
        *,
        chemin: str,
        cles: tuple[str, ...],
        page: int = 0,
        workflow_id: int | None = None,
        jours: int = JOURS_DE_LECTURE,
        par_page: int = RUNS_PAR_PAGE,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Les runs de l'organisation, des ``jours`` derniers jours, qui satisfont le filtre ``chemin`` (jsonpath sur
        ``gathered_context``), du plus récent au plus ancien. Rend (lignes, a_une_suite). Chaque ligne : ``run_id``,
        ``workflow_id``, ``workflow_nom``, ``cree_le``, ``extrait`` (seulement ``cles``), ``annotations``."""
        depuis = datetime.now(timezone.utc) - timedelta(days=jours)
        contexte = cast(WorkflowRunModel.gathered_context, JSONB)
        extrait = func.jsonb_build_object(*[morceau for cle in cles for morceau in (literal(cle), contexte.op("->")(literal(cle)))])
        requete = (
            select(
                WorkflowRunModel.id,
                WorkflowRunModel.workflow_id,
                WorkflowModel.name,
                WorkflowRunModel.created_at,
                extrait,
                WorkflowRunModel.annotations,
            )
            .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
            .where(
                and_(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowRunModel.created_at >= depuis,
                    text("jsonb_path_exists(workflow_runs.gathered_context::jsonb, CAST(:chemin AS jsonpath))").bindparams(
                        chemin=chemin
                    ),
                )
            )
            .order_by(WorkflowRunModel.id.desc())
            .limit(par_page + 1)
            .offset(max(page, 0) * par_page)
        )
        if workflow_id is not None:
            requete = requete.where(WorkflowRunModel.workflow_id == workflow_id)
        async with self.async_session() as session:
            lignes = (await session.execute(requete)).all()
        a_une_suite = len(lignes) > par_page
        return (
            [
                {
                    "run_id": run_id,
                    "workflow_id": wf_id,
                    "workflow_nom": nom,
                    "cree_le": cree_le,
                    "extrait": extrait_json or {},
                    "annotations": annotations or {},
                }
                for run_id, wf_id, nom, cree_le, extrait_json, annotations in lignes[:par_page]
            ],
            a_une_suite,
        )

    async def taux_de_sortie_d_impasse(self, organization_id: int, *, jours: int) -> list[dict[str, Any]]:
        """Par agent de l'organisation, sur les ``jours`` derniers jours : les appels, ceux qui ont eu au moins une impasse, ceux
        dont la fiche porte le compteur de reprises, et ceux qui ont une reprise sans impasse. Un seul passage SQL, aucun
        contexte lu en entier. ⛔ Seuls les runs de l'organisation : la jointure sur ``WorkflowModel.organization_id``."""
        depuis = datetime.now(timezone.utc) - timedelta(days=jours)
        # ``gathered_context`` est du JSON : l'objet ``impasse`` est extrait et converti UNE fois par run (sous-requête), puis les
        # trois chemins le lisent (un run sans impasse donne NULL : aucun des comptes ne le compte).
        impasse = cast(WorkflowRunModel.gathered_context, JSONB).op("->")(literal(CLE_IMPASSE)).label("impasse")
        runs = (
            select(WorkflowRunModel.workflow_id.label("workflow_id"), impasse)
            .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
            .where(and_(WorkflowModel.organization_id == organization_id, WorkflowRunModel.created_at >= depuis))
            .subquery()
        )

        def existe(chemin: str):
            return func.jsonb_path_exists(runs.c.impasse, cast(literal(chemin), JSONPATH))

        requete = (
            select(
                runs.c.workflow_id,
                WorkflowModel.name,
                func.count(),
                func.count().filter(existe(CHEMIN_AVEC_IMPASSE)),
                func.count().filter(existe(CHEMIN_PORTE_LE_COMPTEUR)),
                func.count().filter(and_(existe(CHEMIN_AVEC_REPRISE), ~existe(CHEMIN_AVEC_IMPASSE))),
            )
            .join(WorkflowModel, WorkflowModel.id == runs.c.workflow_id)
            .group_by(runs.c.workflow_id, WorkflowModel.name)
            .order_by(runs.c.workflow_id)
        )
        async with self.async_session() as session:
            lignes = (await session.execute(requete)).all()
        return [ligne_de_taux(*ligne) for ligne in lignes]

    async def run_de_l_organisation(self, organization_id: int, run_id: int) -> dict[str, Any] | None:
        """Le contexte utile d'UN run, seulement s'il est de l'organisation (sinon ``None``, jamais une fuite)."""
        async with self.async_session() as session:
            ligne = (
                await session.execute(
                    select(WorkflowRunModel.id, WorkflowRunModel.gathered_context, WorkflowRunModel.annotations)
                    .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                    .where(WorkflowRunModel.id == run_id, WorkflowModel.organization_id == organization_id)
                )
            ).first()
        if ligne is None:
            return None
        return {"run_id": ligne[0], "gathered_context": ligne[1] or {}, "annotations": ligne[2] or {}}

    async def ecrire_le_tri(
        self, organization_id: int, run_id: int, identifiant: str, statut: str, par: int | None = None
    ) -> bool:
        """Écrit le statut d'un signalement dans ``annotations["tri"]`` du run, sous verrou de ligne, sans toucher au reste.
        ``False`` : run absent ou d'une autre organisation, ou statut inconnu."""
        if statut not in STATUTS:
            return False
        async with self.async_session() as session:
            resultat = await session.execute(
                select(WorkflowRunModel)
                .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                .where(WorkflowRunModel.id == run_id, WorkflowModel.organization_id == organization_id)
                .with_for_update(of=WorkflowRunModel)
            )
            run = resultat.scalars().first()
            if run is None:
                return False
            annotations = copy.deepcopy(run.annotations or {})
            tri = dict(annotations.get(CLE_TRI) or {})
            tri[identifiant] = {"statut": statut, "le": datetime.now(timezone.utc).isoformat(), "par": par}
            annotations[CLE_TRI] = tri
            run.annotations = annotations
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            return True
