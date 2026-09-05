# OpenET 2

OpenET 2 is a modular research toolkit for repeatable remote eye-tracker
collection, validation, benchmarking, visualisation, and longitudinal comparison.
Version 1.6 is the final COMP9900 delivery: it preserves the validated v1.5
implementation, centralises release metadata, and removes duplicate or
machine-specific material.

The production package is `src/openet2`. It extends the supplied OpenET
prototype through the compatibility boundary in `legacy.py`; client source
recordings remain read-only.

## Start here

1. Read this file for installation and the supported workflows.
2. Open `index.html` or `reports/*/report.html` for the bundled evidence.
3. Review `docs/requirements_traceability.md` for the ten project requirements.
4. Use `docs/client_demo_guide.md` and `docs/hardware_validation_checklist.md`
   for the final demonstration and laboratory boundary.
5. Read `CONTRIBUTING.md` and `docs/github_delivery.md` before changing or
   publishing the repository.

## Final delivery layout

```text
OpenET2_v1.6_Final_2026-07-28/
├── src/openet2/       Runtime package: collection, import, QC, metrics, reports
├── tests/             Automated regression and requirement tests
├── docs/              User, developer, architecture, metrics and final-report guides
├── examples/          Safe small input and synthetic three-date workflow
├── reports/           Final client-data and synthetic evidence reports
├── references/        Client brief, research papers and isolated client-delay evidence
├── docker/            Legacy compatibility helper used by collection tests
├── .github/workflows/ GitHub Actions offline Windows validation
├── CONTRIBUTING.md    Jira branch, commit, pull-request and review policy
├── Dockerfile         Portable runtime and test image
├── compose.yaml       Report server, mounted analysis and test services
└── PACKAGE_CONTENTS.md  Included, excluded and validation inventory
```

`outputs/` is deliberately absent from the delivery and ignored by Git. It is
created only when you run a new local or Docker analysis; final evidence is kept
under `reports/`.

## Project-requirement coverage

The implementation covers the supplied client brief: modular extension of
OpenET; structured session, device and metadata management; guided collection;
CSV/TSV/JSON import; automated quality checks; benchmark and repeatability
metrics; per-session and cohort visualisation; long-term comparison; and user,
developer and technical documentation. Each requirement is linked to source
modules and verification in `docs/requirements_traceability.md`.

## Install

```powershell
# Run from the folder containing this README.
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,video]"
.\.venv\Scripts\python.exe -c "from importlib.metadata import version; print(version('openet2'))"
```

The final command should print `1.6.0`. Add the `collection` extra on a
laboratory computer used for live acquisition:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,video,collection]"
```

The core offline pipeline requires no eye-tracker SDK. Live Tobii collection
requires `.[collection]` and the licensed official Tobii Pro SDK.

## Quick start

### Docker

Open the bundled reports without installing Python:

```powershell
docker compose up --build -d report
```

Then open <http://localhost:8080/>. See `docs/docker_guide.md` for mounted
analysis, test execution and external-data configuration.

### Local Python

Run the small example:

```powershell
openet2 run `
  --data-root "examples\example_data" `
  --output-root "outputs\example" `
  --expected-marker-events 2
```

Create and analyse the synthetic three-date workflow:

```powershell
openet2 generate-example --output-root "outputs\synthetic_longitudinal_data"
openet2 run `
  --data-root "outputs\synthetic_longitudinal_data" `
  --output-root "outputs\synthetic_longitudinal_report"
```

Run the supplied client dataset only when its authorised path is available:

```powershell
openet2 run `
  --data-root "<path-to-client-data>" `
  --output-root "outputs\client_benchmark" `
  --recover-targets-from-video `
  --client-delay-evidence "references\client_delay_comparison"
```

The isolated delay bundle reports approximate assumed-FOV degree scores based on
a fixed 60.00 x 33.75 degree display grid. They are not measured visual angles or
pixel distances; the bundled CSV files and `rebuild_figures.py` reproduce all six
focused delay figures with explicit axis labels.

Create a deterministic no-hardware collection session:

```powershell
openet2 collect `
  --legacy-code-root "docker\legacy_code" `
  --output-root "outputs\collection" `
  --subject-id "DEMO01" `
  --device-id "GP3HD" `
  --test-id "Accuracy" `
  --test-condition "standard" `
  --duration-s 30 `
  --display-width-mm 530 `
  --display-height-mm 300 `
  --viewing-distance-mm 600
```

Dry-run is the default. Add `--live` only on a configured laboratory computer,
and use `--calibration-confirmed` only after completing live device calibration.

For a real repeated-measurement study, use the fixed-duration, metadata-complete
protocol in `docs/research_collection_protocol.md`. It adds `--visit-label`,
display/ambient-light fields, calibration-confidence evidence, and an optional
4.2-second target presentation that validates nominal post-settling capacity.
Templates are in `examples/research_session_metadata_template.json` and
`examples/calibration_result.example.json`.

## Outputs and verification

Every run writes CSV/JSON inventories, quality and benchmark metrics,
date-level/repeatability summaries, target-level metrics, an HTML report, focused
figures, session reviews, and a portable run manifest beneath the selected output
directory. Each standardised session also records its shared relative-time origin
in `time_alignment.json`; the run manifest records Python and direct-dependency
versions. See `docs/metrics.md` for definitions.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider
```

The full workspace suite processes the authorised client dataset and passes 27
tests. In a standalone delivery without client data, the read-only client-data
test skips and all offline tests still pass.

## Evidence boundary

The bundled client-data report contains derived, auditable evidence only; raw
recordings and AVI files are excluded. The synthetic workflow demonstrates
software behaviour, not device performance. GP3/Tobii hardware, monitor
selection, achieved frame rate and physical timing remain subject to the signed
laboratory checklist. Pygame flip-return times are application-level evidence,
not measurements of physical pixel onset.
