"""Generate deterministic synthetic validation data."""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .collection import ACCURACY_TARGETS


EXAMPLE_DATES = ("2026_01_01", "2026_01_08", "2026_01_15")


def _markers(duration_s: float, repeats: int, seed: int) -> pd.DataFrame:
    targets = list(ACCURACY_TARGETS) * repeats
    random.Random(seed).shuffle(targets)
    slot = duration_s / len(targets)
    rows: list[dict[str, object]] = []
    for index, (target_id, target_x, target_y) in enumerate(targets):
        start = index * slot
        end = start + slot * 0.78
        rows.append(
            {
                "planned_start_s": start,
                "planned_end_s": end,
                "marker_start_s": start,
                "marker_end_s": end,
                "marker_id": f"{target_id}_r{index // len(ACCURACY_TARGETS) + 1}",
                "target_x": target_x,
                "target_y": target_y,
                "coordinate_space": "normalised",
                "timing_source": "synthetic_schedule",
                "onset_delay_ms": 0.0,
                "duration_error_ms": 0.0,
                "presentation_status": "simulated",
            }
        )
    return pd.DataFrame(rows)


def _target_at_time(markers: pd.DataFrame, timestamp: float) -> tuple[float, float]:
    active = markers.loc[
        (markers["marker_start_s"] <= timestamp) & (timestamp <= markers["marker_end_s"])
    ]
    if active.empty:
        return 0.5, 0.5
    return float(active.iloc[0]["target_x"]), float(active.iloc[0]["target_y"])


def _write_metadata(session: Path, payload: dict[str, object]) -> None:
    with (session / "Recording_info.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for key, value in payload.items():
            writer.writerow([key, value])
    (session / "session_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def generate_longitudinal_example(output_root: Path, overwrite: bool = False) -> Path:
    """Create synthetic validation data that is not performance evidence."""

    output_root = output_root.resolve()
    # Three-second slots retain over 100 post-settling samples at 60 Hz.
    duration_s = 81.0
    sampling_hz = 60.0
    video_fps = 30.0
    markers = _markers(duration_s, repeats=3, seed=2026)

    for session_index, date in enumerate(EXAMPLE_DATES):
        session = output_root / date / "000"
        if session.exists() and any(session.iterdir()) and not overwrite:
            raise FileExistsError(f"Example session already exists: {session}")
        session.mkdir(parents=True, exist_ok=True)

        start_epoch = datetime.strptime(date, "%Y_%m_%d").replace(
            hour=10, tzinfo=timezone.utc
        ).timestamp()
        calibration_error = 0.30 + session_index * 0.03
        metadata = {
            "SchemaVersion": "1.0",
            "OpenET2Version": __version__,
            "Recording start time": start_epoch,
            "Recording end time": start_epoch + duration_s,
            "PlannedDurationS": duration_s,
            "SubjectID": "SYNTHETIC_P01",
            "EyeTrackerID": "SYNTHETIC_GP3",
            "TestID": "Synthetic longitudinal accuracy",
            "TrialNumber": session_index + 1,
            "TestCondition": "synthetic_standard",
            "VisitLabel": f"synthetic_visit_{session_index + 1}",
            "OperatorID": "openet2_generator",
            "DeviceModel": "software_simulator",
            "DeviceSerial": "SYNTHETIC-NOT-HARDWARE",
            "DeviceSoftwareVersion": "1.0",
            "NominalSamplingHz": sampling_hz,
            "CalibrationMethod": "simulated nine-point",
            "CalibrationConfirmed": True,
            "CalibrationStatus": "simulated_pass",
            "Calibration avg error": calibration_error,
            "Calibration valid points": 9,
            "CalibrationHighQualitySamples": 180,
            "CalibrationConfidenceThreshold": 0.8,
            "CalibrationErrorUnit": "degrees",
            "CalibrationSource": "openet2_example_generator",
            "ValidationMethod": "synthetic 27-interval protocol",
            "DisplayWidthPx": 1920,
            "DisplayHeightPx": 1080,
            "DisplayWidthMm": 530,
            "DisplayHeightMm": 300,
            "ViewingDistanceMm": 600,
            "DisplayModel": "synthetic display",
            "DisplayRefreshHz": 60,
            "Environment": "synthetic; no physical environment",
            "AmbientIlluminanceLux": 0,
            "HeadSupport": "not applicable",
            "TargetPresentationS": 2.34,
            "TargetSettlingS": 0.6,
            "MinimumPostSettleValidSamples": 100,
            "Notes": "Generated example only; not measured device performance.",
            "DryRun": True,
        }
        _write_metadata(session, metadata)
        markers.to_csv(session / "marker_data.csv", index=False)
        markers.to_csv(session / "marker_plan.csv", index=False)

        rng = np.random.default_rng(2026 + session_index)
        times = np.arange(0.0, duration_s + 0.5 / sampling_hz, 1 / sampling_hz)
        bias_x = 0.002 + session_index * 0.0015
        bias_y = -0.001 - session_index * 0.001
        noise_sd = 0.004 + session_index * 0.0005
        targets = np.asarray([_target_at_time(markers, float(value)) for value in times])
        valid = np.ones(len(times), dtype=int)
        valid[::101] = 0
        gaze_x = targets[:, 0] + bias_x + rng.normal(0, noise_sd, len(times))
        gaze_y = targets[:, 1] + bias_y + rng.normal(0, noise_sd, len(times))
        gaze_x[valid == 0] = np.nan
        gaze_y[valid == 0] = np.nan
        pd.DataFrame(
            {
                "Time_s": times,
                "FPOGX": gaze_x,
                "FPOGY": gaze_y,
                "FPOGV": valid,
                "CX": targets[:, 0],
                "CY": targets[:, 1],
            }
        ).to_csv(session / "GP3HD_data.csv", index=False)

        frame_times = np.arange(0.0, duration_s + 0.5 / video_fps, 1 / video_fps)
        pd.DataFrame({"FrameID": np.arange(len(frame_times)), "Time_s": frame_times}).to_csv(
            session / "Video_data.csv", index=False
        )
        calibration = {
            "timestamp_utc": datetime.fromtimestamp(start_epoch, timezone.utc).isoformat(),
            "method": "simulated nine-point",
            "status": "simulated_pass",
            "valid_points": 9,
            "high_quality_samples": 180,
            "confidence_threshold": 0.8,
            "average_error": calibration_error,
            "unit": "degrees",
            "source": "openet2_example_generator",
        }
        (session / "Calibration_info.txt").write_text(
            json.dumps(calibration, indent=2), encoding="utf-8"
        )
        (session / "calibration_summary.json").write_text(
            json.dumps(calibration, indent=2), encoding="utf-8"
        )
        (session / "application.log").write_text(
            "Synthetic OpenET2 example; no hardware was used.\n", encoding="utf-8"
        )

    manifest = {
        "dataset_type": "synthetic_longitudinal_example",
        "physical_hardware_used": False,
        "dates": list(EXAMPLE_DATES),
        "participant_count": 1,
        "session_count": len(EXAMPLE_DATES),
        "warning": "Do not report these measurements as physical device validation.",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "SYNTHETIC_DATASET.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return output_root
