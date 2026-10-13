import { useQuery } from "@tanstack/react-query";
import type { Feature } from "geojson";

import { api } from "@/lib/api";

/* ------------------------------------------------------------------ types */

export type AdminLevel = "union" | "upazila" | "district" | "division";
export type Operator = "gte" | "gt" | "lte" | "lt" | "eq";

/**
 * How the trigger threshold is read.
 *
 * "value" compares the trigger metric to the number typed. "return_period"
 * reads the number as years and keeps only the unions where this cyclone beats
 * their own 1-in-T-year event — 10,000 people affected is an ordinary season
 * for a large mainland union and an unprecedented disaster on a char, and the
 * return period is what tells those two apart.
 */
export type ThresholdMode = "value" | "return_period";

/** The return period only has per-union statistics for this one metric. */
export const RETURN_PERIOD_METRIC = "affected_people";

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

export type LocationOption = {
  value: string;
  label: string;
  parent: string | null;
};

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
  /** the lead time the NEAP columns on these rows were classified at */
  lead_time_hours: number | null;
  metric: string;
  metric_min: number | null;
  metric_max: number | null;
};

export type MapResponse = {
  type: "FeatureCollection";
  features: Feature[];
  /** which administrative level the polygons are */
  level: AdminLevel;
  metric: string;
  metric_label: string;
  metric_unit: string;
  metric_min: number | null;
  metric_max: number | null;
  feature_count: number;
};

export type TrackResponse = {
  type: "FeatureCollection";
  features: Feature[];
  feature_count: number;
};

export type BoundaryLevel = "district" | "division";

export type BoundaryResponse = {
  type: "FeatureCollection";
  features: Feature[];
  level: BoundaryLevel;
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
  /** how `threshold` is read — a flat value, or a return period in years */
  thresholdMode: ThresholdMode;
  /**
   * Hours of warning before landfall. Drives the NEAP impact numbers: the same
   * hazard scores lower the earlier it is known, because there is time to act.
   */
  leadTimeHours: number;
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
  thresholdMode: "value",
  // What CCM_Main.py puts in its own lead-time box when left empty.
  leadTimeHours: 120,
};

/* ----------------------------------------------------------------- params */

function locationParams(
  f: Pick<CCMFilters, "division" | "district" | "upazila">,
) {
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
  if (f.thresholdMode === "return_period") {
    // The comparison is against each union's own expected T-year figure, so
    // there is no operator to send — only the period itself.
    return {
      metric: RETURN_PERIOD_METRIC,
      threshold: f.threshold,
      threshold_mode: "return_period",
    };
  }
  return {
    metric: f.triggerMetric,
    operator: f.operator,
    threshold: f.threshold,
  };
}

/* ----------------------------------------------------------------- hooks */

export const ccmKeys = {
  metrics: ["ccm", "metrics"] as const,
  cyclones: ["ccm", "cyclones"] as const,
  cyclone: (code: string) => ["ccm", "cyclone", code] as const,
  locations: (code: string, level: string, parent?: string | null) =>
    ["ccm", "locations", code, level, parent ?? null] as const,
  results: (f: CCMFilters, page: number) =>
    ["ccm", "results", f, page] as const,
  map: (f: CCMFilters) => ["ccm", "map", f] as const,
  track: (code: string) => ["ccm", "track", code] as const,
  boundaries: (code: string, level: BoundaryLevel, f: CCMFilters) =>
    [
      "ccm",
      "boundaries",
      code,
      level,
      f.division,
      f.district,
      f.upazila,
    ] as const,
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
    queryFn: async () =>
      (await api.get<CycloneDetail>(`/ccm/cyclones/${code}`)).data,
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
            lead_time_hours: filters.leadTimeHours,
            page,
            size,
          },
        })
      ).data,
    enabled: Boolean(filters.cyclone),
    placeholderData: (previous) => previous,
  });
}

/**
 * How hard to simplify the polygons for the current view.
 *
 * The cost is the number of vertices leaving the database, which depends on
 * how many areas are drawn, not on how big they are. Above union level there
 * are tens of shapes rather than 1,585, so they can be drawn nearly exactly;
 * at union level across the whole coast the tolerance has to be loosened or
 * the payload gets unreasonable.
 */
function mapSimplify(filters: CCMFilters): number {
  if (filters.level !== "union") return 0.0002;
  return filters.district ? 0.0003 : 0.0015;
}

export function useMapData(filters: CCMFilters, enabled = true) {
  return useQuery({
    queryKey: ccmKeys.map(filters),
    queryFn: async () =>
      (
        await api.get<MapResponse>(`/ccm/cyclones/${filters.cyclone}/map`, {
          params: {
            metric: filters.metric,
            // The level is the map, not only the table: at district level the
            // API returns dissolved district polygons, so the union lines
            // inside them are gone rather than drawn over a district figure.
            level: filters.level,
            ...locationParams(filters),
            ...triggerParams(filters),
            // Union boundaries at full precision are ~40 MB of GeoJSON, so the
            // API simplifies them. Loosen it when the whole country is in
            // view, and tighten it above union level — a handful of dissolved
            // areas is cheap, and their edges are the only edges on screen.
            simplify: mapSimplify(filters),
          },
        })
      ).data,
    enabled: enabled && Boolean(filters.cyclone),
    placeholderData: (previous) => previous,
  });
}

/**
 * District or division outlines for the map overlay.
 *
 * Kept as its own query rather than folded into the map call: the outlines
 * depend only on the area in view, not on the metric or the trigger, so they
 * stay cached while you flip between metrics. The dissolve behind this is the
 * slow part of the map, so not re-fetching it on every metric change matters.
 */
export function useBoundaries(
  filters: CCMFilters,
  level: BoundaryLevel,
  enabled = true,
) {
  return useQuery({
    queryKey: ccmKeys.boundaries(filters.cyclone, level, filters),
    queryFn: async () =>
      (
        await api.get<BoundaryResponse>(
          `/ccm/cyclones/${filters.cyclone}/boundaries`,
          { params: { level, ...locationParams(filters), simplify: 0.002 } },
        )
      ).data,
    enabled: enabled && Boolean(filters.cyclone),
    staleTime: 10 * 60_000,
    placeholderData: (previous) => previous,
  });
}

/** URL for the CSV export — the web equivalent of the tool's "Save Table". */
/**
 * A download link for the table as it is currently filtered.
 *
 * The browser's table is paged; the download is not — the API re-runs the same
 * query with the page cap lifted, so the file holds every matching row.
 */
export function resultsDownloadUrl(
  filters: CCMFilters,
  format: "csv" | "xlsx",
): string {
  const base = api.defaults.baseURL ?? "";
  const params = new URLSearchParams({ level: filters.level });
  for (const [key, value] of Object.entries({
    ...locationParams(filters),
    ...triggerParams(filters),
    lead_time_hours: filters.leadTimeHours,
  })) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  return `${base}/ccm/cyclones/${filters.cyclone}/results.${format}?${params.toString()}`;
}

/**
 * The cyclone's track line.
 *
 * Its own query, keyed on the cyclone alone: the track does not move when the
 * metric, the area or the threshold changes, so it is fetched once and stays
 * cached while the operator works through the rest of the panel.
 */
export function useTrack(code: string | null) {
  return useQuery({
    queryKey: ccmKeys.track(code ?? ""),
    queryFn: async () =>
      (await api.get<TrackResponse>(`/ccm/cyclones/${code}/track`)).data,
    enabled: Boolean(code),
    staleTime: Infinity,
  });
}

/* -------------------------------------------------------------- model runs */

export type RunStatus = "queued" | "running" | "succeeded" | "failed";

export type CCMRun = {
  id: number;
  cyclone_code: string;
  status: RunStatus;
  cyclone_id: number | null;
  cyclone_name: string | null;
  row_count: number | null;
  error: string | null;
  took_ms: number | null;
  created_at: string;
  finished_at: string | null;
};

/** The simulation files a run needs. `required` drives the form's validation. */
export const RUN_FILE_FIELDS = [
  {
    field: "water_depth_xyz",
    label: "Water Depth",
    hint: "Water Depth.xyz",
    required: true,
  },
  {
    field: "wind_speed_xyz",
    label: "Wind Speed",
    hint: "Wind Speed.xyz",
    required: true,
  },
  { field: "rain_csv", label: "Rainfall", hint: "Rain.csv", required: true },
  {
    field: "track_shp",
    label: "Track — .shp",
    hint: "Track.shp",
    required: true,
  },
  {
    field: "track_shx",
    label: "Track — .shx",
    hint: "Track.shx",
    required: true,
  },
  {
    field: "track_dbf",
    label: "Track — .dbf",
    hint: "Track.dbf",
    required: true,
  },
  {
    field: "track_prj",
    label: "Track — .prj",
    hint: "Track.prj",
    required: false,
  },
  {
    field: "track_cpg",
    label: "Track — .cpg",
    hint: "Track.cpg",
    required: false,
  },
] as const;

/**
 * Thrust force can arrive either already computed, or as the three grids the
 * model derives it from. Exactly one of these two groups is needed.
 */
export const THRUST_FORCE_FIELDS = [
  {
    field: "thrust_force_csv",
    label: "Thrust Force (pre-computed)",
    hint: "Thrush Force.csv",
  },
  {
    field: "water_depth_tf_xyz",
    label: "Water Depth (TF grid)",
    hint: "Water Depth-TF.xyz",
  },
  {
    field: "wind_speed_tf_xyz",
    label: "Wind Speed (TF grid)",
    hint: "Wind Speed-TF.xyz",
  },
  {
    field: "depth_avg_velocity_tf_xyz",
    label: "Depth-Averaged Velocity (TF grid)",
    hint: "Depth Averaged Velocity-TF.xyz",
  },
] as const;

export type RunMeta = {
  cyclone_code: string;
  name?: string;
  event_date?: string;
  landfall_location?: string;
  max_wind_speed?: string;
  remark?: string;
  cyclone_type?: string;
};

/** Starts a run. Resolves as soon as the server accepts it, not when it finishes. */
export async function startRun(
  meta: RunMeta,
  files: Record<string, File | undefined>,
): Promise<{ id: number; cyclone_code: string; status: RunStatus }> {
  const form = new FormData();
  for (const [key, value] of Object.entries(meta)) {
    if (value !== undefined && value !== "") form.append(key, value);
  }
  for (const [field, file] of Object.entries(files)) {
    if (file) form.append(field, file);
  }
  const { data } = await api.post("/ccm/runs", form);
  return data;
}

export function useRuns(limit = 20) {
  return useQuery({
    queryKey: ["ccm", "runs", limit] as const,
    queryFn: async () =>
      (await api.get<CCMRun[]>("/ccm/runs", { params: { limit } })).data,
    // A run in flight should show progress without the operator reloading.
    refetchInterval: (query) =>
      (query.state.data ?? []).some(
        (r) => r.status === "queued" || r.status === "running",
      )
        ? 5_000
        : false,
  });
}

/** Polls one run while it is in flight, then stops. */
export function useRun(runId: number | null) {
  return useQuery({
    queryKey: ["ccm", "run", runId] as const,
    queryFn: async () => (await api.get<CCMRun>(`/ccm/runs/${runId}`)).data,
    enabled: runId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 3_000 : false;
    },
  });
}
