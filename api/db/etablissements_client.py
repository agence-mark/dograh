"""[.mark] The reads the establishments need (chantier l-agent-travaille, L1).

A module of its own rather than a method in Dograh's phone-number client: the
fewer upstream files a .mark feature touches, the fewer conflicts at the next
rise of the fork. Mixed into ``DBClient`` by one line.
"""


from sqlalchemy import select

from api.db.base_client import BaseDBClient
from api.db.models import TelephonyPhoneNumberModel, WorkflowModel


class EtablissementsClient(BaseDBClient):
    async def lister_numeros_de_lorganisation(
        self, organization_id: int
    ) -> list[tuple[str, str | None, int | None, str | None, bool]]:
        """Every Telephony number of ONE organization: (canonical address, label,
        inbound agent id, inbound agent name, active). Filtered by organization
        at the query level (tenant isolation)."""
        async with self.async_session() as session:
            result = await session.execute(
                select(
                    TelephonyPhoneNumberModel.address_normalized,
                    TelephonyPhoneNumberModel.label,
                    TelephonyPhoneNumberModel.inbound_workflow_id,
                    WorkflowModel.name,
                    TelephonyPhoneNumberModel.is_active,
                )
                .join(
                    WorkflowModel,
                    WorkflowModel.id == TelephonyPhoneNumberModel.inbound_workflow_id,
                    isouter=True,
                )
                .where(TelephonyPhoneNumberModel.organization_id == organization_id)
                .order_by(TelephonyPhoneNumberModel.created_at)
            )
            return [tuple(ligne) for ligne in result.all()]
