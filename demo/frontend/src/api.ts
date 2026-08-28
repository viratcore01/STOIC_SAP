const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // State
  getState: () => request<any>('/state'),

  // Disruption
  triggerDisruption: (disruptionId: string = 'D-001') =>
    fetch(`${BASE}/disruption/trigger?disruption_id=${disruptionId}`, { method: 'POST' }).then((r) => r.json()),

  // Allocation
  runAllocation: (w1 = 0.4, w2 = 0.3, w3 = 0.3) =>
    request<any>(`/allocation/run?w1=${w1}&w2=${w2}&w3=${w3}`, { method: 'POST' }),

  getProposedAllocation: () => request<any>('/allocation/proposed'),

  approveAllocation: (approverId: string = 'ops-manager@demo') =>
    request<any>(`/allocation/approve?approver_id=${approverId}`, { method: 'POST' }),

  rejectAllocation: (approverId: string = 'ops-manager@demo') =>
    request<any>(`/allocation/reject?approver_id=${approverId}`, { method: 'POST' }),

  modifyAllocation: (modifications: any[], approverId: string = 'ops-manager@demo') =>
    request<any>(`/allocation/modify?approver_id=${approverId}`, {
      method: 'POST',
      body: JSON.stringify(modifications),
    }),

  // Audit
  getAuditLog: (limit = 20) => request<any>(`/audit/log?limit=${limit}`),

  // History
  getAllocationHistory: () => request<any>('/allocation/history'),

  // Disruptions
  getDisruptions: () => request<any>('/disruptions'),

  // Settings
  getSettings: () => request<any>('/settings'),

  // Reset
  reset: () => request<any>('/reset', { method: 'POST' }),
};
