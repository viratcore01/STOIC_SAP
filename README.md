# CCRO Platform — ColdChain Resilience Orchestrator

> **DHL Life Sciences & Healthcare — Cold Chain Resilience Platform**

A hybrid deterministic-agentic system for pharmaceutical cold-chain disruption response. CCRO compresses disruption assessment/recovery-planning cycles from 4–12 hours of manual coordination to under 5 minutes, while satisfying FDA/EMA cold-chain compliance requirements.

## Governing Architectural Principle

**AI Reasons. Rules Constrain. Policies Govern. Humans Approve. SAP Executes.**

## Live Demo

**[https://stoic-23qcxc7tg-viratcore01s-projects.vercel.app/](https://stoic-23qcxc7tg-viratcore01s-projects.vercel.app/)**

- React 19 SPA (Vite) + FastAPI backend deployed on Vercel
- Real OR-Tools CP-SAT solver with deterministic audit hashes
- LangGraph orchestrator pipeline with S1–S5 state machine
- Immutable audit chain with tamper detection
- Swagger API docs at `/docs`

## Architecture Overview

CCRO is built as a five-layer functional decomposition:

| Layer | Function | Implementation |
|-------|----------|----------------|
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

## Resilience State Machine (S1–S5)

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

### State Machine Integration (Round 2)

The demo backend now uses `ResilienceStateMachine` to evaluate state transitions from live metrics instead of hardcoding states. Each transition is logged to the immutable audit chain with timestamps and trigger information.

## Agents

### Disruption Sensing Agent (`agents/sensing_agent/`)
- IoT telemetry ingestion via MQTT bridge
- Weather/port disruption webhook processing
- Carrier tracking signal normalization
- Three input formats: MQTT JSON, weather webhooks, LBN carrier tracking

### Impact & Scenario Agent (`agents/impact_agent/`)
- Shelf-life projection from batch expiry data
- Thermal decay modeling
- Per-site demand impact assessment

### Recovery Agent Cluster (`agents/recovery_agents/`)
- AutoGen-style multi-agent negotiation (route, warehouse, fleet sub-agents)
- Competing recovery proposals ranked by feasibility × impact
- Speculative RAG pre-fetch during S3 (latency hiding)

### Scarcity Allocation Engine (`agents/scarcity_engine/`)
- Priority scoring: P_i = w1 × SR_i + w2 × OS_i + w3 × VPI_i
- OR-Tools CP-SAT solver with deterministic seed (reproducible audit)
- Three hard constraints: thermal lifetime, vehicle capacity, reachability
- SciPy LP relaxation pre-check (rapid feasibility filtering)

### Policy Agent (`agents/policy_agent/`)
- ChromaDB vector store for SOP clause retrieval (cosine similarity)
- LLM structured output for policy weight extraction
- Pydantic validation: w1 + w2 + w3 = 1.0, each in [0, 1]
- Speculative prefetch during S3, cached with TTL validation

### Compliance Agent (`agents/compliance_agent/`) — NEW
- **Sanctions compliance**: Blocks allocations to sanctioned regions (RU, IR, KP, SY, CU, BY) and entities
- **Cold chain temperature**: Validates pharmaceutical shipments stay within 2–8°C range
- **Allocation limits**: Prevents over-allocation (max 500 units/site)
- **Dropped site risk**: Flags high-priority sites that couldn't be allocated
- **Vehicle compatibility**: Checks cold-chain vehicle assignments
- Runs as mandatory pre-writeback check before SAP TM execution

### Execution Agent (`agents/execution_agent/`)
- Two-phase SAP writeback (TM first, then S/4HANA)
- Idempotency keys on all writes (SHA-256 deterministic)
- Optimistic concurrency via If-Match ETags
- Compliance agent gate: blocks writeback if violations found

## Solver Pipeline

```
Shelf-Life Projections → Constraint Builder (C1/C2/C3) → Pre-filter infeasible pairs
                          ↓
Policy Weights (w1,w2,w3) → Objective Builder (P_i scores) → SciPy LP relaxation check
                          ↓
Feasible Variables + Priority Scores → OR-Tools CP-SAT → AllocationPlan
```

### Three Hard Constraints (C1–C3)

- **C1 (Thermal Lifetime):** TransitTime(v,i) + HandlingBuffer < RemainingShelfLife(i)
- **C2 (Capacity):** Σ(PayloadMass × x_{i,v}) ≤ C_max(v)
- **C3 (Reachability):** Sites unreachable within shelf life are dropped before solver runs

## Demo API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | React SPA (or API landing page) |
| `/health` | GET | Health check |
| `/api/state` | GET | Full system state with orchestrator pipeline info |
| `/api/disruptions` | GET | Available disruption scenarios |
| `/api/disruption/trigger` | POST | Trigger disruption, run orchestrator pipeline |
| `/api/allocation/run` | POST | Run solver with compliance check |
| `/api/allocation/what-if` | POST | Compare solver across varying policy weights |
| `/api/allocation/proposed` | GET | Get current proposed allocation |
| `/api/compliance/check` | POST | Run compliance agent on current allocation |
| `/api/allocation/approve` | POST | Approve allocation (compliance gate + SAP writeback) |
| `/api/allocation/reject` | POST | Reject allocation |
| `/api/allocation/modify` | POST | Modify allocation with C1 validation |
| `/api/audit/log` | GET | Immutable audit chain (hash-chained, tamper-proof) |
| `/api/allocation/history` | GET | Allocation execution history |
| `/api/settings` | GET | System configuration |
| `/api/reset` | POST | Reset demo to initial state |
| `/docs` | GET | Swagger API documentation |

## What-If Simulation

Compare solver output across multiple policy weight scenarios:

```bash
curl -X POST https://your-vercel-url/api/allocation/what-if \
  -H "Content-Type: application/json" \
  -d '[
    {"w1": 0.7, "w2": 0.2, "w3": 0.1, "label": "Clinical Focus"},
    {"w1": 0.3, "w2": 0.4, "w3": 0.3, "label": "Balanced"},
    {"w1": 0.1, "w2": 0.2, "w3": 0.7, "label": "Value Focus"}
  ]'
```

Returns comparative results with objective values, units dispatched, avoided loss, and the best scenario highlighted.

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
│   ├── compliance_agent/      # Pre-writeback compliance checking
│   ├── execution_agent/       # Phase 6 — EXECUTE (post-approval SAP write)
│   └── orchestrator/          # LangGraph State Orchestrator (S1–S5)
├── solver/                    # Deterministic optimization (NO SAP access)
│   ├── models/                # Constraint builder, objective builder
│   └── engines/               # OR-Tools MILP, SciPy relaxation
├── rag/                       # SOP corpus ingestion, vector store, weight validation
├── api/                       # Vercel serverless function entrypoint
├── sap_connectors/            # SOLE authorized SAP write path
│   ├── odata_client/          # S/4HANA + SAP TM OData v4 clients
│   ├── idempotency/           # Redis-backed replay protection
│   └── destinations/          # BTP Destination Service config
├── schemas/                   # Canonical data contracts (shared type system)
├── demo/                      # Self-contained demo backend + React frontend
│   ├── backend/main.py        # FastAPI app with mock data + real solver
│   └── frontend/              # React 19 + Vite SPA
├── governance_ui/             # React/Fiori frontend (Approval Card, Dashboard)
├── infra/                     # Kyma manifests, Event Mesh config, CI/CD
└── tests/                     # Unit, integration, solver determinism tests
```

## Key Design Decisions

### Deterministic Solver Bounding
LLM/RAG components may only influence **objective function weighting** — they can never relax, bypass, or override a hard physical constraint. Policy weights are bounded to [0,1] with w1+w2+w3=1 enforced by Pydantic validators.

### Immutable Audit Trail (21 CFR Part 11)
- Hash-chained records (SHA-256)
- Append-only storage (WORM / HANA Audit Log)
- Actor attribution from SAP-authenticated SAML/OAuth2 sessions
- Deterministic solver re-run capability via input snapshot hashes

### Compliance Agent Gate
Every SAP writeback passes through the Compliance Agent, which checks sanctions, cold chain temperature, allocation limits, and vehicle compatibility. If any blocking violation is found, the writeback is refused and the audit chain records the compliance failure.

### Module Boundary Enforcement
CI/CD enforces: `/solver` and `/rag` are **prohibited** from importing anything from `/sap_connectors` — structurally guaranteeing that deterministic and retrieval layers remain side-effect-free with respect to SAP.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"
pip install chromadb  # Required for RAG vector store

# Run tests
pytest tests/ -v

# Run full pipeline dry-run
python dry_run.py

# Start demo backend
uvicorn demo.backend.main:app --reload --port 8000

# Or deploy to Vercel
vercel deploy
```

## Deployment (Vercel)

The demo is deployed as a Python serverless function on Vercel:

- **Entrypoint**: `api/index.py` re-exports the FastAPI app
- **Dependencies**: `requirements.txt` (fastapi, pydantic, structlog, ortools, numpy)
- **Build**: `@vercel/python` runtime with `pip install -r requirements.txt`
- **Frontend**: Pre-built React SPA served from `demo/frontend/dist/`

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
