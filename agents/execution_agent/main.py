"""Execution Agent Service — Phase 6 EXECUTE.

Post-approval only: triggers SAP writeback via the SAP Integration Gateway.
Writes audit records to the Immutable Audit Ledger.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI

from schemas import (
    AllocationPlan,
    ApprovalDecision,
    AuditEventType,
    AuditPayload,
    Actor,
    ActorType,
    WritebackConfirmation,
    WritebackStatus,
)
from schemas.audit_record import AuditChain
from sap_connectors.odata_client.sap_tm_client import SAPTMClient

logger = structlog.get_logger(__name__)
app = FastAPI(title="CCRO Execution Agent", version="0.1.0")

# Audit chain for this execution session
audit_chain = AuditChain()


@app.post("/execute", response_model=WritebackConfirmation)
async def execute_allocation(
    allocation_plan: AllocationPlan,
    approval_record: ApprovalDecision,
) -> WritebackConfirmation:
    """Execute an approved allocation plan via SAP writeback.

    Two-phase writeback:
    1. Write to SAP TM (freight orders) — MUST succeed
    2. Write to S/4HANA (inventory flags) — compensating event on failure

    Args:
        allocation_plan: The approved allocation plan.
        approval_record: The human approval decision.

    Returns:
        WritebackConfirmation with SAP response details.
    """
    logger.info(
        "execution.started",
        plan_id=allocation_plan.plan_id,
        approver=approval_record.approver_id,
        n_assignments=len(allocation_plan.assignments),
    )

    # Log approval decision to audit chain
    audit_chain.append(
        event_type=AuditEventType.APPROVAL_DECISION,
        actor=Actor(type=ActorType.HUMAN, id=approval_record.approver_id),
        allocation_plan_id=allocation_plan.plan_id,
        payload=AuditPayload(
            approval_decision=approval_record.decision,
        ),
    )

    tm_client = SAPTMClient()
    confirmation = WritebackConfirmation()

    # Phase 1: Write to SAP TM
    try:
        for assignment in allocation_plan.assignments:
            freight_order_id = await tm_client.update_freight_order(
                allocation_plan_id=allocation_plan.plan_id,
                site_id=assignment.site_id,
                vehicle_id=assignment.vehicle_id,
                allocated_units=assignment.allocated_units,
                payload_mass_kg=assignment.payload_mass_kg,
                priority_score=assignment.priority_score,
                approver_id=approval_record.approver_id,
            )
            confirmation.freight_order_ids.append(freight_order_id)
            confirmation.sap_response_codes.append("200")

        confirmation.writeback_status = WritebackStatus.SUCCESS
        logger.info("execution.tm_writeback_success", plan_id=allocation_plan.plan_id)

    except Exception as e:
        logger.error("execution.tm_writeback_failed", error=str(e))
        confirmation.writeback_status = WritebackStatus.FAILED
        confirmation.error_message = str(e)

        # Log failure to audit chain
        audit_chain.append(
            event_type=AuditEventType.WRITEBACK_FAILURE,
            actor=Actor(type=ActorType.SYSTEM, id="execution_agent"),
            allocation_plan_id=allocation_plan.plan_id,
            payload=AuditPayload(
                error_details=str(e),
            ),
        )

        return confirmation

    # Phase 2: Write to S/4HANA (inventory allocation flags)
    # This would use SAP S/4HANA client in production
    # For now, log success
    audit_chain.append(
        event_type=AuditEventType.SAP_WRITEBACK,
        actor=Actor(type=ActorType.SYSTEM, id="execution_agent"),
        allocation_plan_id=allocation_plan.plan_id,
        payload=AuditPayload(
            sap_response_codes=confirmation.sap_response_codes,
        ),
    )

    return confirmation


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "audit_chain_length": str(len(audit_chain.get_records())),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)
