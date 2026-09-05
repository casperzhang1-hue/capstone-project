# Changelog
## 1.6.0 - 2026-07-27

- Prepare the final COMP9900 delivery from the validated v1.5 implementation.
- Regenerate final reports with the centralised `1.6.0` runtime and matching
  manifests; add portable input SHA-256 provenance inventories.
- Add report evidence-status labels that distinguish synthetic validation,
  descriptive evidence, and matched comparative preconditions.
- Add an optional research collection protocol, structured display/environment
  and visit metadata, calibration sample-confidence fields, and application-level
  marker timing summaries without altering historical client source data.
- Remove duplicate Docker-generated outputs and local environment state from the
  package; future generated files use ignored `outputs/` paths.
- Retain only runtime source, tests, documentation, safe examples, references,
  Docker/CI support and final derived evidence reports.
- Centralise release-version metadata so collection, synthetic examples and run
  manifests record the package version consistently.
- Align Docker, landing page and delivery guidance with the clean final layout.
- Curate the final report to up to seven interpretable figures; remove redundant counts,
  single-device comparisons, unit-ambiguous calibration and precision charts, and
  the presentation-only unfiltered centroid diagnostic. Retain all audit values in
  exported CSV/JSON tables and label retained axes with explicit units.
- Add an optional, independently scoped client-requested delay comparison module:
  50/100/150 ms evidence, 50 ms shortest-equivalent recommendation, portable
  report snapshot, provenance, and CLI support through `--client-delay-evidence`.
- Standardise legacy epoch timestamps against one shared recorded or inferred
  origin and write per-session `time_alignment.json` audit records.
- Treat known GP3 `FPOGX`/`FPOGY` columns as normalised coordinates while retaining
  out-of-bounds values for QC rather than misclassifying the whole session.
- Use QC-only OMAE/precision consistently in target Figures 09-11 and the compact
  HTML target summary; omit the quality-flags figure when there are no flags.
- Relabel unmatched client dates as independent cohorts and flag test-like subject
  identifiers before repeatability claims.
- Rebuild the six DemoB delay figures with explicit assumed-FOV axes and archive
  their minimum source rows plus a deterministic rebuild script.
- Record Python/platform/direct-dependency versions, move CI to
  `.github/workflows`, and merge the duplicate calibration-result templates.


## 1.5.0 - 2026-07-24

- Replace the target-location mean-confidence ellipse with a correctly scaled
  95% observation ellipse based on centroid dispersion.
- Add auditable in-screen sample, nearest-target, and modified-MAD centroid QC
  for the paper-style target-location view.
- Add an unfiltered centroid diagnostic figure and retain all QC statuses,
  nearest targets, errors, and thresholds in `target_visit_summary`.
- Update documentation, client/synthetic reports, and regression coverage for
  the revised visualisation; 27 automated tests pass.
- Add a self-contained Docker runtime, Compose report server, mounted offline
  analysis workflow, containerised test target, and browser landing page.
- Make the delivery folder location-independent: Compose defaults to the
  current folder and exported inventories/manifests use portable logical paths.

## 1.4.0 - 2026-07-17

- Keep legacy CSV metadata authoritative, flag conflicting JSON values, and
  report unreadable JSON metadata with auditable diagnostics.
- Replace the machine-specific installation command with a portable Windows
  virtual-environment workflow and explicit installed-version check.
- Apply a configurable target-analysis settling window, defaulting to the
  paper's 0.6 seconds after target onset.
- Export analysis start times and per-interval/per-session counts of valid gaze
  samples excluded by the settling window.
- Add `paper_reference_criteria.csv/.json` so paper thresholds are distinguished
  from device-agnostic project warnings and non-comparable GP3 fields.
- Add a target-layout and data-coverage figure based on the paper's information
  structure, with retained sample counts and median target error.
- Update the client run to 995 analysable intervals and 348 target observations
  after the settling rule; retain all source and full standardised gaze tables.
- Replace the mean-confidence ellipse with a correctly scaled 95% observation
  ellipse, add in-screen/nearest-target/modified-MAD plot QC, and retain all
  excluded centroids in a separate unfiltered diagnostic figure and CSV fields.
- Increase automated coverage to 27 passing tests.

## 1.3.0 - 2026-07-03

- Recover the supplied prototype's random nine-point target order from AVI
  screen recordings with midpoint frame alignment and Hough-circle detection.
- Reject partial/ambiguous recovery unless all 27 intervals and the exact
  nine-target-by-three-repeat protocol validate.
- Export per-interval video recovery audit files and a cohort recovery summary.
- Add normalised target-level error, precision and eccentricity metrics when
  physical display geometry is absent; angular fields remain blank.
- Render honest normalised Figure 3/4-style client plots with explicit
  cross-sectional labels and visible off-screen/off-scale markers.
- Process 39 usable client videos (1053 recovered intervals); retain the one
  empty-video/empty-marker session as an explicit unrecoverable source failure.
- Increase automated coverage to 22 passing tests.

## 1.2.0 - 2026-06-25

- Add per-marker `target_metrics.csv/.json` observations.
- Add participant/visit/target `target_visit_summary.csv/.json` aggregation.
- Add a paper Figure 3-style target gaze-direction and 95% confidence-ellipse plot.
- Add a paper Figure 4-style OMAE versus target-eccentricity faceted plot.
- Report visit slope, correlation and observation count without imputing missing data.
- Add explicit unavailable figures when participant, target or display geometry data are absent.
- Add the target observation table to the HTML report and regression tests for the full workflow.

## 1.1.0 - 2026-06-17

- Record planned marker timing separately from Pygame flip-return timing.
- Clear each validation target at its planned end and record timing deviation.
- Import structured passing device-calibration JSON with explicit units.
- Apply calibration thresholds only to matching units.
- Fix calibration metadata column collisions in the combined report table.
- Add a deterministic three-date longitudinal/accuracy example generator.
- Add regression coverage for longitudinal, angular, calibration and reporting paths.
- Add Windows GitHub Actions offline validation and GitHub delivery guidance.

Live GP3/Tobii behaviour remains subject to the laboratory sign-off checklist.

## 1.0.0 - 2026-06-11

- Integrated the six team work packages into the modular `openet2` package.
- Added structured collection, import, QC, metrics, reports and documentation.
- Processed all 40 client sessions without pipeline failures.
