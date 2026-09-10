import { RotateCcw, SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useLocations,
  type AdminLevel,
  type CCMFilters,
  type Cyclone,
  type Metric,
  type Operator,
} from "@/lib/ccmApi";

const LEVELS: { value: AdminLevel; label: string }[] = [
  { value: "union", label: "Union" },
  { value: "upazila", label: "Upazila" },
  { value: "district", label: "District" },
  { value: "division", label: "Division" },
];

const OPERATORS: { value: Operator; label: string }[] = [
  { value: "gte", label: "at or above" },
  { value: "gt", label: "above" },
  { value: "lte", label: "at or below" },
  { value: "lt", label: "below" },
  { value: "eq", label: "exactly" },
];

/** Radix Select has no empty-string value, so "all" stands in for no filter. */
const ALL = "__all__";

type FilterPanelProps = {
  draft: CCMFilters;
  onChange: (next: CCMFilters) => void;
  onApply: () => void;
  onClear: () => void;
  cyclones: Cyclone[];
  metrics: Metric[];
  dirty: boolean;
};

/**
 * The web version of the desktop tool's input dock — same controls, same
 * order. Capped at viewport height with the actions pinned below, so Apply is
 * always reachable however long the list gets.
 */
export function FilterPanel({
  draft,
  onChange,
  onApply,
  onClear,
  cyclones,
  metrics,
  dirty,
}: FilterPanelProps) {
  const set = <K extends keyof CCMFilters>(key: K, value: CCMFilters[K]) =>
    onChange({ ...draft, [key]: value });

  const divisions = useLocations(draft.cyclone, "division");
  const districts = useLocations(draft.cyclone, "district", draft.division);
  const upazilas = useLocations(draft.cyclone, "upazila", draft.district);

  const triggerMetric = metrics.find((m) => m.key === draft.triggerMetric);
  const operatorLabel = OPERATORS.find((o) => o.value === draft.operator)?.label;

  return (
    <aside className="flex flex-col overflow-hidden rounded-card border border-border bg-card xl:max-h-[calc(100vh-6.5rem)]">
      <header className="flex shrink-0 items-center gap-2 border-b border-border px-5 py-3.5">
        <SlidersHorizontal className="size-4 text-muted-foreground" />
        <h2 className="font-display text-base font-semibold">Model inputs</h2>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {/* Cyclone */}
        <div>
          <Label htmlFor="ccm-cyclone">Cyclone</Label>
          <Select
            value={draft.cyclone}
            onValueChange={(value) =>
              onChange({ ...draft, cyclone: value, division: null, district: null, upazila: null })
            }
          >
            <SelectTrigger id="ccm-cyclone" className="mt-1.5">
              <SelectValue placeholder="Choose a cyclone" />
            </SelectTrigger>
            <SelectContent>
              {cyclones.map((cyclone) => (
                <SelectItem key={cyclone.code} value={cyclone.code}>
                  {cyclone.name}
                  {cyclone.event_date ? ` — ${formatDate(cyclone.event_date)}` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Level */}
        <div>
          <Label htmlFor="ccm-level">Select level</Label>
          <Select value={draft.level} onValueChange={(v) => set("level", v as AdminLevel)}>
            <SelectTrigger id="ccm-level" className="mt-1.5">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LEVELS.map((level) => (
                <SelectItem key={level.value} value={level.value}>
                  {level.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Location — cascading */}
        <div className="space-y-2.5 rounded-lg border border-border bg-muted p-3">
          <Label>Select location</Label>

          <Select
            value={draft.division ?? ALL}
            onValueChange={(value) =>
              onChange({
                ...draft,
                division: value === ALL ? null : value,
                district: null,
                upazila: null,
              })
            }
          >
            <SelectTrigger aria-label="Division">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All divisions</SelectItem>
              {(divisions.data ?? []).map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={draft.district ?? ALL}
            disabled={!draft.division}
            onValueChange={(value) =>
              onChange({ ...draft, district: value === ALL ? null : value, upazila: null })
            }
          >
            <SelectTrigger aria-label="District">
              <SelectValue placeholder="Pick a division first" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All districts</SelectItem>
              {(districts.data ?? []).map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={draft.upazila ?? ALL}
            disabled={!draft.district}
            onValueChange={(value) => set("upazila", value === ALL ? null : value)}
          >
            <SelectTrigger aria-label="Upazila">
              <SelectValue placeholder="Pick a district first" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All upazilas</SelectItem>
              {(upazilas.data ?? []).map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Map type */}
        <div>
          <Label htmlFor="ccm-metric">Map type</Label>
          <Select value={draft.metric} onValueChange={(v) => set("metric", v)}>
            <SelectTrigger id="ccm-metric" className="mt-1.5">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {metrics.map((metric) => (
                <SelectItem key={metric.key} value={metric.key}>
                  {metric.label}
                  {metric.unit ? ` (${metric.unit})` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="mt-1 text-[11px] text-muted-foreground">Colours the map.</p>
        </div>

        {/* Trigger */}
        <div className="space-y-2.5 rounded-lg border border-border bg-muted p-3">
          <Label htmlFor="ccm-trigger">Trigger parameter</Label>
          <Select value={draft.triggerMetric} onValueChange={(v) => set("triggerMetric", v)}>
            <SelectTrigger id="ccm-trigger">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {metrics.map((metric) => (
                <SelectItem key={metric.key} value={metric.key}>
                  {metric.label}
                  {metric.unit ? ` (${metric.unit})` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex gap-2">
            <Select value={draft.operator} onValueChange={(v) => set("operator", v as Operator)}>
              <SelectTrigger aria-label="Threshold comparison" className="flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {OPERATORS.map((op) => (
                  <SelectItem key={op.value} value={op.value}>
                    {op.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              aria-label="Threshold value"
              type="number"
              inputMode="decimal"
              step="any"
              placeholder="—"
              className="w-24"
              value={draft.threshold ?? ""}
              onChange={(event) =>
                set("threshold", event.target.value === "" ? null : Number(event.target.value))
              }
            />
          </div>

          <p className="text-[11px] text-muted-foreground">
            {draft.threshold === null
              ? "No threshold. Showing every union."
              : `Only where ${triggerMetric?.label ?? "value"} is ${operatorLabel} ${draft.threshold}${
                  triggerMetric?.unit ? ` ${triggerMetric.unit}` : ""
                }.`}
          </p>
        </div>
      </div>

      {/* Pinned — always reachable */}
      <footer className="shrink-0 border-t border-border bg-card px-5 py-3">
        {dirty && <p className="mb-2 text-[11px] text-amber-900">Not applied yet.</p>}
        <div className="flex gap-2">
          <Button onClick={onApply} disabled={!dirty} className="flex-1">
            Apply
          </Button>
          <Button variant="secondary" onClick={onClear}>
            <RotateCcw />
            Clear
          </Button>
        </div>
      </footer>
    </aside>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}
