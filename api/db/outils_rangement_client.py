"""[.mark] Lot 11 du chantier module (E-22, E-46) : le rangement des outils (dossiers) et les kits d'outils.

Mécanisme commun : aucun mot de métier. Deux familles de gestes :

- les DOSSIERS d'une organisation (``tool_folders``) : deux niveaux au plus, un outil a au plus un dossier ; supprimer un dossier supprime ses
  sous-dossiers et jamais un outil. Chaque requête filtre par organisation DANS la requête (un dossier d'une autre organisation n'existe pas) ;
- les KITS du fork (``tool_kits``, aucune organisation) : lus par tous, écrits par l'équipe (la route le contrôle). Appliquer un kit COPIE ses outils
  dans l'organisation ; une version plus récente d'un outil du kit est PROPOSÉE, l'organisation l'accepte ou non (un agent reste sur la version d'outil
  que sa version publiée a figée : ``tool_versions`` et ``outils_epingles``). Le kit ne touche jamais un agent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from api.db.base_client import BaseDBClient
from api.db.models import ToolFolderModel, ToolKitItemModel, ToolKitModel, ToolModel
from api.db.models_builder import ToolVersionModel
from api.enums import ToolStatus

# Ce qu'un kit peut porter : une définition sans identifiant d'un client. Un appel HTTP ou un serveur MCP porte une adresse, des en-têtes
# et un identifiant propres à une organisation : jamais dans un kit du fork.
CATEGORIES_DE_KIT = ("integration", "native", "calculator", "end_call")
# Les champs d'une définition d'outil qui appartiennent à UNE organisation : retirés en entrant dans un kit, gardés quand un kit se met à jour.
CHAMPS_DE_L_ORGANISATION = ("compte", "dernier_essai", "premier_essai")


class ErreurRangement(Exception):
    """Un refus normal. ``code`` : introuvable (404), conflit (409), invalide (422)."""

    def __init__(self, message: str, code: str = "introuvable"):
        super().__init__(message)
        self.code = code


def definition_sans_compte(definition: dict[str, Any]) -> dict[str, Any]:
    """La définition d'un outil sans ce qui appartient à une organisation (compte connecté, derniers essais)."""
    copie = {**definition}
    config = copie.get("config")
    if isinstance(config, dict):
        copie["config"] = {k: v for k, v in config.items() if k not in CHAMPS_DE_L_ORGANISATION}
    return copie


def _fusionner_la_definition(kit: dict[str, Any], actuelle: dict[str, Any]) -> dict[str, Any]:
    """La définition du kit, avec ce qui appartient à l'organisation repris de l'outil qu'elle a déjà."""
    neuve = definition_sans_compte(kit)
    ancienne = (actuelle or {}).get("config")
    if isinstance(neuve.get("config"), dict) and isinstance(ancienne, dict):
        for cle in CHAMPS_DE_L_ORGANISATION:
            if cle in ancienne:
                neuve["config"][cle] = ancienne[cle]
    return neuve


class OutilsRangementClient(BaseDBClient):
    # ------------------------------------------------------------------ dossiers

    async def lister_dossiers_d_outils(self, organization_id: int) -> list[dict[str, Any]]:
        """En liste simple, avec le nombre d'outils (non archivés) rangés directement dans chaque dossier."""
        async with self.async_session() as session:
            dossiers = (
                await session.scalars(
                    select(ToolFolderModel)
                    .where(ToolFolderModel.organization_id == organization_id)
                    .order_by(ToolFolderModel.name)
                )
            ).all()
            comptes = dict(
                (
                    await session.execute(
                        select(ToolModel.folder_id, func.count())
                        .where(
                            ToolModel.organization_id == organization_id,
                            ToolModel.folder_id.is_not(None),
                            ToolModel.status != ToolStatus.ARCHIVED.value,
                        )
                        .group_by(ToolModel.folder_id)
                    )
                ).all()
            )
            return [
                {"id": d.id, "name": d.name, "parent_id": d.parent_id, "created_at": d.created_at, "tool_count": comptes.get(d.id, 0)}
                for d in dossiers
            ]

    async def _dossier(self, session, organization_id: int, dossier_id: int) -> ToolFolderModel:
        dossier = await session.scalar(
            select(ToolFolderModel).where(ToolFolderModel.id == dossier_id, ToolFolderModel.organization_id == organization_id)
        )
        if dossier is None:
            raise ErreurRangement("Folder not found")
        return dossier

    async def _nom_de_dossier_pris(self, session, organization_id: int, parent_id: int | None, name: str, sauf: int | None = None) -> bool:
        """Vérifié AVANT l'écriture (un refus normal ne passe pas par l'erreur d'intégrité) ; l'index unique reste le filet d'une course."""
        requete = select(func.count()).select_from(ToolFolderModel).where(
            ToolFolderModel.organization_id == organization_id,
            func.coalesce(ToolFolderModel.parent_id, 0) == (parent_id or 0),
            ToolFolderModel.name == name,
        )
        if sauf is not None:
            requete = requete.where(ToolFolderModel.id != sauf)
        return bool(await session.scalar(requete))

    async def creer_dossier_d_outils(self, organization_id: int, name: str, parent_id: int | None = None) -> ToolFolderModel:
        async with self.async_session() as session:
            if parent_id is not None:
                parent = await self._dossier(session, organization_id, parent_id)
                if parent.parent_id is not None:
                    raise ErreurRangement("A folder holds one level of sub-folders at most", "invalide")
            if await self._nom_de_dossier_pris(session, organization_id, parent_id, name):
                raise ErreurRangement(f"A folder named '{name}' already exists here", "conflit")
            dossier = ToolFolderModel(organization_id=organization_id, name=name, parent_id=parent_id)
            session.add(dossier)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ErreurRangement(f"A folder named '{name}' already exists here", "conflit") from None
            await session.refresh(dossier)
            return dossier

    async def renommer_dossier_d_outils(self, organization_id: int, dossier_id: int, name: str) -> ToolFolderModel:
        async with self.async_session() as session:
            dossier = await self._dossier(session, organization_id, dossier_id)
            if await self._nom_de_dossier_pris(session, organization_id, dossier.parent_id, name, sauf=dossier_id):
                raise ErreurRangement(f"A folder named '{name}' already exists here", "conflit")
            dossier.name = name
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ErreurRangement(f"A folder named '{name}' already exists here", "conflit") from None
            await session.refresh(dossier)
            return dossier

    async def deplacer_dossier_d_outils(self, organization_id: int, dossier_id: int, parent_id: int | None) -> ToolFolderModel:
        """Sous un autre dossier de premier niveau, ou au premier niveau (``None``). Deux niveaux au plus."""
        async with self.async_session() as session:
            dossier = await self._dossier(session, organization_id, dossier_id)
            if parent_id is not None:
                if parent_id == dossier_id:
                    raise ErreurRangement("A folder cannot be its own parent", "conflit")
                parent = await self._dossier(session, organization_id, parent_id)
                if parent.parent_id is not None:
                    raise ErreurRangement("A folder holds one level of sub-folders at most", "invalide")
                a_des_enfants = await session.scalar(
                    select(func.count()).select_from(ToolFolderModel).where(
                        ToolFolderModel.organization_id == organization_id, ToolFolderModel.parent_id == dossier_id
                    )
                )
                if a_des_enfants:
                    raise ErreurRangement("A folder that holds sub-folders stays at the top level", "invalide")
            if await self._nom_de_dossier_pris(session, organization_id, parent_id, dossier.name, sauf=dossier_id):
                raise ErreurRangement("A folder with this name already exists there", "conflit")
            dossier.parent_id = parent_id
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ErreurRangement("A folder with this name already exists there", "conflit") from None
            await session.refresh(dossier)
            return dossier

    async def supprimer_dossier_d_outils(self, organization_id: int, dossier_id: int) -> dict[str, int]:
        """Supprime le dossier et ses sous-dossiers ; les outils restent, sans dossier. Rend ce qui a été retiré."""
        async with self.async_session() as session:
            dossier = await self._dossier(session, organization_id, dossier_id)
            ids = [dossier.id] + list(
                (
                    await session.scalars(
                        select(ToolFolderModel.id).where(
                            ToolFolderModel.organization_id == organization_id, ToolFolderModel.parent_id == dossier.id
                        )
                    )
                ).all()
            )
            # Les outils d'abord (explicite : le filet de la base fait la même chose), puis les dossiers.
            sortis = await session.execute(
                update(ToolModel)
                .where(ToolModel.organization_id == organization_id, ToolModel.folder_id.in_(ids))
                .values(folder_id=None)
            )
            await session.execute(
                ToolFolderModel.__table__.delete().where(
                    ToolFolderModel.organization_id == organization_id, ToolFolderModel.id.in_(ids)
                )
            )
            await session.commit()
            return {"dossiers": len(ids), "outils_sortis": sortis.rowcount or 0}

    async def ranger_un_outil(self, organization_id: int, tool_uuid: str, dossier_id: int | None) -> ToolModel:
        """Range un outil dans un dossier de la même organisation, ou l'en sort (``None``). Ne crée aucune version d'outil."""
        async with self.async_session() as session:
            outil = await session.scalar(
                select(ToolModel).where(ToolModel.tool_uuid == tool_uuid, ToolModel.organization_id == organization_id)
            )
            if outil is None:
                raise ErreurRangement("Tool not found")
            if dossier_id is not None:
                await self._dossier(session, organization_id, dossier_id)
            outil.folder_id = dossier_id
            await session.commit()
            await session.refresh(outil)
            return outil

    # ------------------------------------------------------------------ kits

    @staticmethod
    def _vue_kit(kit: ToolKitModel) -> dict[str, Any]:
        return {
            "id": kit.id,
            "name": kit.name,
            "description": kit.description,
            "items": [
                {
                    "id": i.id,
                    "name": i.name,
                    "description": i.description,
                    "category": i.category,
                    "icon": i.icon,
                    "icon_color": i.icon_color,
                    "definition": i.definition,
                    "version": i.version,
                }
                for i in sorted(kit.items, key=lambda i: (i.position, i.id))
            ],
        }

    async def lister_les_kits(self) -> list[dict[str, Any]]:
        async with self.async_session() as session:
            kits = (await session.scalars(select(ToolKitModel).options(selectinload(ToolKitModel.items)).order_by(ToolKitModel.name))).all()
            return [self._vue_kit(k) for k in kits]

    async def lire_un_kit(self, kit_id: int) -> dict[str, Any]:
        async with self.async_session() as session:
            kit = await session.scalar(select(ToolKitModel).options(selectinload(ToolKitModel.items)).where(ToolKitModel.id == kit_id))
            if kit is None:
                raise ErreurRangement("Kit not found")
            return self._vue_kit(kit)

    async def creer_un_kit(self, name: str, description: str | None = None) -> dict[str, Any]:
        async with self.async_session() as session:
            if await session.scalar(select(func.count()).select_from(ToolKitModel).where(ToolKitModel.name == name)):
                raise ErreurRangement(f"A kit named '{name}' already exists", "conflit")
            kit = ToolKitModel(name=name, description=description)
            session.add(kit)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ErreurRangement(f"A kit named '{name}' already exists", "conflit") from None
            return {"id": kit.id, "name": kit.name, "description": kit.description, "items": []}

    async def modifier_un_kit(self, kit_id: int, name: str | None = None, description: str | None = None) -> dict[str, Any]:
        async with self.async_session() as session:
            kit = await session.scalar(select(ToolKitModel).where(ToolKitModel.id == kit_id))
            if kit is None:
                raise ErreurRangement("Kit not found")
            if name is not None:
                if await session.scalar(
                    select(func.count()).select_from(ToolKitModel).where(ToolKitModel.name == name, ToolKitModel.id != kit_id)
                ):
                    raise ErreurRangement(f"A kit named '{name}' already exists", "conflit")
                kit.name = name
            if description is not None:
                kit.description = description
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ErreurRangement(f"A kit named '{name}' already exists", "conflit") from None
        return await self.lire_un_kit(kit_id)

    async def supprimer_un_kit(self, kit_id: int) -> None:
        """Supprime le kit : les outils déjà copiés dans des organisations restent (ils perdent seulement leur origine)."""
        async with self.async_session() as session:
            kit = await session.scalar(select(ToolKitModel).where(ToolKitModel.id == kit_id))
            if kit is None:
                raise ErreurRangement("Kit not found")
            await session.delete(kit)
            await session.commit()

    async def _item(self, session, kit_id: int, item_id: int) -> ToolKitItemModel:
        item = await session.scalar(select(ToolKitItemModel).where(ToolKitItemModel.id == item_id, ToolKitItemModel.kit_id == kit_id))
        if item is None:
            raise ErreurRangement("Kit tool not found")
        return item

    async def ajouter_un_outil_au_kit(
        self,
        kit_id: int,
        *,
        name: str,
        description: str | None,
        category: str,
        definition: dict[str, Any],
        icon: str | None = None,
        icon_color: str | None = None,
    ) -> dict[str, Any]:
        if category not in CATEGORIES_DE_KIT:
            raise ErreurRangement("A kit holds only tools without a client's address or identifier", "invalide")
        async with self.async_session() as session:
            kit = await session.scalar(select(ToolKitModel).where(ToolKitModel.id == kit_id))
            if kit is None:
                raise ErreurRangement("Kit not found")
            if await session.scalar(
                select(func.count()).select_from(ToolKitItemModel).where(ToolKitItemModel.kit_id == kit_id, ToolKitItemModel.name == name)
            ):
                raise ErreurRangement(f"The kit already holds a tool named '{name}'", "conflit")
            derniere = await session.scalar(select(func.max(ToolKitItemModel.position)).where(ToolKitItemModel.kit_id == kit_id))
            session.add(
                ToolKitItemModel(
                    kit_id=kit_id,
                    position=(derniere if derniere is not None else -1) + 1,
                    name=name,
                    description=description,
                    category=category,
                    icon=icon,
                    icon_color=icon_color,
                    definition=definition_sans_compte(definition),
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ErreurRangement(f"The kit already holds a tool named '{name}'", "conflit") from None
        return await self.lire_un_kit(kit_id)

    async def modifier_un_outil_du_kit(
        self,
        kit_id: int,
        item_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Un changement du contenu monte la version de l'outil du kit ; aucune organisation n'est touchée (elle reçoit une PROPOSITION)."""
        async with self.async_session() as session:
            item = await self._item(session, kit_id, item_id)
            avant = (item.name, item.description, item.definition)
            if name is not None:
                if name != item.name and await session.scalar(
                    select(func.count()).select_from(ToolKitItemModel).where(
                        ToolKitItemModel.kit_id == kit_id, ToolKitItemModel.name == name, ToolKitItemModel.id != item_id
                    )
                ):
                    raise ErreurRangement(f"The kit already holds a tool named '{name}'", "conflit")
                item.name = name
            if description is not None:
                item.description = description
            if definition is not None:
                item.definition = definition_sans_compte(definition)
            if (item.name, item.description, item.definition) != avant:
                item.version = (item.version or 1) + 1
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ErreurRangement(f"The kit already holds a tool named '{name}'", "conflit") from None
        return await self.lire_un_kit(kit_id)

    async def retirer_un_outil_du_kit(self, kit_id: int, item_id: int) -> dict[str, Any]:
        async with self.async_session() as session:
            item = await self._item(session, kit_id, item_id)
            await session.delete(item)
            await session.commit()
        return await self.lire_un_kit(kit_id)

    async def poser_un_kit_livre(self, name: str, description: str | None, items: list[dict[str, Any]]) -> dict[str, int]:
        """Pose un kit livré s'il manque, et ses outils qui manquent. Idempotent ; ne réécrit JAMAIS ce qu'une personne a changé."""
        async with self.async_session() as session:
            kit = await session.scalar(select(ToolKitModel).options(selectinload(ToolKitModel.items)).where(ToolKitModel.name == name))
            nouveau = kit is None
            if kit is None:
                kit = ToolKitModel(name=name, description=description)
                session.add(kit)
                await session.flush()
                presents: set[str] = set()
            else:
                presents = {i.name for i in kit.items}
            ajoutes = 0
            for rang, item in enumerate(items):
                if item["name"] in presents:
                    continue
                session.add(
                    ToolKitItemModel(
                        kit_id=kit.id,
                        position=rang,
                        name=item["name"],
                        description=item.get("description"),
                        category=item["category"],
                        icon=item.get("icon"),
                        icon_color=item.get("icon_color"),
                        definition=definition_sans_compte(item["definition"]),
                    )
                )
                ajoutes += 1
            await session.commit()
            return {"kit_cree": int(nouveau), "outils_ajoutes": ajoutes}

    # ------------------------------------------------------------------ l'organisation reçoit un kit

    async def appliquer_un_kit(self, organization_id: int, user_id: int, kit_id: int, dossier_id: int | None = None) -> dict[str, Any]:
        """Copie dans l'organisation les outils du kit qu'elle n'a pas encore. Idempotent. Aucun agent n'est touché."""
        async with self.async_session() as session:
            kit = await session.scalar(select(ToolKitModel).options(selectinload(ToolKitModel.items)).where(ToolKitModel.id == kit_id))
            if kit is None:
                raise ErreurRangement("Kit not found")
            if dossier_id is not None:
                await self._dossier(session, organization_id, dossier_id)
            deja = set(
                (
                    await session.scalars(
                        select(ToolModel.kit_item_id).where(
                            ToolModel.organization_id == organization_id,
                            ToolModel.kit_item_id.in_([i.id for i in kit.items] or [0]),
                            ToolModel.status != ToolStatus.ARCHIVED.value,
                        )
                    )
                ).all()
            )
            crees: list[str] = []
            for item in sorted(kit.items, key=lambda i: (i.position, i.id)):
                if item.id in deja:
                    continue
                outil = ToolModel(
                    organization_id=organization_id,
                    created_by=user_id,
                    name=item.name,
                    description=item.description,
                    category=item.category,
                    icon=item.icon,
                    icon_color=item.icon_color,
                    definition=definition_sans_compte(item.definition),
                    status=ToolStatus.ACTIVE.value,
                    folder_id=dossier_id,
                    kit_item_id=item.id,
                    kit_version=item.version,
                )
                session.add(outil)
                await session.flush()
                session.add(
                    ToolVersionModel(
                        organization_id=organization_id,
                        tool_id=outil.id,
                        version=1,
                        name=outil.name,
                        description=outil.description,
                        category=outil.category,
                        definition=outil.definition,
                        created_by=user_id,
                    )
                )
                crees.append(outil.tool_uuid)
            await session.commit()
            logger.info(f"Kit {kit_id} applied to organization {organization_id}: {len(crees)} tools created")
            return {"kit_id": kit_id, "crees": crees, "deja_presents": len(deja)}

    async def outils_recus_d_un_kit(self, organization_id: int, kit_id: int) -> list[dict[str, Any]]:
        """Les outils de l'organisation créés depuis ce kit (non archivés), avec la version reçue et celle que le kit porte maintenant."""
        async with self.async_session() as session:
            if await session.scalar(select(ToolKitModel.id).where(ToolKitModel.id == kit_id)) is None:
                raise ErreurRangement("Kit not found")
            lignes = (
                await session.execute(
                    select(ToolModel.tool_uuid, ToolModel.kit_version, ToolKitItemModel.version)
                    .join(ToolKitItemModel, ToolKitItemModel.id == ToolModel.kit_item_id)
                    .where(
                        ToolModel.organization_id == organization_id,
                        ToolKitItemModel.kit_id == kit_id,
                        ToolModel.status != ToolStatus.ARCHIVED.value,
                    )
                )
            ).all()
            return [{"tool_uuid": u, "version_recue": v or 1, "version_du_kit": k} for u, v, k in lignes]

    async def propositions_de_kit(self, organization_id: int) -> list[dict[str, Any]]:
        """Les outils de l'organisation dont le kit a une version plus récente que celle reçue."""
        async with self.async_session() as session:
            lignes = (
                await session.execute(
                    select(ToolModel, ToolKitItemModel, ToolKitModel)
                    .join(ToolKitItemModel, ToolKitItemModel.id == ToolModel.kit_item_id)
                    .join(ToolKitModel, ToolKitModel.id == ToolKitItemModel.kit_id)
                    .where(
                        ToolModel.organization_id == organization_id,
                        ToolModel.status != ToolStatus.ARCHIVED.value,
                        ToolModel.kit_version.is_not(None),
                        ToolKitItemModel.version > ToolModel.kit_version,
                    )
                    .order_by(ToolKitModel.name, ToolKitItemModel.position)
                )
            ).all()
            return [
                {
                    "tool_uuid": o.tool_uuid,
                    "tool_name": o.name,
                    "kit_id": k.id,
                    "kit_name": k.name,
                    "version_recue": o.kit_version,
                    "version_du_kit": i.version,
                }
                for o, i, k in lignes
            ]

    async def accepter_une_proposition_de_kit(self, organization_id: int, user_id: int, tool_uuid: str) -> dict[str, Any]:
        """L'organisation prend la version plus récente du kit : l'outil reçoit une NOUVELLE version d'outil. Les agents ne bougent pas
        d'eux-mêmes (ils restent sur la version figée par leur version publiée, ``Passer à la vN``)."""
        async with self.async_session() as session:
            outil = await session.scalar(
                select(ToolModel).where(ToolModel.tool_uuid == tool_uuid, ToolModel.organization_id == organization_id).with_for_update()
            )
            if outil is None or outil.kit_item_id is None:
                raise ErreurRangement("Tool not found")
            item = await session.scalar(select(ToolKitItemModel).where(ToolKitItemModel.id == outil.kit_item_id))
            if item is None or (outil.kit_version or 0) >= item.version:
                raise ErreurRangement("No newer version of the kit for this tool", "conflit")
            definition = _fusionner_la_definition(item.definition, outil.definition)
            if (outil.name, outil.description, outil.definition) != (item.name, item.description, definition):
                numero = (outil.version_courante or 1) + 1
                outil.version_courante = numero
                session.add(
                    ToolVersionModel(
                        organization_id=organization_id,
                        tool_id=outil.id,
                        version=numero,
                        name=item.name,
                        description=item.description,
                        category=outil.category,
                        definition=definition,
                        created_by=user_id,
                    )
                )
            outil.name = item.name
            outil.description = item.description
            outil.definition = definition
            outil.kit_version = item.version
            outil.updated_at = datetime.now(UTC)
            await session.commit()
            return {"tool_uuid": tool_uuid, "version_du_kit": item.version, "version_de_l_outil": outil.version_courante}
