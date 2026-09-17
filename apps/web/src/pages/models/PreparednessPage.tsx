import { useEffect, useState } from "react";
import { Database, PlayCircle } from "lucide-react";

import { PageHeader } from "@/components/shared/PageHeader";
import { StatusDot } from "@/components/shared/StatusDot";
import { Card } from "@/components/shared/Card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RunDetail } from "@/features/models/preparedness/RunDetail";
import { RunList } from "@/features/models/preparedness/RunList";
import { UploadPanel } from "@/features/models/preparedness/UploadPanel";
import { useRuns } from "@/lib/preparednessApi";

export default function PreparednessPage() {
  const runs = useRuns();
  const [tab, setTab] = useState("runs");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Default the selection to the most recent run once the list arrives.
  useEffect(() => {
    if (selectedId == null && runs.data?.length) setSelectedId(runs.data[0].id);
  }, [runs.data, selectedId]);

  const loaded = runs.data?.length ?? 0;

  return (
    <>
      <PageHeader
        title="Cyclone Preparedness Guidance"
        module="Module 3"
        description="Impact by union, upazila and district from a cyclone forecast, with a plain-language preparedness guideline."
        meta={
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <StatusDot status={runs.isError ? "offline" : loaded > 0 ? "healthy" : "unknown"} />
            <span>{loaded > 0 ? `${loaded} run${loaded === 1 ? "" : "s"}` : "No runs yet"}</span>
            <span>IWFM / BUET · LLM-assisted</span>
          </div>
        }
      />

      <div className="p-6">
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
              <Card title="Runs" subtitle="Every preparedness run, newest first" bodyClassName="p-0">
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
    </>
  );
}
