import { useState, type FormEvent } from "react";
import { AlertTriangle, Upload } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCreateRun, type DamageModel } from "@/lib/preparednessApi";

const ACCEPT = ".nc,.csv,.xlsx,.xls";

export function UploadPanel({ onCreated }: { onCreated: (runId: number) => void }) {
  const create = useCreateRun();

  const [cycloneName, setCycloneName] = useState("");
  const [wind, setWind] = useState<File | null>(null);
  const [rainfall, setRainfall] = useState<File | null>(null);
  const [stormSurge, setStormSurge] = useState<File | null>(null);
  const [damageModel, setDamageModel] = useState<DamageModel>("ccm");
  const [polish, setPolish] = useState(true);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!wind) return;
    create.mutate(
      { cycloneName: cycloneName.trim() || "cyclone", wind, rainfall, stormSurge, damageModel, polish },
      { onSuccess: (run) => onCreated(run.id) },
    );
  };

  const fileField = (
    label: string,
    required: boolean,
    file: File | null,
    setFile: (f: File | null) => void,
  ) => (
    <label className="block">
      <span className="text-sm font-medium text-foreground">
        {label} {required && <span className="text-sunrise-900">*</span>}
      </span>
      <Input
        type="file"
        accept={ACCEPT}
        required={required}
        className="mt-1.5 cursor-pointer py-1.5"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      {file && <span className="mt-1 block text-xs text-muted-foreground">{file.name}</span>}
    </label>
  );

  return (
    <Card
      title="New preparedness run"
      subtitle="Upload a cyclone forecast — the portal runs the impact model and writes the guideline"
    >
      <form onSubmit={submit} className="space-y-5">
        <label className="block">
          <span className="text-sm font-medium text-foreground">Cyclone name</span>
          <Input
            className="mt-1.5"
            placeholder="e.g. Remal"
            value={cycloneName}
            onChange={(e) => setCycloneName(e.target.value)}
          />
        </label>

        <div className="grid gap-4 sm:grid-cols-3">
          {fileField("Wind forecast", true, wind, setWind)}
          {fileField("Rainfall", false, rainfall, setRainfall)}
          {fileField("Storm surge", false, stormSurge, setStormSurge)}
        </div>
        <p className="text-xs text-muted-foreground">Accepted formats: NetCDF, CSV, XLSX, XLS.</p>

        <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <label className="block">
            <span className="text-sm font-medium text-foreground">Damage model</span>
            <select
              className="mt-1.5 h-9 w-40 rounded-md border border-input bg-card px-3 text-sm text-foreground focus-visible:border-green-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25"
              value={damageModel}
              onChange={(e) => setDamageModel(e.target.value as DamageModel)}
            >
              <option value="ccm">CCM (default)</option>
              <option value="safir">SAFIR</option>
            </select>
          </label>

          <label className="flex items-center gap-2 pt-5 text-sm text-foreground">
            <input
              type="checkbox"
              className="size-4 accent-green-700"
              checked={polish}
              onChange={(e) => setPolish(e.target.checked)}
            />
            Polish guideline with the language model (if a key is configured)
          </label>
        </div>

        {create.isError && (
          <div className="flex items-start gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-xs text-sunrise-900">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>
              Could not start the run.{" "}
              {(create.error as { response?: { data?: { error?: { message?: string } } } })?.response
                ?.data?.error?.message ?? "Check the wind file and try again."}
            </span>
          </div>
        )}

        <Button type="submit" disabled={!wind || create.isPending}>
          <Upload />
          {create.isPending ? "Queuing…" : "Queue run"}
        </Button>
      </form>
    </Card>
  );
}
