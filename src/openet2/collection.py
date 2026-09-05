"""Collect calibrated eye-tracking sessions through legacy adapters."""

from __future__ import annotations

import csv
import json
import logging
import math
import statistics
import queue
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .legacy import LegacyGP3Adapter, LegacyTobiiAdapter, create_session_folder


ACCURACY_TARGETS = (
    ("top_left", 0.15, 0.15),
    ("bottom_left", 0.15, 0.85),
    ("centre", 0.50, 0.50),
    ("top_right", 0.85, 0.15),
    ("bottom_right", 0.85, 0.85),
    ("inner_top_left", 0.33, 0.33),
    ("inner_bottom_left", 0.33, 0.66),
    ("inner_top_right", 0.66, 0.33),
    ("inner_bottom_right", 0.66, 0.66),
)


@dataclass(frozen=True)
class CollectionConfig:
    """Validated settings for one collection session."""

    legacy_code_root: Path
    output_root: Path
    subject_id: str
    device_id: str
    test_id: str
    duration_s: float = 30.0
    dry_run: bool = True
    manage_gazepoint_control: bool = True
    trial_number: int = 1
    test_condition: str = "standard"
    visit_label: str = ""
    operator_id: str = ""
    device_model: str = ""
    device_serial: str = ""
    device_software_version: str = ""
    nominal_sampling_hz: float = 60.0
    calibration_method: str = "manual"
    calibration_confirmed: bool = False
    calibration_result_json: Path | None = None
    validation_method: str = "nine-point accuracy protocol"
    display_width_px: int = 1920
    display_height_px: int = 1080
    display_width_mm: float | None = None
    display_height_mm: float | None = None
    viewing_distance_mm: float | None = None
    display_model: str = ""
    display_refresh_hz: float | None = None
    environment: str = ""
    ambient_illuminance_lux: float | None = None
    head_support: str = ""
    notes: str = ""
    target_presentation_s: float | None = None
    target_settle_time_s: float = 0.6
    minimum_post_settle_valid_samples: int = 100
    run_calibration: bool = True
    run_validation: bool = True
    present_stimulus: bool = True
    capture_video: bool = True
    video_monitor_id: int = 1
    video_fps: float = 30.0
    marker_repeats: int = 3
    random_seed: int = 2026

    def __post_init__(self) -> None:
        """Validate collection settings."""

        if self.duration_s <= 0:
            raise ValueError("duration_s must be positive")
        if self.nominal_sampling_hz <= 0 or self.video_fps <= 0:
            raise ValueError("sampling frequencies must be positive")
        if self.marker_repeats <= 0:
            raise ValueError("marker_repeats must be positive")
        if self.trial_number <= 0:
            raise ValueError("trial_number must be positive")
        if self.display_width_px <= 0 or self.display_height_px <= 0:
            raise ValueError("display dimensions must be positive")
        if self.display_refresh_hz is not None and (
            not math.isfinite(self.display_refresh_hz) or self.display_refresh_hz <= 0
        ):
            raise ValueError("display_refresh_hz must be a positive finite number when supplied")
        if self.ambient_illuminance_lux is not None and (
            not math.isfinite(self.ambient_illuminance_lux) or self.ambient_illuminance_lux < 0
        ):
            raise ValueError("ambient_illuminance_lux must be a non-negative finite number when supplied")
        if not math.isfinite(self.target_settle_time_s) or self.target_settle_time_s < 0:
            raise ValueError("target_settle_time_s must be a non-negative finite number")
        if self.minimum_post_settle_valid_samples <= 0:
            raise ValueError("minimum_post_settle_valid_samples must be positive")
        if self.target_presentation_s is not None:
            if not math.isfinite(self.target_presentation_s) or self.target_presentation_s <= self.target_settle_time_s:
                raise ValueError("target_presentation_s must exceed target_settle_time_s")
            target_count = len(ACCURACY_TARGETS) * self.marker_repeats
            if self.duration_s < target_count * self.target_presentation_s:
                raise ValueError("duration_s is too short for every requested target presentation")
            nominal_post_settle_samples = (
                self.target_presentation_s - self.target_settle_time_s
            ) * self.nominal_sampling_hz
            if nominal_post_settle_samples < self.minimum_post_settle_valid_samples:
                raise ValueError("target presentation cannot nominally retain the requested post-settling samples")
        for name, value in (
            ("subject_id", self.subject_id),
            ("device_id", self.device_id),
            ("test_id", self.test_id),
            ("test_condition", self.test_condition),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        if (
            not self.dry_run
            and self.run_calibration
            and not self.calibration_confirmed
            and self.calibration_result_json is None
        ):
            raise ValueError(
                "Live collection requires explicit calibration confirmation "
                "or a device calibration result JSON"
            )


@dataclass(frozen=True)
class CalibrationResult:
    """Normalised evidence that calibration was completed before collection."""

    status: str
    method: str
    valid_points: int | None
    high_quality_samples: int | None
    confidence_threshold: float | None
    average_error: float | None
    unit: str
    source: str
    timestamp_utc: str

    def to_dict(self) -> dict[str, object]:
        """Return serialisable calibration evidence."""

        return {
            "timestamp_utc": self.timestamp_utc,
            "method": self.method,
            "status": self.status,
            "valid_points": self.valid_points,
            "high_quality_samples": self.high_quality_samples,
            "confidence_threshold": self.confidence_threshold,
            "average_error": self.average_error,
            "unit": self.unit,
            "source": self.source,
        }


def _logger(session_dir: Path) -> logging.Logger:
    logger = logging.getLogger(f"openet2.collection.{session_dir.parent.name}.{session_dir.name}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(session_dir / "application.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_event(session_dir: Path, state: str, detail: str = "") -> None:
    payload = {"timestamp_utc": _utc_now(), "time_epoch_s": time.time(), "state": state, "detail": detail}
    with (session_dir / "workflow_events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _metadata(
    config: CollectionConfig,
    start_time: float,
    end_time: float | None = None,
    calibration: CalibrationResult | None = None,
) -> dict[str, object]:
    return {
        "SchemaVersion": "1.0",
        "OpenET2Version": __version__,
        "Recording start time": start_time,
        "Recording end time": end_time,
        "PlannedDurationS": config.duration_s,
        "TargetPresentationS": config.target_presentation_s,
        "TargetSettlingS": config.target_settle_time_s,
        "MinimumPostSettleValidSamples": config.minimum_post_settle_valid_samples,
        "SubjectID": config.subject_id,
        "EyeTrackerID": config.device_id,
        "TestID": config.test_id,
        "TrialNumber": config.trial_number,
        "TestCondition": config.test_condition,
        "VisitLabel": config.visit_label,
        "OperatorID": config.operator_id,
        "DeviceModel": config.device_model,
        "DeviceSerial": config.device_serial,
        "DeviceSoftwareVersion": config.device_software_version,
        "NominalSamplingHz": config.nominal_sampling_hz,
        "CalibrationMethod": config.calibration_method,
        "CalibrationConfirmed": config.calibration_confirmed,
        "ValidationMethod": config.validation_method,
        "CalibrationStatus": calibration.status if calibration else "not_run",
        "Calibration avg error": calibration.average_error if calibration else None,
        "Calibration valid points": calibration.valid_points if calibration else None,
        "CalibrationHighQualitySamples": calibration.high_quality_samples if calibration else None,
        "CalibrationConfidenceThreshold": calibration.confidence_threshold if calibration else None,
        "CalibrationErrorUnit": calibration.unit if calibration else "",
        "CalibrationSource": calibration.source if calibration else "",
        "DisplayWidthPx": config.display_width_px,
        "DisplayHeightPx": config.display_height_px,
        "DisplayWidthMm": config.display_width_mm,
        "DisplayHeightMm": config.display_height_mm,
        "ViewingDistanceMm": config.viewing_distance_mm,
        "DisplayModel": config.display_model,
        "DisplayRefreshHz": config.display_refresh_hz,
        "Environment": config.environment,
        "AmbientIlluminanceLux": config.ambient_illuminance_lux,
        "HeadSupport": config.head_support,
        "Notes": config.notes,
        "DryRun": config.dry_run,
        "LegacySourceRoot": str(config.legacy_code_root.resolve()),
    }


def _write_metadata(
    session_dir: Path,
    config: CollectionConfig,
    start_time: float,
    end_time: float | None = None,
    calibration: CalibrationResult | None = None,
) -> None:
    payload = _metadata(config, start_time, end_time, calibration)
    with (session_dir / "Recording_info.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for key, value in payload.items():
            writer.writerow([key, "" if value is None else value])
    (session_dir / "session_metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _target_timeline(config: CollectionConfig) -> list[dict[str, object]]:
    targets = list(ACCURACY_TARGETS) * config.marker_repeats
    random.Random(config.random_seed).shuffle(targets)
    if not config.present_stimulus:
        return []
    slot = config.duration_s / len(targets)
    visible = slot * 0.78 if config.target_presentation_s is None else config.target_presentation_s
    nominal_post_settle_samples = max(
        0.0, (visible - config.target_settle_time_s) * config.nominal_sampling_hz
    )
    return [
        {
            "planned_start_s": index * slot,
            "planned_end_s": min(index * slot + visible, config.duration_s),
            "marker_start_s": index * slot if config.dry_run else None,
            "marker_end_s": min(index * slot + visible, config.duration_s) if config.dry_run else None,
            "marker_id": f"{target_id}_r{index // len(ACCURACY_TARGETS) + 1}",
            "target_x": x,
            "target_y": y,
            "coordinate_space": "normalised",
            "timing_source": "simulated_schedule" if config.dry_run else "not_presented",
            "onset_delay_ms": 0.0 if config.dry_run else None,
            "duration_error_ms": 0.0 if config.dry_run else None,
            "target_settle_time_s": config.target_settle_time_s,
            "minimum_post_settle_valid_samples": config.minimum_post_settle_valid_samples,
            "nominal_post_settle_samples": nominal_post_settle_samples,
            "presentation_status": "simulated" if config.dry_run else "planned",
        }
        for index, (target_id, x, y) in enumerate(targets)
    ]


def _write_markers(path: Path, markers: list[dict[str, object]]) -> None:
    columns = [
        "planned_start_s", "planned_end_s", "marker_start_s", "marker_end_s",
        "marker_id", "target_x", "target_y", "coordinate_space", "timing_source",
        "onset_delay_ms", "duration_error_ms", "target_settle_time_s",
        "minimum_post_settle_valid_samples", "nominal_post_settle_samples", "presentation_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(markers)


def _timing_distribution(values: list[object]) -> dict[str, float | int | None]:
    numbers: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            numbers.append(number)
    if not numbers:
        return {"count": 0, "min_ms": None, "median_ms": None, "p95_ms": None, "max_ms": None}
    numbers.sort()
    p95_index = max(0, math.ceil(len(numbers) * 0.95) - 1)
    return {
        "count": len(numbers),
        "min_ms": numbers[0],
        "median_ms": statistics.median(numbers),
        "p95_ms": numbers[p95_index],
        "max_ms": numbers[-1],
    }


def _write_marker_timing_summary(session_dir: Path, markers: list[dict[str, object]]) -> None:
    """Write application-level timing evidence without implying physical pixel onset."""

    sources = sorted({str(marker.get("timing_source", "")) for marker in markers if marker.get("timing_source")})
    payload = {
        "schema_version": "1.0",
        "marker_count": len(markers),
        "completed_marker_count": sum(marker.get("presentation_status") in {"completed", "simulated"} for marker in markers),
        "timing_sources": sources,
        "onset_delay_ms": _timing_distribution([marker.get("onset_delay_ms") for marker in markers]),
        "duration_error_ms": _timing_distribution([marker.get("duration_error_ms") for marker in markers]),
        "interpretation": "Pygame flip-return and simulated schedule times are application-level markers, not physical display pixel-onset measurements.",
    }
    (session_dir / "marker_timing_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _active_target(markers: list[dict[str, object]], timestamp: float) -> tuple[float, float]:
    for marker in markers:
        if float(marker["marker_start_s"]) <= timestamp <= float(marker["marker_end_s"]):
            return float(marker["target_x"]), float(marker["target_y"])
    return 0.5, 0.5


def _write_dry_run_gaze(path: Path, config: CollectionConfig, markers: list[dict[str, object]]) -> None:
    sample_count = max(2, int(config.duration_s * config.nominal_sampling_hz) + 1)
    random_source = random.Random(config.random_seed)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Time_s", "FPOGX", "FPOGY", "FPOGV", "CX", "CY"])
        for index in range(sample_count):
            timestamp = index / config.nominal_sampling_hz
            target_x, target_y = _active_target(markers, timestamp)
            valid = 0 if index % 40 == 0 else 1
            gaze_x = target_x + random_source.gauss(0, 0.006) if valid else float("nan")
            gaze_y = target_y + random_source.gauss(0, 0.006) if valid else float("nan")
            writer.writerow([timestamp, gaze_x, gaze_y, valid, target_x, target_y])


def _write_dry_run_video(path: Path, config: CollectionConfig) -> None:
    frame_count = max(2, int(config.duration_s * config.video_fps) + 1)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["FrameID", "Time_s"])
        for frame_id in range(frame_count):
            writer.writerow([frame_id, frame_id / config.video_fps])


def _optional_calibration_number(value: object, field: str, cast: Callable[[object], object]) -> object | None:
    if value is None or value == "":
        return None
    try:
        return cast(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Calibration result field '{field}' is invalid") from error


def _resolve_calibration(config: CollectionConfig) -> CalibrationResult | None:
    """Resolve calibration evidence for the configured mode."""

    if not config.run_calibration:
        return None
    if config.dry_run:
        return CalibrationResult(
            status="simulated_pass",
            method="simulated nine-point",
            valid_points=9,
            high_quality_samples=180,
            confidence_threshold=0.8,
            average_error=0.35,
            unit="degrees",
            source="openet2_dry_run",
            timestamp_utc=_utc_now(),
        )
    if config.calibration_result_json is None:
        return CalibrationResult(
            status="researcher_confirmed",
            method=config.calibration_method,
            valid_points=None,
            high_quality_samples=None,
            confidence_threshold=None,
            average_error=None,
            unit="unknown",
            source="operator_confirmation",
            timestamp_utc=_utc_now(),
        )

    path = config.calibration_result_json
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as error:
        raise ValueError(f"Calibration result JSON was not found: {path}") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Calibration result JSON is not readable: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("Calibration result JSON must contain an object")

    status = str(payload.get("status", "")).strip().lower()
    if status not in {"pass", "passed", "valid", "success", "completed"}:
        raise ValueError("Calibration result must explicitly report a passing status")
    average_error = _optional_calibration_number(payload.get("average_error"), "average_error", float)
    valid_points = _optional_calibration_number(payload.get("valid_points"), "valid_points", int)
    high_quality_samples = _optional_calibration_number(
        payload.get("high_quality_samples", payload.get("high_quality_sample_count")),
        "high_quality_samples",
        int,
    )
    confidence_threshold = _optional_calibration_number(
        payload.get("confidence_threshold"), "confidence_threshold", float
    )
    unit = str(payload.get("unit", "")).strip().lower()
    if average_error is not None and not unit:
        raise ValueError("Calibration result with average_error must identify its unit")
    if valid_points is not None and int(valid_points) < 0:
        raise ValueError("Calibration valid_points cannot be negative")
    if high_quality_samples is not None and int(high_quality_samples) < 0:
        raise ValueError("Calibration high_quality_samples cannot be negative")
    if confidence_threshold is not None and not 0 <= float(confidence_threshold) <= 1:
        raise ValueError("Calibration confidence_threshold must be between 0 and 1")
    return CalibrationResult(
        status="device_reported_pass",
        method=str(payload.get("method") or config.calibration_method),
        valid_points=int(valid_points) if valid_points is not None else None,
        high_quality_samples=int(high_quality_samples) if high_quality_samples is not None else None,
        confidence_threshold=float(confidence_threshold) if confidence_threshold is not None else None,
        average_error=float(average_error) if average_error is not None else None,
        unit=unit or "unknown",
        source=str(payload.get("source") or path.name),
        timestamp_utc=str(payload.get("timestamp_utc") or _utc_now()),
    )

def _write_calibration(session_dir: Path, result: CalibrationResult) -> None:
    payload = result.to_dict()
    (session_dir / "calibration_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (session_dir / "Calibration_info.txt").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_validation(session_dir: Path, config: CollectionConfig, markers: list[dict[str, object]]) -> None:
    result = {
        "timestamp_utc": _utc_now(),
        "method": config.validation_method,
        "status": "simulated_pass" if config.dry_run else "recorded_for_offline_analysis",
        "target_count": len(markers),
        "target_presentation_s": config.target_presentation_s,
        "target_settle_time_s": config.target_settle_time_s,
        "minimum_post_settle_valid_samples": config.minimum_post_settle_valid_samples,
    }
    (session_dir / "validation_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def _collect_live(path: Path, config: CollectionConfig, start_monotonic: float) -> None:
    device = config.device_id.lower()
    if "gp3" in device or "gazepoint" in device:
        adapter = LegacyGP3Adapter.from_code_root(
            config.legacy_code_root,
            manage_gazepoint_control=config.manage_gazepoint_control,
        )
        columns = ["Time_s", "FPOGX", "FPOGY", "FPOGV", "CX", "CY"]
        adapter.start()
        try:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                while time.monotonic() - start_monotonic < config.duration_s:
                    sample = adapter.read_sample()
                    writer.writerow({"Time_s": time.monotonic() - start_monotonic, **sample})
        finally:
            adapter.stop()
        return

    if "tobii" in device:
        adapter = LegacyTobiiAdapter.from_code_root(config.legacy_code_root)
        columns = [
            "Time_s", "system_time_us", "device_time_us", "gaze_x", "gaze_y", "valid",
            "left_gaze_x", "left_gaze_y", "right_gaze_x", "right_gaze_y",
        ]
        adapter.start()
        try:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                while time.monotonic() - start_monotonic < config.duration_s:
                    sample = adapter.read_sample(timeout_s=min(1.0, config.duration_s))
                    writer.writerow({"Time_s": time.monotonic() - start_monotonic, **sample})
        finally:
            adapter.stop()
        return
    raise NotImplementedError(f"No live adapter is registered for device: {config.device_id}")


def _record_screen(session_dir: Path, config: CollectionConfig, start_monotonic: float, stop: threading.Event) -> None:
    """Capture a selected monitor and aligned frame timestamps in live mode."""

    import cv2
    import mss
    import numpy as np

    video_path = session_dir / "display_video.avi"
    timestamp_path = session_dir / "Video_data.csv"
    with mss.mss() as capture:
        if config.video_monitor_id < 1 or config.video_monitor_id >= len(capture.monitors):
            raise ValueError(f"Video monitor {config.video_monitor_id} is unavailable")
        monitor = capture.monitors[config.video_monitor_id]
        size = (int(monitor["width"]), int(monitor["height"]))
        writer = cv2.VideoWriter(
            str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), config.video_fps, size
        )
        if not writer.isOpened():
            raise RuntimeError(f"Could not open video writer: {video_path}")
        try:
            with timestamp_path.open("w", newline="", encoding="utf-8") as handle:
                csv_writer = csv.writer(handle)
                csv_writer.writerow(["FrameID", "Time_s"])
                frame_id = 0
                next_frame = start_monotonic
                while not stop.is_set() and time.monotonic() - start_monotonic < config.duration_s:
                    now = time.monotonic()
                    if now < next_frame:
                        time.sleep(min(next_frame - now, 0.005))
                        continue
                    frame = np.asarray(capture.grab(monitor))[:, :, :3]
                    writer.write(frame)
                    csv_writer.writerow([frame_id, now - start_monotonic])
                    frame_id += 1
                    next_frame += 1.0 / config.video_fps
        finally:
            writer.release()


def _present_targets(
    config: CollectionConfig,
    markers: list[dict[str, object]],
    start_monotonic: float,
    stop: threading.Event,
) -> None:
    """Present targets and record application-level display flip timestamps."""

    import pygame

    pygame.init()
    screen = pygame.display.set_mode((config.display_width_px, config.display_height_px))
    pygame.display.set_caption("OpenET 2 validation stimulus")
    try:
        for marker in markers:
            planned_start = float(marker["planned_start_s"])
            planned_end = float(marker["planned_end_s"])
            while not stop.is_set() and time.monotonic() - start_monotonic < planned_start:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        marker["presentation_status"] = "operator_aborted"
                        return
                time.sleep(0.002)
            if stop.is_set():
                marker["presentation_status"] = "recording_stopped"
                return
            screen.fill((245, 245, 245))
            position = (
                int(float(marker["target_x"]) * config.display_width_px),
                int(float(marker["target_y"]) * config.display_height_px),
            )
            pygame.draw.circle(screen, (30, 30, 30), position, 18)
            pygame.draw.circle(screen, (220, 55, 55), position, 5)
            pygame.display.flip()
            actual_start = time.monotonic() - start_monotonic
            marker["marker_start_s"] = actual_start
            marker["timing_source"] = "pygame_flip_return"
            marker["onset_delay_ms"] = (actual_start - planned_start) * 1000
            marker["presentation_status"] = "presented"
            while not stop.is_set() and time.monotonic() - start_monotonic < planned_end:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        marker["presentation_status"] = "operator_aborted"
                        return
                time.sleep(0.002)
            screen.fill((245, 245, 245))
            pygame.display.flip()
            actual_end = time.monotonic() - start_monotonic
            marker["marker_end_s"] = actual_end
            marker["duration_error_ms"] = (
                (actual_end - actual_start) - (planned_end - planned_start)
            ) * 1000
            marker["presentation_status"] = "completed"
    finally:
        pygame.quit()


def _worker_entry(
    errors: queue.Queue[Exception],
    target: Callable[..., None],
    *args: object,
) -> None:
    try:
        target(*args)
    except Exception as error:
        errors.put(error)


def collect_session(config: CollectionConfig) -> Path:
    """Run the calibration, validation, and recording workflow."""

    calibration = _resolve_calibration(config)
    session_dir = create_session_folder(config.legacy_code_root, config.output_root)
    logger = _logger(session_dir)
    start_epoch = time.time()
    _write_metadata(session_dir, config, start_epoch, calibration=calibration)
    _record_event(session_dir, "session_created")
    try:
        markers = _target_timeline(config)
        if config.run_calibration:
            _record_event(session_dir, "calibration_started", config.calibration_method)
            assert calibration is not None
            _write_calibration(session_dir, calibration)
            _record_event(session_dir, "calibration_completed")

        if config.run_validation:
            _record_event(session_dir, "validation_started", config.validation_method)
            _write_validation(session_dir, config, markers)
            _record_event(session_dir, "validation_ready", f"{len(markers)} targets")

        _write_markers(session_dir / "marker_plan.csv", markers)
        _record_event(session_dir, "recording_started", "dry-run" if config.dry_run else config.device_id)
        start_monotonic = time.monotonic()
        if config.dry_run:
            gaze_name = "Tobii_data.csv" if "tobii" in config.device_id.lower() else "GP3HD_data.csv"
            _write_dry_run_gaze(session_dir / gaze_name, config, markers)
            if config.capture_video:
                _write_dry_run_video(session_dir / "Video_data.csv", config)
        else:
            stop_video = threading.Event()
            worker_errors: queue.Queue[Exception] = queue.Queue()
            workers: list[threading.Thread] = []
            if config.capture_video:
                workers.append(
                    threading.Thread(
                        target=_worker_entry,
                        args=(worker_errors, _record_screen, session_dir, config, start_monotonic, stop_video),
                        daemon=True,
                        name="openet2-video",
                    )
                )
            if config.present_stimulus:
                workers.append(
                    threading.Thread(
                        target=_worker_entry,
                        args=(worker_errors, _present_targets, config, markers, start_monotonic, stop_video),
                        daemon=True,
                        name="openet2-stimulus",
                    )
                )
            for worker in workers:
                worker.start()
            gaze_name = "Tobii_data.csv" if "tobii" in config.device_id.lower() else "GP3HD_data.csv"
            try:
                _collect_live(session_dir / gaze_name, config, start_monotonic)
            finally:
                stop_video.set()
                for worker in workers:
                    worker.join(timeout=5)
                _write_markers(session_dir / "marker_data.csv", markers)
                unfinished = [worker.name for worker in workers if worker.is_alive()]
                if unfinished:
                    raise RuntimeError(f"Collection workers did not stop: {', '.join(unfinished)}")
                if not worker_errors.empty():
                    error = worker_errors.get_nowait()
                    raise RuntimeError(f"Collection worker failed: {type(error).__name__}: {error}") from error

        if config.dry_run:
            _write_markers(session_dir / "marker_data.csv", markers)
        _write_marker_timing_summary(session_dir, markers)
        _record_event(session_dir, "recording_stopped")
        _record_event(session_dir, "session_completed")
        _record_event(session_dir, "completed")
        _write_metadata(session_dir, config, start_epoch, time.time(), calibration)
        logger.info("Collection completed")
        return session_dir
    except Exception as error:
        _record_event(session_dir, "session_failed", f"{type(error).__name__}: {error}")
        _write_metadata(session_dir, config, start_epoch, time.time(), calibration)
        logger.exception("Collection failed")
        raise
    finally:
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
