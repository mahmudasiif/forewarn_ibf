import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import {
  ChevronDown,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  UserRound,
  X,
} from "lucide-react";

import { NAV, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

const COLLAPSE_KEY = "forewarn.sidebar.collapsed";

/** Remember the choice between visits. Storage can throw in private windows. */
function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

function BrandMark() {
  return (
    <Link to="/" className="block px-5 py-5">
      <p className="font-display text-xl font-bold uppercase leading-none tracking-wide text-white">
        FOREWARN
      </p>
      <p className="font-display mt-1 text-sm font-medium uppercase leading-none tracking-[0.2em] text-green-500">
        Bangladesh
      </p>
      <p className="mt-2 text-[11px] leading-tight text-navy-200">
        Impact-Based Forecasting Portal
      </p>
    </Link>
  );
}

function NavGroup({ item, pathname }: { item: NavItem; pathname: string }) {
  const childActive = useMemo(
    () => item.children?.some((child) => pathname === child.to) ?? false,
    [item.children, pathname],
  );
  const [open, setOpen] = useState(childActive);
  const isOpen = open || childActive;
  const Icon = item.icon;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={isOpen}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors",
          "text-navy-200 hover:bg-white/5 hover:text-white",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green-500",
          childActive && "text-white",
        )}
      >
        <Icon className="size-4 shrink-0" />
        <span className="flex-1 font-medium">{item.label}</span>
        <ChevronDown
          className={cn("size-4 shrink-0 transition-transform", isOpen && "rotate-180")}
        />
      </button>

      {isOpen && (
        <ul className="ml-5 mt-1 space-y-0.5 border-l border-white/10 pl-3">
          {item.children?.map((child) => (
            <li key={child.to}>
              <Link
                to={child.to}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                  "text-navy-200 hover:bg-white/5 hover:text-white",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green-500",
                )}
                activeProps={{ className: "bg-white/10 text-white font-medium" }}
                activeOptions={{ exact: true }}
              >
                <span className="min-w-0 flex-1 truncate">{child.label}</span>
                {child.live && (
                  <span
                    className="size-1.5 shrink-0 rounded-full bg-green-300"
                    title="Connected to a live model service"
                  />
                )}
                {child.module && (
                  <span className="shrink-0 text-[10px] tabular-nums text-navy-200/60">
                    {child.module}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SidebarNav({ pathname }: { pathname: string }) {
  return (
    <nav className="min-h-0 flex-1 space-y-6 overflow-y-auto px-3 pb-6">
      {NAV.map((section, index) => (
        <div key={section.heading ?? `section-${index}`}>
          {section.heading && (
            <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.15em] text-navy-200/60">
              {section.heading}
            </p>
          )}
          <div className="space-y-0.5">
            {section.items.map((item) =>
              item.children ? (
                <NavGroup key={item.label} item={item} pathname={pathname} />
              ) : (
                <Link
                  key={item.to}
                  to={item.to!}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                    "text-navy-200 hover:bg-white/5 hover:text-white",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green-500",
                  )}
                  activeProps={{ className: "bg-white/10 text-white font-medium" }}
                  activeOptions={{ exact: true }}
                >
                  <item.icon className="size-4 shrink-0" />
                  <span className="flex-1">{item.label}</span>
                  {item.module && (
                    <span className="text-[10px] tabular-nums text-navy-200/60">
                      {item.module}
                    </span>
                  )}
                </Link>
              ),
            )}
          </div>
        </div>
      ))}
    </nav>
  );
}

/**
 * Fixed-height shell: the sidebar and top bar stay put, only the page body
 * scrolls.
 *
 * The sidebar hides on both sizes, but differently. On a phone it slides over
 * the page as a drawer, because there is no room to sit beside it. On a desktop
 * it collapses to nothing and the content widens into the space — which is the
 * point, since the map and the wide result tables want every pixel. The desktop
 * choice is remembered; the mobile drawer is not, because a drawer that is still
 * open when you come back is just in the way.
 */
export function DashboardLayout() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((value) => {
      const next = !value;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        // Private windows can refuse storage; the toggle still works this session.
      }
      return next;
    });
  }, []);

  // Ctrl/Cmd+B, the shortcut people already expect from their editor.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") {
        event.preventDefault();
        toggleCollapsed();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggleCollapsed]);

  // Close the mobile drawer on navigation — otherwise it covers the page you
  // just asked for.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <div className="flex h-screen overflow-hidden bg-navy-50">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 shrink-0 overflow-hidden bg-navy-900",
          "transition-transform duration-200",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          // On desktop it is part of the layout and animates its width instead.
          "lg:static lg:translate-x-0 lg:transition-[width] lg:duration-200",
          collapsed ? "lg:w-0" : "lg:w-64",
        )}
        aria-hidden={collapsed ? undefined : false}
      >
        {/* Fixed inner width so the contents do not reflow mid-animation */}
        <div className="flex h-full w-64 flex-col">
          <div className="shrink-0">
            <BrandMark />
          </div>
          <SidebarNav pathname={pathname} />
          <div className="shrink-0 border-t border-white/10 px-5 py-4">
            <p className="text-[10px] leading-relaxed text-navy-200/70">
              A programme of the
              <br />
              <span className="text-green-500">Start Bangladesh Hub</span>
            </p>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-navy-900/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-card px-4 lg:px-6">
          <div className="flex items-center gap-3">
            {/* Phone: opens the drawer */}
            <button
              type="button"
              onClick={() => setMobileOpen((value) => !value)}
              className="rounded-lg p-2 text-navy-700 hover:bg-navy-50 lg:hidden"
              aria-label={mobileOpen ? "Close menu" : "Open menu"}
            >
              {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>

            {/* Desktop: collapses the sidebar into the page */}
            <button
              type="button"
              onClick={toggleCollapsed}
              className="hidden rounded-lg p-2 text-navy-700 hover:bg-navy-50 lg:inline-flex"
              aria-label={collapsed ? "Show sidebar" : "Hide sidebar"}
              title={`${collapsed ? "Show" : "Hide"} sidebar  (Ctrl+B)`}
            >
              {collapsed ? (
                <PanelLeftOpen className="size-5" />
              ) : (
                <PanelLeftClose className="size-5" />
              )}
            </button>

            {/* The wordmark reappears here when the sidebar is away, so the
                page never loses its identity or a way back home. */}
            {collapsed && (
              <Link to="/" className="hidden items-center lg:flex">
                <span className="font-display text-base font-bold uppercase tracking-wide text-navy-900">
                  FOREWARN
                </span>
                <span className="font-display ml-1.5 text-xs font-medium uppercase tracking-[0.2em] text-green-700">
                  BD
                </span>
              </Link>
            )}
          </div>

          <p className="hidden text-xs text-muted-foreground xl:block">
            Anticipatory action for Bangladesh · data shown in Asia/Dhaka (+06)
          </p>

          <div className="flex items-center gap-2">
            <Link
              to="/profile"
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-navy-700 hover:bg-navy-50"
            >
              <span className="flex size-7 items-center justify-center rounded-full bg-accent">
                <UserRound className="size-4 text-green-700" />
              </span>
              <span className="hidden sm:inline">M. Saleheen</span>
            </Link>
            <Link
              to="/login"
              className="rounded-lg p-2 text-muted-foreground hover:bg-navy-50 hover:text-navy-900"
              aria-label="Sign out"
            >
              <LogOut className="size-4" />
            </Link>
          </div>
        </header>

        {/* The only scrolling region on the page */}
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
