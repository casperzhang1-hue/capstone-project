# Live hardware validation checklist

Record device model, serial, firmware/software, SDK, computer, operating system,
display, and OpenET 2 commit/version for every signed run.

## Before collection

- [ ] GP3 Control or official Tobii SDK sees the intended device.
- [ ] Device ID/model/serial/software and nominal sampling rate are correct.
- [ ] Display pixel/physical dimensions and viewing distance are measured.
- [ ] Selected capture monitor and resolution are correct.
- [ ] A 30-second dry-run completes and its report opens.

## Live workflow

- [ ] Calibration stage completes and saves device-reported results.
- [ ] Calibration result records its error unit, valid points, source, and status.
- [ ] Validation targets appear at all nine positions, three repeats each.
- [ ] Target Y positions use display height and visually align with expectations.
- [ ] Gaze, video, marker, and workflow timestamps share recording-relative time.
- [ ] `marker_plan.csv` and `marker_data.csv` timing deviations are reviewed.
- [ ] Physical display onset/offset latency is measured externally if the study
      requires timing beyond application-level Pygame flip timestamps.
- [ ] Start/normal stop creates `session_completed` and closes device/video.
- [ ] Forced failure creates `session_failed` and still releases resources.

## Post-collection

- [ ] Gaze duration approximately matches planned duration.
- [ ] Effective sampling rate is plausible for the nominal rate.
- [ ] Video timestamps and AVI frame count agree within one frame.
- [ ] Session review shows target-aligned gaze and expected invalid periods.
- [ ] Calibration units are identified; angular metrics use measured geometry.
- [ ] Two repeated sessions produce a participant-matched repeatability row.
- [ ] Target X/Y and display geometry produce finite `target_visit_summary`
      angular values and the two paper-aligned figures.

## Sign-off

```text
Device/serial:
SDK/software:
OpenET 2 version/commit:
Date:
Operator:
Pass/fail and notes:
```

## Research evidence extension

- [ ] Record monitor model, pixel dimensions, physical width/height, refresh
  rate, viewing distance, environment, ambient illuminance, and head support.
- [ ] Preserve the vendor calibration export with error unit, high-quality
  sample count, and confidence threshold when the device supplies them.
- [ ] For paper-style comparison, use a fixed `4.2 s` presentation, exclude
  the first `0.6 s`, and verify more than 100 retained valid samples per target.
- [ ] Collect the same participant/device/protocol at baseline, `+5 min`, and
  `+1 h`; record each `VisitLabel` and do not substitute unmatched cohorts.
- [ ] Review `marker_timing_summary.json`; sign off only after a separate
  physical-display timing validation if photon-onset latency is required.
- [ ] Archive `input_provenance.json`, `run_manifest.json`, calibration export,
  and the complete QC report with the approved research record.
