/**
 * Designed placeholders for modules not built yet. The scope lists come from
 * the RFP so a reviewer can see what each module will do. Replace a component
 * here with a real page as it gets built.
 */
import { UnderDevelopment } from "@/components/shared/UnderDevelopment";

export function EarlyWarningPage() {
  return (
    <UnderDevelopment
      title="Early Warning Signals"
      description="Turns model output into a plain-language warning when a threshold is crossed."
      phase="After the models are live"
      scope={[
        "Reads output from Modules 2, 3, 5, 7 and 9",
        "Writes the warning message automatically",
        "Thresholds set per hazard and per area",
        "Pushes signals to the Crisis Dashboard and alert channels",
        "Model output only — no personal data",
        "Audit trail of every signal",
      ]}
    />
  );
}

export function PreCrisisTargetingPage() {
  return (
    <UnderDevelopment
      title="Pre-crisis Targeting"
      module="Module 4"
      description="Targeting dashboard built on the pre-crisis dataset from FOREWARN and the working groups."
      phase="Phase 3"
      scope={[
        "Multi-layer selection",
        "Aligned with NAWG and humanitarian data standards",
        "Mauza-level data rolled up to union, upazila, district, division",
        "PDF reports by administrative level",
        "Excel and CSV export",
        "Role-based access",
      ]}
    />
  );
}

export function CycloneTrackPage() {
  return (
    <UnderDevelopment
      title="AI Cyclone Track Predictive Tool"
      module="Module 2"
      description="Built at the FOREWARN Hackathon. We host it here — we don't rebuild it."
      phase="Phase 3"
      scope={[
        "Upload a CSV to run the model",
        "Predicted tracks on an interactive map",
        "History of every run",
        "Full audit trail",
        "Role-based access",
        "Export results",
      ]}
    />
  );
}

export function PreparednessGuidancePage() {
  return (
    <UnderDevelopment
      title="Cyclone Preparedness Guidance"
      module="Module 3"
      description="Estimates cyclone impact by district, upazila and union, then writes guidance for it."
      phase="Phase 3"
      scope={[
        "Takes Excel, CSV, netCDF and raster input",
        "Union and thana-wise impact forecasts",
        "Table and map views",
        "Filter, search, browse past runs",
        "Guidance text written by an LLM",
        "Audit trail",
      ]}
    />
  );
}

export function FloodRiskPage() {
  return (
    <UnderDevelopment
      title="Dynamic Flood Risk Model (DFRM)"
      module="Module 7"
      description="IWFM's Jamuna basin flood model. v5.2.5 covers Jamalpur and Kurigram and is already on the server."
      phase="Phase 4 — after CCM"
      scope={[
        "Standalone software moved onto the web",
        "Automatic input from the FFWC feed",
        "Manual input too",
        "Runs in the cloud",
        "Map and table, with PDF and Excel export",
        "Role-based access",
      ]}
    />
  );
}

export function NowcastingPage() {
  return (
    <UnderDevelopment
      title="Weather Forecast & Nowcasting"
      module="Module 9"
      description="Daily guidance for decision-makers and for end users. Another team builds the pipeline; we put it on the web."
      phase="Phase 3"
      scope={[
        "Cloud-hosted visualisation",
        "Separate outputs for the two audiences",
        "Map view of forecast products",
        "Export in several formats",
        "Archive of past guidance",
        "Backup for the archive",
      ]}
    />
  );
}

export function ReportsPage() {
  return (
    <UnderDevelopment
      title="Reports & Exports"
      description="Reports and exports across every module — PDF, Excel, CSV."
      scope={[
        "PDF reports by administrative level",
        "Excel and CSV export from any view",
        "Large reports queued in the background",
        "Archive of past reports",
        "Role-based access",
      ]}
    />
  );
}

export function AnalyticsPage() {
  return (
    <UnderDevelopment
      title="Analytics"
      description="How well the forecasts did, and how impact and action have trended."
      scope={[
        "Forecast against what actually happened",
        "Model skill over time, by hazard",
        "Trends in people at risk and actions triggered",
        "Comparison across administrative levels",
      ]}
    />
  );
}

export function AdminUsersPage() {
  return (
    <UnderDevelopment
      title="Users & Roles"
      module="Module 1"
      description="Who can see and do what, across the whole platform."
      phase="Phase 3 — built first"
      scope={[
        "Create and manage users and roles",
        "Permissions per module and per dataset",
        "Four roles: Super Admin, Admin, Registered Viewer, General Viewer",
        "Public and signed-in access",
        "Email notifications",
        "Audit log of admin actions",
      ]}
    />
  );
}

export function LegacyDataPage() {
  return (
    <UnderDevelopment
      title="Legacy Data"
      module="Module 10"
      description="Moving data and features from the old IBF Portal into this one."
      phase="Phase 6"
      scope={[
        "Migrate data from the old platform",
        "Rebuild the features worth keeping",
        "Keep data intact and consistent",
        "End-to-end testing before go-live",
      ]}
    />
  );
}

export function AdminSettingsPage() {
  return (
    <UnderDevelopment
      title="Settings"
      description="Models, data sources, thresholds, notifications and backups."
      scope={[
        "Register, enable or disable a model",
        "Data sources and their schedules",
        "Alert thresholds by hazard and area",
        "Notification channels",
        "Backup schedule",
      ]}
    />
  );
}

export function ProfilePage() {
  return (
    <UnderDevelopment
      title="My Profile"
      description="Your account, your role, your notifications."
      scope={[
        "View and update your details",
        "Change password",
        "See what your role allows",
        "Choose which emails you get",
      ]}
    />
  );
}

export function NotFoundPage() {
  return (
    <UnderDevelopment
      title="Page not found"
      description="No page at this address. Use the menu on the left."
    />
  );
}
