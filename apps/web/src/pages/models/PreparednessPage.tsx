import { useEffect, useState } from "react";
import { Database, PlayCircle } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RunDetail } from "@/features/models/preparedness/RunDetail";
import { RunList } from "@/features/models/preparedness/RunList";
import { UploadPanel } from "@/features/models/preparedness/UploadPanel";
import { usePageHeading } from "@/lib/pageHeading";
import { useRuns } from "@/lib/preparednessApi";

export default function PreparednessPage() {
  const runs = useRuns();
  const [tab, setTab] = useState("runs");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Default the selection to the most recent run once the list arrives.
  useEffect(() => {
    if (selectedId == null && runs.data?.length) setSelectedId(runs.data[0].id);
  }, [runs.data, selectedId]);

  usePageHeading("Cyclone Preparedness Guidance (IWFM / BUET)", "Module 3");

  return (
    <div className="p-3">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="runs">
            <Database />
            Runs
          </TabsTrigger>
          <TabsTrigger value="new">
            <PlayCircle />
            New Run
          </TabsTrigger>
        </TabsList>

        <TabsContent value="runs">
          <div className="space-y-6">
            <Card
              title="Runs"
              subtitle="Every preparedness run, newest first"
              bodyClassName="p-0"
            >
              <RunList
                runs={runs.data ?? []}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            </Card>
            {selectedId != null && <RunDetail runId={selectedId} />}
          </div>
        </TabsContent>

        <TabsContent value="new">
          <UploadPanel
            onCreated={(id) => {
              setSelectedId(id);
              setTab("runs");
            }}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
