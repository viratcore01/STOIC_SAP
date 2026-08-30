import { useEffect, useRef, useState, useCallback } from 'react';
import { api } from '../api';
import { Globe as GlobeIcon } from 'lucide-react';
import 'leaflet/dist/leaflet.css';

// ─── Config ───────────────────────────────────────────────────────────────────
const ION_TOKEN = (import.meta as any).env?.VITE_GOOGLE_MAPS_API_KEY as string | undefined;

const COLORS = {
  nominal: '#3ED598',
  priority: '#F4A100',
  critical: '#FF3B3B',
  dropped: '#5B6B78',
  hub: '#4CC9F0',
  selected: '#2FD8FF',
};

function clinicColorHex(c: any): string {
  if (c.is_dropped) return COLORS.dropped;
  if (c.criticality === 'critical') return COLORS.critical;
  if (c.criticality === 'high') return COLORS.priority;
  return COLORS.nominal;
}

function routeColorHex(status: string): string {
  if (status === 'thermal_breach') return COLORS.critical;
  if (status === 'thermal_warning') return COLORS.priority;
  return COLORS.nominal;
}

// ─── WebGL detection ──────────────────────────────────────────────────────────
// Default to Leaflet; upgrade to Cesium only after verifying it works
const USE_CESIUM = false;

// ─── Types ────────────────────────────────────────────────────────────────────
interface Topology {
  hubs: any[];
  clinics: any[];
  routes: any[];
  disruptions: any[];
  audit: { chain_hash: string; chain_valid: boolean; chain_length: number };
  state_machine: { current_state: string; capacity_margin_pct: number; total_demand: number; total_capacity: number };
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function ResilienceGlobeView({ addToast }: { addToast: (msg: string, type?: 'success' | 'error') => void }) {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [loading, setLoading] = useState(true);
  const [hudEntity, setHudEntity] = useState<{ kind: string; data: any } | null>(null);
  const [whatIf, setWhatIf] = useState<any>(null);
  const [mapSource, setMapSource] = useState('loading');
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(false);

  const [useCesium, setUseCesium] = useState(USE_CESIUM);

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

  // ─── Actions ────────────────────────────────────────────────────────────
  const triggerWhatIf = useCallback(async () => {
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
        <span style={{ fontFamily: 'monospace', fontSize: 13 }}>Loading Globe…</span>
      </div>
    );
  }

  const state_machine = topology?.state_machine ?? { current_state: 'S1_STABLE', capacity_margin_pct: 0 };
  const audit = topology?.audit ?? { chain_hash: '', chain_valid: false, chain_length: 0 };
  const clinics = topology?.clinics ?? [];
  const routes = topology?.routes ?? [];

  return (
    <div style={S.root}>
      {/* Map Container — either CesiumJS or Leaflet */}
      {useCesium ? (
        <CesiumGlobe
          topology={topology}
          onEntityClick={setHudEntity}
          onDisruptionClick={triggerWhatIf}
          onReady={setMapSource}
          onError={(msg) => { console.warn(msg); setUseCesium(false); }}
        />
      ) : (
        <LeafletMap
          topology={topology}
          onMarkerClick={setHudEntity}
          onDisruptionClick={triggerWhatIf}
        />
      )}

      {/* Top bar */}
      <div style={S.topBar}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <GlobeIcon size={16} color="#4CC9F0" />
          <span style={S.topBarTitle}>RESILIENCE GLOBE</span>
        </div>
        <span style={S.topBarSub}>
          {state_machine.current_state.replace(/_/g, ' ')} · {useCesium ? (mapSource === 'google' ? '🛰 GOOGLE 3D' : '🗺 CesiumJS OSM') : '🗺 Leaflet Dark'} · {clinics.length} CLINICS · {routes.length} ROUTES
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
              <Row label="Arrhenius k" value={String(hudEntity.data.arrhenius_decay_rate ?? '—')} />
              <Row label="Shelf Life" value={`${hudEntity.data.remaining_shelf_life_hours ?? '—'}h`} />
              <Row label="Status" value={(hudEntity.data.route_status ?? '—').replace(/_/g, ' ').toUpperCase()} accent={routeColorHex(hudEntity.data.route_status)} />
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
        {[
          ['Nominal coverage', COLORS.nominal],
          ['Priority outbreak', COLORS.priority],
          ['Critical demand', COLORS.critical],
          ['Dropped site', COLORS.dropped],
          ['Selected route', COLORS.selected],
        ].map(([label, color]) => (
          <div key={label} style={S.legendRow}>
            <span style={{ ...S.legendDot, background: color }} />
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// LEAFLET FALLBACK — 2D dark map, works without WebGL
// =============================================================================
function LeafletMap({ topology, onMarkerClick, onDisruptionClick }: {
  topology: Topology | null;
  onMarkerClick: (h: { kind: string; data: any } | null) => void;
  onDisruptionClick: (d: any) => void;
}) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    // Dynamic import for L
    import('leaflet').then((L) => {
      if (!mapRef.current || mapInstanceRef.current) return;

      const map = L.map(mapRef.current, {
        center: [20, 30],
        zoom: 3,
        zoomControl: false,
        attributionControl: false,
      });

      // Free dark map tiles (no API key needed)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap',
      }).addTo(map);
      // Apply dark filter via CSS
      map.getContainer().style.filter = 'invert(0.92) hue-rotate(180deg) brightness(0.8) contrast(1.2)';

      L.control.zoom({ position: 'topright' }).addTo(map);

      mapInstanceRef.current = map;

      // Force resize after mount
      setTimeout(() => map.invalidateSize(), 200);
    });

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  // Render entities when topology changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !topology) return;

    // Clear existing layers except tiles
    map.eachLayer((layer: any) => {
      if (layer._url || !layer._latlng) {
        // Keep tile layers
      } else {
        map.removeLayer(layer);
      }
    });

    // Dynamic import for L
    import('leaflet').then((L) => {
      // Hubs
      (topology.hubs || []).forEach((hub) => {
        const lat = hub.coordinates?.[0] ?? hub.lat ?? 0;
        const lon = hub.coordinates?.[1] ?? hub.lon ?? 0;
        const marker = L.circleMarker([lat, lon], {
          radius: 14,
          fillColor: COLORS.hub,
          fillOpacity: 0.9,
          color: '#fff',
          weight: 2,
        }).addTo(map);
        marker.bindTooltip(`${hub.name} · HUB`, {
          permanent: true,
          direction: 'top',
          offset: [0, -10],
          className: 'dark-tooltip',
        });
        marker.on('click', () => onMarkerClick({ kind: 'hub', data: hub }));
      });

      // Clinics
      (topology.clinics || []).forEach((clinic) => {
        const lat = clinic.coordinates?.[0] ?? clinic.lat ?? 0;
        const lon = clinic.coordinates?.[1] ?? clinic.lon ?? 0;
        const color = clinicColorHex(clinic);
        const marker = L.circleMarker([lat, lon], {
          radius: clinic.is_dropped ? 6 : 9,
          fillColor: color,
          fillOpacity: clinic.is_dropped ? 0.4 : 0.85,
          color: '#fff',
          weight: clinic.is_dropped ? 1 : 2,
          dashArray: clinic.is_dropped ? '4 4' : undefined,
        }).addTo(map);
        marker.bindTooltip(`${clinic.name}${clinic.is_dropped ? ' (DROPPED)' : ''}`, {
          permanent: false,
          direction: 'top',
          offset: [0, -8],
          className: 'dark-tooltip',
        });
        marker.on('click', () => onMarkerClick({ kind: 'clinic', data: clinic }));
      });

      // Routes as polylines
      (topology.routes || []).forEach((route) => {
        const origin = route.origin || [route.from?.[1], route.from?.[0]];
        const dest = route.destination || [route.to?.[1], route.to?.[0]];
        if (!origin || !dest) return;
        const color = routeColorHex(route.route_status);
        const line = L.polyline(
          [[origin[0], origin[1]], [dest[0], dest[1]]],
          {
            color,
            weight: route.route_status === 'thermal_breach' ? 4 : 2,
            opacity: route.route_status === 'thermal_breach' ? 0.9 : 0.5,
            dashArray: route.route_status === 'thermal_warning' ? '8 6' : undefined,
          }
        ).addTo(map);
        line.on('click', () => onMarkerClick({ kind: 'route', data: route }));
      });

      // Disruptions as pulsing red markers
      (topology.disruptions || []).forEach((d: any) => {
        const lat = d.coordinates?.[0] ?? d.lat ?? 0;
        const lon = d.coordinates?.[1] ?? d.lon ?? 0;
        const marker = L.circleMarker([lat, lon], {
          radius: 18,
          fillColor: COLORS.critical,
          fillOpacity: 0.3,
          color: COLORS.critical,
          weight: 2,
        }).addTo(map);
        // Inner ring
        L.circleMarker([lat, lon], {
          radius: 8,
          fillColor: COLORS.critical,
          fillOpacity: 0.7,
          color: COLORS.critical,
          weight: 1,
        }).addTo(map);
        marker.bindTooltip(`⚠ ${(d.severity || 'alert').toUpperCase()}: ${d.name}`, {
          permanent: true,
          direction: 'top',
          offset: [0, -20],
          className: 'dark-tooltip alert-tooltip',
        });
        marker.on('click', () => onMarkerClick({ kind: 'disruption', data: d }));
        // Double-click triggers what-if
        marker.on('dblclick', () => {
          onDisruptionClick(d);
        });
      });

      // Fit bounds to show all entities
      const allLats: number[] = [];
      const allLons: number[] = [];
      [...(topology.hubs || []), ...(topology.clinics || []), ...(topology.disruptions || [])].forEach((p) => {
        allLats.push(p.coordinates?.[0] ?? p.lat ?? 0);
        allLons.push(p.coordinates?.[1] ?? p.lon ?? 0);
      });
      if (allLats.length > 0) {
        map.fitBounds([[Math.min(...allLats), Math.min(...allLons)], [Math.max(...allLats), Math.max(...allLons)]], { padding: [40, 40] });
      }
    });
  }, [topology, onMarkerClick, onDisruptionClick]);

  return <div ref={mapRef} style={{ position: 'absolute', inset: 0, background: '#0a0f1a' }} />;
}

// =============================================================================
// CESIUM 3D GLOBE — full WebGL 3D experience
// =============================================================================
function CesiumGlobe({ topology, onEntityClick, onDisruptionClick, onReady, onError }: {
  topology: Topology | null;
  onEntityClick: (h: { kind: string; data: any } | null) => void;
  onDisruptionClick: (d: any) => void;
  onReady: (source: string) => void;
  onError: (msg: string | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);
  const entitiesRef = useRef<any[]>([]);

  // Viewer bootstrap
  useEffect(() => {
    let destroyed = false;
    let resizeObs: ResizeObserver | null = null;

    async function init() {
      try {
        const Cesium = await import('cesium');
        await import('cesium/Build/Cesium/Widgets/widgets.css');
        if (destroyed || !containerRef.current) return;

        if (ION_TOKEN) Cesium.Ion.defaultAccessToken = ION_TOKEN;

        const viewer = new Cesium.Viewer(containerRef.current, {
          timeline: false,
          animation: false,
          sceneModePicker: false,
          baseLayerPicker: false,
          geocoder: false,
          homeButton: false,
          navigationHelpButton: false,
          fullscreenButton: false,
          infoBox: false,
          selectionIndicator: false,
          shadows: false,
          contextOptions: { webgl: { alpha: false } },
        });

        if (viewer.scene.skyAtmosphere) {
          viewer.scene.skyAtmosphere.show = true;
        }
        viewer.scene.fog.enabled = true;
        try { (viewer as any)._cesiumWidget._creditContainer.style.display = 'none'; } catch {}

        // Try Google 3D Tiles, fallback to OSM
        let source = 'osm';
        if (ION_TOKEN) {
          try {
            const tileset = await (Cesium as any).createGooglePhotorealistic3DTileset({ onlyUsingWithGoogleGeocoder: false });
            if (!destroyed) {
              viewer.scene.primitives.add(tileset);
              source = 'google';
            } else {
              tileset.destroy?.();
            }
          } catch { /* fallback */ }
        }
        if (!destroyed) {
          try {
            viewer.imageryLayers.removeAll();
            viewer.imageryLayers.addImageryProvider(
              new Cesium.OpenStreetMapImageryProvider({ url: 'https://tile.openstreetmap.org/' })
            );
          } catch { /* ok */ }
          onReady(source);
        }

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
            onEntityClick(null);
            return;
          }
          const meta = (picked as any).id._meta;
          if (!meta) { onEntityClick(null); return; }
          onEntityClick(meta);
          if (meta.kind !== 'route') {
            const d = meta.data;
            viewer.camera.flyTo({
              destination: Cesium.Cartesian3.fromDegrees(d.coordinates?.[1] ?? d.lon ?? 0, d.coordinates?.[0] ?? d.lat ?? 0, 3_500),
              orientation: { heading: 0, pitch: Cesium.Math.toRadians(-45), roll: 0 },
              duration: 2.0,
            });
          }
          if (meta.kind === 'disruption') onDisruptionClick(meta.data);
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        if (!destroyed) {
          viewerRef.current = viewer;
          resizeObs = new ResizeObserver(() => viewer.resize());
          resizeObs.observe(containerRef.current);
        } else {
          handler.destroy();
          viewer.destroy();
        }
      } catch (err) {
        console.error('CesiumJS init failed:', err);
        onError('3D globe unavailable — showing 2D map');
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

  // Entity rendering
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !topology) return;

    // Lazy load Cesium for entity types
    import('cesium').then((Cesium) => {
      // Clear
      entitiesRef.current.forEach((e) => viewer.entities.remove(e));
      entitiesRef.current = [];
      const add = (e: any) => { entitiesRef.current.push(e); return e; };

      // Hubs
      (topology.hubs || []).forEach((hub) => {
        const lat = hub.coordinates?.[0] ?? hub.lat ?? 0;
        const lon = hub.coordinates?.[1] ?? hub.lon ?? 0;
        const pillar = add(viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 60_000),
          cylinder: { length: 120_000, topRadius: 200, bottomRadius: 10_000, material: Cesium.Color.fromCssColorString(COLORS.hub).withAlpha(0.35), outline: true, outlineColor: Cesium.Color.fromCssColorString(COLORS.hub).withAlpha(0.9) },
        }));
        pillar._meta = { kind: 'hub', data: hub };
        const label = add(viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 130_000),
          label: { text: `${(hub.name || '').toUpperCase()} · HUB`, font: '600 14px monospace', fillColor: Cesium.Color.fromCssColorString(COLORS.hub), outlineColor: Cesium.Color.BLACK, outlineWidth: 3, style: Cesium.LabelStyle.FILL_AND_OUTLINE, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        }));
        label._meta = { kind: 'hub', data: hub };
      });

      // Clinics
      (topology.clinics || []).forEach((clinic) => {
        const lat = clinic.coordinates?.[0] ?? clinic.lat ?? 0;
        const lon = clinic.coordinates?.[1] ?? clinic.lon ?? 0;
        const color = Cesium.Color.fromCssColorString(clinicColorHex(clinic));
        const e = add(viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 800),
          ellipsoid: { radii: new Cesium.Cartesian3(900, 900, 900), material: color.withAlpha(clinic.is_dropped ? 0.35 : 0.85), outline: true, outlineColor: Cesium.Color.WHITE.withAlpha(0.4) },
          label: { text: clinic.name || clinic.id, font: '500 12px monospace', fillColor: color, outlineColor: Cesium.Color.BLACK, outlineWidth: 2, style: Cesium.LabelStyle.FILL_AND_OUTLINE, pixelOffset: new Cesium.Cartesian2(0, -18), disableDepthTestDistance: Number.POSITIVE_INFINITY },
        }));
        e._meta = { kind: 'clinic', data: clinic };
      });

      // Routes
      (topology.routes || []).forEach((route) => {
        const origin = route.origin || [route.from?.[1], route.from?.[0]];
        const dest = route.destination || [route.to?.[1], route.to?.[0]];
        if (!origin || !dest) return;
        const color = Cesium.Color.fromCssColorString(routeColorHex(route.route_status));
        const isPulse = route.route_status === 'thermal_warning';
        const isFlash = route.route_status === 'thermal_breach';
        const colorProp = (isPulse || isFlash)
          ? new Cesium.CallbackProperty(() => {
              const t = performance.now() / (isFlash ? 220 : 650);
              const phase = (Math.sin(t) + 1) / 2;
              return color.withAlpha(isFlash ? 0.35 + phase * 0.65 : 0.5 + phase * 0.5);
            }, false)
          : color.withAlpha(0.9);

        const s = Cesium.Cartographic.fromDegrees(origin[1], origin[0]);
        const e2 = Cesium.Cartographic.fromDegrees(dest[1], dest[0]);
        const sC = Cesium.Cartographic.toCartesian(s);
        const eC = Cesium.Cartographic.toCartesian(e2);
        const dist = Cesium.Cartesian3.distance(sC, eC);
        const arcH = dist * 0.08;
        const positions: any[] = [];
        for (let i = 0; i <= 48; i++) {
          const t = i / 48;
          const pos = Cesium.Cartesian3.lerp(sC, eC, t, new Cesium.Cartesian3());
          const carto = Cesium.Cartographic.fromCartesian(pos);
          const h = carto.height + arcH * Math.sin(Math.PI * t);
          positions.push(Cesium.Cartographic.toCartesian(Cesium.Cartographic.fromRadians(carto.longitude, carto.latitude, h)));
        }

        const entity = add(viewer.entities.add({
          polyline: { positions, width: isFlash ? 5 : 3, arcType: Cesium.ArcType.GEODESIC, material: new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.25, color: colorProp }), clampToGround: false },
        }));
        entity._meta = { kind: 'route', data: route };
      });

      // Disruptions
      (topology.disruptions || []).forEach((d: any) => {
        const lat = d.coordinates?.[0] ?? d.lat ?? 0;
        const lon = d.coordinates?.[1] ?? d.lon ?? 0;
        const ring = add(viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 500),
          cylinder: {
            length: 1000,
            topRadius: new Cesium.CallbackProperty(() => 4000 + Math.abs(Math.sin(performance.now() / 500)) * 6000, false),
            bottomRadius: new Cesium.CallbackProperty(() => 4000 + Math.abs(Math.sin(performance.now() / 500)) * 6000, false),
            material: new Cesium.CallbackProperty(() => Cesium.Color.fromCssColorString(COLORS.critical).withAlpha(0.15 + Math.abs(Math.sin(performance.now() / 500)) * 0.35), false) as any,
          },
        }));
        ring._meta = { kind: 'disruption', data: d };
        const label = add(viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 12_000),
          label: { text: `⚠ ${(d.severity || 'alert').toUpperCase()}`, font: '700 14px monospace', fillColor: Cesium.Color.fromCssColorString(COLORS.critical), outlineColor: Cesium.Color.BLACK, outlineWidth: 3, style: Cesium.LabelStyle.FILL_AND_OUTLINE, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        }));
        label._meta = { kind: 'disruption', data: d };
      });
    });
  }, [topology]);

  return <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />;
}

// ─── Row helper ───────────────────────────────────────────────────────────────
function Row({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div style={S.hudRow}>
      <span style={S.hudRowLabel}>{label}</span>
      <span style={{ ...S.hudRowValue, ...(accent ? { color: accent } : {}) }}>{value}</span>
    </div>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const GLASS = 'rgba(13, 18, 26, 0.82)';
const BORDER = 'rgba(140, 190, 210, 0.18)';

const S: Record<string, React.CSSProperties> = {
  root: { position: 'relative', width: '100vw', height: 'calc(100vh - 60px)', background: '#05070A', overflow: 'hidden', fontFamily: 'Inter, system-ui, sans-serif' },
  topBar: { position: 'absolute', top: 16, left: 20, display: 'flex', flexDirection: 'column', gap: 4, pointerEvents: 'none', zIndex: 10 },
  topBarTitle: { color: '#E8F1F5', fontSize: 14, fontWeight: 700, letterSpacing: '0.14em' },
  topBarSub: { color: '#7C93A3', fontSize: 10, letterSpacing: '0.08em', fontFamily: 'monospace' },
  errorBanner: { position: 'absolute', top: 60, left: '50%', transform: 'translateX(-50%)', background: 'rgba(255,59,59,0.15)', border: '1px solid rgba(255,59,59,0.4)', color: '#FF8A8A', fontSize: 12, padding: '8px 14px', borderRadius: 8, fontFamily: 'monospace', backdropFilter: 'blur(6px)', zIndex: 30 },
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
