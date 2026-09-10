import { cn } from "@/lib/utils";

export type ServiceStatus = "healthy" | "degraded" | "offline" | "unknown";

const STYLES: Record<ServiceStatus, { dot: string; label: string; text: string }> = {
  healthy: { dot: "bg-green-700", label: "Healthy", text: "text-green-700" },
  degraded: { dot: "bg-amber-700", label: "Degraded", text: "text-amber-900" },
  offline: { dot: "bg-sunrise-900", label: "Offline", text: "text-sunrise-900" },
  unknown: { dot: "bg-navy-500", label: "Unknown", text: "text-muted-foreground" },
};

export function StatusDot({
  status,
  withLabel = true,
  className,
}: {
  status: ServiceStatus;
  withLabel?: boolean;
  className?: string;
}) {
  const style = STYLES[status];
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className={cn("size-2 shrink-0 rounded-full", style.dot)} />
      {withLabel && <span className={cn("text-xs font-medium", style.text)}>{style.label}</span>}
    </span>
  );
}
