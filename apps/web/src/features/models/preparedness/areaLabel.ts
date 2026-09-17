import type { AnalysisContext, Lang } from "@/lib/preparednessApi";

/** Human-readable label for an analysis area, matching the original app. */
export function areaLabel(ctx: AnalysisContext, lang: Lang): string {
  const level = ctx.admin_level ?? "union";
  const parts =
    level === "union"
      ? [ctx.union || ctx.name, ctx.upazila, ctx.district]
      : level === "upazila"
        ? [ctx.upazila || ctx.name, ctx.district]
        : [ctx.district || ctx.name];
  return parts.filter(Boolean).join(", ") || (lang === "en" ? "No data" : "তথ্য নেই");
}
