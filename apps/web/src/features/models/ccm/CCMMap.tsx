import { useEffect, useMemo } from "react";
import { GeoJSON, MapContainer, Pane, TileLayer, useMap } from "react-leaflet";
import type { Feature, Geometry } from "geojson";
import L, { type LeafletMouseEvent, type Path, type PathOptions } from "leaflet";
import "leaflet/dist/leaflet.css";

import { buildBuckets, colorFor, formatValue, NO_DATA_COLOR } from "./colorScale";
import type { MapResponse } from "@/lib/ccmApi";

/** Coastal Bangladesh — the extent the CCM reports on. */
const CENTER: [number, number] = [22.2, 90.2];
const ZOOM = 7;
const MAX_ZOOM = 16;

/**
 * Esri's light grey canvas. Free to use without a key, and deliberately
 * desaturated — the design guideline wants the base map quiet so the data is
 * the only saturated colour on screen. Labels come as a separate layer so they
 * can sit *above* the choropleth and stay readable.
 */
const ESRI_BASE =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const ESRI_LABELS =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
const ESRI_ATTRIBUTION =
  'Tiles &copy; <a href="https://www.esri.com/">Esri</a> — Esri, DeLorme, NAVTEQ';

type CCMMapProps = {
  data: MapResponse | undefined;
  loading: boolean;
  onSelect?: (properties: Record<string, unknown>) => void;
};

/** Zoom to whatever is currently shown, so drilling into a district reframes. */
function FitToData({ data }: { data: MapResponse | undefined }) {
  const map = useMap();
  const signature = `${data?.feature_count}-${data?.features?.[0]?.id ?? ""}`;

  useEffect(() => {
    if (!data || data.features.length === 0) return;
    try {
      const bounds = L.geoJSON(data as never).getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [24, 24], maxZoom: 11 });
      }
    } catch {
      // A malformed geometry should never take the whole map down.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, map]);

  return null;
}

export function CCMMap({ data, loading, onSelect }: CCMMapProps) {
  const buckets = useMemo(
    () => buildBuckets(data?.metric_unit ?? "", data?.metric_min ?? null, data?.metric_max ?? null),
    [data?.metric_unit, data?.metric_min, data?.metric_max],
  );

  // Re-key the layer whenever the data changes — Leaflet will not diff GeoJSON.
  const layerKey = `${data?.metric}-${data?.feature_count}-${data?.metric_min}-${data?.metric_max}`;

  const style = (feature?: Feature<Geometry, Record<string, unknown>>): PathOptions => {
    const value = feature?.properties?.value as number | null | undefined;
    return {
      fillColor: colorFor(value, buckets),
      fillOpacity: 0.75,
      color: "#55809D", // navy-500 boundary, per the design guideline
      weight: 0.5,
      opacity: 0.6,
    };
  };

  const onEachFeature = (
    feature: Feature<Geometry, Record<string, unknown>>,
    layer: Path,
  ) => {
    const p = feature.properties ?? {};
    const unit = data?.metric_unit ?? "";
    layer.bindTooltip(
      `<div style="font-family:Roboto,sans-serif;font-size:12px;line-height:1.5">
         <strong style="color:#053244">${p.union_name ?? ""}</strong><br/>
         <span style="color:#55809D">${p.upazila ?? ""}, ${p.district ?? ""}</span><br/>
         <strong>${data?.metric_label ?? "Value"}:</strong>
         ${formatValue(p.value as number, unit)}
       </div>`,
      { sticky: true },
    );
    layer.on({
      click: () => onSelect?.(p),
      mouseover: (event: LeafletMouseEvent) => {
        const target = event.target as Path;
        target.setStyle({ weight: 2, color: "#053244", fillOpacity: 0.9 });
        target.bringToFront();
      },
      mouseout: (event: LeafletMouseEvent) => {
        (event.target as Path).setStyle(style(feature));
      },
    });
  };

  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={CENTER}
        zoom={ZOOM}
        maxZoom={MAX_ZOOM}
        scrollWheelZoom
        className="h-full w-full rounded-b-card"
        style={{ background: "#EFF4F7" }}
      >
        <TileLayer url={ESRI_BASE} attribution={ESRI_ATTRIBUTION} maxZoom={MAX_ZOOM} />

        {data && data.features.length > 0 && (
          <GeoJSON
            key={layerKey}
            data={data as never}
            style={style as never}
            onEachFeature={onEachFeature as never}
          />
        )}

        {/* Place names sit above the choropleth so they stay readable.
            Clicks pass straight through to the unions underneath. */}
        <Pane name="labels" style={{ zIndex: 450, pointerEvents: "none" }}>
          <TileLayer url={ESRI_LABELS} maxZoom={MAX_ZOOM} />
        </Pane>

        <FitToData data={data} />
      </MapContainer>

      {loading && (
        <div className="pointer-events-none absolute inset-0 z-[500] flex items-center justify-center bg-navy-50/60">
          <span className="rounded-full bg-white px-4 py-2 text-sm font-medium text-foreground shadow-sm">
            Loading map…
          </span>
        </div>
      )}

      {!loading && data && data.features.length === 0 && (
        <div className="pointer-events-none absolute inset-0 z-[500] flex items-center justify-center bg-navy-50/80">
          <div className="max-w-xs rounded-card border border-navy-200 bg-white px-5 py-4 text-center">
            <p className="text-sm font-medium">Nothing matches</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Try a lower threshold, or a wider area.
            </p>
          </div>
        </div>
      )}

      {data && data.features.length > 0 && <MapLegend data={data} buckets={buckets} />}
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
        {data.metric_label}
        {data.metric_unit ? ` (${data.metric_unit})` : ""}
      </p>
      <ul className="mt-2 space-y-1">
        {buckets.map((bucket) => (
          <li key={bucket.from} className="flex items-center gap-2">
            <span
              className="size-3 shrink-0 rounded-sm"
              style={{ background: bucket.color }}
            />
            <span className="text-[11px] tabular-nums text-navy-700">
              {formatValue(bucket.from)} – {formatValue(bucket.to)}
            </span>
          </li>
        ))}
        <li className="flex items-center gap-2 border-t border-navy-200 pt-1">
          <span
            className="size-3 shrink-0 rounded-sm"
            style={{ background: NO_DATA_COLOR }}
          />
          <span className="text-[11px] text-muted-foreground">No data</span>
        </li>
      </ul>
      <p className="mt-2 border-t border-navy-200 pt-1.5 text-[10px] text-muted-foreground">
        {data.feature_count.toLocaleString()} unions shown
      </p>
    </div>
  );
}
