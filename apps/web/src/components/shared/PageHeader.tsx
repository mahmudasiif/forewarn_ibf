import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";

type PageHeaderProps = {
  title: string;
  /** RFP module number, e.g. "Module 5" */
  module?: string;
  description?: string;
  actions?: ReactNode;
  meta?: ReactNode;
};

export function PageHeader({ title, module, description, actions, meta }: PageHeaderProps) {
  return (
    <header className="border-b border-border bg-card px-6 py-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-2xl font-bold uppercase tracking-wide text-foreground">
              {title}
            </h1>
            {module && <Badge variant="outline">{module}</Badge>}
          </div>
          {description && <p className="mt-1 max-w-3xl text-sm text-navy-700">{description}</p>}
          {meta && <div className="mt-3">{meta}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
