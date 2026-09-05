"""Recover validation targets from legacy screen recordings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .collection import ACCURACY_TARGETS
from .metadata import SessionRecord, read_recording_info


VIDEO_TARGET_AUDIT_COLUMNS = [
    "session_id",
    "marker_index",
    "marker_start_s",
    "marker_end_s",
    "marker_midpoint_s",
    "frame_id",
    "frame_time_s",
    "frame_time_error_ms",
    "detection_status",
    "candidate_target_count",
    "detected_x_px",
    "detected_y_px",
    "detected_radius_px",
    "detected_x_normalised",
    "detected_y_normalised",
    "matched_target_id",
    "target_x",
    "target_y",
    "normalised_match_offset",
    "detection_confidence",
]

TARGET_PROVENANCE_COLUMNS = [
    "target_source",
    "target_detection_confidence",
    "target_detected_x",
    "target_detected_y",
    "target_frame_id",
    "target_frame_time_s",
]


@dataclass(frozen=True)
class VideoTargetRecoveryResult:
    """Recovered marker tables and video audit evidence."""

    markers: pd.DataFrame
    audit: pd.DataFrame
    summary: dict[str, object]


def _load_cv2() -> Any:
    try:
        import cv2
    except ImportError as error:  # pragma: no cover - depends on optional installation
        raise RuntimeError(
            "Video target recovery requires the optional 'video' dependencies: "
            "pip install -e '.[video]'"
        ) from error
    return cv2


def _video_path(record: SessionRecord) -> Path | None:
    session_path = Path(record.session_path)
    info = read_recording_info(session_path / "Recording_info.csv")
    configured = info.get("video_out_fn", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(session_path / Path(configured).name)
    candidates.extend(
        [
            session_path / "ext_display_acc_video.avi",
            session_path / "display_video.avi",
        ]
    )
    candidates.extend(sorted(session_path.glob("*.avi")))
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _base_summary(
    record: SessionRecord,
    video_path: Path | None,
    interval_count: int,
) -> dict[str, object]:
    return {
        "session_id": record.session_id,
        "target_recovery_attempted": False,
        "target_recovery_status": "not_attempted",
        "target_recovery_validation_passed": False,
        "source_video_file": video_path.name if video_path is not None else "",
        "source_video_bytes": video_path.stat().st_size if video_path is not None else 0,
        "marker_interval_count": int(interval_count),
        "detected_target_intervals": 0,
        "recovered_target_intervals": 0,
        "recovered_unique_targets": 0,
        "expected_target_intervals": len(ACCURACY_TARGETS) * 3,
        "median_normalised_match_offset": None,
        "max_normalised_match_offset": None,
        "target_count_signature": "",
    }


def _result(
    markers: pd.DataFrame,
    summary: dict[str, object],
    audit_rows: list[dict[str, object]] | None = None,
) -> VideoTargetRecoveryResult:
    audit = pd.DataFrame(audit_rows or [], columns=VIDEO_TARGET_AUDIT_COLUMNS)
    return VideoTargetRecoveryResult(markers=markers, audit=audit, summary=summary)


def _protocol_candidates(
    gray: np.ndarray,
    cv2: Any,
    max_candidate_offset: float,
) -> list[dict[str, float | int | str]]:
    height, width = gray.shape[:2]
    minimum_dimension = min(height, width)
    blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=max(20, int(minimum_dimension * 0.025)),
        param1=80,
        param2=10,
        minRadius=max(3, int(round(minimum_dimension * 4 / 1080))),
        maxRadius=max(12, int(round(minimum_dimension * 35 / 1080))),
    )
    if circles is None:
        return []

    targets = np.asarray([(x, y) for _, x, y in ACCURACY_TARGETS], dtype=float)
    best_by_target: dict[int, dict[str, float | int | str]] = {}
    for x_px, y_px, radius_px in circles[0]:
        detected = np.asarray([float(x_px) / width, float(y_px) / height])
        offsets = np.linalg.norm(targets - detected, axis=1)
        target_index = int(np.argmin(offsets))
        offset = float(offsets[target_index])
        if offset > max_candidate_offset:
            continue
        target_id, target_x, target_y = ACCURACY_TARGETS[target_index]
        candidate: dict[str, float | int | str] = {
            "target_index": target_index,
            "matched_target_id": target_id,
            "target_x": target_x,
            "target_y": target_y,
            "detected_x_px": float(x_px),
            "detected_y_px": float(y_px),
            "detected_radius_px": float(radius_px),
            "detected_x_normalised": float(detected[0]),
            "detected_y_normalised": float(detected[1]),
            "normalised_match_offset": offset,
        }
        existing = best_by_target.get(target_index)
        if existing is None or offset < float(existing["normalised_match_offset"]):
            best_by_target[target_index] = candidate
    return sorted(
        best_by_target.values(),
        key=lambda item: float(item["normalised_match_offset"]),
    )


def recover_targets_from_video(
    record: SessionRecord,
    markers: pd.DataFrame,
    video_timestamps: pd.DataFrame,
    *,
    expected_repeats: int = 3,
    max_match_offset: float = 0.015,
    ambiguity_margin: float = 0.005,
) -> VideoTargetRecoveryResult:
    """Recover nine-point target identities from legacy screen video."""

    markers = markers.copy()
    video_path = _video_path(record)
    summary = _base_summary(record, video_path, len(markers))

    if not markers.empty:
        target_x = pd.to_numeric(markers.get("target_x"), errors="coerce")
        target_y = pd.to_numeric(markers.get("target_y"), errors="coerce")
        if target_x.notna().all() and target_y.notna().all():
            summary.update(
                {
                    "target_recovery_status": "already_available",
                    "target_recovery_validation_passed": True,
                    "recovered_unique_targets": int(
                        pd.DataFrame({"x": target_x, "y": target_y}).drop_duplicates().shape[0]
                    ),
                }
            )
            return _result(markers, summary)

    problems: list[str] = []
    if markers.empty:
        problems.append("missing_marker_intervals")
    if video_timestamps.empty:
        problems.append("missing_video_timestamps")
    if video_path is None:
        problems.append("missing_video_file")
    elif video_path.stat().st_size < 10_000:
        problems.append("video_file_too_small")
    if problems:
        summary["target_recovery_status"] = "+".join(problems)
        return _result(markers, summary)

    try:
        cv2 = _load_cv2()
    except RuntimeError:
        summary["target_recovery_status"] = "optional_video_dependency_missing"
        return _result(markers, summary)

    required_marker_columns = {"marker_start_s", "marker_end_s"}
    required_video_columns = {"frame_id", "time_s"}
    if not required_marker_columns.issubset(markers.columns):
        summary["target_recovery_status"] = "invalid_marker_table"
        return _result(markers, summary)
    if not required_video_columns.issubset(video_timestamps.columns):
        summary["target_recovery_status"] = "invalid_video_timestamp_table"
        return _result(markers, summary)

    frame_table = video_timestamps[["frame_id", "time_s"]].copy()
    frame_table["frame_id"] = pd.to_numeric(frame_table["frame_id"], errors="coerce")
    frame_table["time_s"] = pd.to_numeric(frame_table["time_s"], errors="coerce")
    frame_table = frame_table.dropna().sort_values("time_s").reset_index(drop=True)
    if frame_table.empty:
        summary["target_recovery_status"] = "missing_video_timestamps"
        return _result(markers, summary)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        summary["target_recovery_status"] = "unreadable_video_file"
        return _result(markers, summary)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        capture.release()
        summary["target_recovery_status"] = "unreadable_video_dimensions"
        return _result(markers, summary)

    summary["target_recovery_attempted"] = True
    audit_rows: list[dict[str, object]] = []
    frame_times = frame_table["time_s"].to_numpy(dtype=float)
    try:
        for marker_index, (_, marker) in enumerate(markers.iterrows()):
            start = pd.to_numeric(pd.Series([marker.get("marker_start_s")]), errors="coerce").iloc[0]
            end = pd.to_numeric(pd.Series([marker.get("marker_end_s")]), errors="coerce").iloc[0]
            base: dict[str, object] = {
                "session_id": record.session_id,
                "marker_index": marker_index,
                "marker_start_s": start,
                "marker_end_s": end,
                "marker_midpoint_s": None,
                "frame_id": None,
                "frame_time_s": None,
                "frame_time_error_ms": None,
                "detection_status": "invalid_marker_interval",
                "candidate_target_count": 0,
                "detected_x_px": None,
                "detected_y_px": None,
                "detected_radius_px": None,
                "detected_x_normalised": None,
                "detected_y_normalised": None,
                "matched_target_id": "",
                "target_x": None,
                "target_y": None,
                "normalised_match_offset": None,
                "detection_confidence": None,
            }
            if not np.isfinite(start) or not np.isfinite(end) or end < start:
                audit_rows.append(base)
                continue

            midpoint = float((start + end) / 2)
            nearest_index = int(np.argmin(np.abs(frame_times - midpoint)))
            frame_id = int(round(float(frame_table.loc[nearest_index, "frame_id"])))
            frame_time = float(frame_table.loc[nearest_index, "time_s"])
            base.update(
                {
                    "marker_midpoint_s": midpoint,
                    "frame_id": frame_id,
                    "frame_time_s": frame_time,
                    "frame_time_error_ms": abs(frame_time - midpoint) * 1000,
                }
            )
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
            decoded, frame = capture.read()
            if not decoded or frame is None:
                base["detection_status"] = "frame_decode_failed"
                audit_rows.append(base)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            candidates = _protocol_candidates(
                gray,
                cv2,
                max_candidate_offset=max(0.04, max_match_offset),
            )
            base["candidate_target_count"] = len(candidates)
            if not candidates:
                base["detection_status"] = "protocol_circle_not_found"
                audit_rows.append(base)
                continue

            best = candidates[0]
            base.update(best)
            offset = float(best["normalised_match_offset"])
            base["detection_confidence"] = max(0.0, 1.0 - offset / max_match_offset)
            if offset > max_match_offset:
                base["detection_status"] = "target_offset_exceeds_threshold"
            elif (
                len(candidates) > 1
                and float(candidates[1]["normalised_match_offset"]) - offset < ambiguity_margin
            ):
                base["detection_status"] = "ambiguous_protocol_target"
            else:
                base["detection_status"] = "recovered"
            audit_rows.append(base)
    finally:
        capture.release()

    audit = pd.DataFrame(audit_rows, columns=VIDEO_TARGET_AUDIT_COLUMNS)
    recovered = audit[audit["detection_status"] == "recovered"].copy()
    counts = recovered["matched_target_id"].value_counts().reindex(
        [target_id for target_id, _, _ in ACCURACY_TARGETS], fill_value=0
    )
    expected_intervals = len(ACCURACY_TARGETS) * expected_repeats
    validation_passed = bool(
        len(markers) == expected_intervals
        and len(recovered) == expected_intervals
        and (counts == expected_repeats).all()
    )
    offsets = pd.to_numeric(recovered["normalised_match_offset"], errors="coerce")
    summary.update(
        {
            "target_recovery_status": "recovered" if validation_passed else "protocol_validation_failed",
            "target_recovery_validation_passed": validation_passed,
            "detected_target_intervals": int(len(recovered)),
            "recovered_target_intervals": int(len(recovered)) if validation_passed else 0,
            "recovered_unique_targets": int((counts > 0).sum()),
            "expected_target_intervals": expected_intervals,
            "median_normalised_match_offset": float(offsets.median()) if offsets.notna().any() else None,
            "max_normalised_match_offset": float(offsets.max()) if offsets.notna().any() else None,
            "target_count_signature": ";".join(f"{key}:{int(value)}" for key, value in counts.items()),
        }
    )
    if not validation_passed:
        return VideoTargetRecoveryResult(markers=markers, audit=audit, summary=summary)

    recovered_markers = markers.copy()
    for column in TARGET_PROVENANCE_COLUMNS:
        if column not in recovered_markers:
            recovered_markers[column] = np.nan if column != "target_source" else ""
    occurrences = {target_id: 0 for target_id, _, _ in ACCURACY_TARGETS}
    for _, detection in recovered.sort_values("marker_index").iterrows():
        position = int(detection["marker_index"])
        target_id = str(detection["matched_target_id"])
        occurrences[target_id] += 1
        recovered_markers.iloc[position, recovered_markers.columns.get_loc("marker_id")] = (
            f"{target_id}_r{occurrences[target_id]}"
        )
        recovered_markers.iloc[position, recovered_markers.columns.get_loc("target_x")] = float(
            detection["target_x"]
        )
        recovered_markers.iloc[position, recovered_markers.columns.get_loc("target_y")] = float(
            detection["target_y"]
        )
        recovered_markers.iloc[position, recovered_markers.columns.get_loc("coordinate_space")] = "normalised"
        recovered_markers.iloc[position, recovered_markers.columns.get_loc("target_source")] = (
            "screen_video_hough_circle+legacy_nine_point_protocol"
        )
        recovered_markers.iloc[
            position, recovered_markers.columns.get_loc("target_detection_confidence")
        ] = float(detection["detection_confidence"])
        recovered_markers.iloc[position, recovered_markers.columns.get_loc("target_detected_x")] = float(
            detection["detected_x_normalised"]
        )
        recovered_markers.iloc[position, recovered_markers.columns.get_loc("target_detected_y")] = float(
            detection["detected_y_normalised"]
        )
        recovered_markers.iloc[position, recovered_markers.columns.get_loc("target_frame_id")] = int(
            detection["frame_id"]
        )
        recovered_markers.iloc[position, recovered_markers.columns.get_loc("target_frame_time_s")] = float(
            detection["frame_time_s"]
        )
    return VideoTargetRecoveryResult(markers=recovered_markers, audit=audit, summary=summary)
