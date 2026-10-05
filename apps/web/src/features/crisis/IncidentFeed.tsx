import { CheckCircle2, Clock3, MapPin, XCircle } from "lucide-react";

import { SeverityBadge } from "@/components/shared/SeverityBadge";
import { cn } from "@/lib/utils";
import { SEVERITY_HEX, timeAgo } from "./severity";
import type { Incident } from "./mockIncidents";

/**
 * The newest incidents, as a scannable column beside the map.
 *
 * This is the "what just happened" view: ordered strictly by time, not by
 * severity, because an operator checking the dashboard wants to know what has
 * changed since they last looked. Severity is shown on each row, but it never
 * reorders the feed.
 */
export function IncidentFeed({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: Incident[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (incidents.length === 0) {
    return (
      <p className="px-5 py-10 text-center text-sm text-muted-foreground">
        Nothing matches the current filters.
      </p>
    );
  }

  return (
    <ul className="max-h-[520px] divide-y divide-border overflow-y-auto">
      {incidents.map((incident) => {
        const selected = incident.id === selectedId;
        return (
          <li key={incident.id}>
            <button
              type="button"
              onClick={() => onSelect(incident.id)}
              className={cn(
                "flex w-full gap-3 px-5 py-3.5 text-left transition-colors hover:bg-navy-50",
                selected && "bg-navy-50",
              )}
            >
              {/* A coloured rule, not a dot: it ties the row to its severity
                  without competing with the badge for attention. */}
              <span
                className="mt-0.5 w-1 shrink-0 rounded-full"
                style={{ background: SEVERITY_HEX[incident.severity] }}
                aria-hidden
              />

              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 text-sm font-medium leading-snug text-foreground">
                    {incident.title}
                  </p>
                  <VerificationIcon status={incident.status} />
                </div>

                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="size-3" />
                    {incident.district}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Clock3 className="size-3" />
                    {timeAgo(incident.reportedAt)}
                  </span>
                  <span>{incident.hazard}</span>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <SeverityBadge level={incident.severity} />
                  {incident.deaths > 0 && (
                    <span className="text-[11px] font-medium text-sunrise-900">
                      {incident.deaths} dead
                    </span>
                  )}
                  {incident.affected > 0 && (
                    <span className="text-[11px] text-navy-700">
                      {incident.affected.toLocaleString()} affected
                    </span>
                  )}
                </div>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Verification carries an icon as well as colour — status is never colour alone. */
function VerificationIcon({ status }: { status: Incident["status"] }) {
  if (status === "validated") {
    return <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-green-700" aria-label="Validated" />;
  }
  if (status === "rejected") {
    return <XCircle className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-label="Rejected" />;
  }
  return (
    <Clock3 className="mt-0.5 size-3.5 shrink-0 text-amber-700" aria-label="Awaiting validation" />
  );
}
