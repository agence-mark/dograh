"""[.mark] builder partie 2, U8 : les lectures et écritures de la boucle (« À améliorer ») et de la page Qualité.

* ``mark_ameliorations`` : un problème regroupe ses cas ; l'état est celui du problème ;
* les lectures de la page Qualité sont BORNÉES (R7) : une organisation, une fenêtre de jours, seulement quelques morceaux JSON du run
  (``annotations['boucle']`` et le verdict du juge), jamais le journal ni le contexte entiers, au plus ``LIGNES_QUALITE_MAX`` runs.

⛔ Tout passe par ``organization_id`` : un problème ou un run d'une autre organisation n'est ni lu ni écrit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, cast, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB

from api.db.base_client import BaseDBClient
from api.db.models import WorkflowDefinitionModel, WorkflowModel, WorkflowRunModel
from api.db.models_boucle import MarkAmeliorationModel

LIGNES_QUALITE_MAX = 5000
CAS_GARDES = 50
CHAMPS_MODIFIABLES = frozenset({"etat", "assigne", "origine", "correction", "avancement", "gravite", "cause", "action"})
ETATS = ("a_trier", "en_cours", "testee", "publiee", "ignoree")
# Un problème déjà réglé qui revient (nouveau cas) est rouvert ; un problème ignoré le reste.
ETATS_ROUVERTS_PAR_UN_CAS = ("testee", "publiee")


def _vue(ligne: MarkAmeliorationModel) -> dict[str, Any]:
    return {
        "id": ligne.id,
        "organization_id": ligne.organization_id,
        "workflow_id": ligne.workflow_id,
        "cle": ligne.cle,
        "releve_par": ligne.releve_par,
        "titre": ligne.titre,
        "critere": ligne.critere,
        "etape": ligne.etape,
        "gravite": ligne.gravite,
        "cause": ligne.cause,
        "action": ligne.action,
        "etat": ligne.etat,
        "origine": ligne.origine,
        "assigne": ligne.assigne,
        "replique": ligne.replique,
        "confiance": ligne.confiance,
        "cas": list(ligne.cas or []),
        "nb_cas": ligne.nb_cas,
        "correction": ligne.correction,
        "avancement": dict(ligne.avancement or {}),
        "version_numero": ligne.version_numero,
        "premiere_le": ligne.premiere_le,
        "derniere_le": ligne.derniere_le,
    }


class BoucleClient(BaseDBClient):
    async def ajouter_un_cas_d_amelioration(
        self, organization_id: int, workflow_id: int, cle: str, valeurs: dict[str, Any], cas: dict[str, Any]
    ) -> dict[str, Any]:
        """Range un cas dans le problème de la clé (le crée au premier cas). Un même cas (appel, test) n'est jamais compté deux fois.
        La gravité garde la plus haute vue ; la réplique et la confiance sont celles du cas le plus récent."""
        maintenant = datetime.now(UTC)
        async with self.async_session() as session:
            existant = (
                await session.execute(
                    select(MarkAmeliorationModel)
                    .where(
                        MarkAmeliorationModel.organization_id == organization_id,
                        MarkAmeliorationModel.workflow_id == workflow_id,
                        MarkAmeliorationModel.cle == cle,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if existant is None:
                nouveau = MarkAmeliorationModel(
                    organization_id=organization_id,
                    workflow_id=workflow_id,
                    cle=cle,
                    cas=[{**cas, "le": cas.get("le") or maintenant.isoformat()}],
                    nb_cas=1,
                    avancement={},
                    premiere_le=maintenant,
                    derniere_le=maintenant,
                    **valeurs,
                )
                session.add(nouveau)
                try:
                    await session.flush()
                except Exception:  # noqa: BLE001 -- deux cas en même temps : l'autre a créé la ligne, on la relit
                    await session.rollback()
                    return await self.ajouter_un_cas_d_amelioration(organization_id, workflow_id, cle, valeurs, cas)
                await session.commit()
                await session.refresh(nouveau)
                return _vue(nouveau)
            identite = {k: cas.get(k) for k in ("run_id", "test") if cas.get(k) is not None}
            if any(all(c.get(k) == v for k, v in identite.items()) for c in existant.cas or []):
                return _vue(existant)  # déjà compté
            liste = [*(existant.cas or []), {**cas, "le": cas.get("le") or maintenant.isoformat()}][-CAS_GARDES:]
            existant.cas = liste
            existant.nb_cas = (existant.nb_cas or 0) + 1
            existant.derniere_le = maintenant
            existant.gravite = max(existant.gravite or 1, valeurs.get("gravite") or 1)
            for champ in ("replique", "confiance", "titre", "cause", "action", "version_numero"):
                if valeurs.get(champ) is not None:
                    setattr(existant, champ, valeurs[champ])
            if existant.etat in ETATS_ROUVERTS_PAR_UN_CAS:
                existant.etat = "a_trier"
                existant.avancement = {}
            await session.commit()
            await session.refresh(existant)
            return _vue(existant)

    async def retirer_les_cas_d_un_element(
        self, organization_id: int, workflow_id: int, *, releve_par: str, run_id: int | None = None, test: str | None = None
    ) -> int:
        """Rejuger un élément REMPLACE son jugement précédent : ses cas (même appel ou même test) sont retirés des problèmes du
        ``releve_par`` donné, puis le nouveau verdict les remet. Un problème qui n'a plus aucun cas et qu'on n'a pas encore traité
        (« à trier ») disparaît. Rend le nombre de cas retirés. ⛔ Une seule organisation, un seul agent."""
        identite = {k: v for k, v in (("run_id", run_id), ("test", test)) if v is not None}
        if not identite:
            return 0
        retires = 0
        async with self.async_session() as session:
            lignes = (
                await session.execute(
                    select(MarkAmeliorationModel)
                    .where(
                        MarkAmeliorationModel.organization_id == organization_id,
                        MarkAmeliorationModel.workflow_id == workflow_id,
                        MarkAmeliorationModel.releve_par == releve_par,
                    )
                    .with_for_update()
                )
            ).scalars().all()
            for ligne in lignes:
                restants = [c for c in ligne.cas or [] if not all(c.get(k) == v for k, v in identite.items())]
                if len(restants) == len(ligne.cas or []):
                    continue
                enleves = len(ligne.cas or []) - len(restants)
                retires += enleves
                if not restants and ligne.etat == "a_trier":
                    await session.delete(ligne)
                else:
                    ligne.cas = restants
                    ligne.nb_cas = max((ligne.nb_cas or 0) - enleves, 0)
            await session.commit()
        return retires

    async def lister_les_ameliorations(
        self,
        organization_id: int,
        *,
        etat: str | None = None,
        workflow_id: int | None = None,
        page: int = 0,
        par_page: int = 50,
        depuis: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Les problèmes de l'organisation, le plus grave puis le plus récent d'abord ; (lignes, a_une_suite)."""
        requete = select(MarkAmeliorationModel).where(MarkAmeliorationModel.organization_id == organization_id)
        if etat is not None:
            requete = requete.where(MarkAmeliorationModel.etat == etat)
        else:
            requete = requete.where(MarkAmeliorationModel.etat != "ignoree")
        if workflow_id is not None:
            requete = requete.where(MarkAmeliorationModel.workflow_id == workflow_id)
        if depuis is not None:
            requete = requete.where(MarkAmeliorationModel.derniere_le > depuis)
        requete = (
            requete.order_by(MarkAmeliorationModel.gravite.desc(), MarkAmeliorationModel.derniere_le.desc())
            .limit(par_page + 1)
            .offset(max(page, 0) * par_page)
        )
        async with self.async_session() as session:
            lignes = (await session.execute(requete)).scalars().all()
        return [_vue(ligne) for ligne in lignes[:par_page]], len(lignes) > par_page

    async def compter_les_ameliorations(self, organization_id: int, *, workflow_id: int | None = None) -> dict[str, int]:
        """Le nombre de problèmes par état (les ignorés ne comptent pas)."""
        requete = (
            select(MarkAmeliorationModel.etat, func.count())
            .where(MarkAmeliorationModel.organization_id == organization_id, MarkAmeliorationModel.etat != "ignoree")
            .group_by(MarkAmeliorationModel.etat)
        )
        if workflow_id is not None:
            requete = requete.where(MarkAmeliorationModel.workflow_id == workflow_id)
        async with self.async_session() as session:
            return {etat: n for etat, n in (await session.execute(requete)).all()}

    async def compter_les_ameliorations_graves(self, organization_id: int) -> int:
        """Partie 3, L5b : les problèmes À TRIER de gravité haute (3) de l'organisation (la page de pilotage d'un client)."""
        requete = select(func.count()).where(
            MarkAmeliorationModel.organization_id == organization_id,
            MarkAmeliorationModel.etat == "a_trier",
            MarkAmeliorationModel.gravite >= 3,
        )
        async with self.async_session() as session:
            return int((await session.execute(requete)).scalar_one())

    async def lire_une_amelioration(self, organization_id: int, amelioration_id: int) -> dict[str, Any] | None:
        async with self.async_session() as session:
            ligne = (
                await session.execute(
                    select(MarkAmeliorationModel).where(
                        MarkAmeliorationModel.id == amelioration_id,
                        MarkAmeliorationModel.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            return _vue(ligne) if ligne else None

    async def modifier_une_amelioration(self, organization_id: int, amelioration_id: int, **champs: Any) -> dict[str, Any] | None:
        inconnus = set(champs) - CHAMPS_MODIFIABLES
        if inconnus:
            raise ValueError(f"champ non modifiable : {sorted(inconnus)}")
        async with self.async_session() as session:
            ligne = (
                await session.execute(
                    select(MarkAmeliorationModel)
                    .where(
                        MarkAmeliorationModel.id == amelioration_id,
                        MarkAmeliorationModel.organization_id == organization_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if ligne is None:
                return None
            for champ, valeur in champs.items():
                setattr(ligne, champ, valeur)
            await session.commit()
            await session.refresh(ligne)
            return _vue(ligne)

    async def appels_de_l_agent(self, organization_id: int, *, jours: int, juges_seulement: bool = False) -> dict[int, int]:
        """Par agent de l'organisation, le nombre d'appels des ``jours`` derniers jours (ou seulement ceux que le juge a rendus).
        C'est le « M » de « N appels sur M »."""
        depuis = datetime.now(UTC) - timedelta(days=jours)
        requete = (
            select(WorkflowRunModel.workflow_id, func.count())
            .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
            .where(WorkflowModel.organization_id == organization_id, WorkflowRunModel.created_at >= depuis)
            .group_by(WorkflowRunModel.workflow_id)
        )
        if juges_seulement:
            annotations = cast(WorkflowRunModel.annotations, JSONB)
            requete = requete.where(func.jsonb_extract_path_text(annotations, "juge", "etat") == "juge")
        async with self.async_session() as session:
            return {wf: n for wf, n in (await session.execute(requete)).all()}

    async def runs_pour_la_qualite(
        self, organization_id: int, *, jours: int, workflow_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Les runs de la fenêtre, avec SEULEMENT ce que la page Qualité lit : le bilan de la boucle (``annotations['boucle']``),
        les verdicts du juge et la version de la définition. Au plus ``LIGNES_QUALITE_MAX``, les plus récents d'abord."""
        depuis = datetime.now(UTC) - timedelta(days=jours)
        annotations = cast(WorkflowRunModel.annotations, JSONB)
        morceau = func.jsonb_build_object(
            literal("boucle"),
            annotations.op("->")(literal("boucle")),
            literal("juge"),
            func.jsonb_build_object(
                literal("etat"),
                func.jsonb_extract_path(annotations, "juge", "etat"),
                literal("verdicts"),
                func.jsonb_extract_path(annotations, "juge", "verdicts"),
            ),
        )
        requete = (
            select(
                WorkflowRunModel.id,
                WorkflowRunModel.workflow_id,
                WorkflowModel.name,
                WorkflowRunModel.created_at,
                WorkflowDefinitionModel.version_number,
                morceau,
            )
            .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
            .outerjoin(WorkflowDefinitionModel, WorkflowDefinitionModel.id == WorkflowRunModel.definition_id)
            .where(and_(WorkflowModel.organization_id == organization_id, WorkflowRunModel.created_at >= depuis))
            .order_by(WorkflowRunModel.id.desc())
            .limit(LIGNES_QUALITE_MAX)
        )
        if workflow_id is not None:
            requete = requete.where(WorkflowRunModel.workflow_id == workflow_id)
        async with self.async_session() as session:
            lignes = (await session.execute(requete)).all()
        return [
            {
                "run_id": run_id,
                "workflow_id": wf,
                "workflow_nom": nom,
                "cree_le": cree_le,
                "version": version,
                "annotations": extrait or {},
            }
            for run_id, wf, nom, cree_le, version, extrait in lignes
        ]

    # ------------------------------------------------------------------ vues « tous clients » (partie 3, sous-lot 10)
    # Lecture seule, pour l'équipe .mark : le filtre par organisation est DANS chaque requête (``organization_id IN (…)``), sur la
    # liste que le rôle du compte ouvre ; une liste vide ne lit rien. Jamais une requête par client.

    async def lister_ameliorations_des_organisations(
        self, organisations: list[int], *, etat: str, page: int = 0, par_page: int = 50
    ) -> tuple[list[dict[str, Any]], bool]:
        """Les problèmes d'un état pour plusieurs organisations, le plus grave puis le plus récent d'abord ; (lignes, a_une_suite)."""
        if not organisations:
            return [], False
        requete = (
            select(MarkAmeliorationModel)
            .where(MarkAmeliorationModel.organization_id.in_(organisations), MarkAmeliorationModel.etat == etat)
            .order_by(MarkAmeliorationModel.gravite.desc(), MarkAmeliorationModel.derniere_le.desc(), MarkAmeliorationModel.id.desc())
            .limit(par_page + 1)
            .offset(max(page, 0) * par_page)
        )
        async with self.async_session() as session:
            lignes = (await session.execute(requete)).scalars().all()
        return [_vue(ligne) for ligne in lignes[:par_page]], len(lignes) > par_page

    async def compter_ameliorations_des_organisations(self, organisations: list[int]) -> dict[str, int]:
        """Le nombre de problèmes par état pour plusieurs organisations (les ignorés ne comptent pas). Une seule requête."""
        if not organisations:
            return {}
        requete = (
            select(MarkAmeliorationModel.etat, func.count())
            .where(MarkAmeliorationModel.organization_id.in_(organisations), MarkAmeliorationModel.etat != "ignoree")
            .group_by(MarkAmeliorationModel.etat)
        )
        async with self.async_session() as session:
            return {etat: n for etat, n in (await session.execute(requete)).all()}

    async def appels_des_agents_des_organisations(
        self, organisations: list[int], *, jours: int, juges_seulement: bool = False
    ) -> dict[int, int]:
        """Comme ``appels_de_l_agent`` pour plusieurs organisations (l'identifiant d'un agent est unique : une seule table de comptes)."""
        if not organisations:
            return {}
        depuis = datetime.now(UTC) - timedelta(days=jours)
        requete = (
            select(WorkflowRunModel.workflow_id, func.count())
            .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
            .where(WorkflowModel.organization_id.in_(organisations), WorkflowRunModel.created_at >= depuis)
            .group_by(WorkflowRunModel.workflow_id)
        )
        if juges_seulement:
            annotations = cast(WorkflowRunModel.annotations, JSONB)
            requete = requete.where(func.jsonb_extract_path_text(annotations, "juge", "etat") == "juge")
        async with self.async_session() as session:
            return {wf: n for wf, n in (await session.execute(requete)).all()}

    async def noms_des_agents_des_organisations(self, organisations: list[int], workflow_ids: list[int]) -> dict[int, str]:
        if not organisations or not workflow_ids:
            return {}
        requete = select(WorkflowModel.id, WorkflowModel.name).where(
            WorkflowModel.organization_id.in_(organisations), WorkflowModel.id.in_(workflow_ids)
        )
        async with self.async_session() as session:
            return {i: n for i, n in (await session.execute(requete)).all()}

    async def runs_pour_la_qualite_des_organisations(
        self, organisations: list[int], *, jours: int, par_organisation: int = 1000
    ) -> list[dict[str, Any]]:
        """Les runs de la fenêtre de plusieurs organisations, au plus ``par_organisation`` par organisation (les plus récents) : une
        organisation très active n'efface pas les autres. Une seule requête (fenêtre ``row_number``), mêmes morceaux JSON que
        ``runs_pour_la_qualite``."""
        if not organisations:
            return []
        depuis = datetime.now(UTC) - timedelta(days=jours)
        annotations = cast(WorkflowRunModel.annotations, JSONB)
        morceau = func.jsonb_build_object(
            literal("boucle"),
            annotations.op("->")(literal("boucle")),
            literal("juge"),
            func.jsonb_build_object(
                literal("etat"),
                func.jsonb_extract_path(annotations, "juge", "etat"),
                literal("verdicts"),
                func.jsonb_extract_path(annotations, "juge", "verdicts"),
            ),
        )
        rang = func.row_number().over(partition_by=WorkflowModel.organization_id, order_by=WorkflowRunModel.id.desc()).label("rang")
        sous = (
            select(
                WorkflowRunModel.id.label("run_id"),
                WorkflowRunModel.workflow_id.label("workflow_id"),
                WorkflowModel.organization_id.label("organization_id"),
                WorkflowModel.name.label("nom"),
                WorkflowRunModel.created_at.label("cree_le"),
                WorkflowDefinitionModel.version_number.label("version"),
                morceau.label("extrait"),
                rang,
            )
            .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
            .outerjoin(WorkflowDefinitionModel, WorkflowDefinitionModel.id == WorkflowRunModel.definition_id)
            .where(and_(WorkflowModel.organization_id.in_(organisations), WorkflowRunModel.created_at >= depuis))
            .subquery()
        )
        requete = select(sous).where(sous.c.rang <= par_organisation).order_by(sous.c.run_id.desc())
        async with self.async_session() as session:
            lignes = (await session.execute(requete)).all()
        return [
            {
                "run_id": ligne.run_id,
                "workflow_id": ligne.workflow_id,
                "organization_id": ligne.organization_id,
                "workflow_nom": ligne.nom,
                "cree_le": ligne.cree_le,
                "version": ligne.version,
                "annotations": ligne.extrait or {},
            }
            for ligne in lignes
        ]

    async def lire_une_amelioration_par_cle(self, organization_id: int, workflow_id: int, cle: str) -> dict[str, Any] | None:
        async with self.async_session() as session:
            ligne = (
                await session.execute(
                    select(MarkAmeliorationModel).where(
                        MarkAmeliorationModel.organization_id == organization_id,
                        MarkAmeliorationModel.workflow_id == workflow_id,
                        MarkAmeliorationModel.cle == cle,
                    )
                )
            ).scalar_one_or_none()
            return _vue(ligne) if ligne else None

    async def faire_avancer_les_ameliorations(
        self,
        organization_id: int,
        workflow_id: int,
        *,
        de: tuple[str, ...],
        vers: str,
        temps: str | None = None,
        cle: str | None = None,
    ) -> int:
        """Passe les problèmes de l'agent qui sont dans un des états ``de`` à l'état ``vers`` (et coche le ``temps`` de l'avancement).
        ``cle`` : un seul problème. Rend le nombre de problèmes touchés."""
        async with self.async_session() as session:
            requete = select(MarkAmeliorationModel).where(
                MarkAmeliorationModel.organization_id == organization_id,
                MarkAmeliorationModel.workflow_id == workflow_id,
                MarkAmeliorationModel.etat.in_(de),
            )
            if cle is not None:
                requete = requete.where(MarkAmeliorationModel.cle == cle)
            lignes = (await session.execute(requete.with_for_update())).scalars().all()
            for ligne in lignes:
                ligne.etat = vers
                if temps:
                    ligne.avancement = {**(ligne.avancement or {}), temps: True}
            await session.commit()
            return len(lignes)

    async def resumes_de_runs(self, organization_id: int, run_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Pour les runs donnés (de l'organisation seulement) : l'agent, la date, la durée et le motif. Une seule requête."""
        if not run_ids:
            return {}
        annotations = cast(WorkflowRunModel.annotations, JSONB)
        requete = (
            select(
                WorkflowRunModel.id,
                WorkflowRunModel.workflow_id,
                WorkflowModel.name,
                WorkflowRunModel.created_at,
                cast(WorkflowRunModel.usage_info, JSONB).op("->>")(literal("call_duration_seconds")),
                func.jsonb_extract_path_text(annotations, "boucle", "indicateurs", "motif"),
            )
            .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
            .where(WorkflowModel.organization_id == organization_id, WorkflowRunModel.id.in_(run_ids[:200]))
        )
        async with self.async_session() as session:
            lignes = (await session.execute(requete)).all()
        return {
            run_id: {"workflow_id": wf, "workflow_nom": nom, "cree_le": cree_le, "duree": float(duree) if duree else None, "motif": motif}
            for run_id, wf, nom, cree_le, duree, motif in lignes
        }

    async def noms_des_agents(self, organization_id: int, workflow_ids: list[int]) -> dict[int, str]:
        if not workflow_ids:
            return {}
        requete = select(WorkflowModel.id, WorkflowModel.name).where(
            WorkflowModel.organization_id == organization_id, WorkflowModel.id.in_(workflow_ids)
        )
        async with self.async_session() as session:
            return {i: n for i, n in (await session.execute(requete)).all()}
