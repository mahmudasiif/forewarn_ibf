/** Every React Query key in the app is declared here — no inline string keys. */
export const queryKeys = {
  health: ["health"] as const,
  geo: {
    adminUnits: (level?: number) => ["geo", "admin-units", level] as const,
  },
  hazards: {
    all: ["hazards"] as const,
    detail: (id: string) => ["hazards", id] as const,
    forecasts: (params?: Record<string, unknown>) => ["hazards", "forecasts", params] as const,
  },
  impact: {
    forecasts: (params?: Record<string, unknown>) => ["impact", "forecasts", params] as const,
    matrix: ["impact", "matrix"] as const,
  },
  models: {
    registry: ["models", "registry"] as const,
    runs: (params?: Record<string, unknown>) => ["models", "runs", params] as const,
  },
  alerts: {
    all: (params?: Record<string, unknown>) => ["alerts", params] as const,
    detail: (id: string) => ["alerts", id] as const,
  },
} as const;
