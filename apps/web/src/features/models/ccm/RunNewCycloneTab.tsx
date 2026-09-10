import { useState } from "react";
import { ArrowRight, CheckCircle2, ExternalLink, Info, Monitor, Upload } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";

const CCM_SESSION_URL = import.meta.env.VITE_CCM_DASHBOARD_URL ?? "/ccm/";

const STEPS = [
  {
    title: "Upload the input",
    body: "Add the track and rainfall files for the new cyclone.",
    icon: Upload,
  },
  {
    title: "Run the model",
    body: "Open the model, set the parameters, save the result table.",
    icon: Monitor,
  },
  {
    title: "Results land here",
    body: "The portal picks up the result. The cyclone joins Stored Cyclones.",
    icon: CheckCircle2,
  },
];

export function RunNewCycloneTab() {
  const [sessionOpen, setSessionOpen] = useState(false);

  return (
    <div className="space-y-6">
      <Card title="How it works" subtitle="Three steps, then it behaves like any other cyclone">
        <ol className="grid gap-4 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="relative">
              <div className="flex items-start gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent">
                  <step.icon className="size-4 text-green-700" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    <span className="text-muted-foreground">{index + 1}.</span> {step.title}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-navy-700">{step.body}</p>
                </div>
              </div>
              {index < STEPS.length - 1 && (
                <ArrowRight className="absolute -right-2 top-2 hidden size-4 text-border md:block" />
              )}
            </li>
          ))}
        </ol>
      </Card>

      <Card title="1 · Upload input" subtitle="Track and rainfall files">
        <div className="rounded-lg border-2 border-dashed border-border bg-muted px-6 py-10 text-center">
          <Upload className="mx-auto size-8 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium">Upload not ready yet</p>
          <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-navy-700">
            Waiting on BUET to confirm which files a run needs. Then upload works here.
          </p>
        </div>
      </Card>

      <Card
        title="2 · Run the model"
        subtitle="Opens CCM on the model server"
        action={
          <Button variant="secondary" size="sm" asChild>
            <a href={CCM_SESSION_URL} target="_blank" rel="noreferrer">
              <ExternalLink />
              New window
            </a>
          </Button>
        }
        bodyClassName={sessionOpen ? "p-0" : undefined}
      >
        {sessionOpen ? (
          <div className="h-[560px] w-full overflow-hidden rounded-b-card bg-muted">
            <iframe
              src={CCM_SESSION_URL}
              title="CCM model session"
              className="size-full border-0"
              allow="fullscreen; clipboard-read; clipboard-write"
            />
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-muted">
              <Monitor className="size-6 text-muted-foreground" />
            </span>
            <p className="text-sm font-medium">Model session</p>
            <p className="max-w-sm text-xs leading-relaxed text-navy-700">
              CCM runs on the model server. This opens its own screen for a new run.
            </p>
            <Button className="mt-1" onClick={() => setSessionOpen(true)}>
              Open model session
            </Button>
          </div>
        )}
      </Card>

      <Card title="3 · Import the result" subtitle="Brings the finished run into the portal">
        <div className="rounded-lg border border-border bg-muted px-5 py-4">
          <p className="text-sm text-navy-700">
            Save the run on the server, then import it. Until upload is ready, one command:
          </p>
          <pre className="mt-3 overflow-x-auto rounded-lg border border-border bg-card px-4 py-3 font-mono text-xs">
{`docker compose exec api python -m scripts.import_ccm \\
    --only <CycloneName> --source upload`}
          </pre>
        </div>
      </Card>

      <div className="flex gap-3 rounded-card border border-border bg-card px-5 py-4">
        <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <div className="text-xs leading-relaxed text-navy-700">
          <p className="font-medium text-foreground">Why this tab exists</p>
          <p className="mt-1">
            Cyclones already in the system are served straight from the portal. A brand new one
            still has to be calculated by CCM itself, so that step runs on the model server. We
            have asked BUET for a way to trigger it directly. When that lands, this becomes a
            single Run button.
          </p>
        </div>
      </div>
    </div>
  );
}
