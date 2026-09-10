# data/

Large source data that is **not** kept in git — model packages, boundary files,
raster inputs. Everything here is ignored except this README.

## CCM v2.9.3 cyclone database

The CCM importer reads the model package's own data folder. Copy it here:

```
data/
└── ccm/
    └── CycloneDataBase/        ← copied from the CCM v2.9.3 package
        ├── Cyclone_List.csv
        ├── Cyclone_Info/       (19 result tables, one per cyclone)
        ├── Cyclone_Track/      (track shapefiles)
        └── Shapefiles/         (CCM_Unions_wgs84.* — the union boundaries)
```

You do not need `CCM.exe` here. The portal reads the results the model produced;
it does not run the model.

Then, from the project root:

```bash
docker compose exec api python -m scripts.import_ccm
```

This loads 1,585 union boundaries and ~29,900 result rows across 19 cyclones.
It is safe to re-run — existing rows are replaced, not duplicated.

### Adding a cyclone later

When a new cyclone is run and its result table is produced, drop the CSV into
`Cyclone_Info/`, add a row to `Cyclone_List.csv`, and import just that one:

```bash
docker compose exec api python -m scripts.import_ccm --only <FileStem> --source upload
```

It then appears in the portal beside the cyclones that shipped with the package.
