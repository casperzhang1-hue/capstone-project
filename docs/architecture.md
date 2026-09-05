# OpenET 2 architecture

## Package boundaries

```text
client OpenET source (unchanged)
  create_data_folder.py   GP3_helpers.py   tobii_helpers.py
             |                  |
             +-------- openet2.legacy --------+
                                                |
protocol/config -> openet2.collection -> dated session folders
                                                |
                                                v
metadata discovery -> importer registry -> standard tables
                                                |
                         +------ optional video target recovery ----+
                                                |
                         +----------------------+-------------------+
                         v                      v                   v
                    quality checks        benchmark metrics    session review
                         +----------------------+-------------------+
                                                v
                             combined + long-term + repeatability
                                                v
                                  figures + HTML + manifest
```

- `legacy.py` is the only boundary allowed to load supplied client modules.
- `collection.py` owns lifecycle, metadata, timing, cleanup, stimulus, and video.
- `metadata.py` keeps legacy two-column CSV authoritative, adds optional rich
  JSON fields, and records duplicate-field conflicts or unreadable JSON.
- `importers.py` owns vendor-to-standard conversion and importer registration.
- `video_targets.py` owns optional, strictly validated legacy AVI target
  recovery and interval/frame audit evidence.
- `analysis.py` contains deterministic quality and metric definitions.
- `reporting.py` contains non-interactive plots and the static HTML report.
- `pipeline.py` coordinates batches and isolates per-session failures.
- `cli.py` exposes collection and analysis without hard-coded laboratory paths.

## Standard tables

`standard_gaze.csv` keeps relative time, optional device/system times, combined
and per-eye gaze, validity, pupil fields, raw coordinates, device, and coordinate
space. `standard_marker_events.csv` records interval, target ID, target position,
coordinate space, duration, and optional video-recovery provenance.
`standard_video_timestamps.csv` aligns frame ID with relative recording time.
`time_alignment.json` records the shared epoch origin, transformed columns and
relative-seconds basis without modifying any source file.

## Extension rules

Register a new gaze importer with `register_gaze_importer`. It must return every
column in `STANDARD_GAZE_COLUMNS`, use seconds for time, and state its coordinate
space. New live devices implement the same start/read/stop lifecycle as the GP3
and Tobii adapters. New metrics consume standard tables, not vendor columns.

## Safety and reproducibility

- Source recordings are never modified.
- Hardware imports are lazy, so offline analysis works without lab SDKs.
- Device shutdown is executed in `finally` blocks.
- Every run records thresholds, logical paths, duration, version, Python and
  direct-dependency versions, and mutation policy in `run_manifest.json`.
- Unknown or unavailable measurements remain blank/NaN; they are not inferred.
