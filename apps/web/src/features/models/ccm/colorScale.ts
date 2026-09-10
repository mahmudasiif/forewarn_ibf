/**
 * Choropleth colouring for CCM results.
 *
 * The design guideline is explicit: a choropleth uses the five severity colours
 * and nothing else. So every metric — risk, wind speed, affected people — is
 * bucketed into those same five steps, and the legend always states the numeric
 * range each step covers so the colours stay honest.
 */

export const SCALE_COLORS = [
  "#00A385", // none      — green-700
  "#FD9A00", // advisory  — amber mid
  "#C67C00", // moderate  — amber darkest
  "#FF603A", // severe    — sunrise mid
  "#B93940", // extreme   — sunrise darkest
] as const;

export const NO_DATA_COLOR = "#DDDDE2"; // navy-200

export type Bucket = { from: number; to: number; color: string };

/**
 * Percentage metrics get fixed 0–100 buckets so the same colour always means
 * the same thing across cyclones. Everything else is split into equal
 * intervals across the values actually present.
 */
export function buildBuckets(
  unit: string,
  min: number | null,
  max: number | null,
): Bucket[] {
  if (unit === "%") {
    return SCALE_COLORS.map((color, index) => ({
      from: index * 20,
      to: (index + 1) * 20,
      color,
    }));
  }

  const lo = min ?? 0;
  const hi = max ?? 0;
  if (hi <= lo) {
    return [{ from: lo, to: hi, color: SCALE_COLORS[0] }];
  }

  const step = (hi - lo) / SCALE_COLORS.length;
  return SCALE_COLORS.map((color, index) => ({
    from: lo + step * index,
    to: index === SCALE_COLORS.length - 1 ? hi : lo + step * (index + 1),
    color,
  }));
}

export function colorFor(value: number | null | undefined, buckets: Bucket[]): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NO_DATA_COLOR;
  for (let i = 0; i < buckets.length; i += 1) {
    const bucket = buckets[i];
    const isLast = i === buckets.length - 1;
    if (value >= bucket.from && (isLast ? value <= bucket.to : value < bucket.to)) {
      return bucket.color;
    }
  }
  return value < buckets[0].from ? buckets[0].color : buckets[buckets.length - 1].color;
}

/** Compact number for legends and popups — 1 234, 12.4, 0.08. */
export function formatValue(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  let text: string;
  if (Number.isInteger(value)) text = value.toLocaleString();
  else if (abs >= 1000) text = Math.round(value).toLocaleString();
  else if (abs >= 10) text = value.toFixed(1);
  else if (abs >= 1) text = value.toFixed(2);
  else if (abs === 0) text = "0";
  else text = value.toFixed(3);
  return unit ? `${text} ${unit}` : text;
}
