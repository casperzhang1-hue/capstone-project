"""Discover sessions and normalise recording metadata."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


DATE_PATTERN = re.compile(r"^\d{4}_\d{2}_\d{2}$")
GAZE_CANDIDATES = (
    "GP3HD_data.csv",
    "Tobii_data.csv",
    "Tobii_data.tsv",
    "Tobii_data.json",
    "gaze_data.csv",
    "gaze_data.tsv",
    "gaze_data.json",
)


@dataclass(frozen=True)
class SessionRecord:
    """Portable metadata for one recording session."""

    session_id: str
    date: str
    run_id: str
    session_path: str
    subject_id: str = ""
    device_id: str = ""
    test_id: str = ""
    trial_number: int | None = None
    test_condition: str = ""
    visit_label: str = ""
    recording_start_time: float | None = None
    recording_end_time: float | None = None
    planned_duration_s: float | None = None
    operator_id: str = ""
    device_model: str = ""
    device_serial: str = ""
    device_software_version: str = ""
    nominal_sampling_hz: float | None = None
    calibration_method: str = ""
    validation_method: str = ""
    gaze_file: str = ""
    source_format: str = ""
    calibration_avg_error: float | None = None
    calibration_valid_points: int | None = None
    calibration_high_quality_samples: int | None = None
    calibration_confidence_threshold: float | None = None
    calibration_error_unit: str = ""
    calibration_status: str = ""
    calibration_source: str = ""
    display_width_px: int | None = None
    display_height_px: int | None = None
    display_width_mm: float | None = None
    display_height_mm: float | None = None
    viewing_distance_mm: float | None = None
    display_model: str = ""
    display_refresh_hz: float | None = None
    environment: str = ""
    ambient_illuminance_lux: float | None = None
    head_support: str = ""
    target_presentation_s: float | None = None
    target_settle_time_s: float | None = None
    minimum_post_settle_valid_samples: int | None = None
    notes: str = ""
    metadata_conflict_fields: str = ""
    metadata_read_error: str = ""
    has_gaze: bool = False
    has_video: bool = False
    has_recording_info: bool = False
    has_marker: bool = False
    has_calibration: bool = False
    has_log: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return serialisable session metadata."""

        return asdict(self)


def read_recording_info(path: Path) -> dict[str, str]:
    """Read the two-column key/value metadata used by existing OpenET sessions."""

    if not path.exists():
        return {}
    result: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.reader(handle):
            if len(row) >= 2 and row[0].strip():
                result[row[0].strip()] = row[1].strip()
    return result


def _normalise_metadata_key(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _metadata_values_equal(left: object, right: object) -> bool:
    left_text = str(left).strip()
    right_text = str(right).strip()
    if left_text.casefold() == right_text.casefold():
        return True
    try:
        return float(left_text) == float(right_text)
    except (TypeError, ValueError):
        return False


def _read_session_metadata_with_diagnostics(
    session_path: Path,
) -> tuple[dict[str, str], tuple[str, ...], str]:
    """Merge metadata while retaining CSV authority and conflict evidence."""

    result = read_recording_info(session_path / "Recording_info.csv")
    csv_keys = {_normalise_metadata_key(key): key for key in result}
    json_path = session_path / "session_metadata.json"
    if not json_path.exists():
        return result, (), ""
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return result, (), f"{type(error).__name__}: {error}"
    if not isinstance(payload, dict):
        return result, (), "session_metadata.json must contain a JSON object"

    conflicts: set[str] = set()
    for key, value in payload.items():
        if value is None or isinstance(value, (dict, list)):
            continue
        text_value = str(value)
        normalised_key = _normalise_metadata_key(key)
        csv_key = csv_keys.get(normalised_key)
        if csv_key is None:
            result[str(key)] = text_value
            continue
        csv_value = result[csv_key]
        if csv_value and text_value and not _metadata_values_equal(csv_value, text_value):
            conflicts.add(csv_key)
        elif not csv_value and text_value:
            result[csv_key] = text_value
    return result, tuple(sorted(conflicts, key=str.casefold)), ""


def read_session_metadata(session_path: Path) -> dict[str, str]:
    """Merge legacy CSV metadata with non-conflicting JSON fields."""

    result, _, _ = _read_session_metadata_with_diagnostics(session_path)
    return result


def _first_value(info: dict[str, str], *keys: str) -> str:
    lowered = {key.lower().replace(" ", ""): value for key, value in info.items()}
    for key in keys:
        value = lowered.get(key.lower().replace(" ", ""), "")
        if value:
            return value
    return ""


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _trial_number(info: dict[str, str], run_id: str) -> int | None:
    explicit = _optional_int(_first_value(info, "TrialNumber", "Trial Number", "Trial"))
    if explicit is not None:
        return explicit
    run_number = _optional_int(run_id)
    return run_number + 1 if run_number is not None else None


def find_gaze_file(session_path: Path) -> Path | None:
    """Find the preferred gaze file in a session directory."""

    for filename in GAZE_CANDIDATES:
        candidate = session_path / filename
        if candidate.exists():
            return candidate

    excluded = {"recording_info.csv", "video_data.csv", "acc_marker_external.csv", "marker_data.csv"}
    for candidate in sorted(session_path.iterdir()):
        if not candidate.is_file() or candidate.name.lower() in excluded:
            continue
        if candidate.suffix.lower() not in {".csv", ".tsv", ".json"}:
            continue
        if "gaze" in candidate.stem.lower() or "tobii" in candidate.stem.lower():
            return candidate
    return None


def discover_sessions(data_root: Path) -> list[SessionRecord]:
    """Discover dated sessions and return portable records."""

    if not data_root.exists():
        raise FileNotFoundError(f"Data root not found: {data_root}")
    if not data_root.is_dir():
        raise NotADirectoryError(f"Data root is not a directory: {data_root}")

    records: list[SessionRecord] = []
    date_dirs = sorted(path for path in data_root.iterdir() if path.is_dir() and DATE_PATTERN.match(path.name))
    for date_dir in date_dirs:
        run_dirs = sorted(path for path in date_dir.iterdir() if path.is_dir())
        for run_dir in run_dirs:
            info_path = run_dir / "Recording_info.csv"
            info, metadata_conflicts, metadata_read_error = _read_session_metadata_with_diagnostics(run_dir)
            gaze_path = find_gaze_file(run_dir)
            marker_path = (
                run_dir / "acc_marker_external.csv"
                if (run_dir / "acc_marker_external.csv").exists()
                else run_dir / "marker_data.csv"
            )
            source_format = ""
            if gaze_path is not None:
                source_format = "GP3HD" if gaze_path.name.lower() == "gp3hd_data.csv" else gaze_path.suffix.lower().lstrip(".")

            records.append(
                SessionRecord(
                    session_id=f"{date_dir.name}/{run_dir.name}",
                    date=date_dir.name,
                    run_id=run_dir.name,
                    session_path=str(run_dir.resolve()),
                    subject_id=_first_value(info, "SubjectID", "ParticipantID", "Participant ID"),
                    device_id=_first_value(info, "EyeTrackerID", "EyeTracker ID", "DeviceID", "Device ID"),
                    test_id=_first_value(info, "TestID", "Test ID", "ProtocolID", "Protocol ID"),
                    trial_number=_trial_number(info, run_dir.name),
                    test_condition=_first_value(info, "TestCondition", "Test Condition", "Condition"),
                    visit_label=_first_value(info, "VisitLabel", "Visit Label", "Timepoint"),
                    recording_start_time=_optional_float(
                        _first_value(
                            info,
                            "Recording start time",
                            "RecordingStartTime",
                            "StartTime",
                            "Start_time_s",
                            "Recording_start_s",
                        )
                    ),
                    recording_end_time=_optional_float(
                        _first_value(info, "Recording end time", "RecordingEndTime", "EndTime")
                    ),
                    planned_duration_s=_optional_float(
                        _first_value(info, "PlannedDurationS", "Planned Duration S", "ExpectedDurationS")
                    ),
                    operator_id=_first_value(info, "OperatorID", "Operator ID", "ResearcherID"),
                    device_model=_first_value(info, "DeviceModel", "Device Model", "EyeTrackerModel"),
                    device_serial=_first_value(info, "DeviceSerial", "Device Serial", "SerialNumber"),
                    device_software_version=_first_value(
                        info, "DeviceSoftwareVersion", "Device Software Version", "SoftwareVersion"
                    ),
                    nominal_sampling_hz=_optional_float(
                        _first_value(info, "NominalSamplingHz", "SamplingRate", "Sampling Rate")
                    ),
                    calibration_method=_first_value(
                        info, "CalibrationMethod", "Calibration Method", "CalibrationSettings"
                    ),
                    validation_method=_first_value(info, "ValidationMethod", "Validation Method"),
                    gaze_file=gaze_path.name if gaze_path else "",
                    source_format=source_format,
                    calibration_avg_error=_optional_float(_first_value(info, "Calibration avg error")),
                    calibration_valid_points=_optional_int(_first_value(info, "Calibration valid points")),
                    calibration_high_quality_samples=_optional_int(
                        _first_value(info, "CalibrationHighQualitySamples", "Calibration High Quality Samples")
                    ),
                    calibration_confidence_threshold=_optional_float(
                        _first_value(info, "CalibrationConfidenceThreshold", "Calibration Confidence Threshold")
                    ),
                    calibration_error_unit=_first_value(
                        info, "CalibrationErrorUnit", "Calibration Error Unit", "CalibrationUnit"
                    ).lower(),
                    calibration_status=_first_value(info, "CalibrationStatus", "Calibration Status"),
                    calibration_source=_first_value(info, "CalibrationSource", "Calibration Source"),
                    display_width_px=_optional_int(
                        _first_value(info, "DisplayWidthPx", "width", "display width", "screen width")
                    ),
                    display_height_px=_optional_int(
                        _first_value(info, "DisplayHeightPx", "height", "display height", "screen height")
                    ),
                    display_width_mm=_optional_float(
                        _first_value(info, "DisplayWidthMm", "Display Width Mm", "ScreenWidthMm")
                    ),
                    display_height_mm=_optional_float(
                        _first_value(info, "DisplayHeightMm", "Display Height Mm", "ScreenHeightMm")
                    ),
                    viewing_distance_mm=_optional_float(
                        _first_value(info, "ViewingDistanceMm", "Viewing Distance Mm", "ViewingDistance")
                    ),
                    display_model=_first_value(info, "DisplayModel", "Display Model", "MonitorModel", "Monitor Model"),
                    display_refresh_hz=_optional_float(
                        _first_value(info, "DisplayRefreshHz", "Display Refresh Hz", "MonitorRefreshHz")
                    ),
                    environment=_first_value(info, "Environment", "EnvironmentalConditions", "RoomConditions"),
                    ambient_illuminance_lux=_optional_float(
                        _first_value(info, "AmbientIlluminanceLux", "Ambient Illuminance Lux", "AmbientLightLux")
                    ),
                    head_support=_first_value(info, "HeadSupport", "Head Support", "SeatingSupport"),
                    target_presentation_s=_optional_float(
                        _first_value(info, "TargetPresentationS", "Target Presentation S")
                    ),
                    target_settle_time_s=_optional_float(
                        _first_value(info, "TargetSettlingS", "Target Settling S")
                    ),
                    minimum_post_settle_valid_samples=_optional_int(
                        _first_value(info, "MinimumPostSettleValidSamples", "Minimum Post Settle Valid Samples")
                    ),
                    notes=_first_value(info, "Notes", "SessionNotes"),
                    metadata_conflict_fields=";".join(metadata_conflicts),
                    metadata_read_error=metadata_read_error,
                    has_gaze=gaze_path is not None,
                    has_video=(run_dir / "Video_data.csv").exists(),
                    has_recording_info=info_path.exists() or (run_dir / "session_metadata.json").exists(),
                    has_marker=marker_path.exists(),
                    has_calibration=any(run_dir.glob("*.cal")) or (run_dir / "Calibration_info.txt").exists(),
                    has_log=(run_dir / "application.log").exists(),
                )
            )
    return records
