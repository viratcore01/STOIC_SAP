import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Viewer, Entity, BillboardGraphics, PolylineGraphics, EllipseGraphics, LabelGraphics } from 'resium';
import * as Cesium from 'cesium';
import { api } from '../api';
import {
  ShieldCheck,
  Truck,
  MapPin,
  Activity,
  CheckCircle,
  XCircle,
  RotateCw,
  Globe as GlobeIcon,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────
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
}
interface Topology {
  hubs: Hub[];
  clinics: Clinic[];
  routes: Route[];
  disruptions: Disruption[];
  audit: { chain_hash: string; chain_valid: boolean; chain_length: number };
  state_machine: { current_state: string; capacity_margin_pct: number; total_demand: number; total_capacity: number };
}

// ─── Constants ────────────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, Cesium.Color> = {
  nominal: Cesium.Color.fromCssColorString('#3D8B7A'),
  thermal_warning: Cesium.Color.fromCssColorString('#D4A017'),
  thermal_breach: Cesium.Color.fromCssColorString('#C23B3B'),
};
const STATUS_CSS: Record<string, string> = {
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
const CRITICALITY_CESIUM: Record<string, Cesium.Color> = {
  critical: Cesium.Color.fromCssColorString('#C23B3B'),
  high: Cesium.Color.fromCssColorString('#E07B2F'),
  medium: Cesium.Color.fromCssColorString('#D4A017'),
  low: Cesium.Color.fromCssColorString('#3D8B7A'),
};

function clinicCesiumColor(c: Clinic): Cesium.Color {
  if (c.is_dropped) return Cesium.Color.fromCssColorString('#666');
  if (c.is_threatened) return Cesium.Color.fromCssColorString('#E07B2F');
  return CRITICALITY_CESIUM[c.criticality] || Cesium.Color.fromCssColorString('#3D8B7A');
}

function clinicCssColor(c: Clinic): string {
  if (c.is_dropped) return '#666';
  if (c.is_threatened) return '#E07B2F';
  return CRITICALITY_COLORS[c.criticality] || '#3D8B7A';
}

/** Build a parabolic arc between two cartographic positions, raised off the surface. */
function buildArcPositions(
  origin: number[],
  destination: number[],
  arcHeight = 0.08,
  segments = 48,
): Cesium.Cartesian3[] {
  const startCarto = Cesium.Cartographic.fromDegrees(origin[1], origin[0]);
  const endCarto = Cesium.Cartographic.fromDegrees(destination[1], destination[0]);
  const startCartesian = Cesium.Cartographic.toCartesian(startCarto);
  const endCartesian = Cesium.Cartographic.toCartesian(endCarto);
  const positions: Cesium.Cartesian3[] = [];
  const distance = Cesium.Cartesian3.distance(startCartesian, endCartesian);
  const height = distance * arcHeight;

  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const pos = Cesium.Cartesian3.lerp(startCartesian, endCartesian, t, new Cesium.Cartesian3());
    const carto = Cesium.Cartographic.fromCartesian(pos);
    const normalizedHeight = carto.height + height * Math.sin(Math.PI * t);
    const newPos = Cesium.Cartographic.toCartesian(
      Cesium.Cartographic.fromRadians(carto.longitude, carto.latitude, normalizedHeight),
    );
    positions.push(newPos);
  }
  return positions;
}

// Suppress Cesium Ion token warning — using OpenStreetMap tiles (free, no key)
Cesium.Ion.defaultAccessToken = undefined as unknown as string;

// ─── Component ────────────────────────────────────────────────────────────────
export default function ResilienceGlobeView({
  addToast,
}: {
  addToast: (msg: string, type?: 'success' | 'error') => void;
}) {
  // ALL hooks MUST be declared before any early returns
  const [topology, setTopology] = useState<Topology | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedClinic, setSelectedClinic] = useState<Clinic | null>(null);
  const [hoveredRoute] = useState<Route | null>(null);
  const [hoverPos] = useState({ x: 0, y: 0 });
  const [whatIfRunning, setWhatIfRunning] = useState(false);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const focusedEntityId = useRef<string | null>(null);

  const fetchTopology = useCallback(async () => {
    try {
      const data = await api.getMapTopology();
      setTopology(data);
    } catch (e) {
      console.error('Topology fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTopology();
    const iv = setInterval(fetchTopology, 12000);
    return () => clearInterval(iv);
  }, [fetchTopology]);

  // Fly-to animation when selecting a clinic
  useEffect(() => {
    if (!selectedClinic || !viewerRef.current) return;
    const viewer = viewerRef.current;
    const [lat, lng] = selectedClinic.coordinates;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(lng, lat, 2_500_000),
      orientation: {
        heading: 0,
        pitch: Cesium.Math.toRadians(-35),
        roll: 0,
      },
      duration: 1.5,
    });
    focusedEntityId.current = selectedClinic.id;
  }, [selectedClinic]);

  const handleDisruptionClick = async (disruption: Disruption) => {
    setWhatIfRunning(true);
    try {
      const res = await fetch('/api/allocation/what-if', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([
          { w1: 0.5, w2: 0.3, w3: 0.2, label: 'Clinical Focus' },
          { w1: 0.3, w2: 0.4, w3: 0.3, label: 'Balanced' },
          { w1: 0.2, w2: 0.2, w3: 0.6, label: 'Value Focus' },
        ]),
      });
      const data = await res.json();
      addToast(
        `What-if complete — best scenario: ${data.best_scenario?.label || 'N/A'}`,
        'success',
      );
      if (disruption.affected_sites.length > 0 && viewerRef.current) {
        const clinicId = disruption.affected_sites[0];
        const clinic = topology?.clinics.find((c) => c.id === clinicId);
        if (clinic) setSelectedClinic(clinic);
      }
    } catch {
      addToast('What-if simulation failed', 'error');
    } finally {
      setWhatIfRunning(false);
    }
  };

  const handleApprove = async () => {
    try {
      const res = await api.approveAllocation();
      addToast(res.message || 'Allocation approved & written to SAP', 'success');
      fetchTopology();
    } catch (e: any) {
      addToast(e.message || 'Approval failed', 'error');
    }
  };

  // ─── Memoised Cesium entities (hooks MUST be before early returns) ─────────
  const hubs = topology?.hubs ?? [];
  const clinics = topology?.clinics ?? [];
  const routes = topology?.routes ?? [];
  const disruptions = topology?.disruptions ?? [];
  const audit = topology?.audit ?? { chain_hash: '', chain_valid: false, chain_length: 0 };
  const state_machine = topology?.state_machine ?? { current_state: 'S1_STABLE', capacity_margin_pct: 0, total_demand: 0, total_capacity: 0 };

  const cesiumRoutes = useMemo(
    () =>
      routes.slice(0, 30).map((route) => ({
        ...route,
        arcPositions: buildArcPositions(route.origin, route.destination),
        cesiumColor: STATUS_COLORS[route.route_status] || STATUS_COLORS.nominal,
      })),
    [routes],
  );

  const cesiumHubs = useMemo(
    () =>
      hubs.map((hub) => ({
        ...hub,
        cartesian: Cesium.Cartesian3.fromDegrees(hub.coordinates[1], hub.coordinates[0]),
      })),
    [hubs],
  );

  const cesiumClinics = useMemo(
    () =>
      clinics.map((clinic) => ({
        ...clinic,
        cartesian: Cesium.Cartesian3.fromDegrees(clinic.coordinates[1], clinic.coordinates[0]),
        cesiumColor: clinicCesiumColor(clinic),
      })),
    [clinics],
  );

  const cesiumDisruptions = useMemo(
    () =>
      disruptions.map((d) => ({
        ...d,
        cartesian: Cesium.Cartesian3.fromDegrees(d.coordinates[1], d.coordinates[0]),
      })),
    [disruptions],
  );

  // ─── Loading / empty state (render returns AFTER all hooks) ────────────────
  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 12 }}>
        <RotateCw size={24} className="spin" />
        <span style={{ color: 'var(--text-secondary)' }}>Loading 3D Globe…</span>
      </div>
    );
  }
  if (!topology) {
    return <div style={{ padding: 24, color: 'var(--text-secondary)' }}>No topology data.</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 20px',
          borderBottom: '1px solid var(--border-subtle)',
          flexShrink: 0,
          background: 'var(--surface)',
          zIndex: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <GlobeIcon size={20} color="var(--accent)" />
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Resilience Control Center</h2>
          <span
            style={{
              fontSize: 11,
              color: 'var(--text-secondary)',
              background: 'var(--surface-elevated)',
              padding: '2px 8px',
              borderRadius: 4,
            }}
          >
            {state_machine.current_state.replace(/_/g, ' ')}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {whatIfRunning && (
            <span style={{ fontSize: 11, color: '#D4A017' }}>Running what-if…</span>
          )}
          <button className="btn btn-ghost btn-sm" onClick={fetchTopology}>
            <Activity size={14} /> Refresh
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* ─── 3D Globe ──────────────────────────────────────────────────────── */}
        <div style={{ flex: 1, position: 'relative' }}>
          <Viewer
            ref={viewerRef as any}
            animation={false}
            timeline={false}
            baseLayerPicker={false}
            geocoder={false}
            homeButton={false}
            sceneModePicker={false}
            navigationHelpButton={false}
            infoBox={false}
            selectionIndicator={false}
            fullscreenButton={false}
            vrButton={false}
            style={{ background: '#080c18' }}
            scene3DOnly
            baseLayer={new Cesium.ImageryLayer(
              new Cesium.OpenStreetMapImageryProvider({
                url: 'https://tile.openstreetmap.org/',
              }),
            )}
          >
            {/* ─── HUB BEACONS (glowing pillars) ──────────────────────────── */}
            {cesiumHubs.map((hub) => (
              <Entity key={hub.id} position={hub.cartesian} name={hub.name}>
                <BillboardGraphics
                  image="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='20' height='60'><defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='%233D8B7A' stop-opacity='1'/><stop offset='1' stop-color='%233D8B7A' stop-opacity='0.1'/></linearGradient></defs><rect x='6' y='0' width='8' height='60' rx='4' fill='url(%23g)'/><circle cx='10' cy='4' r='6' fill='%233D8B7A' opacity='0.9'/></svg>"
                  scale={1.2}
                  verticalOrigin={Cesium.VerticalOrigin.BOTTOM}
                  disableDepthTestDistance={Number.POSITIVE_INFINITY}
                />
                <LabelGraphics
                  text={hub.name}
                  font="bold 13px sans-serif"
                  fillColor={Cesium.Color.fromCssColorString('#3D8B7A')}
                  outlineColor={Cesium.Color.BLACK}
                  outlineWidth={2}
                  style={Cesium.LabelStyle.FILL_AND_OUTLINE}
                  verticalOrigin={Cesium.VerticalOrigin.BOTTOM}
                  pixelOffset={new Cesium.Cartesian2(0, -70)}
                  disableDepthTestDistance={Number.POSITIVE_INFINITY}
                />
              </Entity>
            ))}

            {/* ─── CLINIC PINS ────────────────────────────────────────────── */}
            {cesiumClinics.map((clinic) => (
              <Entity
                key={clinic.id}
                position={clinic.cartesian}
                name={clinic.name}
                description={`${clinic.city}, ${clinic.country}\nPi: ${clinic.priority_score.toFixed(4)}\nStock: ${clinic.stock_coverage_pct}%\nStatus: ${clinic.allocation_status || (clinic.is_dropped ? 'DROPPED' : 'OK')}`}
                onClick={() => setSelectedClinic(clinic)}
              >
                <BillboardGraphics
                  image={`data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='34'><path d='M12 2C7.03 2 3 5.81 3 10.5c0 6.5 9 19.5 9 19.5s9-13 9-19.5C21 5.81 16.97 2 12 2z' fill='${encodeURIComponent(clinicCssColor(clinic))}' stroke='%23000' stroke-width='1'/><circle cx='12' cy='10' r='4' fill='%230a0e1a'/><text x='12' y='12' text-anchor='middle' fill='white' font-size='6' font-weight='bold'>${clinic.id.slice(-2)}</text></svg>`}
                  scale={selectedClinic?.id === clinic.id ? 1.3 : 1.0}
                  verticalOrigin={Cesium.VerticalOrigin.BOTTOM}
                  disableDepthTestDistance={Number.POSITIVE_INFINITY}
                />
                <LabelGraphics
                  text={clinic.id.replace('CLN-', '')}
                  font="bold 10px sans-serif"
                  fillColor={clinic.cesiumColor}
                  outlineColor={Cesium.Color.BLACK}
                  outlineWidth={2}
                  style={Cesium.LabelStyle.FILL_AND_OUTLINE}
                  verticalOrigin={Cesium.VerticalOrigin.BOTTOM}
                  pixelOffset={new Cesium.Cartesian2(0, -40)}
                  disableDepthTestDistance={Number.POSITIVE_INFINITY}
                  showBackground
                  backgroundColor={Cesium.Color.fromCssColorString('#0a0e1a').withAlpha(0.7)}
                />
              </Entity>
            ))}

            {/* ─── ROUTE ARCS (3D parabolic polylines) ───────────────────── */}
            {cesiumRoutes.map((route) => (
              <Entity key={route.id} name={`${route.vehicle_id} → ${route.destination}`}>
                <PolylineGraphics
                  positions={route.arcPositions}
                  width={route.route_status === 'thermal_breach' ? 3 : 2}
                  material={
                    route.route_status === 'thermal_warning'
                      ? new Cesium.PolylineGlowMaterialProperty({
                          glowPower: 0.15,
                          color: Cesium.Color.fromCssColorString('#D4A017'),
                        })
                      : route.route_status === 'thermal_breach'
                      ? new Cesium.PolylineGlowMaterialProperty({
                          glowPower: 0.25,
                          color: Cesium.Color.fromCssColorString('#C23B3B'),
                        })
                      : new Cesium.PolylineGlowMaterialProperty({
                          glowPower: 0.1,
                          color: Cesium.Color.fromCssColorString('#3D8B7A'),
                        })
                  }
                />
              </Entity>
            ))}

            {/* ─── DISRUPTION BEACONS (pulsing rings) ─────────────────────── */}
            {cesiumDisruptions.map((d) => (
              <Entity
                key={d.id}
                position={d.cartesian}
                name={d.name}
                description={`${d.description}\nSeverity: ${d.severity}\nAffected: ${d.affected_sites.join(', ')}`}
                onClick={() => handleDisruptionClick(d)}
              >
                <EllipseGraphics
                  semiMajorAxis={120000}
                  semiMinorAxis={120000}
                  material={Cesium.Color.fromCssColorString('#C23B3B').withAlpha(0.2)}
                  outline
                  outlineColor={Cesium.Color.fromCssColorString('#C23B3B').withAlpha(0.6)}
                  outlineWidth={2}
                  height={50000}
                  numberOfVerticalLines={0}
                />
                <EllipseGraphics
                  semiMajorAxis={40000}
                  semiMinorAxis={40000}
                  material={Cesium.Color.fromCssColorString('#C23B3B').withAlpha(0.6)}
                  outline
                  outlineColor={Cesium.Color.fromCssColorString('#ff4444')}
                  outlineWidth={2}
                  height={80000}
                />
                <LabelGraphics
                  text={`⚠ ${d.severity.toUpperCase()}`}
                  font="bold 12px sans-serif"
                  fillColor={Cesium.Color.fromCssColorString('#ff6b6b')}
                  outlineColor={Cesium.Color.BLACK}
                  outlineWidth={2}
                  style={Cesium.LabelStyle.FILL_AND_OUTLINE}
                  verticalOrigin={Cesium.VerticalOrigin.BOTTOM}
                  pixelOffset={new Cesium.Cartesian2(0, -60)}
                  disableDepthTestDistance={Number.POSITIVE_INFINITY}
                  showBackground
                  backgroundColor={Cesium.Color.fromCssColorString('#C23B3B').withAlpha(0.7)}
                />
              </Entity>
            ))}
          </Viewer>
        </div>

        {/* ─── RIGHT PANEL ──────────────────────────────────────────────────── */}
        <div
          style={{
            width: 320,
            borderLeft: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            background: 'var(--surface)',
          }}
        >
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
                <span>City:</span>
                <span>{selectedClinic.city}, {selectedClinic.country}</span>
                <span>Demand:</span>
                <span>{selectedClinic.demand_units} units</span>
                <span>Criticality:</span>
                <span style={{ color: CRITICALITY_COLORS[selectedClinic.criticality] }}>
                  {selectedClinic.criticality}
                </span>
                <span>Pi Score:</span>
                <span style={{ fontWeight: 600 }}>{selectedClinic.priority_score.toFixed(4)}</span>
                <span>Stock Coverage:</span>
                <span>{selectedClinic.stock_coverage_pct}%</span>
                <span>Shelf Life:</span>
                <span>{selectedClinic.remaining_shelf_life_hours}h</span>
                <span>Status:</span>
                <span
                  style={{
                    color: selectedClinic.is_dropped ? '#C23B3B' : selectedClinic.is_threatened ? '#E07B2F' : '#3D8B7A',
                    fontWeight: 600,
                  }}
                >
                  {selectedClinic.allocation_status || (selectedClinic.is_dropped ? 'DROPPED' : 'OK')}
                </span>
                {selectedClinic.allocated_vehicle && (
                  <>
                    <span>Vehicle:</span>
                    <span>{selectedClinic.allocated_vehicle}</span>
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
              Click a clinic or disruption on the globe to inspect details
            </div>
          )}

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
                <Truck size={14} color={STATUS_CSS[hoveredRoute.route_status]} />
                {hoveredRoute.vehicle_id} — {hoveredRoute.vehicle_type}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 12px', color: 'var(--text-secondary)' }}>
                <span>Transit:</span>
                <span>{hoveredRoute.transit_time_hours}h ({hoveredRoute.distance_km}km)</span>
                <span>Ambient Temp:</span>
                <span>{hoveredRoute.ambient_temperature_celsius}°C</span>
                <span>Decay Rate (k):</span>
                <span>{hoveredRoute.arrhenius_decay_rate}</span>
                <span>Shelf Life Left:</span>
                <span>{hoveredRoute.remaining_shelf_life_hours}h</span>
                <span>Status:</span>
                <span style={{ color: STATUS_CSS[hoveredRoute.route_status], fontWeight: 600 }}>
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
              <span>Total Demand:</span>
              <span>{state_machine.total_demand} units</span>
              <span>Total Capacity:</span>
              <span>{state_machine.total_capacity} kg</span>
              <span>Hubs:</span>
              <span>{hubs.length}</span>
              <span>Clinics:</span>
              <span>{clinics.length}</span>
              <span>Routes:</span>
              <span>{routes.length}</span>
              <span>Disruptions:</span>
              <span style={{ color: disruptions.length > 0 ? '#C23B3B' : undefined }}>{disruptions.length}</span>
            </div>
            <div style={{ marginTop: 12 }}>
              <h4 style={{ fontSize: 11, fontWeight: 600, margin: '0 0 6px 0' }}>Route Status Summary</h4>
              {(['nominal', 'thermal_warning', 'thermal_breach'] as const).map((status) => {
                const count = routes.filter((r) => r.route_status === status).length;
                return (
                  <div key={status} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, marginBottom: 2 }}>
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: STATUS_CSS[status] }} />
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
