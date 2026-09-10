import { Check, Clock, Filter, X } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatTile } from "@/components/shared/StatTile";
import { CRISIS_EVENTS, type CrisisEvent } from "@/lib/mock";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<CrisisEvent["status"], string> = {
  pending: "bg-amber-100 text-navy-900",
  validated: "bg-green-100 text-navy-900",
  rejected: "bg-navy-50 text-navy-500",
};

const columns: Column<CrisisEvent>[] = [
  {
    key: "title",
    header: "Reported event",
    render: (row) => (
      <div>
        <p className="font-medium text-navy-900">{row.title}</p>
        <p className="text-xs text-navy-500">
          {row.hazard} · {row.location}
        </p>
      </div>
    ),
  },
  { key: "reported", header: "Reported", render: (row) => row.reportedAt },
  { key: "source", header: "Source", render: (row) => row.source },
  {
    key: "status",
    header: "Validation",
    render: (row) => (
      <span
        className={cn(
          "rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
          STATUS_STYLES[row.status],
        )}
      >
        {row.status}
      </span>
    ),
  },
  {
    key: "actions",
    header: "",
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
            className="rounded-lg p-1.5 text-navy-500 hover:bg-navy-50"
            aria-label={`Reject ${row.title}`}
          >
            <X className="size-4" />
          </button>
        </div>
      ) : null,
    numeric: true,
  },
];

export default function CrisisDashboardPage() {
  const pending = CRISIS_EVENTS.filter((event) => event.status === "pending").length;

  return (
    <>
      <PageHeader
        title="Crisis Dashboard"
        module="Module 6"
        description="A live picture of unfolding crises, assembled from automated scraping twice daily and validated by Hub administrators before it informs decisions."
        meta={
          <span className="inline-flex items-center gap-1.5 text-xs text-navy-500">
            <Clock className="size-3.5" />
            Last collection run 09 Sep 2026, 06:00 (+06)
          </span>
        }
        actions={
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-lg border border-navy-200 px-3 py-2 text-sm font-medium text-green-700 hover:bg-navy-50"
          >
            <Filter className="size-4" />
            Filters
          </button>
        }
      />

      <div className="space-y-6 p-6">
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile label="Events (last 3 days)" value={CRISIS_EVENTS.length} context="Highlighted for alert visibility" />
          <StatTile label="Awaiting validation" value={pending} context="Requires Admin or Super Admin review" />
          <StatTile label="Districts affected" value={4} context="Distinct locations in current events" />
          <StatTile label="Collection runs today" value={2} context="Scheduled twice daily" />
        </section>

        <Card
          title="Geo-tagged crisis map"
          subtitle="Events plotted by location, coloured by hazard type"
        >
          <div className="flex aspect-[21/9] items-center justify-center rounded-lg border border-dashed border-navy-200 bg-navy-50">
            <p className="max-w-sm px-6 text-center text-sm text-navy-500">
              Map view renders here once the geo layer and boundary data are loaded. It will show
              each validated event on an interactive map with its descriptive attributes.
            </p>
          </div>
        </Card>

        <Card
          title="Reported events"
          subtitle="Validate an event before it appears on the public picture"
          bodyClassName="p-0"
        >
          <DataTable columns={columns} rows={CRISIS_EVENTS} rowKey={(row) => row.id} />
        </Card>

        <p className="text-caption">Demonstration data — the collection pipeline is not yet connected.</p>
      </div>
    </>
  );
}
