import { useMemo, type ReactNode } from "react";

import { Card } from "@/components/shared/Card";
import type { AnalysisContext, Lang, RunContexts } from "@/lib/preparednessApi";
import { areaLabel } from "./areaLabel";
import { fmtAffected, fmtAffectedDemographic, fmtExposed, fmtNumber, impactTableHeaders } from "./format";

function Row({ ctx, lang, label }: { ctx: AnalysisContext; lang: Lang; label: string }) {
  return (
    <tr className="border-t border-border text-navy-800 odd:bg-muted/40">
      <td className="px-3 py-2">{label}</td>
      <td className="px-3 py-2">{fmtNumber(ctx.wind_speed_kmh, lang, 1)}</td>
      <td className="px-3 py-2">{fmtNumber(ctx.storm_surge_m, lang, 2)}</td>
      <td className="px-3 py-2">{fmtNumber(ctx.total_rainfall_mm, lang, 1)}</td>
      <td className="px-3 py-2">{fmtExposed(ctx, lang)}</td>
      <td className="px-3 py-2">{fmtAffected(ctx.affected_people, ctx.affected_people_pct, ctx.impact_modelled, lang)}</td>
      <td className="px-3 py-2">{fmtAffectedDemographic(ctx, "male", lang)}</td>
      <td className="px-3 py-2">{fmtAffectedDemographic(ctx, "female", lang)}</td>
      <td className="px-3 py-2">{fmtAffectedDemographic(ctx, "age_0_4", lang)}</td>
      <td className="px-3 py-2">{fmtAffectedDemographic(ctx, "age_5_19", lang)}</td>
      <td className="px-3 py-2">{fmtAffectedDemographic(ctx, "age_60_plus", lang)}</td>
      <td className="px-3 py-2">{fmtAffected(ctx.affected_houses, ctx.affected_houses_pct, ctx.impact_modelled, lang)}</td>
    </tr>
  );
}

function Table({ headers, children }: { headers: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[1100px] text-left text-xs">
        <thead className="bg-primary text-primary-foreground">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function ImpactTable({
  contexts,
  selected,
  lang,
  rainfallWindowHours,
}: {
  contexts: RunContexts;
  selected: AnalysisContext;
  lang: Lang;
  rainfallWindowHours: number | null | undefined;
}) {
  const headers = impactTableHeaders(rainfallWindowHours);

  const childAreas = useMemo(() => {
    const norm = (v: unknown) => String(v ?? "").trim().toLowerCase();
    const level = selected.admin_level ?? "union";
    const all = contexts.analysis_contexts ?? [];
    const at = (lvl: string) => all.filter((c) => (c.admin_level ?? "union") === lvl);
    if (level === "upazila") {
      const target = norm(selected.upazila || selected.name);
      const district = norm(selected.district);
      const rows = at("union").filter(
        (c) => norm(c.upazila) === target && (!district || norm(c.district) === district),
      );
      return rows.length ? { title: lang === "en" ? "Unions in this upazila" : "এই উপজেলার ইউনিয়নসমূহ", rows } : null;
    }
    if (level === "district") {
      const target = norm(selected.district || selected.name);
      const rows = at("upazila").filter((c) => norm(c.district) === target);
      return rows.length ? { title: lang === "en" ? "Upazilas in this district" : "এই জেলার উপজেলাসমূহ", rows } : null;
    }
    return null;
  }, [contexts, selected, lang]);

  return (
    <Card title={lang === "en" ? "Cyclone impact — summary table" : "ঘূর্ণিঝড় প্রভাব — সারসংক্ষেপ"} bodyClassName="space-y-5">
      <Table headers={headers}>
        <Row ctx={selected} lang={lang} label={areaLabel(selected, lang)} />
      </Table>

      {childAreas && (
        <div>
          <p className="mb-2 text-sm font-semibold text-foreground">
            {childAreas.title}{" "}
            <span className="font-normal text-muted-foreground">
              ({childAreas.rows.length.toLocaleString(lang === "bn" ? "bn-BD" : "en-US")}{" "}
              {lang === "en" ? "areas" : "টি এলাকা"})
            </span>
          </p>
          <div className="max-h-96 overflow-auto">
            <Table headers={headers}>
              {childAreas.rows.map((row, i) => (
                <Row
                  key={String(row.geo_code ?? `${row.name}-${i}`)}
                  ctx={row}
                  lang={lang}
                  label={String(row.name || row.union || row.upazila || "—")}
                />
              ))}
            </Table>
          </div>
        </div>
      )}
    </Card>
  );
}
