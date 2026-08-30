# CCRO Platform — ColdChain Resilience Orchestrator

> **DHL Life Sciences & Healthcare — Cold Chain Resilience Platform**
> **SAP HackFest 2026 — Enterprise Architecture Specification**

A hybrid deterministic-agentic system for pharmaceutical cold-chain disruption response. CCRO compresses disruption assessment/recovery-planning cycles from 4–12 hours of manual coordination to under 5 minutes, while satisfying FDA/EMA cold-chain compliance requirements.

## Governing Architectural Principle

**AI Reasons. Rules Constrain. Policies Govern. Humans Approve. SAP Executes.**

## Live Demo

**[https://stoic-23qcxc7tg-viratcore01s-projects.vercel.app/](https://stoic-23qcxc7tg-viratcore01s-projects.vercel.app/)**

- React 19 SPA (Vite) + FastAPI backend deployed on Vercel
- Real OR-Tools CP-SAT solver with deterministic audit hashes
- LangGraph orchestrator pipeline with S1–S5 state machine
- 3D Geospatial Map Control Center with interactive route arcs
- Immutable audit chain with SHA-256 tamper detection
- Swagger API docs at `/docs`

---

## Architecture Overview

CCRO is built as a five-layer functional decomposition:

| Layer | Function | Implementation |
|-------|----------|----------------|
| **L1 — Ingestion** | Enterprise Data & Telemetry | Sensing Agent, BTP Event Mesh, SAP Mock Server |
| **L2 — Deterministic Rules** | Feasibility & Constraint Engine | OR-Tools/SciPy Solver + Geodesic Router (upstream of AI) |
| **L3 — Intelligence & Policy** | Multi-Agent Reasoning & RAG | LangGraph/AutoGen agents + Policy Agent + SOP Corpus |
| **L4 — Governance** | Human-in-the-Loop | React Approval Card + Compliance Agent + WebSocket |
| **L5 — ERP Execution** | SAP Writeback | SAP Integration Gateway (sole writer) + Mock TM Server |

### Four Sovereign Boundaries

1. **Enterprise Systems** (SAP Digital Core) — System of record. Never called directly by AI.
2. **AI Orchestration** (Agentic Runtime) — LangGraph/AutoGen on BTP Kyma.
3. **Solver & Knowledge** — Stateless, deterministic compute + RAG. No SAP writes.
4. **Human Governance** — Only boundary permitted to trigger SAP writes.

---

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

### State Machine Integration

The demo backend uses `ResilienceStateMachine` to evaluate state transitions from live metrics instead of hardcoding states. Each transition is logged to the immutable audit chain with timestamps and trigger information.

---

## Multi-Agent System

### 1. SENSE — Disruption Sensing Agent (`agents/sensing_agent/`)

- IoT telemetry ingestion via MQTT bridge (`EventMeshConsumer`)
- Weather/port disruption webhook processing
- Carrier tracking signal normalization (LBN)
- Three input formats: MQTT JSON, weather webhooks, LBN carrier tracking
- `TelemetryNormalizer` maps raw data to canonical `SenseEvent` schema

### 2. UNDERSTAND — Impact & Scenario Agent (`agents/impact_agent/`)

- **Arrhenius Thermal Decay Engine** (`shelf_life_model/thermal_decay.py`):
  - `k = A * exp(-Ea / (R * T))` kinetic formula
  - Computes remaining shelf life from temperature log arrays
  - Configurable activation energy (default 80 kJ/mol for biologics)
  - Wired into Constraint C1 (thermal lifetime) of OR-Tools solver
- Shelf-life projection from batch expiry data
- Per-site demand impact assessment

### 3. ADAPT — Recovery Agent Cluster (`agents/recovery_agents/`)

- **AutoGen-style multi-agent negotiation** (`negotiation_graph.py`):
  - Route Realign Sub-Agent
  - Warehouse Rebalancing Sub-Agent
  - Fleet Expansion Sub-Agent
  - Competing proposals ranked by feasibility × impact
- **Geodesic Recovery Router** (`geodesic_router.py`):
  - Haversine great-circle distance calculation
  - Real European coordinates for 4 warehouse hubs + 8 clinic sites
  - True transit times with cold-chain speed factor (0.85×)
  - C1 feasibility check: `transit_time + buffer < remaining_shelf_life`
  - Full (vehicle, site) pair evaluation with infeasible pair flagging
  - Route distance matrix computation

### 4. PROTECT — Scarcity Allocation Engine (`agents/scarcity_engine/`)

- Priority scoring: `P_i = w1 × SR_i + w2 × OS_i + w3 × VPI_i`
- OR-Tools CP-SAT solver with deterministic seed (reproducible audit)
- Three hard constraints: thermal lifetime, vehicle capacity, reachability
- SciPy LP relaxation pre-check (rapid feasibility filtering)
- Input snapshot hashing for audit reproducibility

### 5. GOVERN — Policy Agent (`agents/policy_agent/`)

- **ChromaDB vector store** for SOP clause retrieval (cosine similarity)
- **LLM structured output** for policy weight extraction
- **Pydantic validation**: `w1 + w2 + w3 = 1.0`, each in `[0, 1]`
- **Speculative prefetch** during S3, cached with TTL validation
- **Local SOP Corpus** (`data/sops/`):
  - `WHO_Cold_Chain_Guidelines.md` — WHO cold chain management
  - `DHL_Emergency_Allocation_SOP.md` — DHL emergency allocation
  - `EU_GDP_Temp_Control.md` — EU GDP temperature control
- **Ingestion Script** (`scripts/ingest_sops.py`):
  - Markdown chunking with section/list-aware boundaries
  - ChromaDB ingestion for policy_agent RAG retrieval
  - Run: `python scripts/ingest_sops.py`

### 6. Compliance Agent (`agents/compliance_agent/`) — Pre-Writeback Gate

| Rule | Type | Effect |
|------|------|--------|
| **SANCTION-001/002** | Blocking | Blocks allocations to sanctioned regions (RU, IR, KP, SY, CU, BY) |
| **COLD-001/002/003** | Blocking/Warning | Validates pharmaceutical cold chain (2–8°C range) |
| **LIMIT-001/002** | Blocking/Warning | Prevents over-allocation (max 500 units/site) |
| **RISK-001** | Warning | Flags high-priority sites that were dropped |
| **VEHICLE-001** | Warning | Checks cold-chain vehicle assignments |

Runs as mandatory pre-writeback check before SAP TM execution.

### 7. EXECUTE — Execution Agent (`agents/execution_agent/`)

- Two-phase SAP writeback (TM first, then S/4HANA)
- Idempotency keys on all writes (SHA-256 deterministic)
- Optimistic concurrency via If-Match ETags
- Compliance agent gate: blocks writeback if violations found
- Audit chain logging for every write operation

### 8. ORCHESTRATOR — LangGraph State Orchestrator (`agents/orchestrator/`)

- 6-node graph: sense → understand → adapt → protect → govern → execute
- Conditional routing based on state machine evaluation
- Redis-backed checkpointer for pause/resume across human-approval boundary
- `CCROGraphState` shared state object (Pydantic) passed between all nodes

---

## Solver Pipeline

```
Shelf-Life Projections → Constraint Builder (C1/C2/C3) → Pre-filter infeasible pairs
                          ↓
Policy Weights (w1,w2,w3) → Objective Builder (P_i scores) → SciPy LP relaxation check
                          ↓
Feasible Variables + Priority Scores → OR-Tools CP-SAT → AllocationPlan
```

### Three Hard Constraints (C1–C3)

- **C1 (Thermal Lifetime):** `TransitTime(v,i) + HandlingBuffer < RemainingShelfLife(i)`
- **C2 (Capacity):** `Σ(PayloadMass × x_{i,v}) ≤ C_max(v)`
- **C3 (Reachability):** Sites unreachable within shelf life are dropped before solver runs

These constraints are **absolute** — they cannot be relaxed, bypassed, or overridden by AI or human operators.

---

## SAP Mock Server (`sap_mock_server/`)

Standalone FastAPI service emulating SAP TM OData v4:

- **GET** `/sap/opu/odata4/sap/api_freightorder/FreightOrder` — list/query freight orders
- **GET** `/sap/opu/odata4/sap/api_freightorder/FreightOrder('{id}')` — read single order
- **PATCH** `/sap/opu/odata4/sap/api_freightorder/FreightOrder('{id}')` — update with ETag validation
- **Idempotency ledger** — cache responses, return previous on duplicate `Idempotency-Key`
- **ETag validation** — HTTP 412 Precondition Failed on `If-Match` mismatch
- **8 seed freight orders** matching demo clinic/vehicle data

Start: `uvicorn sap_mock_server.main:app --port 8080`

---

## 3D Geospatial Map Control Center

### Backend: `GET /api/map/topology`

Returns GeoJSON-style features:

| Feature | Details |
|---------|---------|
| **Warehouse Hubs** | Frankfurt (50.11°N, 8.68°E), Nairobi (-1.29°S, 36.82°E) |
| **8 Clinics** | Real coordinates, Pi scores, stock coverage %, allocation status |
| **32 Route Arcs** | Arrhenius decay rates, ambient temps, transit times, feasibility flags |
| **3 Maritime Routes** | Eurostat searoute paths: Rotterdam-Mombasa, Frankfurt-Nairobi, Rotterdam-Shanghai |
| **909 Harbours** | VISIR-2 port database for nearest-port lookup and multi-modal routing |
| **Disruption Markers** | Red Sea maritime breach + active disruption with pulsing beacons |
| **Dropped Sites** | `is_dropped: true` with C1/C2 violation reasons |
| **Audit Hash** | SHA-256 chain tip + validity status |

### Frontend: `ResilienceGlobeView.tsx`

- CSS 3D perspective map with SVG arc overlays
- **Route arcs**: Green (nominal 2–8°C), Yellow (thermal warning), Red (C1 breach)
- **Animated dots** moving along route arcs showing vehicle transit
- **Pulsing disruption beacons** with severity labels
- **Hover tooltips**: Vehicle ID, ambient temp, Arrhenius decay rate k, remaining hours
- **Click clinic**: Pi score, stock coverage %, allocation status, drop reason
- **Live Governance Overlay**: SHA-256 audit hash, chain validity, "Approve & Write Back to SAP" button
- **Right panel**: Network stats, route status summary, capacity margin

---

## Demo API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | React SPA (or API landing page) |
| `/health` | GET | Health check |
| `/api/state` | GET | Full system state with orchestrator pipeline info |
| `/api/map/topology` | GET | GeoJSON topology for 3D map (includes maritime data, 909 harbours) |
| `/api/routes/maritime` | GET | Maritime route computation with searoute (passage avoidance, K-alternatives) |
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

---

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

---

## Project Structure

```
ccro-platform/
├── agents/                         # All LangGraph/AutoGen agent logic
│   ├── sensing_agent/              # SENSE — IoT + weather ingestion
│   │   ├── ingestion/              #   Event Mesh consumer, MQTT parsing
│   │   └── normalizers/            #   Telemetry normalizer (3 formats)
│   ├── impact_agent/               # UNDERSTAND — shelf-life projection
│   │   └── shelf_life_model/       #   Arrhenius thermal decay engine
│   ├── recovery_agents/            # ADAPT — route/warehouse/fleet
│   │   ├── negotiation_graph.py    #   AutoGen debate pattern
│   │   ├── geodesic_router.py      #   Haversine distance + C1 feasibility
│   │   ├── maritime_router.py      #   Eurostat searoute + VISIR-2 integration
│   │   ├── route_subagent/         #   Route re-alignment
│   │   ├── warehouse_subagent/     #   Warehouse rebalancing
│   │   └── fleet_subagent/         #   Fleet expansion
│   ├── scarcity_engine/            # PROTECT — priority scoring + solver
│   ├── policy_agent/               # GOVERN — RAG retrieval + weight extraction
│   ├── compliance_agent/           # Pre-writeback compliance (5 rules)
│   ├── execution_agent/            # EXECUTE — post-approval SAP write
│   └── orchestrator/               # LangGraph State Orchestrator (S1–S5)
├── solver/                         # Deterministic optimization (NO SAP access)
│   ├── models/                     #   Constraint builder, objective builder
│   └── engines/                    #   OR-Tools MILP, SciPy relaxation
├── rag/                            # SOP corpus, vector store, weight validation
│   ├── vectorstore/                #   ChromaDB client
│   └── schemas/                    #   PolicyWeightsExtraction Pydantic
├── scripts/                        # Data ingestion utilities
│   └── ingest_sops.py              #   SOP markdown → ChromaDB ingestion
├── data/
│   ├── sops/                       # Local SOP corpus (3 documents)
│   └── vi/                         # VISIR-2 GMD 2023 dataset
│       ├── __data/harbours/        #   909-world port database (harbours_DB.csv)
│       ├── _d_Tracce/              #   Yen's K-Shortest Paths, Dijkstra algorithms
│       ├── _c_Pesi/                #   Edge weight computation, velocity models
│       └── Navi/                   #   Vessel performance models (B-spline, NN)
├── sap_mock_server/                # SAP TM OData v4 emulator (port 8080)
├── api/                            # Vercel serverless function entrypoint
├── sap_connectors/                 # SOLE authorized SAP write path
│   ├── odata_client/               #   S/4HANA + SAP TM OData v4 clients
│   ├── idempotency/                #   Redis-backed replay protection
│   └── destinations/               #   BTP Destination Service config
├── schemas/                        # Canonical data contracts (shared type system)
├── demo/                           # Self-contained demo backend + React frontend
│   ├── backend/main.py             #   FastAPI app (23 endpoints + map topology)
│   └── frontend/                   #   React 19 + Vite SPA (6 pages)
│       └── src/pages/              #     Dashboard, Control Center, Approvals,
│                                   #     Allocations, Audit Log, Settings
├── governance_ui/                  # React/Fiori frontend (Approval Card)
├── infra/                          # Kyma manifests, Event Mesh config, CI/CD
└── tests/                          # 45 unit + integration tests
```

---

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

### Geodesic Routing
The Recovery Agent uses Haversine great-circle distances with real European coordinates instead of placeholder heuristics. Routes are pre-filtered by C1 (thermal lifetime) before the solver runs, reducing problem dimensionality.

### Maritime Route Engine (Eurostat SeaRoute + VISIR-2 Integration)
The system integrates **Eurostat SeaRoute** (Dijkstra on global maritime lane network) and **VISIR-2 GMD 2023** concepts for realistic sea routing:

| Component | Source | Description |
|-----------|--------|-------------|
| **MaritimeRouter** | Eurostat searoute | Dijkstra on 5km-resolution shipping lanes (not great-circle) |
| **HarboursDatabase** | VISIR-2 | 909 real-world ports from `harbours_DB.csv` (UN/LOCODE, lat/lon) |
| **K-Shortest Paths** | VISIR-2 Yen's algorithm | Alternative routes by restricting different passages |
| **Weather Impact** | VISIR-2 env fields | Speed/fuel multipliers for calm/moderate/rough/severe conditions |
| **Passage Avoidance** | Eurostat | 12 straits: Suez, Panama, Malacca, Gibraltar, Dover, Bering, etc. |
| **Fuel & Cost Est.** | VISIR-2 velocity models | Tons of fuel + USD cost per route |

**Key routes computed:**
| Route | Distance | Duration | Fuel | Cost |
|-------|----------|----------|------|------|
| Rotterdam → Mombasa | 11,873 km | 267h (11 days) | 1,670 tons | $946k |
| Frankfurt → Nairobi | 12,256 km | 276h (11.5 days) | 1,723 tons | $977k |
| Rotterdam → Shanghai | 15,507 km | 349h (14.5 days) | 2,181 tons | $1.24M |

**Disruption impact analysis:** Suez closure adds ~4,100 km and ~3.8 days to Europe-Asia routes.

```python
from agents.recovery_agents.maritime_router import MaritimeRouter
router = MaritimeRouter()
route = router.compute_route(
    origin=(4.4792, 51.9225),      # Rotterdam (lon, lat)
    destination=(39.6612, -4.0383), # Mombasa
    restrictions=['suez'],          # Avoid Suez Canal
)
print(f"{route.distance_km} km, {route.duration_hours}h, ${route.cost_estimate_usd}")
```

**K-shortest path alternatives** for resilience planning:
```python
alternatives = router.compute_k_alternatives(
    origin=(4.4792, 51.9225),
    destination=(121.4737, 31.2304),
    k=3,
)
# Returns primary route + 2 alternatives via different passage restrictions
```

The `GeodesicRouter` automatically detects seaports near origin/destination and uses maritime routing when available, falling back to Haversine for land-only routes.

### Local SOP Corpus
Policy Agent queries 3 local SOP documents (WHO, DHL, EU GDP) via ChromaDB vector store instead of relying on external APIs. Ingestion is deterministic and idempotent via `scripts/ingest_sops.py`.

---

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"
pip install chromadb  # Required for RAG vector store
pip install searoute  # Maritime route computation (Eurostat SeaRoute)

# Run tests (45/45)
pytest tests/ -v

# Run full pipeline dry-run
python dry_run.py

# Ingest SOP corpus into ChromaDB
python scripts/ingest_sops.py

# Start demo backend (serves API + React SPA)
uvicorn api.index:app --host 0.0.0.0 --port 8001

# Start SAP Mock Server (separate terminal)
uvicorn sap_mock_server.main:app --port 8080

# Deploy to Vercel
vercel deploy
```

## Deployment (Vercel)

The demo is deployed as a Python serverless function on Vercel:

- **Entrypoint**: `api/index.py` re-exports the FastAPI app
- **Dependencies**: `requirements.txt` (fastapi, pydantic, structlog, ortools, numpy)
- **Build**: `@vercel/python` runtime with `pip install -r requirements.txt`
- **Frontend**: Pre-built React SPA served from `demo/frontend/dist/`
- **pyproject.toml**: Excluded from deployment (avoids broken `odata` dep)

---

## SAP Integration

| SAP Product | Role | Data Flow |
|------------|------|-----------|
| **SAP TM** | Freight execution | Read orders → Write dispatch updates |
| **SAP S/4HANA** | Inventory & batch | Read expiry/demand → Write allocation flags |
| **SAP LBN** | Carrier collaboration | Read tracking signals |
| **SAP BTP** | Host platform | Kyma runtime, Event Mesh, Destinations |

All SAP writes flow through a single **SAP Integration Gateway** microservice enforcing idempotency, schema validation, and audit logging.

For development, the **SAP Mock Server** (`sap_mock_server/main.py`) provides a standalone OData v4 emulator with ETag validation and idempotency key ledger.

---

## Test Suite — 45/45 Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/unit/test_schemas.py` | 15 | Pydantic schemas, PolicyWeights, CCROGraphState, AuditChain |
| `tests/unit/test_new_components.py` | 27 | SAP mock server, thermal decay, SOP ingestion, geodesic routing |
| `tests/solver_determinism/` | 3 | Solver reproducibility, different weights, dropped sites |

---

## License

Internal / Partner Engineering — DHL Life Sciences & Healthcare
