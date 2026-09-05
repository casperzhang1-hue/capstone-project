# OpenET 2 example data

`example_data/2026_01_01/000` is a deliberately small, device-neutral session
that demonstrates the supported folder contract, rich metadata, gaze samples,
video timestamps, calibration metadata, and marker targets.

Run it from the repository root:

```powershell
openet2 run `
  --data-root examples/example_data `
  --output-root outputs/example `
  --expected-marker-events 2
```

For a complete 27-target synthetic collection, use `openet2 collect` without
`--live`. The dry-run follows the same state and file contract as a live lab
session and is safe to use without hardware.

Generate and analyse a multi-date example with one repeated synthetic
participant:

```powershell
openet2 generate-example --output-root examples\synthetic_longitudinal_data
openet2 run `
  --data-root examples\synthetic_longitudinal_data `
  --output-root outputs\synthetic_longitudinal_report
```

The generated manifest and every session explicitly identify the data as
synthetic. It exercises participant-matched repeatability, target accuracy and
visual-angle metrics without making a hardware-performance claim.

`calibration_result.example.json` documents the live calibration-result import
contract. Replace every example value with the real device export before use.
