import { ChevronLeft, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { formatValue } from "./colorScale";
import type { AdminLevel, Metric, ResultPage } from "@/lib/ccmApi";

const COLUMN_ORDER = [
  "risk_pct",
  "hazard_pct",
  "vulnerability_pct",
  "surge_height_m",
  "wind_speed_kmh",
  "rainfall_72h_mm",
  "flooded_area_km2",
  "affected_people",
  "affected_houses",
  "house_damage_million_bdt",
];

const CONDITIONS = [
  { key: "polder_damage", label: "Polder" },
  { key: "structure_damage", label: "Structure" },
  { key: "agri_land_damage", label: "Agri. land" },
];

function locationColumns(level: AdminLevel): { key: string; label: string }[] {
  switch (level) {
    case "division":
      return [{ key: "division", label: "Division" }];
    case "district":
      return [
        { key: "district", label: "District" },
        { key: "division", label: "Division" },
      ];
    case "upazila":
      return [
        { key: "upazila", label: "Upazila" },
        { key: "district", label: "District" },
      ];
    default:
      return [
        { key: "union_name", label: "Union" },
        { key: "upazila", label: "Upazila" },
        { key: "district", label: "District" },
      ];
  }
}

/** 'Yes' is the only damage. 'No polder in the area' means there is no polder. */
function ConditionCell({ value }: { value: string | null }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  if (value === "Yes") return <Badge variant="severity-severe">Yes</Badge>;
  if (value === "No") return <span className="text-navy-700">No</span>;
  return (
    <span className="text-muted-foreground" title={value}>
      No polder
    </span>
  );
}

type ResultsTableProps = {
  data: ResultPage | undefined;
  metrics: Metric[];
  loading: boolean;
  page: number;
  onPageChange: (page: number) => void;
};

export function ResultsTable({ data, metrics, loading, page, onPageChange }: ResultsTableProps) {
  if (loading && !data) {
    return <div className="px-6 py-12 text-center text-sm text-muted-foreground">Loading…</div>;
  }
  if (!data || data.items.length === 0) {
    return (
      <div className="px-6 py-12 text-center">
        <p className="text-sm font-medium">Nothing matches</p>
        <p className="mt-1 text-xs text-muted-foreground">Try a lower threshold.</p>
      </div>
    );
  }

  const locCols = locationColumns(data.level);
  const metricByKey = new Map(metrics.map((m) => [m.key, m]));
  const valueCols = COLUMN_ORDER.filter((key) => metricByKey.has(key));
  const totalPages = Math.max(1, Math.ceil(data.total / data.size));

  return (
    <div>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {locCols.map((col) => (
              <TableHead key={col.key}>{col.label}</TableHead>
            ))}
            {valueCols.map((key) => {
              const metric = metricByKey.get(key)!;
              return (
                <TableHead
                  key={key}
                  numeric
                  className={cn(key === data.metric && "text-foreground")}
                >
                  {metric.label}
                  {metric.unit ? (
                    <span className="block font-normal normal-case tracking-normal">
                      {metric.unit}
                    </span>
                  ) : null}
                </TableHead>
              );
            })}
            {CONDITIONS.map((condition) => (
              <TableHead key={condition.key}>{condition.label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.items.map((row, index) => (
            <TableRow key={`${row.union_geo ?? ""}-${index}`}>
              {locCols.map((col) => (
                <TableCell key={col.key}>{(row[col.key] as string) ?? "—"}</TableCell>
              ))}
              {valueCols.map((key) => (
                <TableCell
                  key={key}
                  numeric
                  className={cn(key === data.metric ? "font-medium" : "text-navy-700")}
                >
                  {formatValue(row[key] as number)}
                </TableCell>
              ))}
              {CONDITIONS.map((condition) => (
                <TableCell key={condition.key}>
                  <ConditionCell value={(row[condition.key] as string) ?? null} />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
        <p className="text-xs text-muted-foreground">
          {data.total.toLocaleString()} rows · page {page} of {totalPages}
          {loading && <span className="ml-2 text-navy-700">updating…</span>}
        </p>
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
          >
            <ChevronLeft />
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
          >
            Next
            <ChevronRight />
          </Button>
        </div>
      </div>
    </div>
  );
}
