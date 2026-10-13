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
import { useCan } from "@/lib/permissions";
import {
  useLocations,
  RETURN_PERIOD_METRIC,
  type AdminLevel,
  type CCMFilters,
  type Cyclone,
  type Metric,
  type Operator,
  type ThresholdMode,
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

/**
 * Lead times the NEAP matrices are defined at. Anything between two of these
 * resolves down to the lower one, so offering the defined steps avoids the
 * surprise of typing 100 and getting the 72-hour row.
 */
const LEAD_TIMES: { value: number; label: string }[] = [
  { value: 0, label: "0 hr — no warning" },
  { value: 48, label: "48 hr — 2 days" },
  { value: 72, label: "72 hr — 3 days" },
  { value: 120, label: "120 hr — 5 days" },
  { value: 168, label: "168 hr — 7 days" },
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
 *
 * Deliberately narrow and tightly spaced: the map beside it is the thing being
 * read, and every pixel this panel gives back is map. The controls stay at
 * full tap size; it is the gaps between them that are small.
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

  // Deciding what counts as a trigger is an operational call, so it is gated.
  // Everyone passes today — see lib/permissions.ts.
  const canSetTrigger = useCan("ccm:set-trigger");

  const returnPeriod = draft.thresholdMode === "return_period";
  const triggerMetric = metrics.find((m) => m.key === draft.triggerMetric);
  const operatorLabel = OPERATORS.find(
    (o) => o.value === draft.operator,
  )?.label;

  /**
   * Switching to a return period forces the trigger onto affected people:
   * it is the only quantity the package carries per-union statistics for.
   */
  const setMode = (mode: ThresholdMode) =>
    onChange({
      ...draft,
      thresholdMode: mode,
      triggerMetric:
        mode === "return_period" ? RETURN_PERIOD_METRIC : draft.triggerMetric,
      threshold: null,
    });

  return (
    <aside className="flex flex-col overflow-hidden rounded-card border border-border bg-card xl:max-h-[calc(100vh-5rem)]">
      <header className="flex shrink-0 items-center gap-2 border-b border-border px-3.5 py-2.5">
        <SlidersHorizontal className="size-3.5 text-muted-foreground" />
        <h2 className="font-display text-sm font-semibold">Model inputs</h2>
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3.5 py-3">
        {/* Cyclone */}
        <div>
          <Label htmlFor="ccm-cyclone">Cyclone</Label>
          <Select
            value={draft.cyclone}
            onValueChange={(value) =>
              onChange({
                ...draft,
                cyclone: value,
                division: null,
                district: null,
                upazila: null,
              })
            }
          >
            <SelectTrigger id="ccm-cyclone" className="mt-1">
              <SelectValue placeholder="Choose a cyclone" />
            </SelectTrigger>
            <SelectContent>
              {cyclones.map((cyclone) => (
                <SelectItem key={cyclone.code} value={cyclone.code}>
                  {cyclone.name}
                  {cyclone.event_date
                    ? ` — ${formatDate(cyclone.event_date)}`
                    : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Level */}
        <div>
          <Label htmlFor="ccm-level">Select level</Label>
          <Select
            value={draft.level}
            onValueChange={(v) => set("level", v as AdminLevel)}
          >
            <SelectTrigger id="ccm-level" className="mt-1">
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
        <div className="space-y-2 rounded-lg border border-border bg-muted p-2.5">
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
              onChange({
                ...draft,
                district: value === ALL ? null : value,
                upazila: null,
              })
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
            onValueChange={(value) =>
              set("upazila", value === ALL ? null : value)
            }
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
            <SelectTrigger id="ccm-metric" className="mt-1">
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
          <p className="mt-1 text-[11px] text-muted-foreground">
            Colours the map.
          </p>
        </div>

        {/* Lead time — drives the NEAP impact numbers in the table */}
        <div>
          <Label htmlFor="ccm-lead-time">Lead time</Label>
          <Select
            value={String(draft.leadTimeHours)}
            onValueChange={(v) => set("leadTimeHours", Number(v))}
          >
            <SelectTrigger id="ccm-lead-time" className="mt-1">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LEAD_TIMES.map((option) => (
                <SelectItem key={option.value} value={String(option.value)}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
            Warning time before landfall. Sets the NEAP impact numbers — the
            same hazard scores lower the earlier it is known.
          </p>
        </div>

        {/* Trigger — role-gated */}
        {canSetTrigger && (
          <div className="space-y-2 rounded-lg border border-border bg-muted p-2.5">
            <Label htmlFor="ccm-trigger">Trigger parameter</Label>
            <Select
              value={draft.triggerMetric}
              onValueChange={(v) => set("triggerMetric", v)}
              disabled={returnPeriod}
            >
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

            <Select
              value={draft.thresholdMode}
              onValueChange={(v) => setMode(v as ThresholdMode)}
            >
              <SelectTrigger aria-label="Threshold type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="value">Fixed threshold</SelectItem>
                <SelectItem value="return_period">
                  Return period (years)
                </SelectItem>
              </SelectContent>
            </Select>

            <div className="flex gap-1.5">
              {returnPeriod ? (
                <span className="flex flex-1 items-center rounded-md border border-input bg-card px-3 text-sm text-muted-foreground">
                  exceeds the
                </span>
              ) : (
                <Select
                  value={draft.operator}
                  onValueChange={(v) => set("operator", v as Operator)}
                >
                  <SelectTrigger
                    aria-label="Threshold comparison"
                    className="flex-1"
                  >
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
              )}
              <Input
                aria-label={
                  returnPeriod ? "Return period in years" : "Threshold value"
                }
                type="number"
                inputMode="decimal"
                step="any"
                min={returnPeriod ? 2 : undefined}
                placeholder={returnPeriod ? "yrs" : "—"}
                className="w-20"
                value={draft.threshold ?? ""}
                onChange={(event) =>
                  set(
                    "threshold",
                    event.target.value === ""
                      ? null
                      : Number(event.target.value),
                  )
                }
              />
            </div>

            <p className="text-[11px] leading-snug text-muted-foreground">
              {describeTrigger(draft, triggerMetric, operatorLabel)}
            </p>
          </div>
        )}
      </div>

      {/* Pinned — always reachable */}
      <footer className="shrink-0 border-t border-border bg-card px-3.5 py-2.5">
        {dirty && (
          <p className="mb-1.5 text-[11px] text-amber-900">Not applied yet.</p>
        )}
        <div className="flex gap-2">
          <Button onClick={onApply} disabled={!dirty} className="flex-1">
            Apply
          </Button>
          <Button
            variant="secondary"
            onClick={onClear}
            aria-label="Clear filters"
          >
            <RotateCcw />
            Clear
          </Button>
        </div>
      </footer>
    </aside>
  );
}

/** Say in plain words what the current trigger will keep. */
function describeTrigger(
  draft: CCMFilters,
  triggerMetric: Metric | undefined,
  operatorLabel: string | undefined,
): string {
  if (draft.threshold === null) {
    return draft.thresholdMode === "return_period"
      ? "No return period set. Showing every union."
      : "No threshold. Showing every union.";
  }

  if (draft.thresholdMode === "return_period") {
    if (draft.threshold <= 1)
      return "A return period has to be more than 1 year.";
    return `Only unions where this cyclone affects more people than their own
      1-in-${draft.threshold}-year event. The bar is worked out per union, so a
      char and a mainland union are each judged against their own history.`;
  }

  return `Only where ${triggerMetric?.label ?? "value"} is ${operatorLabel} ${draft.threshold}${
    triggerMetric?.unit ? ` ${triggerMetric.unit}` : ""
  }.`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}
