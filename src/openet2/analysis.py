"""Compute eye-tracking metrics and quality indicators."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from .config import QualityThresholds
from .metadata import SessionRecord


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def duration_s(times: pd.Series) -> float:
    """Return the span of valid timestamps in seconds."""

    values = _numeric(times).dropna()
    if len(values) < 2:
        return float("nan")
    return float(values.max() - values.min())


def interval_statistics(times: pd.Series, tolerance_fraction: float = 0.50) -> dict[str, float]:
    """Summarise sampling intervals and timing gaps."""

    values = _numeric(times).dropna().to_numpy(dtype=float)
    result = {
        "duplicate_timestamps": 0.0,
        "negative_time_jumps": 0.0,
        "median_interval_ms": float("nan"),
        "p95_interval_ms": float("nan"),
        "sampling_jitter_ms": float("nan"),
        "sampling_interval_cv": float("nan"),
        "irregular_interval_pct": float("nan"),
        "estimated_missing_samples": 0.0,
        "longest_gap_s": float("nan"),
    }
    if len(values) < 2:
        return result

    diffs = np.diff(values)
    result["duplicate_timestamps"] = float(np.sum(diffs == 0))
    result["negative_time_jumps"] = float(np.sum(diffs < 0))
    positive = diffs[diffs > 0]
    if len(positive) == 0:
        return result

    median = float(np.median(positive))
    result["median_interval_ms"] = median * 1000.0
    result["p95_interval_ms"] = float(np.percentile(positive, 95)) * 1000.0
    result["sampling_jitter_ms"] = float(np.std(positive)) * 1000.0
    result["sampling_interval_cv"] = float(np.std(positive) / median) if median > 0 else float("nan")
    result["longest_gap_s"] = float(np.max(positive))
    if median > 0:
        result["irregular_interval_pct"] = float(
            np.mean(np.abs(positive - median) > median * tolerance_fraction)
        )
        expected_steps = np.maximum(np.rint(positive / median).astype(int), 1)
        result["estimated_missing_samples"] = float(np.maximum(expected_steps - 1, 0).sum())
    return result


def effective_sampling_hz(times: pd.Series) -> float:
    """Estimate sampling frequency from valid timestamps."""

    values = _numeric(times).dropna()
    duration = duration_s(values)
    if len(values) < 2 or not np.isfinite(duration) or duration <= 0:
        return float("nan")
    return float((len(values) - 1) / duration)


def _valid_mask(gaze: pd.DataFrame) -> pd.Series:
    if gaze.empty:
        return pd.Series(dtype=bool, index=gaze.index)
    valid = _numeric(gaze.get("valid", pd.Series(0, index=gaze.index))).fillna(0) > 0
    coordinates = (
        _numeric(gaze.get("gaze_x", pd.Series(np.nan, index=gaze.index))).notna()
        & _numeric(gaze.get("gaze_y", pd.Series(np.nan, index=gaze.index))).notna()
    )
    return valid & coordinates


def _data_loss(total: int, valid_samples: int, estimated_missing: int) -> float:
    expected = total + estimated_missing
    return float((total - valid_samples + estimated_missing) / expected) if expected else float("nan")


def _visual_angle_deg(record: SessionRecord | None, dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    if (
        record is None
        or record.display_width_mm is None
        or record.display_height_mm is None
        or record.viewing_distance_mm is None
        or record.viewing_distance_mm <= 0
    ):
        return np.full(np.broadcast(dx, dy).shape, np.nan, dtype=float)
    radial_mm = np.sqrt((dx * record.display_width_mm) ** 2 + (dy * record.display_height_mm) ** 2)
    return np.degrees(np.arctan2(radial_mm, record.viewing_distance_mm))


TARGET_METRIC_COLUMNS = [
    "session_id", "date", "subject_id", "device_id", "test_id", "test_condition",
    "recording_start_time", "trial_number", "marker_index", "marker_id", "target_key",
    "target_label", "marker_start_s", "analysis_start_s", "marker_end_s",
    "target_settle_time_s", "settle_excluded_valid_samples", "valid_samples", "coordinate_space",
    "paper_qc_status", "paper_qc_valid_samples", "paper_qc_excluded_samples",
    "paper_qc_mean_gaze_x", "paper_qc_mean_gaze_y",
    "paper_qc_gaze_direction_x_normalised", "paper_qc_gaze_direction_y_normalised",
    "paper_qc_gaze_direction_x_deg", "paper_qc_gaze_direction_y_deg",
    "paper_qc_omae_normalised", "paper_qc_precision_rms_normalised",
    "paper_qc_omae_deg", "paper_qc_precision_rms_deg", "target_x", "target_y",
    "mean_gaze_x", "mean_gaze_y", "target_x_centered", "target_y_centered",
    "gaze_direction_x_normalised", "gaze_direction_y_normalised", "error_x_normalised",
    "error_y_normalised", "centroid_error_normalised", "omae_normalised",
    "precision_rms_normalised", "target_eccentricity_normalised", "target_x_deg", "target_y_deg", "gaze_direction_x_deg",
    "gaze_direction_y_deg", "error_x_deg", "error_y_deg", "centroid_error_deg", "omae_deg",
    "precision_rms_deg", "target_eccentricity_deg",
]

TARGET_VISIT_COLUMNS = [
    "session_id", "date", "subject_id", "device_id", "test_id", "test_condition",
    "recording_start_time", "trial_number", "visit_index", "visit_label", "target_key",
    "target_label", "interval_count", "target_settle_time_s", "settle_excluded_valid_samples",
    "valid_samples", "coordinate_space", "paper_qc_status", "paper_qc_interval_count",
    "paper_qc_valid_samples", "paper_qc_excluded_samples", "paper_qc_mean_gaze_x",
    "paper_qc_mean_gaze_y", "paper_qc_gaze_direction_x_normalised",
    "paper_qc_gaze_direction_y_normalised", "paper_qc_gaze_direction_x_deg",
    "paper_qc_gaze_direction_y_deg", "paper_qc_omae_normalised",
    "paper_qc_precision_rms_normalised", "paper_qc_omae_deg",
    "paper_qc_precision_rms_deg", "paper_plot_status", "paper_plot_nearest_target_key",
    "paper_plot_error_normalised", "paper_plot_cutoff_normalised", "target_x", "target_y", "mean_gaze_x",
    "mean_gaze_y", "target_x_centered", "target_y_centered", "gaze_direction_x_normalised",
    "gaze_direction_y_normalised", "error_x_normalised", "error_y_normalised",
    "centroid_error_normalised", "omae_normalised", "precision_rms_normalised",
    "target_eccentricity_normalised", "target_x_deg", "target_y_deg", "gaze_direction_x_deg",
    "gaze_direction_y_deg", "error_x_deg", "error_y_deg", "centroid_error_deg", "omae_deg",
    "precision_rms_deg", "target_eccentricity_deg",
]


def _apply_paper_plot_qc(summary: pd.DataFrame) -> pd.DataFrame:
    """Flag mislabeled-target and robust centroid outliers for the paper-style plot."""

    result = summary.copy()
    gaze_x = pd.to_numeric(result["paper_qc_gaze_direction_x_normalised"], errors="coerce")
    gaze_y = pd.to_numeric(result["paper_qc_gaze_direction_y_normalised"], errors="coerce")
    target_x = pd.to_numeric(result["target_x_centered"], errors="coerce")
    target_y = pd.to_numeric(result["target_y_centered"], errors="coerce")
    result["paper_plot_error_normalised"] = np.hypot(gaze_x - target_x, gaze_y - target_y)
    result["paper_plot_cutoff_normalised"] = np.nan
    result["paper_plot_nearest_target_key"] = ""
    result["paper_plot_status"] = result["paper_qc_status"].astype(str)

    eligible = result["paper_qc_status"].eq("included") & np.isfinite(
        result["paper_plot_error_normalised"]
    )
    if not eligible.any():
        return result

    target_table = (
        result.loc[eligible, ["target_key", "target_x_centered", "target_y_centered"]]
        .drop_duplicates("target_key")
        .reset_index(drop=True)
    )
    target_coordinates = target_table[["target_x_centered", "target_y_centered"]].to_numpy(
        dtype=float
    )
    eligible_index = result.index[eligible]
    gaze_coordinates = result.loc[
        eligible_index,
        ["paper_qc_gaze_direction_x_normalised", "paper_qc_gaze_direction_y_normalised"],
    ].to_numpy(dtype=float)
    distances = np.linalg.norm(
        gaze_coordinates[:, np.newaxis, :] - target_coordinates[np.newaxis, :, :], axis=2
    )
    nearest_indices = np.argmin(distances, axis=1)
    nearest_keys = target_table.loc[nearest_indices, "target_key"].to_numpy(dtype=str)
    result.loc[eligible_index, "paper_plot_nearest_target_key"] = nearest_keys
    assigned_keys = result.loc[eligible_index, "target_key"].astype(str).to_numpy()
    own_target_is_nearest = assigned_keys == nearest_keys
    result.loc[eligible_index[~own_target_is_nearest], "paper_plot_status"] = "target_mismatch"

    robust_candidates = eligible.copy()
    robust_candidates.loc[eligible_index] = own_target_is_nearest
    for target_key, group in result.loc[robust_candidates].groupby("target_key"):
        errors = pd.to_numeric(group["paper_plot_error_normalised"], errors="coerce").dropna()
        if errors.empty:
            continue
        if len(errors) < 5:
            cutoff = float(errors.max())
        else:
            median = float(errors.median())
            mad = float((errors - median).abs().median())
            cutoff = float(errors.max()) if mad <= 1e-12 else median + 3.5 * 1.4826 * mad
        target_rows = eligible & result["target_key"].eq(target_key)
        result.loc[target_rows, "paper_plot_cutoff_normalised"] = cutoff
        candidate_rows = robust_candidates & result["target_key"].eq(target_key)
        outliers = candidate_rows & result["paper_plot_error_normalised"].gt(cutoff)
        result.loc[candidate_rows, "paper_plot_status"] = "included"
        result.loc[outliers, "paper_plot_status"] = "robust_centroid_outlier"
    return result


def _signed_visual_angle_components(
    record: SessionRecord,
    dx: np.ndarray,
    dy: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return Cartesian visual angles; positive Y points upward on plots."""

    if (
        record.display_width_mm is None
        or record.display_height_mm is None
        or record.viewing_distance_mm is None
        or record.viewing_distance_mm <= 0
    ):
        shape = np.broadcast(dx, dy).shape
        empty = np.full(shape, np.nan, dtype=float)
        return empty.copy(), empty
    horizontal = np.degrees(
        np.arctan2(np.asarray(dx, dtype=float) * record.display_width_mm, record.viewing_distance_mm)
    )
    vertical = -np.degrees(
        np.arctan2(np.asarray(dy, dtype=float) * record.display_height_mm, record.viewing_distance_mm)
    )
    return horizontal, vertical


def target_level_metrics(
    record: SessionRecord,
    gaze: pd.DataFrame,
    markers: pd.DataFrame,
    settle_time_s: float = 0.0,
) -> pd.DataFrame:
    """Calculate one paper-aligned accuracy row per covered marker interval."""

    settle_time_s = float(settle_time_s)
    if not np.isfinite(settle_time_s) or settle_time_s < 0:
        raise ValueError("settle_time_s must be a finite non-negative number")

    if gaze.empty or markers.empty or "time_s" not in gaze:
        return pd.DataFrame(columns=TARGET_METRIC_COLUMNS)
    valid_gaze = gaze.loc[_valid_mask(gaze), ["time_s", "gaze_x", "gaze_y"]].copy()
    valid_gaze = valid_gaze.apply(pd.to_numeric, errors="coerce").dropna()
    if valid_gaze.empty:
        return pd.DataFrame(columns=TARGET_METRIC_COLUMNS)
    coordinate_space = "unknown"
    if "coordinate_space" in gaze:
        spaces = gaze["coordinate_space"].dropna().astype(str).str.strip().str.lower()
        if not spaces.empty:
            coordinate_space = str(spaces.mode().iloc[0])

    rows: list[dict[str, object]] = []
    for marker_index, (_, marker) in enumerate(markers.iterrows()):
        start = pd.to_numeric(pd.Series([marker.get("marker_start_s")]), errors="coerce").iloc[0]
        end = pd.to_numeric(pd.Series([marker.get("marker_end_s")]), errors="coerce").iloc[0]
        target_x = pd.to_numeric(pd.Series([marker.get("target_x")]), errors="coerce").iloc[0]
        target_y = pd.to_numeric(pd.Series([marker.get("target_y")]), errors="coerce").iloc[0]
        if not all(np.isfinite(value) for value in (start, end, target_x, target_y)) or end < start:
            continue
        analysis_start = float(start + settle_time_s)
        interval_samples = valid_gaze[valid_gaze["time_s"].between(start, end)]
        excluded_samples = interval_samples[interval_samples["time_s"] < analysis_start]
        samples = interval_samples[interval_samples["time_s"] >= analysis_start]
        if len(samples) < 5:
            continue

        x = samples["gaze_x"].to_numpy(dtype=float)
        y = samples["gaze_y"].to_numpy(dtype=float)
        mean_x = float(np.mean(x))
        mean_y = float(np.mean(y))
        error_x_normalised = mean_x - target_x
        error_y_normalised = -(mean_y - target_y)
        radial_errors_normalised = np.hypot(x - target_x, y - target_y)
        precision_normalised = np.hypot(x - mean_x, y - mean_y)
        target_x_centered = target_x - 0.5
        target_y_centered = -(target_y - 0.5)
        gaze_x_normalised = mean_x - 0.5
        gaze_y_normalised = -(mean_y - 0.5)
        centroid_error_normalised = float(np.hypot(error_x_normalised, error_y_normalised))
        omae_normalised = float(np.mean(radial_errors_normalised))
        precision_rms_normalised = float(np.sqrt(np.mean(np.square(precision_normalised))))
        eccentricity_normalised = float(np.hypot(target_x - 0.5, target_y - 0.5))
        if coordinate_space == "normalised":
            paper_samples = samples[
                samples["gaze_x"].between(0.0, 1.0)
                & samples["gaze_y"].between(0.0, 1.0)
            ]
            paper_qc_status = (
                "included" if len(paper_samples) >= 5 else "insufficient_in_bounds_samples"
            )
        else:
            paper_samples = samples.iloc[0:0]
            paper_qc_status = "unknown_coordinate_space"
        if paper_qc_status == "included":
            paper_qc_valid_samples = len(paper_samples)
            paper_x = paper_samples["gaze_x"].to_numpy(dtype=float)
            paper_y = paper_samples["gaze_y"].to_numpy(dtype=float)
            paper_qc_mean_x = float(np.mean(paper_x))
            paper_qc_mean_y = float(np.mean(paper_y))
            paper_qc_gaze_x_normalised = paper_qc_mean_x - 0.5
            paper_qc_gaze_y_normalised = -(paper_qc_mean_y - 0.5)
            paper_qc_radial_normalised = np.hypot(paper_x - target_x, paper_y - target_y)
            paper_qc_precision_normalised = np.hypot(
                paper_x - paper_qc_mean_x, paper_y - paper_qc_mean_y
            )
            paper_qc_omae_normalised = float(np.mean(paper_qc_radial_normalised))
            paper_qc_precision_rms_normalised = float(
                np.sqrt(np.mean(np.square(paper_qc_precision_normalised)))
            )
            paper_qc_gaze_x_deg, paper_qc_gaze_y_deg = _signed_visual_angle_components(
                record,
                np.asarray([paper_qc_mean_x - 0.5]),
                np.asarray([paper_qc_mean_y - 0.5]),
            )
            paper_qc_gaze_x_deg_value = float(paper_qc_gaze_x_deg[0])
            paper_qc_gaze_y_deg_value = float(paper_qc_gaze_y_deg[0])
            paper_qc_radial_deg = _visual_angle_deg(
                record, paper_x - target_x, paper_y - target_y
            )
            paper_qc_precision_deg_values = _visual_angle_deg(
                record, paper_x - paper_qc_mean_x, paper_y - paper_qc_mean_y
            )
            paper_qc_omae_deg = (
                float(np.mean(paper_qc_radial_deg[np.isfinite(paper_qc_radial_deg)]))
                if np.isfinite(paper_qc_radial_deg).any() else float("nan")
            )
            paper_qc_precision_rms_deg = (
                float(np.sqrt(np.mean(np.square(
                    paper_qc_precision_deg_values[np.isfinite(paper_qc_precision_deg_values)]
                ))))
                if np.isfinite(paper_qc_precision_deg_values).any() else float("nan")
            )
        else:
            paper_qc_valid_samples = 0
            paper_qc_mean_x = float("nan")
            paper_qc_mean_y = float("nan")
            paper_qc_gaze_x_normalised = float("nan")
            paper_qc_gaze_y_normalised = float("nan")
            paper_qc_gaze_x_deg_value = float("nan")
            paper_qc_gaze_y_deg_value = float("nan")
            paper_qc_omae_normalised = float("nan")
            paper_qc_precision_rms_normalised = float("nan")
            paper_qc_omae_deg = float("nan")
            paper_qc_precision_rms_deg = float("nan")
        paper_qc_excluded_samples = len(samples) - paper_qc_valid_samples
        error_x_deg, error_y_deg = _signed_visual_angle_components(
            record, np.asarray([mean_x - target_x]), np.asarray([mean_y - target_y])
        )
        target_x_deg, target_y_deg = _signed_visual_angle_components(
            record, np.asarray([target_x - 0.5]), np.asarray([target_y - 0.5])
        )
        gaze_x_deg, gaze_y_deg = _signed_visual_angle_components(
            record, np.asarray([mean_x - 0.5]), np.asarray([mean_y - 0.5])
        )
        radial_errors = _visual_angle_deg(record, x - target_x, y - target_y)
        centroid_error = _visual_angle_deg(
            record, np.asarray([mean_x - target_x]), np.asarray([mean_y - target_y])
        )[0]
        precision = _visual_angle_deg(record, x - mean_x, y - mean_y)
        eccentricity = _visual_angle_deg(
            record, np.asarray([target_x - 0.5]), np.asarray([target_y - 0.5])
        )[0]
        marker_id = str(marker.get("marker_id") or f"target_{marker_index + 1:02d}")
        target_label = re.sub(r"_r\d+$", "", marker_id)
        target_key = f"{target_x:.6f},{target_y:.6f}"
        omae = float(np.mean(radial_errors[np.isfinite(radial_errors)])) if np.isfinite(radial_errors).any() else float("nan")
        precision_rms = (
            float(np.sqrt(np.mean(np.square(precision[np.isfinite(precision)]))))
            if np.isfinite(precision).any()
            else float("nan")
        )
        rows.append(
            {
                "session_id": record.session_id,
                "date": record.date,
                "subject_id": record.subject_id,
                "device_id": record.device_id,
                "test_id": record.test_id,
                "test_condition": record.test_condition,
                "recording_start_time": record.recording_start_time,
                "trial_number": record.trial_number,
                "marker_index": marker_index,
                "marker_id": marker_id,
                "target_key": target_key,
                "target_label": target_label,
                "marker_start_s": float(start),
                "analysis_start_s": analysis_start,
                "marker_end_s": float(end),
                "target_settle_time_s": settle_time_s,
                "settle_excluded_valid_samples": len(excluded_samples),
                "valid_samples": len(samples),
                "coordinate_space": coordinate_space,
                "paper_qc_status": paper_qc_status,
                "paper_qc_valid_samples": paper_qc_valid_samples,
                "paper_qc_excluded_samples": paper_qc_excluded_samples,
                "paper_qc_mean_gaze_x": paper_qc_mean_x,
                "paper_qc_mean_gaze_y": paper_qc_mean_y,
                "paper_qc_gaze_direction_x_normalised": paper_qc_gaze_x_normalised,
                "paper_qc_gaze_direction_y_normalised": paper_qc_gaze_y_normalised,
                "paper_qc_gaze_direction_x_deg": paper_qc_gaze_x_deg_value,
                "paper_qc_gaze_direction_y_deg": paper_qc_gaze_y_deg_value,
                "paper_qc_omae_normalised": paper_qc_omae_normalised,
                "paper_qc_precision_rms_normalised": paper_qc_precision_rms_normalised,
                "paper_qc_omae_deg": paper_qc_omae_deg,
                "paper_qc_precision_rms_deg": paper_qc_precision_rms_deg,
                "target_x": float(target_x),
                "target_y": float(target_y),
                "mean_gaze_x": mean_x,
                "mean_gaze_y": mean_y,
                "target_x_centered": float(target_x_centered),
                "target_y_centered": float(target_y_centered),
                "gaze_direction_x_normalised": float(gaze_x_normalised),
                "gaze_direction_y_normalised": float(gaze_y_normalised),
                "error_x_normalised": float(error_x_normalised),
                "error_y_normalised": float(error_y_normalised),
                "centroid_error_normalised": centroid_error_normalised,
                "omae_normalised": omae_normalised,
                "precision_rms_normalised": precision_rms_normalised,
                "target_eccentricity_normalised": eccentricity_normalised,
                "target_x_deg": float(target_x_deg[0]),
                "target_y_deg": float(target_y_deg[0]),
                "gaze_direction_x_deg": float(gaze_x_deg[0]),
                "gaze_direction_y_deg": float(gaze_y_deg[0]),
                "error_x_deg": float(error_x_deg[0]),
                "error_y_deg": float(error_y_deg[0]),
                "centroid_error_deg": float(centroid_error),
                "omae_deg": omae,
                "precision_rms_deg": precision_rms,
                "target_eccentricity_deg": float(eccentricity),
            }
        )
    return pd.DataFrame(rows, columns=TARGET_METRIC_COLUMNS)


def build_target_visit_summary(target_metrics: pd.DataFrame) -> pd.DataFrame:
    """Collapse repeated target intervals to one participant/visit/target observation."""

    if target_metrics.empty:
        return pd.DataFrame(columns=TARGET_VISIT_COLUMNS)
    table = target_metrics.copy()
    required_numeric = [
        "target_x", "target_y", "target_x_centered", "target_y_centered",
        "gaze_direction_x_normalised", "gaze_direction_y_normalised", "error_x_normalised",
        "error_y_normalised", "centroid_error_normalised", "omae_normalised",
        "precision_rms_normalised", "target_eccentricity_normalised",
    ]
    for column in required_numeric:
        table[column] = pd.to_numeric(table.get(column), errors="coerce")
    table["target_settle_time_s"] = pd.to_numeric(
        table.get("target_settle_time_s", pd.Series(0.0, index=table.index)), errors="coerce"
    ).fillna(0.0)
    table["settle_excluded_valid_samples"] = pd.to_numeric(
        table.get("settle_excluded_valid_samples", pd.Series(0, index=table.index)), errors="coerce"
    ).fillna(0)
    table["coordinate_space"] = (
        table.get("coordinate_space", pd.Series("unknown", index=table.index))
        .fillna("unknown")
        .astype(str)
        .str.strip()
        .str.lower()
        .replace("", "unknown")
    )
    paper_qc_numeric = [
        "paper_qc_valid_samples", "paper_qc_excluded_samples", "paper_qc_mean_gaze_x",
        "paper_qc_mean_gaze_y", "paper_qc_gaze_direction_x_normalised",
        "paper_qc_gaze_direction_y_normalised", "paper_qc_gaze_direction_x_deg",
        "paper_qc_gaze_direction_y_deg", "paper_qc_omae_normalised",
        "paper_qc_precision_rms_normalised", "paper_qc_omae_deg",
        "paper_qc_precision_rms_deg",
    ]
    for column in paper_qc_numeric:
        table[column] = pd.to_numeric(
            table.get(column, pd.Series(np.nan, index=table.index)), errors="coerce"
        )
    table["paper_qc_status"] = table.get(
        "paper_qc_status", pd.Series("not_evaluated", index=table.index)
    ).fillna("not_evaluated").astype(str)
    paper_included = table["paper_qc_status"].eq("included")
    table["_paper_qc_interval_count"] = paper_included.astype(int)
    table["paper_qc_valid_samples"] = table["paper_qc_valid_samples"].fillna(0)
    table["paper_qc_excluded_samples"] = table["paper_qc_excluded_samples"].fillna(0)
    weighted_columns = {
        "paper_qc_mean_gaze_x": "_paper_qc_mean_gaze_x_sum",
        "paper_qc_mean_gaze_y": "_paper_qc_mean_gaze_y_sum",
        "paper_qc_gaze_direction_x_normalised": "_paper_qc_gaze_x_normalised_sum",
        "paper_qc_gaze_direction_y_normalised": "_paper_qc_gaze_y_normalised_sum",
        "paper_qc_gaze_direction_x_deg": "_paper_qc_gaze_x_deg_sum",
        "paper_qc_gaze_direction_y_deg": "_paper_qc_gaze_y_deg_sum",
        "paper_qc_omae_normalised": "_paper_qc_omae_normalised_sum",
        "paper_qc_omae_deg": "_paper_qc_omae_deg_sum",
    }
    for source, weighted in weighted_columns.items():
        table[weighted] = (
            table[source] * table["paper_qc_valid_samples"]
        ).where(paper_included)
    table["_paper_qc_precision_normalised_sq_sum"] = (
        np.square(table["paper_qc_precision_rms_normalised"])
        * table["paper_qc_valid_samples"]
    ).where(paper_included)
    table["_paper_qc_precision_deg_sq_sum"] = (
        np.square(table["paper_qc_precision_rms_deg"])
        * table["paper_qc_valid_samples"]
    ).where(paper_included)
    angular_numeric = [
        "target_x_deg", "target_y_deg", "gaze_direction_x_deg", "gaze_direction_y_deg",
        "error_x_deg", "error_y_deg", "centroid_error_deg", "omae_deg",
        "precision_rms_deg", "target_eccentricity_deg",
    ]
    for column in angular_numeric:
        table[column] = pd.to_numeric(table.get(column), errors="coerce")
    table = table.dropna(subset=required_numeric)
    if table.empty:
        return pd.DataFrame(columns=TARGET_VISIT_COLUMNS)
    for column in ("subject_id", "device_id", "test_id", "test_condition"):
        table[column] = table[column].fillna("").replace("", "unknown")

    group_columns = [
        "session_id", "date", "subject_id", "device_id", "test_id", "test_condition",
        "target_key", "target_label", "target_x", "target_y", "target_x_centered",
        "target_y_centered", "target_eccentricity_normalised", "coordinate_space",
    ]
    summary = (
        table.groupby(group_columns, dropna=False, as_index=False)
        .agg(
            recording_start_time=("recording_start_time", "first"),
            trial_number=("trial_number", "first"),
            interval_count=("marker_index", "count"),
            target_settle_time_s=("target_settle_time_s", "max"),
            settle_excluded_valid_samples=("settle_excluded_valid_samples", "sum"),
            valid_samples=("valid_samples", "sum"),
            paper_qc_interval_count=("_paper_qc_interval_count", "sum"),
            paper_qc_valid_samples=("paper_qc_valid_samples", "sum"),
            paper_qc_excluded_samples=("paper_qc_excluded_samples", "sum"),
            _paper_qc_mean_gaze_x_sum=("_paper_qc_mean_gaze_x_sum", lambda values: values.sum(min_count=1)),
            _paper_qc_mean_gaze_y_sum=("_paper_qc_mean_gaze_y_sum", lambda values: values.sum(min_count=1)),
            _paper_qc_gaze_x_normalised_sum=("_paper_qc_gaze_x_normalised_sum", lambda values: values.sum(min_count=1)),
            _paper_qc_gaze_y_normalised_sum=("_paper_qc_gaze_y_normalised_sum", lambda values: values.sum(min_count=1)),
            _paper_qc_gaze_x_deg_sum=("_paper_qc_gaze_x_deg_sum", lambda values: values.sum(min_count=1)),
            _paper_qc_gaze_y_deg_sum=("_paper_qc_gaze_y_deg_sum", lambda values: values.sum(min_count=1)),
            _paper_qc_omae_normalised_sum=("_paper_qc_omae_normalised_sum", lambda values: values.sum(min_count=1)),
            _paper_qc_omae_deg_sum=("_paper_qc_omae_deg_sum", lambda values: values.sum(min_count=1)),
            _paper_qc_precision_normalised_sq_sum=("_paper_qc_precision_normalised_sq_sum", lambda values: values.sum(min_count=1)),
            _paper_qc_precision_deg_sq_sum=("_paper_qc_precision_deg_sq_sum", lambda values: values.sum(min_count=1)),
            mean_gaze_x=("mean_gaze_x", "mean"),
            mean_gaze_y=("mean_gaze_y", "mean"),
            gaze_direction_x_normalised=("gaze_direction_x_normalised", "mean"),
            gaze_direction_y_normalised=("gaze_direction_y_normalised", "mean"),
            error_x_normalised=("error_x_normalised", "mean"),
            error_y_normalised=("error_y_normalised", "mean"),
            centroid_error_normalised=("centroid_error_normalised", "mean"),
            omae_normalised=("omae_normalised", "mean"),
            precision_rms_normalised=("precision_rms_normalised", "mean"),
            target_x_deg=("target_x_deg", "mean"),
            target_y_deg=("target_y_deg", "mean"),
            gaze_direction_x_deg=("gaze_direction_x_deg", "mean"),
            gaze_direction_y_deg=("gaze_direction_y_deg", "mean"),
            error_x_deg=("error_x_deg", "mean"),
            error_y_deg=("error_y_deg", "mean"),
            centroid_error_deg=("centroid_error_deg", "mean"),
            omae_deg=("omae_deg", "mean"),
            precision_rms_deg=("precision_rms_deg", "mean"),
            target_eccentricity_deg=("target_eccentricity_deg", "mean"),
        )
    )
    paper_denominator = summary["paper_qc_valid_samples"].where(
        summary["paper_qc_interval_count"] > 0, np.nan
    )
    summary["paper_qc_mean_gaze_x"] = summary["_paper_qc_mean_gaze_x_sum"] / paper_denominator
    summary["paper_qc_mean_gaze_y"] = summary["_paper_qc_mean_gaze_y_sum"] / paper_denominator
    summary["paper_qc_gaze_direction_x_normalised"] = (
        summary["_paper_qc_gaze_x_normalised_sum"] / paper_denominator
    )
    summary["paper_qc_gaze_direction_y_normalised"] = (
        summary["_paper_qc_gaze_y_normalised_sum"] / paper_denominator
    )
    summary["paper_qc_gaze_direction_x_deg"] = summary["_paper_qc_gaze_x_deg_sum"] / paper_denominator
    summary["paper_qc_gaze_direction_y_deg"] = summary["_paper_qc_gaze_y_deg_sum"] / paper_denominator
    summary["paper_qc_omae_normalised"] = (
        summary["_paper_qc_omae_normalised_sum"] / paper_denominator
    )
    summary["paper_qc_precision_rms_normalised"] = np.sqrt(
        summary["_paper_qc_precision_normalised_sq_sum"] / paper_denominator
    )
    summary["paper_qc_omae_deg"] = summary["_paper_qc_omae_deg_sum"] / paper_denominator
    summary["paper_qc_precision_rms_deg"] = np.sqrt(
        summary["_paper_qc_precision_deg_sq_sum"] / paper_denominator
    )
    summary["paper_qc_status"] = np.where(
        summary["paper_qc_interval_count"] > 0,
        "included",
        np.where(
            summary["coordinate_space"].eq("normalised"),
            "insufficient_in_bounds_samples",
            "unknown_coordinate_space",
        ),
    )
    visit_groups = ["subject_id", "device_id", "test_id", "test_condition"]
    sessions = summary[
        visit_groups + ["session_id", "date", "recording_start_time", "trial_number"]
    ].drop_duplicates()
    sessions["_start"] = pd.to_numeric(sessions["recording_start_time"], errors="coerce")
    sessions["_trial"] = pd.to_numeric(sessions["trial_number"], errors="coerce")
    sessions = sessions.sort_values(visit_groups + ["date", "_start", "_trial", "session_id"])
    sessions["visit_index"] = sessions.groupby(visit_groups, dropna=False).cumcount() + 1
    sessions["visit_label"] = "Visit " + sessions["visit_index"].astype(str)
    summary = summary.merge(
        sessions[["session_id", "visit_index", "visit_label"]], on="session_id", how="left"
    )
    summary = _apply_paper_plot_qc(summary)
    return summary[TARGET_VISIT_COLUMNS].sort_values(
        ["visit_index", "target_y", "target_x", "subject_id"]
    ).reset_index(drop=True)


def marker_based_metrics(
    gaze: pd.DataFrame,
    markers: pd.DataFrame,
    record: SessionRecord | None = None,
    settle_time_s: float = 0.0,
) -> dict[str, float]:
    """Calculate marker-aligned precision and accuracy metrics."""

    settle_time_s = float(settle_time_s)
    if not np.isfinite(settle_time_s) or settle_time_s < 0:
        raise ValueError("settle_time_s must be a finite non-negative number")
    result = {
        "marker_precision_rms": float("nan"),
        "marker_stability_p95": float("nan"),
        "marker_accuracy_rmse": float("nan"),
        "marker_mean_absolute_error": float("nan"),
        "marker_systematic_error_x": float("nan"),
        "marker_systematic_error_y": float("nan"),
        "marker_systematic_error_radial": float("nan"),
        "marker_random_error_rms": float("nan"),
        "marker_repeatability_95": float("nan"),
        "marker_accuracy_rmse_deg": float("nan"),
        "marker_omae_deg": float("nan"),
        "marker_precision_rms_deg": float("nan"),
        "marker_coverage_rate": float("nan"),
        "marker_valid_samples": 0.0,
        "target_settle_time_s": settle_time_s,
        "marker_settle_excluded_samples": 0.0,
    }
    if gaze.empty or markers.empty or "time_s" not in gaze:
        return result

    valid_gaze = gaze.loc[_valid_mask(gaze), ["time_s", "gaze_x", "gaze_y"]].copy()
    valid_gaze = valid_gaze.apply(pd.to_numeric, errors="coerce").dropna()
    if valid_gaze.empty:
        result["marker_coverage_rate"] = 0.0
        return result

    precision_values: list[float] = []
    stability_values: list[float] = []
    accuracy_values: list[float] = []
    precision_degrees: list[float] = []
    angular_sample_errors: list[float] = []
    centroid_errors: list[tuple[float, float]] = []
    covered = 0
    valid_marker_samples = 0
    settle_excluded_samples = 0
    for _, marker in markers.iterrows():
        start = pd.to_numeric(pd.Series([marker.get("marker_start_s")]), errors="coerce").iloc[0]
        end = pd.to_numeric(pd.Series([marker.get("marker_end_s")]), errors="coerce").iloc[0]
        if not np.isfinite(start) or not np.isfinite(end) or end < start:
            continue
        analysis_start = float(start + settle_time_s)
        interval_samples = valid_gaze[valid_gaze["time_s"].between(start, end)]
        settle_excluded_samples += int((interval_samples["time_s"] < analysis_start).sum())
        samples = interval_samples[interval_samples["time_s"] >= analysis_start]
        if len(samples) < 5:
            continue
        covered += 1
        valid_marker_samples += len(samples)
        x = samples["gaze_x"].to_numpy(dtype=float)
        y = samples["gaze_y"].to_numpy(dtype=float)
        center_x = float(np.mean(x))
        center_y = float(np.mean(y))
        dx_center = x - center_x
        dy_center = y - center_y
        radial = np.sqrt(dx_center**2 + dy_center**2)
        precision_values.append(float(np.sqrt(np.mean(radial**2))))
        stability_values.append(float(np.percentile(radial, 95)))
        angle_precision = _visual_angle_deg(record, dx_center, dy_center)
        if np.isfinite(angle_precision).any():
            precision_degrees.append(float(np.sqrt(np.nanmean(angle_precision**2))))

        target_x = pd.to_numeric(pd.Series([marker.get("target_x")]), errors="coerce").iloc[0]
        target_y = pd.to_numeric(pd.Series([marker.get("target_y")]), errors="coerce").iloc[0]
        if np.isfinite(target_x) and np.isfinite(target_y):
            error_x = center_x - target_x
            error_y = center_y - target_y
            centroid_errors.append((error_x, error_y))
            accuracy_values.append(float(np.sqrt(error_x**2 + error_y**2)))
            angular_errors = _visual_angle_deg(record, x - target_x, y - target_y)
            angular_sample_errors.extend(angular_errors[np.isfinite(angular_errors)].tolist())

    result["marker_coverage_rate"] = covered / len(markers) if len(markers) else float("nan")
    result["marker_valid_samples"] = float(valid_marker_samples)
    result["marker_settle_excluded_samples"] = float(settle_excluded_samples)
    if precision_values:
        result["marker_precision_rms"] = float(np.median(precision_values))
        result["marker_stability_p95"] = float(np.median(stability_values))
        result["marker_random_error_rms"] = float(np.sqrt(np.mean(np.square(precision_values))))
    if precision_degrees:
        result["marker_precision_rms_deg"] = float(np.median(precision_degrees))
    if accuracy_values:
        result["marker_accuracy_rmse"] = float(np.sqrt(np.mean(np.square(accuracy_values))))
        result["marker_mean_absolute_error"] = float(np.mean(accuracy_values))
        if len(accuracy_values) > 1:
            result["marker_repeatability_95"] = float(1.96 * np.std(accuracy_values, ddof=1))
    if centroid_errors:
        errors = np.asarray(centroid_errors, dtype=float)
        systematic_x = float(np.mean(errors[:, 0]))
        systematic_y = float(np.mean(errors[:, 1]))
        result["marker_systematic_error_x"] = systematic_x
        result["marker_systematic_error_y"] = systematic_y
        result["marker_systematic_error_radial"] = float(np.hypot(systematic_x, systematic_y))
    if angular_sample_errors:
        angular = np.asarray(angular_sample_errors, dtype=float)
        result["marker_omae_deg"] = float(np.mean(np.abs(angular)))
        result["marker_accuracy_rmse_deg"] = float(np.sqrt(np.mean(angular**2)))
    return result


def evaluate_quality(
    record: SessionRecord,
    gaze: pd.DataFrame,
    video: pd.DataFrame,
    markers: pd.DataFrame,
    thresholds: QualityThresholds,
    settle_time_s: float = 0.0,
) -> dict[str, Any]:
    """Evaluate one session against auditable quality thresholds."""

    flags: list[str] = []
    total = int(len(gaze))
    valid_mask = _valid_mask(gaze)
    valid_samples = int(valid_mask.sum())
    valid_rate = float(valid_samples / total) if total else float("nan")
    stats = interval_statistics(
        gaze["time_s"] if "time_s" in gaze else pd.Series(dtype=float),
        thresholds.interval_tolerance_fraction,
    )
    estimated_missing = int(stats["estimated_missing_samples"])
    data_loss_rate = _data_loss(total, valid_samples, estimated_missing)

    declared_valid = _numeric(gaze.get("valid", pd.Series(dtype=float))).fillna(0) > 0
    missing_coordinates = 0
    if total and {"gaze_x", "gaze_y"}.issubset(gaze.columns):
        missing_coordinates = int(
            (declared_valid & (_numeric(gaze["gaze_x"]).isna() | _numeric(gaze["gaze_y"]).isna())).sum()
        )

    coordinate_space = "unknown"
    if "coordinate_space" in gaze and not gaze.empty:
        spaces = gaze["coordinate_space"].dropna().astype(str)
        coordinate_space = spaces.mode().iloc[0] if not spaces.empty else "unknown"
    out_of_bounds = 0
    if total and coordinate_space == "normalised":
        x = _numeric(gaze["gaze_x"])
        y = _numeric(gaze["gaze_y"])
        out_of_bounds = int(
            (
                declared_valid
                & (
                    ~x.between(thresholds.normalised_gaze_min, thresholds.normalised_gaze_max)
                    | ~y.between(thresholds.normalised_gaze_min, thresholds.normalised_gaze_max)
                )
            ).sum()
        )
    out_of_bounds_rate = out_of_bounds / total if total else float("nan")

    gaze_duration = duration_s(gaze["time_s"]) if "time_s" in gaze else float("nan")
    video_duration = duration_s(video["time_s"]) if "time_s" in video else float("nan")
    duration_mismatch_fraction = float("nan")
    if np.isfinite(gaze_duration) and np.isfinite(video_duration) and max(gaze_duration, video_duration) > 0:
        duration_mismatch_fraction = abs(gaze_duration - video_duration) / max(gaze_duration, video_duration)

    required_metadata = (
        record.subject_id,
        record.device_id,
        record.test_id,
        record.trial_number,
        record.test_condition,
        record.recording_start_time,
    )
    metadata_missing = sum(value is None or value == "" for value in required_metadata)
    metadata_conflicts = tuple(
        field for field in record.metadata_conflict_fields.split(";") if field
    )
    marker_metrics = marker_based_metrics(gaze, markers, record, settle_time_s)
    marker_events = int(len(markers))

    if total == 0:
        flags.append("missing_gaze")
    elif valid_samples == 0:
        flags.append("no_valid_gaze")
    elif np.isfinite(valid_rate) and valid_rate < thresholds.min_valid_rate:
        flags.append("low_valid_gaze_rate")
    if np.isfinite(data_loss_rate) and data_loss_rate > thresholds.max_data_loss_rate:
        flags.append("high_data_loss")
    if stats["duplicate_timestamps"] > 0:
        flags.append("duplicate_timestamps")
    if stats["negative_time_jumps"] > 0:
        flags.append("negative_time_jumps")
    if np.isfinite(stats["irregular_interval_pct"]) and stats["irregular_interval_pct"] > thresholds.max_irregular_interval_pct:
        flags.append("irregular_sampling")
    if np.isfinite(stats["longest_gap_s"]) and stats["longest_gap_s"] > thresholds.max_longest_gap_s:
        flags.append("long_sampling_gap")
    if missing_coordinates:
        flags.append("valid_samples_missing_coordinates")
    if np.isfinite(out_of_bounds_rate) and out_of_bounds_rate > thresholds.max_out_of_bounds_rate:
        flags.append("gaze_out_of_bounds")
    if video.empty:
        flags.append("missing_video_timestamps")
    if np.isfinite(duration_mismatch_fraction) and duration_mismatch_fraction > thresholds.max_duration_mismatch_fraction:
        flags.append("gaze_video_duration_mismatch")
    if record.planned_duration_s and np.isfinite(gaze_duration):
        minimum_duration = record.planned_duration_s * (1 - thresholds.max_incomplete_recording_fraction)
        if gaze_duration < minimum_duration:
            flags.append("incomplete_recording")
    if thresholds.expected_marker_events is not None and marker_events != thresholds.expected_marker_events:
        flags.append("unexpected_marker_count")
    if marker_events and marker_metrics["marker_coverage_rate"] < thresholds.min_marker_coverage_rate:
        flags.append("low_marker_coverage")
    if metadata_missing:
        flags.append("incomplete_metadata")
    if metadata_conflicts:
        flags.append("inconsistent_metadata")
    if record.metadata_read_error:
        flags.append("unreadable_session_metadata")
    if record.recording_start_time and record.recording_end_time and record.recording_end_time < record.recording_start_time:
        flags.append("invalid_recording_times")
    if record.calibration_valid_points is not None and record.calibration_valid_points < thresholds.min_calibration_valid_points:
        flags.append("insufficient_calibration_points")
    if record.calibration_avg_error is not None:
        recorded_unit = record.calibration_error_unit.strip().lower()
        threshold_unit = thresholds.calibration_error_unit.strip().lower()
        if not recorded_unit or recorded_unit in {"unknown", "device_reported"}:
            flags.append("unknown_calibration_error_unit")
        elif (
            thresholds.max_calibration_error is not None
            and recorded_unit == threshold_unit
            and record.calibration_avg_error > thresholds.max_calibration_error
        ):
            flags.append("high_calibration_error")
    if not record.has_calibration:
        flags.append("missing_calibration_record")

    severe = {"missing_gaze", "no_valid_gaze", "incomplete_recording", "invalid_recording_times"}
    status = "fail" if severe.intersection(flags) else "warn" if flags else "pass"
    return {
        "session_id": record.session_id,
        "quality_status": status,
        "valid_rate": valid_rate,
        "data_loss_rate": data_loss_rate,
        "estimated_missing_samples": estimated_missing,
        "longest_gap_s": stats["longest_gap_s"],
        "duplicate_timestamps": int(stats["duplicate_timestamps"]),
        "negative_time_jumps": int(stats["negative_time_jumps"]),
        "irregular_interval_pct": stats["irregular_interval_pct"],
        "missing_coordinate_samples": missing_coordinates,
        "out_of_bounds_samples": out_of_bounds,
        "out_of_bounds_rate": out_of_bounds_rate,
        "marker_events": marker_events,
        "marker_coverage_rate": marker_metrics["marker_coverage_rate"],
        "target_settle_time_s": marker_metrics["target_settle_time_s"],
        "marker_settle_excluded_samples": marker_metrics["marker_settle_excluded_samples"],
        "metadata_missing_fields": metadata_missing,
        "metadata_conflict_count": len(metadata_conflicts),
        "metadata_conflict_fields": record.metadata_conflict_fields,
        "metadata_read_error": record.metadata_read_error,
        "duration_mismatch_fraction": duration_mismatch_fraction,
        "quality_flags": ";".join(flags) if flags else "ok",
    }


def compute_metrics(
    record: SessionRecord,
    gaze: pd.DataFrame,
    video: pd.DataFrame,
    markers: pd.DataFrame,
    settle_time_s: float = 0.0,
) -> dict[str, Any]:
    """Compute descriptive metrics for one standardised session."""

    total = int(len(gaze))
    valid_mask = _valid_mask(gaze)
    valid_samples = int(valid_mask.sum())
    valid_gaze = gaze.loc[valid_mask, ["gaze_x", "gaze_y"]].apply(pd.to_numeric, errors="coerce").dropna()
    times = gaze["time_s"] if "time_s" in gaze else pd.Series(dtype=float)
    stats = interval_statistics(times)
    estimated_missing = int(stats["estimated_missing_samples"])
    marker_metrics = marker_based_metrics(gaze, markers, record, settle_time_s)
    coordinate_space = "unknown"
    if "coordinate_space" in gaze and not gaze.empty:
        spaces = gaze["coordinate_space"].dropna().astype(str)
        coordinate_space = spaces.mode().iloc[0] if not spaces.empty else "unknown"

    return {
        "session_id": record.session_id,
        "gaze_samples": total,
        "duration_s": duration_s(times),
        "effective_sampling_hz": effective_sampling_hz(times),
        "median_interval_ms": stats["median_interval_ms"],
        "p95_interval_ms": stats["p95_interval_ms"],
        "sampling_jitter_ms": stats["sampling_jitter_ms"],
        "sampling_interval_cv": stats["sampling_interval_cv"],
        "estimated_missing_samples": estimated_missing,
        "longest_gap_s": stats["longest_gap_s"],
        "valid_samples": valid_samples,
        "invalid_samples": total - valid_samples,
        "valid_rate": valid_samples / total if total else float("nan"),
        "data_loss_rate": _data_loss(total, valid_samples, estimated_missing),
        "completeness_rate": 1 - _data_loss(total, valid_samples, estimated_missing)
        if total or estimated_missing
        else float("nan"),
        "gaze_dispersion_x": float(valid_gaze["gaze_x"].std()) if len(valid_gaze) > 1 else float("nan"),
        "gaze_dispersion_y": float(valid_gaze["gaze_y"].std()) if len(valid_gaze) > 1 else float("nan"),
        "coordinate_space": coordinate_space,
        "video_frames": int(len(video)),
        "video_duration_s": duration_s(video["time_s"]) if "time_s" in video else float("nan"),
        "marker_events": int(len(markers)),
        "calibration_avg_error": record.calibration_avg_error,
        "calibration_valid_points": record.calibration_valid_points,
        "calibration_high_quality_samples": record.calibration_high_quality_samples,
        "calibration_confidence_threshold": record.calibration_confidence_threshold,
        "calibration_error_unit": record.calibration_error_unit,
        "calibration_status": record.calibration_status,
        "calibration_source": record.calibration_source,
        **marker_metrics,
    }


def build_long_term_summary(combined: pd.DataFrame) -> pd.DataFrame:
    """Aggregate session metrics by date and protocol."""

    columns = [
        "date", "device_id", "test_id", "test_condition", "session_count", "subject_count",
        "repeated_subject_count", "median_sampling_hz", "median_valid_rate", "median_data_loss_rate",
        "median_marker_precision_rms", "median_marker_accuracy_rmse", "median_marker_omae_deg",
        "sessions_with_warnings", "sampling_change_pct_from_baseline",
        "valid_rate_change_points_from_baseline", "precision_change_from_baseline",
    ]
    if combined.empty:
        return pd.DataFrame(columns=columns)

    table = combined.copy()
    for column in ("device_id", "test_id", "test_condition", "subject_id"):
        table[column] = table.get(column, pd.Series("", index=table.index)).fillna("").replace("", "unknown")
    table["has_warning"] = table["quality_status"].fillna("warn") != "pass"
    repeated = table.groupby(["subject_id", "device_id", "test_id", "test_condition"])["date"].transform("nunique") > 1
    table["repeated_subject_id"] = table["subject_id"].where(repeated & (table["subject_id"] != "unknown"), "")
    summary = (
        table.groupby(["date", "device_id", "test_id", "test_condition"], dropna=False, as_index=False)
        .agg(
            session_count=("session_id", "count"),
            subject_count=("subject_id", "nunique"),
            repeated_subject_count=("repeated_subject_id", lambda values: values[values != ""].nunique()),
            median_sampling_hz=("effective_sampling_hz", "median"),
            median_valid_rate=("valid_rate", "median"),
            median_data_loss_rate=("data_loss_rate", "median"),
            median_marker_precision_rms=("marker_precision_rms", "median"),
            median_marker_accuracy_rmse=("marker_accuracy_rmse", "median"),
            median_marker_omae_deg=("marker_omae_deg", "median"),
            sessions_with_warnings=("has_warning", "sum"),
        )
        .sort_values(["device_id", "test_id", "test_condition", "date"])
        .reset_index(drop=True)
    )
    summary["sampling_change_pct_from_baseline"] = np.nan
    summary["valid_rate_change_points_from_baseline"] = np.nan
    summary["precision_change_from_baseline"] = np.nan
    for _, indexes in summary.groupby(["device_id", "test_id", "test_condition"]).groups.items():
        group_indexes = list(indexes)
        first = summary.loc[group_indexes[0]]
        sampling_baseline = first["median_sampling_hz"]
        valid_baseline = first["median_valid_rate"]
        precision_baseline = first["median_marker_precision_rms"]
        if np.isfinite(sampling_baseline) and sampling_baseline != 0:
            summary.loc[group_indexes, "sampling_change_pct_from_baseline"] = (
                (summary.loc[group_indexes, "median_sampling_hz"] - sampling_baseline) / sampling_baseline * 100
            )
        if np.isfinite(valid_baseline):
            summary.loc[group_indexes, "valid_rate_change_points_from_baseline"] = (
                summary.loc[group_indexes, "median_valid_rate"] - valid_baseline
            ) * 100
        if np.isfinite(precision_baseline):
            summary.loc[group_indexes, "precision_change_from_baseline"] = (
                summary.loc[group_indexes, "median_marker_precision_rms"] - precision_baseline
            )
    return summary[columns]


def build_repeatability_summary(combined: pd.DataFrame) -> pd.DataFrame:
    """Summarise genuinely repeated sessions without mixing participants."""

    columns = [
        "subject_id", "device_id", "test_id", "test_condition", "session_count", "date_count",
        "median_sampling_hz", "sampling_hz_range", "sampling_hz_repeatability_95",
        "median_valid_rate", "valid_rate_range", "valid_rate_repeatability_95",
        "median_marker_precision_rms", "precision_range", "precision_repeatability_95",
    ]
    if combined.empty:
        return pd.DataFrame(columns=columns)
    table = combined.copy()
    for column in ("subject_id", "device_id", "test_id", "test_condition"):
        table[column] = table.get(column, pd.Series("", index=table.index)).fillna("").replace("", "unknown")
    rows: list[dict[str, object]] = []
    for keys, group in table.groupby(["subject_id", "device_id", "test_id", "test_condition"], dropna=False):
        if keys[0] == "unknown" or len(group) < 2:
            continue

        def metric_summary(column: str) -> tuple[float, float, float]:
            """Return the median, range, and 95% repeatability."""

            values = pd.to_numeric(group[column], errors="coerce").dropna().to_numpy(dtype=float)
            if len(values) == 0:
                return float("nan"), float("nan"), float("nan")
            span = float(np.ptp(values)) if len(values) > 1 else 0.0
            repeatability = float(1.96 * np.sqrt(2) * np.std(values, ddof=1)) if len(values) > 1 else float("nan")
            return float(np.median(values)), span, repeatability

        sampling = metric_summary("effective_sampling_hz")
        validity = metric_summary("valid_rate")
        precision = metric_summary("marker_precision_rms")
        rows.append(
            {
                "subject_id": keys[0], "device_id": keys[1], "test_id": keys[2], "test_condition": keys[3],
                "session_count": len(group), "date_count": group["date"].nunique(),
                "median_sampling_hz": sampling[0], "sampling_hz_range": sampling[1],
                "sampling_hz_repeatability_95": sampling[2], "median_valid_rate": validity[0],
                "valid_rate_range": validity[1], "valid_rate_repeatability_95": validity[2],
                "median_marker_precision_rms": precision[0], "precision_range": precision[1],
                "precision_repeatability_95": precision[2],
            }
        )
    return pd.DataFrame(rows, columns=columns)
