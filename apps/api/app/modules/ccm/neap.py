"""NEAP risk-impact classification — the lead-time half of the CCM.

The model's per-union output says how hard a cyclone hits a place. It does not
say how bad that is *given how much warning there was*, and that is the number
the National Early Action Protocol acts on: the same 222 km/hr wind is a 16
with no notice and an 8 with five days' notice, because five days is enough to
evacuate.

CCM_Main.py holds three lookup matrices for this (Base_info/NEAP.xlsx, sheets
Wind_Speed / Storm_Surge / Rain) and applies them when the operator types a
lead time into the desktop tool:

    neap.loc[neap.index <= t, neap.columns <= value].iloc[-1, -1]

— the last row whose lead time is at or below t, and within it the last column
whose threshold is at or below the hazard value. The portal has to produce the
same four columns the desktop tool does: the lead time itself, and the impact
number for wind, storm surge and rainfall ("W / St.Su / RF").

The matrices are copied here rather than read from the workbook. They are
twenty numbers each, they are a published protocol rather than model output,
and embedding them means the API does not need the CCM data volume mounted to
answer a results query. If NEAP.xlsx is ever revised, these change with it —
the sheet remains the source of record.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The value a row gets when the hazard is below every threshold: no impact.
_BASELINE = 0


@dataclass(frozen=True)
class NeapTable:
    """One hazard's lead-time × intensity matrix.

    `lead_times` and `thresholds` are both ascending. `grid[i][j]` is the
    impact number for lead time `lead_times[i]` and intensity at or above
    `thresholds[j]`. The first threshold is -1, i.e. "any value at all",
    which is how the workbook encodes the no-impact column.
    """

    lead_times: tuple[int, ...]
    thresholds: tuple[float, ...]
    grid: tuple[tuple[int, ...], ...]

    def classify(self, value: float | None, lead_time_hours: int) -> int | None:
        if value is None:
            return None

        row = 0
        for i, t in enumerate(self.lead_times):
            if t <= lead_time_hours:
                row = i
            else:
                break

        col = 0
        for j, threshold in enumerate(self.thresholds):
            if threshold <= value:
                col = j
            else:
                break

        return self.grid[row][col]


# Base_info/NEAP.xlsx, sheet Wind_Speed — thresholds in km/hr.
WIND = NeapTable(
    lead_times=(0, 48, 72, 120),
    thresholds=(-1, 62, 89, 118, 222),
    grid=(
        (0, 6, 10, 14, 16),
        (0, 5, 9, 13, 15),
        (0, 2, 4, 11, 12),
        (0, 1, 3, 7, 8),
    ),
)

# Base_info/NEAP.xlsx, sheet Storm_Surge — thresholds in metres.
SURGE = NeapTable(
    lead_times=(0, 48, 72, 120),
    thresholds=(-1, 0.001, 1.5, 3.6, 5),
    grid=(
        (0, 4, 10, 14, 16),
        (0, 3, 9, 13, 15),
        (0, 2, 8, 11, 12),
        (0, 1, 5, 6, 7),
    ),
)

# Base_info/NEAP.xlsx, sheet Rain — thresholds in mm over 72 hours.
RAIN = NeapTable(
    lead_times=(0, 72, 120, 168),
    thresholds=(-1, 0.001, 150, 200, 250),
    grid=(
        (0, 7, 12, 14, 16),
        (0, 6, 10, 13, 15),
        (0, 2, 8, 9, 11),
        (0, 1, 2, 4, 5),
    ),
)

#: What the desktop tool puts in its lead-time box when left empty.
DEFAULT_LEAD_TIME_HOURS = 120

#: The longest lead time any matrix knows about. Beyond this the last row
#: applies, which is correct — more warning than the protocol plans for cannot
#: make the impact worse.
MAX_LEAD_TIME_HOURS = 168

#: Added to every result row, in this order, when a lead time is in play.
FIELDS: tuple[str, ...] = (
    "lead_time_hours",
    "neap_wind",
    "neap_surge",
    "neap_rain",
)


def annotate(row: dict, lead_time_hours: int) -> dict:
    """Add the lead time and the three impact numbers to one result row.

    Mutates and returns `row`, so it can be mapped over a result page. Rows
    above union level carry aggregated hazard values; classifying those is the
    same lookup, and gives the impact number for the worst-case intensity in
    the group, which is what an operator reading a district row wants.
    """
    row["lead_time_hours"] = lead_time_hours
    row["neap_wind"] = WIND.classify(row.get("wind_speed_kmh"), lead_time_hours)
    row["neap_surge"] = SURGE.classify(row.get("surge_height_m"), lead_time_hours)
    row["neap_rain"] = RAIN.classify(row.get("rainfall_72h_mm"), lead_time_hours)
    return row


def clamp_lead_time(hours: int | None) -> int:
    """Keep an operator-supplied lead time inside what the matrices cover."""
    if hours is None:
        return DEFAULT_LEAD_TIME_HOURS
    return max(0, min(int(hours), MAX_LEAD_TIME_HOURS))
