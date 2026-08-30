import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api';
import {
  Globe,
  ShieldCheck,
  Truck,
  MapPin,
  Activity,
  CheckCircle,
  XCircle,
  RotateCw,
} from 'lucide-react';

interface Hub {
  id: string;
  name: string;
  coordinates: number[];
  capacity_kg: number;
  status: string;
}

interface Clinic {
  id: string;
  name: string;
  coordinates: number[];
  city: string;
  country: string;
  demand_units: number;
  criticality: string;
  vpi: number;
  remaining_shelf_life_hours: number;
  stock_coverage_pct: number;
  is_threatened: boolean;
  is_dropped: boolean;
  drop_reason?: string;
  priority_score: number;
  allocation_status?: string;
  allocated_vehicle?: string;
}

interface Route {
  id: string;
  vehicle_id: string;
  vehicle_type: string;
  origin: number[];
  destination: number[];
  transit_time_hours: number;
  distance_km: number;
  remaining_shelf_life_hours: number;
  arrhenius_decay_rate: number;
  ambient_temperature_celsius: number;
  is_feasible: boolean;
  route_status: string;
  route_color: string;
  feasibility_reason: string;
}

interface Disruption {
  id: string;
  name: string;
  type: string;
  severity: string;
  coordinates: number[];
  affected_sites: string[];
  description: string;
  is_static?: boolean;
}

interface Topology {
  hubs: Hub[];
  clinics: Clinic[];
  routes: Route[];
  disruptions: Disruption[];
  audit: { chain_hash: string; chain_valid: boolean; chain_length: number };
  state_machine: { current_state: string; capacity_margin_pct: number; total_demand: number; total_capacity: number };
}

// Mercator projection for lat/lng to x/y on a flat map
function project(lat: number, lng: number, width: number, height: number): [number, number] {
  const x = ((lng + 180) / 360) * width;
  const y = ((90 - lat) / 180) * height;
  return [x, y];
}

const STATUS_COLORS: Record<string, string> = {
  nominal: '#3D8B7A',
  thermal_warning: '#D4A017',
  thermal_breach: '#C23B3B',
};

const CRITICALITY_COLORS: Record<string, string> = {
  critical: '#C23B3B',
  high: '#E07B2F',
  medium: '#D4A017',
  low: '#3D8B7A',
};

export default function ResilienceGlobeView({ addToast }: { addToast: (msg: string, type?: 'success' | 'error') => void }) {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedClinic, setSelectedClinic] = useState<Clinic | null>(null);
  const [hoveredRoute, setHoveredRoute] = useState<Route | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [rotating, setRotating] = useState(false);
  const [rotation, setRotation] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 900, height: 500 });

  const fetchTopology = useCallback(async () => {
    try {
      const data = await api.getMapTopology();
      setTopology(data);
    } catch (e) {
      console.error('Failed to fetch topology:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTopology();
    const interval = setInterval(fetchTopology, 10000);
    return () => clearInterval(interval);
  }, [fetchTopology]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width: Math.max(width, 400), height: Math.max(height, 300) });
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!rotating) return;
    const id = setInterval(() => setRotation((r) => (r + 0.15) % 360), 30);
    return () => clearInterval(id);
  }, [rotating]);

  const handleApprove = async () => {
    try {
      const res = await api.approveAllocation();
      addToast(res.message || 'Allocation approved & written to SAP', 'success');
      fetchTopology();
    } catch (e: any) {
      addToast(e.message || 'Approval failed', 'error');
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 12 }}>
        <RotateCw size={24} className="spin" />
        <span style={{ color: 'var(--text-secondary)' }}>Loading geospatial topology...</span>
      </div>
    );
  }

  if (!topology) {
    return <div style={{ padding: 24, color: 'var(--text-secondary)' }}>No topology data available.</div>;
  }

  const { hubs, clinics, routes, disruptions, audit, state_machine } = topology;
  const w = dimensions.width;
  const h = dimensions.height;

  // Compute projected positions
  const hubPositions = hubs.map((hub) => ({
    ...hub,
    px: project(hub.coordinates[0], hub.coordinates[1], w, h),
  }));

  const clinicPositions = clinics.map((clinic) => ({
    ...clinic,
    px: project(clinic.coordinates[0], clinic.coordinates[1], w, h),
  }));

  const disruptionPositions = disruptions.map((d) => ({
    ...d,
    px: project(d.coordinates[0], d.coordinates[1], w, h),
  }));

  // Build SVG arcs for routes (only show active/feasible ones for clarity)
  const activeRoutes = routes.filter((r) => r.route_status !== 'thermal_breach' || Math.random() > 0.5).slice(0, 20);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0, overflow: 'hidden' }}>
      {/* Header bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px', borderBottom: '1px solid var(--border-subtle)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Globe size={20} color="var(--accent)" />
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Resilience Control Center</h2>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', background: 'var(--surface-elevated)', padding: '2px 8px', borderRadius: 4 }}>
            {state_machine.current_state.replace(/_/g, ' ')}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setRotating(!rotating)}>
            <RotateCw size={14} className={rotating ? 'spin' : ''} /> {rotating ? 'Stop' : 'Rotate'}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={fetchTopology}>
            <Activity size={14} /> Refresh
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Map area */}
        <div ref={containerRef} style={{ flex: 1, position: 'relative', background: '#0a0e1a', overflow: 'hidden' }}>
          <svg
            width={w}
            height={h}
            viewBox={`0 0 ${w} ${h}`}
            style={{ transform: `perspective(800px) rotateY(${rotation * 0.05}deg)` }}
          >
            {/* Grid lines */}
            {[0, 60, 120, 180, 240, 300, 360].map((lng) => {
              const x = ((lng + 180) / 360) * w;
              return <line key={`v${lng}`} x1={x} y1={0} x2={x} y2={h} stroke="#1a2040" strokeWidth={0.5} />;
            })}
            {[0, 30, 60, 90, 120, 150, 180].map((lat) => {
              const y = ((90 - lat) / 180) * h;
              return <line key={`h${lat}`} x1={0} y1={y} x2={w} y2={y} stroke="#1a2040" strokeWidth={0.5} />;
            })}

            {/* Route arcs */}
            {activeRoutes.map((route) => {
              const [x1, y1] = project(route.origin[0], route.origin[1], w, h);
              const [x2, y2] = project(route.destination[0], route.destination[1], w, h);
              const mx = (x1 + x2) / 2;
              const my = Math.min(y1, y2) - 30 - Math.abs(x2 - x1) * 0.08;
              const color = STATUS_COLORS[route.route_status] || '#3D8B7A';
              const dashArray = route.route_status === 'thermal_warning' ? '8 4' : route.route_status === 'thermal_breach' ? '4 4' : 'none';

              return (
                <g key={route.id}>
                  <path
                    d={`M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`}
                    fill="none"
                    stroke={color}
                    strokeWidth={2}
                    strokeDasharray={dashArray}
                    opacity={0.7}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={(e) => {
                      setHoveredRoute(route);
                      setHoverPos({ x: e.clientX, y: e.clientY });
                    }}
                    onMouseMove={(e) => setHoverPos({ x: e.clientX, y: e.clientY })}
                    onMouseLeave={() => setHoveredRoute(null)}
                  />
                  {/* Animated dot along route */}
                  <circle r={3} fill={color} opacity={0.9}>
                    <animateMotion dur={`${3 + route.transit_time_hours * 0.5}s`} repeatCount="indefinite">
                      <mpath href={`#path-${route.id}`} />
                    </animateMotion>
                  </circle>
                  <path id={`path-${route.id}`} d={`M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`} fill="none" stroke="none" />
                </g>
              );
            })}

            {/* Disruption markers */}
            {disruptionPositions.map((d) => (
              <g key={d.id} style={{ cursor: 'pointer' }}>
                <circle cx={d.px[0]} cy={d.px[1]} r={16} fill="#C23B3B" opacity={0.15}>
                  <animate attributeName="r" values="16;24;16" dur="2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.15;0.05;0.15" dur="2s" repeatCount="indefinite" />
                </circle>
                <circle cx={d.px[0]} cy={d.px[1]} r={8} fill="#C23B3B" opacity={0.8}>
                  <animate attributeName="r" values="8;10;8" dur="1.5s" repeatCount="indefinite" />
                </circle>
                <text x={d.px[0]} y={d.px[1] - 14} textAnchor="middle" fill="#ff6b6b" fontSize={9} fontWeight={600}>
                  {d.severity.toUpperCase()}
                </text>
              </g>
            ))}

            {/* Hub nodes */}
            {hubPositions.map((hub) => (
              <g key={hub.id}>
                <rect x={hub.px[0] - 10} y={hub.px[1] - 10} width={20} height={20} rx={4} fill="#1a3a5c" stroke="#3D8B7A" strokeWidth={1.5} />
                <text x={hub.px[0]} y={hub.px[1] + 1} textAnchor="middle" fill="#3D8B7A" fontSize={10} fontWeight={700}>
                  H
                </text>
                <text x={hub.px[0]} y={hub.px[1] + 24} textAnchor="middle" fill="#8899bb" fontSize={9}>
                  {hub.name.split(' ')[0]}
                </text>
              </g>
            ))}

            {/* Clinic nodes */}
            {clinicPositions.map((clinic) => {
              const color = clinic.is_dropped
                ? '#C23B3B'
                : clinic.is_threatened
                ? '#E07B2F'
                : CRITICALITY_COLORS[clinic.criticality] || '#3D8B7A';
              const size = clinic.criticality === 'critical' ? 8 : 6;

              return (
                <g
                  key={clinic.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setSelectedClinic(selectedClinic?.id === clinic.id ? null : clinic)}
                >
                  {/* Glow for threatened */}
                  {clinic.is_threatened && (
                    <circle cx={clinic.px[0]} cy={clinic.px[1]} r={size + 6} fill={color} opacity={0.15}>
                      <animate attributeName="r" values={`${size + 6};${size + 10};${size + 6}`} dur="2s" repeatCount="indefinite" />
                    </circle>
                  )}
                  <circle cx={clinic.px[0]} cy={clinic.px[1]} r={size} fill={color} stroke="#0a0e1a" strokeWidth={1.5} />
                  <text x={clinic.px[0]} y={clinic.px[1] - size - 4} textAnchor="middle" fill={color} fontSize={8} fontWeight={600}>
                    {clinic.id.replace('CLN-', '')}
                  </text>
                  {clinic.is_dropped && (
                    <text x={clinic.px[0]} y={clinic.px[1] + size + 12} textAnchor="middle" fill="#C23B3B" fontSize={8} fontWeight={700}>
                      DROPPED
                    </text>
                  )}
                </g>
              );
            })}
          </svg>

          {/* Hover tooltip for routes */}
          {hoveredRoute && (
            <div
              style={{
                position: 'fixed',
                left: hoverPos.x + 16,
                top: hoverPos.y - 10,
                background: 'var(--surface-elevated)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 8,
                padding: '10px 14px',
                fontSize: 12,
                zIndex: 1000,
                minWidth: 220,
                boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
                pointerEvents: 'none',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Truck size={14} color={STATUS_COLORS[hoveredRoute.route_status]} />
                {hoveredRoute.vehicle_id} — {hoveredRoute.vehicle_type}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 12px', color: 'var(--text-secondary)' }}>
                <span>Transit:</span><span>{hoveredRoute.transit_time_hours}h ({hoveredRoute.distance_km}km)</span>
                <span>Ambient Temp:</span><span>{hoveredRoute.ambient_temperature_celsius}°C</span>
                <span>Decay Rate (k):</span><span>{hoveredRoute.arrhenius_decay_rate}</span>
                <span>Shelf Life Left:</span><span>{hoveredRoute.remaining_shelf_life_hours}h</span>
                <span>Status:</span>
                <span style={{ color: STATUS_COLORS[hoveredRoute.route_status], fontWeight: 600 }}>
                  {hoveredRoute.route_status.replace(/_/g, ' ').toUpperCase()}
                </span>
              </div>
              {hoveredRoute.feasibility_reason && (
                <div style={{ marginTop: 6, padding: '4px 8px', background: '#C23B3B15', borderRadius: 4, color: '#C23B3B', fontSize: 10 }}>
                  {hoveredRoute.feasibility_reason}
                </div>
              )}
            </div>
          )}

          {/* Legend */}
          <div style={{ position: 'absolute', bottom: 12, left: 12, background: 'rgba(10,14,26,0.9)', borderRadius: 8, padding: '8px 12px', fontSize: 10, display: 'flex', gap: 12 }}>
            {Object.entries(STATUS_COLORS).map(([key, color]) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <div style={{ width: 12, height: 3, background: color, borderRadius: 2 }} />
                <span style={{ color: '#8899bb' }}>{key.replace(/_/g, ' ')}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right panel */}
        <div style={{ width: 300, borderLeft: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Selected clinic detail */}
          {selectedClinic ? (
            <div style={{ padding: 16, borderBottom: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>{selectedClinic.name}</h3>
                <button className="btn btn-ghost btn-sm" onClick={() => setSelectedClinic(null)} style={{ padding: 2 }}>
                  <XCircle size={14} />
                </button>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                <span>City:</span><span>{selectedClinic.city}, {selectedClinic.country}</span>
                <span>Demand:</span><span>{selectedClinic.demand_units} units</span>
                <span>Criticality:</span><span style={{ color: CRITICALITY_COLORS[selectedClinic.criticality] }}>{selectedClinic.criticality}</span>
                <span>Pi Score:</span><span style={{ fontWeight: 600 }}>{selectedClinic.priority_score.toFixed(4)}</span>
                <span>Stock Coverage:</span><span>{selectedClinic.stock_coverage_pct}%</span>
                <span>Shelf Life:</span><span>{selectedClinic.remaining_shelf_life_hours}h</span>
                <span>Status:</span>
                <span style={{ color: selectedClinic.is_dropped ? '#C23B3B' : selectedClinic.is_threatened ? '#E07B2F' : '#3D8B7A', fontWeight: 600 }}>
                  {selectedClinic.allocation_status || (selectedClinic.is_dropped ? 'DROPPED' : 'OK')}
                </span>
                {selectedClinic.allocated_vehicle && (
                  <>
                    <span>Vehicle:</span><span>{selectedClinic.allocated_vehicle}</span>
                  </>
                )}
              </div>
              {selectedClinic.is_dropped && selectedClinic.drop_reason && (
                <div style={{ marginTop: 8, padding: '6px 10px', background: '#C23B3B15', borderRadius: 6, fontSize: 11, color: '#C23B3B' }}>
                  <XCircle size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                  {selectedClinic.drop_reason}
                </div>
              )}
            </div>
          ) : (
            <div style={{ padding: 16, borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', fontSize: 12 }}>
              Click a clinic node on the map to view details
            </div>
          )}

          {/* Live Governance Overlay */}
          <div style={{ padding: 16, borderBottom: '1px solid var(--border-subtle)' }}>
            <h4 style={{ fontSize: 12, fontWeight: 600, margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: 6 }}>
              <ShieldCheck size={14} color="var(--accent)" />
              Live Governance Overlay
            </h4>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
              <span>Audit Hash:</span>
              <span style={{ fontFamily: 'monospace', fontSize: 10 }}>{audit.chain_hash}</span>
              <span>Chain Valid:</span>
              <span style={{ color: audit.chain_valid ? '#3D8B7A' : '#C23B3B', fontWeight: 600 }}>
                {audit.chain_valid ? 'VALID' : 'BROKEN'}
              </span>
              <span>Chain Length:</span>
              <span>{audit.chain_length} records</span>
            </div>
            <button
              className="btn btn-primary btn-sm"
              style={{ width: '100%', marginTop: 10, justifyContent: 'center', background: '#1a6b4a' }}
              onClick={handleApprove}
            >
              <CheckCircle size={14} /> Approve & Write Back to SAP
            </button>
          </div>

          {/* Stats */}
          <div style={{ padding: 16, flex: 1, overflow: 'auto' }}>
            <h4 style={{ fontSize: 12, fontWeight: 600, margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: 6 }}>
              <MapPin size={14} color="var(--accent)" />
              Network Overview
            </h4>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
              <span>Capacity Margin:</span>
              <span style={{ fontWeight: 600, color: state_machine.capacity_margin_pct > 15 ? '#3D8B7A' : '#C23B3B' }}>
                {state_machine.capacity_margin_pct}%
              </span>
              <span>Total Demand:</span><span>{state_machine.total_demand} units</span>
              <span>Total Capacity:</span><span>{state_machine.total_capacity} kg</span>
              <span>Hubs:</span><span>{hubs.length}</span>
              <span>Clinics:</span><span>{clinics.length}</span>
              <span>Routes:</span><span>{routes.length}</span>
              <span>Disruptions:</span><span style={{ color: disruptions.length > 0 ? '#C23B3B' : undefined }}>{disruptions.length}</span>
            </div>
            <div style={{ marginTop: 12 }}>
              <h4 style={{ fontSize: 11, fontWeight: 600, margin: '0 0 6px 0' }}>Route Status Summary</h4>
              {['nominal', 'thermal_warning', 'thermal_breach'].map((status) => {
                const count = routes.filter((r) => r.route_status === status).length;
                return (
                  <div key={status} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, marginBottom: 2 }}>
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: STATUS_COLORS[status] }} />
                    <span style={{ color: 'var(--text-secondary)', flex: 1 }}>{status.replace(/_/g, ' ')}</span>
                    <span style={{ fontWeight: 600 }}>{count}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
