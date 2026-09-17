import { useMemo, useState } from "react";
import { Search } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { AdminLevel, AnalysisContext, Lang, RunContexts } from "@/lib/preparednessApi";

const LEVELS: { value: AdminLevel; bn: string; en: string }[] = [
  { value: "union", bn: "ইউনিয়ন", en: "Union" },
  { value: "upazila", bn: "উপজেলা", en: "Upazila" },
  { value: "district", bn: "জেলা", en: "District" },
];

const MAX_VISIBLE = 250;

function optionName(c: AnalysisContext): string {
  return String(c.name ?? c.union ?? c.upazila ?? c.district ?? "—");
}

function parentLabel(c: AnalysisContext, level: AdminLevel, lang: Lang): string {
  if (level === "union") return [c.upazila, c.district].filter(Boolean).join(", ");
  if (level === "upazila") return String(c.district ?? "");
  return lang === "en" ? "District" : "জেলা";
}

export function AreaExplorer({
  contexts,
  level,
  onLevelChange,
  selected,
  onSelect,
  lang,
}: {
  contexts: RunContexts;
  level: AdminLevel;
  onLevelChange: (l: AdminLevel) => void;
  selected: AnalysisContext | null;
  onSelect: (ctx: AnalysisContext) => void;
  lang: Lang;
}) {
  const [q, setQ] = useState("");

  const sorted = useMemo(() => {
    return (contexts.analysis_contexts ?? [])
      .filter((c) => (c.admin_level ?? "union") === level)
      .sort((a, b) => optionName(a).localeCompare(optionName(b), "bn", { sensitivity: "base" }));
  }, [contexts, level]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return sorted;
    return sorted.filter((c) =>
      `${c.name ?? ""} ${c.union ?? ""} ${c.upazila ?? ""} ${c.district ?? ""}`.toLowerCase().includes(s),
    );
  }, [sorted, q]);

  const visible = filtered.slice(0, MAX_VISIBLE);

  return (
    <Card
      title={lang === "en" ? "Administrative level" : "প্রশাসনিক স্তর"}
      subtitle={`${filtered.length.toLocaleString(lang === "bn" ? "bn-BD" : "en-US")} ${lang === "en" ? "areas" : "টি এলাকা"}`}
      bodyClassName="space-y-3"
    >
      <div className="flex gap-1.5">
        {LEVELS.map((l) => (
          <button
            key={l.value}
            onClick={() => onLevelChange(l.value)}
            className={cn(
              "flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
              level === l.value
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground",
            )}
          >
            {lang === "en" ? l.en : l.bn}
          </button>
        ))}
      </div>

      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-8"
          placeholder={lang === "en" ? "Search…" : "অনুসন্ধান করুন…"}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div className="max-h-[420px] space-y-1 overflow-y-auto pr-1">
        {visible.length === 0 ? (
          <p className="py-6 text-center text-xs text-muted-foreground">
            {lang === "en" ? "No results found." : "কোন ফলাফল পাওয়া যায়নি।"}
          </p>
        ) : (
          visible.map((ctx) => {
            const active = selected?.geo_code === ctx.geo_code;
            const parent = parentLabel(ctx, level, lang);
            return (
              <button
                key={String(ctx.geo_code ?? optionName(ctx))}
                onClick={() => onSelect(ctx)}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors",
                  active
                    ? "border-green-700 bg-accent text-foreground"
                    : "border-border bg-card hover:border-green-700",
                )}
              >
                <span className="min-w-0 truncate font-medium">{optionName(ctx)}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">{parent}</span>
              </button>
            );
          })
        )}
      </div>

      {filtered.length > visible.length && (
        <p className="text-[11px] text-muted-foreground">
          {lang === "en"
            ? `Showing the first ${MAX_VISIBLE} results — search to narrow.`
            : `দ্রুত লোডিংয়ের জন্য প্রথম ${MAX_VISIBLE.toLocaleString("bn-BD")}টি দেখানো হচ্ছে — নির্দিষ্ট এলাকা পেতে অনুসন্ধান করুন।`}
        </p>
      )}
    </Card>
  );
}
