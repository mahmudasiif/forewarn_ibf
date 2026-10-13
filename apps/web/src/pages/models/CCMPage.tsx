import { Database, Radio } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RunNewCycloneTab } from "@/features/models/ccm/RunNewCycloneTab";
import { StoredCyclonesTab } from "@/features/models/ccm/StoredCyclonesTab";
import { usePageHeading } from "@/lib/pageHeading";

export default function CCMPage() {
  // This screen has no page header of its own: the map is what the page is
  // for, and a title block above it repeated what the sidebar, the input
  // panel and the map legend all already say. The one line worth keeping goes
  // into the top bar that was on screen anyway.
  usePageHeading("CCM — Cyclone Classifier Model (IWFM / BUET)", "Module 5");

  return (
    <div className="p-3">
      <Tabs defaultValue="past">
        <TabsList>
          <TabsTrigger value="past">
            <Database />
            Past Cyclones
          </TabsTrigger>
          <TabsTrigger value="realtime">
            <Radio />
            Real-Time Cyclone
          </TabsTrigger>
        </TabsList>

        <TabsContent value="past">
          <StoredCyclonesTab />
        </TabsContent>
        <TabsContent value="realtime">
          <RunNewCycloneTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
