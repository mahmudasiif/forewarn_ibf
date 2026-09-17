import type { AnalysisContext, Lang } from "@/lib/preparednessApi";

export function clampPercentage(value: unknown): number | null {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, n));
}

export function fmtNumber(value: unknown, lang: Lang, digits = 1): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return lang === "en" ? "No data" : "তথ্য নেই";
  return n.toLocaleString(lang === "bn" ? "bn-BD" : "en-US", { maximumFractionDigits: digits });
}

export function fmtAffected(
  count: unknown,
  pct: unknown,
  modelled: unknown,
  lang: Lang,
): string {
  const n = typeof count === "number" ? count : Number(count);
  if (!modelled || !Number.isFinite(n)) return lang === "en" ? "Not modelled" : "মডেল করা হয়নি";
  const locale = lang === "bn" ? "bn-BD" : "en-US";
  const bounded = clampPercentage(pct);
  const share = bounded === null ? "" : ` (${bounded.toLocaleString(locale, { maximumFractionDigits: 1 })}%)`;
  return `${Math.round(n).toLocaleString(locale)}${share}`;
}

export function fmtAffectedDemographic(ctx: AnalysisContext, key: string, lang: Lang): string {
  const breakdown = ctx.affected_population_breakdown as Record<string, unknown> | undefined;
  const count = breakdown?.[key];
  const n = typeof count === "number" ? count : Number(count);
  if (!ctx.impact_modelled || !Number.isFinite(n)) return lang === "en" ? "Not modelled" : "মডেল করা হয়নি";
  return Math.round(n).toLocaleString(lang === "bn" ? "bn-BD" : "en-US");
}

export function fmtExposed(ctx: AnalysisContext, lang: Lang): string {
  const housing = (ctx.housing_numbers as Record<string, unknown>) ?? {};
  const houses = Object.values(housing).reduce<number>(
    (sum, n) => sum + (typeof n === "number" && Number.isFinite(n) ? n : 0),
    0,
  );
  const pop =
    typeof ctx.total_population === "number" && ctx.total_population > 0
      ? ctx.total_population
      : houses > 0
        ? houses * 4.06
        : null;
  if (pop === null) return lang === "en" ? "No data" : "তথ্য নেই";
  return Math.round(pop).toLocaleString(lang === "bn" ? "bn-BD" : "en-US");
}

/** The 12 impact-table headers (English, matching the original + the docx). */
export function impactTableHeaders(rainfallWindowHours: number | null | undefined): string[] {
  const rain =
    typeof rainfallWindowHours === "number" && Number.isFinite(rainfallWindowHours) && rainfallWindowHours > 0
      ? `Accumulated rainfall (${Math.round(rainfallWindowHours)} Hours)`
      : "Accumulated rainfall (mm)";
  return [
    "Administrative Boundary",
    "Avg wind speed (km/h)",
    "Max surge (m)",
    rain,
    "Total Population",
    "Total",
    "Male",
    "Female",
    "0–4 Years",
    "5 to 19 Years",
    "Age 60+",
    "Potential affected house",
  ];
}
