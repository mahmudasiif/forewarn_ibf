import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Severity variants follow the brand rule on text colour: white text only on
 * navy or on the darkest shade of a colour family; navy text everywhere else,
 * including every green.
 */
const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium [&_svg]:size-3 [&_svg]:pointer-events-none",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-secondary text-secondary-foreground",
        outline: "border border-border text-foreground",
        muted: "bg-muted text-muted-foreground",

        "severity-none": "bg-severity-none text-navy-900",
        "severity-advisory": "bg-severity-advisory text-navy-900",
        "severity-moderate": "bg-severity-moderate text-white",
        "severity-severe": "bg-severity-severe text-navy-900",
        "severity-extreme": "bg-severity-extreme text-white",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

function Badge({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "span";
  return (
    <Comp data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
