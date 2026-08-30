# EU Guidelines on Good Distribution Practice — Temperature Control

**Document ID:** EU-GDP-TC-2023-007
**Version:** 1.4
**Effective Date:** 2023-09-01
**Regulation Reference:** EU Directive 2001/83/EC, Annex 15; EU GMP Annex 11
**Classification:** Regulatory Compliance

---

## 1. Regulatory Scope

This document implements the temperature control requirements of the EU Guidelines on Good Distribution Practice (GDP) of Medicinal Products for Human Use. It applies to all entities in the pharmaceutical distribution chain operating within the European Economic Area (EEA).

## 2. Temperature Zones and Requirements

### 2.1 Defined Temperature Zones

| Zone | Range | Product Examples | Monitoring Frequency |
|------|-------|-----------------|---------------------|
| **Deep Freeze** | -25°C to -10°C | mRNA vaccines, plasma derivatives | Every 5 minutes |
| **Cold Chain** | +2°C to +8°C | Insulins, most vaccines, biologics | Every 10 minutes |
| **Cool** | +8°C to +15°C | Certain antibiotics, suppositories | Every 15 minutes |
| **Controlled Room Temp** | +15°C to +25°C | Tablets, capsules, oral liquids | Every 30 minutes |

### 2.2 Mean Kinetic Temperature (MKT)

For products stored under controlled room temperature, MKT must not exceed +25°C. MKT is calculated using the formula:

```
MKT = (Delta_H / R) / (-ln(sum(exp(-Delta_H / (R * T_i)) / n)))
```

Where Delta_H = 83.144 kJ/mol (default activation energy), R = 8.314 J/(mol*K), T_i = temperature in Kelvin at each reading.

### 2.3 Cold Chain Deviation Protocol

When temperature deviates from the defined range:

| Deviation | Duration | Action |
|-----------|----------|--------|
| +2°C to +8°C exceeded (up to +10°C) | < 1 hour | Document and continue |
| +2°C to +8°C exceeded (up to +10°C) | 1-4 hours | Quarantine. Assess with manufacturer. |
| Above +10°C | Any duration | Quarantine immediately. Notify QP. |
| Below 0°C | Any duration | Quarantine immediately. Assess freezing damage. |
| Above +25°C | > 30 minutes | Quarantine. Full investigation. |

## 3. Transportation Requirements

### 3.1 Vehicle Qualification

All vehicles used for pharmaceutical cold-chain transport must:

- Be validated for the required temperature range
- Have calibrated temperature monitoring devices
- Have a minimum of 2 independent temperature sensors
- Maintain temperature logging throughout the journey
- Be capable of maintaining temperature for at least 2 hours without power (passive cooling)

### 3.2 Route Planning Constraints

When planning multi-drop pharmaceutical delivery routes:

1. **Total transit time** must not exceed 75% of the shortest remaining shelf life across all delivery points
2. **Handling buffer** of at least 1 hour per stop must be included
3. **Route optimization** must prioritize clinical urgency (shortest shelf life first)
4. **Backup routes** must be pre-planned for each segment in case of disruption

### 3.3 Cross-Border Requirements

For shipments crossing EU/EEA borders:

- Maintain chain of custody documentation
- Ensure GDP-compliant storage at border transit points
- Verify temperature continuity during customs inspection
- Document any temperature excursions during border processing

## 4. Documentation and Record Keeping

### 4.1 Required Records

Every cold-chain distribution must generate:

1. **Temperature log** — continuous recording from dispatch to delivery
2. **Transport record** — vehicle ID, driver, route, departure/arrival times
3. **Handover record** — condition at each transfer point
4. **Exception report** — any deviation from planned conditions
5. **Delivery confirmation** — receipt by authorized person at destination

### 4.2 Retention Period

All temperature-related records must be retained for a minimum of **5 years** or **1 year past the expiry date** of the product, whichever is longer.

### 4.3 Digital Audit Trail

Electronic records must comply with EU GMP Annex 11:

- Unique user identification for all entries
- Timestamp for every record creation and modification
- Audit trail showing all changes with old and new values
- Data integrity verification (checksums or hash chains)
- Backup and disaster recovery procedures

## 5. Quality Risk Management

### 5.1 Risk Assessment for Cold Chain

Risk assessments must consider:

- **Probability of temperature deviation** based on route, season, and vehicle age
- **Severity of impact** based on product value and patient criticality
- **Detectability** of deviations based on monitoring coverage

### 5.2 Corrective and Preventive Actions (CAPA)

Following any cold-chain deviation:

1. Root cause analysis within 48 hours
2. Corrective action implementation within 5 business days
3. Effectiveness verification within 30 days
4. Update to risk assessment if required
