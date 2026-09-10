/**
 * Demonstration data.
 *
 * Everything in this file is placeholder content used to show the interface
 * before the real pipelines are connected. CCM is the exception — that screen
 * talks to the live model service and does not read from here.
 *
 * Delete a block from this file the moment its real endpoint exists.
 */

import type { Severity } from "@/components/shared/SeverityBadge";
import type { ServiceStatus } from "@/components/shared/StatusDot";

export const LAST_ISSUE_TIME = "09 Sep 2026, 06:00 (+06)";

export type DistrictImpact = {
  id: string;
  district: string;
  division: string;
  severity: Severity;
  peopleAtRisk: number;
  unionsAffected: number;
  leadTimeHours: number;
};

export const DISTRICT_IMPACTS: DistrictImpact[] = [
  { id: "kurigram", district: "Kurigram", division: "Rangpur", severity: "severe", peopleAtRisk: 42000, unionsAffected: 14, leadTimeHours: 72 },
  { id: "jamalpur", district: "Jamalpur", division: "Mymensingh", severity: "severe", peopleAtRisk: 38500, unionsAffected: 11, leadTimeHours: 72 },
  { id: "gaibandha", district: "Gaibandha", division: "Rangpur", severity: "moderate", peopleAtRisk: 21400, unionsAffected: 9, leadTimeHours: 96 },
  { id: "sirajganj", district: "Sirajganj", division: "Rajshahi", severity: "moderate", peopleAtRisk: 18900, unionsAffected: 7, leadTimeHours: 96 },
  { id: "bogura", district: "Bogura", division: "Rajshahi", severity: "advisory", peopleAtRisk: 9600, unionsAffected: 5, leadTimeHours: 120 },
  { id: "tangail", district: "Tangail", division: "Dhaka", severity: "advisory", peopleAtRisk: 7300, unionsAffected: 4, leadTimeHours: 120 },
  { id: "rangpur", district: "Rangpur", division: "Rangpur", severity: "none", peopleAtRisk: 0, unionsAffected: 0, leadTimeHours: 120 },
];

export type WarningSignal = {
  id: string;
  headline: string;
  hazard: string;
  area: string;
  severity: Severity;
  issuedAt: string;
  source: string;
};

export const WARNING_SIGNALS: WarningSignal[] = [
  {
    id: "sig-104",
    headline: "Jamuna water level projected above danger level within 72 hours",
    hazard: "Flood",
    area: "Kurigram, Jamalpur, Gaibandha",
    severity: "severe",
    issuedAt: "09 Sep 2026, 06:12 (+06)",
    source: "DFRM v5.2.5 · AI analysis layer",
  },
  {
    id: "sig-103",
    headline: "Sustained rainfall raises moderate flood risk across four upazilas",
    hazard: "Flood",
    area: "Sirajganj",
    severity: "moderate",
    issuedAt: "08 Sep 2026, 18:04 (+06)",
    source: "DFRM v5.2.5 · AI analysis layer",
  },
  {
    id: "sig-102",
    headline: "Low pressure over Bay of Bengal — monitoring for cyclogenesis",
    hazard: "Cyclone",
    area: "Coastal belt",
    severity: "advisory",
    issuedAt: "08 Sep 2026, 09:30 (+06)",
    source: "Cyclone Track · AI analysis layer",
  },
];

export type ModelSummary = {
  id: string;
  name: string;
  shortName: string;
  version: string;
  module: string;
  status: ServiceStatus;
  lastRun: string;
  runtime: string;
  to: string;
  /** True only for models actually wired to a running service. */
  live: boolean;
  description: string;
};

export const MODELS: ModelSummary[] = [
  {
    id: "ccm",
    name: "Cyclone Classifier Model",
    shortName: "CCM",
    version: "v2.9.3",
    module: "Module 5",
    status: "healthy",
    lastRun: "09 Sep 2026, 05:40 (+06)",
    runtime: "IWFM / BUET · Delft3D-dependent",
    to: "/models/ccm",
    live: true,
    description:
      "Cyclone classification from the IWFM/BUET model, web-enabled in the portal. Phase 1 standalone-to-web is integrated; Phase 2 chains it to Delft3D.",
  },
  {
    id: "dfrm",
    name: "Dynamic Flood Risk Model",
    shortName: "DFRM",
    version: "v5.2.5",
    module: "Module 7",
    status: "unknown",
    lastRun: "—",
    runtime: "IWFM Jamuna basin · Jamalpur, Kurigram",
    to: "/models/flood-risk",
    live: false,
    description:
      "IWFM's Jamuna basin flood model, automated against the FFWC feed. Uploaded to the server; web integration pending.",
  },
  {
    id: "cyclone-track",
    name: "AI Cyclone Track Predictive Tool",
    shortName: "Cyclone Track",
    version: "hackathon build",
    module: "Module 2",
    status: "unknown",
    lastRun: "—",
    runtime: "FOREWARN Disaster Hackathon",
    to: "/models/cyclone-track",
    live: false,
    description:
      "Predicts cyclone tracks from CSV input and plots them on an interactive map, with a full history of every run.",
  },
  {
    id: "preparedness",
    name: "Cyclone Preparedness Guidance",
    shortName: "Preparedness",
    version: "hackathon build",
    module: "Module 3",
    status: "unknown",
    lastRun: "—",
    runtime: "FOREWARN Disaster Hackathon · LLM-assisted",
    to: "/models/preparedness",
    live: false,
    description:
      "Estimates cyclone impact by district, upazila and union, then generates plain-language preparedness guidance.",
  },
  {
    id: "nowcasting",
    name: "Weather Forecast & Nowcasting",
    shortName: "Nowcasting",
    version: "pipeline external",
    module: "Module 9",
    status: "unknown",
    lastRun: "—",
    runtime: "Multi-model ensemble · built by partner team",
    to: "/models/nowcasting",
    live: false,
    description:
      "Role-based daily forecast guidelines for decision-makers and end users, built on ensemble forecasts and climatology.",
  },
];

export type ModelRun = {
  id: string;
  model: string;
  trigger: "manual" | "scheduled" | "ingestion";
  status: "succeeded" | "running" | "failed" | "queued";
  startedAt: string;
  duration: string;
  triggeredBy: string;
};

export const MODEL_RUNS: ModelRun[] = [
  { id: "run-2411", model: "CCM v2.9.3", trigger: "scheduled", status: "succeeded", startedAt: "09 Sep 2026, 05:40", duration: "4m 12s", triggeredBy: "Scheduler" },
  { id: "run-2410", model: "CCM v2.9.3", trigger: "manual", status: "succeeded", startedAt: "08 Sep 2026, 21:15", duration: "4m 31s", triggeredBy: "m.saleheen" },
  { id: "run-2409", model: "CCM v2.9.3", trigger: "scheduled", status: "succeeded", startedAt: "08 Sep 2026, 17:40", duration: "3m 58s", triggeredBy: "Scheduler" },
  { id: "run-2408", model: "CCM v2.9.3", trigger: "scheduled", status: "failed", startedAt: "08 Sep 2026, 11:40", duration: "0m 22s", triggeredBy: "Scheduler" },
];

export type CrisisEvent = {
  id: string;
  title: string;
  hazard: string;
  location: string;
  reportedAt: string;
  status: "pending" | "validated" | "rejected";
  source: string;
};

export const CRISIS_EVENTS: CrisisEvent[] = [
  { id: "cr-88", title: "Embankment breach reported near Chilmari", hazard: "Flood", location: "Kurigram", reportedAt: "09 Sep 2026, 07:20", status: "pending", source: "News scrape" },
  { id: "cr-87", title: "Riverine flooding displaces households in Islampur", hazard: "Flood", location: "Jamalpur", reportedAt: "09 Sep 2026, 06:05", status: "validated", source: "News scrape" },
  { id: "cr-86", title: "Heavy rainfall warning issued for northern districts", hazard: "Heavy rain", location: "Rangpur division", reportedAt: "08 Sep 2026, 20:40", status: "validated", source: "BMD bulletin" },
  { id: "cr-85", title: "Local road submerged, market access disrupted", hazard: "Flood", location: "Gaibandha", reportedAt: "08 Sep 2026, 15:10", status: "pending", source: "News scrape" },
];

export type Activity = {
  id: string;
  name: string;
  type: "Anticipatory action" | "Response" | "Readiness";
  sector: string;
  district: string;
  status: "planned" | "in_progress" | "completed";
  members: number;
};

export const ACTIVITIES: Activity[] = [
  { id: "act-31", name: "Pre-positioning of dry food, Kurigram", type: "Anticipatory action", sector: "Food security", district: "Kurigram", status: "in_progress", members: 4 },
  { id: "act-30", name: "Early warning dissemination, Jamalpur unions", type: "Anticipatory action", sector: "Early warning", district: "Jamalpur", status: "in_progress", members: 6 },
  { id: "act-29", name: "Cash transfer readiness verification", type: "Readiness", sector: "Multipurpose cash", district: "Gaibandha", status: "planned", members: 3 },
  { id: "act-28", name: "Shelter kit distribution, Sirajganj", type: "Response", sector: "Shelter", district: "Sirajganj", status: "completed", members: 5 },
];
