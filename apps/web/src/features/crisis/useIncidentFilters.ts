import { useMemo, useState } from "react";

import type { Incident } from "./mockIncidents";

export type Filters = {
  query: string;
  hazard: string;
  severity: string;
  district: string;
  status: string;
};

export const EMPTY_FILTERS: Filters = {
  query: "",
  hazard: "all",
  severity: "all",
  district: "all",
  status: "all",
};

/**
 * Filtering, plus the aggregates the page's tiles read.
 *
 * The tiles deliberately count the *filtered* set, not the whole feed: if an
 * operator narrows to one district, the headline numbers should describe that
 * district. A tile that silently keeps reporting the national total while the
 * table below it shows one district is how people misread a dashboard.
 */
export function useIncidentFilters(incidents: Incident[]) {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);

  const districts = useMemo(
    () => [...new Set(incidents.map((i) => i.district))].sort(),
    [incidents],
  );

  const filtered = useMemo(() => {
    const query = filters.query.trim().toLowerCase();
    return incidents.filter((incident) => {
      if (filters.hazard !== "all" && incident.hazard !== filters.hazard) return false;
      if (filters.severity !== "all" && incident.severity !== filters.severity) return false;
      if (filters.district !== "all" && incident.district !== filters.district) return false;
      if (filters.status !== "all" && incident.status !== filters.status) return false;
      if (!query) return true;
      return (
        incident.title.toLowerCase().includes(query) ||
        incident.district.toLowerCase().includes(query) ||
        incident.division.toLowerCase().includes(query) ||
        incident.source.toLowerCase().includes(query) ||
        incident.hazard.toLowerCase().includes(query)
      );
    });
  }, [incidents, filters]);

  const totals = useMemo(() => {
    const sum = (pick: (i: Incident) => number) => filtered.reduce((acc, i) => acc + pick(i), 0);
    return {
      incidents: filtered.length,
      deaths: sum((i) => i.deaths),
      injured: sum((i) => i.injured),
      missing: sum((i) => i.missing),
      affected: sum((i) => i.affected),
      displaced: sum((i) => i.displaced),
      housesDamaged: sum((i) => i.housesDamaged),
      districts: new Set(filtered.map((i) => i.district)).size,
      pending: filtered.filter((i) => i.status === "pending").length,
    };
  }, [filtered]);

  return { filters, setFilters, filtered, districts, totals };
}
