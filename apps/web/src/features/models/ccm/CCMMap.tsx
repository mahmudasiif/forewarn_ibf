import { useEffect, useMemo } from "react";
import { GeoJSON, MapContainer, Pane, TileLayer, useMap } from "react-leaflet";
import type { Feature, Geometry } from "geojson";
import L, {
  type LeafletMouseEvent,
  type Path,
  type PathOptions,
} from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  buildBuckets,
  colorFor,
  formatValue,
  NO_DATA_COLOR,
} from "./colorScale";
import type {
  BoundaryResponse,
  MapResponse,
  TrackResponse,
} from "@/lib/ccmApi";

/** Coastal Bangladesh — the extent the CCM reports on. */
const CENTER: [number, number] = [22.2, 90.2];
const ZOOM = 7;
const MAX_ZOOM = 16;

/**
 * Plain OpenStreetMap, one tile layer, no overlays on top of it. The earlier
 * Esri grey-canvas setup stacked a second "labels" layer above the choropleth
 * to keep place names readable; that is dropped here in favour of the single
 * standard OSM layer the rest of the deployment uses, so every map in the
 * portal reads the same way and there is one less third-party tile service in
 * the path.
 */
const OSM_TILES = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

type CCMMapProps = {
  data: MapResponse | undefined;
  loading: boolean;
  onSelect?: (properties: Record<string, unknown>) => void;
  /** District outlines, drawn over the choropleth to separate the areas. */
  districts?: BoundaryResponse;
  /** Division outlines — heavier, since a division contains many districts. */
  divisions?: BoundaryResponse;
  /** The cyclone's own path, drawn over everything else. */
  track?: TrackResponse;
  /**
   * Which cyclone the track belongs to. Needed as the track layer's React key:
   * signature() hashes feature ids and values, and track features carry
   * neither, so two different cyclones with the same number of track vertices
   * would hash identically and Leaflet would keep drawing the first one.
   */
  cycloneCode?: string;
};

/**
 * Administrative outlines sit in their own pane above the choropleth (400),
 * and never take pointer events, so hovering a union still hits the union and
 * not the line drawn on top of it.
 */
const BOUNDARY_PANE_Z = 440;

/** The track sits above the outlines — it is the one line nothing may hide. */
const TRACK_PANE_Z = 460;

/**
 * The track, in the desktop tool's red. Drawn twice: a wide translucent casing
 * under a solid core, so the line stays readable crossing both the dark end of
 * the choropleth and the pale sea, without a halo heavy enough to obscure the
 * unions it passes over.
 */
const TRACK_CASING: PathOptions = {
  color: "#FFFFFF",
  weight: 5,
  opacity: 0.75,
  fill: false,
  interactive: false,
};

const TRACK_LINE: PathOptions = {
  color: "#C2300B", // sunrise-900, the palette's red
  weight: 2.2,
  opacity: 0.95,
  fill: false,
  interactive: false,
};

/**
 * A track point. The package's track shapefiles are lines for most cyclones
 * and point sets for a few, so both have to draw: a point renders as a small
 * marker on the same line colour rather than Leaflet's default blue pin.
 */
const TRACK_POINT_RADIUS = 3;

/** What to call the areas on screen, for the legend's count. */
const LEVEL_NOUN: Record<MapResponse["level"], string> = {
  union: "unions",
  upazila: "upazilas",
  district: "districts",
  division: "divisions",
};

/** Navy, per the brand palette. Division reads heavier than district. */
const DISTRICT_LINE: PathOptions = {
  color: "#053244",
  weight: 1.2,
  opacity: 0.55,
  fill: false,
  interactive: false,
};

const DIVISION_LINE: PathOptions = {
  color: "#053244",
  weight: 2.4,
  opacity: 0.85,
  fill: false,
  interactive: false,
};

/**
 * A cheap content fingerprint of a FeatureCollection: length plus a djb2 hash
 * over each feature's id and value. Leaflet does not diff GeoJSON — the
 * react-leaflet GeoJSON layer only rebuilds when its React key changes — so
 * every layer below keys on this signature. Counts and metric min/max are NOT
 * enough: Mocha and Remal both return 1,573 unions spanning risk 0–100, so a
 * count-based key never changed between them and the map kept painting the
 * previous cyclone's polygons while the panel said otherwise.
 */
function signature(data: { features: Feature[] } | undefined): string {
  if (!data || data.features.length === 0) return "empty";
  let hash = 5381;
  for (const feature of data.features) {
    const chunk = `${feature.id}:${feature.properties?.value ?? "∅"}|`;
    for (let i = 0; i < chunk.length; i++) {
      hash = ((hash << 5) + hash + chunk.charCodeAt(i)) | 0;
    }
  }
  return `${data.features.length}-${hash}`;
}

/**
 * The areas containing this one, outermost last — "Amtali, Barguna" for a
 * union, "Barisal" for a district, nothing for a division.
 */
function parentLabels(
  properties: Record<string, unknown>,
  level: MapResponse["level"],
): string {
  const chain: Record<MapResponse["level"], string[]> = {
    union: ["upazila", "district"],
    upazila: ["district", "division"],
    district: ["division"],
    division: [],
  };
  return chain[level]
    .map((key) => properties[key])
    .filter(
      (value): value is string => typeof value === "string" && value.length > 0,
    )
    .join(", ");
}

/**
 * Leaflet tooltips take raw HTML, and these names come from the database.
 * They are place names today, but an apostrophe in "Cox's Bazar" is enough to
 * make the point that they should not be pasted into markup unescaped.
 */
function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/** Zoom to whatever is currently shown, so drilling into a district reframes. */
function FitToData({ data }: { data: MapResponse | undefined }) {
  const map = useMap();
  const fingerprint = signature(data);

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
  }, [fingerprint, map]);

  return null;
}

export function CCMMap({
  data,
  loading,
  onSelect,
  districts,
  divisions,
  track,
  cycloneCode,
}: CCMMapProps) {
  const buckets = useMemo(
    () =>
      buildBuckets(
        data?.metric_unit ?? "",
        data?.metric_min ?? null,
        data?.metric_max ?? null,
      ),
    [data?.metric_unit, data?.metric_min, data?.metric_max],
  );

  // Re-key the layer whenever the *content* changes, not just the counts —
  // see the signature() comment for why counts alone kept two different
  // cyclones looking identical on the map.
  const layerKey = `choropleth-${data?.level ?? "union"}-${data?.metric ?? "none"}-${signature(data)}`;

  // Fewer, larger areas carry a heavier edge. At union level a hairline is
  // right — 1,585 of them, and a thicker line would be most of what you see.
  // At division level there are eight polygons and no outline layer on top of
  // them, so the fill's own edge is the only thing separating them.
  const edgeWeight =
    data?.level === "union" ? 0.5 : data?.level === "upazila" ? 0.8 : 1.4;

  const style = (
    feature?: Feature<Geometry, Record<string, unknown>>,
  ): PathOptions => {
    const value = feature?.properties?.value as number | null | undefined;
    return {
      fillColor: colorFor(value, buckets),
      fillOpacity: 0.75,
      color: "#55809D", // navy-500 boundary, per the design guideline
      weight: edgeWeight,
      opacity: 0.6,
    };
  };

  const onEachFeature = (
    feature: Feature<Geometry, Record<string, unknown>>,
    layer: Path,
  ) => {
    const p = feature.properties ?? {};
    const unit = data?.metric_unit ?? "";
    // The tooltip names whatever level is drawn, and lists the areas above it
    // as context. At division level there is nothing above, so the second line
    // is dropped rather than left as a stray comma.
    const parents = parentLabels(p, data?.level ?? "union");
    layer.bindTooltip(
      `<div style="font-family:Roboto,sans-serif;font-size:12px;line-height:1.5">
         <strong style="color:#053244">${escapeHtml(p.area_name ?? p.union_name ?? "")}</strong><br/>
         ${parents ? `<span style="color:#55809D">${escapeHtml(parents)}</span><br/>` : ""}
         <strong>${data?.metric_label ?? "Value"}:</strong>
         ${formatValue(p.value as number, unit)}
       </div>`,
      { sticky: true },
    );
    layer.on({
      click: () => onSelect?.(p),
      mouseover: (event: LeafletMouseEvent) => {
        const target = event.target as Path;
        target.setStyle({
          weight: edgeWeight + 1.6,
          color: "#053244",
          fillOpacity: 0.9,
        });
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
        <TileLayer
          url={OSM_TILES}
          attribution={OSM_ATTRIBUTION}
          maxZoom={MAX_ZOOM}
        />

        {data && data.features.length > 0 && (
          <GeoJSON
            key={layerKey}
            data={data as never}
            style={style as never}
            onEachFeature={onEachFeature as never}
          />
        )}

        {/* District and division outlines. Re-keyed on content, same as the
            choropleth — two different selections can produce the same number
            of outline features, which would otherwise keep the old lines. */}
        <Pane
          name="admin-boundaries"
          style={{ zIndex: BOUNDARY_PANE_Z, pointerEvents: "none" }}
        >
          {districts && districts.features.length > 0 && (
            <GeoJSON
              key={`district-${signature(districts)}`}
              data={districts as never}
              style={() => DISTRICT_LINE}
            />
          )}
          {divisions && divisions.features.length > 0 && (
            <GeoJSON
              key={`division-${signature(divisions)}`}
              data={divisions as never}
              style={() => DIVISION_LINE}
            />
          )}
        </Pane>

        {/* The cyclone's path. Above the outlines, and never interactive —
            clicking where the track crosses a union must still select the
            union, which is the thing the numbers are about. The track is
            deliberately left out of the zoom fit: it runs far out into the Bay
            and fitting to it would pull the coast down to a sliver. */}
        {track && track.features.length > 0 && (
          <Pane
            name="cyclone-track"
            style={{ zIndex: TRACK_PANE_Z, pointerEvents: "none" }}
          >
            <GeoJSON
              key={`track-casing-${cycloneCode ?? "none"}-${track.features.length}`}
              data={track as never}
              style={() => TRACK_CASING}
              pointToLayer={
                ((_: unknown, latlng: L.LatLng) =>
                  L.circleMarker(latlng, {
                    ...TRACK_CASING,
                    radius: TRACK_POINT_RADIUS + 1.5,
                  })) as never
              }
            />
            <GeoJSON
              key={`track-line-${cycloneCode ?? "none"}-${track.features.length}`}
              data={track as never}
              style={() => TRACK_LINE}
              pointToLayer={
                ((_: unknown, latlng: L.LatLng) =>
                  L.circleMarker(latlng, {
                    ...TRACK_LINE,
                    radius: TRACK_POINT_RADIUS,
                    fill: true,
                    fillColor: TRACK_LINE.color,
                    fillOpacity: 1,
                  })) as never
              }
            />
          </Pane>
        )}

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

      {data && data.features.length > 0 && (
        <MapLegend
          data={data}
          buckets={buckets}
          hasTrack={Boolean(track && track.features.length > 0)}
        />
      )}
    </div>
  );
}

function MapLegend({
  data,
  buckets,
  hasTrack,
}: {
  data: MapResponse;
  buckets: ReturnType<typeof buildBuckets>;
  hasTrack: boolean;
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
        {hasTrack && (
          <li className="flex items-center gap-2">
            <span
              className="h-0.5 w-3 shrink-0 rounded-full"
              style={{ background: TRACK_LINE.color }}
            />
            <span className="text-[11px] text-muted-foreground">
              Cyclone track
            </span>
          </li>
        )}
      </ul>
      <p className="mt-2 border-t border-navy-200 pt-1.5 text-[10px] text-muted-foreground">
        {data.feature_count.toLocaleString()} {LEVEL_NOUN[data.level]} shown
      </p>
    </div>
  );
}
