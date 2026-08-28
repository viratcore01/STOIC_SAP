# CCRO Platform — ColdChain Resilience Orchestrator

> **DHL Life Sciences & Healthcare — Cold Chain Resilience Platform**

A hybrid deterministic-agentic system for pharmaceutical cold-chain disruption response. CCRO compresses disruption assessment/recovery-planning cycles from 4–12 hours of manual coordination to under 5 minutes, while satisfying FDA/EMA cold-chain compliance requirements.

## Governing Architectural Principle

**AI Reasons. Rules Constrain. Policies Govern. Humans Approve. SAP Executes.**

## Architecture Overview

CCRO is built as a five-layer functional decomposition:

| Layer | Function | Implementation |
|-------|----------|---------------|
| **L1 — Ingestion** | Enterprise Data & Telemetry | Sensing Agent, BTP Event Mesh |
| **L2 — Deterministic Rules** | Feasibility & Constraint Engine | OR-Tools/SciPy Solver (upstream of AI) |
| **L3 — Intelligence & Policy** | Multi-Agent Reasoning & RAG | LangGraph/AutoGen agents + Policy Agent |
| **L4 — Governance** | Human-in-the-Loop | Fiori/React Approval Card + WebSocket |
| **L5 — ERP Execution** | SAP Writeback | SAP Integration Gateway (sole writer) |

### Four Sovereign Boundaries

1. **Enterprise Systems** (SAP Digital Core) — System of record. Never called directly by AI.
2. **AI Orchestration** (Agentic Runtime) — LangGraph/AutoGen on BTP Kyma.
3. **Solver & Knowledge** — Stateless, deterministic compute + RAG. No SAP writes.
4. **Human Governance** — Only boundary permitted to trigger SAP writes.

## Resilience State Machine (S1-S5)

```
S1 STABLE → S2 ABSORBING → S3 RECOVERY CONSTRAINED → S4 RECOVERY INSUFFICIENT → S5 SCARCITY ALLOCATION
                 ↑              ↕                         ↕                            ↕
              (resolved)    (capacity restored)       (alternate plan)           (back to S2/S3)
```

| State | Trigger | Response |
|-------|---------|----------|
| **S1** | Nominal operations | Continuous monitoring |
| **S2** | Disruption detected, capacity > demand | Scenario modeling, auto-rerouting |
| **S3** | Capacity margin < 15% | RAG policy pre-fetch, recovery evaluation |
| **S4** | Available capacity < total demand | Mandatory Scarcity Allocation Engine |
| **S5** | Human-approved allocation active | SAP TM dispatch execution |

## Project Structure

```
ccro-platform/
├── agents/                    # All LangGraph/AutoGen agent logic
│   ├── sensing_agent/         # Phase 1 — SENSE (IoT + weather ingestion)
│   ├── impact_agent/          # Phase 2 — UNDERSTAND (shelf-life projection)
│   ├── recovery_agents/       # Phase 3 — ADAPT (route/warehouse/fleet)
│   │   └── negotiation_graph.py  # AutoGen debate pattern
│   ├── scarcity_engine/       # Phase 4 — PROTECT (priority scoring + solver)
│   ├── policy_agent/          # Phase 5 — GOVERN (RAG retrieval + weight extraction)
│   ├── execution_agent/       # Phase 6 — EXECUTE (post-approval SAP write)
│   └── orchestrator/          # LangGraph State Orchestrator (S1-S5)
├── solver/                    # Deterministic optimization (NO SAP access)
│   ├── models/                # Constraint builder, objective builder
│   └── engines/               # OR-Tools MILP, SciPy relaxation
├── rag/                       # SOP corpus ingestion, vector store, weight validation
├── api/                       # API Gateway + WebSocket server
├── sap_connectors/            # SOLE authorized SAP write path
│   ├── odata_client/          # S/4HANA + SAP TM OData v4 clients
│   ├── idempotency/           # Redis-backed replay protection
│   └── destinations/          # BTP Destination Service config
├── schemas/                   # Canonical data contracts (shared type system)
├── governance_ui/             # React/Fiori frontend (Approval Card, Dashboard)
├── infra/                     # Kyma manifests, Event Mesh config, CI/CD
└── tests/                     # Unit, integration, solver determinism tests
```

## Key Design Decisions

### Deterministic Solver Bounding
LLM/RAG components may only influence **objective function weighting** — they can never relax, bypass, or override a hard physical constraint. Policy weights are bounded to [0,1] with w1+w2+w3=1 enforced by Pydantic validators.

### Three Hard Constraints (C1-C3)
- **C1 (Thermal Lifetime):** TransitTime(v,i) + HandlingBuffer < RemainingShelfLife(i)
- **C2 (Capacity):** Σ(PayloadMass × x_{i,v}) ≤ C_max(v)
- **C3 (Reachability):** Sites unreachable within shelf life are dropped before solver runs

### Immutable Audit Trail (21 CFR Part 11)
- Hash-chained records (SHA-256)
- Append-only storage (WORM / HANA Audit Log)
- Actor attribution from SAP-authenticated SAML/OAuth2 sessions
- Deterministic solver re-run capability via input snapshot hashes

### Module Boundary Enforcement
CI/CD enforces: `/solver` and `/rag` are **prohibited** from importing anything from `/sap_connectors` — structurally guaranteeing that deterministic and retrieval layers remain side-effect-free with respect to SAP.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/unit/ -v
pytest tests/solver_determinism/ -v

# Start services (each in separate terminal)
uvicorn agents.orchestrator.main:app --port 8000
uvicorn solver.main:app --port 8001
uvicorn agents.sensing_agent.main:app --port 8002
uvicorn agents.impact_agent.main:app --port 8003
uvicorn agents.scarcity_engine.main:app --port 8004
uvicorn agents.policy_agent.main:app --port 8005
uvicorn agents.execution_agent.main:app --port 8006
```

## SAP Integration

| SAP Product | Role | Data Flow |
|------------|------|-----------|
| **SAP TM** | Freight execution | Read orders → Write dispatch updates |
| **SAP S/4HANA** | Inventory & batch | Read expiry/demand → Write allocation flags |
| **SAP LBN** | Carrier collaboration | Read tracking signals |
| **SAP BTP** | Host platform | Kyma runtime, Event Mesh, Destinations |

All SAP writes flow through a single **SAP Integration Gateway** microservice enforcing idempotency, schema validation, and audit logging.

## License

Internal / Partner Engineering — DHL Life Sciences & Healthcare
