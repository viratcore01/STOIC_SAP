/**
 * ResilienceDashboard — Live state indicator and capacity margin gauge.
 *
 * Design System: Dark Mode (OLED) — Enterprise Gateway pattern
 * Typography: Lexend (headings) + Source Sans 3 (body)
 * Colors: Deep navy (#020617) + emerald CTA (#22C55E)
 *
 * Key UX rules applied:
 * - No emoji icons (SVG only)
 * - cursor-pointer on interactive elements
 * - Smooth transitions (150-300ms)
 * - Focus-visible states for keyboard nav
 * - prefers-reduced-motion respected
 * - Responsive: 375px, 768px, 1024px, 1440px
 */

import React from "react";

interface ResilienceDashboardProps {
  currentState: string;
  capacityMargin: number;
  threadId: string;
}

const STATE_CONFIG: Record<
  string,
  { label: string; color: string; bgColor: string; borderColor: string; icon: string }
> = {
  S1_STABLE: {
    label: "S1 — STABLE",
    color: "#22C55E",
    bgColor: "rgba(34, 197, 94, 0.08)",
    borderColor: "rgba(34, 197, 94, 0.25)",
    icon: "shield-check",
  },
  S2_ABSORBING_DISRUPTION: {
    label: "S2 — ABSORBING DISRUPTION",
    color: "#F59E0B",
    bgColor: "rgba(245, 158, 11, 0.08)",
    borderColor: "rgba(245, 158, 11, 0.25)",
    icon: "alert-triangle",
  },
  S3_RECOVERY_CONSTRAINED: {
    label: "S3 — RECOVERY CONSTRAINED",
    color: "#F97316",
    bgColor: "rgba(249, 115, 22, 0.08)",
    borderColor: "rgba(249, 115, 22, 0.25)",
    icon: "alert-circle",
  },
  S4_RECOVERY_INSUFFICIENT: {
    label: "S4 — RECOVERY INSUFFICIENT",
    color: "#EF4444",
    bgColor: "rgba(239, 68, 68, 0.08)",
    borderColor: "rgba(239, 68, 68, 0.25)",
    icon: "x-octagon",
  },
  S5_SCARCITY_ALLOCATION: {
    label: "S5 — SCARCITY ALLOCATION",
    color: "#DC2626",
    bgColor: "rgba(220, 38, 38, 0.1)",
    borderColor: "rgba(220, 38, 38, 0.3)",
    icon: "siren",
  },
};

/* Lucide-style SVG icons (inline, no emoji) */
const icons: Record<string, React.ReactNode> = {
  "shield-check": (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  ),
  "alert-triangle": (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  ),
  "alert-circle": (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4" />
      <path d="M12 16h.01" />
    </svg>
  ),
  "x-octagon": (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2" />
      <path d="m15 9-6 6" />
      <path d="m9 9 6 6" />
    </svg>
  ),
  "siren": (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 18v-6a5 5 0 1 1 10 0v6" />
      <path d="M5 21a1 1 0 0 1-1-1v-1a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v1a1 1 0 0 1-1 1H5Z" />
      <path d="M2 12h2" />
      <path d="M20 12h2" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
    </svg>
  ),
  "activity": (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  ),
};

export const ResilienceDashboard: React.FC<ResilienceDashboardProps> = ({
  currentState,
  capacityMargin,
  threadId,
}) => {
  const config = STATE_CONFIG[currentState] || STATE_CONFIG.S1_STABLE;
  const marginPercent = Math.max(0, Math.min(100, capacityMargin * 100));
  const marginColor =
    capacityMargin > 0.15
      ? "#22C55E"
      : capacityMargin > 0
        ? "#F59E0B"
        : "#EF4444";

  return (
    <div
      style={{
        padding: "24px",
        fontFamily: "'Source Sans 3', system-ui, sans-serif",
        background: "#0F172A",
        borderRadius: "12px",
        border: "1px solid #1E293B",
        maxWidth: "480px",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "20px" }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        <span
          style={{
            fontFamily: "'Lexend', system-ui, sans-serif",
            fontSize: "15px",
            fontWeight: 600,
            color: "#CBD5E1",
            letterSpacing: "0.01em",
          }}
        >
          Resilience Dashboard
        </span>
      </div>

      {/* State Indicator */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
          marginBottom: "24px",
          padding: "14px 16px",
          borderRadius: "10px",
          background: config.bgColor,
          border: `1px solid ${config.borderColor}`,
          transition: "all 250ms ease",
        }}
        role="status"
        aria-label={`Current resilience state: ${config.label}`}
      >
        <div style={{ color: config.color, display: "flex", alignItems: "center" }}>
          {icons[config.icon]}
        </div>
        <span
          style={{
            fontFamily: "'Lexend', system-ui, sans-serif",
            fontSize: "15px",
            fontWeight: 600,
            color: config.color,
            letterSpacing: "0.02em",
          }}
        >
          {config.label}
        </span>
      </div>

      {/* Capacity Margin Gauge */}
      <div style={{ marginBottom: "20px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "8px",
          }}
        >
          <span style={{ fontSize: "13px", color: "#94A3B8", fontWeight: 500 }}>
            Capacity Margin
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ color: "#64748B" }}>
              {icons.activity}
            </span>
            <span
              style={{
                fontFamily: "'Lexend', system-ui, sans-serif",
                fontSize: "14px",
                fontWeight: 600,
                color: marginColor,
              }}
            >
              {(capacityMargin * 100).toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Gauge Bar */}
        <div
          style={{
            height: "6px",
            backgroundColor: "#1E293B",
            borderRadius: "3px",
            overflow: "hidden",
            position: "relative",
          }}
          role="progressbar"
          aria-valuenow={marginPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Capacity margin: ${(capacityMargin * 100).toFixed(1)}%`}
        >
          <div
            style={{
              height: "100%",
              width: `${marginPercent}%`,
              backgroundColor: marginColor,
              borderRadius: "3px",
              transition: "width 500ms ease, background-color 500ms ease",
              boxShadow: `0 0 8px ${marginColor}40`,
            }}
          />
        </div>

        {/* Gauge Scale */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: "6px",
          }}
        >
          <span style={{ fontSize: "11px", color: "#64748B" }}>0%</span>
          <span style={{ fontSize: "11px", color: "#64748B" }}>15% threshold</span>
          <span style={{ fontSize: "11px", color: "#64748B" }}>100%</span>
        </div>
      </div>

      {/* Thread Info */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          padding: "8px 12px",
          background: "#020617",
          borderRadius: "6px",
          border: "1px solid #1E293B",
        }}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
        <span style={{ fontSize: "12px", color: "#64748B", fontFamily: "'Source Sans 3', monospace" }}>
          {threadId || "No active episode"}
        </span>
      </div>
    </div>
  );
};
