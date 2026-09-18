import { Download } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { StatTile } from "@/components/shared/StatTile";
import { Button } from "@/components/ui/button";
import { warningCsvUrl, type WarningRequest, type WarningResponse, type WarningRow } from "@/lib/dfrmApi";

const RISK_COLORS: Record<number, string> = {
  1: "#00A385",
  2: "#FD9A00",
  3: "#C67C00",
  4: "#FF603A",
  5: "#B93940",
};

function riskColor(level: string | number): string {
  const n = typeof level === "number" ? level : Number(level);
  return Number.isFinite(n) ? RISK_COLORS[n] ?? "#DDDDE2" : "#DDDDE2";
}

function columnsFor(level: string): (keyof WarningRow)[] {
  const geo: (keyof WarningRow)[] =
    level === "District"
      ? ["Division", "District"]
      : level === "Upazilla"
        ? ["Division", "District", "Upazilla"]
        : level === "Union"
          ? ["District", "Upazilla", "Union"]
          : ["Upazilla", "Union", "Village"];
  return [...geo, "Risk Level", "Water Depth", "Flood Duration", "Water Speed", "Damage"];
}

export function WarningCard({ data, request }: { data: WarningResponse; request: WarningRequest }) {
  const s = data.selected;
  const noRisk = s["Risk Level"] === "No Risk";
  const columns = columnsFor(data.level);

  return (
    <div className="space-y-6">
      <Card
        title={`${data.area_name} — flood warning`}
        subtitle={`${data.station} · hydrograph ${data.day}${data.date ? ` · ${data.date}` : ""}`}
        action={
          <Button asChild variant="secondary" size="sm">
            <a href={warningCsvUrl(request)} download>
              <Download />
              CSV
            </a>
          </Button>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile label="Water level" value={`${data.water_level.toFixed(2)} m`} context={`danger ${data.danger_level} m`} />
          <StatTile
            label="Return period"
            value={data.return_period != null && data.return_period >= 2 ? `${data.return_period}` : "—"}
            context="years"
          />
          <StatTile label="Flood condition" value={data.limb} />
          <StatTile
            label="Risk level"
            value={noRisk ? "No Risk" : String(s["Risk Level"])}
            context={noRisk ? "" : `${s.Damage} damage`}
          />
        </div>

        {!noRisk && (
          <div className="mt-4 grid gap-3 rounded-card border border-border bg-muted/40 p-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Water depth" value={s["Water Depth"]} />
            <Field label="Flood duration" value={s["Flood Duration"]} />
            <Field label="Water speed" value={String(s["Water Speed"])} />
            <Field label="Damage" value={String(s.Damage)} />
          </div>
        )}
      </Card>

      <Card title="All areas" subtitle={`${data.rows.length.toLocaleString()} rows`} bodyClassName="p-0">
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                {columns.map((c) => (
                  <th key={String(c)} className="border-b border-border px-3 py-2 font-medium">
                    {String(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row._id} className="border-b border-border/60 hover:bg-muted/40">
                  {columns.map((c) => (
                    <td key={String(c)} className="px-3 py-1.5 text-navy-800">
                      {c === "Risk Level" ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className="size-2.5 rounded-full" style={{ background: riskColor(row["Risk Level"]) }} />
                          {String(row["Risk Level"])}
                        </span>
                      ) : (
                        String(row[c] ?? "")
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-foreground">{value || "—"}</p>
    </div>
  );
}
