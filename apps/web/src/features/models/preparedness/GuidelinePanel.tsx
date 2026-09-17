import { useEffect, useState } from "react";
import { AlertTriangle, Download, FileText, Loader2, Sparkles } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import {
  IMPACT_SECTOR_CARDS,
  downloadGuidelineDocx,
  useGenerateGuideline,
  type AnalysisContext,
  type GuidelineDocument,
  type ImpactCategory,
  type Lang,
} from "@/lib/preparednessApi";
import { areaLabel } from "./areaLabel";

function SectorCards({ bySector }: { bySector: Record<ImpactCategory, string[]> }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {IMPACT_SECTOR_CARDS.map(([label, key]) => (
        <div key={key} className="rounded-lg border border-border bg-muted/40 p-3">
          <p className="text-xs font-semibold text-foreground">{label}</p>
          {(bySector?.[key] ?? []).length ? (
            <ul className="mt-1.5 list-disc space-y-1 pl-4 text-sm text-navy-800">
              {(bySector[key] ?? []).map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-xs text-muted-foreground">—</p>
          )}
        </div>
      ))}
    </div>
  );
}

function FieldRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 py-1 text-sm">
      <span className="min-w-[9rem] shrink-0 font-medium text-muted-foreground">{label}</span>
      <span className="text-navy-800">{value}</span>
    </div>
  );
}

export function GuidelinePanel({
  runId,
  context,
  lang,
}: {
  runId: number;
  context: AnalysisContext;
  lang: Lang;
}) {
  const gen = useGenerateGuideline(runId);
  const [doc, setDoc] = useState<GuidelineDocument | null>(null);
  const [downloading, setDownloading] = useState(false);

  // Clear the shown guideline whenever the selected area changes.
  useEffect(() => setDoc(null), [context.geo_code]);

  const generate = () => gen.mutate({ context, lang }, { onSuccess: setDoc });

  const status = (gen.error as { response?: { status?: number } } | null)?.response?.status;
  const noKey = status === 503;

  if (!doc) {
    return (
      <Card title={lang === "en" ? "Preparedness guideline" : "প্রস্তুতি নির্দেশিকা"}>
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-accent">
            <FileText className="size-6 text-green-700" />
          </span>
          <p className="max-w-sm text-sm text-navy-700">
            {lang === "en"
              ? `Generate an impact-based guideline for ${areaLabel(context, lang)}.`
              : `${areaLabel(context, lang)}-এর জন্য নির্দেশিকা তৈরি করুন।`}
          </p>
          {gen.isError && (
            <div className="flex items-start gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-xs text-sunrise-900">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span>
                {noKey
                  ? lang === "en"
                    ? "The language model key is not configured, so the structured guideline is unavailable. The base guideline is still on the run's downloads."
                    : "ভাষা মডেলের কী কনফিগার করা নেই, তাই কাঠামোবদ্ধ নির্দেশিকা তৈরি করা যাচ্ছে না।"
                  : lang === "en"
                    ? "Could not generate the guideline. Try again."
                    : "নির্দেশিকা তৈরি করা যায়নি। আবার চেষ্টা করুন।"}
              </span>
            </div>
          )}
          <Button onClick={generate} disabled={gen.isPending}>
            {gen.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {gen.isPending
              ? lang === "en"
                ? "Generating guideline…"
                : "গাইডলাইন তৈরি হচ্ছে…"
              : lang === "en"
                ? "Generate guideline"
                : "গাইডলাইন তৈরি করুন"}
          </Button>
        </div>
      </Card>
    );
  }

  const t = (en: string, bn: string) => (lang === "en" ? en : bn);

  return (
    <div className="space-y-6">
      {doc.dataQualityWarnings && doc.dataQualityWarnings.length > 0 && (
        <div className="rounded-card border border-amber-700/40 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p className="font-semibold">{t("Data quality warning", "ডেটা মানের সতর্কতা")}</p>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-xs">
            {doc.dataQualityWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <Card
        title={t("Preparedness guideline", "প্রস্তুতি নির্দেশিকা")}
        subtitle={doc.selectedArea}
        action={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={generate} disabled={gen.isPending}>
              {gen.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
              {t("Regenerate", "পুনরায়")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={downloading}
              onClick={async () => {
                setDownloading(true);
                try {
                  await downloadGuidelineDocx(runId, doc);
                } finally {
                  setDownloading(false);
                }
              }}
            >
              <Download />
              {t("Word", "Word")}
            </Button>
          </div>
        }
      >
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <p className="mb-1 font-display text-sm font-semibold">{t("Current state", "বর্তমান অবস্থা")}</p>
            <FieldRow label={t("Name", "নাম")} value={doc.currentState.name} />
            <FieldRow label={t("Category (IMD)", "শ্রেণী (IMD)")} value={doc.currentState.category} />
            <FieldRow label={t("Wind speed", "বাতাসের গতি")} value={doc.currentState.windSpeedKmh} />
            <FieldRow label={t("Direction", "দিক")} value={doc.currentState.direction} />
            <FieldRow label={t("Location", "অবস্থান")} value={doc.currentState.location} />
          </div>
          <div>
            <p className="mb-1 font-display text-sm font-semibold">{t("Forecast state", "পূর্বাভাস")}</p>
            <FieldRow label={t("Landfall", "ল্যান্ডফল")} value={doc.forecastState.landfallLocation} />
            <FieldRow label={t("Wind speed", "বাতাসের গতি")} value={doc.forecastState.windSpeed} />
            <FieldRow label={t("Storm surge", "জলোচ্ছ্বাস")} value={doc.forecastState.stormSurge} />
            <FieldRow label={t("Time", "সময়")} value={doc.forecastState.time} />
            <FieldRow label={t("Category", "শ্রেণী")} value={doc.forecastState.category} />
            <FieldRow label={t("Precipitation", "বৃষ্টিপাত")} value={doc.forecastState.precipitation} />
          </div>
        </div>
      </Card>

      <Card title={t("Major impact", "প্রধান প্রভাব")}>
        <SectorCards bySector={doc.majorImpact} />
      </Card>

      <Card title={t("Advisories", "পরামর্শ")}>
        <div className="space-y-5">
          {(["community", "institutional"] as const).map((level) => (
            <div key={level}>
              <p className="mb-2 font-display text-sm font-semibold text-green-700">
                {doc.levelLabels[level]}
              </p>
              <SectorCards bySector={doc.advisories[level]} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
