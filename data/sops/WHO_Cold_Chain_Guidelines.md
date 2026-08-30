# WHO Cold Chain Management Guidelines for Pharmaceutical Products

**Document ID:** WHO-CC-2024-001
**Version:** 3.2
**Effective Date:** 2024-01-15
**Classification:** Public Health Guidance

---

## 1. Scope and Purpose

These guidelines establish the minimum requirements for maintaining the cold chain for temperature-sensitive pharmaceutical products, including vaccines, biologics, and insulin products, throughout the supply chain from manufacturing to point of administration.

## 2. Temperature Requirements

### 2.1 Standard Cold Chain Range

All pharmaceutical products classified as "cold chain" must be maintained between **+2°C and +8°C** throughout storage and transportation. This range is non-negotiable and applies to all product categories unless explicitly stated otherwise in the product's Summary of Product Characteristics (SmPC).

### 2.2 Critical Temperature Thresholds

| Threshold | Temperature Range | Action Required |
|-----------|------------------|-----------------|
| **Normal** | +2°C to +8°C | Continue standard monitoring |
| **Warning** | +0°C to +2°C or +8°C to +10°C | Increase monitoring frequency to every 15 minutes. Assess product viability. |
| **Critical** | Below 0°C or above +10°C | Initiate immediate investigation. Quarantine affected product. Notify Quality Assurance. |
| **Lethal** | Below -5°C or above +25°C | Product is presumed compromised. Do not distribute. Initiate loss assessment. |

### 2.3 Thermal excursion handling

When a temperature excursion is detected:

1. **Immediate isolation** of affected product from the distribution chain
2. **Documentation** of excursion duration, peak temperature, and affected batch IDs
3. **Manufacturer consultation** within 4 hours to assess product viability
4. **Decision to release or destroy** must be made within 24 hours
5. **Regulatory notification** if compromised product may have reached patients

## 3. Transit Time Constraints

### 3.1 Maximum Transit Duration

For products with remaining shelf life of less than 72 hours at the time of dispatch:

- Maximum transit time must not exceed **50% of remaining shelf life**
- A **handling buffer of 2 hours** must be added for loading, unloading, and inspection
- If calculated transit time plus buffer exceeds 50% of remaining shelf life, the shipment must be flagged for priority routing

### 3.2 Multi-Drop Route Constraints

When a single vehicle serves multiple clinic sites:

- Route must be planned in order of **decreasing urgency** (shortest remaining shelf life first)
- Each intermediate stop adds to the effective transit time for all subsequent deliveries
- Total route time must satisfy the constraint: `total_route_time + 2h_buffer < min(remaining_shelf_life across all stops)`

## 4. Emergency Allocation Protocol

### 4.1 Scarcity Declaration

A scarcity event is declared when available cold-chain transport capacity falls below total demand across all clinics in the network. The declaration triggers:

1. Activation of the Scarcity Allocation Engine
2. Mandatory policy-weighted allocation (not first-come-first-served)
3. Human approval required before any allocation is executed
4. Full audit trail logging with immutable hash chain

### 4.2 Priority Weighting

In scarcity conditions, allocation priority is determined by:

- **Clinical Urgency (w1):** Sites with shorter remaining shelf life receive higher priority
- **Operational Simplicity (w2):** Easier-to-reach sites receive moderate priority to maximize throughput
- **Value Preservation (w3):** Higher-demand sites receive priority to minimize total loss

The weights w1 + w2 + w3 must equal 1.0 and are determined by organizational policy. Individual weight values must be within the range [0, 1].

### 4.3 Human-in-the-Loop Requirement

No allocation in scarcity conditions may be executed without explicit human approval from an authorized Operations Manager. The approval must be recorded in the audit trail with:

- Approver's authenticated identity (SAP SAML/OAuth2)
- Timestamp of approval
- The specific allocation plan approved
- Any modifications made to the automated recommendation

## 5. Documentation and Audit

All cold chain activities must be documented in an immutable audit trail that satisfies:

- **21 CFR Part 11** requirements for electronic records
- **EU Annex 11** requirements for computerized systems
- **WHO TRS 961 Annex 9** requirements for good storage practices

Audit records must be hash-chained (SHA-256) and append-only. No record may be modified or deleted after creation.
