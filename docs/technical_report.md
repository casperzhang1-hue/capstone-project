# OpenET 2 technical report

## Executive summary

OpenET 2 extends the client-provided OpenET prototype into a unified research
software package for structured eye-tracker collection and long-term
benchmarking. The implementation preserves the original source as evidence,
adapts its working device/folder concepts behind safe interfaces, and replaces
global, hard-coded orchestration with explicit session configuration, standard
tables, automated validation, auditable metrics, and reproducible reports.

## Client baseline findings

The supplied prototype contains useful GP3 socket parsing, Tobii discovery,
screen capture, marker positions, and dated folder creation. It is fragmented
across experimental scripts and contains hard-coded paths/global state. The
timestamp mutator reads the video table for every file and can corrupt gaze
outputs. The marker writer uses display width for both X and Y. The supplied
recorded dataset also comes from a later/different prototype revision: its
metadata uses `Start_time_s`, and its standardised time headers are not present
in the supplied source.

OpenET 2 therefore uses an explicit compatibility boundary. It calls the
original folder creator and GP3/Tobii layers where safe, but performs metadata,
time alignment, marker creation, lifecycle, and analysis in tested modules.

## Implemented system

The collection workflow records required metadata and state transitions for
session creation, calibration, validation, recording, target presentation,
video capture, stop, completion, and failure. A deterministic dry-run exercises
the complete output contract without hardware. Live mode selects guarded GP3 or
Tobii adapters and requires either explicit calibration confirmation or a
structured passing calibration export. Planned marker times remain separate
from application-level Pygame flip-return timestamps and timing deviations.

The offline pipeline discovers legacy and new sessions, converts CSV/TSV/JSON
exports into stable gaze/video/marker tables, runs configurable quality checks,
calculates coordinate and optional angular metrics, generates individual and
cohort figures, and writes long-term plus participant-matched repeatability
summaries. It never modifies source recordings.

Version 1.4 also recovers the supplied prototype's lost random target identity
from its AVI screen recordings. Each marker midpoint is mapped to a timestamped
frame, the circle is detected near the documented nine protocol positions, and
coordinates are accepted only if all 27 intervals resolve and each target occurs
three times. Frame-level evidence is retained in derived audit tables.
Target analyses then apply the reference paper's 0.6-second post-onset settling
window by default. The actual analysis start and excluded valid-sample count are
stored for every retained interval. A paper-criteria table distinguishes rules
that are applied from those that are conditional, descriptive, or not
comparable with the GP3 export schema.

## Research validity decisions

- Historical marker intervals without target coordinates support stability and
  coverage unless a complete video recovery passes strict protocol validation;
  partial or ambiguous recovery remains blank.
- Visual-angle results require measured display geometry and viewing distance.
- Device/date summaries include participant counts. Device drift is not inferred
  from different participant cohorts.
- Repeatability only combines the same participant, device, protocol, and test
  condition across at least two sessions.
- Quality thresholds generate review flags rather than silently excluding data.
- Calibration error thresholds are unit-aware; unknown legacy units are not
  silently interpreted as visual degrees.

## Validation evidence

Thirty automated tests cover CSV/TSV/JSON imports, known GP3 coordinate
semantics, recorded and inferred shared epoch origins, client folder compatibility,
rich/conflicting/unreadable metadata, complete dry-run outputs, gap/loss detection,
target and angular metrics, participant-aware repeatability, failure isolation,
source-data immutability, calibration-result validation, calibration-unit handling,
QC-only target metrics, observation-ellipse scaling, settling-window audit fields,
strict video target recovery, and a three-date synthetic end-to-end workflow.

The current source processed all 40 supplied client sessions with zero pipeline
failures, produced 40 individual session reviews and seven focused cohort figures, and
preserved all source files. Thirty-nine usable AVI recordings recovered all
1053 target intervals with the expected nine-by-three signature. Of those,
995 intervals contained at least five retained valid gaze samples after the
0.6-second settling window and produced 348 session/target observations. The
run records 28,393 excluded valid samples; those samples remain present in the
source and standardised gaze tables. Session `2025_04_12/029` is explicitly
unrecoverable: its video timestamp CSV contains only a header, its AVI is 5,686
bytes with no decodable frame, and its marker file is absent.

The scientific views are aligned with the client paper without inventing
units. The synthetic geometry-complete workflow uses degrees and matched visits.
The client workflow lacks physical display size and viewing distance, so it uses
explicitly labelled normalised screen fractions and cross-sectional date facets.
The known GP3 `FPOGX`/`FPOGY` fields identify all 40 sessions as normalised
coordinates; out-of-bounds values remain quality evidence rather than changing
the unit of an entire session. The final target-location view plots 280 of 348
session/target observations after auditable QC: 13 lack five in-screen samples,
52 are closest to another protocol target, and 3 are robust centroid outliers.
Its target-wise 95% observation ellipses use covariance of retained centroids
without dividing by sample count; 261/280 displayed centroids fall inside. The
full CSV/JSON audit retains all 348 observations. It records 3,694 post-settling
samples excluded by screen-validity QC, while the separate settling rule records
28,393 exclusions; neither group is deleted from source or standardised gaze.
Figures 09-11 and the compact 18-row date/target HTML summary all use the same
`paper_plot_status=included` observations. The target-layout view maps all nine
protocol positions and labels QC-retained session and sample coverage.

The reference criteria table also prevents overclaiming. The client exports do
not provide the paper system's calibration/gaze confidence fields, calibration
errors are not labelled in degrees, no target interval retains more than 100
valid samples after settling, and no confirmed matched repeated participant is
available. Therefore the paper's confidence filters, <=1.5-degree calibration
limit, participant OMAE coefficient of repeatability, and mixed-effects model
are not reported as reproduced client results.

The included example session passes all default quality rules when its expected
marker count is set to two and produces finite coordinate and visual-angle
metrics. The generated multi-date example produces a participant-matched
repeatability row and finite target/angular results; it is explicitly synthetic
and is not hardware-performance evidence. Each run records portable input hashes,
Python/platform/direct-dependency versions and per-session shared time origins.
The client report labels its two dates as unmatched cohorts and flags the
`CL98test` identifier for identity review instead of silently aliasing it.

## Limitations and remaining external work

The code-level live lifecycle is complete, but physical hardware behaviour
cannot be certified without the GP3/Tobii devices, installed vendor software,
and target laboratory displays. SDK version compatibility, calibration output,
screen selection, end-to-end latency, achieved video rate, and forced-failure
cleanup must be signed off using the hardware validation checklist.

The client dataset contains only two collection dates with different participant
cohorts. It demonstrates batch processing and cross-sectional comparison, not a
scientifically adequate long-term repeatability study. Future collection should
repeat the same protocol and condition for the same participants across planned
days/weeks and record physical display geometry.

## Conclusion

OpenET 2 now satisfies the software deliverables in the project brief: extended
source, structured collection, session/device metadata, multi-format import,
quality validation, benchmarking, visualisation, repeated-measurement support,
examples, installation/user/developer documentation, and real-data
demonstration. Live-device sign-off remains an explicitly documented external
verification step rather than an untested software claim.

## Final evidence controls

The final package adds an evidence-status panel and input file fingerprints so a
reader can distinguish descriptive client evidence, synthetic pipeline
validation, and future matched comparative data. It also exposes an optional
research collection protocol with fixed target presentation, visit labels, and
structured display/calibration metadata. These controls do not repair missing
legacy metadata or transform normalised coordinates into physical measurements.
They make the missing prerequisites explicit and reproducible for the next
collection cycle.
