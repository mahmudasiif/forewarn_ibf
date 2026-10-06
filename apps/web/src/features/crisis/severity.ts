/**
 * Severity is a *status* encoding, not a categorical one: the five levels are
 * ordered and reserved, so they never double as chart series colours. The hex
 * values mirror --color-severity-* in globals.css, needed here because Leaflet
 * paints canvas and cannot read a Tailwind class.
 */
import type { Severity } from "@/components/shared/SeverityBadge";

export const SEVERITY_HEX: Record<Severity, string> = {
  none: "#00a385",
  advisory: "#fd9a00",
  moderate: "#c67c00",
  severe: "#ff603a",
  extreme: "#b93940",
};

/** Marker radius grows with severity, so the map reads without colour alone. */
export const SEVERITY_RADIUS: Record<Severity, number> = {
  none: 6,
  advisory: 7,
  moderate: 8,
  severe: 10,
  extreme: 12,
};

export const SEVERITY_ORDER: Severity[] = ["extreme", "severe", "moderate", "advisory", "none"];

/** "2h ago" / "3d ago" — relative time reads faster than a timestamp in a feed. */
export function timeAgo(iso: string, now: Date = new Date("2026-10-02T14:00:00+06:00")): string {
  const minutes = Math.round((now.getTime() - new Date(iso).getTime()) / 60_000);
  if (minutes < 60) return `${Math.max(minutes, 1)}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** 24500 -> "24,500"; 0 -> "—", because a zero casualty count is not news. */
export function formatCount(value: number): string {
  return value === 0 ? "—" : value.toLocaleString();
}
