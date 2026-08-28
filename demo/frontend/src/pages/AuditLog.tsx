import { useState, useEffect } from 'react';
import { ScrollText, Shield, CheckCircle, AlertTriangle, Link, User, Cpu, Bot } from 'lucide-react';
import { api } from '../api';
import type { AuditEntry, AuditLogResponse } from '../types';

export default function AuditLog() {
  const [auditData, setAuditData] = useState<AuditLogResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAuditLog();
  }, []);

  const loadAuditLog = async () => {
    try {
      const res = await api.getAuditLog(30);
      setAuditData(res);
    } catch (e) {
      console.error('Failed to load audit log:', e);
    } finally {
      setLoading(false);
    }
  };

  const eventTypeBadge = (eventType: string) => {
    const config: Record<string, { label: string; className: string }> = {
      STATE_TRANSITION: { label: 'State Transition', className: 'badge-info' },
      SOLVER_RUN: { label: 'Solver Run', className: 'badge-info' },
      APPROVAL_DECISION: { label: 'Approval', className: 'badge-success' },
      SAP_WRITEBACK: { label: 'SAP Writeback', className: 'badge-success' },
      WRITEBACK_FAILURE: { label: 'Writeback Failed', className: 'badge-danger' },
      POLICY_RETRIEVAL: { label: 'Policy Retrieval', className: 'badge-policy' },
    };
    const cfg = config[eventType] || { label: eventType, className: 'badge-info' };
    return <span className={`badge ${cfg.className}`}>{cfg.label}</span>;
  };

  const actorIcon = (actorType: string) => {
    switch (actorType) {
      case 'SYSTEM':
        return <Cpu size={14} color="var(--text-tertiary)" />;
      case 'AGENT':
        return <Bot size={14} color="var(--accent-ice)" />;
      case 'HUMAN':
        return <User size={14} color="var(--stable)" />;
      default:
        return <User size={14} />;
    }
  };

  const formatPayload = (entry: AuditEntry) => {
    const p = entry.payload;
    if (entry.event_type === 'STATE_TRANSITION') {
      return (
        <span>
          {p.previous_state} → <strong style={{ color: 'var(--accent-ice)' }}>{p.new_state}</strong>
        </span>
      );
    }
    if (entry.event_type === 'APPROVAL_DECISION') {
      return (
        <span>
          Decision: <strong style={{ color: p.approval_decision === 'approved' ? 'var(--stable)' : 'var(--critical)' }}>
            {p.approval_decision}
          </strong>
        </span>
      );
    }
    if (entry.event_type === 'SOLVER_RUN') {
      return (
        <span>
          Version: <span className="mono">{p.solver_version}</span>
          {p.policy_weights && (
            <span style={{ marginLeft: 8, color: 'var(--text-tertiary)' }}>
              w={p.policy_weights.w1}/{p.policy_weights.w2}/{p.policy_weights.w3}
            </span>
          )}
        </span>
      );
    }
    if (entry.event_type === 'SAP_WRITEBACK') {
      return (
        <span>
          Response codes: {p.sap_response_codes?.join(', ')}
        </span>
      );
    }
    return null;
  };

  return (
    <div>
      <div className="page-header">
        <h2>Audit Log</h2>
        <p>Immutable hash-chained record for 21 CFR Part 11 compliance</p>
      </div>

      {/* Chain Status */}
      {auditData && (
        <div
          style={{
            display: 'flex',
            gap: 24,
            alignItems: 'center',
            marginBottom: 24,
            padding: '12px 20px',
            background: auditData.chain_valid ? 'var(--stable-dim)' : 'var(--critical-dim)',
            border: `1px solid ${auditData.chain_valid ? 'rgba(61,139,122,0.25)' : 'var(--critical-border)'}`,
            borderRadius: 'var(--radius-md)',
          }}
        >
          <Shield size={18} color={auditData.chain_valid ? 'var(--stable)' : 'var(--critical)'} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: auditData.chain_valid ? 'var(--stable)' : 'var(--critical)' }}>
              {auditData.chain_valid ? 'Chain Integrity Verified' : 'Chain Integrity Compromised'}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
              {auditData.chain_length} records · Tip: <span className="mono">{auditData.chain_tip}</span>
            </div>
          </div>
        </div>
      )}

      {/* Audit Entries */}
      <div className="card">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <div className="spinner" style={{ margin: '0 auto 12px' }} />
            <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>Loading audit log...</div>
          </div>
        ) : !auditData || auditData.entries.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <ScrollText size={48} color="var(--text-tertiary)" style={{ marginBottom: 16 }} />
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
              No Audit Records
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
              Audit records are created automatically when state transitions, solver runs, and approvals occur.
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Event</th>
                  <th>Actor</th>
                  <th>Details</th>
                  <th>Plan</th>
                  <th>Hash</th>
                  <th>Prev</th>
                </tr>
              </thead>
              <tbody>
                {auditData.entries.map((entry) => (
                  <tr key={entry.record_id}>
                    <td>
                      <span style={{ fontSize: 11, color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
                        {new Date(entry.timestamp).toLocaleTimeString()}
                      </span>
                    </td>
                    <td>{eventTypeBadge(entry.event_type)}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        {actorIcon(entry.actor_type)}
                        <span className="mono" style={{ fontSize: 11 }}>
                          {entry.actor_id.split('@')[0]}
                        </span>
                      </div>
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      {formatPayload(entry)}
                    </td>
                    <td>
                      {entry.allocation_plan_id ? (
                        <span className="mono" style={{ fontSize: 10 }}>
                          {entry.allocation_plan_id.slice(0, 8)}...
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-tertiary)' }}>—</span>
                      )}
                    </td>
                    <td>
                      <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                        {entry.record_hash}
                      </span>
                    </td>
                    <td>
                      <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                        {entry.prev_hash}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
