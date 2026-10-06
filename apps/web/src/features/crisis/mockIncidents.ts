/**
 * Demonstration data for the Crisis Dashboard.
 *
 * Module 6 collects incident reports by scraping news and bulletins twice
 * daily; a Hub administrator validates each one before it informs decisions.
 * The pipeline is not connected yet, so this file stands in for it. The shape
 * here is the shape the real feed is expected to deliver — when the collector
 * lands, this file is deleted and the types move to `lib/crisisApi.ts`.
 *
 * Severity uses the portal's own five-level scale (see SeverityBadge), not the
 * taxonomy of any particular upstream source: whatever a source calls a
 * "major" or "critical" event, it is mapped onto this scale on the way in, so
 * one dashboard never mixes two vocabularies.
 */
import type { Severity } from "@/components/shared/SeverityBadge";

export const HAZARD_TYPES = [
  "Flood",
  "Cyclone",
  "Heavy rain",
  "Landslide",
  "River erosion",
  "Lightning",
  "Tidal surge",
  "Heatwave",
] as const;
export type HazardType = (typeof HAZARD_TYPES)[number];

export type VerificationStatus = "pending" | "validated" | "rejected";

export type Incident = {
  id: string;
  title: string;
  summary: string;
  hazard: HazardType;
  severity: Severity;
  district: string;
  division: string;
  /** [lat, lng] — where the incident was reported. */
  coords: [number, number];
  /** ISO timestamp, so the UI can compute "2h ago" rather than storing it. */
  reportedAt: string;
  status: VerificationStatus;
  source: string;
  deaths: number;
  injured: number;
  missing: number;
  affected: number;
  displaced: number;
  housesDamaged: number;
};

/** "2026-10-02T06:20:00+06:00" relative to the dashboard's "now". */
const NOW = new Date("2026-10-02T14:00:00+06:00");
const hoursAgo = (h: number) => new Date(NOW.getTime() - h * 3_600_000).toISOString();

export const INCIDENTS: Incident[] = [
  {
    id: "INC-2026-0412",
    title: "Embankment breach floods eight villages in Chilmari",
    summary:
      "A 60-metre section of the Brahmaputra right-bank embankment gave way overnight. Water entered eight villages in Chilmari upazila; the union parishad has opened three shelters.",
    hazard: "Flood",
    severity: "extreme",
    district: "Kurigram",
    division: "Rangpur",
    coords: [25.5553, 89.6726],
    reportedAt: hoursAgo(2),
    status: "pending",
    source: "News scrape — Prothom Alo",
    deaths: 3,
    injured: 11,
    missing: 2,
    affected: 24_500,
    displaced: 4_200,
    housesDamaged: 860,
  },
  {
    id: "INC-2026-0411",
    title: "Riverine flooding displaces households across Islampur",
    summary:
      "Jamuna water level has stayed above danger level for a third day. Low-lying wards of Islampur and Dewanganj are inundated; livestock losses reported.",
    hazard: "Flood",
    severity: "severe",
    district: "Jamalpur",
    division: "Mymensingh",
    coords: [25.0203, 89.8977],
    reportedAt: hoursAgo(5),
    status: "validated",
    source: "News scrape — Daily Star",
    deaths: 1,
    injured: 4,
    missing: 0,
    affected: 16_800,
    displaced: 2_900,
    housesDamaged: 430,
  },
  {
    id: "INC-2026-0410",
    title: "Landslide blocks Chattogram–Rangamati road at Sapchhari",
    summary:
      "Continuous rainfall triggered a hillside collapse on the Chattogram–Rangamati highway. The road is closed to traffic in both directions; clearing is under way.",
    hazard: "Landslide",
    severity: "severe",
    district: "Rangamati",
    division: "Chattogram",
    coords: [22.6533, 92.1735],
    reportedAt: hoursAgo(9),
    status: "pending",
    source: "Field report — ESDO",
    deaths: 2,
    injured: 6,
    missing: 1,
    affected: 1_200,
    displaced: 310,
    housesDamaged: 48,
  },
  {
    id: "INC-2026-0409",
    title: "Heavy rainfall warning issued for northern districts",
    summary:
      "BMD has forecast 120–160 mm in 24 hours across Rangpur and Rajshahi divisions, with a risk of flash flooding in the Teesta and Dharla basins.",
    hazard: "Heavy rain",
    severity: "moderate",
    district: "Rangpur",
    division: "Rangpur",
    coords: [25.7439, 89.2752],
    reportedAt: hoursAgo(14),
    status: "validated",
    source: "BMD bulletin",
    deaths: 0,
    injured: 0,
    missing: 0,
    affected: 0,
    displaced: 0,
    housesDamaged: 0,
  },
  {
    id: "INC-2026-0408",
    title: "River erosion takes 40 homesteads at Naria",
    summary:
      "Padma erosion has accelerated this week. Forty homesteads and a community clinic have been lost at Naria; families are sheltering with relatives.",
    hazard: "River erosion",
    severity: "severe",
    district: "Shariatpur",
    division: "Dhaka",
    coords: [23.2894, 90.4958],
    reportedAt: hoursAgo(20),
    status: "validated",
    source: "News scrape — Bangla Tribune",
    deaths: 0,
    injured: 0,
    missing: 0,
    affected: 2_100,
    displaced: 640,
    housesDamaged: 40,
  },
  {
    id: "INC-2026-0407",
    title: "Lightning strikes kill four farm workers in Sunamganj",
    summary:
      "Four agricultural workers died in separate lightning strikes during the afternoon thunderstorm across Dharmapasha and Tahirpur upazilas.",
    hazard: "Lightning",
    severity: "moderate",
    district: "Sunamganj",
    division: "Sylhet",
    coords: [25.0658, 91.395],
    reportedAt: hoursAgo(27),
    status: "validated",
    source: "News scrape — Samakal",
    deaths: 4,
    injured: 2,
    missing: 0,
    affected: 0,
    displaced: 0,
    housesDamaged: 0,
  },
  {
    id: "INC-2026-0406",
    title: "Tidal surge overtops polder 32 at Dacope",
    summary:
      "A spring tide combined with onshore wind overtopped a weakened section of polder 32. Saline water has entered shrimp enclosures and two villages.",
    hazard: "Tidal surge",
    severity: "severe",
    district: "Khulna",
    division: "Khulna",
    coords: [22.5708, 89.5103],
    reportedAt: hoursAgo(33),
    status: "pending",
    source: "Field report — Hub volunteer",
    deaths: 0,
    injured: 3,
    missing: 0,
    affected: 5_400,
    displaced: 980,
    housesDamaged: 210,
  },
  {
    id: "INC-2026-0405",
    title: "Flash flood damages Haor crop land in Netrakona",
    summary:
      "Upstream rainfall sent a flash flood through the Khaliajuri haor. Standing boro seedbeds have been submerged; extent is still being assessed.",
    hazard: "Flood",
    severity: "moderate",
    district: "Netrakona",
    division: "Mymensingh",
    coords: [24.8103, 90.8706],
    reportedAt: hoursAgo(41),
    status: "validated",
    source: "News scrape — Ittefaq",
    deaths: 0,
    injured: 0,
    missing: 0,
    affected: 7_300,
    displaced: 120,
    housesDamaged: 35,
  },
  {
    id: "INC-2026-0404",
    title: "Unconfirmed report of boat capsize near Bhola",
    summary:
      "Social media reports of a passenger boat capsizing in the Meghna near Bhola Sadar. No corroborating source found; coastguard contacted for confirmation.",
    hazard: "Cyclone",
    severity: "advisory",
    district: "Bhola",
    division: "Barishal",
    coords: [22.6859, 90.6482],
    reportedAt: hoursAgo(48),
    status: "rejected",
    source: "Social media monitor",
    deaths: 0,
    injured: 0,
    missing: 0,
    affected: 0,
    displaced: 0,
    housesDamaged: 0,
  },
  {
    id: "INC-2026-0403",
    title: "Heatwave advisory for south-western districts",
    summary:
      "Daytime maxima of 38–40 °C forecast for Jashore, Chuadanga and Kushtia over the next three days, with elevated risk for outdoor workers.",
    hazard: "Heatwave",
    severity: "advisory",
    district: "Jashore",
    division: "Khulna",
    coords: [23.1664, 89.2081],
    reportedAt: hoursAgo(56),
    status: "validated",
    source: "BMD bulletin",
    deaths: 0,
    injured: 0,
    missing: 0,
    affected: 0,
    displaced: 0,
    housesDamaged: 0,
  },
  {
    id: "INC-2026-0402",
    title: "Waterlogging disrupts market access in Gaibandha",
    summary:
      "Three days of rain have left the Fulchhari growth centre road under water, cutting market access for roughly 20 villages.",
    hazard: "Flood",
    severity: "moderate",
    district: "Gaibandha",
    division: "Rangpur",
    coords: [25.3288, 89.5281],
    reportedAt: hoursAgo(63),
    status: "validated",
    source: "News scrape — Jugantor",
    deaths: 0,
    injured: 0,
    missing: 0,
    affected: 9_100,
    displaced: 0,
    housesDamaged: 12,
  },
  {
    id: "INC-2026-0401",
    title: "Hailstorm damages standing crops in Dinajpur",
    summary:
      "A short, intense hailstorm flattened vegetable plots across four unions of Birampur upazila. Agriculture extension is assessing the loss.",
    hazard: "Heavy rain",
    severity: "moderate",
    district: "Dinajpur",
    division: "Rangpur",
    coords: [25.6217, 88.6354],
    reportedAt: hoursAgo(70),
    status: "pending",
    source: "Field report — DAE",
    deaths: 0,
    injured: 1,
    missing: 0,
    affected: 3_400,
    displaced: 0,
    housesDamaged: 0,
  },
];

/** The twice-daily collector's last completed pass. */
export const LAST_COLLECTION = hoursAgo(2);
