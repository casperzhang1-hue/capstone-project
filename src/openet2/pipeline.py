"""Run the reproducible OpenET 2 analysis pipeline."""

from __future__ import annotations

import hashlib
import json
import platform
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import (
    TARGET_METRIC_COLUMNS,
    TARGET_VISIT_COLUMNS,
    build_long_term_summary,
    build_repeatability_summary,
    build_target_visit_summary,
    compute_metrics,
    evaluate_quality,
    target_level_metrics,
)
from . import __version__
from .config import QualityThresholds
from .importers import STANDARD_GAZE_COLUMNS, STANDARD_MARKER_COLUMNS, STANDARD_VIDEO_COLUMNS, standardise_session
from .metadata import SessionRecord, discover_sessions
from .reporting import make_figures, make_session_review, write_html_report
from .video_targets import recover_targets_from_video as recover_video_targets


def _runtime_environment() -> dict[str, object]:
    """Return portable interpreter and direct-dependency provenance."""

    distributions = {
        "numpy": "numpy",
        "pandas": "pandas",
        "matplotlib": "matplotlib",
        "seaborn": "seaborn",
        "opencv_python": "opencv-python",
    }
    packages: dict[str, str] = {}
    for label, distribution in distributions.items():
        try:
            packages[label] = distribution_version(distribution)
        except PackageNotFoundError:
            packages[label] = "not-installed"
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "operating_system": platform.system(),
        "platform_release": platform.release(),
        "machine": platform.machine(),
        "packages": packages,
    }


@dataclass(frozen=True)
class PipelineResult:
    """Summary paths and counts from a pipeline run."""

    output_root: Path
    session_count: int
    successful_sessions: int
    failed_sessions: int
    report_path: Path


def _write_frame(frame: pd.DataFrame, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_path, index=False)
    records = json.loads(frame.to_json(orient="records"))
    csv_path.with_suffix(".json").write_text(json.dumps(records, indent=2), encoding="utf-8")


def _portable_inventory(records: list[SessionRecord]) -> pd.DataFrame:
    """Return export-safe metadata without host-specific paths."""

    rows: list[dict[str, object]] = []
    for record in records:
        row = record.to_dict()
        row["session_path"] = record.session_id.replace("\\", "/")
        rows.append(row)
    return pd.DataFrame(rows)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_provenance(data_root: Path, output_root: Path, generated_utc: str) -> dict[str, object]:
    """Create a portable SHA-256 inventory without exposing host paths."""

    entries: list[dict[str, object]] = []
    output_inside_input = output_root.is_relative_to(data_root)
    for path in sorted(data_root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        if output_inside_input and path.resolve().is_relative_to(output_root):
            continue
        relative_path = path.relative_to(data_root).as_posix()
        try:
            entries.append({
                "path": relative_path,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            })
        except OSError as error:
            entries.append({
                "path": relative_path,
                "size_bytes": None,
                "sha256": None,
                "error": type(error).__name__,
            })
    digest_input = json.dumps(entries, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": "1.0",
        "openet2_version": __version__,
        "generated_utc": generated_utc,
        "data_root": "openet2://input",
        "hash_algorithm": "sha256",
        "file_count": len(entries),
        "hash_error_count": sum(1 for entry in entries if entry.get("sha256") is None),
        "content_digest_sha256": hashlib.sha256(digest_input.encode("utf-8")).hexdigest(),
        "files": entries,
    }


def _write_input_provenance(data_root: Path, output_root: Path, generated_utc: str) -> dict[str, object]:
    provenance = _input_provenance(data_root, output_root, generated_utc)
    (output_root / "input_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return provenance


def _empty_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.DataFrame(columns=STANDARD_GAZE_COLUMNS),
        pd.DataFrame(columns=STANDARD_VIDEO_COLUMNS),
        pd.DataFrame(columns=STANDARD_MARKER_COLUMNS),
    )


def _import_failure_rows(
    record: SessionRecord,
    error: Exception,
    settle_time_s: float,
) -> tuple[dict[str, object], dict[str, object]]:
    error_flag = f"import_error_{type(error).__name__}"
    quality = {
        "session_id": record.session_id,
        "quality_status": "fail",
        "valid_rate": float("nan"),
        "data_loss_rate": float("nan"),
        "estimated_missing_samples": 0,
        "longest_gap_s": float("nan"),
        "duplicate_timestamps": 0,
        "negative_time_jumps": 0,
        "irregular_interval_pct": float("nan"),
        "missing_coordinate_samples": 0,
        "out_of_bounds_samples": 0,
        "out_of_bounds_rate": float("nan"),
        "marker_events": 0,
        "marker_coverage_rate": float("nan"),
        "target_settle_time_s": settle_time_s,
        "marker_settle_excluded_samples": 0,
        "metadata_missing_fields": sum(not value for value in (record.subject_id, record.device_id, record.test_id)),
        "metadata_conflict_count": len(
            [field for field in record.metadata_conflict_fields.split(";") if field]
        ),
        "metadata_conflict_fields": record.metadata_conflict_fields,
        "metadata_read_error": record.metadata_read_error,
        "duration_mismatch_fraction": float("nan"),
        "quality_flags": error_flag,
        "processing_error": str(error),
    }
    gaze, video, markers = _empty_tables()
    metrics = compute_metrics(record, gaze, video, markers, settle_time_s)
    return quality, metrics


def _paper_reference_criteria(
    combined: pd.DataFrame,
    target_metrics: pd.DataFrame,
    repeatability: pd.DataFrame,
    settle_time_s: float,
) -> pd.DataFrame:
    """Describe paper criteria separately from device-agnostic project pass/fail rules."""

    retained = pd.to_numeric(
        target_metrics.get("valid_samples", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    sample_evidence = (
        f"{int((retained > 100).sum())}/{len(retained)} analysed target intervals retain >100 valid samples after settling; valid/invalid flags are not treated as vendor confidence."
        if len(retained)
        else "No target-level sample evidence is available."
    )
    calibration_units = combined.get(
        "calibration_error_unit", pd.Series(index=combined.index, dtype=str)
    ).fillna("").astype(str).str.lower()
    calibration_errors = pd.to_numeric(
        combined.get("calibration_avg_error", pd.Series(index=combined.index, dtype=float)), errors="coerce"
    )
    degree_mask = calibration_units.isin({"degree", "degrees", "deg"}) & calibration_errors.notna()
    degree_calibrations = int(degree_mask.sum())
    degree_passes = int((degree_mask & calibration_errors.le(1.5)).sum())

    high_quality_samples = pd.to_numeric(
        combined.get("calibration_high_quality_samples", pd.Series(index=combined.index, dtype=float)),
        errors="coerce",
    )
    confidence_threshold = pd.to_numeric(
        combined.get("calibration_confidence_threshold", pd.Series(index=combined.index, dtype=float)),
        errors="coerce",
    )
    calibration_evidence = high_quality_samples.notna() & confidence_threshold.notna()
    calibration_evidence_count = int(calibration_evidence.sum())
    calibration_sample_passes = int(
        (calibration_evidence & high_quality_samples.gt(150) & confidence_threshold.ge(0.8)).sum()
    )
    if calibration_evidence_count:
        calibration_sample_application = (
            f"{calibration_sample_passes}/{calibration_evidence_count} sessions record >150 high-quality calibration samples "
            f"with a recorded confidence threshold >=0.8."
        )
        calibration_sample_status = "observational_check"
    else:
        calibration_sample_application = (
            "Not directly assessed: the dataset does not record a high-quality calibration-sample count and confidence threshold."
        )
        calibration_sample_status = "not_comparable"

    if degree_calibrations:
        calibration_accuracy_application = (
            f"{degree_passes}/{degree_calibrations} degree-labelled device calibration errors are <=1.5 degrees; "
            "the rule is not applied to other or unknown units."
        )
        calibration_accuracy_status = "observational_check"
    else:
        calibration_accuracy_application = (
            f"0/{len(combined)} sessions provide a degree-labelled calibration error; the limit is applied only when units match."
        )
        calibration_accuracy_status = "conditional"

    repeated_groups = len(repeatability)
    settle_status = "applied" if np.isclose(settle_time_s, 0.6) else "configured_difference"
    rows = [
        {
            "reference_item": "Calibration sample volume and confidence",
            "paper_criterion": ">150 high-quality samples; marker and gaze-coordinate confidence >=0.8.",
            "current_application": calibration_sample_application,
            "status": calibration_sample_status,
        },
        {
            "reference_item": "Calibration mapping accuracy",
            "paper_criterion": "Device-reported mapping accuracy <=1.5 degrees.",
            "current_application": calibration_accuracy_application,
            "status": calibration_accuracy_status,
        },
        {
            "reference_item": "Target settling window",
            "paper_criterion": "Exclude the first 0.6 s after target onset before accuracy analysis.",
            "current_application": f"A {settle_time_s:.3f} s settling window is recorded and applied to marker and target metrics.",
            "status": settle_status,
        },
        {
            "reference_item": "Tracking reliability confidence",
            "paper_criterion": "Use gaze samples with reliability confidence >0.8.",
            "current_application": "Not directly transferable: GP3 valid/invalid flags are used, but they are not assumed to equal the paper's confidence score.",
            "status": "not_comparable",
        },
        {
            "reference_item": "Samples per target",
            "paper_criterion": "The paper reports >100 high-confidence measurements per target after settling.",
            "current_application": sample_evidence,
            "status": "observational_check",
        },
        {
            "reference_item": "Blink/unreliable-time context",
            "paper_criterion": "The paper treats roughly 3-5% overall time as an expected upper range for blink/unreliable data.",
            "current_application": "OpenET2 reports valid rate and estimated data-loss rate, but does not use 3-5% as a universal GP3 pass/fail limit.",
            "status": "reference_only",
        },
        {
            "reference_item": "Coefficient of repeatability",
            "paper_criterion": "1.96 x within-participant SD of OMAE for matched repeated visits.",
            "current_application": f"{repeated_groups} matched repeated participant/device/test groups are available; no paper-specific OMAE CoR is claimed without matched target visits.",
            "status": "conditional",
        },
        {
            "reference_item": "Inferential statistics",
            "paper_criterion": "5% significance; participant random-intercept LMM with Satterthwaite degrees of freedom and Bonferroni correction.",
            "current_application": "Descriptive benchmarking only. The model is intentionally not fitted unless participant identities and genuinely matched repeated visits are available.",
            "status": "not_run",
        },
    ]
    return pd.DataFrame(rows)

def _summary(combined: pd.DataFrame, records: list[SessionRecord], failed_sessions: int) -> dict[str, object]:
    sampling = pd.to_numeric(combined.get("effective_sampling_hz", pd.Series(dtype=float)), errors="coerce")
    valid = pd.to_numeric(combined.get("valid_rate", pd.Series(dtype=float)), errors="coerce")
    devices = {record.device_id for record in records if record.device_id}
    return {
        "session_count": int(len(records)),
        "successful_sessions": int(len(records) - failed_sessions),
        "failed_sessions": int(failed_sessions),
        "date_count": len({record.date for record in records}),
        "device_count": len(devices),
        "devices": sorted(devices),
        "median_sampling_hz": float(sampling.median()) if sampling.notna().any() else None,
        "median_valid_rate": float(valid.median()) if valid.notna().any() else None,
        "sessions_with_warnings": int((combined.get("quality_status", pd.Series(dtype=str)) != "pass").sum()),
    }


def run_pipeline(
    data_root: Path,
    output_root: Path,
    thresholds: QualityThresholds | None = None,
    *,
    recover_targets_from_video: bool = False,
    target_settle_time_s: float = 0.6,
    client_delay_evidence: Path | None = None,
) -> PipelineResult:
    """Run the complete analysis and reporting pipeline."""

    thresholds = thresholds or QualityThresholds()
    target_settle_time_s = float(target_settle_time_s)
    if not np.isfinite(target_settle_time_s) or target_settle_time_s < 0:
        raise ValueError("target_settle_time_s must be a finite non-negative number")
    pipeline_started = time.monotonic()
    data_root = data_root.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if client_delay_evidence is not None:
        client_delay_evidence = client_delay_evidence.resolve()
        if not client_delay_evidence.is_dir():
            raise FileNotFoundError(f"Client-delay evidence directory does not exist: {client_delay_evidence}")

    generated_utc = datetime.now(timezone.utc).isoformat()
    runtime_environment = _runtime_environment()
    records = discover_sessions(data_root)
    if not records:
        raise RuntimeError(f"No dated sessions found under {data_root}")
    input_provenance = _write_input_provenance(data_root, output_root, generated_utc)
    inventory = _portable_inventory(records)
    _write_frame(inventory, output_root / "session_inventory.csv")

    quality_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    target_frames: list[pd.DataFrame] = []
    recovery_rows: list[dict[str, object]] = []
    failed_sessions = 0
    for record in records:
        standard_dir = output_root / "sessions" / record.date / record.run_id
        try:
            gaze, video, markers = standardise_session(record, standard_dir)
            if recover_targets_from_video:
                recovery = recover_video_targets(record, markers, video)
                markers = recovery.markers
                markers.to_csv(standard_dir / "standard_marker_events.csv", index=False)
                _write_frame(recovery.audit, standard_dir / "video_target_recovery_audit.csv")
                recovery_rows.append(recovery.summary)
            make_session_review(record.session_id, gaze, markers, standard_dir / "session_review.png")
            quality_rows.append(
                evaluate_quality(record, gaze, video, markers, thresholds, target_settle_time_s)
            )
            metric_rows.append(compute_metrics(record, gaze, video, markers, target_settle_time_s))
            target_frame = target_level_metrics(record, gaze, markers, target_settle_time_s)
            if not target_frame.empty:
                target_frames.append(target_frame)
        except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError, pd.errors.ParserError) as error:
            failed_sessions += 1
            quality, metrics = _import_failure_rows(record, error, target_settle_time_s)
            quality_rows.append(quality)
            metric_rows.append(metrics)

    quality = pd.DataFrame(quality_rows)
    metrics = pd.DataFrame(metric_rows)
    _write_frame(quality, output_root / "quality_report.csv")
    _write_frame(metrics, output_root / "benchmark_metrics.csv")
    recovery_summary = pd.DataFrame(recovery_rows)
    if recover_targets_from_video:
        _write_frame(recovery_summary, output_root / "video_target_recovery_summary.csv")
    target_metrics = (
        pd.concat(target_frames, ignore_index=True)
        if target_frames
        else pd.DataFrame(columns=TARGET_METRIC_COLUMNS)
    )
    target_visits = (
        build_target_visit_summary(target_metrics)
        if not target_metrics.empty
        else pd.DataFrame(columns=TARGET_VISIT_COLUMNS)
    )
    _write_frame(target_metrics, output_root / "target_metrics.csv")
    _write_frame(target_visits, output_root / "target_visit_summary.csv")

    quality_for_merge = quality.rename(
        columns={
            "valid_rate": "quality_valid_rate",
            "data_loss_rate": "quality_data_loss_rate",
            "estimated_missing_samples": "quality_estimated_missing_samples",
            "longest_gap_s": "quality_longest_gap_s",
            "marker_events": "quality_marker_events",
            "marker_coverage_rate": "quality_marker_coverage_rate",
        }
    )
    # Keep inventory calibration fields unsuffixed for reporting.
    metric_metadata = {
        "calibration_avg_error", "calibration_valid_points", "calibration_high_quality_samples",
        "calibration_confidence_threshold", "calibration_error_unit", "calibration_status",
        "calibration_source",
    }
    metrics_for_merge = metrics.drop(
        columns=[column for column in metric_metadata if column in metrics], errors="ignore"
    )
    combined_inventory = inventory
    if recover_targets_from_video and not recovery_summary.empty:
        combined_inventory = combined_inventory.merge(recovery_summary, on="session_id", how="left")
    combined = combined_inventory.merge(quality_for_merge, on="session_id", how="left").merge(
        metrics_for_merge, on="session_id", how="left"
    )
    combined = combined.sort_values(["date", "run_id"]).reset_index(drop=True)
    _write_frame(combined, output_root / "combined_results.csv")

    long_term = build_long_term_summary(combined)
    _write_frame(long_term, output_root / "long_term_summary.csv")
    repeatability = build_repeatability_summary(combined)
    _write_frame(repeatability, output_root / "repeatability_summary.csv")
    paper_criteria = _paper_reference_criteria(
        combined, target_metrics, repeatability, target_settle_time_s
    )
    _write_frame(paper_criteria, output_root / "paper_reference_criteria.csv")
    summary = _summary(combined, records, failed_sessions)
    summary["target_interval_observations"] = int(len(target_metrics))
    summary["target_visit_observations"] = int(len(target_visits))
    summary["target_settle_time_s"] = target_settle_time_s
    summary["target_settle_excluded_valid_samples"] = int(
        pd.to_numeric(
            target_metrics.get("settle_excluded_valid_samples", pd.Series(dtype=float)), errors="coerce"
        ).fillna(0).sum()
    )
    summary["video_target_recovery_enabled"] = bool(recover_targets_from_video)
    summary["video_target_recovered_sessions"] = int(
        pd.to_numeric(
            recovery_summary.get("target_recovery_validation_passed", pd.Series(dtype=float)),
            errors="coerce",
        ).fillna(0).astype(bool).sum()
    )
    summary["video_target_recovered_intervals"] = int(
        pd.to_numeric(
            recovery_summary.get("recovered_target_intervals", pd.Series(dtype=float)),
            errors="coerce",
        ).fillna(0).sum()
    )
    paper_eligible_targets = (
        target_visits[target_visits["paper_plot_status"].astype(str).eq("included")].copy()
        if not target_visits.empty and "paper_plot_status" in target_visits
        else target_visits.iloc[0:0].copy()
    )
    angular_target_figures = bool(
        not paper_eligible_targets.empty
        and paper_eligible_targets["visit_index"].nunique() >= 2
        and pd.to_numeric(
            paper_eligible_targets["target_eccentricity_deg"], errors="coerce"
        ).nunique() >= 2
        and pd.to_numeric(
            paper_eligible_targets.get(
                "paper_qc_omae_deg", pd.Series(index=paper_eligible_targets.index, dtype=float)
            ),
            errors="coerce",
        ).notna().any()
        and paper_eligible_targets["subject_id"].fillna("").replace("unknown", "").ne("").any()
    )
    normalised_target_figures = bool(
        not paper_eligible_targets.empty
        and "target_eccentricity_normalised" in paper_eligible_targets
        and paper_eligible_targets.get(
            "coordinate_space", pd.Series(index=paper_eligible_targets.index, dtype=str)
        ).astype(str).eq("normalised").any()
        and pd.to_numeric(
            paper_eligible_targets["target_eccentricity_normalised"], errors="coerce"
        ).nunique() >= 2
        and pd.to_numeric(
            paper_eligible_targets.get(
                "paper_qc_omae_normalised", pd.Series(index=paper_eligible_targets.index, dtype=float)
            ),
            errors="coerce",
        ).notna().any()
    )
    summary["angular_target_figures_available"] = angular_target_figures
    summary["normalised_target_figures_available"] = normalised_target_figures
    summary["target_visualisation_unit"] = (
        "degrees" if angular_target_figures else "normalised_screen_fraction" if normalised_target_figures else "unavailable"
    )
    summary["paper_aligned_figures_available"] = angular_target_figures or normalised_target_figures
    summary["client_delay_evidence_included"] = client_delay_evidence is not None
    summary["input_provenance_file"] = "input_provenance.json"
    summary["input_file_count"] = int(input_provenance["file_count"])
    summary["input_hash_error_count"] = int(input_provenance["hash_error_count"])
    summary["input_content_digest_sha256"] = str(input_provenance["content_digest_sha256"])
    summary["runtime_environment"] = runtime_environment
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    make_figures(combined, long_term, output_root / "figures", target_visits=target_visits)
    report_path = write_html_report(
        combined,
        long_term,
        summary,
        output_root / "report.html",
        repeatability=repeatability,
        target_visits=target_visits,
        paper_criteria=paper_criteria,
        client_delay_evidence=client_delay_evidence,
    )
    manifest = {
        "openet2_version": __version__,
        "generated_utc": generated_utc,
        "runtime_environment": runtime_environment,
        "processing_duration_s": time.monotonic() - pipeline_started,
        "data_root": "openet2://input",
        "output_root": "openet2://output",
        "path_policy": "portable_logical_roots",
        "session_path_base": "data_root",
        "thresholds": asdict(thresholds),
        "session_count": len(records),
        "failed_sessions": failed_sessions,
        "target_interval_observations": len(target_metrics),
        "target_visit_observations": len(target_visits),
        "target_settle_time_s": target_settle_time_s,
        "target_settle_excluded_valid_samples": summary["target_settle_excluded_valid_samples"],
        "video_target_recovery_enabled": recover_targets_from_video,
        "video_target_recovered_sessions": summary["video_target_recovered_sessions"],
        "video_target_recovered_intervals": summary["video_target_recovered_intervals"],
        "paper_aligned_figures_available": summary["paper_aligned_figures_available"],
        "client_delay_evidence_included": summary["client_delay_evidence_included"],
        "angular_target_figures_available": summary["angular_target_figures_available"],
        "normalised_target_figures_available": summary["normalised_target_figures_available"],
        "target_visualisation_unit": summary["target_visualisation_unit"],
        "source_data_modified": False,
        "input_provenance_file": "input_provenance.json",
        "input_file_count": int(input_provenance["file_count"]),
        "input_hash_error_count": int(input_provenance["hash_error_count"]),
        "input_content_digest_sha256": str(input_provenance["content_digest_sha256"]),
    }
    (output_root / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return PipelineResult(
        output_root=output_root,
        session_count=len(records),
        successful_sessions=len(records) - failed_sessions,
        failed_sessions=failed_sessions,
        report_path=report_path,
    )
