import { useEffect, useRef, useState } from "react";
import { Loader2, Map as MapIcon } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { cn } from "@/lib/utils";
import { useAreaMap, type AnalysisContext, type AreaMetric, type Lang } from "@/lib/preparednessApi";

const METRICS: { value: AreaMetric; bn: string; en: string }[] = [
  { value: "wind", bn: "বাতাসের গতি", en: "Wind speed" },
  { value: "rainfall", bn: "বৃষ্টিপাত", en: "Rainfall" },
  { value: "surge", bn: "ঝড়জলোচ্ছ্বাস", en: "Storm surge" },
  { value: "risk", bn: "ঝুঁকি শ্রেণী", en: "Risk class" },
];

export function AreaMaps({ runId, context, lang }: { runId: number; context: AnalysisContext; lang: Lang }) {
  const areaMap = useAreaMap(runId);
  const [metric, setMetric] = useState<AreaMetric>("wind");
  const [url, setUrl] = useState<string>("");
  const urlRef = useRef<string>("");

  useEffect(() => {
    const level = context.admin_level ?? "union";
    const geoCode =
      level === "union"
        ? String(context.boundary_geo_code || context.geo_code || "")
        : String(context.geo_code || "");
    areaMap.mutate(
      {
        level,
        metric,
        district: context.district ?? "",
        upazila: context.upazila ?? "",
        union: context.union ?? context.name ?? "",
        geo_code: geoCode,
        lang,
      },
      {
        onSuccess: (blobUrl) => {
          if (urlRef.current) URL.revokeObjectURL(urlRef.current);
          urlRef.current = blobUrl;
          setUrl(blobUrl);
        },
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, context.geo_code, metric, lang]);

  useEffect(() => () => void (urlRef.current && URL.revokeObjectURL(urlRef.current)), []);

  return (
    <Card
      title={lang === "en" ? "Area map" : "এলাকার মানচিত্র"}
      bodyClassName="space-y-3"
      action={
        <div className="flex flex-wrap items-center gap-1.5">
          <MapIcon className="size-4 text-muted-foreground" />
          {METRICS.map((m) => (
            <button
              key={m.value}
              onClick={() => setMetric(m.value)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                metric === m.value
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:text-foreground",
              )}
            >
              {lang === "en" ? m.en : m.bn}
            </button>
          ))}
        </div>
      }
    >
      <div className="flex min-h-[320px] items-center justify-center overflow-hidden rounded-lg border border-border bg-muted">
        {areaMap.isPending ? (
          <Loader2 className="size-6 animate-spin text-green-700" />
        ) : areaMap.isError ? (
          <p className="px-4 py-8 text-center text-xs text-sunrise-900">
            {lang === "en" ? "Could not build the area map." : "এলাকার মানচিত্র তৈরি করা যায়নি।"}
          </p>
        ) : url ? (
          <img src={url} alt="Area map" className="max-h-[520px] w-full object-contain" />
        ) : null}
      </div>
    </Card>
  );
}
