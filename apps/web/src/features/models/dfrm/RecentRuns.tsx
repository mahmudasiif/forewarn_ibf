import { formatDistanceToNow } from "date-fns";
import { Clock, Map as MapIcon, TriangleAlert } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { useDfrmRuns, type DfrmRun } from "@/lib/dfrmApi";

function when(iso: string): string {
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

function detail(run: DfrmRun): string {
  const s = run.summary ?? {};
  if (run.kind === "warning") {
    const risk = s.risk_level;
    return risk === "No Risk" || risk == null ? "No risk" : `Risk level ${risk}`;
  }
  const n = s.feature_count;
  return typeof n === "number" ? `${n} area${n === 1 ? "" : "s"}` : "map";
}

export function RecentRuns() {
  const runs = useDfrmRuns(20);
  const rows = runs.data ?? [];

  return (
    <Card
      title="Recent queries"
      subtitle={rows.length ? `${rows.length} shown` : "Every map and warning you run is logged here"}
      bodyClassName={rows.length ? "p-0" : undefined}
    >
      {rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          {runs.isLoading ? "Loading…" : "No queries yet — run a map or warning."}
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((run) => (
            <li key={run.id} className="flex items-start gap-3 px-4 py-2.5">
              <span className="mt-0.5 text-muted-foreground">
                {run.kind === "warning" ? (
                  <TriangleAlert className="size-4" />
                ) : (
                  <MapIcon className="size-4" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">
                  {run.area_name} · {run.layer}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {run.level} · {run.water_level.toFixed(2)} m {run.wl_kind} · {run.limb} · {detail(run)}
                </p>
              </div>
              <span className="flex shrink-0 items-center gap-1 whitespace-nowrap text-[11px] text-muted-foreground">
                <Clock className="size-3" />
                {when(run.created_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
