import { Database, PlayCircle } from "lucide-react";

import { PageHeader } from "@/components/shared/PageHeader";
import { StatusDot } from "@/components/shared/StatusDot";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RunNewCycloneTab } from "@/features/models/ccm/RunNewCycloneTab";
import { StoredCyclonesTab } from "@/features/models/ccm/StoredCyclonesTab";
import { useCyclones } from "@/lib/ccmApi";

export default function CCMPage() {
  const cyclones = useCyclones();
  const loaded = cyclones.data?.length ?? 0;

  return (
    <>
      <PageHeader
        title="CCM — Cyclone Classifier Model"
        module="Module 5"
        description="Cyclone impact by union across coastal Bangladesh, from the IWFM/BUET model."
        meta={
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">CCM v2.9.3</span>
            <StatusDot
              status={cyclones.isError ? "offline" : loaded > 0 ? "healthy" : "unknown"}
            />
            <span>{loaded > 0 ? `${loaded} cyclones loaded` : "No data loaded"}</span>
            <span>IWFM / BUET</span>
          </div>
        }
      />

      <div className="p-6">
        <Tabs defaultValue="stored">
          <TabsList>
            <TabsTrigger value="stored">
              <Database />
              Stored Cyclones
            </TabsTrigger>
            <TabsTrigger value="new">
              <PlayCircle />
              Run New Cyclone
            </TabsTrigger>
          </TabsList>

          <TabsContent value="stored">
            <StoredCyclonesTab />
          </TabsContent>
          <TabsContent value="new">
            <RunNewCycloneTab />
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
}
