import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Download,
  Home,
  Map as MapIcon,
  RefreshCw,
  Users,
  X,
} from "lucide-react";

import { Card } from "@/components/shared/Card";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { PageHeader } from "@/components/shared/PageHeader";
import { SeverityBadge } from "@/components/shared/SeverityBadge";
import { StatTile } from "@/components/shared/StatTile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FilterBar } from "@/features/crisis/FilterBar";
import { HazardBreakdown } from "@/features/crisis/HazardBreakdown";
import { IncidentFeed } from "@/features/crisis/IncidentFeed";
import { IncidentMap } from "@/features/crisis/IncidentMap";
import { SeveritySplit } from "@/features/crisis/SeveritySplit";
import { INCIDENTS, LAST_COLLECTION, type Incident } from "@/features/crisis/mockIncidents";
import { formatCount, formatDateTime, timeAgo } from "@/features/crisis/severity";
import { useIncidentFilters } from "@/features/crisis/useIncidentFilters";

const STATUS_BADGE: Record<Incident["status"], { label: string; className: string }> = {
  pending: { label: "Awaiting review", className: "bg-amber-100 text-navy-900" },
  validated: { label: "Validated", className: "bg-green-100 text-navy-900" },
  rejected: { label: "Rejected", className: "bg-navy-50 text-navy-500" },
};

export default function CrisisDashboardPage() {
  const { filters, setFilters, filtered, districts, totals } = useIncidentFilters(INCIDENTS);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Newest first — the feed answers "what changed since I last looked".
  const byRecency = useMemo(
    () =>
      [...filtered].sort(
        (a, b) => new Date(b.reportedAt).getTime() - new Date(a.reportedAt).getTime(),
      ),
    [filtered],
  );

  const selected = filtered.find((i) => i.id === selectedId) ?? null;

  const columns: Column<Incident>[] = [
    {
      key: "incident",
      header: "Incident",
      render: (row) => (
        <div className="min-w-0">
          <p className="font-medium text-foreground">{row.title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {row.id} · {row.hazard} · {row.district}, {row.division}
          </p>
        </div>
      ),
    },
    {
      key: "severity",
      header: "Severity",
      render: (row) => <SeverityBadge level={row.severity} />,
    },
    {
      key: "reported",
      header: "Reported",
      render: (row) => (
        <div className="whitespace-nowrap">
          <p className="text-sm">{timeAgo(row.reportedAt)}</p>
          <p className="text-[11px] text-muted-foreground">{formatDateTime(row.reportedAt)}</p>
        </div>
      ),
    },
    {
      key: "casualties",
      header: "Dead / Inj / Miss",
      numeric: true,
      render: (row) => (
        <span className="whitespace-nowrap tabular-nums">
          <span className={row.deaths > 0 ? "font-medium text-sunrise-900" : "text-muted-foreground"}>
            {formatCount(row.deaths)}
          </span>
          <span className="mx-1 text-navy-200">/</span>
          <span className="text-navy-700">{formatCount(row.injured)}</span>
          <span className="mx-1 text-navy-200">/</span>
          <span className="text-navy-700">{formatCount(row.missing)}</span>
        </span>
      ),
    },
    {
      key: "affected",
      header: "Affected",
      numeric: true,
      render: (row) => <span className="tabular-nums">{formatCount(row.affected)}</span>,
    },
    {
      key: "source",
      header: "Source",
      render: (row) => <span className="text-xs text-navy-700">{row.source}</span>,
    },
    {
      key: "status",
      header: "Validation",
      render: (row) => (
        <span
          className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-medium ${STATUS_BADGE[row.status].className}`}
        >
          {STATUS_BADGE[row.status].label}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      numeric: true,
      render: (row) =>
        row.status === "pending" ? (
          <div className="flex justify-end gap-1">
            <button
              type="button"
              className="rounded-lg p-1.5 text-green-700 hover:bg-green-100"
              aria-label={`Validate ${row.title}`}
            >
              <Check className="size-4" />
            </button>
            <button
              type="button"
              className="rounded-lg p-1.5 text-muted-foreground hover:bg-navy-50"
              aria-label={`Reject ${row.title}`}
            >
              <X className="size-4" />
            </button>
          </div>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader
        title="Crisis Dashboard"
        module="Module 6"
        description="A live picture of unfolding crises, assembled from automated collection twice daily and validated by Hub administrators before it informs decisions."
        meta={
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="inline-flex items-center gap-2 text-xs text-navy-700">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-green-500 opacity-60" />
                <span className="relative inline-flex size-2 rounded-full bg-green-700" />
              </span>
              Collector last ran {timeAgo(LAST_COLLECTION)}
            </span>
            {totals.pending > 0 && (
              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-900">
                <AlertTriangle className="size-3.5" />
                {totals.pending} awaiting validation
              </span>
            )}
          </div>
        }
        actions={
          <>
            <Button variant="secondary" size="sm">
              <RefreshCw />
              Refresh
            </Button>
            <Button variant="secondary" size="sm">
              <Download />
              Export CSV
            </Button>
          </>
        }
      />

      <div className="space-y-6 p-6">
        {/* Headline counts. These describe the *filtered* set, so narrowing to
            a district re-reads every tile for that district. */}
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <StatTile label="Incidents" value={totals.incidents} context="Matching current filters" />
          <StatTile
            label="Deaths"
            value={totals.deaths}
            valueClassName={totals.deaths > 0 ? "text-sunrise-900" : undefined}
            context={`${totals.injured} injured · ${totals.missing} missing`}
          />
          <StatTile
            label="People affected"
            value={totals.affected.toLocaleString()}
            context={`${totals.displaced.toLocaleString()} displaced`}
            icon={<Users className="size-4" />}
          />
          <StatTile
            label="Houses damaged"
            value={totals.housesDamaged.toLocaleString()}
            context="Reported, not yet assessed"
            icon={<Home className="size-4" />}
          />
          <StatTile
            label="Districts affected"
            value={totals.districts}
            context="Distinct districts in view"
            icon={<MapIcon className="size-4" />}
          />
          <StatTile
            label="Awaiting validation"
            value={totals.pending}
            context="Needs Admin review"
            valueClassName={totals.pending > 0 ? "text-amber-900" : undefined}
          />
        </section>

        {/* Filters apply to everything below — map, feed, charts and table. */}
        <Card bodyClassName="p-0">
          <FilterBar
            filters={filters}
            onChange={setFilters}
            districts={districts}
            resultCount={filtered.length}
            totalCount={INCIDENTS.length}
          />
        </Card>

        {/* Map and feed read together: the map answers "where", the feed
            answers "what just happened", and selecting in one marks the other. */}
        <section className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <Card
            title="Incident map"
            subtitle="Positioned by report location, sized and coloured by severity"
            bodyClassName="p-0"
            action={
              <span className="text-xs text-muted-foreground">Click a marker for detail</span>
            }
          >
            <div className="h-[520px] w-full">
              <IncidentMap
                incidents={filtered}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            </div>
          </Card>

          <Card
            title="Live feed"
            subtitle="Newest first"
            bodyClassName="p-0"
            action={<Badge variant="outline">{byRecency.length}</Badge>}
          >
            <IncidentFeed
              incidents={byRecency}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </Card>
        </section>

        {/* The selected incident, shown only when one is picked — the detail
            an operator needs before validating or dismissing a report. */}
        {selected && (
          <Card
            title={selected.title}
            subtitle={`${selected.id} · ${selected.district}, ${selected.division} · ${formatDateTime(selected.reportedAt)}`}
            action={
              <Button variant="link" size="sm" onClick={() => setSelectedId(null)}>
                Close
              </Button>
            }
          >
            <p className="max-w-3xl text-sm leading-relaxed text-navy-700">{selected.summary}</p>

            <dl className="mt-5 grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
              {[
                ["Hazard", selected.hazard],
                ["Deaths", formatCount(selected.deaths)],
                ["Injured", formatCount(selected.injured)],
                ["Missing", formatCount(selected.missing)],
                ["Affected", formatCount(selected.affected)],
                ["Displaced", formatCount(selected.displaced)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    {label}
                  </dt>
                  <dd className="mt-0.5 font-display text-xl font-bold tabular-nums text-foreground">
                    {value}
                  </dd>
                </div>
              ))}
            </dl>

            <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-border pt-4">
              <SeverityBadge level={selected.severity} />
              <span
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${STATUS_BADGE[selected.status].className}`}
              >
                {STATUS_BADGE[selected.status].label}
              </span>
              <span className="text-xs text-muted-foreground">{selected.source}</span>

              {selected.status === "pending" && (
                <div className="ml-auto flex gap-2">
                  <Button size="sm" variant="secondary">
                    <X />
                    Reject
                  </Button>
                  <Button size="sm">
                    <Check />
                    Validate
                  </Button>
                </div>
              )}
            </div>
          </Card>
        )}

        <section className="grid gap-6 lg:grid-cols-2">
          <Card title="By hazard type" subtitle="Incidents in the current view, ranked">
            <HazardBreakdown incidents={filtered} />
          </Card>
          <Card title="Severity split" subtitle="How the current view distributes">
            <SeveritySplit incidents={filtered} />
          </Card>
        </section>

        <Card
          title="All incidents"
          subtitle="Validate a report before it informs the operational picture"
          bodyClassName="p-0"
        >
          <DataTable
            columns={columns}
            rows={byRecency}
            rowKey={(row) => row.id}
            onRowClick={(row) => setSelectedId(row.id)}
            emptyMessage="No incidents match the current filters."
          />
        </Card>

        <p className="text-caption">
          Demonstration data — the collection pipeline is not yet connected, and the validate and
          reject actions are not wired up.
        </p>
      </div>
    </>
  );
}
