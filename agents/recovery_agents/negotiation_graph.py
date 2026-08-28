"""Recovery Agent Cluster — AutoGen-style multi-agent debate/negotiation.

The route, warehouse, and fleet sub-agents propose competing recovery options.
The internal negotiation resolves to a single RecoveryOptions[] output before
returning control to the Orchestrator. External agents never see intermediate turns.
"""

from __future__ import annotations

from typing import Optional

import structlog

from schemas import (
    RecoveryOption,
    RecoveryOptionType,
    ShelfLifeProjection,
)

logger = structlog.get_logger(__name__)


class RouteRealignSubagent:
    """Evaluates route re-alignment recovery options."""

    def propose(
        self,
        shelf_life_projections: dict[str, ShelfLifeProjection],
        current_routes: dict[str, str],
        capacity_margin: float,
    ) -> list[RecoveryOption]:
        """Propose route re-alignment options based on disruption context."""
        options: list[RecoveryOption] = []

        for site_id, proj in shelf_life_projections.items():
            if proj.remaining_shelf_life_hours < 12:
                # Propose expedited route for urgent sites
                options.append(
                    RecoveryOption(
                        option_type=RecoveryOptionType.ROUTE,
                        delta_capacity=0.0,
                        cost_estimate=500.0,
                        feasibility_score=0.8,
                        description=f"Expedited route for {site_id} ({proj.remaining_shelf_life_hours:.1f}h remaining)",
                        affected_site_ids=[site_id],
                    )
                )

        return options


class WarehouseRebalSubagent:
    """Evaluates warehouse rebalancing recovery options."""

    def propose(
        self,
        shelf_life_projections: dict[str, ShelfLifeProjection],
        warehouse_capacities: dict[str, float],
    ) -> list[RecoveryOption]:
        """Propose warehouse rebalancing options."""
        options: list[RecoveryOption] = []

        # Identify overstocked and understocked warehouses
        total_demand = sum(p.demand_units for p in shelf_life_projections.values())
        if total_demand > 0:
            options.append(
                RecoveryOption(
                    option_type=RecoveryOptionType.WAREHOUSE,
                    delta_capacity=total_demand * 0.1,
                    cost_estimate=300.0,
                    feasibility_score=0.7,
                    description="Rebalance buffer stock from high-inventory to high-demand warehouses",
                    affected_site_ids=list(shelf_life_projections.keys()),
                )
            )

        return options


class FleetExpansionSubagent:
    """Evaluates fleet expansion recovery options."""

    def propose(
        self,
        shelf_life_projections: dict[str, ShelfLifeProjection],
        available_vehicles: int,
        max_fleet_expansion: int = 5,
    ) -> list[RecoveryOption]:
        """Propose fleet expansion options."""
        options: list[RecoveryOption] = []
        n_urgent = sum(
            1 for p in shelf_life_projections.values()
            if p.remaining_shelf_life_hours < 24
        )

        if n_urgent > 0 and available_vehicles < max_fleet_expansion:
            additional = min(n_urgent, max_fleet_expansion - available_vehicles)
            options.append(
                RecoveryOption(
                    option_type=RecoveryOptionType.FLEET,
                    delta_capacity=additional * 500.0,  # assume 500kg per vehicle
                    cost_estimate=additional * 200.0,
                    feasibility_score=0.6,
                    description=f"Expand fleet by {additional} vehicles for {n_urgent} urgent sites",
                    affected_site_ids=list(shelf_life_projections.keys()),
                )
            )

        return options


class RecoveryNegotiationGraph:
    """Coordinates the three sub-agents and resolves to a single output.

    Uses a simple aggregation + ranking approach (AutoGen-style debate
    resolved via priority scoring).
    """

    def __init__(self) -> None:
        self.route_agent = RouteRealignSubagent()
        self.warehouse_agent = WarehouseRebalSubagent()
        self.fleet_agent = FleetExpansionSubagent()

    def negotiate(
        self,
        shelf_life_projections: dict[str, ShelfLifeProjection],
        capacity_margin: float,
    ) -> list[RecoveryOption]:
        """Run the multi-agent negotiation and return resolved recovery options.

        All three sub-agents propose, then we rank by feasibility × impact
        and return the top options.
        """
        logger.info("recovery.negotiation_started", n_sites=len(shelf_life_projections))

        # Each sub-agent proposes independently
        route_options = self.route_agent.propose(
            shelf_life_projections, {}, capacity_margin
        )
        warehouse_options = self.warehouse_agent.propose(
            shelf_life_projections, {}
        )
        fleet_options = self.fleet_agent.propose(
            shelf_life_projections, available_vehicles=10
        )

        # Aggregate all proposals
        all_options = route_options + warehouse_options + fleet_options

        # Rank by feasibility score (higher = better)
        all_options.sort(key=lambda o: o.feasibility_score, reverse=True)

        # Take top options (up to 5 for governance review)
        resolved = all_options[:5]

        logger.info(
            "recovery.negotiation_completed",
            total_proposals=len(all_options),
            resolved=len(resolved),
        )

        return resolved
