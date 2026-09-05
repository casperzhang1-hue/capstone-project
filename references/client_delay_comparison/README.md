# Client-requested delay comparison evidence

This focused bundle is derived from the supplied `DemoB_FinalEdition` analysis and remains separate from the OpenET2 session pipeline.

## Decision

- Primary candidates: 0.0500 s, 0.1000 s and 0.1500 s.
- Selected client delay: 0.0500 s (50 ms), using the recorded shortest-equivalent rule.
- Primary outcomes: balanced target error and repeated-marker radial spread.
- Pairwise evidence: participant-level paired bootstrap with 3,000 repetitions.
- `ellipse_coverage.png` is post-selection QA, not part of the delay score.

## Coordinate boundary

The source analysis maps normalised screen coordinates to a fixed 60.00 x 33.75 degree display-field-of-view grid. Physical display dimensions and viewing distance were not supplied. Therefore every `*_deg` value in this bundle is an **approximate assumed-FOV degree score**, not a measured physical visual angle and not a substitute for pixel coordinates.

The six figures were rebuilt without changing the archived metrics. Their axes now state seconds/milliseconds, percentages, or assumed-FOV degree scores explicitly. Run `python rebuild_figures.py` to reproduce them from the included CSV files.

## Audit contents

- Candidate metrics and paired-bootstrap results.
- Participant/condition/target metrics used by the decision rule.
- Corrected target positions, QC-retained recording-target means and ellipse coverage source rows used to rebuild the figures.
- Machine-readable selection rule and provenance.
- Six focused figures; unrelated threshold-tuning material is excluded.
