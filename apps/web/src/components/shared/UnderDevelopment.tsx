import { Construction } from "lucide-react";

import { PageHeader } from "@/components/shared/PageHeader";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type UnderDevelopmentProps = {
  title: string;
  module?: string;
  description?: string;
  scope?: string[];
  phase?: string;
};

/** Placeholder for modules not built yet. Every route lands on a real screen. */
export function UnderDevelopment({
  title,
  module,
  description,
  scope = [],
  phase,
}: UnderDevelopmentProps) {
  return (
    <>
      <PageHeader title={title} module={module} description={description} />
      <div className="p-6">
        <Card>
          <CardHeader className="flex-col items-center gap-3 py-10 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-accent">
              <Construction className="size-6 text-green-700" />
            </span>
            <h2 className="font-display text-lg font-semibold">Not built yet</h2>
            <p className="max-w-md text-sm text-navy-700">
              Here is what this module will do.
            </p>
            {phase && <Badge variant="muted">{phase}</Badge>}
          </CardHeader>

          {scope.length > 0 && (
            <CardContent>
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Planned
              </p>
              <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                {scope.map((item) => (
                  <li
                    key={item}
                    className="flex gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-sm text-navy-700"
                  >
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-green-700" />
                    {item}
                  </li>
                ))}
              </ul>
            </CardContent>
          )}
        </Card>
      </div>
    </>
  );
}
