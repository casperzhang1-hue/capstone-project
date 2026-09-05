"""Requirement-level tests for the OpenET 2 package."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from openet2.analysis import evaluate_quality, target_level_metrics
from openet2.collection import CollectionConfig, _resolve_calibration, _target_timeline
from openet2.config import QualityThresholds
from openet2.example_data import generate_longitudinal_example
from openet2.importers import import_gaze_file, standardise_session
from openet2.metadata import SessionRecord, discover_sessions
from openet2.pipeline import run_pipeline


@pytest.mark.parametrize("suffix", [".csv", ".tsv", ".json"])
def test_csv_tsv_and_json_gaze_imports(suffix: str) -> None:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"gaze{suffix}"
        frame = pd.DataFrame(
            {"Time_s": [0.0, 0.1], "gaze_x": [0.4, 0.5], "gaze_y": [0.6, 0.5], "valid": [1, 1]}
        )
        if suffix == ".csv":
            frame.to_csv(path, index=False)
        elif suffix == ".tsv":
            frame.to_csv(path, sep="\t", index=False)
        else:
            path.write_text(json.dumps({"samples": frame.to_dict(orient="records")}), encoding="utf-8")
        imported = import_gaze_file(path, source_device="fixture")
        assert len(imported) == 2
        assert imported["valid"].sum() == 2


def test_rich_json_metadata_extends_legacy_csv() -> None:
    with tempfile.TemporaryDirectory() as folder:
        session = Path(folder) / "2026_01_01" / "000"
        session.mkdir(parents=True)
        (session / "Recording_info.csv").write_text(
            "Recording start time,1000\nSubjectID,P01\nEyeTrackerID,GP3\nTestID,Accuracy\n",
            encoding="utf-8",
        )
        (session / "session_metadata.json").write_text(
            json.dumps(
                {
                    "TrialNumber": 2,
                    "TestCondition": "low light",
                    "DeviceSerial": "ABC123",
                    "DeviceSoftwareVersion": "4.2",
                    "DisplayWidthMm": 530,
                    "DisplayHeightMm": 300,
                    "ViewingDistanceMm": 600,
                    "Environment": "24 C",
                }
            ),
            encoding="utf-8",
        )
        pd.DataFrame({"Time_s": [0, 0.1], "FPOGX": [0.5, 0.5], "FPOGY": [0.5, 0.5], "FPOGV": [1, 1]}).to_csv(
            session / "GP3HD_data.csv", index=False
        )
        record = discover_sessions(Path(folder))[0]
        assert record.trial_number == 2
        assert record.test_condition == "low light"
        assert record.device_serial == "ABC123"
        assert record.viewing_distance_mm == 600


def test_conflicting_json_metadata_is_flagged_without_overwriting_csv() -> None:
    with tempfile.TemporaryDirectory() as folder:
        session = Path(folder) / "2026_01_01" / "000"
        session.mkdir(parents=True)
        (session / "Recording_info.csv").write_text(
            "Recording start time,1000\nSubjectID,P01\nEyeTrackerID,GP3\n"
            "TestID,Accuracy\nTrialNumber,1\nTestCondition,standard\n",
            encoding="utf-8",
        )
        (session / "session_metadata.json").write_text(
            json.dumps({"Subject ID": "P02", "Environment": "controlled"}),
            encoding="utf-8",
        )
        pd.DataFrame(
            {
                "Time_s": [0.0, 0.1],
                "FPOGX": [0.5, 0.5],
                "FPOGY": [0.5, 0.5],
                "FPOGV": [1, 1],
            }
        ).to_csv(session / "GP3HD_data.csv", index=False)

        record = discover_sessions(Path(folder))[0]
        assert record.subject_id == "P01"
        assert record.environment == "controlled"
        assert record.metadata_conflict_fields == "SubjectID"

        gaze = pd.DataFrame(
            {
                "time_s": [0.0, 0.1],
                "gaze_x": [0.5, 0.5],
                "gaze_y": [0.5, 0.5],
                "valid": [1, 1],
                "coordinate_space": ["normalised", "normalised"],
            }
        )
        video = pd.DataFrame({"time_s": [0.0, 0.1]})
        quality = evaluate_quality(
            record,
            gaze,
            video,
            pd.DataFrame(),
            QualityThresholds(expected_marker_events=None),
        )
        assert "inconsistent_metadata" in quality["quality_flags"]
        assert quality["metadata_conflict_count"] == 1
        assert quality["metadata_conflict_fields"] == "SubjectID"


def test_unreadable_json_metadata_is_reported() -> None:
    with tempfile.TemporaryDirectory() as folder:
        session = Path(folder) / "2026_01_01" / "000"
        session.mkdir(parents=True)
        (session / "Recording_info.csv").write_text(
            "Recording start time,1000\nSubjectID,P01\nEyeTrackerID,GP3\n"
            "TestID,Accuracy\nTrialNumber,1\nTestCondition,standard\n",
            encoding="utf-8",
        )
        (session / "session_metadata.json").write_text("{not valid JSON", encoding="utf-8")
        pd.DataFrame(
            {"Time_s": [0.0, 0.1], "FPOGX": [0.5, 0.5], "FPOGY": [0.5, 0.5], "FPOGV": [1, 1]}
        ).to_csv(session / "GP3HD_data.csv", index=False)

        record = discover_sessions(Path(folder))[0]
        assert record.metadata_read_error.startswith("JSONDecodeError:")
        quality = evaluate_quality(
            record,
            pd.DataFrame(
                {
                    "time_s": [0.0, 0.1],
                    "gaze_x": [0.5, 0.5],
                    "gaze_y": [0.5, 0.5],
                    "valid": [1, 1],
                    "coordinate_space": ["normalised", "normalised"],
                }
            ),
            pd.DataFrame({"time_s": [0.0, 0.1]}),
            pd.DataFrame(),
            QualityThresholds(expected_marker_events=None),
        )
        assert "unreadable_session_metadata" in quality["quality_flags"]


def test_supplied_client_dataset_is_discoverable_and_read_only() -> None:
    project_root = Path(__file__).resolve().parents[2]
    data_root = project_root / "ET acc testing data"
    if not data_root.exists():
        pytest.skip("Client dataset is not present in this checkout")
    records = discover_sessions(data_root)
    assert len(records) == 40
    version_mismatch_record = next(item for item in records if item.session_id == "2025_04_12/001")
    assert version_mismatch_record.recording_start_time == pytest.approx(1_744_413_207.420712)
    record = next(item for item in records if item.gaze_file)
    source = Path(record.session_path) / record.gaze_file
    before = source.read_bytes()
    with tempfile.TemporaryDirectory() as folder:
        gaze, _, _ = standardise_session(record, Path(folder))
        assert not gaze.empty
    assert source.read_bytes() == before


def test_live_collection_requires_explicit_calibration_confirmation() -> None:
    with pytest.raises(ValueError, match="calibration confirmation"):
        CollectionConfig(
            legacy_code_root=Path("code"), output_root=Path("out"), subject_id="P01",
            device_id="GP3HD", test_id="Accuracy", dry_run=False,
        )


def test_device_calibration_result_requires_status_and_error_unit() -> None:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "calibration.json"
        path.write_text(
            json.dumps({"status": "passed", "average_error": 0.42, "valid_points": 9}),
            encoding="utf-8",
        )
        config = CollectionConfig(
            legacy_code_root=Path("code"), output_root=Path("out"), subject_id="P01",
            device_id="GP3HD", test_id="Accuracy", dry_run=False,
            calibration_result_json=path,
        )
        with pytest.raises(ValueError, match="identify its unit"):
            _resolve_calibration(config)

        path.write_text(
            json.dumps(
                {
                    "status": "passed", "average_error": 0.42, "valid_points": 9,
                    "high_quality_samples": 180, "confidence_threshold": 0.8,
                    "unit": "degrees", "method": "device nine-point", "source": "fixture",
                }
            ),
            encoding="utf-8",
        )
        result = _resolve_calibration(config)
        assert result is not None
        assert result.status == "device_reported_pass"
        assert result.average_error == pytest.approx(0.42)
        assert result.high_quality_samples == 180
        assert result.confidence_threshold == pytest.approx(0.8)
        assert result.unit == "degrees"


def test_research_target_protocol_validates_capacity_and_records_audit_fields() -> None:
    with pytest.raises(ValueError, match="duration_s is too short"):
        CollectionConfig(
            legacy_code_root=Path("code"), output_root=Path("out"), subject_id="P01",
            device_id="GP3HD", test_id="nine_point_accuracy_v1", duration_s=30,
            target_presentation_s=4.2,
        )
    config = CollectionConfig(
        legacy_code_root=Path("code"), output_root=Path("out"), subject_id="P01",
        device_id="GP3HD", test_id="nine_point_accuracy_v1", duration_s=114,
        target_presentation_s=4.2, target_settle_time_s=0.6,
        minimum_post_settle_valid_samples=100, visit_label="baseline",
        display_model="fixture monitor", display_refresh_hz=60,
        ambient_illuminance_lux=300, head_support="chin rest",
    )
    markers = _target_timeline(config)
    assert len(markers) == 27
    assert markers[0]["target_settle_time_s"] == pytest.approx(0.6)
    assert markers[0]["nominal_post_settle_samples"] == pytest.approx(216)
    assert all(marker["minimum_post_settle_valid_samples"] == 100 for marker in markers)


def test_unknown_calibration_unit_is_not_compared_to_degree_threshold() -> None:
    record = SessionRecord(
        session_id="fixture", date="2026_01_01", run_id="000", session_path=".",
        subject_id="P01", device_id="GP3", test_id="Accuracy", trial_number=1,
        test_condition="standard", recording_start_time=1.0,
        calibration_avg_error=28.64, calibration_error_unit="", has_calibration=True,
    )
    gaze = pd.DataFrame(
        {
            "time_s": [0.0, 0.01], "gaze_x": [0.5, 0.5], "gaze_y": [0.5, 0.5],
            "valid": [1, 1], "coordinate_space": ["normalised", "normalised"],
        }
    )
    video = pd.DataFrame({"time_s": [0.0, 0.01]})
    result = evaluate_quality(
        record, gaze, video, pd.DataFrame(), QualityThresholds(expected_marker_events=None)
    )
    assert "unknown_calibration_error_unit" in result["quality_flags"]
    assert "high_calibration_error" not in result["quality_flags"]


def test_target_settling_window_excludes_early_samples_and_records_evidence() -> None:
    record = SessionRecord(
        session_id="fixture", date="2026_01_01", run_id="000", session_path=".",
        subject_id="P01", device_id="GP3", test_id="Accuracy", trial_number=1,
        test_condition="standard", recording_start_time=1.0,
    )
    times = [index / 10 for index in range(11)]
    gaze = pd.DataFrame(
        {
            "time_s": times,
            "gaze_x": [0.8 if value < 0.6 else 0.5 for value in times],
            "gaze_y": [0.5] * len(times),
            "valid": [1] * len(times),
        }
    )
    markers = pd.DataFrame(
        {"marker_start_s": [0.0], "marker_end_s": [1.0], "marker_id": ["centre"],
         "target_x": [0.5], "target_y": [0.5]}
    )
    result = target_level_metrics(record, gaze, markers, settle_time_s=0.6)
    assert len(result) == 1
    assert result.loc[0, "analysis_start_s"] == pytest.approx(0.6)
    assert result.loc[0, "settle_excluded_valid_samples"] == 6
    assert result.loc[0, "valid_samples"] == 5
    assert result.loc[0, "centroid_error_normalised"] == pytest.approx(0.0)


def test_synthetic_example_exercises_longitudinal_and_angular_pipeline() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        data_root = generate_longitudinal_example(root / "example")
        delay_evidence = Path(__file__).resolve().parents[1] / "references" / "client_delay_comparison"
        result = run_pipeline(data_root, root / "output", client_delay_evidence=delay_evidence)
        assert result.session_count == 3
        assert result.failed_sessions == 0
        repeatability = pd.read_csv(root / "output" / "repeatability_summary.csv")
        metrics = pd.read_csv(root / "output" / "benchmark_metrics.csv")
        target_metrics = pd.read_csv(root / "output" / "target_metrics.csv")
        target_visits = pd.read_csv(root / "output" / "target_visit_summary.csv")
        inventory = pd.read_csv(root / "output" / "session_inventory.csv")
        summary = json.loads((root / "output" / "summary.json").read_text(encoding="utf-8"))
        manifest = json.loads((root / "output" / "run_manifest.json").read_text(encoding="utf-8"))
        provenance = json.loads((root / "output" / "input_provenance.json").read_text(encoding="utf-8"))
        assert len(repeatability) == 1
        assert repeatability.loc[0, "subject_id"] == "SYNTHETIC_P01"
        assert metrics["marker_accuracy_rmse"].notna().all()
        assert metrics["marker_omae_deg"].notna().all()
        assert len(target_metrics) == 81
        assert len(target_visits) == 27
        assert target_metrics["target_settle_time_s"].eq(0.6).all()
        assert target_metrics["valid_samples"].gt(100).all()
        assert target_visits["paper_qc_status"].eq("included").all()
        assert target_visits["paper_qc_excluded_samples"].eq(0).all()
        assert inventory["session_path"].eq(inventory["session_id"]).all()
        assert manifest["data_root"] == "openet2://input"
        assert manifest["output_root"] == "openet2://output"
        assert manifest["path_policy"] == "portable_logical_roots"
        assert manifest["openet2_version"] == "1.6.0"
        assert manifest["input_provenance_file"] == "input_provenance.json"
        assert manifest["input_content_digest_sha256"] == provenance["content_digest_sha256"]
        assert manifest["runtime_environment"]["python_version"]
        assert manifest["runtime_environment"]["packages"]["pandas"] != "not-installed"
        assert summary["runtime_environment"] == manifest["runtime_environment"]
        assert provenance["file_count"] > 0
        assert provenance["hash_error_count"] == 0
        assert all(":" not in item["path"] and not item["path"].startswith("/") for item in provenance["files"])
        assert summary["paper_aligned_figures_available"] is True
        assert summary["target_settle_time_s"] == pytest.approx(0.6)
        assert len(pd.read_csv(root / "output" / "paper_reference_criteria.csv")) >= 8
        figures = {path.name for path in (root / "output" / "figures").glob("*.png")}
        assert {
            "02_sampling_rate_by_session.png",
            "03_valid_rate_by_session.png",
            "05_long_term_comparison.png",
            "09_target_error_confidence_ellipses.png",
            "10_omae_vs_target_eccentricity.png",
            "11_target_layout_and_coverage.png",
        }.issubset(figures)
        assert {
            "01_sessions_by_date.png",
            "04_quality_flags_summary.png",
            "06_marker_precision_by_session.png",
            "07_device_comparison.png",
            "08_calibration_quality.png",
            "12_target_error_unfiltered_diagnostic.png",
        }.isdisjoint(figures)
        report_html = (root / "output" / "report.html").read_text(encoding="utf-8")
        assert "12_target_error_unfiltered_diagnostic.png" not in report_html
        assert "04_quality_flags_summary.png" not in report_html
        assert "alt='02_sampling_rate_by_session.png'" not in report_html
        assert "Valid gaze samples by session (%)" in report_html
        display_sessions = pd.read_csv(root / "output" / "report_display_session_metrics.csv")
        display_targets = pd.read_csv(root / "output" / "report_display_target_visits.csv")
        assert display_sessions.loc[0, "valid_gaze_samples_pct"] == pytest.approx(
            pd.read_csv(root / "output" / "combined_results.csv").loc[0, "valid_rate"] * 100
        )
        assert display_targets.loc[0, "target_x_pct_display_width"] == pytest.approx(
            target_visits.loc[0, "target_x"] * 100
        )
        assert {
            "paper_qc_status",
            "paper_plot_status",
            "paper_qc_omae_relative_coordinate_pct",
            "paper_qc_omae_deg",
        }.issubset(display_targets.columns)
        for date in ("2026_01_01", "2026_01_08", "2026_01_15"):
            alignment = json.loads(
                (root / "output" / "sessions" / date / "000" / "time_alignment.json").read_text(
                    encoding="utf-8"
                )
            )
            assert alignment["standard_time_basis"] == "relative_seconds"
        assert (root / "output" / "report_display_units.json").exists()
        assert "Evidence overview" in report_html
        assert "Evidence status" in report_html
        assert "Software-validation example" in report_html
        assert "Input file fingerprint" in report_html
        assert "Target X (% of display width)" in report_html
        assert "Auditable data downloads" in report_html
        assert "Client-requested delay comparison" in report_html
        assert "50 ms" in report_html
        assert "2.8906&deg;" in report_html
        assert "0.5912&deg;" in report_html
        assert "delay_accuracy.png" in report_html
        assert "does not alter the OpenET2 target settling window" in report_html
        assert "assumed-FOV degree scores" in report_html
        assert "rebuild_figures.py" in report_html
        assert "Matched long-term comparison" in report_html
        assert "QC-retained target summary by date" in report_html
        delay_rule = json.loads(
            (delay_evidence / "data" / "selected_delay_client_rule.json").read_text(encoding="utf-8")
        )
        assert delay_rule["assumed_field_of_view_deg"] == {"x": 60.0, "y": 33.75}
        assert delay_rule["physical_display_geometry_available"] is False
