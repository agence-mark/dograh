from typing import List, Optional

from sqlalchemy import and_
from sqlalchemy.future import select

from api.db.base_client import BaseDBClient
from api.db.models import APIKeyModel
from api.utils.api_key import generate_api_key, hash_api_key


class APIKeyClient(BaseDBClient):
    async def create_api_key(
        self,
        organization_id: int,
        name: str,
        created_by: Optional[int] = None,
        role_id: Optional[int] = None,
    ) -> tuple[APIKeyModel, str]:
        """Create a new API key for an organization.

        Returns:
            Tuple of (APIKeyModel, raw_api_key)
        """
        # Generate a secure random API key
        raw_api_key, key_hash, key_prefix = generate_api_key()

        async with self.async_session() as session:
            api_key = APIKeyModel(
                organization_id=organization_id,
                name=name,
                key_hash=key_hash,
                key_prefix=key_prefix,
                created_by=created_by,
                is_active=True,
                role_id=role_id,
            )
            session.add(api_key)
            await session.commit()
            await session.refresh(api_key)

            return api_key, raw_api_key

    async def get_api_keys_by_organization(
        self, organization_id: int, include_archived: bool = False
    ) -> List[APIKeyModel]:
        """Get all API keys for an organization."""
        async with self.async_session() as session:
            query = select(APIKeyModel).where(
                APIKeyModel.organization_id == organization_id
            )

            if not include_archived:
                query = query.where(APIKeyModel.archived_at.is_(None))

            result = await session.execute(query)
            return result.scalars().all()

    async def get_api_key_by_hash(self, key_hash: str) -> Optional[APIKeyModel]:
        """Get an API key by its hash."""
        async with self.async_session() as session:
            result = await session.execute(
                select(APIKeyModel).where(
                    and_(
                        APIKeyModel.key_hash == key_hash,
                        APIKeyModel.is_active == True,
                        APIKeyModel.archived_at.is_(None),
                    )
                )
            )
            return result.scalars().first()

    async def validate_api_key(self, raw_api_key: str) -> Optional[APIKeyModel]:
        """Validate an API key and return the associated model if valid."""
        key_hash = hash_api_key(raw_api_key)
        api_key = await self.get_api_key_by_hash(key_hash)

        if api_key:
            # Update last_used_at
            from datetime import datetime, timezone

            async with self.async_session() as session:
                await session.execute(
                    APIKeyModel.__table__.update()
                    .where(APIKeyModel.id == api_key.id)
                    .values(last_used_at=datetime.now(timezone.utc))
                )
                await session.commit()

        return api_key

    async def archive_api_key(self, api_key_id: int) -> bool:
        """Archive an API key (soft delete)."""
        from datetime import datetime, timezone

        async with self.async_session() as session:
            result = await session.execute(
                APIKeyModel.__table__.update()
                .where(APIKeyModel.id == api_key_id)
                .values(is_active=False, archived_at=datetime.now(timezone.utc))
            )
            await session.commit()
            return result.rowcount > 0

    async def reactivate_api_key(self, api_key_id: int) -> bool:
        """Reactivate an archived API key."""
        async with self.async_session() as session:
            result = await session.execute(
                APIKeyModel.__table__.update()
                .where(APIKeyModel.id == api_key_id)
                .values(is_active=True, archived_at=None)
            )
            await session.commit()
            return result.rowcount > 0

    async def get_api_key_by_id(
        self, organization_id: int, api_key_id: int
    ) -> Optional[APIKeyModel]:
        """[.mark] Une clé de CETTE organisation (le filtre est dans la requête), active ou non."""
        async with self.async_session() as session:
            result = await session.execute(
                select(APIKeyModel).where(
                    APIKeyModel.id == api_key_id,
                    APIKeyModel.organization_id == organization_id,
                )
            )
            return result.scalars().first()

    async def set_api_key_role(
        self, organization_id: int, api_key_id: int, role_id: Optional[int]
    ) -> bool:
        """[.mark] Clôture, lot A (D21) : change le rôle que la clé porte (le filtre par organisation est dans la requête)."""
        async with self.async_session() as session:
            result = await session.execute(
                APIKeyModel.__table__.update()
                .where(
                    APIKeyModel.id == api_key_id,
                    APIKeyModel.organization_id == organization_id,
                )
                .values(role_id=role_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def set_api_key_active(
        self, organization_id: int, api_key_id: int, active: bool
    ) -> bool:
        """[.mark] Suspend (``False``) ou rétablit (``True``) une clé non révoquée ; une clé révoquée (archivée) ne se rétablit pas ici."""
        async with self.async_session() as session:
            result = await session.execute(
                APIKeyModel.__table__.update()
                .where(
                    APIKeyModel.id == api_key_id,
                    APIKeyModel.organization_id == organization_id,
                    APIKeyModel.archived_at.is_(None),
                )
                .values(is_active=active)
            )
            await session.commit()
            return result.rowcount > 0

    async def set_api_key_mcp_gestes(
        self,
        organization_id: int,
        api_key_id: int,
        *,
        publier: Optional[bool] = None,
        tests_payants: Optional[bool] = None,
        appels_reels: Optional[bool] = None,
    ) -> bool:
        """[.mark] Allume ou éteint les interrupteurs MCP d'une clé de CETTE organisation (``None`` : inchangé) ; faux si la clé n'existe pas ici."""
        valeurs = {
            colonne: valeur
            for colonne, valeur in (("mcp_publier", publier), ("mcp_tests_payants", tests_payants), ("mcp_appels_reels", appels_reels))
            if valeur is not None
        }
        if not valeurs:
            return await self.get_api_key_by_id(organization_id, api_key_id) is not None
        async with self.async_session() as session:
            result = await session.execute(
                APIKeyModel.__table__.update()
                .where(
                    APIKeyModel.id == api_key_id,
                    APIKeyModel.organization_id == organization_id,
                    APIKeyModel.archived_at.is_(None),
                )
                .values(**valeurs)
            )
            await session.commit()
            return result.rowcount > 0

    async def count_api_keys_with_role(self, role_id: int) -> int:
        """[.mark] Combien de clés (révoquées exclues) portent ce rôle : un rôle utilisé par une clé ne se supprime pas."""
        from sqlalchemy import func

        async with self.async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(APIKeyModel)
                .where(APIKeyModel.role_id == role_id, APIKeyModel.archived_at.is_(None))
            )
            return int(result.scalar_one())
