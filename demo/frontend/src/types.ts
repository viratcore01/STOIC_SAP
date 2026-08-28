export type ResilienceState =
  | 'S1_STABLE'
  | 'S2_ABSORBING_DISRUPTION'
  | 'S3_RECOVERY_CONSTRAINED'
  | 'S4_RECOVERY_INSUFFICIENT'
  | 'S5_SCARCITY_ALLOCATION';

export interface SiteInfo {
  id: string;
  name: string;
  city: string;
  demand_units: number;
  criticality: string;
  vpi: number;
  remaining_shelf_life_hours: number;
  original_shelf_life_hours: number;
  batch_ids: string[];
  is_threatened: boolean;
}

export interface VehicleInfo {
  id: string;
  type: string;
  max_payload_kg: number;
}

export interface SystemState {
  resilience_state: ResilienceState;
  capacity_margin: number;
  total_demand: number;
  total_available_capacity: number;
  thread_id: string;
  tick_count: number;
  current_disruption: Disruption | null;
  has_proposed_allocation: boolean;
  sites: SiteInfo[];
  vehicles: VehicleInfo[];
}

export interface Disruption {
  id: string;
  name: string;
  type: string;
  severity: string;
  description: string;
  affected_sites: string[];
  timestamp: string;
}

export interface DisruptionScenario {
  id: string;
  name: string;
  type: string;
  severity: string;
  affected_sites: string[];
  description: string;
}

export interface AllocationAssignment {
  site_id: string;
  site_name: string;
  city: string;
  allocated_units: number;
  vehicle_id: string;
  priority_score: number;
  payload_mass_kg: number;
}

export interface DroppedSite {
  site_id: string;
  site_name: string;
  reason: string;
  priority_score: number;
}

export interface ProposedAllocation {
  plan_id: string;
  assignments: AllocationAssignment[];
  dropped_sites: DroppedSite[];
  objective_value: number;
  solver_version: string;
  input_snapshot_hash: string;
  created_at: string;
  policy_weights: PolicyWeights;
  do_nothing: {
    total_spoilage_cost_eur: number;
    sites_at_risk: string[];
    estimated_stockout_sites: string[];
  };
  ccro_allocation: {
    total_avoided_loss_eur: number;
    sites_covered: number;
    total_units_dispatched: number;
  };
}

export interface PolicyWeights {
  w1: number;
  w2: number;
  w3: number;
}

export interface AuditEntry {
  record_id: string;
  event_type: string;
  timestamp: string;
  actor_type: string;
  actor_id: string;
  thread_id: string;
  allocation_plan_id: string | null;
  payload: Record<string, any>;
  record_hash: string;
  prev_hash: string;
}

export interface AuditLogResponse {
  entries: AuditEntry[];
  chain_length: number;
  chain_valid: boolean;
  chain_tip: string;
}

export interface AllocationHistoryEntry {
  plan_id: string;
  status: string;
  approved_by: string;
  approved_at: string;
  assignments_count: number;
  dropped_count: number;
  objective_value: number;
  policy_weights: PolicyWeights;
  disruption: string | null;
}

export interface Settings {
  state_machine_thresholds: {
    s2_s3_capacity_margin: number;
    s3_s4_capacity_margin: number;
  };
  solver_config: {
    handling_buffer_hours: number;
    per_unit_mass_kg: number;
    time_limit_seconds: number;
  };
  policy_weights: PolicyWeights;
  sap_destinations: Record<string, { status: string; url: string }>;
  agent_health: Record<string, string>;
}
