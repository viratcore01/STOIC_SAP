import { useEffect, useRef, useState, useCallback } from 'react';
import * as Cesium from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import { api } from '../api';
import { Globe as GlobeIcon } from 'lucide-react';

// ─── Config ───────────────────────────────────────────────────────────────────
const ION_TOKEN = (import.meta as any).env?.VITE_GOOGLE_MAPS_API_KEY as string | undefined;
const HUB_HEIGHT_M = 120_000;
const HUB_RADIUS_M = 10_000;
const ROUTE_ARC_HEIGHT_M = 60_000;

const COLORS = {
  nominal: Cesium.Color.fromCssColorString('#3ED598'),
  priority: Cesium.Color.fromCssColorString('#F4A100'),
  critical: Cesium.Color.fromCssColorString('#FF3B3B'),
  dropped: Cesium.Color.fromCssColorString('#5B6B78'),
  hub: Cesium.Color.fromCssColorString('#4CC9F0'),
  selected: Cesium.Color.fromCssColorString('#2FD8FF'),
  approved: Cesium.Color.fromCssColorString('#4FC3F7'),
};

function clinicColor(c: any): Cesium.Color {
  if (c.is_dropped) return COLORS.dropped;
  if (c.criticality === 'critical') return COLORS.critical;
  if (c.criticality === 'high') return COLORS.priority;
  return COLORS.nominal;
}

function routeColor(status: string): Cesium.Color {
  if (status === 'thermal_breach') return COLORS.critical;
  if (status === 'thermal_warning') return COLORS.priority;
  return COLORS.nominal;
}

function buildArcPositions(origin: number[], dest: number[], _height = ROUTE_ARC_HEIGHT_M, segs = 48): Cesium.Cartesian3[] {
  const start = Cesium.Cartographic.fromDegrees(origin[1], origin[0]);
  const end = Cesium.Cartographic.fromDegrees(dest[1], dest[0]);
  const s = Cesium.Cartographic.toCartesian(start);
  const e = Cesium.Cartographic.toCartesian(end);
  const dist = Cesium.Cartesian3.distance(s, e);
  const arcH = dist * 0.08;
  const positions: Cesium.Cartesian3[] = [];
  for (let i = 0; i <= segs; i++) {
    const t = i / segs;
    const pos = Cesium.Cartesian3.lerp(s, e, t, new Cesium.Cartesian3());
    const carto = Cesium.Cartographic.fromCartesian(pos);
    const h = carto.height + arcH * Math.sin(Math.PI * t);
    positions.push(Cesium.Cartographic.toCartesian(Cesium.Cartographic.fromRadians(carto.longitude, carto.latitude, h)));
  }
  return positions;
}

// ─── Types ────────────────────────────────────────────────────────────────────
interface Topology {
  hubs: any[];
  clinics: any[];
  routes: any[];
  disruptions: any[];
  audit: { chain_hash: string; chain_valid: boolean; chain_length: number };
  state_machine: { current_state: string; capacity_margin_pct: number; total_demand: number; total_capacity: number };
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function ResilienceGlobeView({ addToast }: { addToast: (msg: string, type?: 'success' | 'error') => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const entitiesRef = useRef<Cesium.Entity[]>([]);
  const [topology, setTopology] = useState<Topology | null>(null);
  const [loading, setLoading] = useState(true);
  const [hudEntity, setHudEntity] = useState<{ kind: string; data: any } | null>(null);
  const [whatIf, setWhatIf] = useState<any>(null);
  const [mapSource, setMapSource] = useState('loading');
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(false);

  // ─── Viewer bootstrap ───────────────────────────────────────────────────
  useEffect(() => {
    let destroyed = false;
    let resizeObs: ResizeObserver | null = null;

    async function init() {
      if (!containerRef.current) return;

      if (ION_TOKEN) Cesium.Ion.defaultAccessToken = ION_TOKEN;

      const viewer = new Cesium.Viewer(containerRef.current, {
        timeline: false,
        animation: false,
        sceneModePicker: false,
        baseLayerPicker: false,
        globe: false,
        geocoder: false,
        homeButton: false,
        navigationHelpButton: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        shadows: false,
        contextOptions: { webgl: { alpha: true } },
      });

      if (viewer.scene.skyAtmosphere) {
        viewer.scene.skyAtmosphere.show = true;
        viewer.scene.skyAtmosphere.hueShift = -0.02;
      }
      viewer.scene.fog.enabled = true;
      (viewer as any)._cesiumWidget._creditContainer.style.display = 'none';

      // Try Google 3D Tiles, fallback to OSM
      let source = 'osm';
      if (ION_TOKEN) {
        try {
          const tileset = await (Cesium as any).createGooglePhotorealistic3DTileset({
            onlyUsingWithGoogleGeocoder: false,
          });
          if (!destroyed) {
            viewer.scene.primitives.add(tileset);
            source = 'google';
          } else {
            tileset.destroy?.();
          }
        } catch {
          // fallback
        }
      }
      if (source === 'osm' && !destroyed) {
        viewer.scene.globe.show = true;
        try {
          const osm = new Cesium.OpenStreetMapImageryProvider({ url: 'https://tile.openstreetmap.org/' });
          viewer.imageryLayers.addImageryProvider(osm);
        } catch { /* ok */ }
      }
      if (!destroyed) setMapSource(source);

      // Camera
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(20, 15, 12_000_000),
        duration: 0,
      });

      // Click handler
      const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
      handler.setInputAction((movement: any) => {
        const picked = viewer.scene.pick(movement.position);
        if (!Cesium.defined(picked) || !(picked as any).id) {
          setHudEntity(null);
          return;
        }
        const entity = (picked as any).id;
        const meta = entity._meta;
        if (!meta) { setHudEntity(null); return; }

        setHudEntity(meta);

        if (meta.kind !== 'route') {
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(meta.data.coordinates?.[1] ?? meta.data.lon ?? 0, meta.data.coordinates?.[0] ?? meta.data.lat ?? 0, 3_500),
            orientation: { heading: 0, pitch: Cesium.Math.toRadians(-45), roll: 0 },
            duration: 2.0,
          });
        }

        if (meta.kind === 'disruption') {
          triggerWhatIf(meta.data);
        }
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

      handler.setInputAction((movement: any) => {
        const picked = viewer.scene.pick(movement.endPosition);
        if (Cesium.defined(picked) && (picked as any).id?._meta) {
          viewer.canvas.style.cursor = 'pointer';
        } else {
          viewer.canvas.style.cursor = 'default';
        }
      }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

      if (!destroyed) {
        viewerRef.current = viewer;
        resizeObs = new ResizeObserver(() => viewer.resize());
        resizeObs.observe(containerRef.current);
      } else {
        handler.destroy();
        viewer.destroy();
      }
    }

    init();

    return () => {
      destroyed = true;
      resizeObs?.disconnect();
      const v = viewerRef.current;
      if (v && !v.isDestroyed()) v.destroy();
      viewerRef.current = null;
    };
  }, []);

  // ─── Data fetch ─────────────────────────────────────────────────────────
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
    const iv = setInterval(fetchTopology, 12_000);
    return () => clearInterval(iv);
  }, [fetchTopology]);

  // ─── Entity rendering ───────────────────────────────────────────────────
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !topology) return;

    // Clear old entities
    entitiesRef.current.forEach((e) => viewer.entities.remove(e));
    entitiesRef.current = [];

    const add = (e: Cesium.Entity) => { entitiesRef.current.push(e); return e; };

    // Hubs
    (topology.hubs || []).forEach((hub) => {
      const lat = hub.coordinates?.[0] ?? hub.lat ?? 0;
      const lon = hub.coordinates?.[1] ?? hub.lon ?? 0;

      const pillar = add(viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, HUB_HEIGHT_M / 2),
        cylinder: {
          length: HUB_HEIGHT_M,
          topRadius: 200,
          bottomRadius: HUB_RADIUS_M,
          material: COLORS.hub.withAlpha(0.35),
          outline: true,
          outlineColor: COLORS.hub.withAlpha(0.9),
          outlineWidth: 1,
        },
      }));
      (pillar as any)._meta = { kind: 'hub', data: hub };

      const label = add(viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, HUB_HEIGHT_M + 4000),
        label: {
          text: `${(hub.name || '').toUpperCase()} · HUB`,
          font: '600 14px monospace',
          fillColor: COLORS.hub,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 3,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          pixelOffset: new Cesium.Cartesian2(0, -6),
        },
        point: { pixelSize: 6, color: COLORS.hub, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      }));
      (label as any)._meta = { kind: 'hub', data: hub };
    });

    // Clinics
    (topology.clinics || []).forEach((clinic) => {
      const lat = clinic.coordinates?.[0] ?? clinic.lat ?? 0;
      const lon = clinic.coordinates?.[1] ?? clinic.lon ?? 0;
      const color = clinicColor(clinic);

      const entity = add(viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 800),
        ellipsoid: {
          radii: new Cesium.Cartesian3(900, 900, 900),
          material: color.withAlpha(clinic.is_dropped ? 0.35 : 0.85),
          outline: true,
          outlineColor: Cesium.Color.WHITE.withAlpha(0.4),
        },
        label: {
          text: clinic.name || clinic.id,
          font: '500 12px monospace',
          fillColor: color,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -18),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scaleByDistance: new Cesium.NearFarScalar(1.0e4, 1.0, 4.0e6, 0.4),
        },
      }));
      (entity as any)._meta = { kind: 'clinic', data: clinic };
    });

    // Routes with pulsing
    (topology.routes || []).forEach((route) => {
      const origin = route.origin || [route.from?.[1], route.from?.[0]];
      const dest = route.destination || [route.to?.[1], route.to?.[0]];
      if (!origin || !dest) return;

      const baseColor = routeColor(route.route_status);
      const isPulsing = route.route_status === 'thermal_warning';
      const isFlashing = route.route_status === 'thermal_breach';

      const colorProp = (isPulsing || isFlashing)
        ? new Cesium.CallbackProperty(() => {
            const t = performance.now() / (isFlashing ? 220 : 650);
            const phase = (Math.sin(t) + 1) / 2;
            const alpha = isFlashing ? 0.35 + phase * 0.65 : 0.5 + phase * 0.5;
            return baseColor.withAlpha(alpha);
          }, false)
        : baseColor.withAlpha(0.9);

      const positions = buildArcPositions(origin, dest);

      const entity = add(viewer.entities.add({
        polyline: {
          positions,
          width: isFlashing ? 5 : 3,
          arcType: Cesium.ArcType.GEODESIC,
          material: new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.25, color: colorProp }),
          clampToGround: false,
        },
      }));
      (entity as any)._meta = { kind: 'route', data: route };
    });

    // Disruptions with pulsing rings
    (topology.disruptions || []).forEach((d: any) => {
      const lat: number = d.coordinates?.[0] ?? d.lat ?? 0;
      const lon: number = d.coordinates?.[1] ?? d.lon ?? 0;

      const ring = add(viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 500),
        cylinder: {
          length: 1000,
          topRadius: new Cesium.CallbackProperty(() => 4000 + Math.abs(Math.sin(performance.now() / 500)) * 6000, false),
          bottomRadius: new Cesium.CallbackProperty(() => 4000 + Math.abs(Math.sin(performance.now() / 500)) * 6000, false),
          material: new Cesium.CallbackProperty(() => COLORS.critical.withAlpha(0.15 + Math.abs(Math.sin(performance.now() / 500)) * 0.35), false) as any,
          outline: false,
        },
      }));
      (ring as any)._meta = { kind: 'disruption', data: d };

      const label = add(viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 12_000),
        label: {
          text: `⚠ ${(d.severity || 'alert').toUpperCase()}`,
          font: '700 14px monospace',
          fillColor: COLORS.critical,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 3,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      }));
      (label as any)._meta = { kind: 'disruption', data: d };
    });
  }, [topology]);

  // ─── Actions ────────────────────────────────────────────────────────────
  const triggerWhatIf = useCallback(async (_disruption: any) => {
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
      setWhatIf(data);
      addToast(`What-if complete — best: ${data.best_scenario?.label || 'N/A'}`, 'success');
    } catch {
      setWhatIf({ error: 'Simulation failed' });
    }
  }, [addToast]);

  const approveAndWriteBack = useCallback(async () => {
    setApproving(true);
    try {
      const res = await api.approveAllocation();
      setApproved(true);
      addToast(res.message || 'Approved & written to SAP', 'success');
      fetchTopology();
    } catch (e: any) {
      addToast(e.message || 'Approval failed', 'error');
    } finally {
      setApproving(false);
    }
  }, [addToast, fetchTopology]);

  // ─── Loading ────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 12, background: '#05070A', color: '#7C93A3' }}>
        <div className="spin" style={{ width: 20, height: 20, border: '2px solid #4CC9F0', borderTopColor: 'transparent', borderRadius: '50%' }} />
        <span style={{ fontFamily: 'monospace', fontSize: 13 }}>Loading 3D Globe…</span>
      </div>
    );
  }

  const state_machine = topology?.state_machine ?? { current_state: 'S1_STABLE', capacity_margin_pct: 0 };
  const audit = topology?.audit ?? { chain_hash: '', chain_valid: false, chain_length: 0 };
  const clinics = topology?.clinics ?? [];
  const routes = topology?.routes ?? [];

  return (
    <div style={S.root}>
      <div ref={containerRef} style={S.canvasHost} />

      {/* Top bar */}
      <div style={S.topBar}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <GlobeIcon size={16} color="#4CC9F0" />
          <span style={S.topBarTitle}>RESILIENCE GLOBE</span>
        </div>
        <span style={S.topBarSub}>
          {state_machine.current_state.replace(/_/g, ' ')} · {mapSource === 'google' ? '🛰 GOOGLE 3D' : '🗺 OSM'} · {clinics.length} CLINICS · {routes.length} ROUTES
        </span>
      </div>

      {/* HUD */}
      {hudEntity && (
        <div style={S.hud}>
          <div style={S.hudHeader}>
            <span style={S.hudKind}>{hudEntity.kind.toUpperCase()}</span>
            <button style={S.hudClose} onClick={() => setHudEntity(null)}>×</button>
          </div>
          {hudEntity.kind === 'route' && (
            <>
              <Row label="Vehicle" value={hudEntity.data.vehicle_id ?? '—'} />
              <Row label="Temp" value={`${hudEntity.data.ambient_temperature_celsius ?? '—'}°C`} />
              <Row label="Arrhenius k" value={hudEntity.data.arrhenius_decay_rate ?? '—'} />
              <Row label="Shelf Life" value={`${hudEntity.data.remaining_shelf_life_hours ?? '—'}h`} />
              <Row label="Status" value={(hudEntity.data.route_status ?? '—').replace(/_/g, ' ').toUpperCase()} accent={routeColor(hudEntity.data.route_status)} />
            </>
          )}
          {hudEntity.kind === 'clinic' && (
            <>
              <Row label="Clinic" value={hudEntity.data.name ?? hudEntity.data.id} />
              <Row label="Priority (Pᵢ)" value={hudEntity.data.priority_score?.toFixed(3) ?? '—'} />
              <Row label="Stock" value={`${hudEntity.data.stock_coverage_pct ?? '—'}%`} />
              <Row label="Shelf Life" value={`${hudEntity.data.remaining_shelf_life_hours ?? '—'}h`} />
              {hudEntity.data.is_dropped && <Row label="Status" value="DROPPED" accent={COLORS.dropped} />}
            </>
          )}
          {hudEntity.kind === 'hub' && (
            <>
              <Row label="Hub" value={hudEntity.data.name} />
              <Row label="Capacity" value={`${hudEntity.data.capacity_kg ?? '—'} kg`} />
            </>
          )}
          {hudEntity.kind === 'disruption' && (
            <>
              <Row label="Event" value={hudEntity.data.name} />
              <Row label="Severity" value={(hudEntity.data.severity ?? 'unknown').toUpperCase()} accent={COLORS.critical} />
              {hudEntity.data.description && <Row label="Detail" value={hudEntity.data.description.slice(0, 80) + '…'} />}
            </>
          )}
        </div>
      )}

      {/* What-If Panel */}
      {whatIf && (
        <div style={S.whatIf}>
          <div style={S.hudHeader}>
            <span style={S.hudKind}>WHAT-IF SCENARIO</span>
            <button style={S.hudClose} onClick={() => setWhatIf(null)}>×</button>
          </div>
          {whatIf.error ? (
            <div style={{ color: '#FF8A8A', fontFamily: 'monospace', fontSize: 12 }}>{whatIf.error}</div>
          ) : (
            <>
              {whatIf.results?.map((r: any, i: number) => (
                <div key={i} style={{ padding: '6px 0', borderBottom: '1px solid rgba(140,190,210,0.12)' }}>
                  <div style={{ color: '#E8F1F5', fontSize: 12, fontWeight: 600 }}>{r.label}</div>
                  <div style={{ color: '#8FA3B3', fontSize: 11 }}>w1={r.w1} w2={r.w2} w3={r.w3} · objective: {r.objective?.toFixed(3)}</div>
                </div>
              ))}
              {whatIf.best_scenario && (
                <div style={{ marginTop: 8, padding: '6px 10px', background: 'rgba(62,213,152,0.1)', borderRadius: 6, color: '#3ED598', fontSize: 12, fontWeight: 600 }}>
                  Best: {whatIf.best_scenario.label}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Governance Panel */}
      <div style={S.governance}>
        <div style={S.govLabel}>AUDIT HASH (SHA-256)</div>
        <div style={S.govHash}>{audit.chain_hash ? `${audit.chain_hash.slice(0, 16)}…` : 'awaiting…'}</div>
        <div style={{ color: audit.chain_valid ? '#3ED598' : '#FF3B3B', fontSize: 11, marginBottom: 8, fontFamily: 'monospace' }}>
          Chain: {audit.chain_length} records · {audit.chain_valid ? 'VALID ✓' : 'BROKEN'}
        </div>
        <button
          style={{ ...S.approveBtn, ...(approved ? S.approveBtnDone : {}), opacity: approving ? 0.55 : 1, cursor: approving || approved ? 'default' : 'pointer' }}
          disabled={approving || approved}
          onClick={approveAndWriteBack}
        >
          {approved ? '✓ WRITTEN TO SAP' : approving ? 'WRITING BACK…' : 'APPROVE & WRITE BACK TO SAP'}
        </button>
      </div>

      {/* Legend */}
      <div style={S.legend}>
        {([
          ['Nominal coverage', COLORS.nominal],
          ['Priority outbreak', COLORS.priority],
          ['Critical demand', COLORS.critical],
          ['Dropped site', COLORS.dropped],
          ['Selected route', COLORS.selected],
        ] as [string, Cesium.Color][]).map(([label, color]) => (
          <div key={label} style={S.legendRow}>
            <span style={{ ...S.legendDot, background: color.toCssColorString() }} />
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Row helper ───────────────────────────────────────────────────────────────
function Row({ label, value, accent }: { label: string; value: string; accent?: Cesium.Color }) {
  return (
    <div style={S.hudRow}>
      <span style={S.hudRowLabel}>{label}</span>
      <span style={{ ...S.hudRowValue, ...(accent ? { color: accent.toCssColorString() } : {}) }}>{value}</span>
    </div>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const GLASS = 'rgba(13, 18, 26, 0.78)';
const BORDER = 'rgba(140, 190, 210, 0.18)';

const S: Record<string, React.CSSProperties> = {
  root: { position: 'relative', width: '100%', height: '100%', minHeight: '100vh', background: '#05070A', overflow: 'hidden', fontFamily: 'Inter, system-ui, sans-serif' },
  canvasHost: { position: 'absolute', inset: 0 },
  topBar: { position: 'absolute', top: 16, left: 20, display: 'flex', flexDirection: 'column', gap: 4, pointerEvents: 'none', zIndex: 10 },
  topBarTitle: { color: '#E8F1F5', fontSize: 14, fontWeight: 700, letterSpacing: '0.14em' },
  topBarSub: { color: '#7C93A3', fontSize: 10, letterSpacing: '0.08em', fontFamily: 'monospace' },
  hud: { position: 'absolute', top: 16, right: 20, width: 300, background: GLASS, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '14px 16px', backdropFilter: 'blur(14px)', boxShadow: '0 8px 32px rgba(0,0,0,0.45)', zIndex: 20 },
  hudHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, borderBottom: `1px solid ${BORDER}`, paddingBottom: 8 },
  hudKind: { color: '#4CC9F0', fontSize: 11, fontWeight: 700, letterSpacing: '0.12em', fontFamily: 'monospace' },
  hudClose: { background: 'none', border: 'none', color: '#7C93A3', fontSize: 18, lineHeight: 1, cursor: 'pointer' },
  hudRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '4px 0', gap: 12 },
  hudRowLabel: { color: '#8FA3B3', fontSize: 11 },
  hudRowValue: { color: '#E8F1F5', fontSize: 12, fontWeight: 600, textAlign: 'right' as const },
  whatIf: { position: 'absolute', top: 16, right: 336, width: 320, maxHeight: 360, overflowY: 'auto', background: GLASS, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '14px 16px', backdropFilter: 'blur(14px)', boxShadow: '0 8px 32px rgba(0,0,0,0.45)', zIndex: 20 },
  governance: { position: 'absolute', bottom: 16, left: 20, width: 300, background: GLASS, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '12px 16px', backdropFilter: 'blur(14px)', boxShadow: '0 8px 32px rgba(0,0,0,0.45)', zIndex: 20 },
  govLabel: { color: '#7C93A3', fontSize: 10, letterSpacing: '0.1em', fontFamily: 'monospace' },
  govHash: { color: '#4CC9F0', fontSize: 12, fontFamily: 'monospace', margin: '4px 0 6px' },
  approveBtn: { width: '100%', padding: '10px 0', background: 'linear-gradient(180deg, #1B4A5A, #0F2E38)', border: '1px solid rgba(76,201,240,0.5)', color: '#E8F1F5', fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', borderRadius: 6, cursor: 'pointer' },
  approveBtnDone: { background: 'linear-gradient(180deg, #1B5A38, #0F3822)', border: '1px solid rgba(62,213,152,0.6)', color: '#B7F5D8' },
  legend: { position: 'absolute', bottom: 16, right: 20, background: GLASS, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '10px 14px', backdropFilter: 'blur(14px)', display: 'flex', flexDirection: 'column', gap: 6, zIndex: 20 },
  legendRow: { display: 'flex', alignItems: 'center', gap: 8, color: '#B8CBD6', fontSize: 11 },
  legendDot: { width: 8, height: 8, borderRadius: '50%', display: 'inline-block' },
};
