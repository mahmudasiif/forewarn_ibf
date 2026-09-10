"""CCM business logic.

Everything here reads the results that CCM v2.9.3 produced. The portal does not
recompute anything — it stores, filters, aggregates and serves the model's own
output. Rows arrive either from the shipped cyclone database or from a result
file uploaded later through the portal.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.ccm import metrics as metric_registry
from app.modules.ccm.schemas import AdminLevel, Operator

#: Aggregation function per metric, used when viewing above union level.
_AGG_SQL = {"sum": "SUM", "max": "MAX", "mean": "AVG"}

#: Columns that identify a row at each level, innermost first.
_LEVEL_COLUMNS: dict[str, list[str]] = {
    "division": ["division"],
    "district": ["division", "district"],
    "upazila": ["division", "district", "upazila"],
    "union": ["division", "district", "upazila", "union_name", "union_geo"],
}

_OPERATOR_SQL: dict[str, str] = {
    "gte": ">=",
    "gt": ">",
    "lte": "<=",
    "lt": "<",
    "eq": "=",
}


def _metric_select_sql(level: AdminLevel) -> str:
    """Build the metric part of the SELECT, aggregated when above union level."""
    if level == "union":
        cols = [m.key for m in metric_registry.METRICS]
        cols += [f for f, _ in metric_registry.CONDITION_FIELDS]
        return ", ".join(f"r.{c}" for c in cols)

    parts = []
    for metric in metric_registry.METRICS:
        fn = _AGG_SQL[metric.aggregation]
        parts.append(f"{fn}(r.{metric.key}) AS {metric.key}")
    # Conditions are three-state, so roll them up by precedence rather than as
    # a boolean: damage anywhere makes the group 'Yes'; otherwise 'No' if any
    # child has the asset undamaged; otherwise carry the 'no asset here' text.
    for field, _ in metric_registry.CONDITION_FIELDS:
        parts.append(
            f"""CASE
                WHEN BOOL_OR(r.{field} = 'Yes') THEN 'Yes'
                WHEN BOOL_OR(r.{field} = 'No') THEN 'No'
                ELSE MIN(r.{field})
            END AS {field}"""
        )
    return ", ".join(parts)


def _filters(params: dict[str, Any]) -> str:
    """WHERE clauses shared by the table and map queries."""
    clauses = ["r.cyclone_id = :cyclone_id"]
    for key in ("division", "district", "upazila"):
        if params.get(key):
            clauses.append(f"r.{key} = :{key}")
    return " AND ".join(clauses)


async def list_cyclones(db: AsyncSession) -> list[dict]:
    rows = await db.execute(
        text(
            """
            SELECT c.*, COUNT(r.id) AS union_count
            FROM ccm.cyclones c
            LEFT JOIN ccm.results r ON r.cyclone_id = c.id
            GROUP BY c.id
            ORDER BY c.event_date DESC NULLS LAST, c.name
            """
        )
    )
    return [dict(row) for row in rows.mappings()]


async def get_cyclone(db: AsyncSession, code: str) -> dict:
    row = (
        await db.execute(
            text("SELECT * FROM ccm.cyclones WHERE code = :code"), {"code": code}
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError(f"No cyclone with code '{code}'.")

    cyclone = dict(row)
    totals = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)                              AS union_count,
                       COALESCE(SUM(affected_people), 0)     AS affected_people,
                       COALESCE(SUM(affected_houses), 0)     AS affected_houses,
                       COALESCE(SUM(flooded_area_km2), 0)    AS flooded_area_km2,
                       COALESCE(SUM(house_damage_million_bdt), 0) AS house_damage_million_bdt,
                       COALESCE(MAX(wind_speed_kmh), 0)      AS max_wind_speed_kmh,
                       COALESCE(MAX(surge_height_m), 0)      AS max_surge_height_m,
                       COALESCE(AVG(risk_pct), 0)            AS mean_risk_pct,
                       COUNT(*) FILTER (WHERE risk_pct >= 50) AS unions_risk_50_plus
                FROM ccm.results WHERE cyclone_id = :cid
                """
            ),
            {"cid": cyclone["id"]},
        )
    ).mappings().first()

    cyclone["union_count"] = int(totals["union_count"])
    cyclone["totals"] = {k: float(v) for k, v in dict(totals).items() if k != "union_count"}
    return cyclone


async def locations(
    db: AsyncSession, code: str, level: str, parent: str | None = None
) -> list[dict]:
    """Options for the cascading Division → District → Upazila picker."""
    if level not in ("division", "district", "upazila"):
        return []

    parent_column = {"division": None, "district": "division", "upazila": "district"}[level]
    where = ["c.code = :code"]
    params: dict[str, Any] = {"code": code}
    if parent_column and parent:
        where.append(f"r.{parent_column} = :parent")
        params["parent"] = parent

    parent_select = f"r.{parent_column}" if parent_column else "NULL"
    rows = await db.execute(
        text(
            f"""
            SELECT DISTINCT r.{level} AS value, {parent_select} AS parent
            FROM ccm.results r
            JOIN ccm.cyclones c ON c.id = r.cyclone_id
            WHERE {" AND ".join(where)}
            ORDER BY value
            """
        ),
        params,
    )
    return [{"value": r["value"], "label": r["value"], "parent": r["parent"]} for r in rows.mappings()]


async def results(
    db: AsyncSession,
    *,
    code: str,
    level: AdminLevel = "union",
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    metric: str | None = None,
    operator: Operator | None = None,
    threshold: float | None = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    """The results table, at the requested administrative level."""
    cyclone = await get_cyclone(db, code)
    chosen = metric_registry.resolve(metric)

    params: dict[str, Any] = {
        "cyclone_id": cyclone["id"],
        "division": division,
        "district": district,
        "upazila": upazila,
    }
    group_columns = _LEVEL_COLUMNS[level]
    id_select = ", ".join(f"r.{c}" for c in group_columns)
    group_by = "" if level == "union" else f"GROUP BY {', '.join(f'r.{c}' for c in group_columns)}"

    base = f"""
        SELECT {id_select}, {_metric_select_sql(level)}
        FROM ccm.results r
        WHERE {_filters(params)}
        {group_by}
    """

    having = ""
    if threshold is not None and operator in _OPERATOR_SQL:
        having = f"WHERE agg.{chosen.key} {_OPERATOR_SQL[operator]} :threshold"
        params["threshold"] = threshold

    count_sql = f"SELECT COUNT(*) FROM ({base}) agg {having}"
    total = (await db.execute(text(count_sql), params)).scalar_one()

    bounds = (
        await db.execute(
            text(
                f"SELECT MIN(agg.{chosen.key}) AS lo, MAX(agg.{chosen.key}) AS hi "
                f"FROM ({base}) agg {having}"
            ),
            params,
        )
    ).mappings().first()

    params["limit"] = max(1, min(size, 2000))
    params["offset"] = (max(page, 1) - 1) * params["limit"]
    page_sql = f"""
        SELECT * FROM ({base}) agg
        {having}
        ORDER BY agg.{chosen.key} DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """
    rows = await db.execute(text(page_sql), params)

    return {
        "items": [dict(r) for r in rows.mappings()],
        "total": int(total),
        "page": max(page, 1),
        "size": params["limit"],
        "level": level,
        "metric": chosen.key,
        "metric_min": float(bounds["lo"]) if bounds and bounds["lo"] is not None else None,
        "metric_max": float(bounds["hi"]) if bounds and bounds["hi"] is not None else None,
    }


async def map_features(
    db: AsyncSession,
    *,
    code: str,
    metric: str | None = None,
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    operator: Operator | None = None,
    threshold: float | None = None,
    simplify: float = 0.001,
) -> dict:
    """Union polygons with the selected metric attached, as GeoJSON.

    Geometry is simplified server-side — union boundaries at full precision are
    ~40 MB of GeoJSON, which no browser should be asked to swallow.
    """
    cyclone = await get_cyclone(db, code)
    chosen = metric_registry.resolve(metric)

    params: dict[str, Any] = {
        "cyclone_id": cyclone["id"],
        "division": division,
        "district": district,
        "upazila": upazila,
        "simplify": max(0.0, min(simplify, 0.05)),
    }
    where = _filters(params)
    if threshold is not None and operator in _OPERATOR_SQL:
        where += f" AND r.{chosen.key} {_OPERATOR_SQL[operator]} :threshold"
        params["threshold"] = threshold

    rows = await db.execute(
        text(
            f"""
            SELECT r.union_geo,
                   r.division, r.district, r.upazila, r.union_name,
                   r.{chosen.key} AS value,
                   r.risk_pct, r.hazard_pct, r.vulnerability_pct,
                   r.wind_speed_kmh, r.surge_height_m, r.affected_people,
                   ST_AsGeoJSON(
                       ST_SimplifyPreserveTopology(u.geom, :simplify), 5
                   ) AS geometry
            FROM ccm.results r
            JOIN ccm.unions u ON u.union_geo = r.union_geo
            WHERE {where}
            """
        ),
        params,
    )

    import json

    features: list[dict] = []
    lo: float | None = None
    hi: float | None = None
    for row in rows.mappings():
        value = row["value"]
        if value is not None:
            lo = value if lo is None else min(lo, value)
            hi = value if hi is None else max(hi, value)
        features.append(
            {
                "type": "Feature",
                "id": row["union_geo"],
                "geometry": json.loads(row["geometry"]),
                "properties": {
                    "union_geo": row["union_geo"],
                    "division": row["division"],
                    "district": row["district"],
                    "upazila": row["upazila"],
                    "union_name": row["union_name"],
                    "value": value,
                    "risk_pct": row["risk_pct"],
                    "hazard_pct": row["hazard_pct"],
                    "vulnerability_pct": row["vulnerability_pct"],
                    "wind_speed_kmh": row["wind_speed_kmh"],
                    "surge_height_m": row["surge_height_m"],
                    "affected_people": row["affected_people"],
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "metric": chosen.key,
        "metric_label": chosen.label,
        "metric_unit": chosen.unit,
        "metric_min": lo,
        "metric_max": hi,
        "feature_count": len(features),
    }
