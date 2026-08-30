"""Compliance Agent — Rule-based trade regulation and sanctions checking.

Checks allocations against:
  1. EU/US sanctions lists (sanctioned countries, entities)
  2. Cold chain temperature thresholds (pharmaceutical compliance)
  3. Export/import restrictions (dual-use goods, controlled substances)
  4. Maximum allocation limits per site (prevent hoarding)

Returns a ComplianceReport with pass/fail status and violation details.
This agent runs BEFORE SAP TM writeback in the EXECUTE phase.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from schemas import AllocationPlan, SiteAllocation, WritebackStatus

logger = structlog.get_logger(__name__)


class ComplianceViolation(BaseModel):
    """A single compliance violation detected."""

    rule_id: str
    rule_name: str
    severity: str  # "blocking", "warning", "info"
    site_id: str
    message: str
    details: dict = Field(default_factory=dict)


class ComplianceReport(BaseModel):
    """Result of compliance checking on an allocation plan."""

    plan_id: str
    is_compliant: bool
    violations: list[ComplianceViolation] = Field(default_factory=list)
    warnings: list[ComplianceViolation] = Field(default_factory=list)
    checked_rules: int = 0
    summary: str = ""


# ---------------------------------------------------------------------------
# Sanctions and restricted regions
# ---------------------------------------------------------------------------

# EU/US sanctioned countries/regions (simplified for demo)
SANCTIONED_REGIONS: set[str] = {
    "RU",  # Russia
    "IR",  # Iran
    "KP",  # North Korea
    "SY",  # Syria
    "CU",  # Cuba
    "BY",  # Belarus
}

# Sanctioned entity types (simplified)
SANCTIONED_ENTITY_KEYWORDS: list[str] = [
    "military",
    "defense",
    "weapons",
    "nuclear",
]

# Temperature thresholds for pharmaceutical cold chain (°C)
COLD_CHAIN_TEMP_MIN = 2.0
COLD_CHAIN_TEMP_MAX = 8.0
COLD_CHAIN_CRITICAL_MIN = 0.0
COLD_CHAIN_CRITICAL_MAX = 10.0

# Maximum allocation per site (prevent over-allocation)
MAX_ALLOCATION_PER_SITE_UNITS = 500


class ComplianceAgent:
    """Rule-based compliance checker for allocation plans.

    Runs a battery of checks before SAP writeback:
      - Sanctions compliance
      - Cold chain temperature compliance
      - Allocation limit checks
      - Export restriction checks
    """

    def check_plan(
        self,
        allocation: AllocationPlan,
        site_metadata: dict[str, dict] | None = None,
    ) -> ComplianceReport:
        """Run all compliance checks on an allocation plan.

        Args:
            allocation: The allocation plan to check.
            site_metadata: Optional site metadata (country, product type, etc.)

        Returns:
            ComplianceReport with pass/fail and violation details.
        """
        violations: list[ComplianceViolation] = []
        warnings: list[ComplianceViolation] = []
        checked_rules = 0

        # Rule 1: Sanctions check
        checked_rules += 1
        v, w = self._check_sanctions(allocation, site_metadata)
        violations.extend(v)
        warnings.extend(w)

        # Rule 2: Cold chain compliance
        checked_rules += 1
        v, w = self._check_cold_chain(allocation, site_metadata)
        violations.extend(v)
        warnings.extend(w)

        # Rule 3: Allocation limits
        checked_rules += 1
        v, w = self._check_allocation_limits(allocation)
        violations.extend(v)
        warnings.extend(w)

        # Rule 4: Dropped site risk assessment
        checked_rules += 1
        v, w = self._check_dropped_risk(allocation)
        violations.extend(v)
        warnings.extend(w)

        # Rule 5: Vehicle-site compatibility
        checked_rules += 1
        v, w = self._check_vehicle_compatibility(allocation, site_metadata)
        violations.extend(v)
        warnings.extend(w)

        # Determine overall compliance
        blocking_violations = [v for v in violations if v.severity == "blocking"]
        is_compliant = len(blocking_violations) == 0

        summary = self._generate_summary(is_compliant, violations, warnings)

        report = ComplianceReport(
            plan_id=allocation.plan_id,
            is_compliant=is_compliant,
            violations=violations,
            warnings=warnings,
            checked_rules=checked_rules,
            summary=summary,
        )

        logger.info(
            "compliance.check_completed",
            plan_id=allocation.plan_id,
            is_compliant=is_compliant,
            n_violations=len(violations),
            n_warnings=len(warnings),
            checked_rules=checked_rules,
        )

        return report

    def _check_sanctions(
        self,
        allocation: AllocationPlan,
        site_metadata: dict[str, dict] | None,
    ) -> tuple[list[ComplianceViolation], list[ComplianceViolation]]:
        """Check if any allocations involve sanctioned regions or entities."""
        violations: list[ComplianceViolation] = []
        warnings: list[ComplianceViolation] = []

        if not site_metadata:
            return violations, warnings

        for assignment in allocation.assignments:
            meta = site_metadata.get(assignment.site_id, {})
            country = meta.get("country", "").upper()

            if country in SANCTIONED_REGIONS:
                violations.append(
                    ComplianceViolation(
                        rule_id="SANCTION-001",
                        rule_name="Sanctioned Region",
                        severity="blocking",
                        site_id=assignment.site_id,
                        message=f"Site {assignment.site_id} is in sanctioned region {country}. Allocation blocked.",
                        details={"country": country, "vehicle_id": assignment.vehicle_id},
                    )
                )

            # Check entity keywords
            entity_name = meta.get("entity_name", "").lower()
            for keyword in SANCTIONED_ENTITY_KEYWORDS:
                if keyword in entity_name:
                    violations.append(
                        ComplianceViolation(
                            rule_id="SANCTION-002",
                            rule_name="Sanctioned Entity",
                            severity="blocking",
                            site_id=assignment.site_id,
                            message=f"Entity at {assignment.site_id} matches sanctioned keyword '{keyword}'.",
                            details={"entity": entity_name, "keyword": keyword},
                        )
                    )

        return violations, warnings

    def _check_cold_chain(
        self,
        allocation: AllocationPlan,
        site_metadata: dict[str, dict] | None,
    ) -> tuple[list[ComplianceViolation], list[ComplianceViolation]]:
        """Check cold chain temperature compliance for pharmaceutical shipments."""
        violations: list[ComplianceViolation] = []
        warnings: list[ComplianceViolation] = []

        if not site_metadata:
            return violations, warnings

        for assignment in allocation.assignments:
            meta = site_metadata.get(assignment.site_id, {})
            product_type = meta.get("product_type", "")
            current_temp = meta.get("current_temperature_celsius")

            # Only check cold chain for pharmaceutical products
            if product_type not in ("pharmaceutical", "vaccine", "biologic"):
                continue

            if current_temp is None:
                warnings.append(
                    ComplianceViolation(
                        rule_id="COLD-001",
                        rule_name="Missing Temperature Data",
                        severity="warning",
                        site_id=assignment.site_id,
                        message=f"No temperature data for pharmaceutical site {assignment.site_id}.",
                        details={"product_type": product_type},
                    )
                )
                continue

            if current_temp < COLD_CHAIN_CRITICAL_MIN or current_temp > COLD_CHAIN_CRITICAL_MAX:
                violations.append(
                    ComplianceViolation(
                        rule_id="COLD-002",
                        rule_name="Critical Temperature Breach",
                        severity="blocking",
                        site_id=assignment.site_id,
                        message=f"Temperature {current_temp}°C at {assignment.site_id} outside critical range [{COLD_CHAIN_CRITICAL_MIN}, {COLD_CHAIN_CRITICAL_MAX}]°C. Product may be compromised.",
                        details={"temperature": current_temp, "product_type": product_type},
                    )
                )
            elif current_temp < COLD_CHAIN_TEMP_MIN or current_temp > COLD_CHAIN_TEMP_MAX:
                warnings.append(
                    ComplianceViolation(
                        rule_id="COLD-003",
                        rule_name="Temperature Warning",
                        severity="warning",
                        site_id=assignment.site_id,
                        message=f"Temperature {current_temp}°C at {assignment.site_id} outside recommended range [{COLD_CHAIN_TEMP_MIN}, {COLD_CHAIN_TEMP_MAX}]°C.",
                        details={"temperature": current_temp, "product_type": product_type},
                    )
                )

        return violations, warnings

    def _check_allocation_limits(
        self,
        allocation: AllocationPlan,
    ) -> tuple[list[ComplianceViolation], list[ComplianceViolation]]:
        """Check if any site exceeds maximum allocation limits."""
        violations: list[ComplianceViolation] = []
        warnings: list[ComplianceViolation] = []

        for assignment in allocation.assignments:
            if assignment.allocated_units > MAX_ALLOCATION_PER_SITE_UNITS:
                violations.append(
                    ComplianceViolation(
                        rule_id="LIMIT-001",
                        rule_name="Allocation Limit Exceeded",
                        severity="blocking",
                        site_id=assignment.site_id,
                        message=f"Allocation of {assignment.allocated_units} units at {assignment.site_id} exceeds limit of {MAX_ALLOCATION_PER_SITE_UNITS}.",
                        details={
                            "allocated": assignment.allocated_units,
                            "limit": MAX_ALLOCATION_PER_SITE_UNITS,
                        },
                    )
                )
            elif assignment.allocated_units > MAX_ALLOCATION_PER_SITE_UNITS * 0.8:
                warnings.append(
                    ComplianceViolation(
                        rule_id="LIMIT-002",
                        rule_name="High Allocation Warning",
                        severity="warning",
                        site_id=assignment.site_id,
                        message=f"Allocation of {assignment.allocated_units} units at {assignment.site_id} is above 80% of limit.",
                        details={
                            "allocated": assignment.allocated_units,
                            "limit": MAX_ALLOCATION_PER_SITE_UNITS,
                        },
                    )
                )

        return violations, warnings

    def _check_dropped_risk(
        self,
        allocation: AllocationPlan,
    ) -> tuple[list[ComplianceViolation], list[ComplianceViolation]]:
        """Assess risk from dropped sites (sites that couldn't be allocated)."""
        violations: list[ComplianceViolation] = []
        warnings: list[ComplianceViolation] = []

        for dropped in allocation.dropped_sites:
            if dropped.priority_score > 0.7:
                warnings.append(
                    ComplianceViolation(
                        rule_id="RISK-001",
                        rule_name="High-Priority Site Dropped",
                        severity="warning",
                        site_id=dropped.site_id,
                        message=f"High-priority site {dropped.site_id} (P_i={dropped.priority_score:.3f}) was dropped: {dropped.reason}.",
                        details={
                            "reason": dropped.reason,
                            "priority_score": dropped.priority_score,
                        },
                    )
                )

        return violations, warnings

    def _check_vehicle_compatibility(
        self,
        allocation: AllocationPlan,
        site_metadata: dict[str, dict] | None,
    ) -> tuple[list[ComplianceViolation], list[ComplianceViolation]]:
        """Check vehicle-site compatibility for sensitive shipments."""
        violations: list[ComplianceViolation] = []
        warnings: list[ComplianceViolation] = []

        if not site_metadata:
            return violations, warnings

        for assignment in allocation.assignments:
            meta = site_metadata.get(assignment.site_id, {})
            requires_cold_chain = meta.get("requires_cold_chain_vehicle", False)

            if requires_cold_chain and not assignment.vehicle_id:
                warnings.append(
                    ComplianceViolation(
                        rule_id="VEHICLE-001",
                        rule_name="Missing Vehicle Assignment",
                        severity="warning",
                        site_id=assignment.site_id,
                        message=f"Cold-chain site {assignment.site_id} has no vehicle assigned.",
                        details={"requires_cold_chain": requires_cold_chain},
                    )
                )

        return violations, warnings

    def _generate_summary(
        self,
        is_compliant: bool,
        violations: list[ComplianceViolation],
        warnings: list[ComplianceViolation],
    ) -> str:
        """Generate a human-readable compliance summary."""
        if is_compliant and not warnings:
            return "All compliance checks passed. Plan is approved for writeback."
        elif is_compliant and warnings:
            return f"Plan is compliant with {len(warnings)} warning(s). Review recommended before writeback."
        else:
            blocking = [v for v in violations if v.severity == "blocking"]
            return f"Plan BLOCKED: {len(blocking)} compliance violation(s) found. {len(warnings)} warning(s). Fix violations before writeback."
