import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

/* ------------------------------------------------------------------ types */

export type RunStatus = "queued" | "running" | "succeeded" | "failed";
export type DamageModel = "ccm" | "safir";

export type ArtifactInfo = {
  label: string;
  name: string;
  content_type: string;
  size: number;
};

export type RunSummary = {
  id: number;
  cyclone_name: string;
  status: RunStatus;
  damage_model: string;
  llm_polished: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

/** Loosely typed — the shape mirrors the model's manifest, accessed defensively. */
export type RunSummaryStats = {
  cyclone_track?: {
    current_state?: Record<string, unknown>;
    forecast_state?: Record<string, unknown>;
  };
  max_wind_record?: { wind_speed_kmh?: number | null } | null;
  max_rain_record?: { total_rainfall_mm?: number | null } | null;
  max_storm_surge_record?: { storm_surge_m?: number | null } | null;
  data_quality_warnings_en?: string[];
  [key: string]: unknown;
};

export type RunDetail = RunSummary & {
  polished: boolean;
  input_files: Record<string, { filename: string; key: string }>;
  summary: RunSummaryStats | null;
  guideline_markdown: string | null;
  artifacts: ArtifactInfo[] | null;
  error: string | null;
};

export type CreateRunInput = {
  cycloneName: string;
  wind: File;
  rainfall?: File | null;
  stormSurge?: File | null;
  damageModel: DamageModel;
  polish: boolean;
};

/* ----------------------------------------------------------------- keys */

export const prepKeys = {
  runs: ["preparedness", "runs"] as const,
  run: (id: number) => ["preparedness", "run", id] as const,
};

const ACTIVE = (s: RunStatus) => s === "queued" || s === "running";

/* ----------------------------------------------------------------- hooks */

export function useRuns() {
  return useQuery({
    queryKey: prepKeys.runs,
    queryFn: async () => (await api.get<RunSummary[]>("/preparedness/runs")).data,
    // Poll while any run is still working so the list advances on its own.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((r) => ACTIVE(r.status)) ? 4000 : false,
  });
}

export function useRun(id: number | null) {
  return useQuery({
    queryKey: prepKeys.run(id ?? 0),
    queryFn: async () => (await api.get<RunDetail>(`/preparedness/runs/${id}`)).data,
    enabled: id != null,
    refetchInterval: (query) => (query.state.data && ACTIVE(query.state.data.status) ? 3000 : false),
  });
}

export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateRunInput) => {
      const form = new FormData();
      form.append("cyclone_name", input.cycloneName);
      form.append("wind", input.wind);
      if (input.rainfall) form.append("rainfall", input.rainfall);
      if (input.stormSurge) form.append("storm_surge", input.stormSurge);
      form.append("damage_model", input.damageModel);
      form.append("polish", String(input.polish));
      return (await api.post<RunDetail>("/preparedness/runs", form)).data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: prepKeys.runs }),
  });
}

/** Absolute URL to a run artifact (map HTML for iframes, or a file download). */
export function artifactUrl(runId: number, name: string): string {
  const base = api.defaults.baseURL ?? "";
  return `${base}/preparedness/runs/${runId}/artifacts/${encodeURIComponent(name)}`;
}

/* ------------------------------------------------ interactive (Phase 2) types */

export type Lang = "bn" | "en";
export type AdminLevel = "union" | "upazila" | "district";
export type AreaMetric = "wind" | "rainfall" | "surge" | "risk";

export type ImpactCategory =
  | "populationAndHouse"
  | "infrastructurePolder"
  | "agriculture"
  | "livestockFisheries"
  | "livelihood"
  | "healthDisease"
  | "utilityService";

export type AnalysisContext = {
  admin_level?: AdminLevel;
  name?: string;
  geo_code?: string;
  boundary_geo_code?: string;
  union?: string;
  upazila?: string;
  district?: string;
  member_count?: number;
  wind_speed_kmh?: number | null;
  wind_class_label?: string;
  total_rainfall_mm?: number | null;
  storm_surge_m?: number | null;
  risk?: string;
  [key: string]: unknown;
};

export type RunContexts = {
  analysis_contexts: AnalysisContext[];
  analysis_options: AnalysisContext[];
  cyclone_track?: Record<string, unknown> | null;
  cyclone_name?: string;
  rainfall_window_hours?: number | null;
  data_quality_warnings?: string[];
  data_quality_warnings_en?: string[];
};

export type ImpactSummaryRow = {
  area: string;
  windSpeedKmh: string;
  surgeM: string;
  precipitationMm: string;
  totalPopulation: string;
  affectedPopulation: string;
  affectedMale: string;
  affectedFemale: string;
  affectedAge0To4: string;
  affectedAge5To19: string;
  affectedAge60Plus: string;
  affectedHouseStructure: string;
};

export type GuidelineDocument = {
  cycloneName: string;
  generatedAt: string;
  analysisLevel?: AdminLevel;
  selectedArea?: string;
  levelLabels: Record<"community" | "institutional", string>;
  rainfallWindowHours?: number | null;
  trackMapUrl?: string;
  dataQualityWarnings?: string[];
  currentState: { name: string; category: string; windSpeedKmh: string; direction: string; location: string };
  forecastState: {
    landfallLocation: string;
    windSpeed: string;
    stormSurge: string;
    time: string;
    category: string;
    precipitation: string;
  };
  impactSummaryTable: ImpactSummaryRow[];
  majorImpact: Record<ImpactCategory, string[]>;
  advisories: Record<"community" | "institutional", Record<ImpactCategory, string[]>>;
};

export const IMPACT_SECTOR_CARDS: [string, ImpactCategory][] = [
  ["Population and House", "populationAndHouse"],
  ["Infrastructure/Polder", "infrastructurePolder"],
  ["Agriculture", "agriculture"],
  ["Livestock + Fisheries", "livestockFisheries"],
  ["Livelihood", "livelihood"],
  ["Health/Disease", "healthDisease"],
  ["Utility service", "utilityService"],
];

/* ----------------------------------------------- interactive (Phase 2) hooks */

export function useRunContexts(runId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["preparedness", "contexts", runId],
    queryFn: async () => (await api.get<RunContexts>(`/preparedness/runs/${runId}/contexts`)).data,
    enabled: enabled && runId != null,
    staleTime: Infinity,
  });
}

export function useGenerateGuideline(runId: number) {
  return useMutation({
    mutationFn: async ({ context, lang }: { context: AnalysisContext; lang: Lang }) =>
      (await api.post<{ document: GuidelineDocument }>(`/preparedness/runs/${runId}/guideline`, { context, lang })).data
        .document,
  });
}

export function useAreaMap(runId: number) {
  return useMutation({
    mutationFn: async (body: {
      level: AdminLevel;
      metric: AreaMetric;
      district?: string;
      upazila?: string;
      union?: string;
      geo_code?: string;
      lang: Lang;
    }) => {
      const resp = await api.post(`/preparedness/runs/${runId}/area-map`, body, { responseType: "blob" });
      return URL.createObjectURL(resp.data as Blob);
    },
  });
}

/** Download the guideline as a Word document. */
export async function downloadGuidelineDocx(runId: number, document: GuidelineDocument): Promise<void> {
  const resp = await api.post(
    `/preparedness/runs/${runId}/guideline/docx`,
    { document },
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(resp.data as Blob);
  const a = window.document.createElement("a");
  a.href = url;
  const name = (document.cycloneName || "guideline").toLowerCase().replace(/\s+/g, "_");
  a.download = `${name}_ibf_guideline.docx`;
  window.document.body.appendChild(a);
  a.click();
  window.document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
