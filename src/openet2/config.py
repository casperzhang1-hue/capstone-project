"""Define validated quality thresholds."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityThresholds:
    """Auditable thresholds used to create warnings, never to delete samples."""

    min_valid_rate: float = 0.80
    max_irregular_interval_pct: float = 0.20
    interval_tolerance_fraction: float = 0.50
    expected_marker_events: int | None = 27
    max_duration_mismatch_fraction: float = 0.20
    max_out_of_bounds_rate: float = 0.01
    max_data_loss_rate: float = 0.20
    max_longest_gap_s: float = 0.25
    min_marker_coverage_rate: float = 0.80
    min_calibration_valid_points: int = 5
    max_calibration_error: float | None = 1.0
    calibration_error_unit: str = "degrees"
    max_incomplete_recording_fraction: float = 0.10
    normalised_gaze_min: float = 0.0
    normalised_gaze_max: float = 1.0

    def __post_init__(self) -> None:
        """Validate quality thresholds."""

        fractions = {
            "min_valid_rate": self.min_valid_rate,
            "max_irregular_interval_pct": self.max_irregular_interval_pct,
            "interval_tolerance_fraction": self.interval_tolerance_fraction,
            "max_duration_mismatch_fraction": self.max_duration_mismatch_fraction,
            "max_out_of_bounds_rate": self.max_out_of_bounds_rate,
            "max_data_loss_rate": self.max_data_loss_rate,
            "min_marker_coverage_rate": self.min_marker_coverage_rate,
            "max_incomplete_recording_fraction": self.max_incomplete_recording_fraction,
        }
        for name, value in fractions.items():
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.expected_marker_events is not None and self.expected_marker_events < 0:
            raise ValueError("expected_marker_events cannot be negative")
        if self.max_longest_gap_s < 0:
            raise ValueError("max_longest_gap_s cannot be negative")
        if self.min_calibration_valid_points < 0:
            raise ValueError("min_calibration_valid_points cannot be negative")
        if self.max_calibration_error is not None and self.max_calibration_error < 0:
            raise ValueError("max_calibration_error cannot be negative")
        if self.max_calibration_error is not None and not self.calibration_error_unit.strip():
            raise ValueError("calibration_error_unit is required when a calibration threshold is enabled")
        if self.normalised_gaze_min >= self.normalised_gaze_max:
            raise ValueError("normalised gaze bounds are invalid")
