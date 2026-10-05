import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Clock, Minus } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import { Card } from "@/components/shared/Card";
import { cn } from "@/lib/utils";
import {
  useDfrmForecastLatest,
  useForecastDayMap,
  type ForecastDay,
} from "@/lib/dfrmApi";
import { DFRMMap } from "./DFRMMap";

/** Phase chip colours — mirrors FFWC's Normal / Warning / Flood legend. */
const PHASE_STYLE: Record<string, string> = {
  Normal: "bg-green-100 text-navy-900",
  Warning: "bg-sunrise-100 text-navy-900",
  Flood: "bg-red-200 text-red-900",
};

function LimbIcon({ limb }: { limb: string }) {
  if (limb === "Flood Increasing") return <ArrowUp className="size-3.5 text-red-600" />;
  if (limb === "Flood Decreasing") return <ArrowDown className="size-3.5 text-green-600" />;
  return <Minus className="size-3.5 text-muted-foreground" />;
}

function shortLimb(limb: string): string {
  return limb.replace("Flood ", "");
}

export function ForecastTab() {
  const q = useDfrmForecastLatest();
  const set = q.data;
  const [area, setArea] = useState<string | null>(null);
  const [dayIndex, setDayIndex] = useState(1);

  const areas = useMemo(() => {
    const seen = new Map<string, string>();
    for (const d of set?.days ?? []) if (!seen.has(d.area_id)) seen.set(d.area_id, d.area_name);
    return [...seen].map(([id, name]) => ({ id, name }));
  }, [set]);

  const activeArea = area ?? areas[0]?.id ?? null;
  const daysForArea = useMemo(
    () =>
      (set?.days ?? [])
        .filter((d) => d.area_id === activeArea)
        .sort((a, b) => a.day_index - b.day_index),
    [set, activeArea],
  );
  const selectedDay: ForecastDay | undefined =
    daysForArea.find((d) => d.day_index === dayIndex) ?? daysForArea[0];
  const mapQ = useForecastDayMap(selectedDay?.id ?? null);

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

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <Card title="5-Day Forecast" subtitle={`${set.source} · ${set.layer}`}>
          <dl className="space-y-1.5 text-xs">
            <div className="flex justify-between gap-2">
              <dt className="text-navy-500">Run date</dt>
              <dd className="font-medium text-navy-900">{set.run_date}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-navy-500">Station</dt>
              <dd className="text-navy-900">{set.station}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-navy-500">Danger level</dt>
              <dd className="tabular-nums text-navy-900">{set.danger_level.toFixed(2)} m</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-navy-500">Latest observed</dt>
              <dd className="tabular-nums text-navy-900">
                {set.observed_wl != null ? `${set.observed_wl.toFixed(2)} m` : "—"}
              </dd>
            </div>
          </dl>

          {areas.length > 1 && (
            <div className="mt-3 flex gap-2">
              {areas.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => setArea(a.id)}
                  className={cn(
                    "flex-1 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors",
                    a.id === activeArea
                      ? "border-green-700 bg-green-50 text-navy-900"
                      : "border-navy-200 text-navy-700 hover:border-green-700",
                  )}
                >
                  {a.name}
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card title="Days" subtitle={`${set.station} · forecast water level`} bodyClassName="p-0">
          <ul className="divide-y divide-border">
            {daysForArea.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => setDayIndex(d.day_index)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left transition-colors",
                    d.day_index === dayIndex ? "bg-green-50" : "hover:bg-navy-50",
                  )}
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">
                      Day {d.day_index} · {d.forecast_date}
                    </p>
                    <p className="flex items-center gap-1 text-xs text-muted-foreground">
                      <LimbIcon limb={d.limb} />
                      <span className="tabular-nums">{d.water_level.toFixed(2)} m</span>
                      <span>· {shortLimb(d.limb)}</span>
                    </p>
                  </div>
                  <span
                    className={cn(
                      "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium",
                      PHASE_STYLE[d.phase] ?? "bg-navy-100 text-navy-900",
                    )}
                  >
                    {d.phase}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <p className="flex items-center gap-1 px-1 text-[11px] text-muted-foreground">
          <Clock className="size-3" />
          Generated {formatDistanceToNow(new Date(set.created_at), { addSuffix: true })}
        </p>
      </div>

      <div className="min-w-0">
        <Card
          title={
            selectedDay
              ? `${selectedDay.area_name} — Day ${selectedDay.day_index} (${selectedDay.forecast_date})`
              : "Flood map"
          }
          subtitle={
            selectedDay
              ? `${set.station} · water level ${selectedDay.water_level.toFixed(2)} m · ${selectedDay.limb}` +
                (selectedDay.return_period != null && selectedDay.return_period >= 2
                  ? ` · return period ${selectedDay.return_period} yr`
                  : "")
              : undefined
          }
          bodyClassName="p-0"
        >
          <div className="h-[600px] w-full overflow-hidden rounded-b-card bg-muted">
            <DFRMMap data={mapQ.data} loading={mapQ.isLoading} />
          </div>
        </Card>
      </div>
    </div>
  );
}
