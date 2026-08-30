# DHL Life Sciences & Healthcare — Emergency Allocation SOP

**Document ID:** DHL-LSH-EAL-2025-003
**Version:** 2.1
**Effective Date:** 2025-03-01
**Classification:** Internal — Operations
**Approved By:** VP Supply Chain, DHL Life Sciences & Healthcare

---

## 1. Purpose

This Standard Operating Procedure defines the process for allocating scarce cold-chain pharmaceutical products when normal supply capacity is insufficient to meet all clinic demands simultaneously. This SOP activates automatically when the CCRO platform enters State S4 (CRITICAL) or S5 (SCARCITY ALLOCATION).

## 2. Activation Criteria

The Emergency Allocation Protocol activates when ALL of the following conditions are met:

1. **Capacity Shortfall Confirmed:** Available refrigerated transport capacity < total clinic demand (kg)
2. **Recovery Options Exhausted:** All standard recovery options (rerouting, warehouse rebalancing, fleet expansion) have been evaluated and found insufficient
3. **Hard Deadline Approaching:** At least one clinic site has remaining cold-chain viability of less than 12 hours
4. **State Machine Triggered:** CCRO platform has transitioned to S4_RECOVERY_INSUFFICIENT

## 3. Allocation Process

### 3.1 Step 1 — Policy Weight Determination

Before allocation can proceed, policy weights must be determined by the Policy Agent:

- **Clinical Urgency Weight (w1):** Higher values prioritize sites closest to expiry
- **Operational Simplicity Weight (w2):** Higher values prioritize easier-to-reach sites
- **Value Preservation Weight (w3):** Higher values prioritize higher-demand sites

**Constraint:** w1 + w2 + w3 = 1.0, with each weight in range [0, 1]

Weights are determined through RAG retrieval of applicable SOP clauses and organizational policy. The Policy Agent must cite the specific SOP clauses that justify the weight selection.

### 3.2 Step 2 — Constraint Validation

Before the solver runs, each potential (vehicle, site) pair must pass three hard constraints:

| Constraint | Formula | Description |
|-----------|---------|-------------|
| **C1: Thermal Lifetime** | transit_time + buffer < remaining_shelf_life | Product must arrive before thermal viability expires |
| **C2: Vehicle Capacity** | sum(allocated_mass per vehicle) <= max_payload | No vehicle may exceed its weight capacity |
| **C3: Reachability** | A feasible route must exist within thermal constraints | Sites with no viable route are dropped |

These constraints are **absolute** — they cannot be relaxed, bypassed, or overridden by AI or human operators.

### 3.3 Step 3 — Solver Execution

The OR-Tools CP-SAT solver computes the optimal allocation that maximizes priority-weighted fulfillment:

**Objective:** Maximize sum(P_i * x_{i,v}) for all feasible (site, vehicle) pairs

Where P_i = w1 * SR_i + w2 * OS_i + w3 * VPI_i

The solver produces:
- An allocation plan with specific (site, vehicle, units) assignments
- A list of dropped sites with reasons
- An objective value quantifying total priority-weighted fulfillment
- A deterministic input snapshot hash for audit reproducibility

### 3.4 Step 4 — Compliance Check

Before execution, the Compliance Agent verifies:

1. **Sanctions Compliance:** No allocations to sanctioned regions or entities
2. **Cold Chain Compliance:** All pharmaceutical products within temperature thresholds
3. **Allocation Limits:** No site exceeds maximum allocation per dispatch
4. **Vehicle Compatibility:** Cold-chain vehicles assigned to pharmaceutical shipments

If any blocking violation is found, execution is halted and the violation is logged.

### 3.5 Step 5 — Human Approval

The proposed allocation is presented to an authorized Operations Manager via the Governance UI. The manager may:

- **Approve:** Execute the allocation as proposed
- **Modify:** Adjust specific assignments (subject to C1/C2/C3 re-validation)
- **Reject:** Return to the solver for an alternate plan

Approval must be recorded with the manager's authenticated SAP identity.

### 3.6 Step 6 — SAP Execution

Upon approval, the Execution Agent:

1. Writes freight order updates to SAP TM with idempotency keys
2. Updates inventory allocation flags in SAP S/4HANA
3. Records all write operations in the immutable audit chain
4. Generates a writeback confirmation with SAP response codes

## 4. Escalation Matrix

| Condition | Escalation Level | Response Time |
|-----------|-----------------|---------------|
| Single clinic at risk | Operations Manager | 30 minutes |
| Multiple clinics at risk | Regional Director | 15 minutes |
| Network-wide scarcity | VP Supply Chain | Immediate |
| Patient safety concern | Chief Medical Officer | Immediate |

## 5. Documentation Requirements

All emergency allocations must produce:

1. **Allocation Plan** with solver version, input hash, and objective value
2. **Compliance Report** with all checked rules and results
3. **Approval Record** with authenticated approver identity and timestamp
4. **Audit Chain** with hash-linked records from state transition through execution
5. **Post-Event Review** within 48 hours documenting lessons learned

## 6. Post-Allocation Monitoring

After execution, the system must:

1. Monitor SAP TM for delivery confirmation
2. Verify temperature logs for all dispatched shipments
3. Update clinic inventory levels in SAP S/4HANA
4. Transition state machine back to S1 (NORMAL) or S2 (DEGRADED) based on updated metrics
5. Archive the complete audit trail for regulatory compliance
