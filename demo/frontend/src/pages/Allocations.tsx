import { useState, useEffect } from 'react';
import { History, CheckCircle, XCircle, Clock } from 'lucide-react';
import { api } from '../api';
import type { AllocationHistoryEntry } from '../types';

interface Props {
  addToast: (msg: string, type?: 'success' | 'error') => void;
}

export default function Allocations({ addToast }: Props) {
  const [history, setHistory] = useState<AllocationHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const res = await api.getAllocationHistory();
      setHistory(res.history || []);
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const statusBadge = (status: string) => {
    switch (status) {
      case 'EXECUTED':
        return <span className="badge badge-success">Executed</span>;
      case 'REJECTED':
        return <span className="badge badge-danger">Rejected</span>;
      case 'PENDING':
        return <span className="badge badge-warning">Pending</span>;
      default:
        return <span className="badge badge-info">{status}</span>;
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2>Allocation History</h2>
        <p>Record of all allocation decisions and their outcomes</p>
      </div>

      <div className="card">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <div className="spinner" style={{ margin: '0 auto 12px' }} />
            <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>Loading history...</div>
          </div>
        ) : history.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <History size={48} color="var(--text-tertiary)" style={{ marginBottom: 16 }} />
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
              No Allocations Yet
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
              Run the scarcity allocation engine and submit a decision to see history here.
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Plan ID</th>
                  <th>Status</th>
                  <th>Disruption</th>
                  <th>Sites</th>
                  <th>Dropped</th>
                  <th>Objective</th>
                  <th>Weights</th>
                  <th>Approved By</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {history.map((entry) => (
                  <tr key={entry.plan_id}>
                    <td>
                      <span className="mono" style={{ color: 'var(--text-primary)' }}>
                        {entry.plan_id.slice(0, 10)}...
                      </span>
                    </td>
                    <td>{statusBadge(entry.status)}</td>
                    <td style={{ fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {entry.disruption || '—'}
                    </td>
                    <td className="mono">{entry.assignments_count}</td>
                    <td className="mono" style={{ color: entry.dropped_count > 0 ? 'var(--critical)' : 'var(--text-tertiary)' }}>
                      {entry.dropped_count}
                    </td>
                    <td className="mono">{entry.objective_value.toFixed(3)}</td>
                    <td>
                      <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                        {entry.policy_weights.w1}/{entry.policy_weights.w2}/{entry.policy_weights.w3}
                      </span>
                    </td>
                    <td>
                      <span className="mono" style={{ fontSize: 11 }}>
                        {entry.approved_by?.split('@')[0] || '—'}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                        {new Date(entry.approved_at).toLocaleTimeString()}
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
