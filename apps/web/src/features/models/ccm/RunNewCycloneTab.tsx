import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  FileUp,
  Info,
  Loader2,
  Play,
} from "lucide-react";

import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  RUN_FILE_FIELDS,
  THRUST_FORCE_FIELDS,
  startRun,
  useRun,
  useRuns,
  type CCMRun,
  type RunMeta,
} from "@/lib/ccmApi";

/** A run holds the model busy for minutes; this is only about how it reads. */
const STATUS_LABEL: Record<CCMRun["status"], string> = {
  queued: "Queued",
  running: "Running…",
  succeeded: "Done",
  failed: "Failed",
};

type Files = Record<string, File | undefined>;

export function RunNewCycloneTab() {
  const queryClient = useQueryClient();
  const runs = useRuns();

  const [meta, setMeta] = useState<RunMeta>({
    cyclone_code: "",
    cyclone_type: "realtime",
  });
  const [files, setFiles] = useState<Files>({});
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const activeRun = useRun(activeRunId);

  const pickFile =
    (field: string) => (event: React.ChangeEvent<HTMLInputElement>) =>
      setFiles((current) => ({ ...current, [field]: event.target.files?.[0] }));

  const missingRequired = RUN_FILE_FIELDS.filter(
    (f) => f.required && !files[f.field],
  );
  // Thrust force: either the pre-computed CSV, or all three source grids.
  const hasThrustCsv = Boolean(files.thrust_force_csv);
  const hasThrustGrids =
    Boolean(files.water_depth_tf_xyz) &&
    Boolean(files.wind_speed_tf_xyz) &&
    Boolean(files.depth_avg_velocity_tf_xyz);
  const thrustSatisfied = hasThrustCsv || hasThrustGrids;

  const codeValid = /^[A-Za-z0-9_-]{3,120}$/.test(meta.cyclone_code);
  const canSubmit =
    codeValid && missingRequired.length === 0 && thrustSatisfied && !submitting;

  const submit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const accepted = await startRun(meta, files);
      setActiveRunId(accepted.id);
      void queryClient.invalidateQueries({ queryKey: ["ccm", "runs"] });
    } catch (error) {
      const detail =
        (
          error as {
            response?: {
              data?: { detail?: string; error?: { message?: string } };
            };
          }
        ).response?.data?.detail ??
        (error as { response?: { data?: { error?: { message?: string } } } })
          .response?.data?.error?.message ??
        "The run could not be started.";
      setSubmitError(String(detail));
    } finally {
      setSubmitting(false);
    }
  };

  // Once results land, the stored-cyclone lists are stale.
  if (activeRun.data?.status === "succeeded") {
    void queryClient.invalidateQueries({ queryKey: ["ccm", "cyclones"] });
  }

  return (
    <div className="space-y-6">
      <Card
        title="Run the model"
        subtitle="Upload a cyclone's simulation output — the portal computes hazard, vulnerability and risk for every coastal union"
      >
        <div className="flex gap-3 rounded-lg border border-border bg-muted px-4 py-3">
          <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <p className="text-xs leading-relaxed text-navy-700">
            These files come from the storm-surge modelling run, not from the
            portal. The model needs the water depth, wind speed and rainfall
            grids plus the cyclone track, and thrust force — either already
            computed, or the three grids it is derived from. A run takes a few
            minutes; you can leave this page while it works.
          </p>
        </div>

        {/* Cyclone identity */}
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="cyclone_code">
              Cyclone code <span className="text-destructive">*</span>
            </Label>
            <Input
              id="cyclone_code"
              placeholder="MD19072026_Actual"
              value={meta.cyclone_code}
              onChange={(e) =>
                setMeta({ ...meta, cyclone_code: e.target.value })
              }
            />
            <p className="text-[11px] text-muted-foreground">
              {meta.cyclone_code && !codeValid
                ? "Letters, digits, underscore or hyphen; 3–120 characters."
                : "Re-using a code replaces that cyclone's results."}
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="name">Display name</Label>
            <Input
              id="name"
              placeholder="Remal"
              value={meta.name ?? ""}
              onChange={(e) => setMeta({ ...meta, name: e.target.value })}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="event_date">Event date</Label>
            <Input
              id="event_date"
              type="date"
              value={meta.event_date ?? ""}
              onChange={(e) => setMeta({ ...meta, event_date: e.target.value })}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="landfall_location">Landfall location</Label>
            <Input
              id="landfall_location"
              placeholder="Satkhira"
              value={meta.landfall_location ?? ""}
              onChange={(e) =>
                setMeta({ ...meta, landfall_location: e.target.value })
              }
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="max_wind_speed">Max wind speed (km/hr)</Label>
            <Input
              id="max_wind_speed"
              type="number"
              inputMode="numeric"
              placeholder="111"
              value={meta.max_wind_speed ?? ""}
              onChange={(e) =>
                setMeta({ ...meta, max_wind_speed: e.target.value })
              }
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="remark">Remark</Label>
            <Input
              id="remark"
              placeholder="Forecast track, 48h lead"
              value={meta.remark ?? ""}
              onChange={(e) => setMeta({ ...meta, remark: e.target.value })}
            />
          </div>
        </div>

        {/* Required simulation files */}
        <p className="mt-8 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Simulation output
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {RUN_FILE_FIELDS.map((field) => (
            <FilePicker
              key={field.field}
              id={field.field}
              label={field.label}
              hint={field.hint}
              required={field.required}
              file={files[field.field]}
              onChange={pickFile(field.field)}
            />
          ))}
        </div>

        {/* Thrust force */}
        <p className="mt-8 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Thrust force
        </p>
        <p className="mt-1 text-xs text-navy-700">
          Upload the pre-computed file, <em>or</em> all three grids below.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {THRUST_FORCE_FIELDS.map((field) => (
            <FilePicker
              key={field.field}
              id={field.field}
              label={field.label}
              hint={field.hint}
              file={files[field.field]}
              onChange={pickFile(field.field)}
            />
          ))}
        </div>

        {/* Submit */}
        <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-border pt-5">
          <Button onClick={submit} disabled={!canSubmit}>
            {submitting ? <Loader2 className="animate-spin" /> : <Play />}
            {submitting ? "Starting…" : "Run model"}
          </Button>

          {!canSubmit && !submitting && (
            <p className="text-xs text-muted-foreground">
              {!codeValid
                ? "Enter a cyclone code to continue."
                : missingRequired.length > 0
                  ? `Still needed: ${missingRequired.map((f) => f.label).join(", ")}`
                  : "Thrust force is still missing."}
            </p>
          )}
        </div>

        {submitError && (
          <p className="mt-3 flex items-start gap-2 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            {submitError}
          </p>
        )}
      </Card>

      {activeRun.data && <RunProgress run={activeRun.data} />}

      <Card title="Recent runs" subtitle="Newest first" bodyClassName="p-0">
        {runs.isLoading ? (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">
            Loading…
          </p>
        ) : (runs.data?.length ?? 0) === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">
            No runs yet. The cyclones shipped with the model are under Stored
            Cyclones.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {runs.data?.map((run) => (
              <li
                key={run.id}
                className="flex flex-wrap items-center justify-between gap-3 px-5 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {run.cyclone_name ?? run.cyclone_code}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(run.created_at).toLocaleString()}
                    {run.row_count !== null &&
                      ` · ${run.row_count.toLocaleString()} unions`}
                    {run.took_ms !== null &&
                      ` · ${Math.round(run.took_ms / 1000)}s`}
                  </p>
                  {run.error && (
                    <p className="mt-1 max-w-xl text-xs leading-relaxed text-destructive">
                      {run.error}
                    </p>
                  )}
                </div>
                <StatusPill status={run.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function FilePicker({
  id,
  label,
  hint,
  required = false,
  file,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  required?: boolean;
  file?: File;
  onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Label htmlFor={id} className="text-sm">
            {label} {required && <span className="text-destructive">*</span>}
          </Label>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
            {file ? `${file.name} · ${formatBytes(file.size)}` : hint}
          </p>
        </div>
        {file ? (
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-green-700" />
        ) : (
          <FileUp className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        )}
      </div>
      <Input
        id={id}
        type="file"
        onChange={onChange}
        className="mt-2 h-auto py-1.5 text-xs"
      />
    </div>
  );
}

function RunProgress({ run }: { run: CCMRun }) {
  const inFlight = run.status === "queued" || run.status === "running";

  return (
    <Card
      title={`Run #${run.id} — ${run.cyclone_code}`}
      subtitle={
        inFlight
          ? "The model is working. This updates on its own; you can leave the page."
          : run.status === "succeeded"
            ? "Finished. The cyclone is now in Stored Cyclones."
            : "The run did not finish."
      }
      action={<StatusPill status={run.status} />}
    >
      {inFlight && (
        <div className="flex items-center gap-3 text-sm text-navy-700">
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
          Joining the simulation grid against 1,585 union boundaries — usually a
          few minutes.
        </div>
      )}

      {run.status === "succeeded" && (
        <p className="text-sm text-navy-700">
          {run.row_count?.toLocaleString()} unions computed
          {run.took_ms ? ` in ${Math.round(run.took_ms / 1000)} seconds` : ""}.
          Switch to <strong>Stored Cyclones</strong> and pick{" "}
          {run.cyclone_name ?? run.cyclone_code} to see the map and table.
        </p>
      )}

      {run.status === "failed" && (
        <div className="flex gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div className="min-w-0 text-xs leading-relaxed">
            <p className="font-medium text-destructive">
              The model rejected this run
            </p>
            <p className="mt-1 break-words text-navy-700">{run.error}</p>
            <p className="mt-2 text-muted-foreground">
              Most often this is a file in an unexpected shape — a grid with a
              different number of header lines, or a track missing one of its
              sidecar files. Nothing was saved, so correcting the file and
              running again is safe.
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}

function StatusPill({ status }: { status: CCMRun["status"] }) {
  const tone =
    status === "succeeded"
      ? "bg-accent text-green-700"
      : status === "failed"
        ? "bg-destructive/10 text-destructive"
        : "bg-muted text-navy-700";

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${tone}`}
    >
      {(status === "queued" || status === "running") && (
        <Loader2 className="size-3 animate-spin" />
      )}
      {STATUS_LABEL[status]}
    </span>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}
