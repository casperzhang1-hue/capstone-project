# Client demonstration guide

## Recommended 10-minute flow

1. Explain that `src/openet2` extends the supplied OpenET code through the
   compatibility layer in `legacy.py`; the client source remains unchanged.
2. Run a 30-second dry-run collection and show the dated session folder,
   structured metadata, calibration evidence, marker plan/observations, gaze,
   video timestamps, workflow states, and log.
3. Open `reports/client_data/report.html`. State that all 40 supplied
   sessions processed without pipeline failures; 39 usable AVI recordings
   recovered all 1053 target intervals, while session `2025_04_12/029` has an
   empty timestamp table, a 5,686-byte undecodable AVI, and no marker file.
   Show the recovery summary, QC flags, paper-reference criteria table, target
   plots, target-layout/coverage view, and a session review.
4. Open `reports/synthetic_longitudinal/report.html`. Clearly state that
   it is synthetic software-validation data, then show the evidence-status
   label, three dates, finite target/angular metrics, participant-matched
   repeatability row, QC-filtered target observation ellipses, and OMAE/
   eccentricity facets. The unfiltered diagnostic remains auditable in exports
   but is deliberately excluded from the presentation report.
5. End with `docs/requirements_traceability.md` and the unsigned items in
   `docs/hardware_validation_checklist.md`.

## Commands

```powershell
python -m pip install -e ".[dev,video]"
python -m pytest -q -p no:cacheprovider

openet2 collect `
  --legacy-code-root "docker\legacy_code" `
  --output-root "outputs\client_demo_collection" `
  --subject-id "DEMO01" `
  --device-id "GP3HD" `
  --test-id "Accuracy demo" `
  --duration-s 30 `
  --display-width-mm 530 `
  --display-height-mm 300 `
  --viewing-distance-mm 600

openet2 run `
  --data-root "<path-to-client-data>" `
  --output-root "outputs\openet2_v1_client" `
  --recover-targets-from-video

openet2 generate-example `
  --output-root "examples\synthetic_longitudinal_data" `
  --overwrite

openet2 run `
  --data-root "examples\synthetic_longitudinal_data" `
  --output-root "outputs\synthetic_longitudinal_report"
```

## Claims that are supported

- The offline package installs and all automated tests pass.
- All 40 supplied client sessions are imported without processing failures.
- All 1053 intervals in the 39 usable videos pass strict target-recovery
  validation; the unusable 40th recording remains explicitly reported.
- After the paper's 0.6-second settling window, the client target plots contain
  348 session/target observations from 995 intervals with at least five
  retained valid samples, in normalised screen units. The run records 28,393
  excluded valid samples; source and standardised gaze tables remain complete.
- The paper-style target-location view plots 280 QC-eligible observations: 13
  lack five in-screen samples, 52 are closest to a different protocol target,
  and 3 are robust centroid outliers. All 348 remain in exported audit columns;
  Figures 09-11 and the HTML target summary use the same retained observations.
- The software detects and reports quality problems without altering source data.
- All 40 GP3 sessions retain the known normalised coordinate unit; out-of-bounds
  values are screened by QC instead of causing session-wide unit ambiguity.
- The separate client-delay evidence selects 50 ms within its three declared
  candidates and explicitly labels the fixed 60.00 x 33.75 degree assumed-FOV
  conversion as approximate rather than a physical visual angle.
- The synthetic workflow demonstrates multi-date comparison, target accuracy,
  angular metrics, participant-matched repeatability, and both paper-aligned
  scientific visualisations.
- GP3/Tobii lifecycle adapters and application-level timing capture are implemented.

## Claims that are not yet supported

- Do not say that live GP3 or Tobii hardware is validated.
- Do not treat Pygame flip-return timestamps as physical pixel onset measurements.
- Do not describe the synthetic repeatability result as device performance.
- Do not interpret the client calibration values as degrees until the client
  confirms their unit.
- Do not claim a real longitudinal study from the supplied two-date dataset.
- Do not claim the paper's >100 high-confidence samples per target: the client
  protocol intervals are shorter and retain 5-84 valid samples after settling.
- Do not describe the client normalised-screen plots as angular-degree results
  or matched-visit repeatability.
- Do not present the DemoB assumed-FOV degree scores as measured visual angles or
  replace them with pixels unless source resolution and a defined pixel-space
  comparison are explicitly introduced.

If asked about these boundaries, show the hardware checklist and propose the
short lab validation run as the next acceptance activity.
