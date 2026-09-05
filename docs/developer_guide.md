# Developer guide

## Development setup

Install `.[dev,video]` for offline client-data development, or
`.[dev,collection]` on a Python version supported by Pygame for live collection.
Run all tests with bytecode
and pytest cache disabled when checking that the source tree remains clean.

## Adding a file format

Implement a callable with signature `(path, source_device, display_width_px,
display_height_px) -> DataFrame`, return `STANDARD_GAZE_COLUMNS`, and register it
with `register_gaze_importer(name, predicate, importer)`. Preserve raw values,
convert time to seconds, and declare coordinate space. Add CSV/JSON fixtures and
tests for missing columns and invalid values.

## Adding a live device

Implement idempotent `start`, blocking or timed `read_sample`, and `stop`.
Dependencies must be imported lazily. `stop` must tolerate partial startup and
be called from `finally`. Add the device selection to `_collect_live` and keep
vendor names out of offline modules.

## Adding a protocol

Protocol targets must have IDs, relative start/end seconds, target X/Y, and
coordinate space. Store actual display dimensions in metadata. A protocol may
change expected marker count through CLI thresholds, but must not silently
reuse the 27-target default.

## Adding a metric

Consume standard tables and document inclusion rules, aggregation, units,
missing-value behaviour, and limitations. Never convert coordinate units to
degrees without physical geometry. Add a deterministic unit test and expose the
result in CSV before adding a plot.

## Failure policy

Malformed sessions create failure rows while other sessions continue. Raw data
must never be rewritten. Programming errors should be fixed rather than hidden;
the pipeline catches expected data/plot/runtime errors at the session boundary.

## Release checklist

1. Update version in `pyproject.toml`, `openet2.__init__`, collection metadata,
   manifest, and README.
2. Run unit/integration tests and the supplied-data regression.
3. Run the included example and inspect `report.html` plus session review.
4. Execute the hardware checklist for each live device/SDK version.
5. Confirm documentation and requirements traceability reflect implemented code.
