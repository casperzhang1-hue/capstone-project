# User guide

## 1. Prepare a study

Record a stable participant ID, device ID/model/serial/software version, test
protocol, trial number, condition, nominal sampling rate, calibration method,
display pixel and physical dimensions, viewing distance, environment, and
operator. Avoid names, email addresses, or other direct identifiers.

## 2. Rehearse without hardware

Run `openet2 collect` without `--live`. Confirm that the new session contains
metadata CSV/JSON, calibration and validation summaries, 27 target intervals,
gaze, video timestamps, workflow events, and an application log. Then run
`openet2 run` on its parent data root and open `report.html`.

## 3. Collect in the laboratory

Complete the hardware checklist first. Use `--live`, the real device ID, and
accurate display geometry and pass `--calibration-confirmed` only after the
device calibration has actually completed. When possible, pass
`--calibration-result-json` using the example schema so status, error unit,
valid points and source are auditable. GP3 and Tobii are selected from the device ID. Stop
the process normally; adapters release device resources in `finally` blocks.
After an abnormal stop, retain the session: the `session_failed` event and log
are evidence for quality review.

## 4. Analyse recordings

Point `openet2 run` at a root containing `YYYY_MM_DD/NNN` folders. For the
supplied legacy dataset, install `.[video]` and add
`--recover-targets-from-video`; this reconstructs target identity from the AVI
only when the complete nine-point/three-repeat validation passes. To include the
separate client-delay decision evidence, add
`--client-delay-evidence references/client_delay_comparison`; this reports the
DemoB 50/100/150 ms comparison separately and does not change
`target_settle_time_s`. Review:

1. `summary.json` and `run_manifest.json` for run scope and runtime versions.
2. `quality_report.csv` for failed/warned sessions.
3. Each `session_review.png` for trace, missing periods, targets, and intervals.
4. `benchmark_metrics.csv` for units and missing fields.
5. `long_term_summary.csv` for device trends.
6. `repeatability_summary.csv` for matched participant comparisons.
7. `target_metrics.csv` for each covered marker interval.
8. `target_visit_summary.csv` for participant/session/target observations used
   by the paper-aligned figures, including `paper_qc_*` sample screening and
   `paper_plot_*` nearest-target/outlier audit fields.
9. `paper_reference_criteria.csv` for paper thresholds, applicability, and
   non-comparable fields.
10. `video_target_recovery_summary.csv` and each session's
    `video_target_recovery_audit.csv` for frame-level recovery evidence.
11. `client_delay_evidence/` when `--client-delay-evidence` was supplied; it is a
    portable report snapshot with figures, figure-source CSV files, rebuild script,
    selection rule and provenance.
12. Each session's `time_alignment.json` for the shared relative-time origin and
    list of transformed epoch columns.

Target metrics exclude the first 0.6 seconds after onset by default. This is a
paper-reference settling rule, not source-data deletion: standardised gaze
tables remain complete, and every excluded valid-sample count is exported. Use
`--target-settle-time-s` only when the approved study protocol requires a
different value.

Do not report coordinate-unit accuracy as degrees or pixels. Without verified
physical display size and viewing distance, OpenET2 target figures use labelled
normalised-screen percentages. The isolated delay bundle is different: its values
are approximate scores on a declared 60.00 x 33.75 degree assumed-FOV grid, not
measured visual angles.

Figure 09 is the paper-style QC view. Its dashed curves are 95% observation
ellipses, not confidence intervals for the mean, so a small number of valid
points may fall outside. The final report keeps the presentation view focused;
use `target_visit_summary.csv/.json` and its `paper_qc_*` / `paper_plot_*` fields
to audit every centroid and exclusion. Figures 09-11 and the compact HTML target
summary all use the same `paper_plot_status=included` observations.

In Figure 09, hollow circles, stars, and filled circles identify the first three
recording groups; a green `x` is the averaged target position, a red `+` is the
ellipse centre, and the red dashed line is the 95% observation interval. Stage
names are only shown when supplied by study metadata; otherwise the figure uses
truthful visit numbers or collection dates.

## 5. Common issues

- `No dated sessions found`: the root must contain `YYYY_MM_DD` directories.
- `unexpected_marker_count`: change the expected count only when the protocol
  intentionally differs from the 27-target client protocol.
- blank angular metrics: add physical display width/height and viewing distance.
- `unknown_calibration_error_unit`: identify the device unit or configure a
  matching `--calibration-error-unit`; never assume a legacy value is degrees.
- live marker timing: `marker_plan.csv` preserves the schedule, while
  `marker_data.csv` records Pygame flip-return times and timing deviations.
- unavailable Figure 3/4-style plots: collect target X/Y, participant IDs,
  physical display dimensions, viewing distance, and at least two matched
  sessions. OpenET2 does not infer these values from unrelated sessions.
- `video_file_too_small` or `missing_video_timestamps`: the source recording
  cannot support video recovery; retain the session and report the failure.
- few samples per target after settling: the client protocol's target intervals
  are shorter than the paper's; report the retained count rather than claiming
  the paper's >100-sample observation was reproduced.
- missing Tobii SDK: install the official licensed SDK on the lab computer; the
  offline pipeline does not need it.
- many duration mismatch flags: inspect video timestamp frequency and whether
  capture stopped before gaze collection.

## Research evidence controls

- Use `docs/research_collection_protocol.md` for real repeated measurements;
  do not backfill unknown display geometry, confidence, or environment values.
- `input_provenance.json` is generated beside `run_manifest.json` and links the
  report to portable SHA-256 input fingerprints.
- `marker_timing_summary.json` is written for new collection sessions. Its
  values are application-level schedule or Pygame flip-return times, not a
  physical pixel-onset latency measurement.
- The report evidence-status panel must be read before interpreting a trend.
  A descriptive or synthetic label is a boundary, not a failure to be hidden.
