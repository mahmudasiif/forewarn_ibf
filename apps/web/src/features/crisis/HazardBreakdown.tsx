import { useMemo } from "react";

import type { Incident } from "./mockIncidents";

/**
 * Incidents by hazard type, as a ranked horizontal bar list.
 *
 * The job here is magnitude comparison, so bar length carries the value and a
 * single hue carries no meaning beyond "this is the measure" — hazard identity
 * is already given by the row label, so colouring each bar differently would
 * add a second encoding for something the reader can already see. One hue also
 * sidesteps the colour-blindness problem entirely.
 */
export function HazardBreakdown({ incidents }: { incidents: Incident[] }) {
  const rows = useMemo(() => {
    const counts = new Map<string, number>();
    for (const incident of incidents) {
      counts.set(incident.hazard, (counts.get(incident.hazard) ?? 0) + 1);
    }
    const total = incidents.length || 1;
    return [...counts.entries()]
      .map(([hazard, count]) => ({ hazard, count, share: (count / total) * 100 }))
      .sort((a, b) => b.count - a.count);
  }, [incidents]);

  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No incidents to break down.</p>;
  }

  // Scale to the largest bar, not to the total — otherwise every bar is a
  // sliver as soon as one hazard dominates, which is the usual case here.
  const max = Math.max(...rows.map((r) => r.count));

  return (
    <ul className="space-y-3">
      {rows.map((row) => (
        <li key={row.hazard} className="group">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-xs font-medium text-foreground">{row.hazard}</span>
            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
              {row.count}
              <span className="ml-1.5 text-[11px] opacity-70">{row.share.toFixed(0)}%</span>
            </span>
          </div>
          {/* Thin mark, rounded data-end, recessive track. */}
          <div className="mt-1.5 h-2 w-full rounded-full bg-navy-50">
            <div
              className="h-2 rounded-full bg-navy-700 transition-[width] duration-300 group-hover:bg-navy-900"
              style={{ width: `${Math.max((row.count / max) * 100, 3)}%` }}
              title={`${row.hazard}: ${row.count} incident${row.count === 1 ? "" : "s"} (${row.share.toFixed(0)}%)`}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
