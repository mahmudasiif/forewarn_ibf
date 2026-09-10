import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusDot } from "@/components/shared/StatusDot";
import { MODELS, MODEL_RUNS, type ModelRun } from "@/lib/mock";
import { cn } from "@/lib/utils";

const runColumns: Column<ModelRun>[] = [
  { key: "id", header: "Run", render: (row) => <span className="font-mono text-xs">{row.id}</span> },
  { key: "model", header: "Model", render: (row) => row.model },
  { key: "trigger", header: "Trigger", render: (row) => <span className="capitalize">{row.trigger}</span> },
  {
    key: "status",
    header: "Status",
    render: (row) => {
      const map: Record<ModelRun["status"], string> = {
        succeeded: "bg-green-100 text-navy-900",
        running: "bg-cyan-100 text-navy-900",
        queued: "bg-navy-50 text-navy-700",
        failed: "bg-sunrise-100 text-navy-900",
      };
      return (
        <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium capitalize", map[row.status])}>
          {row.status}
        </span>
      );
    },
  },
  { key: "startedAt", header: "Started", render: (row) => row.startedAt },
  { key: "duration", header: "Duration", numeric: true, render: (row) => row.duration },
];

export default function ModelsPage() {
  return (
    <>
      <PageHeader
        title="Models"
        description="Every predictive model registered with the portal. Each runs as its own service, so a model can be updated or replaced without changing the portal itself."
      />

      <div className="space-y-6 p-6">
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {MODELS.map((model) => (
            <Link
              key={model.id}
              to={model.to}
              className="group rounded-card border border-navy-200 bg-white p-5 transition-colors hover:border-green-700"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-navy-500">
                    {model.module}
                  </p>
                  <h2 className="font-display mt-1 text-lg font-semibold leading-tight text-navy-900">
                    {model.shortName}
                  </h2>
                </div>
                <StatusDot status={model.status} />
              </div>

              <p className="mt-3 text-sm leading-relaxed text-navy-700">{model.description}</p>

              <dl className="mt-4 space-y-1.5 border-t border-navy-200 pt-3 text-xs">
                <div className="flex justify-between gap-2">
                  <dt className="text-navy-500">Version</dt>
                  <dd className="font-medium text-navy-900">{model.version}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-navy-500">Last run</dt>
                  <dd className="tabular-nums text-navy-900">{model.lastRun}</dd>
                </div>
              </dl>

              <p className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-green-700">
                {model.live ? "Open live model" : "View module"}
                <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
              </p>
            </Link>
          ))}
        </section>

        <Card
          title="Recent runs"
          subtitle="Across all registered models"
          bodyClassName="p-0"
        >
          <DataTable columns={runColumns} rows={MODEL_RUNS} rowKey={(row) => row.id} />
        </Card>
      </div>
    </>
  );
}
