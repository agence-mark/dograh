"""[.mark] Chantier Partie 1, lot 17 : la couche de données des gabarits (D11), de leurs applications et de leurs diffusions.

* une version de gabarit est FIGÉE : ``figer_le_gabarit`` l'écrit une fois ; la même version avec un autre contenu est refusée
  (``GabaritDejaFige``), jamais réécrite ;
* une application (un agent installé depuis un gabarit) se lit et s'écrit TOUJOURS avec l'organisation dans la requête ; la liste
  de toutes les organisations n'est rendue qu'à la diffusion, qui contrôle d'abord la clé de son geste ;
* le rodage (D28) : un appel relu s'ajoute une fois (``UPDATE ... WHERE NOT (rodage_relus @> ...)``), deux relectures simultanées du
  même appel n'en comptent qu'une.

Les lectures rendent des dictionnaires (jamais un objet lié à une session fermée).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, select, text, update
from sqlalchemy.dialects.postgresql import insert

from api.db.base_client import BaseDBClient
from api.db.models_gabarits import GabaritApplicationModel, GabaritDiffusionModel, GabaritModel

LIGNES_MAX = 500  # une lecture de liste n'en rend jamais plus (pagination par ``apres_id``)


class GabaritDejaFige(Exception):
    """La version existe déjà avec un autre contenu : une version figée ne change jamais."""


def _gabarit(g: GabaritModel) -> dict[str, Any]:
    return {"id": g.id, "nom": g.nom, "version": g.version, "contenu": g.contenu, "empreinte": g.empreinte, "statut": g.statut, "cree_le": g.cree_le}


def _application(a: GabaritApplicationModel) -> dict[str, Any]:
    return {
        "id": a.id,
        "organization_id": a.organization_id,
        "workflow_id": a.workflow_id,
        "gabarit_nom": a.gabarit_nom,
        "gabarit_version": a.gabarit_version,
        "commit_fork": a.commit_fork,
        "agents": dict(a.agents or {}),
        "trous": dict(a.trous or {}),
        "formulaire": dict(a.formulaire or {}),
        "retouches": dict(a.retouches or {}),
        "empreinte_retouches": a.empreinte_retouches,
        "rodage_relus": list(a.rodage_relus or []),
        "installee_le": a.installee_le,
        "maj_le": a.maj_le,
    }


def _diffusion(d: GabaritDiffusionModel) -> dict[str, Any]:
    return {
        "id": d.id,
        "gabarit_nom": d.gabarit_nom,
        "gabarit_version": d.gabarit_version,
        "portee": d.portee,
        "organization_id": d.organization_id,
        "par_user_id": d.par_user_id,
        "statut": d.statut,
        "resultat": dict(d.resultat or {}),
        "le": d.le,
    }


class GabaritsClient(BaseDBClient):
    # ------------------------------------------------------------------ les versions figées

    async def figer_le_gabarit(self, nom: str, version: int, contenu: dict[str, Any], empreinte: str) -> dict[str, Any]:
        """Écrit la version si elle manque ; la rend telle qu'en base. Même version, autre empreinte : ``GabaritDejaFige``."""
        async with self.async_session() as session:
            await session.execute(
                insert(GabaritModel)
                .values(nom=nom, version=version, contenu=contenu, empreinte=empreinte)
                .on_conflict_do_nothing(constraint="uq_mark_gabarits_nom_version")
            )
            await session.commit()
            ligne = await session.scalar(select(GabaritModel).where(GabaritModel.nom == nom, GabaritModel.version == version))
        if ligne.empreinte != empreinte:
            raise GabaritDejaFige(f"{nom} v{version}")
        return _gabarit(ligne)

    async def lire_le_gabarit(self, nom: str, version: int | None = None) -> dict[str, Any] | None:
        """La version demandée, ou la plus récente des actives."""
        async with self.async_session() as session:
            requete = select(GabaritModel).where(GabaritModel.nom == nom)
            if version is None:
                requete = requete.where(GabaritModel.statut == "actif").order_by(GabaritModel.version.desc()).limit(1)
            else:
                requete = requete.where(GabaritModel.version == version)
            ligne = await session.scalar(requete)
        return _gabarit(ligne) if ligne else None

    # ------------------------------------------------------------------ les applications (un agent installé)

    async def ecrire_l_application(self, organization_id: int, workflow_id: int, **champs: Any) -> dict[str, Any]:
        """Crée ou met à jour l'application de l'agent ``workflow_id`` DE CETTE organisation (rejouable : même ligne)."""
        maintenant = datetime.now(UTC)
        async with self.async_session() as session:
            existante = await session.scalar(
                select(GabaritApplicationModel).where(
                    GabaritApplicationModel.workflow_id == workflow_id, GabaritApplicationModel.organization_id == organization_id
                )
            )
            if existante is None:
                ligne = GabaritApplicationModel(organization_id=organization_id, workflow_id=workflow_id, maj_le=maintenant, **champs)
                session.add(ligne)
            else:
                for cle, valeur in champs.items():
                    setattr(existante, cle, valeur)
                existante.maj_le = maintenant
                ligne = existante
            await session.commit()
            await session.refresh(ligne)
            return _application(ligne)

    async def application_de(self, organization_id: int, workflow_id: int) -> dict[str, Any] | None:
        """L'application dont ``workflow_id`` est le principal OU une étape, dans CETTE organisation ; ``None`` sinon (404 en amont)."""
        async with self.async_session() as session:
            ligne = await session.scalar(
                select(GabaritApplicationModel).where(
                    GabaritApplicationModel.organization_id == organization_id,
                    (GabaritApplicationModel.workflow_id == workflow_id)
                    | GabaritApplicationModel.agents.op("@>")(text(f"'{{\"_ids\": [{int(workflow_id)}]}}'::jsonb")),
                )
            )
        return _application(ligne) if ligne else None

    async def applications_du_gabarit(
        self, nom: str, *, organization_id: int | None, apres_id: int = 0, limite: int = LIGNES_MAX
    ) -> list[dict[str, Any]]:
        """Les applications d'un gabarit : d'UNE organisation (``organization_id``), ou de toutes (``None``, réservé à la diffusion
        « toutes les organisations », contrôlée avant). Paginé par identifiant."""
        async with self.async_session() as session:
            from api.db.models import WorkflowModel

            # Lot 20 : une application dont l'agent principal est archivé n'est ni diffusée ni lue par la porte (des installations d'essai archivées
            # bloquaient la diffusion de toute l'organisation).
            conditions = [GabaritApplicationModel.gabarit_nom == nom, GabaritApplicationModel.id > apres_id, WorkflowModel.status == "active"]
            if organization_id is not None:
                conditions.append(GabaritApplicationModel.organization_id == organization_id)
            lignes = await session.scalars(
                select(GabaritApplicationModel).join(WorkflowModel, WorkflowModel.id == GabaritApplicationModel.workflow_id)
                .where(and_(*conditions)).order_by(GabaritApplicationModel.id).limit(min(limite, LIGNES_MAX))
            )
            return [_application(l) for l in lignes]

    async def applications_de_l_etablissement(self, organization_id: int, etablissement_id: int) -> list[dict[str, Any]]:
        """Les agents installés de CETTE organisation qui servent cet établissement de sa base (la carte change : leurs tests se régénèrent)."""
        async with self.async_session() as session:
            lignes = await session.scalars(
                select(GabaritApplicationModel)
                .where(
                    GabaritApplicationModel.organization_id == organization_id,
                    GabaritApplicationModel.formulaire["etablissement_id"].astext == str(int(etablissement_id)),
                )
                .order_by(GabaritApplicationModel.id)
                .limit(LIGNES_MAX)
            )
            return [_application(l) for l in lignes]

    async def noter_un_appel_relu(self, organization_id: int, workflow_id: int, run_id: int) -> list[int] | None:
        """Ajoute ``run_id`` aux appels relus (une seule fois) ; rend la liste, ``None`` si l'application n'est pas de cette organisation."""
        async with self.async_session() as session:
            await session.execute(
                update(GabaritApplicationModel)
                .where(
                    GabaritApplicationModel.organization_id == organization_id,
                    GabaritApplicationModel.workflow_id == workflow_id,
                    ~GabaritApplicationModel.rodage_relus.op("@>")(text(f"'[{int(run_id)}]'::jsonb")),
                )
                .values(rodage_relus=GabaritApplicationModel.rodage_relus.op("||")(text(f"'[{int(run_id)}]'::jsonb")), maj_le=datetime.now(UTC))
            )
            await session.commit()
            relus = await session.scalar(
                select(GabaritApplicationModel.rodage_relus).where(
                    GabaritApplicationModel.organization_id == organization_id, GabaritApplicationModel.workflow_id == workflow_id
                )
            )
        return None if relus is None else [int(x) for x in relus]

    # ------------------------------------------------------------------ le journal des diffusions

    async def noter_une_diffusion(
        self, *, nom: str, version: int, portee: str, organization_id: int | None, par_user_id: int | None, statut: str, resultat: dict[str, Any]
    ) -> dict[str, Any]:
        async with self.async_session() as session:
            ligne = GabaritDiffusionModel(
                gabarit_nom=nom, gabarit_version=version, portee=portee, organization_id=organization_id, par_user_id=par_user_id,
                statut=statut, resultat=json.loads(json.dumps(resultat, default=str)),
            )
            session.add(ligne)
            await session.commit()
            await session.refresh(ligne)
            return _diffusion(ligne)

    async def diffusions_de(self, nom: str, *, organization_id: int | None, limite: int = 50) -> list[dict[str, Any]]:
        """Le journal des diffusions d'un gabarit : celles qui visaient CETTE organisation (``organization_id``), ou toutes (``None``)."""
        async with self.async_session() as session:
            requete = select(GabaritDiffusionModel).where(GabaritDiffusionModel.gabarit_nom == nom)
            if organization_id is not None:
                requete = requete.where(GabaritDiffusionModel.organization_id == organization_id)
            lignes = await session.scalars(requete.order_by(GabaritDiffusionModel.le.desc(), GabaritDiffusionModel.id.desc()).limit(min(limite, LIGNES_MAX)))
            return [_diffusion(l) for l in lignes]
