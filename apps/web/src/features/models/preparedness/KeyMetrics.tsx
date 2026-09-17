import { useMemo } from "react";

import { Card } from "@/components/shared/Card";
import type { Lang, RunContexts } from "@/lib/preparednessApi";
import { fmtNumber } from "./format";

type Rec = Record<string, unknown>;

function extremePlace(record: Rec | null | undefined): string {
  if (!record) return "—";
  const parts = [record.union || record.name, record.upazila, record.district].filter(Boolean).map(String);
  return Array.from(new Set(parts)).join(", ") || "—";
}

function names(display: unknown, extended: Rec[], top10: unknown): string {
  if (typeof display === "string" && display.trim()) return display;
  if (extended.length) return extended.map((r) => r.union ?? r.name ?? r.upazila).filter(Boolean).join(", ");
  if (Array.isArray(top10)) return top10.join(", ");
  return "—";
}

export function KeyMetrics({
  summary,
  contexts,
  lang,
}: {
  summary: Rec;
  contexts: RunContexts | undefined;
  lang: Lang;
}) {
  const block = (summary.summary as Rec) ?? {};
  const topRisk = (summary.top_risk_upazilas_extended as Rec[]) ?? [];
  const topRain = (summary.top_rain_upazilas_extended as Rec[]) ?? [];
  const maxWind = (summary.max_wind_record as Rec) ?? null;
  const maxRain = (summary.max_rain_record as Rec) ?? null;
  const maxSurge = (summary.max_storm_surge_record as Rec) ?? null;
  const damageModel = String(block.damage_model ?? summary.damage_model ?? "ccm").toUpperCase();

  const rainfallEvac = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const ctx of contexts?.analysis_contexts ?? []) {
      if ((ctx.admin_level ?? "union") !== "union") continue;
      const evac = ctx.rainfall_evacuation as { house_types?: string }[] | undefined;
      for (const entry of evac ?? []) {
        const ht = entry.house_types?.trim();
        if (!ht) continue;
        if (!map.has(ht)) map.set(ht, new Set());
        const area = (ctx.union ?? ctx.name) as string | undefined;
        if (area) map.get(ht)!.add(area);
      }
    }
    return Array.from(map.entries()).map(([houseTypes, areas]) => ({
      houseTypes,
      areas: Array.from(areas).sort().slice(0, 10),
    }));
  }, [contexts]);

  const t = (en: string, bn: string) => (lang === "en" ? en : bn);
  const riskNames = names(block.top_risk_upazilas_display, topRisk, block.top_risk_upazilas_top10);
  const rainNames = names(block.top_rain_upazilas_display, topRain, block.top_rain_upazilas_top10);

  const stat = (label: string, value: string) => (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium text-navy-900">{value}</dd>
    </div>
  );

  return (
    <Card title={t("Key metrics", "মূল পরিসংখ্যান")} bodyClassName="space-y-5">
      <div>
        <p className="mb-1.5 text-sm font-semibold text-foreground">
          {t("Risk classification (wind)", "ঝুঁকি শ্রেণীবিভাগ (বাতাস)")}
        </p>
        <ul className="space-y-1 text-sm text-navy-800">
          <li>
            <span className="font-medium">{t("Highest risk area", "সর্বোচ্চ ঝুঁকি")}:</span>{" "}
            {String(topRisk[0]?.union ?? topRisk[0]?.name ?? topRisk[0]?.upazila ?? "—")}
            {topRisk[0]?.district ? ` (${String(topRisk[0].district)})` : ""}
          </li>
          <li>
            <span className="font-medium">{t("Max wind", "সর্বোচ্চ বাতাস")}:</span>{" "}
            {maxWind ? `${fmtNumber(maxWind.wind_speed_kmh, lang, 1)} km/h (${extremePlace(maxWind)})` : fmtNumber(block.max_wind_speed_kmh, lang, 1)}
          </li>
          <li>
            <span className="font-medium">{t("Max surge", "সর্বোচ্চ জলোচ্ছ্বাস")}:</span>{" "}
            {maxSurge ? `${fmtNumber(maxSurge.storm_surge_m, lang, 2)} m (${extremePlace(maxSurge)})` : fmtNumber(block.max_storm_surge_m, lang, 2)}
          </li>
        </ul>
      </div>

      <div>
        <p className="mb-1.5 text-sm font-semibold text-foreground">{t("Rainfall analysis", "অতিবৃষ্টি বিশ্লেষণ")}</p>
        <ul className="space-y-1 text-sm text-navy-800">
          <li>
            <span className="font-medium">{t("Max rainfall", "সর্বোচ্চ বৃষ্টিপাত")}:</span>{" "}
            {maxRain ? `${fmtNumber(maxRain.total_rainfall_mm, lang, 1)} mm (${extremePlace(maxRain)})` : fmtNumber(block.max_rainfall_mm, lang, 1)}
          </li>
          {rainfallEvac.length > 0 && (
            <li>
              <span className="font-medium">{t("Rainfall evacuation by house type", "বৃষ্টিপাতে আশ্রয় (ঘরভেদে)")}:</span>
              <ul className="mt-1 space-y-0.5 pl-4 text-xs text-muted-foreground">
                {rainfallEvac.map((it) => (
                  <li key={it.houseTypes}>
                    <span className="font-medium text-navy-800">{it.houseTypes}</span>:{" "}
                    {it.areas.length ? it.areas.join(", ") : "—"}
                  </li>
                ))}
              </ul>
            </li>
          )}
        </ul>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stat(t("Total unions", "মোট ইউনিয়ন"), String(block.total_unions ?? "—"))}
        {stat(t("Total upazilas", "মোট উপজেলা"), String(block.total_upazilas ?? "—"))}
        {stat(t("Total districts", "মোট জেলা"), String(block.total_districts ?? "—"))}
        {stat(t("Damage model", "ক্ষয়ক্ষতি মডেল"), damageModel)}
        {stat(t("Top-risk unions", "শীর্ষ ঝুঁকির ইউনিয়ন"), riskNames)}
        {stat(t("Top-rain unions", "শীর্ষ বৃষ্টির ইউনিয়ন"), rainNames)}
      </dl>
    </Card>
  );
}
