import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Waves } from "lucide-react";

import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { AreaTree, DFRMLevel, LayerChoice, WLKind } from "@/lib/dfrmApi";

const LAYERS: LayerChoice[] = ["Inundation", "Hazard", "Risk", "Vulnerability", "Warning"];

export type SubmitMeta = {
  level: DFRMLevel;
  layer: LayerChoice;
  area_id: string;
  area_name: string;
  river: string;
  station: string;
  danger_level: number;
  water_level: number;
  wl_kind: WLKind;
  limb: string;
  date: string | null;
};

export function ControlPanel({
  tree,
  onSubmit,
  onClear,
  pending,
}: {
  tree: AreaTree;
  onSubmit: (meta: SubmitMeta) => void;
  onClear: () => void;
  pending: boolean;
}) {
  const [layer, setLayer] = useState<LayerChoice>("Inundation");
  const [level, setLevel] = useState<DFRMLevel>("Union");
  const [distId, setDistId] = useState(tree.districts[0]?.id ?? "");
  const [thanaId, setThanaId] = useState("");
  const [uniId, setUniId] = useState("");
  const [villId, setVillId] = useState("");
  const [wlKind, setWlKind] = useState<WLKind>("WL");
  const [waterLevel, setWaterLevel] = useState("");
  const [limb, setLimb] = useState(tree.limbs[0] ?? "Flood Increasing");
  const [date, setDate] = useState("");

  // Warning is the only layer that maps at the village level.
  const levels: DFRMLevel[] =
    layer === "Warning" ? ["District", "Upazilla", "Union", "Village"] : ["District", "Upazilla", "Union"];

  useEffect(() => {
    if (!levels.includes(level)) setLevel("Union");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layer]);

  const district = useMemo(() => tree.districts.find((d) => d.id === distId), [tree, distId]);
  const upazila = useMemo(() => district?.upazilas.find((u) => u.id === thanaId), [district, thanaId]);
  const union = useMemo(() => upazila?.unions.find((u) => u.id === uniId), [upazila, uniId]);
  const village = useMemo(() => union?.villages.find((v) => v.id === villId), [union, villId]);

  // Keep the cascade consistent: when a parent changes, default its children.
  useEffect(() => {
    const first = district?.upazilas[0];
    setThanaId(first?.id ?? "");
  }, [district]);
  useEffect(() => {
    setUniId(upazila?.unions[0]?.id ?? "");
  }, [upazila]);
  useEffect(() => {
    setVillId(union?.villages[0]?.id ?? "");
  }, [union]);

  // Which river gauges the current selection (drives station + danger level).
  const river = useMemo(() => {
    if (level === "Village") return village?.river ?? "Jamuna";
    if (level === "Union") return union?.river ?? "Jamuna";
    return "Jamuna";
  }, [level, union, village]);
  const station = tree.stations[river] ?? tree.stations["Jamuna"];

  const areaId =
    level === "District" ? distId : level === "Upazilla" ? thanaId : level === "Union" ? uniId : villId;
  const areaName =
    level === "District"
      ? district?.name
      : level === "Upazilla"
        ? upazila?.name
        : level === "Union"
          ? union?.name
          : village?.name;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const wl = Number(waterLevel);
    if (!areaId || !Number.isFinite(wl)) return;
    onSubmit({
      level,
      layer,
      area_id: areaId,
      area_name: areaName ?? areaId,
      river,
      station: station.station,
      danger_level: station.danger_level,
      water_level: wl,
      wl_kind: wlKind,
      limb,
      date: date || null,
    });
  };

  const segment = (active: boolean) =>
    cn(
      "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
      active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground",
    );

  return (
    <Card title="Flood risk query" subtitle="Pick an area and a forecast water level" bodyClassName="space-y-4">
      <form onSubmit={submit} className="space-y-4">
        {/* layer choice */}
        <div>
          <span className="text-sm font-medium text-foreground">Layer</span>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {LAYERS.map((l) => (
              <button type="button" key={l} onClick={() => setLayer(l)} className={segment(layer === l)}>
                {l}
              </button>
            ))}
          </div>
        </div>

        {/* administrative level */}
        <label className="block">
          <span className="text-sm font-medium text-foreground">Map level</span>
          <div className="mt-1.5 flex gap-1.5">
            {levels.map((l) => (
              <button type="button" key={l} onClick={() => setLevel(l)} className={cn("flex-1", segment(level === l))}>
                {l}
              </button>
            ))}
          </div>
        </label>

        {/* cascade */}
        <ComboField label="District" value={distId} onChange={setDistId}
          options={tree.districts.map((d) => ({ value: d.id, label: d.name }))} />

        {level !== "District" && (
          <ComboField label="Upazila" value={thanaId} onChange={setThanaId}
            options={(district?.upazilas ?? []).map((u) => ({ value: u.id, label: u.name }))} />
        )}
        {(level === "Union" || level === "Village") && (
          <ComboField label="Union" value={uniId} onChange={setUniId}
            options={(upazila?.unions ?? []).map((u) => ({ value: u.id, label: u.name }))} />
        )}
        {level === "Village" && (
          <ComboField label="Village" value={villId} onChange={setVillId}
            options={(union?.villages ?? []).map((v) => ({ value: v.id, label: v.name }))} />
        )}

        {/* water level */}
        <div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-foreground">
              {wlKind === "WL" ? "Water level (m)" : "Level above danger (m)"}
            </span>
            <div className="flex gap-1">
              {(["WL", "DL"] as const).map((k) => (
                <button type="button" key={k} onClick={() => setWlKind(k)} className={segment(wlKind === k)}>
                  {k}
                </button>
              ))}
            </div>
          </div>
          <Input
            className="mt-1.5"
            type="number"
            step="0.01"
            inputMode="decimal"
            placeholder={wlKind === "WL" ? `e.g. ${station.danger_level}` : "e.g. 0.5"}
            value={waterLevel}
            onChange={(e) => setWaterLevel(e.target.value)}
          />
          <p className="mt-1 text-[11px] text-muted-foreground">
            {station.station} · danger level {station.danger_level} m
          </p>
        </div>

        {/* flood condition + date */}
        <ComboField label="Flood condition" value={limb} onChange={setLimb}
          options={tree.limbs.map((l) => ({ value: l, label: l }))} />

        <label className="block">
          <span className="text-sm font-medium text-foreground">Date of warning</span>
          <Input className="mt-1.5" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>

        <div className="flex gap-2">
          <Button type="submit" disabled={pending || !areaId || waterLevel === ""} className="flex-1">
            <Waves />
            {pending ? "Working…" : layer === "Warning" ? "Get warning" : "Show map"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setWaterLevel("");
              setDate("");
              onClear();
            }}
          >
            Clear
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ComboField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="mt-1.5">
          <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}
