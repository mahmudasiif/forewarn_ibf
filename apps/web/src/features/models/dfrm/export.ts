import type { Feature } from "geojson";

import type { MapResponse } from "@/lib/dfrmApi";

function slug(s: string): string {
  return (s || "map").replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "map";
}

export function mapFileStem(data: MapResponse): string {
  return `DFRM_${slug(data.area_name)}_${data.layer}_${data.day}`;
}

/** Bundle every drawn layer into one FeatureCollection, tagged by `_layer`. */
export function buildGeoJSON(data: MapResponse) {
  const tag = (features: Feature[], layer: string) =>
    features.map((f) => ({ ...f, properties: { ...(f.properties ?? {}), _layer: layer } }));
  return {
    type: "FeatureCollection" as const,
    features: [
      ...tag(data.features, data.layer),
      ...tag(data.rivers.corridor.features, "river_corridor"),
      ...tag(data.rivers.active.features, "river_active"),
      ...tag(data.context.upazila.features, "upazila_outline"),
      ...tag(data.context.district.features, "district_outline"),
    ],
  };
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function downloadGeoJSON(data: MapResponse): void {
  const blob = new Blob([JSON.stringify(buildGeoJSON(data))], { type: "application/geo+json" });
  downloadBlob(blob, `${mapFileStem(data)}.geojson`);
}
