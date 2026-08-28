"""LangGraph State Orchestrator Service — The Heart of CCRO.

Owns the Resilience State Machine (S1-S5) and coordinates all agents
via a supervisor-worker LangGraph topology.

Governing principle: AI Reasons. Rules Constrain. Policies Govern.
Humans Approve. SAP Executes.
"""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agents.orchestrator.checkpointer_config import CheckpointerConfig
from agents.orchestrator.graph_definition import (
    adapt_node,
    evaluate_transition,
    execute_node,
    govern_node,
    protect_node,
    sense_node,
    understand_node,
)
from agents.orchestrator.state_machine import ResilienceStateMachine
from schemas import ResilienceState
from schemas.graph_state import CCROGraphState

logger = structlog.get_logger(__name__)
app = FastAPI(title="CCRO LangGraph Orchestrator", version="0.1.0")

state_machine = ResilienceStateMachine()
checkpointer_config = CheckpointerConfig()


# ---------------------------------------------------------------------------
# LangGraph State Definition
# ---------------------------------------------------------------------------


class OrchestratorState(TypedDict):
    """LangGraph state type wrapping CCROGraphState."""

    ccro_state: CCROGraphState
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------


def route_after_sense(state: OrchestratorState) -> str:
    """Route after SENSE phase based on whether disruption was detected."""
    ccro = state["ccro_state"]
    if ccro.telemetry_buffer:
        return "understand"
    return "sense"  # keep sensing


def route_after_understand(state: OrchestratorState) -> str:
    """Route after UNDERSTAND phase based on capacity margin."""
    ccro = state["ccro_state"]
    new_state = evaluate_transition(ccro)

    if new_state == ResilienceState.S3_RECOVERY_CONSTRAINED:
        return "adapt"
    elif new_state == ResilienceState.S4_RECOVERY_INSUFFICIENT:
        return "protect"  # skip recovery, go straight to scarcity
    else:
        return "sense"  # stable or absorbing — keep monitoring


def route_after_adapt(state: OrchestratorState) -> str:
    """Route after ADAPT phase — check if scarcity allocation is needed."""
    ccro = state["ccro_state"]
    new_state = evaluate_transition(ccro)

    if new_state == ResilienceState.S4_RECOVERY_INSUFFICIENT:
        return "protect"
    elif new_state in (ResilienceState.S2_ABSORBING, ResilienceState.S1_STABLE):
        return "sense"  # recovery succeeded
    else:
        return "protect"  # still constrained, try scarcity


def route_after_protect(state: OrchestratorState) -> str:
    """Route after PROTECT phase — always go to governance."""
    return "govern"


def route_after_govern(state: OrchestratorState) -> str:
    """Route after GOVERN phase based on approval decision."""
    ccro = state["ccro_state"]
    if ccro.approval_record and ccro.approval_record.decision == "approved":
        return "execute"
    elif ccro.approval_record and ccro.approval_record.decision == "rejected":
        return "protect"  # back to scarcity engine for alternate plan
    else:
        return "govern"  # waiting for decision


def route_after_execute(state: OrchestratorState) -> str:
    """Route after EXECUTE phase — re-measure and transition."""
    ccro = state["ccro_state"]
    if ccro.writeback_status.value == "success":
        # Post-execution: re-measure capacity and potentially transition back
        new_state = evaluate_transition(ccro)
        if new_state in (ResilienceState.S1_STABLE, ResilienceState.S2_ABSORBING):
            return "sense"
    return "sense"  # default: re-enter sensing cycle


# ---------------------------------------------------------------------------
# Build the LangGraph
# ---------------------------------------------------------------------------


def build_orchestrator_graph() -> StateGraph:
    """Build and compile the CCRO orchestrator graph."""
    graph = StateGraph(OrchestratorState)

    # Add nodes (agent phases)
    graph.add_node("sense", sense_node)
    graph.add_node("understand", understand_node)
    graph.add_node("adapt", adapt_node)
    graph.add_node("protect", protect_node)
    graph.add_node("govern", govern_node)
    graph.add_node("execute", execute_node)

    # Entry point
    graph.set_entry_point("sense")

    # Edges with conditional routing
    graph.add_conditional_edges("sense", route_after_sense)
    graph.add_conditional_edges("understand", route_after_understand)
    graph.add_conditional_edges("adapt", route_after_adapt)
    graph.add_conditional_edges("protect", route_after_protect)
    graph.add_conditional_edges("govern", route_after_govern)
    graph.add_conditional_edges("execute", route_after_execute)

    return graph


# Compile the graph at module load time
_graph = build_orchestrator_graph()
_compiled_graph = _graph.compile()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.post("/ingest/sense")
async def ingest_sense_event(event: dict) -> dict:
    """Ingest a SenseEvent from the Sensing Agent."""
    from schemas import SenseEvent

    sense_event = SenseEvent(**event)

    # Initialize or update the graph state
    initial_state = OrchestratorState(
        ccro_state=CCROGraphState(telemetry_buffer=[sense_event]),
        messages=[],
    )

    # Run the graph
    result = await _compiled_graph.ainvoke(initial_state)

    ccro_result = result["ccro_state"]
    return {
        "resilience_state": ccro_result.resilience_state.value,
        "capacity_margin": ccro_result.capacity_margin,
        "thread_id": ccro_result.thread_id,
    }


@app.post("/approve")
async def submit_approval(decision: dict) -> dict:
    """Submit a human approval decision."""
    from schemas import ApprovalDecision

    approval = ApprovalDecision(**decision)

    # Update the graph state with the approval
    # In production, this would resume the graph from the checkpoint
    return {
        "status": "received",
        "plan_id": approval.plan_id,
        "decision": approval.decision,
    }


@app.get("/state/{thread_id}")
async def get_state(thread_id: str) -> dict:
    """Get the current state for a disruption episode."""
    # In production, this reads from the checkpoint store
    return {"thread_id": thread_id, "status": "not_found"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "graph_nodes": "6"}


# WebSocket for live state push to Governance UI
@app.websocket("/ws/state/{thread_id}")
async def websocket_state(websocket: WebSocket, thread_id: str) -> None:
    """WebSocket channel for live state updates to Governance UI."""
    await websocket.accept()
    try:
        while True:
            # In production, this pushes state changes via WebSocket
            # For now, just keep the connection alive
            data = await websocket.receive_text()
            await websocket.send_json({"status": "ok", "thread_id": thread_id})
    except WebSocketDisconnect:
        logger.info("orchestrator.ws_disconnected", thread_id=thread_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
