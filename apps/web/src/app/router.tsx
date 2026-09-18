import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import type { ReactNode } from "react";

import { AuthLayout } from "@/app/layouts/AuthLayout";
import { DashboardLayout } from "@/app/layouts/DashboardLayout";

import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import CrisisDashboardPage from "@/pages/CrisisDashboardPage";
import ActivityTrackingPage from "@/pages/ActivityTrackingPage";
import ModelsPage from "@/pages/models/ModelsPage";
import CCMPage from "@/pages/models/CCMPage";
import PreparednessPage from "@/pages/models/PreparednessPage";
import DFRMPage from "@/pages/models/DFRMPage";
import {
  AdminSettingsPage,
  AdminUsersPage,
  AnalyticsPage,
  CycloneTrackPage,
  EarlyWarningPage,
  LegacyDataPage,
  NotFoundPage,
  NowcastingPage,
  PreCrisisTargetingPage,
  ProfilePage,
  ReportsPage,
} from "@/pages/placeholders";

const rootRoute = createRootRoute({ component: Outlet, notFoundComponent: NotFoundPage });

const authLayout = createRoute({
  getParentRoute: () => rootRoute,
  id: "auth",
  component: AuthLayout,
});

const appLayout = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  component: DashboardLayout,
});

type Layout = typeof authLayout | typeof appLayout;

// `path` must stay a string literal, not widen to `string`, or TanStack
// Router loses the per-route type and every `Link to=` falls back to just
// "/" | "." | "..". The <TPath extends string> generic is what keeps it.
const route = <TPath extends string>(
  parent: Layout,
  path: TPath,
  component: () => ReactNode,
) => createRoute({ getParentRoute: () => parent, path, component });

const routeTree = rootRoute.addChildren([
  authLayout.addChildren([route(authLayout, "/login", LoginPage)]),
  appLayout.addChildren([
    route(appLayout, "/", DashboardPage),

    // Situation
    route(appLayout, "/crisis", CrisisDashboardPage),
    route(appLayout, "/early-warning", EarlyWarningPage),
    route(appLayout, "/pre-crisis", PreCrisisTargetingPage),

    // Models — CCM is the one wired to a live service
    route(appLayout, "/models", ModelsPage),
    route(appLayout, "/models/ccm", CCMPage),
    route(appLayout, "/models/cyclone-track", CycloneTrackPage),
    route(appLayout, "/models/preparedness", PreparednessPage),
    route(appLayout, "/models/flood-risk", DFRMPage),
    route(appLayout, "/models/nowcasting", NowcastingPage),

    // Programme
    route(appLayout, "/activities", ActivityTrackingPage),
    route(appLayout, "/reports", ReportsPage),
    route(appLayout, "/analytics", AnalyticsPage),

    // Administration
    route(appLayout, "/admin/users", AdminUsersPage),
    route(appLayout, "/admin/legacy", LegacyDataPage),
    route(appLayout, "/admin/settings", AdminSettingsPage),

    route(appLayout, "/profile", ProfilePage),
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

export function AppRouter() {
  return <RouterProvider router={router} />;
}
