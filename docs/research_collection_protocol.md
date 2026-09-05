# Research-ready collection protocol

This protocol makes a future OpenET2 study comparable without changing or
backfilling historical source data. It is an optional research workflow; the
30-second dry-run remains a software demonstration only.

## Before every session

1. Use a pseudonymous `SubjectID`, a stable `TestID` for the same protocol,
   and a `VisitLabel` such as `baseline`, `plus_5min`, or `plus_1h`.
2. Record device model, serial, software version, nominal sample rate, monitor
   model, pixel resolution, physical width/height in mm, refresh rate, and
   measured viewing distance in mm.
3. Record environment, ambient illuminance (lux when measured), seating or head
   support, operator, and deviations in `Notes`.
4. Preserve the device-exported calibration result. Do not enter a degree value
   unless the vendor explicitly reports degrees.

## Calibration and validation

- Record calibration status, average error, unit, valid points, high-quality
  calibration-sample count, and the confidence threshold used by the device.
- The JOSAA reference is only comparable when the export provides the needed
  fields: more than 150 high-quality samples, a recorded confidence threshold
  of at least 0.8, and a degree-labelled mapping error no greater than 1.5 deg.
- Run and retain a nine-position validation with three repeats. The application
  records display flip-return timing, not physical photon-onset timing.

## Target protocol

For a paper-aligned 27-target session at 60 Hz, use a 4.2-second presentation
for each target and exclude the first 0.6 seconds. This provides 216 nominal
post-settling samples per target before quality loss; the analysed export must
still show more than 100 retained valid samples per target before making the
paper-style sample-count comparison.

```powershell
openet2 collect `
  --legacy-code-root "docker\legacy_code" `
  --output-root "outputs\research_collection" `
  --subject-id "P001" `
  --device-id "GP3HD" `
  --test-id "nine_point_accuracy_v1" `
  --visit-label "baseline" `
  --duration-s 114 `
  --target-presentation-s 4.2 `
  --target-settle-time-s 0.6 `
  --minimum-post-settle-valid-samples 100 `
  --display-width-px 1920 `
  --display-height-px 1080 `
  --display-width-mm 530 `
  --display-height-mm 300 `
  --viewing-distance-mm 600 `
  --display-refresh-hz 60 `
  --ambient-illuminance-lux 300 `
  --head-support "chin rest"
```

The fixed-presentation option validates nominal capacity only. It does not
invent confidence values or override post-run QC.

## Repeated and long-term measurement

Use the same participant, device, `TestID`, test condition, target layout,
display geometry, viewing distance, and environmental setup for baseline,
short-term (`plus_5min`), and longer (`plus_1h`) repeats. Add weekly or monthly
visits only with the same protocol. Do not claim device drift from unmatched
cohorts.

Only after these prerequisites are met should a participant random-intercept
mixed model, Satterthwaite degrees of freedom, and Bonferroni-adjusted
comparisons be considered. Retain the current descriptive tables when the
preconditions are not met.

## Evidence and privacy

- Keep raw inputs read-only; the pipeline creates `input_provenance.json` with
  portable SHA-256 fingerprints.
- Review `marker_timing_summary.json` as application-level timing evidence.
- Store consent, re-identification keys, raw eye videos, and device exports
  outside the delivery package according to the approved data-governance plan.
