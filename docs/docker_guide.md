# Docker guide

The `OpenET2_v1.6_Final_2026-07-28` folder is a self-contained Docker delivery.
It includes runtime source, final reports, examples, tests, `Dockerfile` and
`compose.yaml`. Docker Desktop (Windows/macOS) or Docker Engine with Compose
(Linux) is the only host prerequisite.

## Open final reports

Run this command from the folder containing `compose.yaml`:

```powershell
docker compose up --build -d report
```

Open <http://localhost:8080/>. Stop the service with:

```powershell
docker compose down
```

Set `OPENET2_REPORT_PORT` before starting if port 8080 is occupied.

## Run the synthetic analysis

The default analysis mounts the included synthetic dataset read-only and writes
new derived files to the ignored `outputs/` folder:

```console
docker compose --profile analysis run --rm analysis run --data-root /data --output-root /output
```

With the report service running, open
<http://localhost:8080/outputs/report.html> to inspect that new run.

## Analyse another dataset

Copy `.env.example` to `.env`, then set `OPENET2_DATA_ROOT` to the authorised
host path and optionally change `OPENET2_OUTPUT_ROOT`. The default output is
`./outputs`, keeping generated files outside the final evidence folders.

```console
docker compose --profile analysis run --rm analysis run --data-root /data --output-root /output --recover-targets-from-video
```

The input mount is read-only; only the selected output directory is writable.
Generated inventories use paths relative to the input root, and manifests use
`openet2://input` and `openet2://output` logical roots for portability.

## Run tests

```powershell
docker compose --profile test run --rm test
```

The containerised suite passes all offline tests. The authorised client dataset
is deliberately absent from this final package, so its availability test skips.

## Boundary

Docker supports offline import, video target recovery, quality checks, metrics,
figures, reports and synthetic dry-run evidence. Live GP3/Tobii acquisition is
not portable through the image because vendor SDKs, host displays, cameras and
device permissions need laboratory-specific configuration.