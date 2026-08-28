/**
 * ApprovalCard — Human-in-the-loop approval interface.
 *
 * Design System: Dark Mode (OLED) — Enterprise Gateway pattern
 *
 * Renders side-by-side comparison:
 *   - Do Nothing / Standard Route (counterfactual)
 *   - CCRO Policy Allocation (AI-recommended)
 *
 * Key governance constraints:
 * - Scoring rationale is non-editable (preserves audit trail integrity)
 * - Manual overrides are re-validated against C1-C3 constraints
 */

import React, { useState } from "react";

interface Assignment {
  site_id: string;
  allocated_units: number;
  vehicle_id: string;
  priority_score: number;
  payload_mass_kg: number;
}

interface DroppedSite {
  site_id: string;
  reason: string;
  priority_score: number;
}

interface SOPClause {
  clause_id: string;
  source_doc: string;
  similarity_score: number;
  text_excerpt: string;
}

interface ApprovalCardProps {
  planId: string;
  assignments: Assignment[];
  droppedSites: DroppedSite[];
  policyWeights: {
    w1: number;
    w2: number;
    w3: number;
    cited_clauses: SOPClause[];
    confidence_score: number;
  };
  onApprove: (planId: string) => void;
  onReject: (planId: string) => void;
  onModify: (planId: string, modifications: Assignment[]) => void;
}

/* Lucide-style SVG icons */
const icons = {
  checkCircle: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <path d="m9 11 3 3L22 4" />
    </svg>
  ),
  xCircle: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="m15 9-6 6" />
      <path d="m9 9 6 6" />
    </svg>
  ),
  alertTriangle: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  ),
  fileText: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" x2="8" y1="13" y2="13" />
      <line x1="16" x2="8" y1="17" y2="17" />
    </svg>
  ),
  edit: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      <path d="m15 5 4 4" />
    </svg>
  ),
};

/* Inline styles using design tokens */
const styles = {
  card: {
    padding: "28px",
    fontFamily: "'Source Sans 3', system-ui, sans-serif",
    maxWidth: "960px",
    background: "#0F172A",
    borderRadius: "12px",
    border: "1px solid #1E293B",
  } as React.CSSProperties,
  title: {
    fontFamily: "'Lexend', system-ui, sans-serif",
    fontSize: "18px",
    fontWeight: 600,
    color: "#F8FAFC",
    marginBottom: "20px",
    display: "flex",
    alignItems: "center",
    gap: "8px",
  } as React.CSSProperties,
  compareGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "16px",
    marginBottom: "24px",
  } as React.CSSProperties,
  compareCard: {
    padding: "18px",
    borderRadius: "10px",
    border: "1px solid #1E293B",
    background: "#020617",
  } as React.CSSProperties,
  compareCardActive: {
    padding: "18px",
    borderRadius: "10px",
    border: "2px solid #22C55E",
    background: "rgba(34, 197, 94, 0.05)",
  } as React.CSSProperties,
  compareTitle: {
    fontFamily: "'Lexend', system-ui, sans-serif",
    fontSize: "14px",
    fontWeight: 600,
    marginBottom: "8px",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,
  compareText: {
    fontSize: "13px",
    color: "#94A3B8",
    lineHeight: 1.5,
  } as React.CSSProperties,
  sectionTitle: {
    fontFamily: "'Lexend', system-ui, sans-serif",
    fontSize: "14px",
    fontWeight: 600,
    color: "#CBD5E1",
    marginBottom: "10px",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "13px",
  } as React.CSSProperties,
  th: {
    textAlign: "left" as const,
    padding: "10px 12px",
    fontFamily: "'Lexend', system-ui, sans-serif",
    fontSize: "11px",
    fontWeight: 500,
    letterSpacing: "0.05em",
    textTransform: "uppercase" as const,
    color: "#64748B",
    borderBottom: "1px solid #1E293B",
  } as React.CSSProperties,
  td: {
    padding: "10px 12px",
    color: "#CBD5E1",
    borderBottom: "1px solid rgba(30, 41, 59, 0.5)",
  } as React.CSSProperties,
  droppedPanel: {
    marginBottom: "24px",
    padding: "16px 18px",
    borderRadius: "10px",
    border: "1px solid rgba(239, 68, 68, 0.25)",
    background: "rgba(239, 68, 68, 0.06)",
  } as React.CSSProperties,
  droppedTitle: {
    fontFamily: "'Lexend', system-ui, sans-serif",
    fontSize: "14px",
    fontWeight: 600,
    marginBottom: "10px",
    color: "#EF4444",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,
  policyPanel: {
    marginBottom: "24px",
    padding: "18px",
    borderRadius: "10px",
    border: "1px solid #1E293B",
    background: "#020617",
  } as React.CSSProperties,
  weightRow: {
    display: "flex",
    gap: "16px",
    marginBottom: "14px",
    flexWrap: "wrap" as const,
  } as React.CSSProperties,
  weight: {
    fontSize: "13px",
    color: "#CBD5E1",
  } as React.CSSProperties,
  clauseItem: {
    fontSize: "12px",
    color: "#94A3B8",
    marginBottom: "6px",
    paddingLeft: "14px",
    display: "flex",
    alignItems: "flex-start",
    gap: "6px",
    lineHeight: 1.5,
  } as React.CSSProperties,
  actions: {
    display: "flex",
    gap: "10px",
    flexWrap: "wrap" as const,
  } as React.CSSProperties,
  btn: {
    fontFamily: "'Lexend', system-ui, sans-serif",
    fontWeight: 500,
    fontSize: "14px",
    padding: "12px 22px",
    borderRadius: "8px",
    border: "none",
    cursor: "pointer",
    transition: "all 150ms ease",
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    minHeight: "44px",
  } as React.CSSProperties,
};

export const ApprovalCard: React.FC<ApprovalCardProps> = ({
  planId,
  assignments,
  droppedSites,
  policyWeights,
  onApprove,
  onReject,
  onModify,
}) => {
  const [modifications, setModifications] = useState<Assignment[]>([]);
  const [isEditing, setIsEditing] = useState(false);

  const totalFulfillment = assignments.reduce(
    (s, a) => s + a.priority_score * a.allocated_units,
    0
  );

  return (
    <div style={styles.card}>
      {/* Title */}
      <div style={styles.title}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#F8FAFC" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        Allocation Approval Card
      </div>

      {/* Side-by-side comparison */}
      <div style={styles.compareGrid}>
        {/* Do Nothing / Standard Route */}
        <div style={styles.compareCard}>
          <div style={{ ...styles.compareTitle, color: "#64748B" }}>
            {icons.xCircle}
            Do Nothing / Standard Route
          </div>
          <p style={styles.compareText}>
            Standard cost-minimization TMS routing. No policy-weighted allocation.{" "}
            {droppedSites.length} sites may lose inventory due to thermal expiry.
          </p>
        </div>

        {/* CCRO Policy Allocation */}
        <div style={styles.compareCardActive}>
          <div style={{ ...styles.compareTitle, color: "#22C55E" }}>
            {icons.checkCircle}
            CCRO Policy Allocation
          </div>
          <p style={styles.compareText}>
            Priority-weighted allocation. {assignments.length} sites covered. Objective value:{" "}
            <strong style={{ color: "#F8FAFC" }}>{totalFulfillment.toFixed(2)}</strong>
          </p>
        </div>
      </div>

      {/* Proposed Allocation Table */}
      <div style={{ marginBottom: "24px" }}>
        <div style={styles.sectionTitle}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#CBD5E1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2" />
            <path d="M3 9h18" />
            <path d="M3 15h18" />
            <path d="M9 3v18" />
          </svg>
          Proposed Allocation
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Site</th>
                <th style={styles.th}>Units</th>
                <th style={styles.th}>Vehicle</th>
                <th style={styles.th}>Priority (P_i)</th>
                <th style={styles.th}>Mass (kg)</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((a) => (
                <tr key={a.site_id}>
                  <td style={styles.td}>
                    <span style={{ fontFamily: "'Lexend', monospace", fontWeight: 500 }}>
                      {a.site_id}
                    </span>
                  </td>
                  <td style={styles.td}>{a.allocated_units}</td>
                  <td style={{ ...styles.td, fontFamily: "'Source Sans 3', monospace", fontSize: "12px" }}>
                    {a.vehicle_id}
                  </td>
                  <td style={styles.td}>
                    <span
                      style={{
                        color: a.priority_score > 0.6 ? "#22C55E" : a.priority_score > 0.3 ? "#F59E0B" : "#94A3B8",
                        fontWeight: 500,
                      }}
                    >
                      {a.priority_score.toFixed(3)}
                    </span>
                  </td>
                  <td style={styles.td}>{a.payload_mass_kg.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Dropped Sites Panel */}
      {droppedSites.length > 0 && (
        <div style={styles.droppedPanel}>
          <div style={styles.droppedTitle}>
            {icons.alertTriangle}
            Dropped Sites ({droppedSites.length})
          </div>
          {droppedSites.map((ds) => (
            <div
              key={ds.site_id}
              style={{ fontSize: "13px", color: "#FCA5A5", marginBottom: "4px", paddingLeft: "22px" }}
            >
              <strong>{ds.site_id}</strong>: {ds.reason}
            </div>
          ))}
        </div>
      )}

      {/* Policy Justification Panel */}
      <div style={styles.policyPanel}>
        <div style={styles.sectionTitle}>
          {icons.fileText}
          Policy Justification
        </div>

        {/* Weight Breakdown */}
        <div style={styles.weightRow}>
          <span style={styles.weight}>
            <strong style={{ color: "#22C55E" }}>w1</strong> Clinical Urgency:{" "}
            <span style={{ fontFamily: "'Lexend', monospace" }}>{policyWeights.w1.toFixed(3)}</span>
          </span>
          <span style={styles.weight}>
            <strong style={{ color: "#3B82F6" }}>w2</strong> Operational Simplicity:{" "}
            <span style={{ fontFamily: "'Lexend', monospace" }}>{policyWeights.w2.toFixed(3)}</span>
          </span>
          <span style={styles.weight}>
            <strong style={{ color: "#A855F7" }}>w3</strong> Value Preservation:{" "}
            <span style={{ fontFamily: "'Lexend', monospace" }}>{policyWeights.w3.toFixed(3)}</span>
          </span>
          <span style={{ ...styles.weight, color: "#64748B" }}>
            Confidence: {(policyWeights.confidence_score * 100).toFixed(1)}%
          </span>
        </div>

        {/* SOP Clauses */}
        <div>
          <div style={{ fontSize: "12px", fontWeight: 600, color: "#64748B", marginBottom: "6px", fontFamily: "'Lexend', sans-serif", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Cited SOP Clauses
          </div>
          {policyWeights.cited_clauses.map((clause) => (
            <div key={clause.clause_id} style={styles.clauseItem}>
              <span style={{ flexShrink: 0, color: "#64748B" }}>{icons.fileText}</span>
              <span>
                <strong style={{ color: "#CBD5E1" }}>{clause.source_doc}</strong>{" "}
                &sect;{clause.clause_id} —{" "}
                <em style={{ color: "#94A3B8" }}>{clause.text_excerpt}</em>{" "}
                <span style={{ color: "#64748B", fontSize: "11px" }}>
                  ({(clause.similarity_score * 100).toFixed(0)}% match)
                </span>
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Action Buttons */}
      <div style={styles.actions}>
        <button
          onClick={() => onApprove(planId)}
          style={{
            ...styles.btn,
            background: "#22C55E",
            color: "#000",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "#16A34A";
            e.currentTarget.style.boxShadow = "0 0 20px rgba(34, 197, 94, 0.15)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "#22C55E";
            e.currentTarget.style.boxShadow = "none";
          }}
          aria-label="Approve allocation as-is"
        >
          {icons.checkCircle}
          Approve as-is
        </button>

        <button
          onClick={() => setIsEditing(!isEditing)}
          style={{
            ...styles.btn,
            background: "#1E293B",
            color: "#F8FAFC",
            border: "1px solid #334155",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "#334155";
            e.currentTarget.style.borderColor = "#475569";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "#1E293B";
            e.currentTarget.style.borderColor = "#334155";
          }}
          aria-label="Modify allocation before approving"
        >
          {icons.edit}
          Modify &amp; Approve
        </button>

        <button
          onClick={() => onReject(planId)}
          style={{
            ...styles.btn,
            background: "rgba(239, 68, 68, 0.1)",
            color: "#EF4444",
            border: "1px solid rgba(239, 68, 68, 0.25)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(239, 68, 68, 0.2)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "rgba(239, 68, 68, 0.1)";
          }}
          aria-label="Reject allocation"
        >
          {icons.xCircle}
          Reject
        </button>
      </div>
    </div>
  );
};
