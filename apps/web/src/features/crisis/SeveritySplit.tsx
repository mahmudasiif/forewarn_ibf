import { useMemo } from "react";

import type { Severity } from "@/components/shared/SeverityBadge";
import { SEVERITY_HEX, SEVERITY_ORDER } from "./severity";
import type { Incident } from "./mockIncidents";

/**
 * How the current set of incidents distributes across severity levels.
 *
 * Severity is a reserved, ordered status encoding, so this is the one place on
 * the page where the severity colours are used as a scale. Every segment is
 * also labelled underneath — colour is never the only way to read it.
 */
export function SeveritySplit({ incidents }: { incidents: Incident[] }) {
  const { segments, total } = useMemo(() => {
    const counts = new Map<Severity, number>();
    for (const incident of incidents) {
      counts.set(incident.severity, (counts.get(incident.severity) ?? 0) + 1);
    }
    const segments = SEVERITY_ORDER.map((level) => ({
      level,
      count: counts.get(level) ?? 0,
    })).filter((s) => s.count > 0);
    return { segments, total: incidents.length };
  }, [incidents]);

  if (total === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No incidents to summarise.</p>;
  }

  return (
    <div>
      {/* One stacked bar, most severe first, with a 2px surface gap between
          segments so adjacent colours never bleed into one another. */}
      <div className="flex h-3 w-full gap-0.5 overflow-hidden">
        {segments.map((segment) => (
          <div
            key={segment.level}
            className="h-3 rounded-sm first:rounded-l-full last:rounded-r-full"
            style={{
              width: `${(segment.count / total) * 100}%`,
              background: SEVERITY_HEX[segment.level],
            }}
            title={`${segment.level}: ${segment.count} of ${total}`}
          />
        ))}
      </div>

      <ul className="mt-4 space-y-2">
        {segments.map((segment) => (
          <li key={segment.level} className="flex items-center gap-2.5">
            <span
              className="size-2.5 shrink-0 rounded-sm"
              style={{ background: SEVERITY_HEX[segment.level] }}
              aria-hidden
            />
            <span className="flex-1 text-xs capitalize text-navy-700">{segment.level}</span>
            <span className="text-xs font-medium tabular-nums text-foreground">{segment.count}</span>
            <span className="w-10 text-right text-[11px] tabular-nums text-muted-foreground">
              {Math.round((segment.count / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
