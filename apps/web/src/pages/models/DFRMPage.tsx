import { PageHeader } from "@/components/shared/PageHeader";
import { StatusDot } from "@/components/shared/StatusDot";
import { ForecastTab } from "@/features/models/dfrm/ForecastTab";
import { useAreas } from "@/lib/dfrmApi";

export default function DFRMPage() {
  const areas = useAreas();
  const ready = Boolean(areas.data);

  return (
    <>
      <PageHeader
        title="Dynamic Flood Risk Model (DFRM)"
        module="Module 7"
        description="Automated 5-day Jamuna basin flood forecast (Jamalpur & Kurigram), driven by the FFWC Bahadurabad water level — inundation, hazard, risk and vulnerability per forecast day."
        meta={
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">DFRM v5.2</span>
            <StatusDot status={areas.isError ? "offline" : ready ? "healthy" : "unknown"} />
            <span>{ready ? "Ready" : areas.isError ? "Service offline" : "Loading…"}</span>
            <span>FFWC-driven · daily</span>
            <span>IWFM / BUET</span>
          </div>
        }
      />

      <div className="p-6">
        <ForecastTab />
      </div>
    </>
  );
}
