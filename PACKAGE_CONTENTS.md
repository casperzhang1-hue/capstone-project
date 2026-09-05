# OpenET2 v1.6 final delivery

Prepared: 28 July 2026

This is the clean, self-contained final COMP9900 delivery for the OpenET 2
project. Start with `README.md`, then use
`docs/requirements_traceability.md`, `docs/client_demo_guide.md`, and
`docs/technical_report.md`.

## Included

- `src/openet2`: maintainable runtime source for collection, import,
  quality checks, metrics, reporting and long-term comparison.
- `tests`: automated requirement and end-to-end regression coverage.
- `docs`: installation, user, developer, architecture, metric definitions,
  traceability, hardware-validation, Docker, GitHub and technical-report guides.
- `examples`: safe minimal input plus a clearly labelled three-date synthetic
  dataset for reproducible offline validation.
- `reports/client_data`: final derived evidence from 40 supplied sessions,
  including CSV/JSON outputs, figures, HTML report and per-session recovery
  audits. When included, `client_delay_evidence/` is a portable snapshot of the
  separate DemoB client-delay decision evidence, explicit 60.00 x 33.75 degree
  assumed-FOV boundary, figure source rows and deterministic rebuild script. No
  raw gaze files or recordings are included.
- `reports/synthetic_longitudinal`: final three-visit software-validation
  evidence, including angular target metrics and participant-matched
  repeatability.
- `references`: the client project brief, supplied JOSAA paper and the
  minimal, independently documented `client_delay_comparison` evidence bundle.
- Docker, Compose, CI and the legacy compatibility helper required to run the
  project on a separate machine.

## Structure

```text
src/        Executable package

tests/      Automated verification

docs/       Documentation and delivery guidance

examples/   Reproducible, safe input data

reports/    Final, read-only evidence artifacts

references/ Client brief, research context and canonical delay evidence

docker/     Compatibility helper for collection workflow

.github/workflows/  GitHub Actions offline validation
```

## Validation snapshot

- Release version: `1.6.0`.
- Requirements: all ten client-brief requirements map to implementation and
  verification in `docs/requirements_traceability.md`.
- Automated validation: 30 tests pass in the full workspace with authorised
  client data; a standalone copy skips only the client-data availability test.
- Client evidence: 40 sessions processed, 39 usable video recordings recovered
  1,053 target intervals, and the unusable source session remains explicitly
  reported in the derived outputs.
- Synthetic evidence: three dates, 81 target intervals, 27 target observations
  and one participant-aware repeatability result.
- JOSAA alignment: the 0.6-second target-settling rule and related criteria are
  documented with applicability boundaries in `paper_reference_criteria.*`.

The bundled reports are regenerated with the centralised `1.6.0` runtime and
contain matching run manifests, generated timestamps, Python/direct-dependency
runtime snapshots, report evidence-status labels, shared session time-alignment
records, and portable `input_provenance.json` SHA-256 inventories. The reports
remain derived evidence; they do not include raw client gaze files or videos.

## Deliberately excluded

- Raw client eye-tracking data and AVI recordings.
- Duplicate `docker-output` artifacts; new derived files are created under the
  ignored `outputs/` directory when required.
- Local `.env` files, virtual environments, caches, bytecode, archives and
  machine-specific development state.
- Six historical task-split copies and other superseded delivery folders.

Live device behaviour remains subject to
`docs/hardware_validation_checklist.md`. Do not present synthetic or
application-level timing evidence as physical device validation.