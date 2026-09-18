import {
  Activity,
  BarChart3,
  Boxes,
  CloudSun,
  Cpu,
  Database,
  FileText,
  LayoutDashboard,
  Radio,
  Settings,
  ShieldAlert,
  Siren,
  Target,
  Users,
  Waves,
  Wind,
  type LucideIcon,
} from "lucide-react";

export type NavChild = {
  label: string;
  to: string;
  /** RFP module number, shown as a quiet tag in the sidebar */
  module?: string;
  icon?: LucideIcon;
  live?: boolean;
};

export type NavItem = {
  label: string;
  to?: string;
  icon: LucideIcon;
  module?: string;
  children?: NavChild[];
};

export type NavSection = {
  heading?: string;
  items: NavItem[];
};

/**
 * Sidebar structure, mapped to the ten RFP modules plus the AI warning layer.
 * "Models" is a group; CCM sits inside it as the first child because it is the
 * only model wired to a live running service.
 */
export const NAV: NavSection[] = [
  {
    items: [{ label: "Dashboard", to: "/", icon: LayoutDashboard }],
  },
  {
    heading: "Situation",
    items: [
      { label: "Crisis Dashboard", to: "/crisis", icon: Siren, module: "6" },
      { label: "Early Warning Signals", to: "/early-warning", icon: ShieldAlert },
      { label: "Pre-crisis Targeting", to: "/pre-crisis", icon: Target, module: "4" },
    ],
  },
  {
    heading: "Models",
    items: [
      {
        label: "Models",
        icon: Cpu,
        children: [
          { label: "CCM — Cyclone Classifier", to: "/models/ccm", module: "5", icon: Waves, live: true },
          { label: "Cyclone Track", to: "/models/cyclone-track", module: "2", icon: Wind },
          { label: "Preparedness Guidance", to: "/models/preparedness", module: "3", icon: Radio, live: true },
          { label: "Flood Risk (DFRM)", to: "/models/flood-risk", module: "7", icon: Waves, live: true },
          { label: "Weather Nowcasting", to: "/models/nowcasting", module: "9", icon: CloudSun },
          { label: "All models & runs", to: "/models", icon: Boxes },
        ],
      },
    ],
  },
  {
    heading: "Programme",
    items: [
      { label: "Activity Tracking", to: "/activities", icon: Activity, module: "8" },
      { label: "Reports & Exports", to: "/reports", icon: FileText },
      { label: "Analytics", to: "/analytics", icon: BarChart3 },
    ],
  },
  {
    heading: "Administration",
    items: [
      { label: "Users & Roles", to: "/admin/users", icon: Users, module: "1" },
      { label: "Legacy Data", to: "/admin/legacy", icon: Database, module: "10" },
      { label: "Settings", to: "/admin/settings", icon: Settings },
    ],
  },
];
