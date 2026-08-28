import { useState, useEffect, useCallback } from 'react';
import {
  LayoutDashboard,
  ShieldCheck,
  History,
  ScrollText,
  Settings,
  Activity,
  AlertTriangle,
  AlertCircle,
  XOctagon,
  Siren,
} from 'lucide-react';
import { api } from './api';
import type { SystemState } from './types';
import Dashboard from './pages/Dashboard';
import Approvals from './pages/Approvals';
import Allocations from './pages/Allocations';
import AuditLog from './pages/AuditLog';
import SettingsPage from './pages/Settings';
import './App.css';

type Page = 'dashboard' | 'approvals' | 'allocations' | 'audit' | 'settings';

interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error';
}

let toastId = 0;

function App() {
  const [page, setPage] = useState<Page>('dashboard');
  const [systemState, setSystemState] = useState<SystemState | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: 'success' | 'error' = 'success') => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const refreshState = useCallback(async () => {
    try {
      const state = await api.getState();
      setSystemState(state);
    } catch (e) {
      console.error('Failed to fetch state:', e);
    }
  }, []);

  useEffect(() => {
    refreshState();
    const interval = setInterval(refreshState, 5000);
    return () => clearInterval(interval);
  }, [refreshState]);

  const stateLabel: Record<string, { label: string; color: string; Icon: typeof Activity }> = {
    S1_STABLE: { label: 'S1 Stable', color: '#3D8B7A', Icon: ShieldCheck },
    S2_ABSORBING_DISRUPTION: { label: 'S2 Absorbing', color: '#D4A017', Icon: AlertTriangle },
    S3_RECOVERY_CONSTRAINED: { label: 'S3 Constrained', color: '#E07B2F', Icon: AlertCircle },
    S4_RECOVERY_INSUFFICIENT: { label: 'S4 Insufficient', color: '#C23B3B', Icon: XOctagon },
    S5_SCARCITY_ALLOCATION: { label: 'S5 Scarcity', color: '#A52020', Icon: Siren },
  };

  const currentState = systemState?.resilience_state || 'S1_STABLE';
  const stateInfo = stateLabel[currentState] || stateLabel.S1_STABLE;
  const hasPending = systemState?.has_proposed_allocation;

  const navItems: { id: Page; label: string; Icon: typeof LayoutDashboard; badge?: number }[] = [
    { id: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard },
    { id: 'approvals', label: 'Approvals', Icon: ShieldCheck, badge: hasPending ? 1 : undefined },
    { id: 'allocations', label: 'Allocations', Icon: History },
    { id: 'audit', label: 'Audit Log', Icon: ScrollText },
    { id: 'settings', label: 'Settings', Icon: Settings },
  ];

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <Activity size={20} color={stateInfo.color} />
            <div>
              <h1>CCRO</h1>
              <span>Cold Sentinel</span>
            </div>
          </div>
          <div
            style={{
              marginTop: 12,
              padding: '6px 10px',
              borderRadius: 6,
              background: `${stateInfo.color}15`,
              border: `1px solid ${stateInfo.color}30`,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <div
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: stateInfo.color,
              }}
            />
            <span style={{ fontSize: 11, fontWeight: 600, color: stateInfo.color }}>
              {stateInfo.label}
            </span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {navItems.map(({ id, label, Icon, badge }) => (
            <button
              key={id}
              className={`nav-item ${page === id ? 'active' : ''}`}
              onClick={() => setPage(id)}
            >
              <Icon size={16} />
              <span className="nav-label">{label}</span>
              {badge !== undefined && <span className="nav-badge">{badge}</span>}
            </button>
          ))}
        </nav>

        <div style={{ padding: '16px', borderTop: '1px solid var(--border-subtle)' }}>
          <button
            className="btn btn-ghost btn-sm"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={async () => {
              await api.reset();
              await refreshState();
              addToast('Demo reset to initial state');
              setPage('dashboard');
            }}
          >
            Reset Demo
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        {page === 'dashboard' && (
          <Dashboard state={systemState} onRefresh={refreshState} addToast={addToast} />
        )}
        {page === 'approvals' && (
          <Approvals state={systemState} onRefresh={refreshState} addToast={addToast} />
        )}
        {page === 'allocations' && <Allocations addToast={addToast} />}
        {page === 'audit' && <AuditLog />}
        {page === 'settings' && <SettingsPage />}
      </main>

      {/* Toasts */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>
            {t.type === 'success' ? (
              <ShieldCheck size={16} color="#3D8B7A" />
            ) : (
              <AlertTriangle size={16} color="#C23B3B" />
            )}
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
