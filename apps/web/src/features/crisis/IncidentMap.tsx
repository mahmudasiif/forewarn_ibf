import { useEffect } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { SEVERITY_HEX, SEVERITY_ORDER, SEVERITY_RADIUS, timeAgo } from "./severity";
import type { Incident } from "./mockIncidents";

/** Bangladesh, framed so the whole country sits in a wide card. */
const CENTER: [number, number] = [23.8, 90.3];
const ZOOM = 6;

const OSM_TILES = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/** Reframes when the filtered set changes, so filtering actually shows you the result. */
function FitToIncidents({ incidents }: { incidents: Incident[] }) {
  const map = useMap();
  const signature = incidents.map((i) => i.id).join(",");

  useEffect(() => {
    if (incidents.length === 0) return;
    const bounds = L.latLngBounds(incidents.map((i) => i.coords));
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 9 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, map]);

  return null;
}

export function IncidentMap({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: Incident[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={CENTER}
        zoom={ZOOM}
        scrollWheelZoom
        className="h-full w-full rounded-b-card"
        style={{ background: "#eff4f7" }}
      >
        <TileLayer url={OSM_TILES} attribution={OSM_ATTRIBUTION} />

        {incidents.map((incident) => {
          const selected = incident.id === selectedId;
          return (
            <CircleMarker
              key={incident.id}
              center={incident.coords}
              radius={SEVERITY_RADIUS[incident.severity] + (selected ? 4 : 0)}
              pathOptions={{
                color: "#ffffff",
                weight: 2,
                fillColor: SEVERITY_HEX[incident.severity],
                fillOpacity: incident.status === "rejected" ? 0.35 : 0.85,
              }}
              eventHandlers={{ click: () => onSelect(incident.id) }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <div style={{ fontFamily: "Roboto, sans-serif", fontSize: 12, lineHeight: 1.5 }}>
                  <strong style={{ color: "#053244" }}>{incident.district}</strong>
                  <br />
                  <span style={{ color: "#55809d" }}>
                    {incident.hazard} · {timeAgo(incident.reportedAt)}
                  </span>
                </div>
              </Tooltip>
            </CircleMarker>
          );
        })}

        <FitToIncidents incidents={incidents} />
      </MapContainer>

      {/* Legend. Severity is ordered, so it is listed most severe first and
          sized as well as coloured — colour alone is never the only cue. */}
      <div className="absolute bottom-4 left-4 z-[500] rounded-card border border-navy-200 bg-white/95 px-3 py-2.5 backdrop-blur">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Severity
        </p>
        <ul className="mt-2 space-y-1.5">
          {SEVERITY_ORDER.filter((level) => level !== "none").map((level) => (
            <li key={level} className="flex items-center gap-2">
              <span
                className="shrink-0 rounded-full border-2 border-white"
                style={{
                  width: SEVERITY_RADIUS[level],
                  height: SEVERITY_RADIUS[level],
                  background: SEVERITY_HEX[level],
                }}
              />
              <span className="text-[11px] capitalize text-navy-700">{level}</span>
            </li>
          ))}
        </ul>
      </div>

      {incidents.length === 0 && (
        <div className="pointer-events-none absolute inset-0 z-[500] flex items-center justify-center bg-navy-50/80">
          <div className="max-w-xs rounded-card border border-navy-200 bg-white px-5 py-4 text-center">
            <p className="text-sm font-medium">No incidents match</p>
            <p className="mt-1 text-xs text-muted-foreground">Widen the filters to see more.</p>
          </div>
        </div>
      )}
    </div>
  );
}
