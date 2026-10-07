import { useEffect, useMemo, useState } from "react";
import { Clock } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import { Card } from "@/components/shared/Card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  mergeMaps,
  useAreas,
  useDfrmForecastLatest,
  useForecastDayMaps,
  useLiveForecastMap,
  type DFRMLevel,
  type ForecastDay,
  type MapLayer,
  type MapRequest,
} from "@/lib/dfrmApi";
import { DFRMMap } from "./DFRMMap";

/** Phase chip colours — mirrors FFWC's Normal / Warning / Flood legend. */
const PHASE_STYLE: Record<string, string> = {
  Normal: "bg-green-100 text-navy-900",
  Warning: "bg-sunrise-100 text-navy-900",
  Flood: "bg-red-200 text-red-900",
};

/** Preferred display order for the layer switcher. */
const LAYER_ORDER: MapLayer[] = ["Inundation", "Hazard", "Risk", "Vulnerability"];
const LEVELS: DFRMLevel[] = ["District", "Upazilla", "Union"];
/** District-dropdown sentinel for the merged both-districts view. */
const ALL = "all";

/** Today's date in Bangladesh (Asia/Dhaka), as YYYY-MM-DD (en-CA format). */
function bstToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(new Date());
}

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** day_index 0 (the observed day) reads Today/Yesterday by its real BST date, so
 *  a run that's gone stale shows "Yesterday" until the next run makes it today. */
function dayLabel(dayIndex: number, forecastDate: string): string {
  if (dayIndex !== 0) return `Day ${dayIndex}`;
  const today = bstToday();
  if (forecastDate === today) return "Today";
  if (forecastDate === addDays(today, -1)) return "Yesterday";
  return "Observed";
}

export function ForecastTab() {
  const q = useDfrmForecastLatest();
  const areas = useAreas();
  const set = q.data;
  const tree = areas.data;

  const [dayIndex, setDayIndex] = useState(0); // 0 = Today
  const [layer, setLayer] = useState<MapLayer | null>(null);
  const [level, setLevel] = useState<DFRMLevel>("District");
  const [distId, setDistId] = useState<string>(ALL); // "all" = both districts
  const [thanaId, setThanaId] = useState("");
  const [uniId, setUniId] = useState("");

  const layers = useMemo(() => {
    const avail = new Set((set?.days ?? []).map((d) => d.layer));
    return LAYER_ORDER.filter((l) => avail.has(l));
  }, [set]);
  const activeLayer = layer ?? layers[0] ?? "Inundation";

  // Cascade lookups from the area tree.
  const district = useMemo(() => tree?.districts.find((d) => d.id === distId), [tree, distId]);
  const upazila = useMemo(() => district?.upazilas.find((u) => u.id === thanaId), [district, thanaId]);
  const union = useMemo(() => upazila?.unions.find((u) => u.id === uniId), [upazila, uniId]);

  // Sub-district levels need a concrete district (not "both").
  useEffect(() => {
    if (level !== "District" && (distId === ALL || !distId)) {
      setDistId(tree?.districts[0]?.id ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, tree]);
  useEffect(() => {
    setThanaId(district?.upazilas[0]?.id ?? "");
  }, [district]);
  useEffect(() => {
    setUniId(upazila?.unions[0]?.id ?? "");
  }, [upazila]);

  // Per-day labels (water level / limb / phase are layer- and area-independent).
  const dayGroups = useMemo(() => {
    const byIndex = new Map<number, ForecastDay[]>();
    for (const d of set?.days ?? []) {
      const arr = byIndex.get(d.day_index) ?? [];
      arr.push(d);
      byIndex.set(d.day_index, arr);
    }
    return [...byIndex.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([index, rows]) => ({ index, rows, rep: rows[0] }));
  }, [set]);
  const selected = dayGroups.find((g) => g.index === dayIndex) ?? dayGroups[0];
  const rep = selected?.rep;

  // --- map sourcing: District = pre-generated; Upazila/Union = live on demand ---
  const isLive = level === "Upazilla" || level === "Union";
  const preGenIds = useMemo(() => {
    if (isLive) return [];
    return (selected?.rows ?? [])
      .filter((r) => r.layer === activeLayer && r.status === "ok" && r.map_url)
      .filter((r) => distId === ALL || r.area_id === distId)
      .map((r) => r.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, activeLayer, distId, isLive]);
  const preGen = useForecastDayMaps(preGenIds);

  const liveReq: MapRequest | null = useMemo(() => {
    if (!isLive || !rep) return null;
    const areaId = level === "Union" ? uniId : thanaId;
    if (!areaId) return null;
    return {
      level,
      area_id: areaId,
      layer: activeLayer,
      water_level: rep.water_level,
      wl_kind: "WL",
      limb: rep.limb,
    };
  }, [isLive, rep, level, uniId, thanaId, activeLayer]);
  const live = useLiveForecastMap(liveReq);

  const mergedPreGen = useMemo(() => mergeMaps(preGen.maps), [preGen.maps]);
  const mapData = isLive ? live.data : mergedPreGen;
  const mapLoading = isLive ? live.isLoading : preGen.isLoading;

  const areaLabel = useMemo(() => {
    if (level === "District") {
      if (distId === ALL)
        return [...new Set((set?.days ?? []).map((d) => d.area_name))].join(" & ");
      return district?.name ?? distId;
    }
    if (level === "Upazilla") return upazila?.name ?? thanaId;
    return union?.name ?? uniId;
  }, [level, distId, district, upazila, union, set, thanaId, uniId]);

  if (q.isLoading) {
    return (
      <Card>
        <div className="py-16 text-center text-sm text-muted-foreground">Loading forecast…</div>
      </Card>
    );
  }
  if (q.isError || !set) {
    return (
      <Card>
        <div className="py-16 text-center text-sm text-muted-foreground">
          No automated forecast yet — it runs daily once the FFWC data arrives.
        </div>
      </Card>
    );
  }

  const districtOptions = [
    ...(level === "District" ? [{ value: ALL, label: "Both districts" }] : []),
    ...(tree?.districts ?? []).map((d) => ({ value: d.id, label: d.name })),
  ];

  return (
    <div className="space-y-4">
      {/* Day selector — horizontal tabs across the top of the page body. */}
      <div className="flex overflow-x-auto rounded-lg border border-navy-200 bg-white">
        {dayGroups.map((g, i) => (
          <button
            key={g.index}
            type="button"
            onClick={() => setDayIndex(g.index)}
            className={cn(
              "flex min-w-[96px] flex-1 flex-col items-center gap-0.5 px-4 py-2.5 transition-colors",
              i > 0 && "border-l border-navy-200",
              g.index === dayIndex
                ? "bg-primary text-primary-foreground"
                : "text-navy-700 hover:bg-navy-50",
            )}
          >
            <span className="text-sm font-semibold">
              {dayLabel(g.index, g.rep.forecast_date)}
            </span>
            <span
              className={cn(
                "text-[11px]",
                g.index === dayIndex ? "text-primary-foreground/80" : "text-muted-foreground",
              )}
            >
              {g.rep.forecast_date}
            </span>
            <span
              className={cn(
                "mt-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                PHASE_STYLE[g.rep.phase] ?? "bg-navy-100 text-navy-900",
              )}
            >
              {g.rep.phase}
            </span>
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <Card title="5-Day Forecast">
          <dl className="space-y-1.5 text-xs">
            <Row k="Run date" v={set.run_date} strong />
            <Row k="Danger level" v={`${set.danger_level.toFixed(2)} m`} mono />
            <Row
              k="Latest observed"
              v={set.observed_wl != null ? `${set.observed_wl.toFixed(2)} m` : "—"}
              mono
            />
          </dl>

          {layers.length > 1 && (
            <div className="mt-3 border-t border-navy-200 pt-3">
              <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-navy-500">
                Layer
              </p>
              <div className="flex flex-wrap gap-1.5">
                {layers.map((l) => (
                  <button
                    key={l}
                    type="button"
                    onClick={() => setLayer(l)}
                    className={cn(
                      "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
                      l === activeLayer
                        ? "border-green-700 bg-green-700 text-white"
                        : "border-navy-200 text-navy-700 hover:border-green-700",
                    )}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card title="Location" subtitle="Drill into a district, upazila or union" bodyClassName="space-y-3">
          <div>
            <span className="text-xs font-medium text-navy-500">Map level</span>
            <div className="mt-1.5 flex gap-1.5">
              {LEVELS.map((l) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => setLevel(l)}
                  className={cn(
                    "flex-1 rounded-md border px-2 py-1.5 text-xs font-medium transition-colors",
                    l === level
                      ? "border-green-700 bg-green-700 text-white"
                      : "border-navy-200 text-navy-700 hover:border-green-700",
                  )}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>

          <Combo label="District" value={distId} onChange={setDistId} options={districtOptions} />
          {level !== "District" && (
            <Combo
              label="Upazila"
              value={thanaId}
              onChange={setThanaId}
              options={(district?.upazilas ?? []).map((u) => ({ value: u.id, label: u.name }))}
            />
          )}
          {level === "Union" && (
            <Combo
              label="Union"
              value={uniId}
              onChange={setUniId}
              options={(upazila?.unions ?? []).map((u) => ({ value: u.id, label: u.name }))}
            />
          )}
        </Card>

        <p className="flex items-center gap-1 px-1 text-[11px] text-muted-foreground">
          <Clock className="size-3" />
          Generated {formatDistanceToNow(new Date(set.created_at), { addSuffix: true })}
        </p>
      </div>

      <div className="min-w-0">
        <Card
          title={
            rep
              ? `${areaLabel} · ${activeLayer} — ${dayLabel(rep.day_index, rep.forecast_date)} (${rep.forecast_date})`
              : "Flood map"
          }
          subtitle={
            rep
              ? `${set.station} · water level ${rep.water_level.toFixed(2)} m · ${rep.limb}` +
                (rep.return_period != null && rep.return_period >= 2
                  ? ` · return period ${rep.return_period} yr`
                  : "")
              : undefined
          }
          bodyClassName="p-0"
        >
          <div className="h-[calc(100vh-13rem)] min-h-[520px] w-full overflow-hidden rounded-b-card bg-muted">
            <DFRMMap data={mapData} loading={mapLoading} />
          </div>
        </Card>
      </div>
      </div>
    </div>
  );
}

function Row({ k, v, strong, mono }: { k: string; v: string; strong?: boolean; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-navy-500">{k}</dt>
      <dd
        className={cn(
          "text-navy-900",
          strong && "font-medium",
          mono && "tabular-nums",
        )}
      >
        {v}
      </dd>
    </div>
  );
}

function Combo({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-navy-500">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="mt-1.5">
          <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}
