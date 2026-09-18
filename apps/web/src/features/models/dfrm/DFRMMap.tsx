import { useEffect, useMemo, useRef, useState } from "react";
import { GeoJSON, MapContainer, Pane, TileLayer, useMap } from "react-leaflet";
import type { Feature, Geometry } from "geojson";
import L, { type Path, type PathOptions } from "leaflet";
import "leaflet/dist/leaflet.css";
import { Download, Image as ImageIcon } from "lucide-react";

import { buildBuckets, colorFor, formatValue, NO_DATA_COLOR } from "@/features/models/ccm/colorScale";
import { downloadBlob, downloadGeoJSON, mapFileStem } from "./export";
import type { MapResponse } from "@/lib/dfrmApi";

/** Jamuna basin — the extent DFRM covers (Jamalpur / Kurigram). */
const CENTER: [number, number] = [25.0, 89.7];
const ZOOM = 9;
const MAX_ZOOM = 16;

const ESRI_BASE =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const ESRI_LABELS =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
const ESRI_ATTRIBUTION =
  'Tiles &copy; <a href="https://www.esri.com/">Esri</a> — Esri, DeLorme, NAVTEQ';

function featureName(p: Record<string, unknown>): string {
  return String(p.UNINAME ?? p.THANAME ?? p.DISTNAME ?? "");
}

/** Reframe on whatever is currently shown. */
function FitToData({ data }: { data: MapResponse | undefined }) {
  const map = useMap();
  const signature = `${data?.area_id}-${data?.layer}-${data?.day}`;
  useEffect(() => {
    if (!data || data.features.length === 0) return;
    try {
      const bounds = L.geoJSON(data as never).getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 12 });
    } catch {
      /* a malformed geometry should never take the map down */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, map]);
  return null;
}

export function DFRMMap({ data, loading }: { data: MapResponse | undefined; loading: boolean }) {
  const captureRef = useRef<HTMLDivElement>(null);
  const [saving, setSaving] = useState(false);

  const buckets = useMemo(
    () => buildBuckets(data?.metric_unit ?? "", data?.metric_min ?? null, data?.metric_max ?? null),
    [data?.metric_unit, data?.metric_min, data?.metric_max],
  );

  const savePng = async () => {
    if (!captureRef.current || !data) return;
    setSaving(true);
    try {
      // Import lazily so the export lib isn't in the initial bundle.
      const { toPng } = await import("html-to-image");
      const url = await toPng(captureRef.current, {
        cacheBust: true,
        pixelRatio: 2,
        // Don't rasterise the export toolbar itself.
        filter: (node) => !(node instanceof HTMLElement && node.dataset.export === "skip"),
      });
      const blob = await (await fetch(url)).blob();
      downloadBlob(blob, `${mapFileStem(data)}.png`);
    } catch {
      // Tainted canvas (tile CORS) or unsupported browser — fall back to data.
      downloadGeoJSON(data);
    } finally {
      setSaving(false);
    }
  };

  const layerKey = `${data?.area_id}-${data?.layer}-${data?.day}-${data?.feature_count}`;

  const style = (feature?: Feature<Geometry, Record<string, unknown>>): PathOptions => ({
    fillColor: colorFor(feature?.properties?.value as number | null | undefined, buckets),
    fillOpacity: 0.8,
    color: "#55809D",
    weight: 0.6,
    opacity: 0.7,
  });

  const onEachFeature = (feature: Feature<Geometry, Record<string, unknown>>, layer: Path) => {
    const p = feature.properties ?? {};
    const unit = data?.metric_unit ?? "";
    layer.bindTooltip(
      `<div style="font-family:Roboto,sans-serif;font-size:12px;line-height:1.5">
         <strong style="color:#053244">${featureName(p)}</strong><br/>
         <span style="color:#55809D">${p.THANAME ?? ""}${p.DISTNAME ? `, ${p.DISTNAME}` : ""}</span><br/>
         <strong>${data?.layer ?? "Value"}:</strong> ${formatValue(p.value as number, unit)}
       </div>`,
      { sticky: true },
    );
  };

  return (
    <div className="relative h-full w-full">
      <div ref={captureRef} className="relative h-full w-full">
      <MapContainer
        center={CENTER}
        zoom={ZOOM}
        maxZoom={MAX_ZOOM}
        scrollWheelZoom
        className="h-full w-full rounded-b-card"
        style={{ background: "#EFF4F7" }}
      >
        <TileLayer url={ESRI_BASE} attribution={ESRI_ATTRIBUTION} maxZoom={MAX_ZOOM} crossOrigin="anonymous" />

        {/* River corridor (soft) then active channel (blue), under the choropleth. */}
        {data && data.rivers.corridor.features.length > 0 && (
          <GeoJSON
            key={`corridor-${layerKey}`}
            data={data.rivers.corridor as never}
            style={{ fillColor: "#9CC3DD", fillOpacity: 0.15, color: "#55809D", weight: 0.4, opacity: 0.4 } as PathOptions}
            interactive={false}
          />
        )}
        {data && data.rivers.active.features.length > 0 && (
          <GeoJSON
            key={`active-${layerKey}`}
            data={data.rivers.active as never}
            style={{ fillColor: "#5FA8D3", fillOpacity: 0.35, color: "#3E7CB1", weight: 0.5, opacity: 0.6 } as PathOptions}
            interactive={false}
          />
        )}

        {data && data.features.length > 0 && (
          <GeoJSON
            key={layerKey}
            data={data as never}
            style={style as never}
            onEachFeature={onEachFeature as never}
          />
        )}

        {/* Admin outlines (from the DFRM geometry) drawn over the choropleth so
            upazila/district boundaries stay legible. Non-interactive. */}
        {data && data.context.upazila.features.length > 0 && (
          <GeoJSON
            key={`upz-${layerKey}`}
            data={data.context.upazila as never}
            style={{ fill: false, color: "#053244", weight: 1.2, opacity: 0.85, dashArray: "5 3" } as PathOptions}
            interactive={false}
          />
        )}
        {data && data.context.district.features.length > 0 && (
          <GeoJSON
            key={`dist-${layerKey}`}
            data={data.context.district as never}
            style={{ fill: false, color: "#053244", weight: 2, opacity: 0.9 } as PathOptions}
            interactive={false}
          />
        )}

        <Pane name="labels" style={{ zIndex: 450, pointerEvents: "none" }}>
          <TileLayer url={ESRI_LABELS} maxZoom={MAX_ZOOM} crossOrigin="anonymous" />
        </Pane>

        <FitToData data={data} />
      </MapContainer>

      {data && data.features.length > 0 && <MapLegend data={data} buckets={buckets} />}
      </div>

      {/* Export toolbar — excluded from the PNG capture. */}
      {data && data.features.length > 0 && (
        <div data-export="skip" className="absolute right-3 top-3 z-[600] flex gap-1.5">
          <button
            type="button"
            onClick={savePng}
            disabled={saving}
            title="Save the map as a PNG image"
            className="flex items-center gap-1.5 rounded-md border border-navy-200 bg-white/95 px-2.5 py-1.5 text-xs font-medium text-navy-800 shadow-sm backdrop-blur hover:border-green-700 disabled:opacity-60"
          >
            <ImageIcon className="size-3.5" />
            {saving ? "Saving…" : "PNG"}
          </button>
          <button
            type="button"
            onClick={() => downloadGeoJSON(data)}
            title="Download the map layers as GeoJSON"
            className="flex items-center gap-1.5 rounded-md border border-navy-200 bg-white/95 px-2.5 py-1.5 text-xs font-medium text-navy-800 shadow-sm backdrop-blur hover:border-green-700"
          >
            <Download className="size-3.5" />
            GeoJSON
          </button>
        </div>
      )}

      {loading && (
        <div className="pointer-events-none absolute inset-0 z-[500] flex items-center justify-center bg-navy-50/60">
          <span className="rounded-full bg-white px-4 py-2 text-sm font-medium text-foreground shadow-sm">
            Rendering map…
          </span>
        </div>
      )}
    </div>
  );
}

function MapLegend({
  data,
  buckets,
}: {
  data: MapResponse;
  buckets: ReturnType<typeof buildBuckets>;
}) {
  return (
    <div className="absolute bottom-4 left-4 z-[500] rounded-card border border-navy-200 bg-white/95 px-3 py-2.5 backdrop-blur">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {data.layer}
        {data.metric_unit ? ` (${data.metric_unit})` : ""}
      </p>
      <ul className="mt-2 space-y-1">
        {buckets.map((bucket) => (
          <li key={bucket.from} className="flex items-center gap-2">
            <span className="size-3 shrink-0 rounded-sm" style={{ background: bucket.color }} />
            <span className="text-[11px] tabular-nums text-navy-700">
              {formatValue(bucket.from)} – {formatValue(bucket.to)}
            </span>
          </li>
        ))}
        <li className="flex items-center gap-2 border-t border-navy-200 pt-1">
          <span className="size-3 shrink-0 rounded-sm" style={{ background: NO_DATA_COLOR }} />
          <span className="text-[11px] text-muted-foreground">No data</span>
        </li>
      </ul>
      <p className="mt-2 border-t border-navy-200 pt-1.5 text-[10px] text-muted-foreground">
        {data.feature_count.toLocaleString()} areas · hydrograph {data.day}
      </p>
    </div>
  );
}
