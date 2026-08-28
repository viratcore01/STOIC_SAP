/**
 * OverrideEditor — Manual allocation override editor.
 *
 * Design System: Dark Mode (OLED) — Enterprise Gateway pattern
 *
 * Allows the Operations Manager to modify the proposed allocation.
 * All modifications are re-validated against hard constraints (C1-C3)
 * before submission is permitted.
 *
 * Key constraint: The scoring rationale (P_i computation, SOP citations)
 * is non-editable — only the allocation decisions can be modified.
 */

import React, { useState } from "react";

interface Assignment {
  site_id: string;
  allocated_units: number;
  vehicle_id: string;
  priority_score: number;
  payload_mass_kg: number;
}

interface OverrideEditorProps {
  originalAssignments: Assignment[];
  onSubmit: (modifications: Assignment[]) => void;
  onCancel: () => void;
}

/* Inline styles using design tokens */
const styles = {
  container: {
    padding: "28px",
    fontFamily: "'Source Sans 3', system-ui, sans-serif",
    background: "#0F172A",
    borderRadius: "12px",
    border: "1px solid #1E293B",
    maxWidth: "960px",
  } as React.CSSProperties,
  title: {
    fontFamily: "'Lexend', system-ui, sans-serif",
    fontSize: "18px",
    fontWeight: 600,
    color: "#F8FAFC",
    marginBottom: "8px",
    display: "flex",
    alignItems: "center",
    gap: "8px",
  } as React.CSSProperties,
  subtitle: {
    fontSize: "13px",
    color: "#94A3B8",
    marginBottom: "20px",
    lineHeight: 1.5,
  } as React.CSSProperties,
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "13px",
    marginBottom: "20px",
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
  input: {
    width: "80px",
    padding: "8px 10px",
    background: "#020617",
    border: "1px solid #334155",
    borderRadius: "6px",
    color: "#F8FAFC",
    fontFamily: "'Source Sans 3', system-ui, sans-serif",
    fontSize: "13px",
    outline: "none",
    transition: "border-color 150ms ease, box-shadow 150ms ease",
    minHeight: "36px",
  } as React.CSSProperties,
  inputFocus: {
    borderColor: "#22C55E",
    boxShadow: "0 0 0 2px rgba(34, 197, 94, 0.15)",
  } as React.CSSProperties,
  errorText: {
    color: "#EF4444",
    fontSize: "11px",
    marginTop: "4px",
  } as React.CSSProperties,
  readOnly: {
    fontFamily: "'Lexend', monospace",
    fontSize: "12px",
    color: "#64748B",
  } as React.CSSProperties,
  actions: {
    display: "flex",
    gap: "10px",
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

export const OverrideEditor: React.FC<OverrideEditorProps> = ({
  originalAssignments,
  onSubmit,
  onCancel,
}) => {
  const [edits, setEdits] = useState<Assignment[]>(
    originalAssignments.map((a) => ({ ...a }))
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [focusedField, setFocusedField] = useState<string | null>(null);

  const updateAssignment = (
    siteId: string,
    field: keyof Assignment,
    value: string | number
  ) => {
    setEdits((prev) =>
      prev.map((a) => (a.site_id === siteId ? { ...a, [field]: value } : a))
    );
    setErrors((prev) => {
      const next = { ...prev };
      delete next[`${siteId}.${field}`];
      return next;
    });
  };

  const validateOverrides = (): boolean => {
    const newErrors: Record<string, string> = {};
    let isValid = true;

    for (const edit of edits) {
      if (edit.allocated_units < 0) {
        newErrors[`${edit.site_id}.allocated_units`] = "Units cannot be negative";
        isValid = false;
      }
      if (!edit.vehicle_id) {
        newErrors[`${edit.site_id}.vehicle_id`] = "Vehicle is required";
        isValid = false;
      }
    }

    setErrors(newErrors);
    return isValid;
  };

  const handleSubmit = () => {
    if (validateOverrides()) {
      onSubmit(edits);
    }
  };

  const getInputStyle = (fieldKey: string): React.CSSProperties => ({
    ...styles.input,
    ...(focusedField === fieldKey ? styles.inputFocus : {}),
    borderColor: errors[fieldKey] ? "#EF4444" : styles.input.borderColor,
  });

  return (
    <div style={styles.container}>
      {/* Title */}
      <div style={styles.title}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#F8FAFC" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
          <path d="m15 5 4 4" />
        </svg>
        Modify Allocation
      </div>
      <p style={styles.subtitle}>
        Modify allocation quantities below. Changes will be re-validated against
        thermal (C1), capacity (C2), and reachability (C3) constraints before submission.
      </p>

      {/* Allocation Table */}
      <div style={{ overflowX: "auto", marginBottom: "4px" }}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Site</th>
              <th style={styles.th}>Units</th>
              <th style={styles.th}>Vehicle</th>
              <th style={styles.th}>Priority (P_i)</th>
            </tr>
          </thead>
          <tbody>
            {edits.map((edit) => {
              const unitKey = `${edit.site_id}.allocated_units`;
              const vehicleKey = `${edit.site_id}.vehicle_id`;
              return (
                <tr key={edit.site_id}>
                  <td style={styles.td}>
                    <span style={{ fontFamily: "'Lexend', monospace", fontWeight: 500, fontSize: "13px" }}>
                      {edit.site_id}
                    </span>
                  </td>
                  <td style={styles.td}>
                    <div>
                      <input
                        type="number"
                        value={edit.allocated_units}
                        onChange={(e) =>
                          updateAssignment(edit.site_id, "allocated_units", parseInt(e.target.value) || 0)
                        }
                        onFocus={() => setFocusedField(unitKey)}
                        onBlur={() => setFocusedField(null)}
                        style={getInputStyle(unitKey)}
                        aria-label={`Allocated units for ${edit.site_id}`}
                        aria-invalid={!!errors[unitKey]}
                      />
                      {errors[unitKey] && (
                        <div style={styles.errorText} role="alert">
                          {errors[unitKey]}
                        </div>
                      )}
                    </div>
                  </td>
                  <td style={styles.td}>
                    <div>
                      <input
                        type="text"
                        value={edit.vehicle_id}
                        onChange={(e) =>
                          updateAssignment(edit.site_id, "vehicle_id", e.target.value)
                        }
                        onFocus={() => setFocusedField(vehicleKey)}
                        onBlur={() => setFocusedField(null)}
                        style={{ ...getInputStyle(vehicleKey), width: "120px" }}
                        aria-label={`Vehicle for ${edit.site_id}`}
                        aria-invalid={!!errors[vehicleKey]}
                        placeholder="e.g. V1"
                      />
                      {errors[vehicleKey] && (
                        <div style={styles.errorText} role="alert">
                          {errors[vehicleKey]}
                        </div>
                      )}
                    </div>
                  </td>
                  <td style={styles.td}>
                    <span style={styles.readOnly} title="P_i is read-only to preserve audit trail integrity">
                      {edit.priority_score.toFixed(3)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Constraint validation note */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "10px 14px",
          marginBottom: "20px",
          background: "rgba(59, 130, 246, 0.06)",
          border: "1px solid rgba(59, 130, 246, 0.2)",
          borderRadius: "8px",
          fontSize: "12px",
          color: "#94A3B8",
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4" />
          <path d="M12 8h.01" />
        </svg>
        Priority scores (P_i) are read-only. All modifications will be re-validated against C1 (thermal), C2 (capacity), and C3 (reachability) constraints.
      </div>

      {/* Action Buttons */}
      <div style={styles.actions}>
        <button
          onClick={handleSubmit}
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
          aria-label="Submit modified allocation"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <path d="m9 11 3 3L22 4" />
          </svg>
          Submit Modified Allocation
        </button>

        <button
          onClick={onCancel}
          style={{
            ...styles.btn,
            background: "#1E293B",
            color: "#CBD5E1",
            border: "1px solid #334155",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "#334155";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "#1E293B";
          }}
          aria-label="Cancel modification"
        >
          Cancel
        </button>
      </div>
    </div>
  );
};
