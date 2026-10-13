import { ForecastTab } from "@/features/models/dfrm/ForecastTab";
import { usePageHeading } from "@/lib/pageHeading";

export default function DFRMPage() {
  // Map screen: the title line lives in the top bar, so the forecast map keeps
  // the height a page header would have taken. Same treatment as CCM.
  usePageHeading("DFRM — Dynamic Flood Risk Model (IWFM / BUET)", "Module 7");

  return (
    <div className="p-3">
      <ForecastTab />
    </div>
  );
}
