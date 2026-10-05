import { RotateCcw, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SEVERITY_LEVELS } from "@/components/shared/SeverityBadge";
import { HAZARD_TYPES } from "./mockIncidents";
import type { Filters } from "./useIncidentFilters";

/**
 * Filters sit in one row above the content they affect, so it is always
 * obvious what is being narrowed. Every control is a plain select rather than
 * a multi-select: an operator scanning a crisis feed should not have to learn
 * a widget.
 */
export function FilterBar({
  filters,
  onChange,
  districts,
  resultCount,
  totalCount,
}: {
  filters: Filters;
  onChange: (next: Filters) => void;
  districts: string[];
  resultCount: number;
  totalCount: number;
}) {
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    onChange({ ...filters, [key]: value });

  const dirty =
    filters.query !== "" ||
    filters.hazard !== "all" ||
    filters.severity !== "all" ||
    filters.district !== "all" ||
    filters.status !== "all";

  return (
    <div className="flex flex-wrap items-center gap-2 px-5 py-3">
      <div className="relative min-w-[200px] flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={filters.query}
          onChange={(e) => set("query", e.target.value)}
          placeholder="Search incidents, districts, sources…"
          className="h-9 pl-9 text-sm"
          aria-label="Search incidents"
        />
      </div>

      <Select
        label="Hazard"
        value={filters.hazard}
        onChange={(v) => set("hazard", v)}
        options={["all", ...HAZARD_TYPES]}
      />
      <Select
        label="Severity"
        value={filters.severity}
        onChange={(v) => set("severity", v)}
        options={["all", ...SEVERITY_LEVELS.filter((l) => l !== "none")]}
      />
      <Select
        label="District"
        value={filters.district}
        onChange={(v) => set("district", v)}
        options={["all", ...districts]}
      />
      <Select
        label="Validation"
        value={filters.status}
        onChange={(v) => set("status", v)}
        options={["all", "pending", "validated", "rejected"]}
      />

      <span className="ml-auto whitespace-nowrap text-xs tabular-nums text-muted-foreground">
        {resultCount} of {totalCount}
      </span>

      {dirty && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            onChange({ query: "", hazard: "all", severity: "all", district: "all", status: "all" })
          }
        >
          <RotateCcw />
          Reset
        </Button>
      )}
    </div>
  );
}

/** A native select, styled to match the Input height and border. */
function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly string[];
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border border-input bg-card px-2.5 text-sm capitalize text-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
    >
      {options.map((option) => (
        <option key={option} value={option} className="capitalize">
          {option === "all" ? `All ${label.toLowerCase()}` : option}
        </option>
      ))}
    </select>
  );
}
