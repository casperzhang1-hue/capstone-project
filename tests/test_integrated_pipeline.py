"""Integration tests for the OpenET 2 pipeline."""

from __future__ import annotations

import json

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from openet2.analysis import (
    build_repeatability_summary,
    build_target_visit_summary,
    interval_statistics,
    marker_based_metrics,
    target_level_metrics,
)
from openet2.collection import ACCURACY_TARGETS, CollectionConfig, collect_session
from openet2.config import QualityThresholds
from openet2.importers import import_gaze_file, standardise_session
from openet2.legacy import create_session_folder
from openet2.metadata import SessionRecord, discover_sessions
from openet2.pipeline import run_pipeline
from openet2.reporting import _observation_ellipse_parameters, _paper_plot_data
from openet2.video_targets import recover_targets_from_video


class ImporterTests(unittest.TestCase):
    """Test data import and metric behaviour."""

    def test_millisecond_time_column_is_converted_to_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gaze_data.csv"
            pd.DataFrame(
                {
                    "Time (ms)": [1000, 1016, 1032],
                    "gaze_x": [0.1, 0.2, 0.3],
                    "gaze_y": [0.4, 0.5, 0.6],
                    "valid": [1, 1, 1],
                }
            ).to_csv(path, index=False)
            gaze = import_gaze_file(path, source_device="fixture")
            self.assertAlmostEqual(gaze.loc[0, "time_s"], 1.0)
            self.assertAlmostEqual(gaze.loc[2, "time_s"], 1.032)
            self.assertEqual(gaze.loc[0, "coordinate_space"], "normalised")

    def test_gp3_fpog_columns_remain_normalised_when_outliers_exist(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "GP3HD_data.csv"
            pd.DataFrame(
                {
                    "TIME": [0.0, 0.1, 0.2, 0.3],
                    "FPOGX": [0.50, 0.52, 4.00, 0.49],
                    "FPOGY": [0.50, 0.48, 0.50, 0.51],
                    "FPOGV": [1, 1, 1, 1],
                }
            ).to_csv(path, index=False)
            gaze = import_gaze_file(path, source_device="GP3HD")
            self.assertTrue(gaze["coordinate_space"].eq("normalised").all())
            self.assertGreater(gaze["gaze_x"].max(), 1.0)

    def test_marker_precision_uses_only_samples_inside_marker_periods(self) -> None:
        gaze = pd.DataFrame(
            {
                "time_s": np.arange(10, dtype=float),
                "gaze_x": [0.5, 0.5, 0.49, 0.51, 0.5, 0.8, 0.8, 0.79, 0.81, 0.8],
                "gaze_y": [0.5, 0.51, 0.5, 0.49, 0.5, 0.2, 0.21, 0.2, 0.19, 0.2],
                "valid": 1,
            }
        )
        markers = pd.DataFrame(
            {
                "marker_start_s": [0.0, 5.0],
                "marker_end_s": [4.0, 9.0],
                "target_x": [0.5, 0.8],
                "target_y": [0.5, 0.2],
            }
        )
        metrics = marker_based_metrics(gaze, markers)
        self.assertEqual(metrics["marker_coverage_rate"], 1.0)
        self.assertLess(metrics["marker_precision_rms"], 0.02)
        self.assertLess(metrics["marker_accuracy_rmse"], 0.01)

    def test_gap_detection_estimates_missing_samples(self) -> None:
        stats = interval_statistics(pd.Series([0.00, 0.01, 0.02, 0.05, 0.06]))
        self.assertEqual(stats["estimated_missing_samples"], 2)
        self.assertAlmostEqual(stats["longest_gap_s"], 0.03)

    def test_angular_metrics_are_available_with_physical_display_metadata(self) -> None:
        gaze = pd.DataFrame(
            {
                "time_s": np.arange(10) / 10,
                "gaze_x": [0.51] * 10,
                "gaze_y": [0.50] * 10,
                "valid": [1] * 10,
            }
        )
        markers = pd.DataFrame(
            {"marker_start_s": [0.0], "marker_end_s": [0.9], "target_x": [0.5], "target_y": [0.5]}
        )
        record = SessionRecord(
            session_id="fixture", date="2026_01_01", run_id="000", session_path=".",
            display_width_mm=530, display_height_mm=300, viewing_distance_mm=600,
        )
        metrics = marker_based_metrics(gaze, markers, record)
        self.assertTrue(np.isfinite(metrics["marker_omae_deg"]))
        self.assertGreater(metrics["marker_omae_deg"], 0)

    def test_target_level_metrics_support_paper_aligned_figures(self) -> None:
        gaze = pd.DataFrame(
            {
                "time_s": np.arange(10) / 10,
                "gaze_x": [0.51] * 10,
                "gaze_y": [0.49] * 10,
                "valid": [1] * 10,
                "coordinate_space": ["normalised"] * 10,
            }
        )
        markers = pd.DataFrame(
            {
                "marker_start_s": [0.0], "marker_end_s": [0.9], "marker_id": ["centre_r1"],
                "target_x": [0.5], "target_y": [0.5],
            }
        )
        record = SessionRecord(
            session_id="2026_01_01/000", date="2026_01_01", run_id="000", session_path=".",
            subject_id="P01", device_id="GP3", test_id="Accuracy", test_condition="standard",
            recording_start_time=1.0, trial_number=1,
            display_width_mm=530, display_height_mm=300, viewing_distance_mm=600,
        )
        target_metrics = target_level_metrics(record, gaze, markers)
        self.assertEqual(len(target_metrics), 1)
        self.assertEqual(target_metrics.loc[0, "target_label"], "centre")
        self.assertAlmostEqual(target_metrics.loc[0, "target_eccentricity_deg"], 0.0)
        self.assertGreater(target_metrics.loc[0, "omae_deg"], 0)
        self.assertEqual(target_metrics.loc[0, "paper_qc_status"], "included")
        summary = build_target_visit_summary(target_metrics)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.loc[0, "visit_label"], "Visit 1")
        self.assertEqual(summary.loc[0, "paper_qc_status"], "included")

    def test_target_level_metrics_keep_normalised_values_without_physical_geometry(self) -> None:
        gaze = pd.DataFrame(
            {
                "time_s": np.arange(10) / 10,
                "gaze_x": [0.51] * 10,
                "gaze_y": [0.49] * 10,
                "valid": [1] * 10,
                "coordinate_space": ["normalised"] * 10,
            }
        )
        markers = pd.DataFrame(
            {
                "marker_start_s": [0.0], "marker_end_s": [0.9], "marker_id": ["centre_r1"],
                "target_x": [0.5], "target_y": [0.5],
            }
        )
        record = SessionRecord(
            session_id="2026_01_01/000", date="2026_01_01", run_id="000", session_path=".",
            subject_id="P01", device_id="GP3", test_id="Accuracy", test_condition="standard",
        )
        target_metrics = target_level_metrics(record, gaze, markers)
        self.assertTrue(np.isfinite(target_metrics.loc[0, "omae_normalised"]))
        self.assertTrue(np.isnan(target_metrics.loc[0, "omae_deg"]))
        summary = build_target_visit_summary(target_metrics)
        self.assertEqual(len(summary), 1)
        self.assertTrue(np.isfinite(summary.loc[0, "omae_normalised"]))

    def test_paper_plot_qc_excludes_off_screen_samples_but_preserves_raw_metrics(self) -> None:
        gaze = pd.DataFrame(
            {
                "time_s": np.arange(10) / 10,
                "gaze_x": [0.5] * 8 + [4.0, 4.0],
                "gaze_y": [0.5] * 10,
                "valid": [1] * 10,
                "coordinate_space": ["normalised"] * 10,
            }
        )
        markers = pd.DataFrame(
            {
                "marker_start_s": [0.0], "marker_end_s": [0.9], "marker_id": ["centre_r1"],
                "target_x": [0.5], "target_y": [0.5],
            }
        )
        record = SessionRecord(
            session_id="2026_01_01/000", date="2026_01_01", run_id="000", session_path=".",
            subject_id="P01", device_id="GP3", test_id="Accuracy", test_condition="standard",
        )

        target_metrics = target_level_metrics(record, gaze, markers)
        self.assertGreater(target_metrics.loc[0, "mean_gaze_x"], 1.0)
        self.assertEqual(target_metrics.loc[0, "paper_qc_status"], "included")
        self.assertEqual(target_metrics.loc[0, "paper_qc_valid_samples"], 8)
        self.assertEqual(target_metrics.loc[0, "paper_qc_excluded_samples"], 2)
        self.assertAlmostEqual(target_metrics.loc[0, "paper_qc_mean_gaze_x"], 0.5)
        self.assertGreater(
            target_metrics.loc[0, "omae_normalised"],
            target_metrics.loc[0, "paper_qc_omae_normalised"],
        )
        self.assertAlmostEqual(target_metrics.loc[0, "paper_qc_omae_normalised"], 0.0)
        summary = build_target_visit_summary(target_metrics)
        self.assertAlmostEqual(summary.loc[0, "paper_qc_gaze_direction_x_normalised"], 0.0)
        self.assertAlmostEqual(summary.loc[0, "paper_qc_omae_normalised"], 0.0)
        paper, mode = _paper_plot_data(summary)
        self.assertEqual(mode, "normalised")
        self.assertAlmostEqual(paper.loc[0, "plot_omae"], 0.0)

    def test_observation_ellipse_represents_dispersion_not_mean_uncertainty(self) -> None:
        points = np.asarray([[-1.0, 0.0], [1.0, 0.0], [0.0, -1.0], [0.0, 1.0]])
        parameters = _observation_ellipse_parameters(points)
        self.assertIsNotNone(parameters)
        _, width, height, _ = parameters
        self.assertGreater(width, 3.0)
        self.assertGreater(height, 3.0)


@unittest.skipUnless(importlib.util.find_spec("cv2"), "optional OpenCV dependency is not installed")
class VideoTargetRecoveryTests(unittest.TestCase):
    """Test video target recovery safeguards."""

    def test_video_recovery_requires_complete_nine_point_three_repeat_validation(self) -> None:
        import cv2

        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder)
            width, height = 640, 360
            video_path = session / "ext_display_acc_video.avi"
            writer = cv2.VideoWriter(
                str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (width, height)
            )
            self.assertTrue(writer.isOpened())
            marker_rows = []
            video_rows = []
            for index, (_, target_x, target_y) in enumerate(list(ACCURACY_TARGETS) * 3):
                frame = np.full((height, width, 3), 255, dtype=np.uint8)
                cv2.circle(
                    frame,
                    (int(target_x * width), int(target_y * height)),
                    8,
                    (0, 0, 0),
                    2,
                )
                writer.write(frame)
                marker_rows.append(
                    {"marker_start_s": float(index), "marker_end_s": float(index) + 0.8}
                )
                video_rows.append({"frame_id": index, "time_s": float(index) + 0.4})
            writer.release()
            (session / "Recording_info.csv").write_text(
                "video_out_fn,ext_display_acc_video.avi\n", encoding="utf-8"
            )
            markers = pd.DataFrame(marker_rows)
            markers["marker_id"] = [f"target_{index + 1:02d}" for index in range(len(markers))]
            markers["target_x"] = np.nan
            markers["target_y"] = np.nan
            markers["coordinate_space"] = "unknown"
            markers["target_duration_s"] = 0.8
            original = markers.copy(deep=True)
            record = SessionRecord(
                session_id="2026_01_01/000",
                date="2026_01_01",
                run_id="000",
                session_path=str(session),
            )
            result = recover_targets_from_video(record, markers, pd.DataFrame(video_rows))
            self.assertTrue(result.summary["target_recovery_validation_passed"])
            self.assertEqual(result.summary["recovered_target_intervals"], 27)
            self.assertEqual(result.markers[["target_x", "target_y"]].drop_duplicates().shape[0], 9)
            self.assertTrue((result.audit["detection_status"] == "recovered").all())
            self.assertTrue(original["target_x"].isna().all())


class PipelineTests(unittest.TestCase):
    """Test the complete offline pipeline."""

    def _create_session(self, root: Path) -> Path:
        session = root / "2026_07_16" / "000"
        session.mkdir(parents=True)
        times = np.arange(0.0, 2.0, 1 / 60)
        pd.DataFrame(
            {
                "Time_s": times,
                "FPOGX": 0.5 + 0.005 * np.sin(times * 10),
                "FPOGY": 0.5 + 0.005 * np.cos(times * 10),
                "FPOGV": 1,
                "CX": 0.5,
                "CY": 0.5,
            }
        ).to_csv(session / "GP3HD_data.csv", index=False)
        pd.DataFrame({"FrameID": range(60), "Time_s": np.arange(60) / 30}).to_csv(
            session / "Video_data.csv", index=False
        )
        pd.DataFrame([[0.1, 0.9], [1.0, 1.8]]).to_csv(
            session / "acc_marker_external.csv", index=False, header=False
        )
        (session / "Recording_info.csv").write_text(
            "Recording start time,1744000000\nSubjectID,TEST01\nEyeTrackerID,GP3HD\nTestID,Accuracy\n"
            "TrialNumber,1\nTestCondition,standard\n"
            "width,1920\nheight,1080\nCalibration avg error,0.42\nCalibration valid points,5\n"
            "CalibrationErrorUnit,degrees\n",
            encoding="utf-8",
        )
        (session / "Calibration_info.txt").write_text("fixture", encoding="utf-8")
        return session

    def test_discovery_and_complete_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_root = root / "data"
            self._create_session(data_root)
            records = discover_sessions(data_root)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].session_id, "2026_07_16/000")
            self.assertEqual(records[0].calibration_valid_points, 5)

            output = root / "outputs"
            result = run_pipeline(
                data_root,
                output,
                QualityThresholds(expected_marker_events=2),
            )
            self.assertEqual(result.session_count, 1)
            self.assertEqual(result.failed_sessions, 0)
            self.assertTrue((output / "combined_results.csv").exists())
            self.assertTrue((output / "long_term_summary.csv").exists())
            self.assertTrue((output / "report.html").exists())
            combined = pd.read_csv(output / "combined_results.csv")
            self.assertEqual(combined.loc[0, "quality_status"], "pass")
            self.assertGreater(combined.loc[0, "marker_coverage_rate"], 0.9)
            self.assertIn("calibration_avg_error", combined.columns)
            self.assertNotIn("calibration_avg_error_x", combined.columns)


class LegacyContinuationTests(unittest.TestCase):
    """Test compatibility with supplied legacy helpers."""

    @property
    def legacy_code_root(self) -> Path:
        return Path(__file__).resolve().parents[1] / "docker" / "legacy_code"

    def test_original_session_folder_contract_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = create_session_folder(self.legacy_code_root, root)
            second = create_session_folder(self.legacy_code_root, root)
            self.assertEqual(first.parent, second.parent)
            self.assertEqual(first.name, "000")
            self.assertEqual(second.name, "001")

    def test_original_tobii_columns_and_mislabelled_epoch_seconds_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Tobii_data.csv"
            pd.DataFrame(
                {
                    "SysTime(ms)": [1_744_413_281.50, 1_744_413_281.52],
                    "TobiiSysTime": [10, 20],
                    "OD_x": [0.4, 0.5],
                    "OD_y": [0.2, 0.3],
                    "OS_x": [0.6, 0.7],
                    "OS_y": [0.4, 0.5],
                }
            ).to_csv(path, index=False)
            gaze = import_gaze_file(path, source_device="Tobii")
            self.assertAlmostEqual(gaze.loc[1, "time_s"] - gaze.loc[0, "time_s"], 0.02, places=5)
            self.assertAlmostEqual(gaze.loc[0, "gaze_x"], 0.5)
            self.assertAlmostEqual(gaze.loc[0, "gaze_y"], 0.3)

    def test_collection_dry_run_uses_original_folder_creator(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output_root = Path(folder)
            session = collect_session(
                CollectionConfig(
                    legacy_code_root=self.legacy_code_root,
                    output_root=output_root,
                    subject_id="DRY01",
                    device_id="GP3HD",
                    test_id="Dry run",
                    duration_s=0.2,
                    dry_run=True,
                )
            )
            self.assertEqual(session.name, "000")
            self.assertTrue((session / "Recording_info.csv").exists())
            self.assertTrue((session / "GP3HD_data.csv").exists())
            self.assertTrue((session / "Video_data.csv").exists())
            self.assertTrue((session / "marker_data.csv").exists())
            self.assertTrue((session / "calibration_summary.json").exists())
            markers = pd.read_csv(session / "marker_data.csv")
            self.assertEqual(len(markers), 27)
            self.assertTrue((session / "marker_plan.csv").exists())
            self.assertTrue((session / "marker_timing_summary.json").exists())
            timing_summary = json.loads((session / "marker_timing_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(timing_summary["onset_delay_ms"]["count"], 27)
            self.assertIn("application-level", timing_summary["interpretation"])
            self.assertTrue((markers["planned_start_s"] == markers["marker_start_s"]).all())
            self.assertTrue((markers["planned_end_s"] == markers["marker_end_s"]).all())
            self.assertTrue((markers["timing_source"] == "simulated_schedule").all())
            self.assertTrue(markers["target_x"].between(0, 1).all())
            self.assertTrue(markers["target_y"].between(0, 1).all())
            events = (session / "workflow_events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"state": "completed"', events)

    def test_legacy_epoch_seconds_are_standardised_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder)
            start = 1_744_000_000.0
            (session / "Recording_info.csv").write_text(
                f"Recording start time,{start}\n",
                encoding="utf-8",
            )
            pd.DataFrame(
                {"Time (ms)": [start + 1, start + 2], "FPOGX": [0.1, 0.2], "FPOGY": [0.3, 0.4]}
            ).to_csv(
                session / "GP3HD_data.csv", index=False
            )
            pd.DataFrame({"FrameID": [0, 1], "Time (ms)": [start + 3, start + 4]}).to_csv(
                session / "Video_data.csv", index=False
            )
            pd.DataFrame(
                {"Start_time(ms)": [start + 5], "End_time(ms)": [start + 6], "marker_x": [960], "marker_y": [540]}
            ).to_csv(session / "marker_data.csv", index=False)

            record = SessionRecord(
                session_id="2026_01_01/000", date="2026_01_01", run_id="000", session_path=str(session),
                device_id="GP3HD", gaze_file="GP3HD_data.csv", recording_start_time=start,
                display_width_px=1920, display_height_px=1080,
            )
            original_gaze = (session / "GP3HD_data.csv").read_bytes()
            gaze, video, markers = standardise_session(record, session / "standard")
            self.assertEqual(list(gaze["time_s"]), [1.0, 2.0])
            self.assertEqual(list(video["time_s"]), [3.0, 4.0])
            self.assertEqual(markers.loc[0, "marker_start_s"], 5.0)
            self.assertEqual(markers.loc[0, "marker_end_s"], 6.0)
            alignment = json.loads((session / "standard" / "time_alignment.json").read_text(encoding="utf-8"))
            self.assertEqual(alignment["origin_source"], "recording_start_time")
            self.assertEqual(alignment["time_origin_epoch_s"], start)
            self.assertEqual(alignment["standard_time_basis"], "relative_seconds")
            self.assertEqual((session / "GP3HD_data.csv").read_bytes(), original_gaze)

    def test_epoch_origin_is_inferred_when_recording_metadata_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder)
            start = 1_744_100_000.0
            pd.DataFrame(
                {
                    "Time (ms)": [start + 0.10, start + 0.20],
                    "FPOGX": [0.5, 0.51],
                    "FPOGY": [0.5, 0.49],
                    "FPOGV": [1, 1],
                }
            ).to_csv(session / "GP3HD_data.csv", index=False)
            pd.DataFrame(
                {"FrameID": [0, 1], "Time (ms)": [start + 0.05, start + 0.15]}
            ).to_csv(session / "Video_data.csv", index=False)
            pd.DataFrame(
                {
                    "Start_time(ms)": [start],
                    "End_time(ms)": [start + 0.30],
                    "target_x": [0.5],
                    "target_y": [0.5],
                }
            ).to_csv(session / "marker_data.csv", index=False)
            record = SessionRecord(
                session_id="2026_01_01/000",
                date="2026_01_01",
                run_id="000",
                session_path=str(session),
                device_id="GP3HD",
                gaze_file="GP3HD_data.csv",
            )
            gaze, video, markers = standardise_session(record, session / "standard")
            self.assertAlmostEqual(gaze.loc[0, "time_s"], 0.10, places=5)
            self.assertAlmostEqual(video.loc[0, "time_s"], 0.05, places=5)
            self.assertAlmostEqual(markers.loc[0, "marker_start_s"], 0.0, places=5)
            alignment = json.loads((session / "standard" / "time_alignment.json").read_text(encoding="utf-8"))
            self.assertEqual(alignment["origin_source"], "inferred_earliest_epoch_timestamp")
            self.assertEqual(alignment["time_origin_epoch_s"], start)
            self.assertEqual(len(alignment["transformed_columns"]), 4)


class LongTermTests(unittest.TestCase):
    """Test longitudinal repeatability grouping."""

    def test_repeatability_summary_keeps_participants_separate(self) -> None:
        combined = pd.DataFrame(
            {
                "session_id": ["a", "b", "c"], "date": ["2026_01_01", "2026_01_02", "2026_01_02"],
                "subject_id": ["P01", "P01", "P02"], "device_id": ["GP3"] * 3,
                "test_id": ["Accuracy"] * 3, "test_condition": ["standard"] * 3,
                "effective_sampling_hz": [60, 59, 40], "valid_rate": [0.9, 0.8, 0.2],
                "marker_precision_rms": [0.01, 0.02, 0.3],
            }
        )
        summary = build_repeatability_summary(combined)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.loc[0, "subject_id"], "P01")
        self.assertEqual(summary.loc[0, "session_count"], 2)


if __name__ == "__main__":
    unittest.main()
