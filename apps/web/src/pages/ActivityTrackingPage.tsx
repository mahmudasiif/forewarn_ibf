import { Download, Filter } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatTile } from "@/components/shared/StatTile";
import { ACTIVITIES, type Activity } from "@/lib/mock";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<Activity["status"], { label: string; className: string }> = {
  planned: { label: "Planned", className: "bg-navy-50 text-navy-700" },
  in_progress: { label: "In progress", className: "bg-cyan-100 text-navy-900" },
  completed: { label: "Completed", className: "bg-green-100 text-navy-900" },
};

const columns: Column<Activity>[] = [
  {
    key: "name",
    header: "Activity",
    render: (row) => (
      <div>
        <p className="font-medium text-navy-900">{row.name}</p>
        <p className="text-xs text-navy-500">
          {row.type} · {row.sector}
        </p>
      </div>
    ),
  },
  { key: "district", header: "District", render: (row) => row.district },
  { key: "members", header: "Members", numeric: true, render: (row) => row.members },
  {
    key: "status",
    header: "Status",
    render: (row) => (
      <span
        className={cn(
          "rounded-full px-2.5 py-0.5 text-xs font-medium",
          STATUS_STYLES[row.status].className,
        )}
      >
        {STATUS_STYLES[row.status].label}
      </span>
    ),
  },
];

export default function ActivityTrackingPage() {
  const counts = {
    planned: ACTIVITIES.filter((a) => a.status === "planned").length,
    inProgress: ACTIVITIES.filter((a) => a.status === "in_progress").length,
    completed: ACTIVITIES.filter((a) => a.status === "completed").length,
  };

  return (
    <>
      <PageHeader
        title="Activity Tracking"
        module="Module 8"
        description="Start Ready and Start Fund activity across early action, response and national reserve readiness — tracked by status, sector and geography."
        actions={
          <>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-lg border border-navy-200 px-3 py-2 text-sm font-medium text-green-700 hover:bg-navy-50"
            >
              <Filter className="size-4" />
              Filters
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-lg bg-navy-900 px-3 py-2 text-sm font-medium text-white hover:bg-navy-700"
            >
              <Download className="size-4" />
              Export
            </button>
          </>
        }
      />

      <div className="space-y-6 p-6">
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile label="Total activities" value={ACTIVITIES.length} context="Across all members this season" />
          <StatTile label="Planned" value={counts.planned} context="Not yet started" />
          <StatTile label="In progress" value={counts.inProgress} context="Currently being delivered" />
          <StatTile label="Completed" value={counts.completed} context="Delivered and reported" />
        </section>

        <Card
          title="Activity repository"
          subtitle="Filterable by year, type, sector and geography"
          bodyClassName="p-0"
        >
          <DataTable columns={columns} rows={ACTIVITIES} rowKey={(row) => row.id} />
        </Card>

        <p className="text-caption">
          Demonstration data — the data pipeline and formats are built in consultation with Start
          Fund Bangladesh and the Start Ready team.
        </p>
      </div>
    </>
  );
}
