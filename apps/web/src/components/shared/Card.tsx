import type { ReactNode } from "react";

import {
  Card as UICard,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

type CardProps = {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
};

/**
 * Project convenience wrapper over the shadcn Card — title, subtitle and a
 * right-aligned action in one prop set, so pages don't repeat the same header
 * markup. Reach for the shadcn primitives directly when you need more control.
 */
export function Card({ title, subtitle, action, className, bodyClassName, children }: CardProps) {
  return (
    <UICard className={className}>
      {(title || action) && (
        <CardHeader>
          <div className="min-w-0">
            {title && <CardTitle>{title}</CardTitle>}
            {subtitle && <CardDescription>{subtitle}</CardDescription>}
          </div>
          {action && <CardAction>{action}</CardAction>}
        </CardHeader>
      )}
      <CardContent className={cn(bodyClassName)}>{children}</CardContent>
    </UICard>
  );
}
