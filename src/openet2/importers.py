"""Import legacy eye-tracking files into standard tables."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from .metadata import SessionRecord, read_recording_info


STANDARD_GAZE_COLUMNS = [
    "time_s",
    "device_time_s",
    "system_time_s",
    "gaze_x",
    "gaze_y",
    "valid",
    "left_gaze_x",
    "left_gaze_y",
    "right_gaze_x",
    "right_gaze_y",
    "left_valid",
    "right_valid",
    "pupil_left",
    "pupil_right",
    "source_device",
    "raw_gaze_x",
    "raw_gaze_y",
    "raw_cx",
    "raw_cy",
    "coordinate_space",
]
STANDARD_VIDEO_COLUMNS = ["frame_id", "time_s"]
STANDARD_MARKER_COLUMNS = [
    "marker_start_s",
    "marker_end_s",
    "marker_id",
    "target_x",
    "target_y",
    "coordinate_space",
    "target_duration_s",
    "target_source",
    "target_detection_confidence",
    "target_detected_x",
    "target_detected_y",
    "target_frame_id",
    "target_frame_time_s",
]

GazeImporter = Callable[[Path, str, int | None, int | None], pd.DataFrame]
_CUSTOM_GAZE_IMPORTERS: list[tuple[str, Callable[[Path], bool], GazeImporter]] = []


def register_gaze_importer(
    name: str,
    predicate: Callable[[Path], bool],
    importer: GazeImporter,
) -> None:
    """Register a vendor importer ahead of the built-in tabular importer."""

    if not name.strip():
        raise ValueError("Importer name is required")
    if any(existing_name == name for existing_name, _, _ in _CUSTOM_GAZE_IMPORTERS):
        raise ValueError(f"Gaze importer is already registered: {name}")
    _CUSTOM_GAZE_IMPORTERS.append((name, predicate, importer))


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _first_matching_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    normalised = {_normalise_name(str(column)): str(column) for column in columns}
    for candidate in candidates:
        match = normalised.get(_normalise_name(candidate))
        if match is not None:
            return match
    return None


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict):
                for key in ("data", "samples", "gaze", "records"):
                    if isinstance(payload.get(key), list):
                        return pd.DataFrame(payload[key])
            if isinstance(payload, list):
                return pd.DataFrame(payload)
            return pd.DataFrame(payload)
        except (ValueError, TypeError, json.JSONDecodeError):
            return pd.read_json(path)
    separator = "\t" if suffix == ".tsv" else ","
    try:
        return pd.read_csv(path, sep=separator, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _time_to_seconds(values: pd.Series, column_name: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    name = _normalise_name(column_name)
    if "nanosecond" in name or name.endswith("ns"):
        return numeric / 1_000_000_000.0
    if "microsecond" in name or name.endswith("us"):
        return numeric / 1_000_000.0
    if "millisecond" in name or name.endswith("ms") or "timestampms" in name:
        finite = numeric.dropna().to_numpy(dtype=float)
        # Legacy files may label epoch seconds as milliseconds.
        if (
            len(finite)
            and 100_000_000 < float(np.median(np.abs(finite))) < 100_000_000_000
        ):
            return numeric
        return numeric / 1_000.0
    return numeric


def _validity(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        return (pd.to_numeric(values, errors="coerce").fillna(0) > 0).astype(int)
    normalised = values.astype("string").str.strip().str.lower()
    valid_tokens = {"1", "true", "valid", "yes", "ok", "success"}
    return normalised.isin(valid_tokens).astype(int)


def _coordinate_space(x: pd.Series, y: pd.Series, x_name: str, y_name: str) -> str:
    names = f"{x_name} {y_name}".lower()
    if "pixel" in names or "px" in names:
        return "pixels"
    normalised_names = {_normalise_name(x_name), _normalise_name(y_name)}
    if normalised_names == {"fpogx", "fpogy"}:
        return "normalised"
    combined = pd.concat([pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")]).dropna()
    if combined.empty:
        return "unknown"
    within_normalised_range = float(combined.between(-0.25, 1.25).mean()) >= 0.95
    return "normalised" if within_normalised_range else "unknown"


def _import_tabular_gaze(
    path: Path,
    source_device: str = "",
    display_width_px: int | None = None,
    display_height_px: int | None = None,
) -> pd.DataFrame:
    """Map a supported gaze table to the standard schema."""

    raw = _read_table(path)
    if raw.empty and len(raw.columns) == 0:
        return pd.DataFrame(columns=STANDARD_GAZE_COLUMNS)
    raw = raw.rename(columns={column: str(column).strip() for column in raw.columns})

    time_col = _first_matching_column(
        raw.columns,
        {
            "Time_s",
            "Time (ms)",
            "Time",
            "Timestamp",
            "Recording timestamp",
            "Device timestamp",
            "System timestamp",
            "SysTime(ms)",
            "SysTime",
        },
    )
    x_col = _first_matching_column(
        raw.columns,
        {"FPOGX", "gaze_x", "gaze x", "Gaze point X", "Gaze point X (DACSpx)", "x"},
    )
    y_col = _first_matching_column(
        raw.columns,
        {"FPOGY", "gaze_y", "gaze y", "Gaze point Y", "Gaze point Y (DACSpx)", "y"},
    )
    if time_col is None:
        raise ValueError(f"No supported time column found in {path.name}")

    left_x_col = _first_matching_column(raw.columns, {"left_gaze_x", "OD_x", "left_x"})
    left_y_col = _first_matching_column(raw.columns, {"left_gaze_y", "OD_y", "left_y"})
    right_x_col = _first_matching_column(raw.columns, {"right_gaze_x", "OS_x", "right_x"})
    right_y_col = _first_matching_column(raw.columns, {"right_gaze_y", "OS_y", "right_y"})
    if x_col is not None and y_col is not None:
        gaze_x = pd.to_numeric(raw[x_col], errors="coerce")
        gaze_y = pd.to_numeric(raw[y_col], errors="coerce")
        x_name, y_name = x_col, y_col
    else:
        x_parts = [
            pd.to_numeric(raw[column], errors="coerce")
            for column in (left_x_col, right_x_col)
            if column is not None
        ]
        y_parts = [
            pd.to_numeric(raw[column], errors="coerce")
            for column in (left_y_col, right_y_col)
            if column is not None
        ]
        if not x_parts or not y_parts:
            raise ValueError(f"No supported gaze coordinate columns found in {path.name}")
        gaze_x = pd.concat(x_parts, axis=1).mean(axis=1, skipna=True)
        gaze_y = pd.concat(y_parts, axis=1).mean(axis=1, skipna=True)
        x_name = "/".join(column for column in (left_x_col, right_x_col) if column)
        y_name = "/".join(column for column in (left_y_col, right_y_col) if column)

    valid_col = _first_matching_column(
        raw.columns,
        {"FPOGV", "valid", "validity", "gaze_valid", "Gaze point validity"},
    )
    left_valid_col = _first_matching_column(raw.columns, {"Validity left", "Left validity"})
    right_valid_col = _first_matching_column(raw.columns, {"Validity right", "Right validity"})
    left_valid = _validity(raw[left_valid_col]) if left_valid_col is not None else pd.Series(np.nan, index=raw.index)
    right_valid = (
        _validity(raw[right_valid_col]) if right_valid_col is not None else pd.Series(np.nan, index=raw.index)
    )
    if valid_col is not None:
        valid = _validity(raw[valid_col])
    elif left_valid_col is not None or right_valid_col is not None:
        validity_parts = []
        if left_valid_col is not None:
            validity_parts.append(_validity(raw[left_valid_col]))
        if right_valid_col is not None:
            validity_parts.append(_validity(raw[right_valid_col]))
        valid = pd.concat(validity_parts, axis=1).max(axis=1).astype(int)
    else:
        valid = (gaze_x.notna() & gaze_y.notna()).astype(int)

    cx_col = _first_matching_column(raw.columns, {"CX", "raw_cx", "cursor_x"})
    cy_col = _first_matching_column(raw.columns, {"CY", "raw_cy", "cursor_y"})
    device_time_col = _first_matching_column(
        raw.columns, {"device_time_s", "device_time_us", "Device timestamp", "TobiiSysTime"}
    )
    system_time_col = _first_matching_column(
        raw.columns, {"system_time_s", "system_time_us", "System timestamp", "SysTime(ms)"}
    )
    pupil_left_col = _first_matching_column(raw.columns, {"pupil_left", "left pupil diameter", "left_pupil"})
    pupil_right_col = _first_matching_column(raw.columns, {"pupil_right", "right pupil diameter", "right_pupil"})
    device = source_device.strip() or ("GP3HD" if path.name.lower() == "gp3hd_data.csv" else path.stem)
    space = _coordinate_space(gaze_x, gaze_y, x_name, y_name)
    raw_gaze_x = gaze_x.copy()
    raw_gaze_y = gaze_y.copy()
    if space == "pixels" and display_width_px and display_height_px:
        gaze_x = gaze_x / display_width_px
        gaze_y = gaze_y / display_height_px
        space = "normalised"

    def optional_time(column: str | None) -> pd.Series:
        """Return a time column or missing values."""

        if column is None:
            return pd.Series(np.nan, index=raw.index)
        return _time_to_seconds(raw[column], column)

    def optional_numeric(column: str | None) -> pd.Series:
        """Return a numeric column or missing values."""

        if column is None:
            return pd.Series(np.nan, index=raw.index)
        return pd.to_numeric(raw[column], errors="coerce")

    return pd.DataFrame(
        {
            "time_s": _time_to_seconds(raw[time_col], time_col),
            "device_time_s": optional_time(device_time_col),
            "system_time_s": optional_time(system_time_col),
            "gaze_x": gaze_x,
            "gaze_y": gaze_y,
            "valid": valid,
            "left_gaze_x": optional_numeric(left_x_col),
            "left_gaze_y": optional_numeric(left_y_col),
            "right_gaze_x": optional_numeric(right_x_col),
            "right_gaze_y": optional_numeric(right_y_col),
            "left_valid": left_valid,
            "right_valid": right_valid,
            "pupil_left": optional_numeric(pupil_left_col),
            "pupil_right": optional_numeric(pupil_right_col),
            "source_device": device,
            "raw_gaze_x": raw_gaze_x,
            "raw_gaze_y": raw_gaze_y,
            "raw_cx": pd.to_numeric(raw[cx_col], errors="coerce") if cx_col else np.nan,
            "raw_cy": pd.to_numeric(raw[cy_col], errors="coerce") if cy_col else np.nan,
            "coordinate_space": space,
        },
        columns=STANDARD_GAZE_COLUMNS,
    )


def import_gaze_file(
    path: Path,
    source_device: str = "",
    display_width_px: int | None = None,
    display_height_px: int | None = None,
) -> pd.DataFrame:
    """Import gaze samples through custom or built-in handlers."""

    for _, predicate, importer in _CUSTOM_GAZE_IMPORTERS:
        if predicate(path):
            return importer(path, source_device, display_width_px, display_height_px)
    return _import_tabular_gaze(path, source_device, display_width_px, display_height_px)


def import_video_file(path: Path) -> pd.DataFrame:
    """Import frame timestamps into the standard video schema."""

    if not path.exists():
        return pd.DataFrame(columns=STANDARD_VIDEO_COLUMNS)
    raw = _read_table(path)
    if raw.empty and len(raw.columns) == 0:
        return pd.DataFrame(columns=STANDARD_VIDEO_COLUMNS)

    time_col = _first_matching_column(raw.columns, {"Time_s", "Time (ms)", "Time", "Timestamp"})
    frame_col = _first_matching_column(raw.columns, {"FrameID", "Frame ID", "Frame", "Frame number"})
    if time_col is None:
        raise ValueError(f"No supported video time column found in {path.name}")
    frame_id = pd.to_numeric(raw[frame_col], errors="coerce") if frame_col else np.arange(len(raw))
    return pd.DataFrame(
        {"frame_id": frame_id, "time_s": _time_to_seconds(raw[time_col], time_col)},
        columns=STANDARD_VIDEO_COLUMNS,
    )


def import_marker_file(
    path: Path,
    display_width_px: int | None = None,
    display_height_px: int | None = None,
) -> pd.DataFrame:
    """Import intervals into the standard marker schema."""

    if not path.exists():
        return pd.DataFrame(columns=STANDARD_MARKER_COLUMNS)
    try:
        raw = pd.read_csv(path, header=None, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=STANDARD_MARKER_COLUMNS)
    if raw.empty:
        return pd.DataFrame(columns=STANDARD_MARKER_COLUMNS)

    first_row = " ".join(str(value) for value in raw.iloc[0].tolist()).lower()
    has_header = any(token in first_row for token in ("start", "marker", "target", "end_time"))
    if has_header:
        raw = pd.read_csv(path, encoding="utf-8-sig")
        start_col = _first_matching_column(raw.columns, {"marker_start_s", "Start_time(ms)", "start", "start_time"})
        end_col = _first_matching_column(raw.columns, {"marker_end_s", "End_time(ms)", "end", "end_time"})
        x_col = _first_matching_column(raw.columns, {"target_x", "marker_x", "x"})
        y_col = _first_matching_column(raw.columns, {"target_y", "marker_y", "y"})
        id_col = _first_matching_column(raw.columns, {"marker_id", "target_id", "id"})
    else:
        start_col = raw.columns[0] if raw.shape[1] >= 1 else None
        end_col = raw.columns[1] if raw.shape[1] >= 2 else None
        x_col = raw.columns[2] if raw.shape[1] >= 4 else None
        y_col = raw.columns[3] if raw.shape[1] >= 4 else None
        id_col = raw.columns[4] if raw.shape[1] >= 5 else None

    if start_col is None or end_col is None:
        raise ValueError(f"Marker file must contain start and end times: {path.name}")
    starts = _time_to_seconds(raw[start_col], str(start_col))
    ends = _time_to_seconds(raw[end_col], str(end_col))
    target_x = pd.to_numeric(raw[x_col], errors="coerce") if x_col is not None else pd.Series(np.nan, index=raw.index)
    target_y = pd.to_numeric(raw[y_col], errors="coerce") if y_col is not None else pd.Series(np.nan, index=raw.index)
    space = "unknown"
    finite_targets = pd.concat([target_x, target_y]).dropna()
    if not finite_targets.empty:
        if float(finite_targets.between(-0.25, 1.25).mean()) >= 0.95:
            space = "normalised"
        elif display_width_px and display_height_px:
            target_x = target_x / display_width_px
            target_y = target_y / display_height_px
            space = "normalised"
        else:
            space = "pixels"

    marker_ids = raw[id_col].astype("string") if id_col is not None else pd.Series(
        [f"target_{index + 1:02d}" for index in range(len(raw))], index=raw.index, dtype="string"
    )
    target_available = target_x.notna() & target_y.notna()
    return pd.DataFrame(
        {
            "marker_start_s": starts,
            "marker_end_s": ends,
            "marker_id": marker_ids,
            "target_x": target_x,
            "target_y": target_y,
            "coordinate_space": space,
            "target_duration_s": ends - starts,
            "target_source": np.where(target_available, "marker_file", ""),
            "target_detection_confidence": np.nan,
            "target_detected_x": np.nan,
            "target_detected_y": np.nan,
            "target_frame_id": np.nan,
            "target_frame_time_s": np.nan,
        },
        columns=STANDARD_MARKER_COLUMNS,
    )


def standardise_session(record: SessionRecord, output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Import and save all standard tables for one session."""

    session_path = Path(record.session_path)
    if not record.gaze_file:
        raise FileNotFoundError(f"No gaze file found for {record.session_id}")

    info = read_recording_info(session_path / "Recording_info.csv")
    source_device = record.device_id or info.get("EyeTrackerID", "")
    gaze = import_gaze_file(
        session_path / record.gaze_file,
        source_device=source_device,
        display_width_px=record.display_width_px,
        display_height_px=record.display_height_px,
    )
    video = import_video_file(session_path / "Video_data.csv")
    marker_path = (
        session_path / "acc_marker_external.csv"
        if (session_path / "acc_marker_external.csv").exists()
        else session_path / "marker_data.csv"
    )
    markers = import_marker_file(marker_path, record.display_width_px, record.display_height_px)

    timed_frames = (
        ("gaze", gaze, ("time_s", "system_time_s")),
        ("video", video, ("time_s",)),
        ("markers", markers, ("marker_start_s", "marker_end_s")),
    )
    epoch_columns: list[tuple[str, pd.DataFrame, str, pd.Series]] = []
    epoch_minima: list[float] = []
    for frame_name, frame, columns in timed_frames:
        for column in columns:
            if column not in frame:
                continue
            values = pd.to_numeric(frame[column], errors="coerce")
            finite = values.dropna()
            if not finite.empty and float(finite.abs().median()) > 100_000_000:
                epoch_columns.append((frame_name, frame, column, values))
                epoch_minima.append(float(finite.min()))

    time_origin_epoch_s: float | None = None
    origin_source = "not_applicable"
    if epoch_columns:
        if (
            record.recording_start_time is not None
            and np.isfinite(float(record.recording_start_time))
            and float(record.recording_start_time) > 100_000_000
        ):
            time_origin_epoch_s = float(record.recording_start_time)
            origin_source = "recording_start_time"
        else:
            time_origin_epoch_s = min(epoch_minima)
            origin_source = "inferred_earliest_epoch_timestamp"
        for _, frame, column, values in epoch_columns:
            frame[column] = values - time_origin_epoch_s

    output_dir.mkdir(parents=True, exist_ok=True)
    gaze.to_csv(output_dir / "standard_gaze.csv", index=False)
    video.to_csv(output_dir / "standard_video_timestamps.csv", index=False)
    markers.to_csv(output_dir / "standard_marker_events.csv", index=False)
    alignment = {
        "standard_time_basis": "relative_seconds",
        "time_origin_epoch_s": time_origin_epoch_s,
        "origin_source": origin_source,
        "transformed_columns": [
            {"frame": frame_name, "column": column}
            for frame_name, _, column, _ in epoch_columns
        ],
        "source_data_modified": False,
    }
    (output_dir / "time_alignment.json").write_text(
        json.dumps(alignment, indent=2), encoding="utf-8"
    )
    return gaze, video, markers
