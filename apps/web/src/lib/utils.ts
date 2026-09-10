import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const SEVERITY = ["none", "advisory", "moderate", "severe", "extreme"] as const;
export type Severity = (typeof SEVERITY)[number];

export const severityColor: Record<Severity, string> = {
  none: "var(--color-severity-none)",
  advisory: "var(--color-severity-advisory)",
  moderate: "var(--color-severity-moderate)",
  severe: "var(--color-severity-severe)",
  extreme: "var(--color-severity-extreme)",
};
