import { DataTable, type Column } from "@/components/shared/DataTable";
import { cn } from "@/lib/utils";
import type { RunStatus, RunSummary } from "@/lib/preparednessApi";

const STATUS_STYLE: Record<RunStatus, string> = {
  succeeded: "bg-green-100 text-navy-900",
  running: "bg-cyan-100 text-navy-900",
  queued: "bg-navy-50 text-navy-700",
  failed: "bg-sunrise-100 text-navy-900",
};

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function RunList({
  runs,
  selectedId,
  onSelect,
}: {
  runs: RunSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const columns: Column<RunSummary>[] = [
    {
      key: "cyclone_name",
      header: "Cyclone",
      render: (r) => (
        <span className={cn("font-medium", r.id === selectedId && "text-green-700")}>
          {r.cyclone_name}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (r) => (
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
            STATUS_STYLE[r.status],
          )}
        >
          {r.status}
        </span>
      ),
    },
    { key: "damage_model", header: "Model", render: (r) => r.damage_model.toUpperCase() },
    {
      key: "guideline",
      header: "Guideline",
      render: (r) => (r.llm_polished ? "LLM-polished" : "Base"),
    },
    { key: "created_at", header: "Started", render: (r) => when(r.created_at) },
  ];

  return (
    <DataTable
      columns={columns}
      rows={runs}
      rowKey={(r) => String(r.id)}
      onRowClick={(r) => onSelect(r.id)}
      emptyMessage="No runs yet — queue one from the New Run tab."
    />
  );
}
