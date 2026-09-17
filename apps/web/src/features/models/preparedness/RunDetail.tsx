import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";
import { Download, FileText, Loader2, Map as MapIcon } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { StatTile } from "@/components/shared/StatTile";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  artifactUrl,
  useRun,
  useRunContexts,
  type AdminLevel,
  type AnalysisContext,
  type ArtifactInfo,
  type Lang,
} from "@/lib/preparednessApi";
import { AreaExplorer } from "./AreaExplorer";
import { AreaMaps } from "./AreaMaps";
import { GuidelinePanel } from "./GuidelinePanel";
import { ImpactTable } from "./ImpactTable";
import { KeyMetrics } from "./KeyMetrics";

function num(value: unknown, digits = 0): string {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";
}
function str(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "—";
}
function rec(summary: Record<string, unknown> | null | undefined, key: string): Record<string, unknown> {
  return (summary?.[key] as Record<string, unknown>) ?? {};
}

export function RunDetail({ runId }: { runId: number }) {
  const { data: run, isLoading } = useRun(runId);
  const [lang, setLang] = useState<Lang>("bn");
  const [level, setLevel] = useState<AdminLevel>("union");
  const [area, setArea] = useState<AnalysisContext | null>(null);
  const [activeMap, setActiveMap] = useState(0);

  const succeeded = run?.status === "succeeded";
  const contexts = useRunContexts(runId, succeeded);

  const maps = useMemo<ArtifactInfo[]>(
    () => (run?.artifacts ?? []).filter((a) => a.content_type === "text/html"),
    [run],
  );
  const trackMap = useMemo(
    () => (run?.artifacts ?? []).find((a) => a.content_type === "image/jpeg"),
    [run],
  );

  // Reset the selected area when switching runs.
  useEffect(() => setArea(null), [runId]);

  if (isLoading || !run) {
    return (
      <Card>
        <div className="py-16 text-center text-sm text-muted-foreground">Loading run…</div>
      </Card>
    );
  }

  if (run.status === "queued" || run.status === "running") {
    return (
      <Card title={run.cyclone_name} subtitle={`Run #${run.id}`}>
        <div className="flex flex-col items-center gap-3 py-14 text-center">
          <Loader2 className="size-6 animate-spin text-green-700" />
          <p className="text-sm font-medium">
            {run.status === "queued" ? "Queued…" : "Running the impact pipeline…"}
          </p>
          <p className="max-w-sm text-xs leading-relaxed text-navy-700">
            Mapping hazards over the boundaries, rendering maps and writing the guideline. This page
            updates itself when the run finishes.
          </p>
        </div>
      </Card>
    );
  }

  if (run.status === "failed") {
    return (
      <Card title={run.cyclone_name} subtitle={`Run #${run.id} — failed`}>
        <div className="rounded-lg border border-border bg-muted px-4 py-3 text-sm text-sunrise-900">
          <p className="font-medium">The run failed.</p>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs text-navy-700">
            {run.error ?? "No error detail recorded."}
          </pre>
        </div>
      </Card>
    );
  }

  const summary = run.summary ?? {};
  const track = rec(summary, "cyclone_track");
  const forecast = rec(track, "forecast_state");
  const current = rec(track, "current_state");
  const guidelineHtml = run.guideline_markdown
    ? (marked.parse(run.guideline_markdown, { async: false }) as string)
    : "";
  const rainfallWindowHours =
    (contexts.data?.rainfall_window_hours ?? (rec(summary, "input_metadata").rainfall_accumulation_hours as number)) ??
    null;
  const warnings =
    ((lang === "en" ? summary["data_quality_warnings_en"] : summary["data_quality_warnings"]) as string[]) ?? [];
  const inputType = String(rec(summary, "summary").input_type ?? summary["input_type"] ?? "");

  return (
    <div className="space-y-6">
      {/* language toggle */}
      <div className="flex items-center justify-end gap-1.5">
        {(["bn", "en"] as const).map((l) => (
          <button
            key={l}
            onClick={() => setLang(l)}
            className={cn(
              "rounded-md px-3 py-1 text-xs font-medium transition-colors",
              lang === l ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground",
            )}
          >
            {l === "bn" ? "বাংলা" : "English"}
          </button>
        ))}
      </div>

      {/* situation briefing */}
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="IMD category" value={str(forecast.category_imd_en ?? current.category_imd_en)} context="at landfall" />
        <StatTile label="Landfall wind" value={num(forecast.landfall_wind_kmh ?? rec(summary, "max_wind_record").wind_speed_kmh)} context="km/hr" />
        <StatTile label="Max surge" value={num(rec(summary, "max_storm_surge_record").storm_surge_m, 1)} context="metres" />
        <StatTile label="Max 72h rainfall" value={num(rec(summary, "max_rain_record").total_rainfall_mm)} context="mm" />
      </section>

      {warnings.length > 0 && (
        <div className="rounded-card border border-amber-700/40 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p className="font-semibold">
            {lang === "en"
              ? "Data quality warning — verify before operational use"
              : "ডেটা মানের সতর্কতা — পরিচালনগত ব্যবহারের আগে যাচাই করুন"}
          </p>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-xs">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {trackMap && (
          <Card title={lang === "en" ? "Cyclone track" : "ঘূর্ণিঝড়ের গতিপথ"} bodyClassName="p-0">
            <img
              src={artifactUrl(run.id, trackMap.name)}
              alt="Cyclone track"
              className="max-h-[520px] w-full rounded-b-card object-contain"
            />
          </Card>
        )}
        <KeyMetrics summary={summary} contexts={contexts.data} lang={lang} />
      </div>

      {inputType === "tabular" && (
        <p className="rounded-lg border border-border bg-muted px-4 py-2 text-xs text-navy-700">
          {lang === "en"
            ? "This was a tabular (CSV/Excel) run — only areas present in the uploaded table are selectable below."
            : "এটি একটি টেবুলার (CSV/Excel) রান — কেবল আপলোড করা টেবিলে থাকা এলাকাগুলো নিচে নির্বাচন করা যাবে।"}
        </p>
      )}

      {/* interactive area explorer + per-area maps/guideline */}
      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="lg:sticky lg:top-6 lg:self-start">
          {contexts.isLoading ? (
            <Card><div className="py-10 text-center text-sm text-muted-foreground">Loading areas…</div></Card>
          ) : contexts.data ? (
            <AreaExplorer
              contexts={contexts.data}
              level={level}
              onLevelChange={setLevel}
              selected={area}
              onSelect={setArea}
              lang={lang}
            />
          ) : (
            <Card><div className="py-10 text-center text-xs text-muted-foreground">Area data unavailable.</div></Card>
          )}
        </div>

        <div className="min-w-0 space-y-6">
          {area ? (
            <>
              <AreaMaps runId={run.id} context={area} lang={lang} />
              {contexts.data && (
                <ImpactTable
                  contexts={contexts.data}
                  selected={area}
                  lang={lang}
                  rainfallWindowHours={rainfallWindowHours}
                />
              )}
              <GuidelinePanel runId={run.id} context={area} lang={lang} />
            </>
          ) : (
            <Card>
              <div className="flex flex-col items-center gap-2 py-16 text-center">
                <FileText className="size-6 text-muted-foreground" />
                <p className="max-w-sm text-sm text-navy-700">
                  {lang === "en"
                    ? "Select an area from the list to see its maps and generate a guideline."
                    : "মানচিত্র ও নির্দেশিকা দেখতে তালিকা থেকে একটি এলাকা নির্বাচন করুন।"}
                </p>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* whole-cyclone maps produced by the run */}
      {maps.length > 0 && (
        <Card
          title="Cyclone-wide maps"
          subtitle={maps[activeMap]?.label}
          bodyClassName="p-0"
          action={
            <div className="flex flex-wrap items-center gap-1.5">
              <MapIcon className="size-4 text-muted-foreground" />
              {maps.map((m, i) => (
                <Button key={m.name} size="sm" variant={i === activeMap ? "secondary" : "ghost"} onClick={() => setActiveMap(i)}>
                  {m.label.replace(/\s*\(HTML\)$/, "")}
                </Button>
              ))}
            </div>
          }
        >
          <div className="h-[520px] w-full overflow-hidden rounded-b-card bg-muted">
            <iframe key={maps[activeMap].name} src={artifactUrl(run.id, maps[activeMap].name)} title={maps[activeMap].label} className="size-full border-0" />
          </div>
        </Card>
      )}

      {/* base guideline (whole cyclone, produced by the run) */}
      {run.guideline_markdown && (
        <Card
          title="Base guideline"
          subtitle={run.llm_polished ? "Language-model polished" : "Base (no LLM polish)"}
          action={<FileText className="size-4 text-muted-foreground" />}
        >
          <div
            className="max-w-none text-sm leading-relaxed text-navy-800 [&_h1]:font-display [&_h1]:text-xl [&_h1]:font-bold [&_h2]:font-display [&_h2]:mt-5 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:mt-4 [&_h3]:font-semibold [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_p]:my-2 [&_table]:my-3 [&_table]:w-full [&_table]:text-xs [&_th]:border [&_th]:border-border [&_th]:bg-muted [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1"
            dangerouslySetInnerHTML={{ __html: guidelineHtml }}
          />
        </Card>
      )}

      <Card title="Downloads" subtitle="Maps, spreadsheets and the guideline">
        {run.artifacts && run.artifacts.length > 0 ? (
          <ul className="grid gap-2 sm:grid-cols-2">
            {run.artifacts.map((a) => (
              <li key={a.name}>
                <a
                  href={artifactUrl(run.id, a.name)}
                  download={a.name}
                  className="flex items-center gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-sm text-navy-800 hover:border-green-700"
                >
                  <Download className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate">{a.label}</span>
                  <span className="text-xs text-muted-foreground">{(a.size / 1024).toFixed(0)} KB</span>
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No artifacts produced.</p>
        )}
      </Card>
    </div>
  );
}
