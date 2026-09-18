import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Feature } from "geojson";

import { api } from "@/lib/api";

/* ------------------------------------------------------------------ types */

export type DFRMLevel = "District" | "Upazilla" | "Union" | "Village";
export type MapLayer = "Inundation" | "Hazard" | "Risk" | "Vulnerability";
/** The tool's radio group: four graded map layers plus the Warning table. */
export type LayerChoice = MapLayer | "Warning";
export type WLKind = "WL" | "DL";

export type Village = { id: string; name: string; river: string };
export type Union = { id: string; name: string; river: string; villages: Village[] };
export type Upazila = { id: string; name: string; unions: Union[] };
export type District = { id: string; name: string; upazilas: Upazila[] };

export type StationInfo = { station: string; danger_level: number };

export type AreaTree = {
  stations: Record<string, StationInfo>;
  limbs: string[];
  map_layers: MapLayer[];
  levels: DFRMLevel[];
  districts: District[];
};

export type MapResponse = {
  level: DFRMLevel;
  area_id: string;
  area_name: string;
  layer: MapLayer;
  river: string;
  station: string;
  danger_level: number;
  day: string;
  limb: string;
  water_level: number;
  return_period: number | null;
  metric_min: number | null;
  metric_max: number | null;
  metric_unit: string;
  bounds: [number, number, number, number];
  feature_count: number;
  features: Feature[];
  rivers: {
    corridor: { type: "FeatureCollection"; features: Feature[] };
    active: { type: "FeatureCollection"; features: Feature[] };
  };
  context: {
    upazila: { type: "FeatureCollection"; features: Feature[] };
    district: { type: "FeatureCollection"; features: Feature[] };
  };
};

export type WarningRow = {
  _id: string;
  Division: string | null;
  District: string | null;
  Upazilla?: string | null;
  Union?: string | null;
  Village?: string | null;
  "Risk Level": string | number;
  "Water Depth": string;
  "Flood Duration": string;
  "Water Speed": string | number;
  Damage: string | number;
};

export type WarningResponse = {
  level: DFRMLevel;
  area_id: string;
  area_name: string;
  day: string;
  limb: string;
  date: string | null;
  river: string;
  station: string;
  danger_level: number;
  water_level: number;
  return_period: number | null;
  selected: WarningRow;
  rows: WarningRow[];
};

export type MapRequest = {
  level: DFRMLevel;
  area_id: string;
  layer: MapLayer;
  water_level: number;
  wl_kind: WLKind;
  limb: string;
  simplify?: number;
};

export type WarningRequest = {
  level: DFRMLevel;
  area_id: string;
  water_level: number;
  wl_kind: WLKind;
  limb: string;
  date: string | null;
};

export type DfrmRun = {
  id: number;
  kind: "map" | "warning";
  level: DFRMLevel;
  area_id: string;
  area_name: string;
  layer: string;
  water_level: number;
  wl_kind: WLKind;
  limb: string;
  date: string | null;
  river: string;
  station: string;
  return_period: number | null;
  summary: Record<string, unknown> | null;
  created_at: string;
};

/* ----------------------------------------------------------------- hooks */

export function useAreas() {
  return useQuery({
    queryKey: ["dfrm", "areas"],
    queryFn: async () => (await api.get<AreaTree>("/dfrm/areas")).data,
    staleTime: Infinity,
  });
}

export function useMapLayer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (req: MapRequest) => (await api.post<MapResponse>("/dfrm/map", req)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dfrm", "runs"] }),
  });
}

export function useWarning() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (req: WarningRequest) =>
      (await api.post<WarningResponse>("/dfrm/warning", req)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dfrm", "runs"] }),
  });
}

export function useDfrmRuns(limit = 20) {
  return useQuery({
    queryKey: ["dfrm", "runs", limit],
    queryFn: async () => (await api.get<DfrmRun[]>("/dfrm/runs", { params: { limit } })).data,
    staleTime: 10_000,
  });
}

/** URL for the warning CSV export — the web equivalent of the tool's "Save". */
export function warningCsvUrl(req: WarningRequest): string {
  const base = api.defaults.baseURL ?? "";
  const params = new URLSearchParams({
    level: req.level,
    area_id: req.area_id,
    water_level: String(req.water_level),
    wl_kind: req.wl_kind,
    limb: req.limb,
  });
  if (req.date) params.set("date", req.date);
  return `${base}/dfrm/warning.csv?${params.toString()}`;
}
