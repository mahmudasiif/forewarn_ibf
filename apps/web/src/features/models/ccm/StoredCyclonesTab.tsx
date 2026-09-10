import { useEffect, useMemo, useState } from "react";
import { Download, Map as MapIcon, Table2 } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { StatTile } from "@/components/shared/StatTile";
import {
  DEFAULT_FILTERS,
  resultsCsvUrl,
  useCyclone,
  useCyclones,
  useMapData,
  useMetrics,
  useResults,
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
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);

  // Start on the most recent cyclone once the list arrives.
  useEffect(() => {
    if (applied || !cyclones.data?.length) return;
    const initial: CCMFilters = { ...DEFAULT_FILTERS, cyclone: cyclones.data[0].code };
    setApplied(initial);
    setDraft(initial);
  }, [cyclones.data, applied]);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(applied),
    [draft, applied],
  );

  const detail = useCyclone(applied?.cyclone ?? null);
  const results = useResults(applied ?? ({} as CCMFilters), page);
  const mapData = useMapData(applied ?? ({} as CCMFilters), Boolean(applied));

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

  const totals = detail.data?.totals ?? {};

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
    <div className="grid gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
      <div className="xl:sticky xl:top-6 xl:self-start">
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

      <div className="min-w-0 space-y-6">
        {/* Headline totals for the whole cyclone, not the filtered subset */}
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="People affected"
            value={formatValue(totals.affected_people)}
            context={`${detail.data?.union_count.toLocaleString() ?? "—"} unions`}
          />
          <StatTile
            label="Max wind speed"
            value={formatValue(totals.max_wind_speed_kmh)}
            context="km/hr, highest union"
          />
          <StatTile
            label="Max surge height"
            value={formatValue(totals.max_surge_height_m)}
            context="metres, highest union"
          />
          <StatTile
            label="Unions at risk ≥ 50%"
            value={formatValue(totals.unions_risk_50_plus)}
            context="Risk 50% or above"
          />
        </section>

        {/* Map */}
        <Card
          title="Impact map"
          subtitle={
            mapData.data
              ? `${mapData.data.metric_label} by union${
                  applied.district ? ` — ${applied.district}` : ""
                }`
              : "Loading…"
          }
          bodyClassName="p-0"
          action={
            <div className="flex items-center gap-2">
              <MapIcon className="size-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Click a union for detail</span>
            </div>
          }
        >
          <div className="h-[520px] w-full">
            <CCMMap data={mapData.data} loading={mapData.isFetching} onSelect={setSelected} />
          </div>
        </Card>

        {/* Selected union */}
        {selected && (
          <Card
            title={`${selected.union_name ?? "Union"}`}
            subtitle={`${selected.upazila ?? ""}, ${selected.district ?? ""}, ${
              selected.division ?? ""
            }`}
            action={
              <Button variant="link" size="sm" onClick={() => setSelected(null)}>
                Close
              </Button>
            }
          >
            <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {[
                ["Risk", selected.risk_pct, "%"],
                ["Hazard", selected.hazard_pct, "%"],
                ["Vulnerability", selected.vulnerability_pct, "%"],
                ["Wind speed", selected.wind_speed_kmh, "km/hr"],
                ["Surge height", selected.surge_height_m, "m"],
                ["Affected people", selected.affected_people, ""],
              ].map(([label, value, unit]) => (
                <div key={label as string}>
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    {label as string}
                  </dt>
                  <dd className="mt-0.5 font-display text-xl font-bold tabular-nums text-foreground">
                    {formatValue(value as number, unit as string)}
                  </dd>
                </div>
              ))}
            </dl>
          </Card>
        )}

        {/* Table */}
        <Card
          title="Results"
          subtitle={`By ${applied.level}, ranked by ${
            metrics.data?.find((m) => m.key === applied.metric)?.label ?? "value"
          }`}
          bodyClassName="p-0"
          action={
            <Button variant="secondary" size="sm" asChild>
              <a href={resultsCsvUrl(applied)}>
                <Download />
                Export CSV
              </a>
            </Button>
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
            Results from CCM {detail.data?.model_version ?? "v2.9.3"}. A blank means the model
            gave no value — the Sundarbans ranges have no residents, so risk there is undefined,
            not zero.
          </span>
        </p>
      </div>
    </div>
  );
}
