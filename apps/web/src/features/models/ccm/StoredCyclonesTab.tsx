import { useEffect, useMemo, useState } from "react";
import { Table2, X } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { DownloadMenu } from "@/components/shared/DownloadMenu";
import {
  DEFAULT_FILTERS,
  resultsDownloadUrl,
  useBoundaries,
  useCyclone,
  useCyclones,
  useMapData,
  useMetrics,
  useResults,
  useTrack,
  type AdminLevel,
  type CCMFilters,
} from "@/lib/ccmApi";
import { CCMMap } from "./CCMMap";
import { FilterPanel } from "./FilterPanel";
import { ResultsTable } from "./ResultsTable";
import { formatValue } from "./colorScale";

export function StoredCyclonesTab() {
  const cyclones = useCyclones();
  const metrics = useMetrics();

  const [applied, setApplied] = useState<CCMFilters | null>(null);
  const [draft, setDraft] = useState<CCMFilters | null>(null);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(
    null,
  );

  // Start on the most recent cyclone once the list arrives.
  useEffect(() => {
    if (applied || !cyclones.data?.length) return;
    const initial: CCMFilters = {
      ...DEFAULT_FILTERS,
      cyclone: cyclones.data[0].code,
    };
    setApplied(initial);
    setDraft(initial);
  }, [cyclones.data, applied]);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(applied),
    [draft, applied],
  );

  const detail = useCyclone(applied?.cyclone ?? null);
  const track = useTrack(applied?.cyclone ?? null);
  const results = useResults(applied ?? ({} as CCMFilters), page);
  const mapData = useMapData(applied ?? ({} as CCMFilters), Boolean(applied));
  // Outlines to separate the administrative areas on the map. Divisions are
  // only drawn while looking at more than one — once a division is picked its
  // outline is just the edge of the data, which the district lines already show.
  //
  // An outline is only worth drawing when it is *above* the level being
  // filled. At district level the fill already ends at each district edge, so
  // a district outline is a line drawn on top of itself; at division level a
  // district outline is worse than redundant — it puts borders inside an area
  // whose single number is the one on screen, and invites reading a figure off
  // a piece of it. So each outline switches off once the fill has reached it.
  const level = applied?.level;
  const showDistrictLines = level === "union" || level === "upazila";
  // Division lines go once the fill is divisions, and also once a single
  // division is picked — then the outline is just the edge of the data.
  const showDivisionLines = level !== "division" && !applied?.division;

  const districtLines = useBoundaries(
    applied ?? ({} as CCMFilters),
    "district",
    Boolean(applied) && showDistrictLines,
  );
  const divisionLines = useBoundaries(
    applied ?? ({} as CCMFilters),
    "division",
    Boolean(applied) && showDivisionLines,
  );

  if (cyclones.isLoading || metrics.isLoading || !applied || !draft) {
    return (
      <div className="rounded-card border border-border bg-card px-6 py-16 text-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (cyclones.isError) {
    return (
      <div className="rounded-card border border-border bg-card px-6 py-12 text-center">
        <p className="text-sm font-medium">Can't reach the data</p>
        <p className="mx-auto mt-1 max-w-sm text-xs text-muted-foreground">
          The API didn't respond. Check the backend is running.
        </p>
      </div>
    );
  }

  if (!cyclones.data?.length) {
    return (
      <div className="rounded-card border border-border bg-card px-6 py-12 text-center">
        <p className="text-sm font-medium">No cyclones loaded</p>
        <p className="mx-auto mt-1 max-w-sm text-xs text-muted-foreground">
          Run the importer, then reload.
        </p>
      </div>
    );
  }

  const apply = () => {
    setApplied(draft);
    setPage(1);
    setSelected(null);
  };

  const clear = () => {
    const reset: CCMFilters = { ...DEFAULT_FILTERS, cyclone: draft.cyclone };
    setDraft(reset);
    setApplied(reset);
    setPage(1);
    setSelected(null);
  };

  return (
    // 260px of controls, the rest map. The panel was 300px and the gaps 24px;
    // both come down so the choropleth gets the width back — on this screen the
    // map is the document and the panel is the margin.
    <div className="grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)]">
      <div className="xl:sticky xl:top-3 xl:self-start">
        <FilterPanel
          draft={draft}
          onChange={setDraft}
          onApply={apply}
          onClear={clear}
          cyclones={cyclones.data}
          metrics={metrics.data ?? []}
          dirty={dirty}
        />
      </div>

      <div className="min-w-0 space-y-3">
        {/* Map. No card header: the panel beside it already names the cyclone
            and the metric, and the legend in the corner repeats the metric —
            a title bar here only pushed the map down. */}
        <div className="relative h-[calc(100vh-14rem)] min-h-[460px] w-full overflow-hidden rounded-card border border-border bg-card">
          <CCMMap
            data={mapData.data}
            loading={mapData.isFetching}
            onSelect={setSelected}
            districts={showDistrictLines ? districtLines.data : undefined}
            divisions={showDivisionLines ? divisionLines.data : undefined}
            track={track.data}
            cycloneCode={applied.cyclone}
          />
        </div>

        {/* Selected area — one line of figures, not a card of tiles. It opens
            between the map and the table, so it has to cost as little vertical
            space as it can while still being readable.

            "Area", not "union": at district level the thing clicked is a
            district, and its figures are the district's. The parent trail
            below the name drops whatever the level has already swallowed. */}
        {selected && (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-card border border-border bg-card px-3.5 py-2.5">
            <div className="min-w-0">
              <p className="font-display text-sm font-semibold leading-tight text-foreground">
                {(selected.area_name as string) ??
                  (selected.union_name as string) ??
                  "Area"}
              </p>
              <p className="truncate text-[11px] leading-tight text-muted-foreground">
                {parentTrail(selected, applied.level)}
              </p>
            </div>

            <dl className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
              {(
                [
                  ["Risk", selected.risk_pct, "%"],
                  ["Hazard", selected.hazard_pct, "%"],
                  ["Vuln.", selected.vulnerability_pct, "%"],
                  ["Wind", selected.wind_speed_kmh, "km/hr"],
                  ["Surge", selected.surge_height_m, "m"],
                  ["Affected", selected.affected_people, ""],
                ] as const
              ).map(([label, value, unit]) => (
                <div key={label} className="flex items-baseline gap-1.5">
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    {label}
                  </dt>
                  <dd className="font-display text-base font-bold leading-none tabular-nums text-foreground">
                    {formatValue(value as number, unit)}
                  </dd>
                </div>
              ))}
            </dl>

            <Button
              variant="ghost"
              size="sm"
              className="ml-auto"
              onClick={() => setSelected(null)}
              aria-label="Close area detail"
            >
              <X />
            </Button>
          </div>
        )}

        {/* Table */}
        <Card
          title="Results"
          subtitle={`By ${applied.level}, ranked by ${
            metrics.data?.find((m) => m.key === applied.metric)?.label ??
            "value"
          }`}
          bodyClassName="p-0"
          action={
            <DownloadMenu
              options={[
                {
                  label: "CSV",
                  hint: "Every filtered row, for any tool",
                  href: resultsDownloadUrl(applied, "csv"),
                  filename: `CCM_${applied.cyclone}_${applied.level}.csv`,
                  icon: "csv",
                },
                {
                  label: "Excel (.xlsx)",
                  hint: "Formatted, with filters on the header",
                  href: resultsDownloadUrl(applied, "xlsx"),
                  filename: `CCM_${applied.cyclone}_${applied.level}.xlsx`,
                  icon: "xlsx",
                },
              ]}
            />
          }
        >
          <ResultsTable
            data={results.data}
            metrics={metrics.data ?? []}
            loading={results.isFetching}
            page={page}
            onPageChange={setPage}
          />
        </Card>

        <p className="flex items-start gap-2 text-caption">
          <Table2 className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Results from CCM {detail.data?.model_version ?? "v2.9.3"}. A blank
            means the model gave no value — the Sundarbans ranges have no
            residents, so risk there is undefined, not zero.
          </span>
        </p>
      </div>
    </div>
  );
}

/**
 * The administrative path above the selected area, outermost last.
 *
 * Only the levels that still sit above the one being shown: a selected
 * district needs "Barisal" after it, not "Barisal, Bagerhat" repeating its own
 * name, and a selected division needs nothing at all.
 */
function parentTrail(
  selected: Record<string, unknown>,
  level: AdminLevel,
): string {
  const parents: Record<AdminLevel, string[]> = {
    union: ["upazila", "district", "division"],
    upazila: ["district", "division"],
    district: ["division"],
    division: [],
  };
  return parents[level]
    .map((key) => selected[key])
    .filter(
      (value): value is string => typeof value === "string" && value !== "",
    )
    .join(", ");
}
