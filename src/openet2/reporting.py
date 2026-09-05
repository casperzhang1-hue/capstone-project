"""Create review figures and the HTML evidence report."""

from __future__ import annotations

import json
import os
import shutil
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse, Rectangle


ALL_FIGURES = (
    "01_sessions_by_date.png",
    "02_sampling_rate_by_session.png",
    "03_valid_rate_by_session.png",
    "04_quality_flags_summary.png",
    "05_long_term_comparison.png",
    "06_marker_precision_by_session.png",
    "07_device_comparison.png",
    "08_calibration_quality.png",
    "09_target_error_confidence_ellipses.png",
    "10_omae_vs_target_eccentricity.png",
    "11_target_layout_and_coverage.png",
    "12_target_error_unfiltered_diagnostic.png",
)

FIGURES = (
    "02_sampling_rate_by_session.png",
    "03_valid_rate_by_session.png",
    "04_quality_flags_summary.png",
    "05_long_term_comparison.png",
    "09_target_error_confidence_ellipses.png",
    "10_omae_vs_target_eccentricity.png",
    "11_target_layout_and_coverage.png",
)

FIGURE_CAPTIONS = {
    "02_sampling_rate_by_session.png": "Effective sampling rate by session (Hz); dashed line is the 60 Hz reference.",
    "03_valid_rate_by_session.png": "Valid gaze samples by session (%); dashed line is the 80% warning threshold.",
    "04_quality_flags_summary.png": "Automated quality flags, shown as the number of affected sessions.",
    "05_long_term_comparison.png": "Date-level median sampling rate (Hz) and valid gaze samples (%) by protocol; matched repeatability is reported separately.",
    "09_target_error_confidence_ellipses.png": "QC-filtered target centroids; axes use visual degrees when display geometry is recorded, otherwise percentages of display width and height.",
    "10_omae_vs_target_eccentricity.png": "QC-filtered target error versus eccentricity; units are visual degrees when available, otherwise relative screen-coordinate distance (%; 100% = 1.0 normalised coordinate unit).",
    "11_target_layout_and_coverage.png": "QC-filtered target layout in percentages of display width and height; bubble size represents retained samples and colour represents target error.",
}


def _style() -> None:
    sns.set_theme(style="whitegrid")
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 180,
            "axes.titlesize": 13,
            "axes.labelsize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
        }
    )


def _save(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def _empty_plot(title: str, message: str) -> None:
    plt.title(title)
    plt.text(0.5, 0.5, message, ha="center", va="center", fontsize=12, wrap=True)
    plt.axis("off")


def make_session_review(
    session_id: str,
    gaze: pd.DataFrame,
    markers: pd.DataFrame,
    output_path: Path,
) -> Path:
    """Create one auditable four-panel review for an individual recording."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _style()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(f"Session review: {session_id}", fontsize=15)
    if gaze.empty or "time_s" not in gaze:
        for axis in axes.flat:
            axis.text(0.5, 0.5, "No gaze data", ha="center", va="center")
            axis.axis("off")
    else:
        time_values = pd.to_numeric(gaze["time_s"], errors="coerce")
        x = pd.to_numeric(gaze.get("gaze_x"), errors="coerce")
        y = pd.to_numeric(gaze.get("gaze_y"), errors="coerce")
        valid = pd.to_numeric(gaze.get("valid", pd.Series(0, index=gaze.index)), errors="coerce").fillna(0) > 0

        axes[0, 0].plot(time_values, x, linewidth=0.7, label="gaze x", color="#2878B5")
        axes[0, 0].plot(time_values, y, linewidth=0.7, label="gaze y", color="#F28E2B")
        axes[0, 0].set(title="Gaze trace", xlabel="Time (s)", ylabel="Screen coordinate (fraction of display dimension)")
        axes[0, 0].legend(loc="best")

        axes[0, 1].fill_between(time_values, 0, valid.astype(int), step="mid", color="#59A14F", alpha=0.75)
        axes[0, 1].set(title="Missing / invalid data timeline", xlabel="Time (s)", ylabel="Sample validity (0 invalid, 1 valid)")
        axes[0, 1].set_ylim(-0.05, 1.05)

        scatter = axes[1, 0].scatter(x[valid], y[valid], c=time_values[valid], s=4, alpha=0.35, cmap="viridis")
        if not markers.empty and {"target_x", "target_y"}.issubset(markers.columns):
            target_x = pd.to_numeric(markers["target_x"], errors="coerce")
            target_y = pd.to_numeric(markers["target_y"], errors="coerce")
            target_mask = target_x.notna() & target_y.notna()
            if target_mask.any():
                axes[1, 0].scatter(
                    target_x[target_mask], target_y[target_mask], marker="+", s=90,
                    linewidth=1.5, color="#C44E52", label="targets",
                )
                axes[1, 0].legend(loc="best")
        axes[1, 0].set(title="Gaze distribution and targets", xlabel="Horizontal screen coordinate (fraction of width)", ylabel="Vertical screen coordinate (fraction of height; origin at top)")
        axes[1, 0].invert_yaxis()
        fig.colorbar(scatter, ax=axes[1, 0], label="Time (s)")

        intervals_ms = time_values.diff() * 1000
        axes[1, 1].plot(time_values, intervals_ms, linewidth=0.65, color="#7B5EA7")
        median_interval = intervals_ms[intervals_ms > 0].median()
        if np.isfinite(median_interval):
            axes[1, 1].axhline(median_interval, linestyle="--", color="#C44E52", label="median")
            axes[1, 1].legend(loc="best")
            finite_intervals = intervals_ms[np.isfinite(intervals_ms)]
            if not finite_intervals.empty and float(finite_intervals.max() - finite_intervals.min()) < max(
                abs(float(median_interval)) * 0.01, 1e-6
            ):
                padding = max(abs(float(median_interval)) * 0.05, 1e-3)
                axes[1, 1].set_ylim(float(median_interval) - padding, float(median_interval) + padding)
        axes[1, 1].ticklabel_format(axis="y", style="plain", useOffset=False)
        axes[1, 1].set(title="Sampling interval stability", xlabel="Time (s)", ylabel="Interval (ms)")
    plt.tight_layout(rect=(0, 0, 1, 0.96))
    plt.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path


def _paper_plot_data(target_visits: pd.DataFrame | None) -> tuple[pd.DataFrame, str]:
    """Prepare QC metrics in degrees when available, otherwise in normalised units."""

    if target_visits is None or target_visits.empty:
        return pd.DataFrame(), ""
    identity = {"session_id", "date", "target_key", "target_label"}
    if not identity.issubset(target_visits.columns):
        return pd.DataFrame(), ""

    table = target_visits.copy()
    degree_structure = [
        "visit_index", "target_x_deg", "target_y_deg", "target_eccentricity_deg",
    ]
    degree_metrics = [
        "paper_qc_gaze_direction_x_deg", "paper_qc_gaze_direction_y_deg",
        "paper_qc_omae_deg",
    ]
    if set(degree_structure + degree_metrics).issubset(table.columns):
        degree = table.copy()
        for column in degree_structure + degree_metrics:
            degree[column] = pd.to_numeric(degree[column], errors="coerce")
        degree = degree.dropna(subset=degree_structure)
        if not degree.empty and degree[degree_metrics].notna().any().any():
            degree["plot_target_x"] = degree["target_x_deg"]
            degree["plot_target_y"] = degree["target_y_deg"]
            degree["plot_gaze_x"] = degree["paper_qc_gaze_direction_x_deg"]
            degree["plot_gaze_y"] = degree["paper_qc_gaze_direction_y_deg"]
            degree["plot_omae"] = degree["paper_qc_omae_deg"]
            degree["plot_eccentricity"] = degree["target_eccentricity_deg"]
            degree["plot_group"] = "Visit " + degree["visit_index"].astype(int).astype(str)
            return degree, "degrees"

    normalised_structure = [
        "target_x_centered", "target_y_centered", "target_eccentricity_normalised",
    ]
    normalised_metrics = [
        "paper_qc_gaze_direction_x_normalised", "paper_qc_gaze_direction_y_normalised",
        "paper_qc_omae_normalised",
    ]
    if not set(normalised_structure + normalised_metrics).issubset(table.columns):
        return pd.DataFrame(), ""
    normalised = table.copy()
    if "coordinate_space" in normalised:
        normalised = normalised[normalised["coordinate_space"].astype(str).eq("normalised")].copy()
    for column in normalised_structure + normalised_metrics:
        normalised[column] = pd.to_numeric(normalised[column], errors="coerce")
    normalised = normalised.dropna(subset=normalised_structure)
    if normalised.empty:
        return pd.DataFrame(), ""
    normalised["plot_target_x"] = normalised["target_x_centered"]
    normalised["plot_target_y"] = normalised["target_y_centered"]
    normalised["plot_gaze_x"] = normalised["paper_qc_gaze_direction_x_normalised"]
    normalised["plot_gaze_y"] = normalised["paper_qc_gaze_direction_y_normalised"]
    normalised["plot_omae"] = normalised["paper_qc_omae_normalised"]
    normalised["plot_eccentricity"] = normalised["target_eccentricity_normalised"]
    normalised["plot_group"] = normalised["date"].astype(str)
    return normalised, "normalised"

def _paper_unavailable_message(table: pd.DataFrame, mode: str) -> str:
    if table.empty:
        return "Unavailable: recovered target positions and valid target-period gaze are required."
    if mode == "degrees" and table["visit_index"].nunique() < 2:
        return "Unavailable: at least two matched visits for the same participant/protocol are required."
    if table["plot_eccentricity"].nunique() < 2:
        return "Unavailable: at least two target eccentricities are required."
    return "Unavailable: insufficient target-level observations."


def _paper_qc_plot_data(table: pd.DataFrame, mode: str) -> tuple[pd.DataFrame, dict[str, int]]:
    """Select auditable, screen-valid observations for the paper-style view."""

    audit = {
        "total_observations": int(len(table)),
        "sample_qc_observations": 0,
        "included_observations": 0,
        "excluded_observations": int(len(table)),
        "target_mismatches": 0,
        "robust_centroid_outliers": 0,
        "excluded_samples": 0,
    }
    if table.empty:
        return table.copy(), audit
    required = {
        "paper_qc_status", "paper_plot_status", "paper_qc_excluded_samples",
        "paper_qc_gaze_direction_x_normalised", "paper_qc_gaze_direction_y_normalised",
        "paper_qc_gaze_direction_x_deg", "paper_qc_gaze_direction_y_deg",
        "paper_qc_omae_normalised", "paper_qc_omae_deg",
    }
    if not required.issubset(table.columns):
        return table.iloc[0:0].copy(), audit
    sample_qc = table["paper_qc_status"].astype(str).eq("included")
    plot_status = table["paper_plot_status"].astype(str)
    selected = table[plot_status.eq("included")].copy()
    if mode == "degrees":
        x_column = "paper_qc_gaze_direction_x_deg"
        y_column = "paper_qc_gaze_direction_y_deg"
        omae_column = "paper_qc_omae_deg"
    else:
        x_column = "paper_qc_gaze_direction_x_normalised"
        y_column = "paper_qc_gaze_direction_y_normalised"
        omae_column = "paper_qc_omae_normalised"
    selected["plot_gaze_x"] = pd.to_numeric(selected[x_column], errors="coerce")
    selected["plot_gaze_y"] = pd.to_numeric(selected[y_column], errors="coerce")
    selected["plot_omae"] = pd.to_numeric(selected[omae_column], errors="coerce")
    selected = selected.dropna(subset=["plot_gaze_x", "plot_gaze_y", "plot_omae"])
    audit["sample_qc_observations"] = int(sample_qc.sum())
    audit["included_observations"] = int(len(selected))
    audit["excluded_observations"] = int(len(table) - len(selected))
    audit["target_mismatches"] = int(plot_status.eq("target_mismatch").sum())
    audit["robust_centroid_outliers"] = int(plot_status.eq("robust_centroid_outlier").sum())
    audit["excluded_samples"] = int(
        pd.to_numeric(table["paper_qc_excluded_samples"], errors="coerce").fillna(0).sum()
    )
    return selected, audit


def _observation_ellipse_parameters(
    points: np.ndarray,
) -> tuple[np.ndarray, float, float, float] | None:
    """Return a chi-square 95% ellipse for the bivariate observation distribution."""

    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
        return None
    covariance = np.cov(points, rowvar=False)
    if covariance.shape != (2, 2) or not np.isfinite(covariance).all():
        return None
    values, vectors = np.linalg.eigh(covariance)
    values = np.maximum(values, 0)
    if float(values.max()) <= 0:
        return None
    order = values.argsort()[::-1]
    values = values[order]
    vectors = vectors[:, order]
    angle = float(np.degrees(np.arctan2(vectors[1, 0], vectors[0, 0])))
    width, height = 2 * np.sqrt(values * 5.991)
    return points.mean(axis=0), float(width), float(height), angle


def make_figures(
    combined: pd.DataFrame,
    long_term: pd.DataFrame,
    output_dir: Path,
    target_visits: pd.DataFrame | None = None,
) -> list[Path]:
    """Create the selected project-level figures."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in ALL_FIGURES:
        (output_dir / filename).unlink(missing_ok=True)
    _style()
    created: list[Path] = []

    path = output_dir / ALL_FIGURES[0]
    plt.figure(figsize=(7, 4))
    if combined.empty:
        _empty_plot("Sessions by collection date", "No sessions were discovered")
    else:
        by_date = combined.groupby("date", as_index=False)["session_id"].count()
        sns.barplot(data=by_date, x="date", y="session_id", color="#2878B5")
        plt.title("Sessions by collection date")
        plt.xlabel("Collection date")
        plt.ylabel("Session count")
    _save(path)
    created.append(path)

    ordered = combined.sort_values(["date", "run_id"]).copy() if not combined.empty else combined.copy()
    if not ordered.empty:
        ordered["session_short"] = ordered["date"].astype(str).str[-5:] + "/" + ordered["run_id"].astype(str)

    path = output_dir / ALL_FIGURES[1]
    plt.figure(figsize=(10, 4.8))
    if ordered.empty or not pd.to_numeric(ordered["effective_sampling_hz"], errors="coerce").notna().any():
        _empty_plot("Effective sampling rate", "No sampling-rate data are available")
    else:
        sns.scatterplot(data=ordered, x="session_short", y="effective_sampling_hz", hue="date", s=55)
        plt.axhline(60, color="#C44E52", linewidth=1.2, linestyle="--", label="60 Hz reference")
        plt.title("Effective sampling rate by session")
        plt.xlabel("Session ID (collection date / run)")
        plt.ylabel("Effective sampling rate (Hz)")
        plt.xticks(rotation=70, ha="right")
    _save(path)
    created.append(path)

    path = output_dir / ALL_FIGURES[2]
    plt.figure(figsize=(10, 4.8))
    if ordered.empty or not pd.to_numeric(ordered["valid_rate"], errors="coerce").notna().any():
        _empty_plot("Valid gaze rate", "No gaze-validity data are available")
    else:
        valid_rate_percent = ordered.assign(valid_rate_percent=ordered["valid_rate"] * 100)
        sns.lineplot(data=valid_rate_percent, x="session_short", y="valid_rate_percent", hue="date", marker="o")
        plt.axhline(80, color="#C44E52", linewidth=1.2, linestyle="--", label="80% warning threshold")
        plt.ylim(0, 105)
        plt.title("Valid gaze sample rate by session")
        plt.xlabel("Session ID (collection date / run)")
        plt.ylabel("Valid gaze samples (%)")
        plt.xticks(rotation=70, ha="right")
    _save(path)
    created.append(path)

    flag_counts = pd.DataFrame()
    if not combined.empty and "quality_flags" in combined:
        flag_counts = (
            combined.assign(flag=combined["quality_flags"].fillna("ok").str.split(";"))
            .explode("flag")
            .query("flag != 'ok'")
            .groupby("flag", as_index=False)["session_id"]
            .count()
            .rename(columns={"session_id": "count"})
            .sort_values("count", ascending=False)
        )
    if not flag_counts.empty:
        path = output_dir / ALL_FIGURES[3]
        plt.figure(figsize=(8.5, 4.8))
        sns.barplot(data=flag_counts, y="flag", x="count", color="#F28E2B")
        plt.title("Automated quality flags across sessions")
        plt.xlabel("Affected sessions (count)")
        plt.ylabel("Quality flag category")
        _save(path)
        created.append(path)

    path = output_dir / ALL_FIGURES[4]
    fig, (ax_rate, ax_valid) = plt.subplots(1, 2, figsize=(11, 4.6), sharex=True)
    if long_term.empty:
        ax_rate.text(0.5, 0.5, "At least one dated session is required", ha="center", va="center")
        ax_rate.axis("off")
        ax_valid.axis("off")
    else:
        plot_data = long_term.sort_values("date")
        group_columns = ["device_id", "test_id"] + (["test_condition"] if "test_condition" in plot_data else [])
        groups = list(plot_data.groupby(group_columns, dropna=False))
        palette = sns.color_palette("deep", n_colors=max(1, len(groups)))
        for color, (group_key, group) in zip(palette, groups):
            values = group_key if isinstance(group_key, tuple) else (group_key,)
            label = " / ".join(str(value) for value in values)
            group = group.sort_values("date")
            ax_rate.plot(group["date"], group["median_sampling_hz"], marker="o", color=color, label=label)
            ax_valid.plot(group["date"], group["median_valid_rate"] * 100, marker="s", color=color, label=label)
        ax_rate.set_title("Sampling rate over time")
        ax_valid.set_title("Valid gaze rate over time")
        ax_rate.set_xlabel("Collection date")
        ax_rate.set_ylabel("Median effective sampling rate (Hz)")
        ax_valid.set_xlabel("Collection date")
        ax_valid.set_ylabel("Median valid gaze samples (%)")
        ax_valid.set_ylim(0, 105)
        ax_valid.axhline(80, color="#C44E52", linewidth=1.1, linestyle="--", label="80% threshold")
        ax_valid.legend(title="Device / test", loc="best", fontsize=7)
        fig.suptitle("Date-level benchmark comparison by protocol", fontsize=14)
    _save(path)
    created.append(path)

    path = output_dir / ALL_FIGURES[5]
    plt.figure(figsize=(10, 4.8))
    precision = (
        pd.to_numeric(ordered.get("marker_precision_rms", pd.Series(dtype=float)), errors="coerce")
        if not ordered.empty
        else pd.Series(dtype=float)
    )
    if ordered.empty or not precision.notna().any():
        _empty_plot(
            "Marker-period gaze precision",
            "No marker intervals contained enough valid gaze samples",
        )
    else:
        precision_data = ordered.loc[precision.notna()].copy()
        positive = precision_data["marker_precision_rms"] > 0
        positive_min = float(precision_data.loc[positive, "marker_precision_rms"].min()) if positive.any() else 1e-6
        display_floor = positive_min / 2
        precision_data["precision_plot"] = precision_data["marker_precision_rms"].clip(lower=display_floor)
        sns.scatterplot(
            data=precision_data,
            x="session_short",
            y="precision_plot",
            hue="date",
            s=55,
        )
        plt.title("Median marker-period gaze precision by session")
        plt.xlabel("Session")
        plt.ylabel("Radial RMS (coordinate units; lower is better)")
        plt.yscale("log")
        if (~positive).any():
            plt.figtext(
                0.01,
                0.01,
                f"Zero RMS values are displayed at the plotting floor ({display_floor:.2g}); CSV output retains zero.",
                fontsize=8,
                color="#61758a",
            )
        plt.xticks(rotation=70, ha="right")
    _save(path)
    created.append(path)

    path = output_dir / ALL_FIGURES[6]
    plt.figure(figsize=(9, 4.8))
    if ordered.empty or "device_id" not in ordered or not pd.to_numeric(ordered.get("valid_rate"), errors="coerce").notna().any():
        _empty_plot("Device comparison", "No device comparison data are available")
    else:
        comparison = ordered.copy()
        comparison["device_id"] = comparison["device_id"].fillna("unknown").replace("", "unknown")
        device_order = sorted(comparison["device_id"].unique())
        sns.stripplot(
            data=comparison, x="device_id", y="valid_rate", order=device_order,
            color="#2878B5", alpha=0.50, size=5, jitter=0.18,
        )
        medians = comparison.groupby("device_id")["valid_rate"].median().reindex(device_order)
        plt.scatter(range(len(device_order)), medians, marker="_", s=700, linewidth=3, color="#C44E52", label="median")
        plt.legend(loc="best")
        plt.axhline(0.8, color="#C44E52", linewidth=1.1, linestyle="--")
        plt.ylim(0, 1.05)
        plt.title("Valid gaze rate by device")
        plt.xlabel("Device")
        plt.ylabel("Valid sample rate")
    _save(path)
    created.append(path)

    path = output_dir / ALL_FIGURES[7]
    fig, (ax_error, ax_points) = plt.subplots(1, 2, figsize=(10, 4.5))
    calibration_error = pd.to_numeric(ordered.get("calibration_avg_error", pd.Series(dtype=float)), errors="coerce")
    calibration_points = pd.to_numeric(ordered.get("calibration_valid_points", pd.Series(dtype=float)), errors="coerce")
    if ordered.empty or (not calibration_error.notna().any() and not calibration_points.notna().any()):
        ax_error.text(0.5, 0.5, "No calibration metadata", ha="center", va="center")
        ax_error.axis("off")
        ax_points.axis("off")
    else:
        if calibration_error.notna().any():
            ax_error.scatter(ordered.loc[calibration_error.notna(), "session_short"], calibration_error.dropna(), s=25)
            ax_error.set(title="Calibration error", xlabel="Session", ylabel="Device-reported error")
            ax_error.tick_params(axis="x", rotation=70)
        else:
            ax_error.text(0.5, 0.5, "No calibration error values", ha="center", va="center")
            ax_error.axis("off")
        if calibration_points.notna().any():
            ax_points.bar(ordered.loc[calibration_points.notna(), "session_short"], calibration_points.dropna())
            ax_points.set(title="Valid calibration points", xlabel="Session", ylabel="Points")
            ax_points.tick_params(axis="x", rotation=70)
        else:
            ax_points.text(0.5, 0.5, "No valid-point values", ha="center", va="center")
            ax_points.axis("off")
    _save(path)
    created.append(path)

    paper, paper_mode = _paper_plot_data(target_visits)
    paper_available = (
        not paper.empty
        and paper["plot_eccentricity"].nunique() >= 2
        and (paper_mode == "normalised" or paper["visit_index"].nunique() >= 2)
    )
    paper_qc, paper_qc_audit = _paper_qc_plot_data(paper, paper_mode)
    paper_qc_available = (
        not paper_qc.empty
        and paper_qc["plot_eccentricity"].nunique() >= 2
        and (paper_mode == "normalised" or paper_qc["visit_index"].nunique() >= 2)
    )
    paper_display = paper.copy()
    paper_qc_display = paper_qc.copy()
    if paper_mode == "normalised":
        for table in (paper_display, paper_qc_display):
            for column in (
                "plot_target_x", "plot_target_y", "plot_gaze_x", "plot_gaze_y",
                "plot_omae", "plot_eccentricity",
            ):
                if column in table:
                    table[column] = pd.to_numeric(table[column], errors="coerce") * 100.0

    path = output_dir / ALL_FIGURES[8]
    fig, ax = plt.subplots(figsize=(10.5, 7.2))
    if not paper_qc_available:
        ax.text(
            0.5, 0.52, _paper_unavailable_message(paper_qc, paper_mode), ha="center", va="center",
            fontsize=11, wrap=True, transform=ax.transAxes,
        )
        ax.text(
            0.5, 0.40, "No QC-ineligible values were imputed.", ha="center", va="center",
            fontsize=9, color="#61758a", transform=ax.transAxes,
        )
        ax.set_title("QC-filtered target gaze locations")
        ax.axis("off")
    else:
        targets = (
            paper_qc_display[["target_key", "target_label", "plot_target_x", "plot_target_y"]]
            .drop_duplicates("target_key")
            .sort_values(["plot_target_y", "plot_target_x"], ascending=[False, True])
        )
        palette = sns.color_palette("husl", n_colors=max(1, len(targets)))
        target_colors = dict(zip(targets["target_key"], palette))
        recording_styles = [
            ("o", False),
            ("*", True),
            ("o", True),
            ("s", True),
            ("D", True),
            ("^", True),
            ("v", True),
        ]
        groups = (
            [f"Visit {value}" for value in sorted(int(value) for value in paper_qc_display["visit_index"].dropna().unique())]
            if paper_mode == "degrees"
            else sorted(paper_qc_display["plot_group"].dropna().astype(str).unique())
        )
        ellipse_count = 0
        normalised_display_limit = 55.0
        for _, target in targets.iterrows():
            key = target["target_key"]
            color = target_colors[key]
            group = paper_qc_display[paper_qc_display["target_key"] == key]
            ax.scatter(
                [target["plot_target_x"]], [target["plot_target_y"]], marker="x", s=85,
                linewidth=2, color="#168b36", zorder=5,
            )
            for group_index, group_label in enumerate(groups):
                observations = group[group["plot_group"] == group_label]
                if observations.empty:
                    continue
                marker, filled = recording_styles[group_index % len(recording_styles)]
                ax.scatter(
                    observations["plot_gaze_x"], observations["plot_gaze_y"],
                    marker=marker, s=48,
                    facecolor=color if filled else "none", edgecolor=color,
                    linewidth=1.0, alpha=0.92, zorder=3,
                )
            points = group[["plot_gaze_x", "plot_gaze_y"]].to_numpy(dtype=float)
            ellipse_parameters = _observation_ellipse_parameters(points)
            if ellipse_parameters is not None:
                centre, width, height, angle = ellipse_parameters
                ax.scatter(
                    [centre[0]], [centre[1]], marker="+", s=90,
                    linewidth=1.8, color="#d62728", zorder=6,
                )
                ellipse = Ellipse(
                    xy=centre, width=width, height=height, angle=angle,
                    fill=False, edgecolor="#d62728", linestyle="--", linewidth=1.5, alpha=0.95,
                )
                ax.add_patch(ellipse)
                ellipse_count += 1
        group_handles = [
            Line2D(
                [0], [0],
                marker=recording_styles[index % len(recording_styles)][0],
                color="none",
                markerfacecolor=(
                    "black" if recording_styles[index % len(recording_styles)][1] else "none"
                ),
                markeredgecolor="black", markeredgewidth=1.1, markersize=8,
                label=(
                    group_label
                    if paper_mode == "degrees"
                    else f"{group_label.replace('_', '-')} recording"
                ),
            )
            for index, group_label in enumerate(groups)
        ]
        reference_handles = [
            Line2D(
                [0], [0], marker="x", color="#168b36", linestyle="none",
                markeredgewidth=1.8, markersize=8, label="Target positions averaged",
            ),
            Line2D(
                [0], [0], marker="+", color="#d62728", linestyle="none",
                markeredgewidth=1.6, markersize=9, label="Center of 95% observation ellipse",
            ),
            Line2D(
                [0], [0], color="#d62728", linestyle="--", linewidth=1.5,
                label="95% observation interval",
            ),
        ]
        ax.legend(
            handles=group_handles + reference_handles,
            loc="center left", bbox_to_anchor=(0.015, 0.52),
            fontsize=9, frameon=False, handlelength=1.5, handletextpad=0.7,
        )
        ax.axhline(0, color="#9aa8b4", linewidth=0.8)
        ax.axvline(0, color="#9aa8b4", linewidth=0.8)
        if paper_mode == "degrees":
            ax.set_aspect("equal", adjustable="datalim")
            ax.set_title("Gaze detection mean of all trials per target")
            ax.set_xlabel("Horizontal gaze direction relative to display centre (deg)")
            ax.set_ylabel("Vertical gaze direction relative to display centre (deg)")
            footer = (
                f"{paper_qc_audit['included_observations']}/{paper_qc_audit['total_observations']} "
                f"participant/visit/target observations plotted; {ellipse_count} 95% observation ellipses. "
                f"Target mismatches: {paper_qc_audit['target_mismatches']}; robust centroid outliers: "
                f"{paper_qc_audit['robust_centroid_outliers']}. "
                f"Excluded source samples: {paper_qc_audit['excluded_samples']}."
            )
        else:
            ax.set_xlim(-normalised_display_limit, normalised_display_limit)
            ax.set_ylim(-normalised_display_limit, normalised_display_limit)
            ax.set_aspect("equal", adjustable="box")
            ax.set_title("Gaze detection mean of all trials per target")
            ax.set_xlabel("Horizontal gaze offset (% of display width; 0% = centre)")
            ax.set_ylabel("Vertical gaze offset (% of display height; + = up; 0% = centre)")
            footer = (
                f"{paper_qc_audit['included_observations']}/{paper_qc_audit['total_observations']} "
                f"session/target observations plotted; {ellipse_count} 95% observation ellipses. "
                f"Target mismatches: {paper_qc_audit['target_mismatches']}; robust centroid outliers: "
                f"{paper_qc_audit['robust_centroid_outliers']}. "
                f"Excluded source samples: {paper_qc_audit['excluded_samples']}. "
                "Cross-sectional by date, not matched-visit repeatability. "
                "Coordinates are percentages of display width and height."
            )
        fig.text(
            0.5, 0.01, footer,
            ha="center", fontsize=8, color="#61758a",
        )
    _save(path)
    created.append(path)

    path = output_dir / ALL_FIGURES[9]
    if not paper_qc_available:
        plt.figure(figsize=(9.5, 4.8))
        _empty_plot(
            "QC-filtered target error over eccentricity",
            _paper_unavailable_message(paper_qc, paper_mode) + " No scientific values were imputed.",
        )
    else:
        groups = (
            [f"Visit {value}" for value in sorted(int(value) for value in paper_qc_display["visit_index"].dropna().unique())]
            if paper_mode == "degrees"
            else sorted(paper_qc_display["plot_group"].dropna().astype(str).unique())
        )
        columns = min(3, max(1, len(groups)))
        rows = int(np.ceil(len(groups) / columns))
        fig, axes = plt.subplots(
            rows, columns, figsize=(5.2 * columns, 3.7 * rows), squeeze=False, sharex=True, sharey=True
        )
        for axis, group_label in zip(axes.flat, groups):
            group = paper_qc_display[paper_qc_display["plot_group"] == group_label]
            x = group["plot_eccentricity"].to_numpy(dtype=float)
            y = group["plot_omae"].to_numpy(dtype=float)
            axis.scatter(x, y, s=34, facecolor="white", edgecolor="#17324d", alpha=0.82)
            unique_x = np.unique(x)
            stats = f"n={len(group)}"
            if len(unique_x) >= 2 and len(group) >= 3:
                slope, intercept = np.polyfit(x, y, 1)
                line_x = np.linspace(float(np.min(x)), float(np.max(x)), 100)
                axis.plot(line_x, slope * line_x + intercept, color="#E15759", linewidth=1.8)
                correlation = (
                    float(np.corrcoef(x, y)[0, 1])
                    if np.std(x) > 0 and np.std(y) > 0
                    else float("nan")
                )
                stats += (
                    f"  slope={slope:.3f}  r={correlation:.3f}"
                    if np.isfinite(correlation)
                    else f"  slope={slope:.3f}"
                )
            axis.text(0.03, 0.94, stats, transform=axis.transAxes, va="top", fontsize=8, color="#526d82")
            axis.set_title(group_label)
            if paper_mode == "degrees":
                axis.set_xlabel("Target eccentricity from display centre (deg)")
                axis.set_ylabel("QC-filtered OMAE (deg)")
            else:
                axis.set_xlabel("Target eccentricity (relative screen-coordinate distance, %)")
                axis.set_ylabel("QC-filtered mean radial error (relative coordinate, %)")
        for axis in axes.flat[len(groups):]:
            axis.axis("off")
        title = (
            "QC-filtered omnidirectional mean average error over target eccentricity"
            if paper_mode == "degrees"
            else "QC-filtered relative target error over eccentricity by collection date"
        )
        fig.suptitle(title, fontsize=14)
        fig.text(
            0.5,
            0.01,
            f"{paper_qc_audit['included_observations']}/{paper_qc_audit['total_observations']} "
            "audited target observations retained. In normalised mode, 100% equals 1.0 coordinate unit.",
            ha="center",
            fontsize=8,
            color="#61758a",
        )
    _save(path)
    created.append(path)

    path = output_dir / ALL_FIGURES[10]
    layout = paper_qc.copy()
    required_layout_columns = {
        "target_x", "target_y", "target_label", "session_id", "paper_qc_valid_samples",
    }
    if layout.empty or not required_layout_columns.issubset(layout.columns):
        plt.figure(figsize=(8.2, 6.6))
        _empty_plot(
            "QC-filtered target layout and data coverage",
            "Unavailable: QC-retained target positions and target-period gaze are required.",
        )
    else:
        for column in (
            "target_x", "target_y", "paper_qc_valid_samples", "paper_qc_excluded_samples",
            "settle_excluded_valid_samples", "target_settle_time_s", "paper_qc_omae_deg",
            "paper_qc_omae_normalised",
        ):
            layout[column] = pd.to_numeric(
                layout.get(column, pd.Series(np.nan, index=layout.index)), errors="coerce"
            )
        layout = layout.dropna(subset=["target_x", "target_y"])
        error_column = (
            "paper_qc_omae_deg"
            if layout["paper_qc_omae_deg"].notna().any()
            else "paper_qc_omae_normalised"
        )
        error_label = (
            "Median QC-filtered OMAE (deg)"
            if error_column == "paper_qc_omae_deg"
            else "Median QC-filtered radial error (relative coordinate, %)"
        )
        layout_summary = (
            layout.groupby(["target_label", "target_x", "target_y"], as_index=False, dropna=False)
            .agg(
                session_observations=("session_id", "nunique"),
                retained_samples=("paper_qc_valid_samples", "sum"),
                excluded_samples=("paper_qc_excluded_samples", "sum"),
                excluded_settle_samples=("settle_excluded_valid_samples", "sum"),
                settle_time_s=("target_settle_time_s", "max"),
                median_error=(error_column, "median"),
            )
        )
        layout_summary["target_x"] = pd.to_numeric(layout_summary["target_x"], errors="coerce") * 100.0
        layout_summary["target_y"] = pd.to_numeric(layout_summary["target_y"], errors="coerce") * 100.0
        if error_column == "paper_qc_omae_normalised":
            layout_summary["median_error"] = pd.to_numeric(
                layout_summary["median_error"], errors="coerce"
            ) * 100.0
        fig, ax = plt.subplots(figsize=(8.2, 6.6))
        if layout_summary.empty:
            ax.text(0.5, 0.5, "No QC-retained target positions", ha="center", va="center")
            ax.axis("off")
        else:
            sample_scale = np.log1p(layout_summary["retained_samples"].clip(lower=0))
            span = float(sample_scale.max() - sample_scale.min())
            sizes = (
                420 + (sample_scale - sample_scale.min()) / span * 520
                if span > 0
                else np.full(len(layout_summary), 620)
            )
            errors = pd.to_numeric(layout_summary["median_error"], errors="coerce")
            plot_errors = errors.fillna(errors.median() if errors.notna().any() else 0.0)
            scatter = ax.scatter(
                layout_summary["target_x"],
                layout_summary["target_y"],
                s=sizes,
                c=plot_errors,
                cmap="viridis",
                edgecolor="white",
                linewidth=1.4,
                zorder=3,
            )
            if errors.notna().any():
                colorbar = fig.colorbar(scatter, ax=ax, fraction=0.045, pad=0.04)
                colorbar.set_label(error_label)
            for _, row in layout_summary.iterrows():
                coverage = (
                    f"{row['target_label']}\n{int(row['session_observations'])} sessions / "
                    f"{int(row['retained_samples'])} QC samples"
                )
                ax.annotate(
                    coverage,
                    (float(row["target_x"]), float(row["target_y"])),
                    xytext=(0, -9),
                    textcoords="offset points",
                    ha="center",
                    va="top",
                    fontsize=7,
                )
            ax.add_patch(Rectangle((0, 0), 100, 100, fill=False, edgecolor="#61758a", linewidth=1.2))
            ax.set_xlim(-4, 104)
            ax.set_ylim(104, -4)
            ax.set_aspect("equal", adjustable="box")
            ax.set_title("QC-filtered target layout and data coverage")
            ax.set_xlabel("Horizontal target position (% of display width)")
            ax.set_ylabel("Vertical target position (% of display height; origin at top)")
            settle_values = layout_summary["settle_time_s"].dropna()
            settle_text = (
                f" after a {float(settle_values.max()):.3f} s settling window"
                if not settle_values.empty
                else ""
            )
            excluded_samples = int(layout_summary["excluded_samples"].fillna(0).sum())
            fig.text(
                0.5,
                0.01,
                f"Bubble size reflects QC-retained valid gaze samples{settle_text}; "
                f"{excluded_samples} post-settling samples were excluded by screen-validity QC. "
                "Coordinates are percentages of display width and height.",
                ha="center",
                fontsize=8,
                color="#61758a",
            )
    _save(path)
    created.append(path)

    path = output_dir / ALL_FIGURES[11]
    fig, ax = plt.subplots(figsize=(10.5, 7.2))
    if not paper_available:
        ax.text(
            0.5, 0.52, _paper_unavailable_message(paper, paper_mode), ha="center", va="center",
            fontsize=11, wrap=True, transform=ax.transAxes,
        )
        ax.set_title("Unfiltered target-centroid diagnostic")
        ax.axis("off")
    else:
        diagnostic_targets = (
            paper[["target_key", "target_label", "plot_target_x", "plot_target_y"]]
            .drop_duplicates("target_key")
            .sort_values(["plot_target_y", "plot_target_x"], ascending=[False, True])
        )
        diagnostic_palette = sns.color_palette("husl", n_colors=max(1, len(diagnostic_targets)))
        diagnostic_colors = dict(zip(diagnostic_targets["target_key"], diagnostic_palette))
        diagnostic_markers = ["o", "*", "s", "D", "^", "v", "P", "X", "<", ">"]
        diagnostic_groups = (
            [f"Visit {value}" for value in sorted(int(value) for value in paper["visit_index"].dropna().unique())]
            if paper_mode == "degrees"
            else sorted(paper["plot_group"].dropna().astype(str).unique())
        )
        diagnostic_limit = 0.75
        diagnostic_off_window = 0
        for _, target in diagnostic_targets.iterrows():
            key = target["target_key"]
            color = diagnostic_colors[key]
            target_group = paper[paper["target_key"] == key]
            ax.scatter(
                [target["plot_target_x"]], [target["plot_target_y"]], marker="x", s=85,
                linewidth=2, color=color, zorder=4,
            )
            ax.annotate(
                str(target["target_label"]),
                (float(target["plot_target_x"]), float(target["plot_target_y"])),
                xytext=(4, 5), textcoords="offset points", fontsize=7, color=color,
            )
            for group_index, group_label in enumerate(diagnostic_groups):
                observations = target_group[target_group["plot_group"] == group_label]
                if observations.empty:
                    continue
                if paper_mode == "normalised":
                    in_window = (
                        observations["plot_gaze_x"].abs().le(diagnostic_limit)
                        & observations["plot_gaze_y"].abs().le(diagnostic_limit)
                    )
                    visible = observations[in_window]
                    off_window = observations[~in_window]
                    if not visible.empty:
                        ax.scatter(
                            visible["plot_gaze_x"], visible["plot_gaze_y"],
                            marker=diagnostic_markers[group_index % len(diagnostic_markers)], s=42,
                            facecolor=color, edgecolor="white", linewidth=0.6, alpha=0.82, zorder=3,
                        )
                    if not off_window.empty:
                        diagnostic_off_window += len(off_window)
                        ax.scatter(
                            off_window["plot_gaze_x"].clip(-diagnostic_limit, diagnostic_limit),
                            off_window["plot_gaze_y"].clip(-diagnostic_limit, diagnostic_limit),
                            marker="X", s=48, facecolor=color, edgecolor="#17202a",
                            linewidth=0.7, alpha=0.9, zorder=3,
                        )
                else:
                    ax.scatter(
                        observations["plot_gaze_x"], observations["plot_gaze_y"],
                        marker=diagnostic_markers[group_index % len(diagnostic_markers)], s=42,
                        facecolor=color, edgecolor="white", linewidth=0.6, alpha=0.82, zorder=3,
                    )
        diagnostic_handles = [
            Line2D(
                [0], [0], marker=diagnostic_markers[index % len(diagnostic_markers)], color="none",
                markerfacecolor="#526d82", markeredgecolor="white", markersize=8, label=group_label,
            )
            for index, group_label in enumerate(diagnostic_groups)
        ]
        diagnostic_handles.append(
            Line2D([0], [0], marker="x", color="#526d82", linestyle="none", markersize=8, label="Target position")
        )
        if paper_mode == "normalised" and diagnostic_off_window:
            diagnostic_handles.append(
                Line2D(
                    [0], [0], marker="X", color="none", markerfacecolor="#526d82",
                    markeredgecolor="#17202a", markersize=7, label="Off-window centroid (shown at border)",
                )
            )
        ax.legend(handles=diagnostic_handles, loc="best", fontsize=8)
        ax.axhline(0, color="#9aa8b4", linewidth=0.8)
        ax.axvline(0, color="#9aa8b4", linewidth=0.8)
        ax.set_title("Unfiltered target-centroid diagnostic")
        if paper_mode == "degrees":
            ax.set_aspect("equal", adjustable="datalim")
            ax.set_xlabel("Horizontal gaze direction relative to display centre (deg)")
            ax.set_ylabel("Vertical gaze direction relative to display centre (deg)")
        else:
            ax.set_xlim(-diagnostic_limit, diagnostic_limit)
            ax.set_ylim(-diagnostic_limit, diagnostic_limit)
            ax.set_aspect("equal", adjustable="box")
            ax.set_xlabel("Horizontal gaze offset (fraction of display width; 0 = centre)")
            ax.set_ylabel("Vertical gaze offset (fraction of display height; + = up; 0 = centre)")
        fig.text(
            0.5, 0.01,
            f"All {len(paper)} exported target centroids are retained; {diagnostic_off_window} off-window "
            "centroids are shown at the border. Use for QC audit, not paper-style inference.",
            ha="center", fontsize=8, color="#61758a",
        )
    _save(path)
    created.append(path)
    for generated in created:
        if generated.name not in FIGURES:
            generated.unlink(missing_ok=True)
    return [generated for generated in created if generated.name in FIGURES]



def _format_value(value: object, decimals: int = 4) -> str:
    if value is None:
        return "-"
    try:
        if bool(pd.isna(value)):
            return "-"
    except (TypeError, ValueError):
        pass
    if isinstance(value, (float, np.floating)):
        return "-" if not np.isfinite(float(value)) else f"{float(value):.{decimals}f}"
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return str(int(value))
    return escape(str(value))


def _format_percent(value: object, decimals: int = 1) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    return "-" if not np.isfinite(numeric) else f"{numeric * 100:.{decimals}f}%"


def _format_unit(value: object, unit: str, decimals: int = 2) -> str:
    formatted = _format_value(value, decimals)
    return "-" if formatted == "-" else f"{formatted} {unit}"


def _column_label(column: str, labels: dict[str, str] | None) -> str:
    return labels.get(column, column.replace("_", " ").title()) if labels else column.replace("_", " ").title()


def _html_table(
    frame: pd.DataFrame,
    columns: list[str],
    labels: dict[str, str] | None = None,
    decimals: dict[str, int] | None = None,
) -> str:
    available = [column for column in columns if column in frame.columns]
    if frame.empty or not available:
        return "<p class='empty'>No data available.</p>"
    head = "".join(f"<th>{escape(_column_label(column, labels))}</th>" for column in available)
    rows = []
    for _, row in frame[available].iterrows():
        cells = "".join(
            f"<td>{_format_value(row[column], (decimals or {}).get(column, 4))}</td>"
            for column in available
        )
        rows.append(f"<tr>{cells}</tr>")
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def _session_review_table(
    frame: pd.DataFrame,
    columns: list[str],
    review_root: Path | None = None,
    labels: dict[str, str] | None = None,
    decimals: dict[str, int] | None = None,
) -> str:
    available = [column for column in columns if column in frame.columns]
    if frame.empty or not available:
        return "<p class='empty'>No data available.</p>"
    head = "".join(f"<th>{escape(_column_label(column, labels))}</th>" for column in available) + "<th>Review</th>"
    rows = []
    for _, row in frame.iterrows():
        cells = "".join(
            f"<td>{_format_value(row[column], (decimals or {}).get(column, 4))}</td>"
            for column in available
        )
        session_id = escape(str(row.get("session_id", "")))
        review_path = review_root / session_id / "session_review.png" if review_root is not None and session_id else None
        link = f"<a href='sessions/{session_id}/session_review.png'>open</a>" if review_path is not None and review_path.is_file() else "-"
        rows.append(f"<tr>{cells}<td>{link}</td></tr>")
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def _display_table(
    frame: pd.DataFrame,
    percent_fields: dict[str, str],
    columns: list[str],
) -> pd.DataFrame:
    table = frame.copy()
    for source, destination in percent_fields.items():
        values = table.get(source, pd.Series(np.nan, index=table.index, dtype=float))
        table[destination] = pd.to_numeric(values, errors="coerce") * 100.0
    return table.reindex(columns=columns).copy()


def _build_report_display_tables(
    combined: pd.DataFrame,
    long_term: pd.DataFrame,
    repeatability: pd.DataFrame,
    target_visits: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Prepare presentation-safe report tables."""

    session = combined.copy()
    if "target_settle_time_s" not in session:
        for source in ("target_settle_time_s_y", "target_settle_time_s_x"):
            if source in session:
                session["target_settle_time_s"] = session[source]
                break
    if "target_settle_time_s" not in session:
        session["target_settle_time_s"] = np.nan

    targets = target_visits.copy()
    target_numeric = (
        "paper_qc_gaze_direction_x_normalised", "paper_qc_gaze_direction_y_normalised",
        "target_x_centered", "target_y_centered", "paper_qc_gaze_direction_x_deg",
        "paper_qc_gaze_direction_y_deg", "target_x_deg", "target_y_deg",
    )
    for column in target_numeric:
        targets[column] = pd.to_numeric(
            targets.get(column, pd.Series(np.nan, index=targets.index)), errors="coerce"
        )
    targets["paper_qc_error_x_normalised"] = (
        targets["paper_qc_gaze_direction_x_normalised"] - targets["target_x_centered"]
    )
    targets["paper_qc_error_y_normalised"] = (
        targets["paper_qc_gaze_direction_y_normalised"] - targets["target_y_centered"]
    )
    targets["paper_qc_error_x_deg"] = (
        targets["paper_qc_gaze_direction_x_deg"] - targets["target_x_deg"]
    )
    targets["paper_qc_error_y_deg"] = (
        targets["paper_qc_gaze_direction_y_deg"] - targets["target_y_deg"]
    )

    return {
        "session": _display_table(
            session,
            {
                "valid_rate": "valid_gaze_samples_pct",
                "data_loss_rate": "data_loss_pct",
                "marker_precision_rms": "marker_precision_relative_coordinate_pct",
                "marker_accuracy_rmse": "marker_accuracy_relative_coordinate_pct",
            },
            [
                "session_id", "date", "subject_id", "device_id", "test_id", "quality_status",
                "coordinate_space", "effective_sampling_hz", "valid_gaze_samples_pct", "data_loss_pct",
                "marker_precision_relative_coordinate_pct", "marker_accuracy_relative_coordinate_pct",
                "target_recovery_status", "recovered_target_intervals", "target_settle_time_s", "quality_flags",
            ],
        ),
        "long_term": _display_table(
            long_term,
            {
                "median_valid_rate": "median_valid_gaze_samples_pct",
                "median_data_loss_rate": "median_data_loss_pct",
                "median_marker_precision_rms": "median_marker_precision_relative_coordinate_pct",
                "median_marker_accuracy_rmse": "median_marker_accuracy_relative_coordinate_pct",
            },
            [
                "date", "device_id", "test_id", "test_condition", "session_count", "subject_count",
                "repeated_subject_count", "median_sampling_hz", "median_valid_gaze_samples_pct",
                "median_data_loss_pct", "median_marker_precision_relative_coordinate_pct",
                "median_marker_accuracy_relative_coordinate_pct", "sessions_with_warnings",
                "sampling_change_pct_from_baseline", "valid_rate_change_points_from_baseline",
            ],
        ),
        "repeatability": _display_table(
            repeatability,
            {
                "median_valid_rate": "median_valid_gaze_samples_pct",
                "valid_rate_repeatability_95": "valid_gaze_repeatability_95_pct",
                "median_marker_precision_rms": "median_marker_precision_relative_coordinate_pct",
                "precision_repeatability_95": "precision_repeatability_95_relative_coordinate_pct",
            },
            [
                "subject_id", "device_id", "test_id", "test_condition", "session_count", "date_count",
                "median_sampling_hz", "sampling_hz_repeatability_95", "median_valid_gaze_samples_pct",
                "valid_gaze_repeatability_95_pct", "median_marker_precision_relative_coordinate_pct",
                "precision_repeatability_95_relative_coordinate_pct",
            ],
        ),
        "target_visits": _display_table(
            targets,
            {
                "target_x": "target_x_pct_display_width",
                "target_y": "target_y_pct_display_height",
                "target_eccentricity_normalised": "target_eccentricity_relative_coordinate_pct",
                "paper_qc_error_x_normalised": "paper_qc_error_x_pct_display_width",
                "paper_qc_error_y_normalised": "paper_qc_error_y_pct_display_height",
                "paper_qc_omae_normalised": "paper_qc_omae_relative_coordinate_pct",
                "paper_qc_precision_rms_normalised": "paper_qc_precision_rms_relative_coordinate_pct",
            },
            [
                "visit_label", "date", "subject_id", "session_id", "target_label", "coordinate_space",
                "paper_qc_status", "paper_plot_status", "target_settle_time_s",
                "settle_excluded_valid_samples", "paper_qc_valid_samples", "paper_qc_excluded_samples",
                "target_x_pct_display_width", "target_y_pct_display_height",
                "target_eccentricity_relative_coordinate_pct", "paper_qc_error_x_pct_display_width",
                "paper_qc_error_y_pct_display_height", "paper_qc_omae_relative_coordinate_pct",
                "paper_qc_precision_rms_relative_coordinate_pct", "target_x_deg", "target_y_deg",
                "target_eccentricity_deg", "paper_qc_error_x_deg", "paper_qc_error_y_deg",
                "paper_qc_omae_deg", "paper_qc_precision_rms_deg", "interval_count",
            ],
        ),
    }


def _summarise_target_display(target_display: pd.DataFrame) -> pd.DataFrame:
    """Collapse QC-retained observations to a concise date/target HTML summary."""

    output_columns = [
        "date", "target_label", "coordinate_space", "qc_session_observations", "qc_subject_count",
        "qc_retained_samples", "qc_excluded_samples", "target_x_pct_display_width",
        "target_y_pct_display_height", "target_eccentricity_relative_coordinate_pct",
        "median_qc_error_x_pct_display_width", "median_qc_error_y_pct_display_height",
        "median_qc_omae_relative_coordinate_pct", "median_qc_precision_rms_relative_coordinate_pct",
        "target_x_deg", "target_y_deg", "target_eccentricity_deg", "median_qc_error_x_deg",
        "median_qc_error_y_deg", "median_qc_omae_deg", "median_qc_precision_rms_deg",
    ]
    if target_display.empty or "paper_plot_status" not in target_display:
        return pd.DataFrame(columns=output_columns)
    included = target_display[target_display["paper_plot_status"].astype(str).eq("included")].copy()
    if included.empty:
        return pd.DataFrame(columns=output_columns)
    group_columns = [
        "date", "target_label", "coordinate_space", "target_x_pct_display_width",
        "target_y_pct_display_height", "target_eccentricity_relative_coordinate_pct",
        "target_x_deg", "target_y_deg", "target_eccentricity_deg",
    ]
    summary = (
        included.groupby(group_columns, as_index=False, dropna=False)
        .agg(
            qc_session_observations=("session_id", "nunique"),
            qc_subject_count=("subject_id", "nunique"),
            qc_retained_samples=("paper_qc_valid_samples", "sum"),
            qc_excluded_samples=("paper_qc_excluded_samples", "sum"),
            median_qc_error_x_pct_display_width=("paper_qc_error_x_pct_display_width", "median"),
            median_qc_error_y_pct_display_height=("paper_qc_error_y_pct_display_height", "median"),
            median_qc_omae_relative_coordinate_pct=("paper_qc_omae_relative_coordinate_pct", "median"),
            median_qc_precision_rms_relative_coordinate_pct=(
                "paper_qc_precision_rms_relative_coordinate_pct", "median"
            ),
            median_qc_error_x_deg=("paper_qc_error_x_deg", "median"),
            median_qc_error_y_deg=("paper_qc_error_y_deg", "median"),
            median_qc_omae_deg=("paper_qc_omae_deg", "median"),
            median_qc_precision_rms_deg=("paper_qc_precision_rms_deg", "median"),
        )
        .sort_values(["date", "target_y_pct_display_height", "target_x_pct_display_width"])
        .reset_index(drop=True)
    )
    return summary.reindex(columns=output_columns)

def _write_report_display_tables(
    output_dir: Path,
    combined: pd.DataFrame,
    long_term: pd.DataFrame,
    repeatability: pd.DataFrame,
    target_visits: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    tables = _build_report_display_tables(combined, long_term, repeatability, target_visits)
    stems = {
        "session": "report_display_session_metrics",
        "long_term": "report_display_long_term",
        "repeatability": "report_display_repeatability",
        "target_visits": "report_display_target_visits",
    }
    for name, table in tables.items():
        csv_path = output_dir / f"{stems[name]}.csv"
        table.to_csv(csv_path, index=False)
        csv_path.with_suffix(".json").write_text(
            json.dumps(json.loads(table.to_json(orient="records")), indent=2), encoding="utf-8"
        )
    units = {
        "raw_data_policy": "Raw analysis files are retained unchanged alongside these presentation tables.",
        "conversions": {
            "*_pct": "source proportion multiplied by 100",
            "*_pct_display_width": "normalised horizontal coordinate or error multiplied by 100",
            "*_pct_display_height": "normalised vertical coordinate or error multiplied by 100",
            "*_relative_coordinate_pct": "normalised radial coordinate distance multiplied by 100; 100% = 1.0 raw unit",
            "*_deg": "visual-angle degrees, present only when physical display geometry and viewing distance are recorded",
        },
    }
    (output_dir / "report_display_units.json").write_text(json.dumps(units, indent=2), encoding="utf-8")
    return tables


_DELAY_EVIDENCE_FIGURES = (
    ("delay_accuracy.png", "Approximate accuracy comparison", "Balanced target error under the declared fixed display-field-of-view assumption. Lower is better."),
    ("delay_spread.png", "Approximate repeat-spread comparison", "Repeated-marker radial spread under the same assumed field of view. Lower is better."),
    ("condition_calibration.png", "Calibration and accuracy", "Selected 50 ms delay under the assumed-FOV conversion, separated by calibration and accuracy condition."),
    ("condition_10min.png", "10-minute accuracy", "Selected 50 ms delay in the 10-minute condition under the assumed-FOV conversion."),
    ("condition_60min.png", "60-minute accuracy", "Selected 50 ms delay in the 60-minute condition under the assumed-FOV conversion."),
    ("ellipse_coverage.png", "Ellipse coverage QA", "Post-selection empirical 95% coverage check; excluded from the primary delay score."),
)


def _report_relative_path(asset: Path, report_path: Path) -> str:
    return Path(os.path.relpath(asset, report_path.parent)).as_posix()


def _stage_client_delay_evidence(evidence_dir: Path | None, report_path: Path) -> Path | None:
    if evidence_dir is None:
        return None
    destination = report_path.parent / "client_delay_evidence"
    if evidence_dir.resolve() != destination.resolve():
        shutil.copytree(evidence_dir, destination, dirs_exist_ok=True)
    return destination


def _client_delay_downloads(evidence_dir: Path | None, report_path: Path) -> list[tuple[str, str, str, str]]:
    if evidence_dir is None:
        return []
    items = (
        ("CSV - CLIENT DELAY", "Delay metrics", "All 0-200 ms sensitivity-scan values and the requested 50/100/150 ms candidates.", "data/delay_metrics_accuracy_and_spread.csv"),
        ("CSV - CLIENT DELAY", "Paired bootstrap evidence", "Participant-level paired confidence intervals used by the shortest-equivalent rule.", "data/client_candidate_pairwise_bootstrap.csv"),
        ("CSV - CLIENT DELAY", "Participant-condition-target data", "Underlying target-level metrics for the delay comparison.", "data/participant_condition_target_metrics.csv"),
        ("JSON - CLIENT DELAY", "Selection rule", "Machine-readable candidates, decision rule, seed and interpretation boundaries.", "data/selected_delay_client_rule.json"),
        ("CSV - FIGURE DATA", "Corrected target positions", "Target coordinates on the declared fixed display-FOV grid.", "data/corrected_target_positions.csv"),
        ("CSV - FIGURE DATA", "Recording-target means", "QC-retained source rows used by the three selected-delay condition figures.", "data/recording_target_means_delay_0.0500s.csv"),
        ("CSV - FIGURE QA", "Ellipse coverage rows", "Underlying post-selection empirical coverage values.", "data/ellipse_master_delay_0.0500s.csv"),
        ("PY - REBUILD", "Rebuild delay figures", "Deterministically redraw the six focused figures with explicit assumed-FOV labels.", "rebuild_figures.py"),
        ("JSON - PROVENANCE", "Delay evidence provenance", "Scope, source, coordinate assumption and included files for the DemoB evidence bundle.", "provenance.json"),
    )
    downloads = []
    for kind, title, detail, relative_asset in items:
        asset = evidence_dir / relative_asset
        if asset.is_file():
            downloads.append((kind, title, detail, _report_relative_path(asset, report_path)))
    return downloads


def _client_delay_section(evidence_dir: Path | None, report_path: Path) -> str:
    if evidence_dir is None:
        return ""
    metrics_path = evidence_dir / "data" / "delay_metrics_accuracy_and_spread.csv"
    rule_path = evidence_dir / "data" / "selected_delay_client_rule.json"
    if not metrics_path.is_file() or not rule_path.is_file():
        return ""
    try:
        metrics = pd.read_csv(metrics_path)
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
        selected_delay = float(rule["selected_delay_s"])
        candidates = [float(value) for value in rule["client_candidates_s"]]
        assumed_fov = rule.get("assumed_field_of_view_deg", {})
        assumed_fov_x = float(assumed_fov.get("x", 60.0))
        assumed_fov_y = float(assumed_fov.get("y", 33.75))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, pd.errors.ParserError):
        return ""
    primary = metrics.loc[metrics.get("condition", pd.Series(dtype=str)).astype(str).eq("ALL")].copy()
    primary["delay_s"] = pd.to_numeric(primary.get("delay_s"), errors="coerce")
    rows = []
    for delay in candidates:
        candidate = primary.loc[np.isclose(primary["delay_s"], delay, atol=1e-9)]
        if candidate.empty:
            continue
        value = candidate.iloc[0]
        selected = bool(np.isclose(delay, selected_delay, atol=1e-9))
        row_class = " class='selected-row'" if selected else ""
        decision = "<span class='pill'>Selected</span>" if selected else "No clear improvement"
        rows.append(
            f"<tr{row_class}><td><strong>{delay:.4f} s / {int(round(delay * 1000))} ms</strong></td>"
            f"<td>{_format_value(value.get('balanced_accuracy_deg'), 4)}&deg;</td>"
            f"<td>{_format_value(value.get('balanced_repeat_spread_deg'), 4)}&deg;</td>"
            f"<td>{_format_value(value.get('valid_marker_windows'), 0)}</td><td>{decision}</td></tr>"
        )
    if len(rows) != len(candidates):
        return ""
    figure_html = []
    for filename, title, caption in _DELAY_EVIDENCE_FIGURES:
        asset = evidence_dir / "figures" / filename
        if asset.is_file():
            figure_html.append(
                f"<figure><img src='{escape(_report_relative_path(asset, report_path))}' alt='{escape(title)}'>"
                f"<figcaption><strong>{escape(title)}</strong> {escape(caption)}</figcaption></figure>"
            )
    if len(figure_html) != len(_DELAY_EVIDENCE_FIGURES):
        return ""
    bootstrap_repetitions = _format_value(rule.get("bootstrap_repetitions"), 0)
    return f"""<section id='delay' class='delay-evidence'>
<div class='heading'><h2>Client-requested delay comparison</h2><p>Independent DemoB client-decision evidence; it does not alter the OpenET2 target settling window.</p></div>
<p class='note'>The primary comparison is exactly 0.0500, 0.1000 and 0.1500 seconds. Balanced target error and repeat spread are assessed separately; a longer delay is used only with clear paired evidence of improvement without a conflicting worsening.</p>
<p class='note'><strong>Coordinate boundary:</strong> the angular labels in this imported evidence use a fixed {assumed_fov_x:.2f}&deg; &times; {assumed_fov_y:.2f}&deg; display-field-of-view assumption because physical display dimensions and viewing distance were not supplied. Values are approximate, dataset-specific assumed-FOV degree scores; not measured visual angles.</p>
<div class='result-banner'><div class='result-value'>{int(round(selected_delay * 1000))} ms<small>recommended client delay</small></div><div><h3>Shortest equivalent candidate</h3><p>Longer candidates slightly reduce repeat spread, but do not establish a clear non-conflicting improvement over 50 ms. The recorded decision rule therefore keeps the shortest candidate.</p></div></div>
<div class='table-wrap delay-table'><table><thead><tr><th>Candidate</th><th>Approx. balanced accuracy (assumed-FOV deg)</th><th>Approx. repeat spread (assumed-FOV deg)</th><th>Valid windows</th><th>Decision</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h3>Primary candidate evidence</h3><div class='figures'>{''.join(figure_html[:2])}</div>
<h3>Selected-delay views by test condition</h3><div class='figures'>{''.join(figure_html[2:5])}</div>
<h3>Post-selection quality assurance</h3><div class='figures'><div>{figure_html[5]}</div><article class='panel decision-panel'><h3>Decision boundary</h3><p>This comparison uses assumed-FOV degree scores, 14 paired participants and {bootstrap_repetitions} bootstrap repetitions. It is separate from the local GP3 normalised-coordinate analysis and from the 0.600 s target-settling exclusion. The 50 ms decision is comparative within this dataset and should not be reported as a physical visual-angle benchmark.</p></article></div>
</section>"""


def _evidence_status_section(
    combined: pd.DataFrame,
    summary: dict[str, object],
    repeatability: pd.DataFrame,
) -> str:
    """State what the run can support without turning quality flags into deletions."""

    session_count = int(len(combined))
    warning_count = int(summary.get("sessions_with_warnings") or 0)
    geometry_columns = ("display_width_mm", "display_height_mm", "viewing_distance_mm")
    geometry_available = bool(session_count) and all(
        pd.to_numeric(
            combined.get(column, pd.Series(index=combined.index, dtype=float)), errors="coerce"
        ).gt(0).all()
        for column in geometry_columns
    )
    calibration_units = combined.get(
        "calibration_error_unit", pd.Series(index=combined.index, dtype=str)
    ).fillna("").astype(str).str.strip().str.lower()
    known_calibration_units = int((~calibration_units.isin({"", "unknown", "device_reported"})).sum())
    synthetic_text = (
        combined.get("device_id", pd.Series("", index=combined.index)).fillna("").astype(str)
        + " "
        + combined.get("notes", pd.Series("", index=combined.index)).fillna("").astype(str)
    )
    is_synthetic = bool(session_count) and synthetic_text.str.contains("synthetic", case=False, na=False).all()
    repeated_groups = len(repeatability)
    subject_ids = combined.get("subject_id", pd.Series(index=combined.index, dtype=str)).fillna("").astype(str)
    test_like_subject_count = int(subject_ids[subject_ids.str.contains("test", case=False, na=False)].nunique())

    if is_synthetic:
        status_class = "status-synthetic"
        title = "Software-validation example"
        conclusion = "This run verifies the collection and analysis workflow with labelled synthetic data; it is not evidence of physical device performance."
    elif not geometry_available or repeated_groups == 0:
        status_class = "status-descriptive"
        title = "Descriptive benchmark only"
        conclusion = "This run supports auditable quality review and descriptive benchmarking, but not visual-angle or device-drift conclusions beyond the measurements recorded."
    elif warning_count:
        status_class = "status-conditional"
        title = "Conditional comparison evidence"
        conclusion = "Physical geometry and matched repeatability are available, but session quality flags require review before any comparative claim."
    else:
        status_class = "status-ready"
        title = "Comparative benchmark candidate"
        conclusion = "The recorded prerequisites support comparative analysis; retain the audit exports and apply the declared protocol before drawing conclusions."

    geometry_text = (
        "Physical display geometry is recorded for every session; degree fields may be evaluated where target data support them."
        if geometry_available
        else "Physical display geometry is incomplete; normalised display percentages remain the only valid coordinate unit for affected sessions."
    )
    repeatability_text = (
        f"{repeated_groups} matched participant/device/protocol repeatability group(s) are available."
        if repeated_groups
        else "No confirmed matched participant/device/protocol repeatability group is available for a longitudinal claim."
    )
    digest = str(summary.get("input_content_digest_sha256") or "").strip()
    provenance_text = (
        f"Input provenance is recorded with SHA-256 digest <code>{escape(digest[:12])}&hellip;</code>."
        if digest
        else "Input provenance was not available when this report was written."
    )
    details = [
        f"{session_count} analysed session(s), {int(summary.get('date_count', 0) or 0)} collection date(s), and {int(summary.get('device_count', 0) or 0)} device(s).",
        f"{warning_count} session(s) are flagged for quality review; flags remain visible and are not silently excluded.",
        geometry_text,
        repeatability_text,
        f"{known_calibration_units}/{session_count} session(s) identify a calibration-error unit.",
        provenance_text,
    ]
    if test_like_subject_count:
        details.insert(
            4,
            f"{test_like_subject_count} subject identifier(s) contain a test-like label; confirm identity mapping before any repeatability claim.",
        )
    return (
        f"<section id='evidence-status' class='evidence-status {status_class}'>"
        f"<div><p class='eyebrow'>Interpretation status</p><h2>{escape(title)}</h2><p>{escape(conclusion)}</p></div>"
        f"<ul>{''.join(f'<li>{item}</li>' for item in details)}</ul></section>"
    )


def write_html_report(
    combined: pd.DataFrame,
    long_term: pd.DataFrame,
    summary: dict[str, object],
    report_path: Path,
    repeatability: pd.DataFrame | None = None,
    target_visits: pd.DataFrame | None = None,
    paper_criteria: pd.DataFrame | None = None,
    client_delay_evidence: Path | None = None,
) -> Path:
    """Write the self-contained HTML evidence report."""

    repeatability = repeatability if repeatability is not None else pd.DataFrame()
    target_visits = target_visits if target_visits is not None else pd.DataFrame()
    paper_criteria = paper_criteria if paper_criteria is not None else pd.DataFrame()
    client_delay_evidence = client_delay_evidence.resolve() if client_delay_evidence is not None else None
    report_path.parent.mkdir(parents=True, exist_ok=True)
    client_delay_evidence = _stage_client_delay_evidence(client_delay_evidence, report_path)
    tables = _write_report_display_tables(report_path.parent, combined, long_term, repeatability, target_visits)
    session_display = tables["session"]
    long_term_display = tables["long_term"]
    repeatability_display = tables["repeatability"]
    target_display = _summarise_target_display(tables["target_visits"])
    delay_section = _client_delay_section(client_delay_evidence, report_path)
    delay_nav = "<a href='#delay'>Client delay</a>" if delay_section else ""
    evidence_status_html = _evidence_status_section(combined, summary, repeatability)
    matched_longitudinal = not repeatability.empty
    long_term_title = (
        "Matched long-term comparison" if matched_longitudinal else "Unmatched date-level cohort comparison"
    )
    long_term_nav_label = "Long-term" if matched_longitudinal else "Date cohorts"
    long_term_description = (
        "Median values by matched date and protocol; valid gaze and data loss use percent units."
        if matched_longitudinal
        else "Median values compare independent date-level cohorts; they do not estimate within-participant drift."
    )
    header_scope = (
        "structured quality review, matched long-term comparison and target-level evidence"
        if matched_longitudinal
        else "structured quality review, unmatched date-cohort comparison and target-level evidence"
    )

    available_figures = [
        filename for filename in FIGURES if (report_path.parent / "figures" / filename).is_file()
    ]
    figure_cards = "".join(
        f"<figure><img src='figures/{escape(filename)}' alt='{escape(FIGURE_CAPTIONS[filename])}'><figcaption>{escape(FIGURE_CAPTIONS[filename])}</figcaption></figure>"
        for filename in available_figures
    )
    cards = [
        ("Analysed sessions", _format_value(summary.get("session_count", 0), 0)),
        ("Collection dates", _format_value(summary.get("date_count", 0), 0)),
        ("Devices", _format_value(summary.get("device_count", 0), 0)),
        ("Sessions flagged for review", _format_value(summary.get("sessions_with_warnings", 0), 0)),
        ("Median sampling rate", _format_unit(summary.get("median_sampling_hz"), "Hz", 2)),
        ("Median valid gaze samples", _format_percent(summary.get("median_valid_rate"), 1)),
        ("Verified target recovery", _format_unit(summary.get("video_target_recovered_sessions"), "sessions", 0)),
        ("Target observations", _format_value(summary.get("target_visit_observations", 0), 0)),
        ("Target settling window", _format_unit(summary.get("target_settle_time_s"), "s", 3)),
    ]
    card_html = "".join(
        f"<div class='card'><span>{escape(label)}</span><strong>{escape(value)}</strong></div>"
        for label, value in cards
    )
    target_unit = summary.get("target_visualisation_unit")
    target_note = (
        "QC-filtered target plots use visual degrees because physical display geometry is available."
        if target_unit == "degrees"
        else "QC-filtered target plots use display percentages: X is % of display width, Y is % of display height, and 100% radial distance equals 1.0 raw normalised coordinate unit."
    )

    session_columns = [
        "session_id", "device_id", "quality_status", "coordinate_space", "effective_sampling_hz",
        "valid_gaze_samples_pct", "data_loss_pct", "marker_precision_relative_coordinate_pct",
        "marker_accuracy_relative_coordinate_pct", "target_recovery_status", "recovered_target_intervals",
        "quality_flags",
    ]
    session_labels = {
        "effective_sampling_hz": "Effective Sampling (Hz)",
        "valid_gaze_samples_pct": "Valid Gaze Samples (%)",
        "data_loss_pct": "Data Loss (%)",
        "marker_precision_relative_coordinate_pct": "Marker Precision RMS (relative coordinate, %)",
        "marker_accuracy_relative_coordinate_pct": "Marker Accuracy RMSE (relative coordinate, %)",
        "recovered_target_intervals": "Recovered Target Intervals (count)",
    }
    rate_decimals = {
        "effective_sampling_hz": 2, "valid_gaze_samples_pct": 1, "data_loss_pct": 1,
        "marker_precision_relative_coordinate_pct": 2, "marker_accuracy_relative_coordinate_pct": 2,
    }
    long_columns = [
        "date", "device_id", "test_id", "test_condition", "session_count", "subject_count",
        "repeated_subject_count", "median_sampling_hz", "median_valid_gaze_samples_pct",
        "median_data_loss_pct", "sessions_with_warnings", "sampling_change_pct_from_baseline",
        "valid_rate_change_points_from_baseline",
    ]
    long_labels = {
        "median_sampling_hz": "Median Sampling (Hz)",
        "median_valid_gaze_samples_pct": "Median Valid Gaze Samples (%)",
        "median_data_loss_pct": "Median Data Loss (%)",
        "sessions_with_warnings": "Sessions Flagged (count)",
        "sampling_change_pct_from_baseline": (
            "Sampling Change from Earliest Matched Date (%)"
            if matched_longitudinal
            else "Sampling Change from Earliest Cohort Date (%)"
        ),
        "valid_rate_change_points_from_baseline": (
            "Valid-rate Change from Earliest Matched Date (percentage points)"
            if matched_longitudinal
            else "Valid-rate Change from Earliest Cohort Date (percentage points)"
        ),
    }
    long_decimals = {
        "median_sampling_hz": 2, "median_valid_gaze_samples_pct": 1, "median_data_loss_pct": 1,
        "sampling_change_pct_from_baseline": 2, "valid_rate_change_points_from_baseline": 2,
    }
    repeat_columns = [
        "subject_id", "device_id", "test_id", "test_condition", "session_count", "date_count",
        "median_sampling_hz", "sampling_hz_repeatability_95", "median_valid_gaze_samples_pct",
        "valid_gaze_repeatability_95_pct", "median_marker_precision_relative_coordinate_pct",
        "precision_repeatability_95_relative_coordinate_pct",
    ]
    repeat_labels = {
        "median_sampling_hz": "Median Sampling (Hz)",
        "sampling_hz_repeatability_95": "Sampling Repeatability 95% (Hz)",
        "median_valid_gaze_samples_pct": "Median Valid Gaze Samples (%)",
        "valid_gaze_repeatability_95_pct": "Valid Gaze Repeatability 95% (percentage points)",
        "median_marker_precision_relative_coordinate_pct": "Median Marker Precision (relative coordinate, %)",
        "precision_repeatability_95_relative_coordinate_pct": "Precision Repeatability 95% (relative coordinate, %)",
    }
    target_columns = [
        "date", "target_label", "coordinate_space", "qc_session_observations", "qc_subject_count",
        "qc_retained_samples", "qc_excluded_samples", "target_x_pct_display_width",
        "target_y_pct_display_height", "target_eccentricity_relative_coordinate_pct",
        "median_qc_error_x_pct_display_width", "median_qc_error_y_pct_display_height",
        "median_qc_omae_relative_coordinate_pct", "median_qc_precision_rms_relative_coordinate_pct",
        "target_x_deg", "target_y_deg", "target_eccentricity_deg", "median_qc_error_x_deg",
        "median_qc_error_y_deg", "median_qc_omae_deg", "median_qc_precision_rms_deg",
    ]
    target_labels = {
        "qc_session_observations": "QC-retained Sessions (count)",
        "qc_subject_count": "QC-retained Subjects (count)",
        "qc_retained_samples": "QC-retained Samples (count)",
        "qc_excluded_samples": "QC-excluded Samples (count)",
        "target_x_pct_display_width": "Target X (% of display width)",
        "target_y_pct_display_height": "Target Y (% of display height)",
        "target_eccentricity_relative_coordinate_pct": "Target Eccentricity (relative coordinate, %)",
        "median_qc_error_x_pct_display_width": "Median QC Error X (% of display width)",
        "median_qc_error_y_pct_display_height": "Median QC Error Y (% of display height; + = up)",
        "median_qc_omae_relative_coordinate_pct": "Median QC OMAE (relative coordinate, %)",
        "median_qc_precision_rms_relative_coordinate_pct": "Median QC Precision RMS (relative coordinate, %)",
        "target_x_deg": "Target X (deg)",
        "target_y_deg": "Target Y (deg)",
        "target_eccentricity_deg": "Target Eccentricity (deg)",
        "median_qc_error_x_deg": "Median QC Error X (deg)",
        "median_qc_error_y_deg": "Median QC Error Y (deg)",
        "median_qc_omae_deg": "Median QC OMAE (deg)",
        "median_qc_precision_rms_deg": "Median QC Precision RMS (deg)",
    }
    target_decimals = {
        "target_x_pct_display_width": 1,
        "target_y_pct_display_height": 1,
        "target_eccentricity_relative_coordinate_pct": 2,
        "median_qc_error_x_pct_display_width": 2,
        "median_qc_error_y_pct_display_height": 2,
        "median_qc_omae_relative_coordinate_pct": 2,
        "median_qc_precision_rms_relative_coordinate_pct": 2,
        "target_x_deg": 3,
        "target_y_deg": 3,
        "target_eccentricity_deg": 3,
        "median_qc_error_x_deg": 3,
        "median_qc_error_y_deg": 3,
        "median_qc_omae_deg": 3,
        "median_qc_precision_rms_deg": 3,
    }
    downloads = _client_delay_downloads(client_delay_evidence, report_path)
    if (report_path.parent / "input_provenance.json").is_file():
        downloads.append(
            (
                "JSON - PROVENANCE",
                "Input file fingerprint",
                "Portable SHA-256 fingerprints for every input file read by this run.",
                "input_provenance.json",
            )
        )
    downloads.extend([
        ("CSV - DISPLAY DATA", "Session metrics with report units", "Percentages used for report tables and session-rate figures.", "report_display_session_metrics.csv"),
        ("CSV - DISPLAY DATA", "Long-term values with report units", "Sampling Hz plus valid and data-loss percentages by date and protocol.", "report_display_long_term.csv"),
        ("CSV - DISPLAY DATA", "Target observations with report units", "Display percentages for coordinates and errors, plus degrees when available.", "report_display_target_visits.csv"),
        ("JSON - UNIT DEFINITIONS", "Display-unit conversion notes", "Machine-readable transformations linking report fields to raw analysis values.", "report_display_units.json"),
        ("CSV - RAW EVIDENCE", "Raw session analysis", "Unmodified source values, including original 0-1 rate proportions.", "combined_results.csv"),
        ("CSV - RAW EVIDENCE", "Raw target-visit analysis", "Unmodified normalised and degree target metrics.", "target_visit_summary.csv"),
        ("JSON - PROVENANCE", "Run manifest", "Version, thresholds, generated timestamp and provenance digest.", "run_manifest.json"),
    ])
    download_html = "".join(
        f"<a class='download' href='{escape(path)}'><span class='format'>{escape(kind)}</span><strong>{escape(title)}</strong><span>{escape(detail)}</span></a>"
        for kind, title, detail, path in downloads
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OpenET 2 Benchmark Report</title>
  <style>
    :root {{ --ink:#17324d; --muted:#61758a; --line:#d9e2ec; --accent:#2878b5; --pale:#eaf4fb; --surface:#fff; }}
    * {{ box-sizing:border-box; }} html {{ scroll-behavior:smooth; }}
    body {{ margin:0; color:#1f2933; background:#f5f8fb; font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
    header {{ color:#fff; background:linear-gradient(120deg,#17324d,#2878b5); }}
    .wrap {{ width:min(1280px,92vw); margin:auto; }} header .wrap {{ padding:38px 0 26px; }}
    .eyebrow {{ margin:0 0 7px; font-size:12px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; opacity:.8; }}
    h1 {{ margin:0; font-size:clamp(30px,4vw,44px); line-height:1.12; }} header p {{ max-width:760px; margin:10px 0 0; color:#e5f2fc; }}
    nav {{ display:flex; flex-wrap:wrap; gap:17px; margin-top:20px; }} nav a {{ color:#fff; text-decoration:none; font-size:13px; font-weight:650; }} nav a:hover {{ text-decoration:underline; }}
    main {{ width:min(1280px,92vw); margin:28px auto 60px; }} section {{ scroll-margin-top:20px; }} section+section {{ margin-top:38px; }}
    .heading {{ display:flex; justify-content:space-between; align-items:baseline; gap:16px; margin-bottom:13px; }} h2 {{ margin:0; color:var(--ink); font-size:24px; }} h3 {{ margin:0 0 7px; color:var(--ink); font-size:16px; }} .heading p,.note {{ margin:0; color:var(--muted); }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(185px,1fr)); gap:13px; }} .card,.panel,figure,.table-wrap,.download,.boundary {{ background:var(--surface); border:1px solid var(--line); border-radius:13px; box-shadow:0 3px 12px #17324d0d; }}
    .card {{ min-height:112px; padding:16px; }} .card span {{ display:block; color:var(--muted); font-size:12px; font-weight:650; }} .card strong {{ display:block; margin-top:8px; color:var(--ink); font-size:24px; line-height:1.1; }}
    .panels {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; margin-top:16px; }} .panel {{ padding:17px; background:var(--pale); border-color:#cfe3f1; }} .panel p,.panel ul {{ margin:0; color:#294a68; }} .panel ul {{ margin-top:9px; padding-left:20px; }} .panel li+li {{ margin-top:5px; }}
    .evidence-status {{ display:grid; grid-template-columns:minmax(260px,.78fr) minmax(320px,1.22fr); gap:20px; margin-top:16px; padding:18px; border:1px solid var(--line); border-radius:13px; box-shadow:0 3px 12px #17324d0d; }} .evidence-status h2 {{ margin:0 0 6px; font-size:21px; }} .evidence-status p {{ margin:0; }} .evidence-status ul {{ margin:0; padding-left:19px; }} .evidence-status li+li {{ margin-top:5px; }} .status-descriptive {{ background:#fff6e8; border-color:#efc77d; color:#6c4813; }} .status-synthetic {{ background:#edf2ff; border-color:#9ab4ed; color:#273d79; }} .status-conditional {{ background:#fff8e6; border-color:#e7cf87; color:#624e19; }} .status-ready {{ background:#edf8f0; border-color:#a4d3ae; color:#245b32; }}
    .result-banner {{ display:grid; grid-template-columns:minmax(145px,.35fr) 1fr; gap:18px; align-items:center; margin:16px 0; padding:18px; background:#edf7ef; border:1px solid #bcdcc4; border-radius:13px; }} .result-value {{ color:#126c35; font-size:31px; font-weight:750; line-height:1; }} .result-value small {{ display:block; margin-top:7px; color:#487058; font-size:11px; font-weight:650; text-transform:uppercase; letter-spacing:.06em; }} .result-banner p {{ margin:0; color:#31523e; }} .selected-row td {{ background:#f1f9f3; }} .pill {{ display:inline-block; padding:2px 7px; color:#126c35; background:#dff2e3; border-radius:999px; font-size:11px; font-weight:750; }} .delay-evidence h3 {{ margin-top:19px; }} .delay-evidence .decision-panel {{ align-self:stretch; }}
    .figures {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(390px,1fr)); gap:17px; }} figure {{ margin:0; padding:11px; }} figure img {{ display:block; width:100%; border-radius:7px; }} figcaption {{ padding:8px 3px 1px; color:var(--muted); font-size:12.5px; }}
    .table-wrap {{ overflow:auto; }} table {{ width:100%; min-width:840px; border-collapse:collapse; font-size:13px; }} th,td {{ padding:9px 11px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; white-space:nowrap; }} th {{ color:var(--ink); background:#edf4fa; font-size:12px; position:sticky; top:0; }} tr:last-child td {{ border-bottom:0; }} td:last-child {{ min-width:170px; white-space:normal; }} .empty {{ padding:17px; color:var(--muted); background:#fff; border:1px solid var(--line); border-radius:13px; }}
    .downloads {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(245px,1fr)); gap:13px; }} .download {{ min-height:118px; padding:16px; color:inherit; text-decoration:none; transition:transform .14s ease,border-color .14s ease; }} .download:hover {{ color:inherit; border-color:#7cb7dc; transform:translateY(-2px); }} .download strong,.download span {{ display:block; }} .download strong {{ margin-top:5px; color:var(--ink); }} .download span:last-child {{ margin-top:5px; color:var(--muted); font-size:12.5px; }} .format {{ color:#226592; font-size:10px; font-weight:750; letter-spacing:.08em; }}
    .boundary {{ padding:17px; }} .boundary ul {{ margin:0; padding-left:21px; }} .boundary li+li {{ margin-top:7px; }} footer {{ margin-top:34px; padding-top:17px; color:var(--muted); font-size:12.5px; border-top:1px solid var(--line); }} code {{ padding:1px 4px; background:#dcecf8; border-radius:4px; }}
    @media(max-width:680px) {{ .heading {{ display:block; }} .heading p {{ margin-top:5px; }} .figures {{ grid-template-columns:1fr; }} .wrap,main {{ width:94vw; }} }}
  </style>
</head>
<body>
<header><div class="wrap"><p class="eyebrow">OpenET 2 · final evidence report</p><h1>Remote Eye-Tracking Benchmark</h1><p>{escape(header_scope.capitalize())} with display-referenced units and auditable data.</p><nav><a href="#overview">Overview</a><a href="#evidence-status">Evidence status</a>{delay_nav}<a href="#figures">Figures</a><a href="#long-term">{escape(long_term_nav_label)}</a><a href="#targets">Targets</a><a href="#downloads">Data</a><a href="#boundaries">Boundaries</a></nav></div></header>
<main>
<section id="overview"><div class="heading"><h2>Evidence overview</h2><p>All presentation values are derived from the generated analysis exports.</p></div><div class="cards">{card_html}</div>
{evidence_status_html}
<div class="panels"><article class="panel"><h3>Report display units</h3><p>Sampling is in Hz; rates use percent rather than raw 0–1 proportions.</p><ul><li><code>valid_gaze_samples_pct = valid_rate × 100</code></li><li><code>data_loss_pct = data_loss_rate × 100</code></li><li>{escape(target_note)}</li></ul></article><article class="panel"><h3>Traceability</h3><p>Raw analysis CSV/JSON files remain unchanged. The report adds explicitly named display tables solely to match its figures and tables.</p><ul><li>Degree fields stay blank without physical geometry.</li><li>Thresholds flag review items; they do not delete source samples.</li></ul></article></div></section>
{delay_section}
<section id="figures"><div class="heading"><h2>Benchmark visualisations</h2><p>Only figures with interpretable axes are retained in the final report.</p></div><div class="figures">{figure_cards}</div></section>
<section id="long-term"><div class="heading"><h2>{escape(long_term_title)}</h2><p>{escape(long_term_description)}</p></div>{_html_table(long_term_display, long_columns, long_labels, long_decimals)}</section>
<section id="repeatability"><div class="heading"><h2>Within-participant repeatability</h2><p>Shown only for genuinely repeated participant, device and protocol groups.</p></div>{_html_table(repeatability_display, repeat_columns, repeat_labels, rate_decimals)}</section>
<section id="criteria"><div class="heading"><h2>Reference-paper criteria and applicability</h2><p>Reference checks are applied only when the recorded measurements and units support them.</p></div>{_html_table(paper_criteria, ["reference_item", "paper_criterion", "current_application", "status"])}</section>
<section id="targets"><div class="heading"><h2>QC-retained target summary by date</h2><p>Only paper-plot-eligible observations appear here; the downloadable target table preserves every inclusion and exclusion status.</p></div>{_html_table(target_display, target_columns, target_labels, target_decimals)}</section>
<section id="sessions"><div class="heading"><h2>Session quality review</h2><p>Each review link opens the generated session-level timing and gaze diagnostic.</p></div>{_session_review_table(session_display, session_columns, report_path.parent / "sessions", session_labels, rate_decimals)}</section>
<section id="downloads"><div class="heading"><h2>Auditable data downloads</h2><p>Presentation-layer tables and unmodified raw analysis files are both available.</p></div><div class="downloads">{download_html}</div></section>
<section id="boundaries"><div class="heading"><h2>Interpretation boundaries</h2><p>These statements preserve the limits of the supplied measurements.</p></div><div class="boundary"><ul><li>Percent display fields are deterministic conversions, not recalibrated measurements.</li><li>Normalised screen-coordinate percentages are display-relative quantities, not visual degrees or pixel distances.</li><li>Visual-angle conclusions require recorded display dimensions and viewing distance; assumed-FOV delay scores are explicitly labelled approximate.</li><li>Date-level changes are descriptive unless participants, devices and protocols are genuinely matched.</li><li>QC exclusions are recorded in exports; this report does not silently impute or delete source values.</li></ul></div></section>
<footer>OpenET 2 final report · Display-unit definitions: <a href="report_display_units.json">report_display_units.json</a>.</footer>
</main></body></html>"""
    report_path.write_text(html, encoding="utf-8")
    return report_path
