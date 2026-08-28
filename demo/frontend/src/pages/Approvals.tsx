import { useState, useEffect } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  FileText,
  Edit3,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Info,
  Send,
} from 'lucide-react';
import { api } from '../api';
import type { SystemState, AllocationAssignment } from '../types';

interface Props {
  state: SystemState | null;
  onRefresh: () => Promise<void>;
  addToast: (msg: string, type?: 'success' | 'error') => void;
}

export default function Approvals({ state, onRefresh, addToast }: Props) {
  const [loading, setLoading] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [edits, setEdits] = useState<AllocationAssignment[]>([]);
  const [allocation, setAllocation] = useState<any>(null);

  useEffect(() => {
    if (state?.has_proposed_allocation) {
      api.getProposedAllocation().then(setAllocation).catch(() => setAllocation(null));
    } else {
      setAllocation(null);
    }
  }, [state?.has_proposed_allocation]);

  const startEditing = () => {
    if (allocation) {
      setEdits(allocation.assignments.map((a: AllocationAssignment) => ({ ...a })));
      setIsEditing(true);
    }
  };

  const handleApprove = async () => {
    setLoading('approve');
    try {
      const res = await api.approveAllocation();
      addToast(res.message || 'Allocation approved');
      await onRefresh();
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setLoading(null);
    }
  };

  const handleReject = async () => {
    setLoading('reject');
    try {
      const res = await api.rejectAllocation();
      addToast(res.message || 'Allocation rejected');
      await onRefresh();
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setLoading(null);
    }
  };

  const handleModifySubmit = async () => {
    setLoading('modify');
    try {
      const modifications = edits.map((e) => ({
        site_id: e.site_id,
        vehicle_id: e.vehicle_id,
        allocated_units: e.allocated_units,
      }));
      const res = await api.modifyAllocation(modifications);
      addToast(res.message || 'Allocation modified');
      setIsEditing(false);
      await onRefresh();
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setLoading(null);
    }
  };

  const updateEdit = (siteId: string, field: string, value: any) => {
    setEdits((prev) =>
      prev.map((e) => (e.site_id === siteId ? { ...e, [field]: value } : e))
    );
  };

  if (!allocation) {
    return (
      <div>
        <div className="page-header">
          <h2>Approval Card</h2>
          <p>Human-in-the-loop allocation review</p>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: 60 }}>
          <ShieldAlert size={48} color="var(--text-tertiary)" style={{ marginBottom: 16 }} />
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
            No Allocation Pending
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
            Trigger a disruption and run the scarcity allocation engine to generate a proposal.
          </div>
        </div>
      </div>
    );
  }

  const doNothing = allocation.do_nothing;
  const ccroAlloc = allocation.ccro_allocation;
  const totalFulfillment = allocation.assignments.reduce(
    (sum: number, a: AllocationAssignment) => sum + a.priority_score * a.allocated_units,
    0
  );

  return (
    <div>
      <div className="page-header">
        <h2>Allocation Approval Card</h2>
        <p>Review the AI-recommended allocation against the standard approach</p>
      </div>

      {/* Side-by-side Comparison */}
      <div className="comparison-grid">
        {/* Do Nothing */}
        <div className="comparison-card">
          <div className="comparison-card-title" style={{ color: 'var(--text-tertiary)' }}>
            <XCircle size={16} />
            Do Nothing / Standard Route
          </div>
          <div className="comparison-card-value" style={{ color: 'var(--critical)' }}>
            €{doNothing.total_spoilage_cost_eur.toLocaleString()}
          </div>
          <div className="comparison-card-detail">
            Estimated spoilage loss from {doNothing.sites_at_risk.length} sites at risk.
            {doNothing.estimated_stockout_sites.length > 0 && (
              <span style={{ color: 'var(--critical)' }}>
                {' '}{doNothing.estimated_stockout_sites.length} sites will stock out.
              </span>
            )}
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {doNothing.sites_at_risk.map((sid: string) => (
              <span key={sid} className="badge badge-danger">{sid}</span>
            ))}
          </div>
        </div>

        {/* CCRO Allocation */}
        <div className="comparison-card recommended">
          <div className="comparison-card-title" style={{ color: 'var(--accent-ice)' }}>
            <ShieldCheck size={16} />
            CCRO Policy Allocation
          </div>
          <div className="comparison-card-value" style={{ color: 'var(--accent-ice)' }}>
            €{ccroAlloc.total_avoided_loss_eur.toLocaleString()}
          </div>
          <div className="comparison-card-detail">
            Avoided loss across {ccroAlloc.sites_covered} sites.
            {ccroAlloc.total_units_dispatched > 0 && (
              <span> {ccroAlloc.total_units_dispatched} units dispatched.</span>
            )}
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            <span className="badge badge-info">
              Objective: {allocation.objective_value.toFixed(3)}
            </span>
            <span className="badge badge-success">
              {allocation.assignments.length} allocated
            </span>
            {allocation.dropped_sites.length > 0 && (
              <span className="badge badge-danger">
                {allocation.dropped_sites.length} dropped
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Allocation Table */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <div className="card-title">
            <FileText size={16} />
            Proposed Allocation
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            Plan: <span className="mono">{allocation.plan_id.slice(0, 12)}...</span>
          </div>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Site</th>
                <th>City</th>
                <th>Units</th>
                <th>Vehicle</th>
                <th>P_i</th>
                <th>Mass (kg)</th>
              </tr>
            </thead>
            <tbody>
              {(isEditing ? edits : allocation.assignments).map((a: AllocationAssignment) => (
                <tr key={a.site_id}>
                  <td>
                    <span className="mono" style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                      {a.site_id}
                    </span>
                  </td>
                  <td>{a.site_name}</td>
                  <td>
                    {isEditing ? (
                      <input
                        type="number"
                        value={a.allocated_units}
                        onChange={(e) =>
                          updateEdit(a.site_id, 'allocated_units', parseInt(e.target.value) || 0)
                        }
                        style={{
                          width: 70,
                          padding: '4px 8px',
                          background: 'var(--bg-deep)',
                          border: '1px solid var(--border-default)',
                          borderRadius: 4,
                          color: 'var(--text-primary)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: 13,
                        }}
                      />
                    ) : (
                      <span className="mono">{a.allocated_units}</span>
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      <input
                        type="text"
                        value={a.vehicle_id}
                        onChange={(e) => updateEdit(a.site_id, 'vehicle_id', e.target.value)}
                        style={{
                          width: 90,
                          padding: '4px 8px',
                          background: 'var(--bg-deep)',
                          border: '1px solid var(--border-default)',
                          borderRadius: 4,
                          color: 'var(--text-primary)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: 13,
                        }}
                      />
                    ) : (
                      <span className="mono">{a.vehicle_id}</span>
                    )}
                  </td>
                  <td>
                    <span
                      style={{
                        color:
                          a.priority_score > 0.6
                            ? '#3D8B7A'
                            : a.priority_score > 0.3
                            ? '#D4A017'
                            : 'var(--text-tertiary)',
                        fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {a.priority_score.toFixed(3)}
                    </span>
                  </td>
                  <td className="mono">{a.payload_mass_kg.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {isEditing && (
          <div
            style={{
              marginTop: 12,
              padding: '8px 12px',
              background: 'var(--accent-ice-dim)',
              border: '1px solid var(--accent-ice-border)',
              borderRadius: 6,
              fontSize: 12,
              color: 'var(--text-secondary)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Info size={14} color="var(--accent-ice)" />
            Modifications will be re-validated against C1 (thermal), C2 (capacity), C3 (reachability) constraints.
          </div>
        )}
      </div>

      {/* Dropped Sites */}
      {allocation.dropped_sites.length > 0 && (
        <div className="dropped-panel">
          <div className="dropped-panel-title">
            <AlertTriangle size={16} />
            Dropped Sites ({allocation.dropped_sites.length})
          </div>
          {allocation.dropped_sites.map((ds: any) => (
            <div
              key={ds.site_id}
              style={{
                fontSize: 13,
                color: 'var(--critical)',
                marginBottom: 6,
                paddingLeft: 22,
              }}
            >
              <strong>{ds.site_id}</strong> ({ds.site_name}) — {ds.reason}
            </div>
          ))}
        </div>
      )}

      {/* Policy Justification */}
      <div className="policy-panel">
        <div className="card-title" style={{ marginBottom: 12 }}>
          <FileText size={16} />
          Policy Justification
        </div>
        <div className="weight-row">
          <div className="weight-item">
            <strong style={{ color: 'var(--stable)' }}>w1</strong>
            Clinical Urgency: <span className="mono">{allocation.policy_weights.w1.toFixed(3)}</span>
          </div>
          <div className="weight-item">
            <strong style={{ color: 'var(--accent-ice)' }}>w2</strong>
            Operational Simplicity: <span className="mono">{allocation.policy_weights.w2.toFixed(3)}</span>
          </div>
          <div className="weight-item">
            <strong style={{ color: 'var(--policy)' }}>w3</strong>
            Value Preservation: <span className="mono">{allocation.policy_weights.w3.toFixed(3)}</span>
          </div>
        </div>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
          Cited SOP Clauses
        </div>
        <div className="citation-item">
          <strong>DHL-LSH-SOP-2024 §4.2</strong> — Cold chain deviation response protocol requires immediate escalation to network-level allocation when thermal drift exceeds 3°C.
        </div>
        <div className="citation-item">
          <strong>DHL-LSH-SOP-2024 §6.1</strong> — Priority-weighted allocation must consider clinical urgency (remaining shelf life), operational feasibility, and vulnerable population index.
        </div>
        <div className="citation-item">
          <strong>EMA-GDP-GUIDE §9.3</strong> — Human approval required for any allocation affecting more than 2 distribution points simultaneously.
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {isEditing ? (
          <>
            <button
              className="btn btn-stable"
              onClick={handleModifySubmit}
              disabled={loading !== null}
            >
              {loading === 'modify' ? (
                <><div className="spinner" /> Submitting...</>
              ) : (
                <><Send size={16} /> Submit Modified Allocation</>
              )}
            </button>
            <button className="btn btn-ghost" onClick={() => setIsEditing(false)}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <button
              className="btn btn-primary"
              onClick={handleApprove}
              disabled={loading !== null}
            >
              {loading === 'approve' ? (
                <><div className="spinner" /> Approving...</>
              ) : (
                <><CheckCircle size={16} /> Approve Allocation</>
              )}
            </button>
            <button
              className="btn btn-ghost"
              onClick={startEditing}
              disabled={loading !== null}
            >
              <Edit3 size={16} /> Modify & Approve
            </button>
            <button
              className="btn btn-danger"
              onClick={handleReject}
              disabled={loading !== null}
            >
              {loading === 'reject' ? (
                <><div className="spinner" /> Rejecting...</>
              ) : (
                <><XCircle size={16} /> Reject</>
              )}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
