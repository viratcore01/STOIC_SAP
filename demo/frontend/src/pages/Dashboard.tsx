import { useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Building2,
  Clock,
  Zap,
} from 'lucide-react';
import { api } from '../api';
import type { SystemState, DisruptionScenario } from '../types';

interface Props {
  state: SystemState | null;
  onRefresh: () => Promise<void>;
  addToast: (msg: string, type?: 'success' | 'error') => void;
}

const STATE_STEPS = [
  { id: 'S1_STABLE', label: 'Stable', shortLabel: 'S1', colorClass: 'stable' },
  { id: 'S2_ABSORBING_DISRUPTION', label: 'Absorbing', shortLabel: 'S2', colorClass: 'absorbing' },
  { id: 'S3_RECOVERY_CONSTRAINED', label: 'Constrained', shortLabel: 'S3', colorClass: 'constrained' },
  { id: 'S4_RECOVERY_INSUFFICIENT', label: 'Insufficient', shortLabel: 'S4', colorClass: 'insufficient' },
  { id: 'S5_SCARCITY_ALLOCATION', label: 'Scarcity', shortLabel: 'S5', colorClass: 'scarcity' },
];

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#C23B3B',
  high: '#D4A017',
  medium: '#E07B2F',
  low: '#3D8B7A',
};

const DISRUPTIONS: DisruptionScenario[] = [
  {
    id: 'D-001',
    name: 'Cold Storage Failure — Munich Hub',
    type: 'thermal_drift',
    severity: 'critical',
    affected_sites: ['CLN-001', 'CLN-004'],
    description: 'Main cold storage compressor failed at Munich distribution hub.',
  },
  {
    id: 'D-002',
    name: 'Port Congestion — Rotterdam',
    type: 'port_disruption',
    severity: 'high',
    affected_sites: ['CLN-002', 'CLN-006', 'CLN-007'],
    description: 'Severe weather caused port closure at Rotterdam.',
  },
  {
    id: 'D-003',
    name: 'Multi-Site Thermal Event',
    type: 'thermal_drift',
    severity: 'critical',
    affected_sites: ['CLN-001', 'CLN-002', 'CLN-004', 'CLN-007', 'CLN-008'],
    description: 'System-wide refrigeration anomaly across Central European network.',
  },
];

export default function Dashboard({ state, onRefresh, addToast }: Props) {
  const [loading, setLoading] = useState<string | null>(null);
  const [showDisruptions, setShowDisruptions] = useState(false);

  const currentState = state?.resilience_state || 'S1_STABLE';
  const activeStepIndex = STATE_STEPS.findIndex((s) => s.id === currentState);
  const margin = state?.capacity_margin ?? 100;
  const isRunning = state?.resilience_state !== 'S1_STABLE';

  const handleTrigger = async (disruptionId: string) => {
    setLoading(disruptionId);
    try {
      const res = await api.triggerDisruption(disruptionId);
      addToast(res.message || 'Disruption triggered');
      await onRefresh();
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setLoading(null);
      setShowDisruptions(false);
    }
  };

  const handleRunSolver = async () => {
    setLoading('solver');
    try {
      const res = await api.runAllocation();
      addToast(res.message || 'Solver completed');
      await onRefresh();
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setLoading(null);
    }
  };

  const threatenedSites = state?.sites?.filter((s) => s.is_threatened) || [];
  const sitesAtRisk = state?.sites?.filter((s) => s.remaining_shelf_life_hours < 12) || [];
  const marginColor = margin > 15 ? '#3D8B7A' : margin > 0 ? '#D4A017' : '#C23B3B';

  return (
    <div>
      <div className="page-header">
        <h2>Resilience Dashboard</h2>
        <p>Cold-chain network status and disruption response</p>
      </div>

      {/* State Machine Bar */}
      <div className="state-machine-bar">
        {STATE_STEPS.map((step, i) => (
          <div
            key={step.id}
            className={`state-step ${i <= activeStepIndex ? 'active' : ''}`}
          >
            <div className={`state-step-dot ${step.colorClass}`} />
            <div className="state-step-id">{step.shortLabel}</div>
            <div className="state-step-label">{step.label}</div>
          </div>
        ))}
      </div>

      {/* Vitals Row */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        {/* Capacity Margin */}
        <div className="metric-card">
          <div className="metric-card-label">Capacity Margin</div>
          <div className="metric-card-value" style={{ color: marginColor }}>
            {margin > 0 ? '+' : ''}{margin.toFixed(1)}%
          </div>
          <div className="gauge-track" style={{ marginTop: 8 }}>
            <div
              className="gauge-fill"
              style={{
                width: `${Math.max(0, Math.min(100, (margin + 20) / 1.2))}%`,
                background: marginColor,
              }}
            />
          </div>
          <div className="metric-card-detail">
            Threshold: 15% (S2→S3)
          </div>
        </div>

        {/* Threatened Sites */}
        <div className="metric-card">
          <div className="metric-card-label">Threatened Sites</div>
          <div className="metric-card-value" style={{ color: threatenedSites.length > 0 ? '#D4A017' : '#3D8B7A' }}>
            {threatenedSites.length}
            <span style={{ fontSize: 14, color: 'var(--text-tertiary)', marginLeft: 4 }}>
              / {state?.sites?.length || 0}
            </span>
          </div>
          <div className="metric-card-detail">
            {sitesAtRisk.length > 0 ? `${sitesAtRisk.length} with < 12h shelf life` : 'All sites stable'}
          </div>
        </div>

        {/* Total Demand */}
        <div className="metric-card">
          <div className="metric-card-label">Total Demand</div>
          <div className="metric-card-value">
            {state?.total_demand?.toLocaleString() || '—'}
          </div>
          <div className="metric-card-detail">
            units across all sites
          </div>
        </div>

        {/* Vehicle Capacity */}
        <div className="metric-card">
          <div className="metric-card-label">Vehicle Capacity</div>
          <div className="metric-card-value">
            {state?.total_available_capacity?.toLocaleString() || '—'}
          </div>
          <div className="metric-card-detail">
            kg across {state?.vehicles?.length || 0} vehicles
          </div>
        </div>
      </div>

      {/* Disruption Info + Actions */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        {/* Active Disruption */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <AlertTriangle size={16} />
              Current Disruption
            </div>
            {state?.current_disruption && (
              <span
                className={`badge badge-${state.current_disruption.severity === 'critical' ? 'danger' : 'warning'}`}
              >
                {state.current_disruption.severity}
              </span>
            )}
          </div>
          {state?.current_disruption ? (
            <div>
              <div style={{ fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
                {state.current_disruption.name}
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 12 }}>
                {state.current_disruption.description}
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {state.current_disruption.affected_sites.map((sid) => (
                  <span key={sid} className="badge badge-warning">{sid}</span>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>
              No active disruption. Network is stable.
            </div>
          )}
        </div>

        {/* Quick Actions */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Zap size={16} />
              Quick Actions
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <button
              className="btn btn-danger"
              onClick={() => setShowDisruptions(!showDisruptions)}
              disabled={loading !== null}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              <AlertTriangle size={16} />
              {isRunning ? 'Trigger Another Disruption' : 'Trigger Disruption'}
            </button>

            {showDisruptions && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {DISRUPTIONS.map((d) => (
                  <button
                    key={d.id}
                    className="btn btn-ghost btn-sm"
                    onClick={() => handleTrigger(d.id)}
                    disabled={loading !== null}
                    style={{ justifyContent: 'flex-start', textAlign: 'left' }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: SEVERITY_COLORS[d.severity],
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ flex: 1 }}>{d.name}</span>
                    <span className={`badge badge-${d.severity === 'critical' ? 'danger' : 'warning'}`}>
                      {d.severity}
                    </span>
                  </button>
                ))}
              </div>
            )}

            <button
              className="btn btn-primary"
              onClick={handleRunSolver}
              disabled={loading !== null || !isRunning}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              {loading === 'solver' ? (
                <>
                  <div className="spinner" />
                  Running Solver...
                </>
              ) : (
                <>
                  <Activity size={16} />
                  Run Scarcity Allocation
                </>
              )}
            </button>

            {state?.has_proposed_allocation && (
              <div
                style={{
                  padding: '10px 14px',
                  background: 'var(--accent-ice-dim)',
                  border: '1px solid var(--accent-ice-border)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 12,
                  color: 'var(--accent-ice)',
                  textAlign: 'center',
                }}
              >
                Allocation ready — go to Approvals to review
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Sites Overview Table */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <Building2 size={16} />
            Sites Overview
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            {threatenedSites.length} threatened · {sitesAtRisk.length} critical
          </div>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Site</th>
                <th>City</th>
                <th>Demand</th>
                <th>Shelf Life</th>
                <th>VPI</th>
                <th>Criticality</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {state?.sites?.map((site) => {
                const slColor =
                  site.remaining_shelf_life_hours < 6
                    ? '#C23B3B'
                    : site.remaining_shelf_life_hours < 12
                    ? '#D4A017'
                    : site.remaining_shelf_life_hours < 24
                    ? '#E07B2F'
                    : '#3D8B7A';
                return (
                  <tr key={site.id}>
                    <td>
                      <span className="mono" style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                        {site.id}
                      </span>
                    </td>
                    <td>{site.name}</td>
                    <td className="mono">{site.demand_units}</td>
                    <td>
                      <span style={{ color: slColor, fontWeight: 600 }} className="mono">
                        {site.remaining_shelf_life_hours.toFixed(1)}h
                      </span>
                      {site.remaining_shelf_life_hours < site.original_shelf_life_hours * 0.5 && (
                        <span style={{ fontSize: 10, color: 'var(--critical)', marginLeft: 4 }}>↓</span>
                      )}
                    </td>
                    <td className="mono">{site.vpi.toFixed(2)}</td>
                    <td>
                      <span
                        className={`badge badge-${
                          site.criticality === 'critical'
                            ? 'danger'
                            : site.criticality === 'high'
                            ? 'warning'
                            : 'info'
                        }`}
                      >
                        {site.criticality}
                      </span>
                    </td>
                    <td>
                      {site.is_threatened ? (
                        <span className="badge badge-danger">Threatened</span>
                      ) : (
                        <span className="badge badge-success">Stable</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Thread ID */}
      {state?.thread_id && (
        <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
          <Clock size={12} />
          Episode: <span className="mono">{state.thread_id}</span>
        </div>
      )}
    </div>
  );
}
