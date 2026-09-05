"""Provide the OpenET 2 command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from .collection import CollectionConfig, collect_session
from .config import QualityThresholds
from .example_data import generate_longitudinal_example
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(
        prog="openet2",
        description="OpenET 2 remote eye-tracker benchmarking tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run the complete offline benchmarking pipeline")
    run.add_argument("--data-root", type=Path, required=True, help="Root containing YYYY_MM_DD/session folders")
    run.add_argument("--output-root", type=Path, required=True, help="Destination for standard tables and reports")
    run.add_argument("--min-valid-rate", type=float, default=0.80)
    run.add_argument("--max-irregular-interval-pct", type=float, default=0.20)
    run.add_argument("--interval-tolerance-fraction", type=float, default=0.50)
    run.add_argument("--expected-marker-events", type=int, default=27)
    run.add_argument("--max-duration-mismatch-fraction", type=float, default=0.20)
    run.add_argument("--max-out-of-bounds-rate", type=float, default=0.01)
    run.add_argument("--max-data-loss-rate", type=float, default=0.20)
    run.add_argument("--max-longest-gap-s", type=float, default=0.25)
    run.add_argument("--min-marker-coverage-rate", type=float, default=0.80)
    run.add_argument("--min-calibration-valid-points", type=int, default=5)
    run.add_argument("--max-calibration-error", type=float, default=1.0)
    run.add_argument(
        "--calibration-error-unit",
        default="degrees",
        help="Unit to which --max-calibration-error applies; other/unknown units are not compared",
    )
    run.add_argument("--max-incomplete-recording-fraction", type=float, default=0.10)
    run.add_argument(
        "--disable-marker-count-check",
        action="store_true",
        help="Do not warn when a session has a different number of marker events",
    )
    run.add_argument(
        "--recover-targets-from-video",
        action="store_true",
        help=(
            "Recover the supplied legacy nine-point target order from AVI screen recordings; "
            "requires the optional video dependencies"
        ),
    )
    run.add_argument(
        "--target-settle-time-s",
        type=float,
        default=0.6,
        help="Seconds excluded after each target onset before target metrics (paper reference: 0.6)",
    )
    run.add_argument(
        "--client-delay-evidence",
        type=Path,
        help="Optional directory containing auditable client-delay evidence to include in the HTML report",
    )
    collect = subparsers.add_parser(
        "collect",
        help="Create a guarded collection session using the continued original OpenET code",
    )
    collect.add_argument("--legacy-code-root", type=Path, required=True)
    collect.add_argument("--output-root", type=Path, required=True)
    collect.add_argument("--subject-id", required=True)
    collect.add_argument("--device-id", default="GP3HD")
    collect.add_argument("--test-id", default="Accuracy benchmark")
    collect.add_argument("--duration-s", type=float, default=30.0)
    collect.add_argument("--trial-number", type=int, default=1)
    collect.add_argument("--test-condition", default="standard")
    collect.add_argument("--visit-label", default="", help="Repeated-measurement label, e.g. baseline, plus_5min or plus_1h")
    collect.add_argument("--operator-id", default="")
    collect.add_argument("--device-model", default="")
    collect.add_argument("--device-serial", default="")
    collect.add_argument("--device-software-version", default="")
    collect.add_argument("--nominal-sampling-hz", type=float, default=60.0)
    collect.add_argument("--calibration-method", default="manual")
    collect.add_argument(
        "--calibration-confirmed",
        action="store_true",
        help="Confirm that live calibration was completed before recording",
    )
    collect.add_argument(
        "--calibration-result-json",
        type=Path,
        help="Device-exported passing calibration result with status, error, unit and valid points",
    )
    collect.add_argument("--validation-method", default="nine-point accuracy protocol")
    collect.add_argument("--display-width-px", type=int, default=1920)
    collect.add_argument("--display-height-px", type=int, default=1080)
    collect.add_argument("--display-width-mm", type=float)
    collect.add_argument("--display-height-mm", type=float)
    collect.add_argument("--viewing-distance-mm", type=float)
    collect.add_argument("--display-model", default="")
    collect.add_argument("--display-refresh-hz", type=float)
    collect.add_argument("--environment", default="")
    collect.add_argument("--ambient-illuminance-lux", type=float)
    collect.add_argument("--head-support", default="")
    collect.add_argument("--notes", default="")
    collect.add_argument("--target-presentation-s", type=float, help="Optional fixed display time for every target; validates research protocol capacity")
    collect.add_argument("--target-settle-time-s", type=float, default=0.6, help="Settling period recorded in target markers")
    collect.add_argument("--minimum-post-settle-valid-samples", type=int, default=100, help="Nominal minimum retained samples required when --target-presentation-s is used")
    collect.add_argument("--video-monitor-id", type=int, default=1)
    collect.add_argument("--video-fps", type=float, default=30.0)
    collect.add_argument("--marker-repeats", type=int, default=3)
    collect.add_argument("--random-seed", type=int, default=2026)
    collect.add_argument("--skip-calibration", action="store_true")
    collect.add_argument("--skip-validation", action="store_true")
    collect.add_argument("--skip-stimulus", action="store_true")
    collect.add_argument("--skip-video", action="store_true")
    collect.add_argument(
        "--live",
        action="store_true",
        help="Use the guarded GP3/Tobii hardware adapter; otherwise create a deterministic dry run",
    )
    collect.add_argument(
        "--leave-gazepoint-control-running",
        action="store_true",
        help="Do not start or stop the Gazepoint Control application",
    )
    example = subparsers.add_parser(
        "generate-example",
        help="Generate a clearly labelled synthetic multi-date validation dataset",
    )
    example.add_argument("--output-root", type=Path, required=True)
    example.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the selected command and return its exit code."""

    args = build_parser().parse_args(argv)
    if args.command == "run":
        thresholds = QualityThresholds(
            min_valid_rate=args.min_valid_rate,
            max_irregular_interval_pct=args.max_irregular_interval_pct,
            interval_tolerance_fraction=args.interval_tolerance_fraction,
            expected_marker_events=None if args.disable_marker_count_check else args.expected_marker_events,
            max_duration_mismatch_fraction=args.max_duration_mismatch_fraction,
            max_out_of_bounds_rate=args.max_out_of_bounds_rate,
            max_data_loss_rate=args.max_data_loss_rate,
            max_longest_gap_s=args.max_longest_gap_s,
            min_marker_coverage_rate=args.min_marker_coverage_rate,
            min_calibration_valid_points=args.min_calibration_valid_points,
            max_calibration_error=args.max_calibration_error,
            calibration_error_unit=args.calibration_error_unit,
            max_incomplete_recording_fraction=args.max_incomplete_recording_fraction,
        )
        result = run_pipeline(
            args.data_root,
            args.output_root,
            thresholds,
            recover_targets_from_video=args.recover_targets_from_video,
            target_settle_time_s=args.target_settle_time_s,
            client_delay_evidence=args.client_delay_evidence,
        )
        print(f"Discovered sessions: {result.session_count}")
        print(f"Processed successfully: {result.successful_sessions}")
        print(f"Processing failures: {result.failed_sessions}")
        print(f"Output folder: {result.output_root}")
        print(f"HTML report: {result.report_path}")
        return 0 if result.failed_sessions == 0 else 2
    if args.command == "collect":
        session_dir = collect_session(
            CollectionConfig(
                legacy_code_root=args.legacy_code_root,
                output_root=args.output_root,
                subject_id=args.subject_id,
                device_id=args.device_id,
                test_id=args.test_id,
                duration_s=args.duration_s,
                dry_run=not args.live,
                manage_gazepoint_control=not args.leave_gazepoint_control_running,
                trial_number=args.trial_number,
                test_condition=args.test_condition,
                visit_label=args.visit_label,
                operator_id=args.operator_id,
                device_model=args.device_model,
                device_serial=args.device_serial,
                device_software_version=args.device_software_version,
                nominal_sampling_hz=args.nominal_sampling_hz,
                calibration_method=args.calibration_method,
                calibration_confirmed=args.calibration_confirmed,
                calibration_result_json=args.calibration_result_json,
                validation_method=args.validation_method,
                display_width_px=args.display_width_px,
                display_height_px=args.display_height_px,
                display_width_mm=args.display_width_mm,
                display_height_mm=args.display_height_mm,
                viewing_distance_mm=args.viewing_distance_mm,
                display_model=args.display_model,
                display_refresh_hz=args.display_refresh_hz,
                environment=args.environment,
                ambient_illuminance_lux=args.ambient_illuminance_lux,
                head_support=args.head_support,
                notes=args.notes,
                target_presentation_s=args.target_presentation_s,
                target_settle_time_s=args.target_settle_time_s,
                minimum_post_settle_valid_samples=args.minimum_post_settle_valid_samples,
                run_calibration=not args.skip_calibration,
                run_validation=not args.skip_validation,
                present_stimulus=not args.skip_stimulus,
                capture_video=not args.skip_video,
                video_monitor_id=args.video_monitor_id,
                video_fps=args.video_fps,
                marker_repeats=args.marker_repeats,
                random_seed=args.random_seed,
            )
        )
        mode = "live" if args.live else "dry-run"
        print(f"Created {mode} session: {session_dir}")
        return 0
    if args.command == "generate-example":
        output = generate_longitudinal_example(args.output_root, overwrite=args.overwrite)
        print(f"Created synthetic longitudinal example: {output}")
        print("This dataset is software-validation evidence only; no hardware was used.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
