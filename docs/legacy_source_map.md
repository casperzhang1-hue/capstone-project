# Client OpenET continuation map

The supplied client source is stored at the caller-provided `--legacy-code-root`
and is treated as an unchanged baseline. The portable delivery includes the
required folder-creation compatibility file under `docker/legacy_code`; it does
not depend on the original workspace or a OneDrive directory.

| Supplied module | Continued responsibility | OpenET 2 boundary |
|---|---|---|
| `create_data_folder.py` | `YYYY_MM_DD/NNN` folder contract | `legacy.create_session_folder` adapts both the original no-argument/no-return function and newer parameterised variants. |
| `GP3_helpers.py` | Gazepoint process control, port 4242 protocol, sample parsing | `LegacyGP3Adapter` adds idempotent start/read/stop and guaranteed cleanup. |
| `tobii_helpers.py` | Tobii discovery and SDK access | `LegacyTobiiAdapter` reuses discovery but owns a safe queue callback because the original callback depends on an undefined global writer. |
| `display_markers_on_2screen.py` | Nine target positions repeated three times | `collection.ACCURACY_TARGETS` continues the protocol and writes correct normalised X/Y targets. |
| `cv2_utilities.py` and collection scripts | Screen capture concept and frame timestamps | `collection._record_screen` records AVI plus second-based frame timestamps with a guarded stop event. |
| Combined prototype scripts | Calibration/recording/stimulus orchestration | `collect_session` replaces global state with explicit configuration and auditable workflow events. |

## Deliberately bypassed prototype defects

The original `GP3_helpers.set_start_time_to_recording_start` reads
`Video_data.csv` inside a loop for gaze, Tobii, and video files. Calling it can
overwrite gaze data with video columns. OpenET 2 never calls this mutator;
`standardise_session` performs read-only, per-file time alignment.

The original marker writer calculates Y pixels using display width. OpenET 2
stores normalised target coordinates and converts X and Y with their respective
display dimensions.

These are adapter/refactoring decisions, not claims that the supplied client
files themselves were edited.
