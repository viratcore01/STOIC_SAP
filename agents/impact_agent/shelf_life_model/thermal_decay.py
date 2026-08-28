"""Thermal Decay Model — Projects remaining shelf life based on temperature history.

Uses the Arrhenius equation and simplified first-order kinetics to estimate
remaining shelf life from cumulative thermal exposure.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Default pharmaceutical cold-chain parameters
DEFAULT_BASE_TEMP_C = 5.0  # nominal storage temperature
DEFAULT_ACTIVATION_ENERGY = 80000.0  # J/mol (typical for biologics)
DEFAULT_GAS_CONSTANT = 8.314  # J/(mol·K)
DEFAULT_ACCELERATION_FACTOR_PER_DEGREE = 2.0  # Q10 model approximation
DEFAULT_HANDLING_BUFFER_HOURS = 2.0


class ShelfLifeProjection:
    """Compute remaining shelf life from temperature exposure history."""

    def __init__(
        self,
        base_temp_c: float = DEFAULT_BASE_TEMP_C,
        activation_energy: float = DEFAULT_ACTIVATION_ENERGY,
        handling_buffer_hours: float = DEFAULT_HANDLING_BUFFER_HOURS,
    ):
        self.base_temp_c = base_temp_c
        self.activation_energy = activation_energy
        self.handling_buffer_hours = handling_buffer_hours

    def compute_remaining_shelf_life(
        self,
        original_shelf_life_hours: float,
        temperature_readings: list[float],
        reading_interval_hours: float = 1.0,
    ) -> float:
        """Compute remaining shelf life given temperature history.

        Uses the Arrhenius-based thermal factor approach:
        effective_time = Σ (k(T_i) / k(T_ref)) * Δt
        remaining_life = original_life - effective_time

        Args:
            original_shelf_life_hours: Original shelf life at reference temperature.
            temperature_readings: List of temperature readings in Celsius.
            reading_interval_hours: Time between readings.

        Returns:
            Estimated remaining shelf life in hours.
        """
        if not temperature_readings:
            return original_shelf_life_hours

        ref_temp_k = self.base_temp_c + 273.15

        # Compute effective (degraded) time
        effective_time = 0.0
        for temp_c in temperature_readings:
            temp_k = temp_c + 273.15
            # Arrhenius rate ratio: k(T) / k(T_ref)
            rate_ratio = math.exp(
                (self.activation_energy / DEFAULT_GAS_CONSTANT)
                * (1.0 / ref_temp_k - 1.0 / temp_k)
            )
            effective_time += rate_ratio * reading_interval_hours

        remaining = max(0.0, original_shelf_life_hours - effective_time)

        logger.debug(
            "shelf_life.computed",
            original_hours=original_shelf_life_hours,
            effective_time=round(effective_time, 2),
            remaining_hours=round(remaining, 2),
        )
        return remaining

    def project_from_sap_data(
        self,
        material_expiry_date: datetime,
        current_time: Optional[datetime] = None,
        temperature_readings: Optional[list[float]] = None,
    ) -> float:
        """Project remaining shelf life from SAP batch expiry data.

        Args:
            material_expiry_date: Batch material expiration date from SAP.
            current_time: Current server time.
            temperature_readings: Optional temperature history for degradation.

        Returns:
            Remaining shelf life in hours (from now to expiry, adjusted for thermal exposure).
        """
        now = current_time or datetime.now(timezone.utc)
        hours_to_expiry = (material_expiry_date - now).total_seconds() / 3600.0

        if hours_to_expiry <= 0:
            return 0.0

        if temperature_readings:
            # Apply thermal degradation factor
            degraded_life = self.compute_remaining_shelf_life(
                hours_to_expiry, temperature_readings
            )
            return max(0.0, degraded_life - self.handling_buffer_hours)

        return max(0.0, hours_to_expiry - self.handling_buffer_hours)
