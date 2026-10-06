import { useEffect, useMemo, useRef, useState } from "react";
import { GeoJSON, LayersControl, MapContainer, TileLayer, useMap } from "react-leaflet";
import type { Feature, Geometry } from "geojson";
import L, { type Path, type PathOptions } from "leaflet";
import "leaflet/dist/leaflet.css";
import { ChevronDown, ChevronUp, Download, Image as ImageIcon } from "lucide-react";

import { buildBuckets, colorFor, formatValue, NO_DATA_COLOR } from "@/features/models/ccm/colorScale";
import { downloadBlob, downloadGeoJSON, mapFileStem } from "./export";
import type { MapResponse } from "@/lib/dfrmApi";

/** Jamuna basin — the extent DFRM covers (Jamalpur / Kurigram). */
const CENTER: [number, number] = [25.0, 89.7];
const ZOOM = 9;
const MAX_ZOOM = 16;

/** Selectable basemaps — same set Forecast-X offers (plain Leaflet). */
const BASEMAPS = [
  {
    name: "OpenStreetMap",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
  {
    name: "Light (CARTO)",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maxZoom: 19,
    subdomains: "abcd",
  },
  {
    name: "Satellite (Esri)",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, GIS User Community",
    maxZoom: 19,
  },
  {
    name: "Topographic",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution:
      'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, SRTM | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
    maxZoom: 17,
  },
] as const;

function featureName(p: Record<string, unknown>): string {
  return String(p.UNINAME ?? p.THANAME ?? p.DISTNAME ?? "");
}

/** Reframe on whatever is currently shown. */
function FitAndResize({ data }: { data: MapResponse | undefined }) {
  const map = useMap();
  // feature_count is in the signature so a merged multi-district view re-fits
  // once the second district's features arrive (otherwise part is cut off).
  const signature = `${data?.area_id}-${data?.layer}-${data?.day}-${data?.feature_count}`;
  useEffect(() => {
    const fit = () => {
      map.invalidateSize();
      if (!data || data.features.length === 0) return;
      try {
        const bounds = L.geoJSON(data as never).getBounds();
        if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 12 });
      } catch {
        /* a malformed geometry should never take the map down */
      }
    };
    // Fit now (once layout settles), and again whenever the container resizes
    // — window resize, sidebar toggle, tab switch. invalidateSize first so
    // Leaflet re-reads the new box, then re-centre the polygons with padding.
    const t = window.setTimeout(fit, 0);
    const container = map.getContainer();
    let raf = 0;
    const ro = new ResizeObserver(() => {
      window.cancelAnimationFrame(raf);
      raf = window.requestAnimationFrame(fit);
    });
    ro.observe(container);
    return () => {
      window.clearTimeout(t);
      window.cancelAnimationFrame(raf);
      ro.disconnect();
    };
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
        <LayersControl position="bottomright">
          {BASEMAPS.map((base, i) => (
            <LayersControl.BaseLayer key={base.name} name={base.name} checked={i === 0}>
              <TileLayer
                url={base.url}
                attribution={base.attribution}
                maxZoom={base.maxZoom}
                subdomains={"subdomains" in base ? base.subdomains : "abc"}
                crossOrigin="anonymous"
              />
            </LayersControl.BaseLayer>
          ))}
        </LayersControl>

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

        <FitAndResize data={data} />
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
  const [open, setOpen] = useState(true);
  return (
    // Top-right, below the export buttons — away from the centred polygons and
    // clear of the bottom-right layers control + attribution. Compact + collapsible.
    <div className="absolute right-3 top-16 z-[500] w-36 overflow-hidden rounded-md border border-navy-200 bg-white/95 shadow-sm backdrop-blur">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={open ? "Collapse legend" : "Expand legend"}
        className="flex w-full items-center justify-between gap-2 px-2.5 py-1.5"
      >
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {data.layer}
          {data.metric_unit ? ` (${data.metric_unit})` : ""}
        </span>
        {open ? (
          <ChevronUp className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        )}
      </button>
      {open && (
        <div className="px-2.5 pb-2">
          <ul className="space-y-0.5">
            {buckets.map((bucket) => (
              <li key={bucket.from} className="flex items-center gap-1.5">
                <span className="size-2.5 shrink-0 rounded-sm" style={{ background: bucket.color }} />
                <span className="text-[10px] tabular-nums text-navy-700">
                  {formatValue(bucket.from)} – {formatValue(bucket.to)}
                </span>
              </li>
            ))}
            <li className="flex items-center gap-1.5 border-t border-navy-200 pt-0.5">
              <span className="size-2.5 shrink-0 rounded-sm" style={{ background: NO_DATA_COLOR }} />
              <span className="text-[10px] text-muted-foreground">No data</span>
            </li>
          </ul>
          <p className="mt-1.5 border-t border-navy-200 pt-1 text-[9px] text-muted-foreground">
            {data.feature_count.toLocaleString()} areas · {data.day}
          </p>
        </div>
      )}
    </div>
  );
}
