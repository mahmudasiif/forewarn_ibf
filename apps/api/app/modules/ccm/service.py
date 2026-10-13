"""CCM business logic.

Everything here reads the results that CCM v2.9.3 produced. The portal does not
recompute anything — it stores, filters, aggregates and serves the model's own
output. Rows arrive either from the shipped cyclone database or from a result
file uploaded later through the portal.
"""
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.ccm import metrics as metric_registry
from app.modules.ccm import neap
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

#: The metric a return-period threshold is expressed against. The desktop tool
#: offers "Return Period in Years" only under the affected-people trigger,
#: because the per-union Avg/Std it needs describe that one quantity.
RETURN_PERIOD_METRIC = "affected_people"


def gumbel_reduced_variate(return_period_years: float) -> float:
    """The Gumbel reduced variate for a T-year event, as CCM_Main.py computes it.

    Extreme values — the worst flood in T years, the worst wind — follow a
    Gumbel distribution rather than a normal one, and this is the standard
    Weibull-plotting-position approximation of its quantile:

        zt = ((1 - 1/T)**0.135 - (1/T)**0.135) / 0.1975

    Paired with the union's own log-mean and log-sd it gives that union's
    expected T-year affected-people count. T must be above 1: a return period
    of one year or less is every year, which the distribution has no quantile
    for.
    """
    if return_period_years <= 1:
        raise ValueError("Return period must be greater than 1 year.")
    p = 1.0 / return_period_years
    return ((1 - p) ** 0.135 - p**0.135) / 0.1975


def _return_period_clause(params: dict[str, Any], years: float) -> str:
    """A WHERE fragment keeping unions this cyclone hits harder than their T-year event.

    Applied to the union rows *before* any roll-up, which is the only reading
    that makes sense: the question is which places are having an exceptional
    event, and a district is not a place with its own return period.
    """
    params["rp_zt"] = gumbel_reduced_variate(years)
    return (
        f"r.{RETURN_PERIOD_METRIC} IS NOT NULL"
        " AND u.ln_affected_avg IS NOT NULL AND u.ln_affected_std IS NOT NULL"
        f" AND r.{RETURN_PERIOD_METRIC} >= EXP(u.ln_affected_avg + :rp_zt * u.ln_affected_std)"
    )


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
    threshold_mode: str = "value",
    lead_time_hours: int | None = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    """The results table, at the requested administrative level.

    `threshold_mode` picks how `threshold` is read. "value" compares the
    trigger metric against it directly. "return_period" reads it as a number
    of years and keeps only the unions where this cyclone beats their own
    T-year event — see `_return_period_clause`.

    `lead_time_hours` adds the NEAP impact numbers to every row, the same four
    columns the desktop tool appends once a lead time is entered.
    """
    cyclone = await get_cyclone(db, code)
    chosen = metric_registry.resolve(metric)
    lead_time = neap.clamp_lead_time(lead_time_hours)

    params: dict[str, Any] = {
        "cyclone_id": cyclone["id"],
        "division": division,
        "district": district,
        "upazila": upazila,
    }
    group_columns = _LEVEL_COLUMNS[level]
    id_select = ", ".join(f"r.{c}" for c in group_columns)
    group_by = "" if level == "union" else f"GROUP BY {', '.join(f'r.{c}' for c in group_columns)}"

    # A return-period threshold is per union and so has to be applied to the
    # raw rows, before any roll-up; an ordinary threshold is applied to what
    # the operator is actually looking at, so it runs after.
    row_where = _filters(params)
    having = ""
    if threshold_mode == "return_period":
        # A period of a year or less has no quantile, so there is nothing to
        # compare against and nothing is filtered. Falling through to the flat
        # comparison instead would silently read "1" as "one person affected".
        if threshold is not None and threshold > 1:
            row_where += " AND " + _return_period_clause(params, float(threshold))
    elif threshold is not None and operator in _OPERATOR_SQL:
        having = f"WHERE agg.{chosen.key} {_OPERATOR_SQL[operator]} :threshold"
        params["threshold"] = threshold

    base = f"""
        SELECT {id_select}, {_metric_select_sql(level)}
        FROM ccm.results r
        LEFT JOIN ccm.unions u ON u.union_geo = r.union_geo
        WHERE {row_where}
        {group_by}
    """

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
        "items": [neap.annotate(dict(r), lead_time) for r in rows.mappings()],
        "total": int(total),
        "page": max(page, 1),
        "size": params["limit"],
        "level": level,
        "lead_time_hours": lead_time,
        "metric": chosen.key,
        "metric_min": float(bounds["lo"]) if bounds and bounds["lo"] is not None else None,
        "metric_max": float(bounds["hi"]) if bounds and bounds["hi"] is not None else None,
    }


async def map_features(
    db: AsyncSession,
    *,
    code: str,
    metric: str | None = None,
    level: AdminLevel = "union",
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    operator: Operator | None = None,
    threshold: float | None = None,
    threshold_mode: str = "value",
    simplify: float = 0.001,
) -> dict:
    """Polygons for the chosen administrative level, with the metric attached.

    The level is the map, not just the table. Asked for districts, this returns
    64-odd district polygons dissolved from their unions and coloured by the
    district's own aggregated figure — not union polygons with a district
    outline drawn over them. Union lines inside a district are not faint detail
    at that level, they are wrong: they invite reading a value off a union when
    the number on screen is the district's.

    Dissolving from the same union polygons the choropleth uses at union level,
    rather than loading separate district shapefiles, is what keeps the levels
    consistent. Two boundary datasets never agree to the metre, and a district
    fill that misses the unions it contains by a few pixels looks like a bug.

    Geometry is simplified server-side — union boundaries at full precision are
    ~40 MB of GeoJSON, which no browser should be asked to swallow.

    The simplification has to be coverage-aware. ST_SimplifyPreserveTopology
    only preserves topology *within* one geometry; run per row, two neighbours
    drop different vertices along the border they share and the map renders a
    thin crack between them along every boundary. ST_CoverageSimplify treats
    the whole result set as one coverage and simplifies each shared edge once,
    so neighbours keep matching borders. It is a window function, hence the
    OVER () — the window is the set of rows this query returns, which is
    exactly the coverage being drawn.

    The third argument, simplifyBoundary, is false: only the *interior* edges
    between neighbouring areas are simplified, and the outer edge of the
    coverage is left at full precision. That outer edge is the coastline, the
    estuary mouths and the char islands — the parts an operator reads the map
    by. Simplifying those too saves little (they are a small share of the
    vertices) and costs a lot: the coast straightens, small islands collapse,
    and the drawn area no longer matches the area the numbers are for. It also
    means the outline stays put as you change the simplify tolerance; only the
    internal borders coarsen.
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
    if threshold_mode == "return_period":
        if threshold is not None and threshold > 1:
            where += " AND " + _return_period_clause(params, float(threshold))
    elif threshold is not None and operator in _OPERATOR_SQL:
        where += f" AND r.{chosen.key} {_OPERATOR_SQL[operator]} :threshold"
        params["threshold"] = threshold

    # The extra metrics ride along so clicking an area can show its headline
    # figures without a second request.
    detail_metrics = (
        "risk_pct", "hazard_pct", "vulnerability_pct",
        "wind_speed_kmh", "surge_height_m", "affected_people",
    )

    if level == "union":
        label_columns = ["division", "district", "upazila", "union_name"]
        value_sql = f"r.{chosen.key} AS value"
        detail_sql = ", ".join(f"r.{m}" for m in detail_metrics)
        geom_source = "u.geom"
        group_by = ""
        id_column = "r.union_geo"
    else:
        label_columns = _LEVEL_COLUMNS[level]
        value_sql = f"{_AGG_SQL[chosen.aggregation]}(r.{chosen.key}) AS value"
        detail_sql = ", ".join(
            f"{_AGG_SQL[metric_registry.METRICS_BY_KEY[m].aggregation]}(r.{m}) AS {m}"
            for m in detail_metrics
        )
        # One polygon per area. ST_UnaryUnion over the collected unions melts
        # the internal lines away, which is the whole point of the level.
        geom_source = "ST_UnaryUnion(ST_Collect(u.geom))"
        group_by = f"GROUP BY {', '.join(f'r.{c}' for c in label_columns)}"
        # The area's full path, not just its own name: there are Sadar upazilas
        # in most districts, so an id of "Sadar" would be several different
        # polygons sharing one feature id. The map's cache key hashes these,
        # and two areas that hash alike keep the previous one's colours.
        id_column = " || ' / ' || ".join(f"r.{c}" for c in label_columns)

    label_sql = ", ".join(f"r.{c}" for c in label_columns)
    geom_sql = (
        "ST_CoverageSimplify(geom, :simplify, false) OVER ()"
        if params["simplify"] > 0
        else "geom"
    )

    rows = await db.execute(
        text(
            f"""
            WITH areas AS (
                SELECT {id_column} AS feature_id, {label_sql},
                       {value_sql}, {detail_sql},
                       {geom_source} AS geom
                FROM ccm.results r
                JOIN ccm.unions u ON u.union_geo = r.union_geo
                WHERE {where}
                {group_by}
            ), simplified AS (
                SELECT feature_id, {label_sql.replace("r.", "")},
                       value, {", ".join(detail_metrics)},
                       {geom_sql} AS geom
                FROM areas r
            )
            SELECT feature_id, {label_sql.replace("r.", "")},
                   value, {", ".join(detail_metrics)},
                   ST_AsGeoJSON(geom, 5) AS geometry
            FROM simplified
            WHERE geom IS NOT NULL
            """
        ),
        params,
    )

    features: list[dict] = []
    lo: float | None = None
    hi: float | None = None
    for row in rows.mappings():
        value = row["value"]
        if value is not None:
            lo = value if lo is None else min(lo, value)
            hi = value if hi is None else max(hi, value)

        properties: dict[str, Any] = {"level": level, "value": value}
        for column in label_columns:
            properties[column] = row[column]
        # Union level keys on Union_Geo; above it, on the area's own name.
        properties["union_geo"] = row["feature_id"] if level == "union" else None
        properties["area_name"] = row[label_columns[-1]]
        for key in detail_metrics:
            properties[key] = row[key]

        features.append(
            {
                "type": "Feature",
                "id": row["feature_id"],
                "geometry": json.loads(row["geometry"]),
                "properties": properties,
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "level": level,
        "metric": chosen.key,
        "metric_label": chosen.label,
        "metric_unit": chosen.unit,
        "metric_min": lo,
        "metric_max": hi,
        "feature_count": len(features),
    }


async def boundaries(
    db: AsyncSession,
    *,
    code: str,
    level: str = "district",
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    simplify: float = 0.002,
) -> dict:
    """District or division outlines, as GeoJSON lines.

    Dissolved from the very same union polygons the choropleth is drawn from,
    rather than loaded from a separate district/division shapefile. Two
    boundary datasets never agree to the metre, and an outline that misses its
    own fill by a few pixels looks like a bug. Dissolving guarantees the line
    sits exactly on the edge of the unions it encloses.

    Returned as boundary lines, not filled polygons, so the layer can sit above
    the choropleth without hiding it.
    """
    cyclone = await get_cyclone(db, code)
    if level not in ("district", "division"):
        raise NotFoundError(f"Unsupported boundary level: {level}")

    params: dict[str, Any] = {
        "cyclone_id": cyclone["id"],
        "division": division,
        "district": district,
        "upazila": upazila,
        "simplify": max(0.0, min(simplify, 0.05)),
    }
    where = _filters(params)

    # Simplify the dissolved coverage, not each outline on its own, so two
    # neighbouring districts keep the single shared line between them — and
    # with simplifyBoundary false, so the coastal edge of the outermost
    # districts still traces the real coast. These lines are drawn directly
    # over the union fill, so if the two were simplified differently the
    # district outline would visibly cut across or float off the polygons
    # underneath it.
    geom_sql = (
        "ST_CoverageSimplify(geom, :simplify, false) OVER ()"
        if params["simplify"] > 0
        else "geom"
    )

    rows = await db.execute(
        text(
            f"""
            WITH merged AS (
                SELECT r.{level} AS name,
                       ST_UnaryUnion(ST_Collect(u.geom)) AS geom
                FROM ccm.results r
                JOIN ccm.unions u ON u.union_geo = r.union_geo
                WHERE {where}
                GROUP BY r.{level}
            ), simplified AS (
                SELECT name, {geom_sql} AS geom FROM merged
            )
            SELECT name, ST_AsGeoJSON(ST_Boundary(geom), 5) AS geometry
            FROM simplified
            WHERE geom IS NOT NULL
            """
        ),
        params,
    )

    features = [
        {
            "type": "Feature",
            "id": row["name"],
            "geometry": json.loads(row["geometry"]),
            "properties": {"name": row["name"], "level": level},
        }
        for row in rows.mappings()
        if row["geometry"]
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "level": level,
        "feature_count": len(features),
    }


async def get_track(db: AsyncSession, code: str) -> dict:
    """The cyclone's track, as a GeoJSON FeatureCollection.

    The CCM package ships one shapefile per cyclone and the desktop tool drew
    it in red over the choropleth. The portal stores it on the cyclone row at
    import time, so the browser gets the line without ever seeing a shapefile.

    A cyclone imported before tracks were loaded has none; that is an empty
    collection rather than a 404, because the map should simply draw no line.
    """
    row = (
        await db.execute(
            text("SELECT track_geojson FROM ccm.cyclones WHERE code = :code"),
            {"code": code},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError(f"No cyclone with code '{code}'.")

    track = row["track_geojson"]
    if not track:
        return {"type": "FeatureCollection", "features": [], "feature_count": 0}

    features = track.get("features", []) if isinstance(track, dict) else []
    return {
        "type": "FeatureCollection",
        "features": features,
        "feature_count": len(features),
    }


async def export_rows(db: AsyncSession, **kwargs: Any) -> dict:
    """Every row the current filters select, for a file download.

    The table in the browser is paged; a download of one page is useless, so
    this re-runs the same query with the page cap lifted. The ceiling is the
    1,585 unions the model reports on, well inside what a single response and
    a spreadsheet can carry.
    """
    kwargs.pop("page", None)
    kwargs.pop("size", None)
    return await results(db, page=1, size=2000, **kwargs)
