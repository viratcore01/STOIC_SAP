import { useState, useEffect } from 'react';
import {
  Server,
  Activity,
  Database,
  Sliders,
} from 'lucide-react';
import { api } from '../api';
import type { Settings as SettingsType } from '../types';

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const res = await api.getSettings();
      setSettings(res);
    } catch (e) {
      console.error('Failed to load settings:', e);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h2>System Settings</h2>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: 40 }}>
          <div className="spinner" style={{ margin: '0 auto 12px' }} />
          <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>Loading settings...</div>
        </div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div>
        <div className="page-header">
          <h2>System Settings</h2>
        </div>
        <div className="card">
          <div style={{ color: 'var(--text-tertiary)', textAlign: 'center', padding: 40 }}>
            Failed to load settings.
          </div>
        </div>
      </div>
    );
  }

  const healthColor = (status: string) =>
    status === 'healthy' ? 'var(--stable)' : status === 'mock' ? 'var(--warning)' : 'var(--critical)';

  return (
    <div>
      <div className="page-header">
        <h2>System Settings</h2>
        <p>Configuration and system health</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* State Machine Thresholds */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Sliders size={16} />
              State Machine Thresholds
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--bg-deep)', borderRadius: 6 }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>S2 → S3 Threshold</span>
              <span className="mono" style={{ fontSize: 14, fontWeight: 600, color: 'var(--warning)' }}>
                {settings.state_machine_thresholds.s2_s3_capacity_margin}%
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--bg-deep)', borderRadius: 6 }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>S3 → S4 Threshold</span>
              <span className="mono" style={{ fontSize: 14, fontWeight: 600, color: 'var(--critical)' }}>
                {settings.state_machine_thresholds.s3_s4_capacity_margin}%
              </span>
            </div>
          </div>
        </div>

        {/* Solver Config */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Server size={16} />
              Solver Configuration
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--bg-deep)', borderRadius: 6 }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Handling Buffer</span>
              <span className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
                {settings.solver_config.handling_buffer_hours}h
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--bg-deep)', borderRadius: 6 }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Time Limit</span>
              <span className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
                {settings.solver_config.time_limit_seconds}s
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--bg-deep)', borderRadius: 6 }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Policy Weights</span>
              <span className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
                {settings.policy_weights.w1}/{settings.policy_weights.w2}/{settings.policy_weights.w3}
              </span>
            </div>
          </div>
        </div>

        {/* SAP Destinations */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Database size={16} />
              SAP Destinations
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {Object.entries(settings.sap_destinations).map(([name, dest]) => (
              <div key={name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--bg-deep)', borderRadius: 6 }}>
                <div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500, textTransform: 'uppercase' }}>
                    {name.replace('_', ' ')}
                  </div>
                  <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                    {dest.url}
                  </div>
                </div>
                <span className={`badge badge-${dest.status === 'mock' ? 'warning' : 'success'}`}>
                  {dest.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Agent Health */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Activity size={16} />
              Agent Health
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {Object.entries(settings.agent_health).map(([agent, status]) => (
              <div key={agent} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--bg-deep)', borderRadius: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: healthColor(status),
                    }}
                  />
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    {agent.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                  </span>
                </div>
                <span className={`badge badge-${status === 'healthy' ? 'success' : status === 'mock' ? 'warning' : 'danger'}`}>
                  {status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
