import { useQuery } from "@tanstack/react-query";
import type { Feature } from "geojson";

import { api } from "@/lib/api";

/* ------------------------------------------------------------------ types */

export type AdminLevel = "union" | "upazila" | "district" | "division";
export type Operator = "gte" | "gt" | "lte" | "lt" | "eq";

export type Cyclone = {
  id: number;
  code: string;
  name: string;
  event_date: string | null;
  landfall_location: string | null;
  max_wind_speed: number | null;
  cyclone_type: string;
  source: string;
  model_version: string;
  imported_at: string;
};

export type CycloneDetail = Cyclone & {
  remark: string | null;
  notes: string | null;
  union_count: number;
  totals: Record<string, number>;
};

export type Metric = {
  key: string;
  label: string;
  unit: string;
  aggregation: string;
  mappable: boolean;
  description: string;
};

export type LocationOption = { value: string; label: string; parent: string | null };

export type ResultRow = {
  union_geo: number | null;
  division: string;
  district: string | null;
  upazila: string | null;
  union_name: string | null;
} & Record<string, string | number | null>;

export type ResultPage = {
  items: ResultRow[];
  total: number;
  page: number;
  size: number;
  level: AdminLevel;
  metric: string;
  metric_min: number | null;
  metric_max: number | null;
};

export type MapResponse = {
  type: "FeatureCollection";
  features: Feature[];
  metric: string;
  metric_label: string;
  metric_unit: string;
  metric_min: number | null;
  metric_max: number | null;
  feature_count: number;
};

/** The controls on the CCM screen, mirroring the desktop tool's input panel. */
export type CCMFilters = {
  cyclone: string;
  level: AdminLevel;
  division: string | null;
  district: string | null;
  upazila: string | null;
  /** which metric colours the map — the tool's "Map Type" */
  metric: string;
  /** the tool's "Trigger Parameter" */
  triggerMetric: string;
  operator: Operator;
  threshold: number | null;
};

export const DEFAULT_FILTERS: Omit<CCMFilters, "cyclone"> = {
  level: "union",
  division: null,
  district: null,
  upazila: null,
  metric: "risk_pct",
  triggerMetric: "risk_pct",
  operator: "gte",
  threshold: null,
};

/* ----------------------------------------------------------------- params */

function locationParams(f: Pick<CCMFilters, "division" | "district" | "upazila">) {
  return {
    division: f.division ?? undefined,
    district: f.district ?? undefined,
    upazila: f.upazila ?? undefined,
  };
}

/**
 * The trigger filters the rows; the map metric colours what remains. When the
 * two differ the API still needs a single `metric` for the threshold to apply
 * to, so the trigger wins for filtering and the map asks separately.
 */
function triggerParams(f: CCMFilters) {
  if (f.threshold === null || Number.isNaN(f.threshold)) return {};
  return { metric: f.triggerMetric, operator: f.operator, threshold: f.threshold };
}

/* ----------------------------------------------------------------- hooks */

export const ccmKeys = {
  metrics: ["ccm", "metrics"] as const,
  cyclones: ["ccm", "cyclones"] as const,
  cyclone: (code: string) => ["ccm", "cyclone", code] as const,
  locations: (code: string, level: string, parent?: string | null) =>
    ["ccm", "locations", code, level, parent ?? null] as const,
  results: (f: CCMFilters, page: number) => ["ccm", "results", f, page] as const,
  map: (f: CCMFilters) => ["ccm", "map", f] as const,
};

export function useMetrics() {
  return useQuery({
    queryKey: ccmKeys.metrics,
    queryFn: async () => (await api.get<Metric[]>("/ccm/metrics")).data,
    staleTime: Infinity,
  });
}

export function useCyclones() {
  return useQuery({
    queryKey: ccmKeys.cyclones,
    queryFn: async () => (await api.get<Cyclone[]>("/ccm/cyclones")).data,
    staleTime: 5 * 60_000,
  });
}

export function useCyclone(code: string | null) {
  return useQuery({
    queryKey: ccmKeys.cyclone(code ?? ""),
    queryFn: async () => (await api.get<CycloneDetail>(`/ccm/cyclones/${code}`)).data,
    enabled: Boolean(code),
  });
}

export function useLocations(
  code: string | null,
  level: "division" | "district" | "upazila",
  parent?: string | null,
) {
  return useQuery({
    queryKey: ccmKeys.locations(code ?? "", level, parent),
    queryFn: async () =>
      (
        await api.get<LocationOption[]>(`/ccm/cyclones/${code}/locations`, {
          params: { level, parent: parent ?? undefined },
        })
      ).data,
    enabled: Boolean(code) && (level === "division" || Boolean(parent)),
  });
}

export function useResults(filters: CCMFilters, page: number, size = 50) {
  return useQuery({
    queryKey: [...ccmKeys.results(filters, page), size],
    queryFn: async () =>
      (
        await api.get<ResultPage>(`/ccm/cyclones/${filters.cyclone}/results`, {
          params: {
            level: filters.level,
            ...locationParams(filters),
            ...triggerParams(filters),
            page,
            size,
          },
        })
      ).data,
    enabled: Boolean(filters.cyclone),
    placeholderData: (previous) => previous,
  });
}

export function useMapData(filters: CCMFilters, enabled = true) {
  return useQuery({
    queryKey: ccmKeys.map(filters),
    queryFn: async () =>
      (
        await api.get<MapResponse>(`/ccm/cyclones/${filters.cyclone}/map`, {
          params: {
            metric: filters.metric,
            ...locationParams(filters),
            ...triggerParams(filters),
            // Union boundaries at full precision are ~40 MB of GeoJSON, so the
            // API simplifies them. Loosen it when the whole country is in view.
            simplify: filters.district ? 0.0003 : 0.0015,
          },
        })
      ).data,
    enabled: enabled && Boolean(filters.cyclone),
    placeholderData: (previous) => previous,
  });
}

/** URL for the CSV export — the web equivalent of the tool's "Save Table". */
export function resultsCsvUrl(filters: CCMFilters): string {
  const base = api.defaults.baseURL ?? "";
  const params = new URLSearchParams({ level: filters.level });
  for (const [key, value] of Object.entries({
    ...locationParams(filters),
    ...triggerParams(filters),
  })) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  return `${base}/ccm/cyclones/${filters.cyclone}/results.csv?${params.toString()}`;
}
