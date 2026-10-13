import { useEffect, useRef, useState } from "react";
import { ChevronDown, Download, FileSpreadsheet, FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type DownloadOption = {
  /** What the file is, in the user's words — "CSV", "Excel (.xlsx)". */
  label: string;
  /** A line under the label saying when to pick it. */
  hint?: string;
  href: string;
  /** Suggested filename, so the browser does not name it after the route. */
  filename?: string;
  icon?: "csv" | "xlsx";
};

type DownloadMenuProps = {
  options: DownloadOption[];
  label?: string;
  disabled?: boolean;
  className?: string;
};

const ICONS = {
  csv: FileText,
  xlsx: FileSpreadsheet,
} as const;

/**
 * A download button that opens a short list of formats.
 *
 * Written by hand rather than pulled from a menu library: it is one button and
 * two links, and the portal has no dropdown dependency yet. Adding one for
 * this would mean a new package in the image for every deployment.
 *
 * Each option is a plain anchor with `download`, so the browser handles the
 * transfer itself — no fetch, no blob held in memory, and a large export
 * streams straight to disk while the page stays usable.
 */
export function DownloadMenu({
  options,
  label = "Download",
  disabled = false,
  className,
}: DownloadMenuProps) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  // Close on an outside click or Escape. Both, because a menu that only closes
  // one way strands keyboard users with it open over the table.
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={container} className={cn("relative", className)}>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Download />
        {label}
        <ChevronDown
          className={cn("transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </Button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 w-56 overflow-hidden rounded-card border border-border bg-card py-1 shadow-lg"
        >
          {options.map((option) => {
            const Icon = ICONS[option.icon ?? "csv"];
            return (
              <a
                key={option.label}
                role="menuitem"
                href={option.href}
                download={option.filename}
                onClick={() => setOpen(false)}
                className="flex items-start gap-2.5 px-3 py-2 text-left text-sm transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
              >
                <Icon
                  className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                  aria-hidden
                />
                <span className="min-w-0">
                  <span className="block font-medium text-foreground">
                    {option.label}
                  </span>
                  {option.hint && (
                    <span className="block text-[11px] leading-snug text-muted-foreground">
                      {option.hint}
                    </span>
                  )}
                </span>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
