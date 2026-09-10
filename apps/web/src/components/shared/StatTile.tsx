import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type StatTileProps = {
  label: string;
  value: ReactNode;
  context?: string;
  /** Only severity may colour the value — see the design guideline. */
  valueClassName?: string;
  icon?: ReactNode;
};

export function StatTile({ label, value, context, valueClassName, icon }: StatTileProps) {
  return (
    <Card className="px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        {icon && <span className="text-muted-foreground">{icon}</span>}
      </div>
      <p
        className={cn(
          "mt-2 font-display text-3xl font-bold tabular-nums text-foreground",
          valueClassName,
        )}
      >
        {value}
      </p>
      {context && <p className="mt-1 text-xs text-muted-foreground">{context}</p>}
    </Card>
  );
}
