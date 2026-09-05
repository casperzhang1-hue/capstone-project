# Metric and quality definitions

## Timing and completeness

- `duration_s`: last finite timestamp minus first finite timestamp.
- `effective_sampling_hz`: `(sample count - 1) / duration_s`.
- `median_interval_ms`, `p95_interval_ms`, and `sampling_jitter_ms`: statistics
  of positive consecutive intervals; duplicate and backward timestamps are
  counted separately.
- `estimated_missing_samples`: for each positive interval, the rounded number
  of median sampling intervals minus one.
- `data_loss_rate`: invalid observed samples plus estimated missing samples,
  divided by observed plus estimated missing samples.
- `completeness_rate`: one minus data loss rate.

Missing-sample estimates assume the dominant median interval represents the
intended local sampling period. They should be interpreted with the nominal
device rate and irregular-sampling flag. Epoch-like gaze, video and marker
columns are converted to one shared relative-seconds origin. `time_alignment.json`
records whether that origin came from recording metadata or the earliest observed
epoch timestamp and lists every transformed column.

## Marker-period performance

Only valid finite gaze samples inside marker intervals are used. By default the
first 0.6 seconds after every target onset are excluded, matching the reference
paper's settling rule; change this with `--target-settle-time-s`. An interval
requires at least five retained samples. `target_settle_time_s`,
`analysis_start_s`, `settle_excluded_valid_samples`, and
`marker_settle_excluded_samples` make this exclusion auditable.

- `marker_precision_rms`: radial RMS around each interval gaze centroid, then
  the median across intervals.
- `marker_stability_p95`: median interval-level 95th percentile radius.
- `marker_accuracy_rmse`: RMS of interval centroid-to-target radial errors.
- `marker_mean_absolute_error`: mean absolute centroid-to-target radial error.
- `marker_systematic_error_x/y`: mean signed centroid error across targets.
- `marker_systematic_error_radial`: magnitude of the mean signed error vector.
- `marker_random_error_rms`: RMS of interval precision values.
- `marker_repeatability_95`: `1.96 * SD` of interval radial target errors.
- `marker_coverage_rate`: covered intervals divided by recorded intervals.

Coordinate-unit metrics use the standard table's coordinate system. For the
supplied GP3 data this is normally a proportion of display width/height.
`marker_repeatability_95` is an interval-level descriptive metric and must not
be presented as the paper's participant-level OMAE coefficient of
repeatability.

## Visual-angle metrics

When `DisplayWidthMm`, `DisplayHeightMm`, and `ViewingDistanceMm` are present,
normalised displacement is converted to millimetres and then to visual angle:

```text
angle_deg = degrees(atan2(radial_displacement_mm, viewing_distance_mm))
```

- `marker_omae_deg`: overall mean absolute sample-to-target visual-angle error.
- `marker_accuracy_rmse_deg`: RMS sample-to-target visual-angle error.
- `marker_precision_rms_deg`: median target-period precision in degrees.

These transparent definitions support the systematic/random/OMAE direction of
the client paper. They are not populated when physical geometry is unavailable.

## Paper-aligned target observations

`target_metrics` contains one row for every marker interval with at least five
retained valid gaze samples and a finite target position. It always records explicitly
named normalised-screen errors, precision, OMAE, and eccentricity. When physical
geometry is available it additionally records visual-degree fields. Vertical
values are Cartesian, so positive values point up even though normalised screen
Y increases downward.

`target_visit_summary` then averages repeated intervals at the same target to
one participant/session/target observation. It does not treat high-frequency
gaze samples as independent participants.

- `target_eccentricity_deg`: angular distance from the target to display centre.
- `error_x_deg`, `error_y_deg`: signed centroid-to-target angular errors.
- `centroid_error_deg`: radial angular error of the interval centroid.
- `omae_deg`: mean radial sample-to-target angular error.
- `precision_rms_deg`: radial RMS around the interval gaze centroid.

The corresponding `_normalised` fields use fractions of screen width/height and
must not be called degrees. The Figure 3-style main view only uses gaze samples
inside the normalised display and requires at least five such samples per
interval. At the session/target level, a centroid must be closest to its
assigned protocol target. A target-wise modified-MAD rule then flags remaining
radial centroid errors above `median + 3.5 * 1.4826 * MAD`. The audit fields
`paper_qc_*` and `paper_plot_*` record sample counts, QC-only OMAE/precision,
nearest target, radial error, cutoff, and inclusion status; original metrics are
not overwritten. Figures 09-11 and the HTML target summary all use the same
`paper_plot_status=included` rows.

The main view uses target directions, QC-included session/target means, and a
bivariate 95% observation ellipse. The ellipse uses the sample covariance
without dividing it by the number of observations and
`chi-square(2, 0.95) = 5.991`; it is drawn only for targets with at least three
observations. This is a distribution ellipse, not a confidence interval for
the mean. A 95% ellipse is expected to leave about 5% of valid observations
outside, so enlarging it to contain every point would mislabel the statistic.
The final HTML report omits the unfiltered centroid diagnostic because it is an
audit view rather than a presentation result. All centroid statuses, original
values and QC thresholds remain in `target_visit_summary.csv/.json`.

Figure 09 follows the paper's visual grammar: the first three observed groups
use a hollow circle, star, and filled circle; averaged target positions use a
green `x`; ellipse centres use a red `+`; and observation intervals use red
dashes. Legend text comes from actual visit labels or collection dates. OpenET2
does not infer "initial", "5 min", or "1 hour" when those stages are absent
from the supplied metadata.

Figure 4 displays errors above the normalised plotting limit as triangles;
regression and exported values remain unclipped. It uses one target observation per
participant/visit and reports an ordinary least-squares slope plus Pearson
correlation for each visit. These are descriptive plots; they do not replace the
paper's mixed-effects inferential model.

Figure 11 maps the recovered nine target positions and reports per-target
session coverage, retained valid-sample totals, and median target error. It
adapts the information structure of the paper's target-layout diagram without
copying the paper artwork or implying identical hardware.

## Reference-paper criteria

`paper_reference_criteria.csv/.json` separates reference-paper rules from
OpenET2's configurable device-agnostic warnings. The table records:

- the paper's >150 high-quality calibration samples and >=0.8 confidence rule,
  which is not directly comparable because GP3 exports do not contain the same
  per-sample confidence fields;
- the <=1.5-degree mapping-accuracy rule, applied only to calibration errors
  explicitly labelled in degrees;
- the applied 0.6-second target settling window;
- the observed count of target intervals retaining >100 valid samples;
- the paper's 3-5% blink/unreliable-time context, retained as reference rather
  than a universal GP3 pass/fail limit;
- the paper OMAE coefficient of repeatability and mixed-effects model, which
  require genuine participant identities and matched repeated visits.

The client dataset has no confirmed matched repeated participants or physical
display geometry, so OpenET2 does not claim a paper-specific OMAE coefficient,
fit the paper's inferential model, or convert its target errors to degrees.

## Legacy AVI target recovery

With `--recover-targets-from-video`, each marker midpoint is aligned to the
nearest `Video_data.csv` frame. A Hough-circle detector searches only near the
nine positions documented by the supplied target presenter. A session is
accepted only if all 27 intervals resolve unambiguously and every target occurs
exactly three times. `video_target_recovery_audit.csv` stores source frame,
timing error, detected centre/radius, matched protocol target, offset and
confidence. Failed or incomplete sessions keep blank targets and an explicit
status; source files are never changed.

## Repeated measurements

`long_term_summary` reports device/protocol/condition medians per date, including
participant and repeated-participant counts. `repeatability_summary` only groups
the same participant, device, test, and condition across two or more sessions.
Its 95% repeatability coefficient is `1.96 * sqrt(2) * within-group SD`.

Different participant cohorts must not be interpreted as causal device drift.

## Default quality thresholds

| Check | Default |
|---|---:|
| Minimum valid rate | 0.80 |
| Maximum data loss rate | 0.20 |
| Maximum irregular interval fraction | 0.20 |
| Interval deviation tolerance | 0.50 of median |
| Longest allowed sampling gap | 0.25 s |
| Expected marker events | 27 |
| Minimum marker coverage | 0.80 |
| Maximum gaze/video duration mismatch | 0.20 |
| Maximum normalised out-of-bounds rate | 0.01 |
| Minimum valid calibration points | 5 |
| Maximum calibration error | 1.0 degrees by default |
| Maximum recording shortfall | 0.10 of planned duration |

The separate target-analysis setting defaults to a 0.6-second settling window;
it is not a quality pass/fail threshold.

## Final-report chart units

The final HTML report contains only figures with interpretable axes: sampling
rate in Hz, valid gaze samples in percent, non-empty QC frequency as affected-
session counts, elapsed time in seconds, visual-angle quantities in degrees when
physical geometry is recorded, and otherwise normalised screen percentages. A
blank QC chart is omitted when no flags exist. A normalised horizontal coordinate is a fraction of display width;
a vertical coordinate is a fraction of display height. Raw coordinate values are
never relabelled as degrees.

The final report also writes presentation-layer tables alongside the unchanged raw
analysis exports: `report_display_session_metrics.csv`,
`report_display_long_term.csv`, `report_display_repeatability.csv`, and
`report_display_target_visits.csv`. The full target display export retains every
QC status, while the HTML table is a concise date/target summary of included rows.
Their `*_pct` fields equal the corresponding raw proportion multiplied by 100. Horizontal and vertical display fields explicitly
name `% of display width` or `% of display height`; radial fields named
`*_relative_coordinate_pct` use 100% for one raw normalised-coordinate unit. The
conversion mapping is stored in `report_display_units.json`.

Thresholds are configurable and create flags only. The calibration threshold
is applied only when the recorded unit matches `--calibration-error-unit`. A
numeric error with an absent, `unknown`, or `device_reported` unit receives
`unknown_calibration_error_unit` and is not silently compared with a degree
threshold. This prevents legacy percentages or device-specific scores from
being misinterpreted as visual degrees.

Metadata checks are deterministic rather than threshold based. When
`Recording_info.csv` and `session_metadata.json` provide different non-empty
values for the same normalised key, the CSV value remains authoritative and
the session receives `inconsistent_metadata`. The conflicting field names are
exported in `metadata_conflict_fields`. An unreadable or non-object JSON file
receives `unreadable_session_metadata` and its diagnostic is retained in
`metadata_read_error`.

## Client-requested delay evidence

`references/client_delay_comparison/` is a focused, external evidence bundle copied
from the supplied DemoB analysis. When passed through
`--client-delay-evidence`, it adds a separate report section comparing the requested
0.0500 s, 0.1000 s and 0.1500 s client delays. Its balanced target-error and
repeat-spread fields retain their source `*_deg` names, but are explicitly defined
as approximate scores on a fixed 60.00 x 33.75 degree assumed-FOV grid because
physical display geometry is absent. Paired bootstrap results, source rows, rebuilt
figures, selection rule and provenance remain separate from OpenET2 session metrics. The selected 0.0500 s client
delay must not be confused with `target_settle_time_s=0.6000`, which is the OpenET2
target-analysis exclusion window.

## Evidence status and input provenance

Each generated report now contains an evidence-status panel. It labels a run as
synthetic software validation, descriptive-only, conditional comparison, or a
comparative benchmark candidate from recorded, not assumed, properties:
physical display geometry, matched repeatability groups, quality flags, and
calibration units. The label never deletes data or converts a QC warning into a
silent exclusion.

`input_provenance.json` contains a portable SHA-256 fingerprint for each input
file read by a run plus one deterministic content digest. `run_manifest.json`
repeats the digest, source-file count, package version, generated timestamp,
thresholds, Python version, platform and direct-dependency versions. Absolute
local paths are never exported.

## Research protocol fields

`CollectionConfig` and `openet2 collect` can record `VisitLabel`, display model
and refresh rate, ambient illuminance, head support, target presentation time,
settling time, and nominal minimum post-settling samples. When
`--target-presentation-s` is supplied, the command verifies that the requested
duration can schedule every target and nominally retain the requested number of
samples after the settling period. Actual retention remains an output QC fact,
not a promise.

Calibration exports can additionally provide `high_quality_samples` and
`confidence_threshold`. The paper-reference table uses those fields only when
present; a valid/invalid sample flag is not reinterpreted as a vendor confidence
score. See `docs/research_collection_protocol.md`.
