import { useState } from "react";
import { FileText } from "lucide-react";

import { PageHeader } from "@/components/shared/PageHeader";
import { StatusDot } from "@/components/shared/StatusDot";
import { Card } from "@/components/shared/Card";
import { ControlPanel, type SubmitMeta } from "@/features/models/dfrm/ControlPanel";
import { DFRMMap } from "@/features/models/dfrm/DFRMMap";
import { RecentRuns } from "@/features/models/dfrm/RecentRuns";
import { WarningCard } from "@/features/models/dfrm/WarningCard";
import {
  useAreas,
  useDfrmRuns,
  useMapLayer,
  useWarning,
  type MapRequest,
  type WarningRequest,
} from "@/lib/dfrmApi";

export default function DFRMPage() {
  const areas = useAreas();
  const mapMutation = useMapLayer();
  const warnMutation = useWarning();
  const [mode, setMode] = useState<"map" | "warning" | null>(null);
  const [warnReq, setWarnReq] = useState<WarningRequest | null>(null);

  const onSubmit = (meta: SubmitMeta) => {
    if (meta.layer === "Warning") {
      const req: WarningRequest = {
        level: meta.level,
        area_id: meta.area_id,
        water_level: meta.water_level,
        wl_kind: meta.wl_kind,
        limb: meta.limb,
        date: meta.date,
      };
      setWarnReq(req);
      setMode("warning");
      warnMutation.reset();
      warnMutation.mutate(req);
    } else {
      const req: MapRequest = {
        level: meta.level,
        area_id: meta.area_id,
        layer: meta.layer,
        water_level: meta.water_level,
        wl_kind: meta.wl_kind,
        limb: meta.limb,
      };
      setMode("map");
      mapMutation.reset();
      mapMutation.mutate(req);
    }
  };

  const runs = useDfrmRuns(20);
  const runCount = runs.data?.length ?? 0;
  const ready = Boolean(areas.data);
  const pending = mapMutation.isPending || warnMutation.isPending;
  const error = mapMutation.error || warnMutation.error;

  return (
    <>
      <PageHeader
        title="Dynamic Flood Risk Model (DFRM)"
        module="Module 7"
        description="Jamuna basin flood risk (Jamalpur & Kurigram) from a forecast water level — inundation, hazard, risk, vulnerability and warnings."
        meta={
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">DFRM v5.2</span>
            <StatusDot status={areas.isError ? "offline" : ready ? "healthy" : "unknown"} />
            <span>{ready ? "Ready" : areas.isError ? "Service offline" : "Loading…"}</span>
            <span>{runCount > 0 ? `${runCount}${runs.data && runCount >= 20 ? "+" : ""} recent quer${runCount === 1 ? "y" : "ies"}` : "No queries yet"}</span>
            <span>IWFM / BUET</span>
          </div>
        }
      />

      <div className="grid gap-6 p-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="space-y-6 lg:sticky lg:top-6 lg:self-start">
          {areas.data ? (
            <ControlPanel
              tree={areas.data}
              onSubmit={onSubmit}
              onClear={() => {
                setMode(null);
                mapMutation.reset();
                warnMutation.reset();
              }}
              pending={pending}
            />
          ) : (
            <Card>
              <div className="py-10 text-center text-sm text-muted-foreground">
                {areas.isError ? "Could not reach the DFRM service." : "Loading areas…"}
              </div>
            </Card>
          )}
          <RecentRuns />
        </div>

        <div className="min-w-0 space-y-6">
          {error && (
            <Card>
              <p className="text-sm text-sunrise-900">
                {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
                  "The query failed. Check the water level and try again."}
              </p>
            </Card>
          )}

          {mode === "map" && (mapMutation.data || mapMutation.isPending) && (
            <Card
              title={mapMutation.data ? `${mapMutation.data.area_name} — ${mapMutation.data.layer}` : "Flood map"}
              subtitle={
                mapMutation.data
                  ? `${mapMutation.data.station} · water level ${mapMutation.data.water_level.toFixed(2)} m` +
                    (mapMutation.data.return_period != null && mapMutation.data.return_period >= 2
                      ? ` · return period ${mapMutation.data.return_period} yr`
                      : "")
                  : undefined
              }
              bodyClassName="p-0"
            >
              <div className="h-[600px] w-full overflow-hidden rounded-b-card bg-muted">
                <DFRMMap data={mapMutation.data} loading={mapMutation.isPending} />
              </div>
            </Card>
          )}

          {mode === "warning" && warnMutation.data && warnReq && (
            <WarningCard data={warnMutation.data} request={warnReq} />
          )}

          {mode === null && (
            <Card>
              <div className="flex flex-col items-center gap-2 py-20 text-center">
                <FileText className="size-6 text-muted-foreground" />
                <p className="max-w-sm text-sm text-navy-700">
                  Choose a layer, an area and a forecast water level, then run the query to see the
                  flood map or warning table.
                </p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
