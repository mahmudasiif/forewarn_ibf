import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export const SEVERITY_LEVELS = ["none", "advisory", "moderate", "severe", "extreme"] as const;
export type Severity = (typeof SEVERITY_LEVELS)[number];

const LABELS: Record<Severity, string> = {
  none: "None",
  advisory: "Advisory",
  moderate: "Moderate",
  severe: "Severe",
  extreme: "Extreme",
};

/** Colour and text colour are set by the Badge variant — see badge.tsx. */
export function SeverityBadge({
  level,
  className,
  showLevelNumber = false,
}: {
  level: Severity;
  className?: string;
  showLevelNumber?: boolean;
}) {
  return (
    <Badge variant={`severity-${level}`} className={className}>
      {showLevelNumber && (
        <span className="tabular-nums opacity-80">{SEVERITY_LEVELS.indexOf(level) + 1}</span>
      )}
      {LABELS[level]}
    </Badge>
  );
}

export function SeverityLegend({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Impact level
      </span>
      {SEVERITY_LEVELS.map((level) => (
        <SeverityBadge key={level} level={level} showLevelNumber />
      ))}
    </div>
  );
}
