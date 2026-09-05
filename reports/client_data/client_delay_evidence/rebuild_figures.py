"""Rebuild client-delay figures from source tables."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse

FOV_X_DEG = 60.0
FOV_Y_DEG = 33.75
SELECTED_DELAY_S = 0.05
CLIENT_CANDIDATES_S = (0.05, 0.10, 0.15)
CONDITION_ORDER = ("Calib & Acc", "Acc 10min", "Acc 60min")
CONDITION_FILES = {
    "Calib & Acc": "condition_calibration.png",
    "Acc 10min": "condition_10min.png",
    "Acc 60min": "condition_60min.png",
}


def _style() -> None:
    """Configure consistent figure styling."""

    plt.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 220,
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.labelsize": 10,
            "axes.edgecolor": "#8aa0b3",
            "axes.facecolor": "#fbfdff",
            "figure.facecolor": "white",
            "grid.color": "#dce5ec",
            "grid.alpha": 0.75,
        }
    )


def _save(figure: plt.Figure, path: Path) -> None:
    """Save and close a figure."""

    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _candidate_figure(
    metrics: pd.DataFrame,
    metric: str,
    ylabel: str,
    title: str,
    output_path: Path,
) -> None:
    """Plot candidate delays for one comparison metric."""

    subset = metrics[
        metrics["condition"].astype(str).eq("ALL")
        & metrics["delay_s"].isin(CLIENT_CANDIDATES_S)
    ].sort_values("delay_s")
    if len(subset) != len(CLIENT_CANDIDATES_S):
        raise ValueError("The three declared client-delay candidates are required")
    x = subset["delay_ms"].to_numpy(dtype=float)
    y = subset[metric].to_numpy(dtype=float)
    colors = ["#168651" if np.isclose(value, 50.0) else "#2878b5" for value in x]
    figure, axis = plt.subplots(figsize=(8.4, 5.1), constrained_layout=True)
    axis.plot(x, y, color="#9bb3c5", linewidth=1.8, zorder=1)
    axis.scatter(x, y, s=125, c=colors, edgecolor="white", linewidth=1.4, zorder=3)
    padding = max(float(np.ptp(y)) * 0.16, 0.006)
    for delay_ms, value in zip(x, y):
        axis.text(delay_ms, value + padding, f"{value:.4f}", ha="center", color="#17324d")
    axis.set_xticks(x)
    axis.set_xticklabels([f"{int(value)} ms\n({value / 1000:.4f} s)" for value in x])
    axis.set_xlabel("Client-requested delay (ms and s)")
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.grid(axis="y")
    axis.set_axisbelow(True)
    axis.text(
        0.01,
        -0.20,
        f"Approximate score based on a fixed {FOV_X_DEG:.2f} x {FOV_Y_DEG:.2f} deg display-FOV grid; not measured visual angle.",
        transform=axis.transAxes,
        color="#61758a",
        fontsize=8,
    )
    _save(figure, output_path)


def _ellipse_parameters(points: np.ndarray) -> tuple[np.ndarray, float, float, float] | None:
    """Return a 95% observation ellipse for two-dimensional points."""

    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
        return None
    covariance = np.cov(points, rowvar=False)
    if covariance.shape != (2, 2) or not np.isfinite(covariance).all():
        return None
    values, vectors = np.linalg.eigh(covariance)
    values = np.maximum(values, 0.0)
    if float(values.max()) <= 0:
        return None
    order = values.argsort()[::-1]
    values = values[order]
    vectors = vectors[:, order]
    angle = float(np.degrees(np.arctan2(vectors[1, 0], vectors[0, 0])))
    width, height = 2.0 * np.sqrt(values * 5.991)
    return points.mean(axis=0), float(width), float(height), angle


def _condition_figure(
    means: pd.DataFrame,
    targets: pd.DataFrame,
    condition: str,
    output_path: Path,
) -> None:
    """Plot retained observations for one test condition."""

    subset = means[
        means["condition"].astype(str).eq(condition)
        & means["visual_qc_status"].astype(str).eq("included")
    ].copy()
    if subset.empty:
        raise ValueError(f"No QC-retained recording-target means for {condition}")
    target_ids = sorted(int(value) for value in targets["target_id"].unique())
    palette = plt.get_cmap("tab10")
    colors = {target_id: palette((target_id - 1) % 10) for target_id in target_ids}
    figure, axis = plt.subplots(figsize=(9.0, 6.3), constrained_layout=True)
    ellipse_count = 0
    for target_id in target_ids:
        target = targets.loc[targets["target_id"].eq(target_id)].iloc[0]
        group = subset[subset["target_id"].eq(target_id)]
        color = colors[target_id]
        axis.scatter(
            group["gaze_x_deg"],
            group["gaze_y_deg"],
            s=25,
            color=color,
            alpha=0.45,
            edgecolor="none",
            zorder=2,
        )
        parameters = _ellipse_parameters(group[["gaze_x_deg", "gaze_y_deg"]].to_numpy(dtype=float))
        if parameters is not None:
            centre, width, height, angle = parameters
            axis.add_patch(
                Ellipse(
                    centre,
                    width,
                    height,
                    angle=angle,
                    fill=False,
                    edgecolor=color,
                    linewidth=1.6,
                    linestyle="--",
                    zorder=3,
                )
            )
            ellipse_count += 1
        axis.scatter(
            [target["target_x_deg"]],
            [target["target_y_deg"]],
            marker="x",
            s=95,
            color="#168651",
            linewidth=2.2,
            zorder=5,
        )
        axis.annotate(
            f"T{target_id}",
            (float(target["target_x_deg"]), float(target["target_y_deg"])),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
            color="#17324d",
        )
    axis.axhline(0, color="#9aa8b4", linewidth=0.9)
    axis.axvline(0, color="#9aa8b4", linewidth=0.9)
    axis.set_xlim(-FOV_X_DEG / 2.0, FOV_X_DEG / 2.0)
    axis.set_ylim(-FOV_Y_DEG / 2.0, FOV_Y_DEG / 2.0)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel(f"Horizontal score on assumed {FOV_X_DEG:.2f} deg display-FOV grid (deg)")
    axis.set_ylabel(f"Vertical score on assumed {FOV_Y_DEG:.2f} deg display-FOV grid (deg)")
    axis.set_title(f"{condition} at selected 50 ms delay")
    axis.grid(True)
    axis.set_axisbelow(True)
    axis.legend(
        handles=[
            Line2D([0], [0], marker="o", color="none", markerfacecolor="#2878b5", alpha=0.55, label="QC-retained recording-target mean"),
            Line2D([0], [0], marker="x", color="#168651", linestyle="none", markersize=8, label="Protocol target"),
            Line2D([0], [0], color="#2878b5", linestyle="--", label="95% observation ellipse"),
        ],
        loc="lower center",
        ncol=3,
        fontsize=8,
        frameon=True,
    )
    axis.text(
        0.01,
        -0.15,
        f"{len(subset)} QC-retained observations and {ellipse_count} target ellipses. Assumed-FOV coordinates are approximate, not physical visual angles.",
        transform=axis.transAxes,
        color="#61758a",
        fontsize=8,
    )
    _save(figure, output_path)


def _coverage_figure(ellipse_master: pd.DataFrame, output_path: Path) -> None:
    """Plot empirical ellipse coverage by condition."""

    groups = [
        pd.to_numeric(
            ellipse_master.loc[ellipse_master["condition"].astype(str).eq(condition), "empirical_coverage"],
            errors="coerce",
        ).dropna().to_numpy(dtype=float)
        * 100.0
        for condition in CONDITION_ORDER
    ]
    if any(len(group) == 0 for group in groups):
        raise ValueError("All three conditions require empirical coverage values")
    figure, axis = plt.subplots(figsize=(8.6, 5.2), constrained_layout=True)
    try:
        boxes = axis.boxplot(groups, tick_labels=CONDITION_ORDER, patch_artist=True, showfliers=True)
    except TypeError:
        boxes = axis.boxplot(groups, labels=CONDITION_ORDER, patch_artist=True, showfliers=True)
    for patch, color in zip(boxes["boxes"], ("#78b7d8", "#9ccf9b", "#e7b26d")):
        patch.set_facecolor(color)
        patch.set_alpha(0.72)
    axis.axhline(95.0, color="#c44e52", linestyle="--", linewidth=1.5, label="Nominal 95%")
    axis.set_ylabel("Raw gaze samples inside fitted ellipse (%)")
    axis.set_xlabel("Test condition")
    axis.set_ylim(80, 101)
    axis.set_title("Post-selection empirical ellipse coverage at 50 ms")
    axis.legend(loc="lower right")
    axis.grid(axis="y")
    axis.set_axisbelow(True)
    axis.text(
        0.01,
        -0.18,
        "Coverage is a percentage and is not part of the client-delay selection score.",
        transform=axis.transAxes,
        color="#61758a",
        fontsize=8,
    )
    _save(figure, output_path)


def main() -> None:
    """Rebuild all client-delay comparison figures."""

    root = Path(__file__).resolve().parent
    data = root / "data"
    figures = root / "figures"
    metrics = pd.read_csv(data / "delay_metrics_accuracy_and_spread.csv")
    targets = pd.read_csv(data / "corrected_target_positions.csv")
    means = pd.read_csv(data / "recording_target_means_delay_0.0500s.csv")
    ellipse_master = pd.read_csv(data / "ellipse_master_delay_0.0500s.csv")
    _style()
    _candidate_figure(
        metrics,
        "balanced_accuracy_deg",
        "Approx. balanced target error (assumed-FOV deg; lower is better)",
        "Client-delay accuracy comparison",
        figures / "delay_accuracy.png",
    )
    _candidate_figure(
        metrics,
        "balanced_repeat_spread_deg",
        "Approx. repeat spread (assumed-FOV deg; lower is better)",
        "Client-delay repeat-spread comparison",
        figures / "delay_spread.png",
    )
    for condition in CONDITION_ORDER:
        _condition_figure(means, targets, condition, figures / CONDITION_FILES[condition])
    _coverage_figure(ellipse_master, figures / "ellipse_coverage.png")


if __name__ == "__main__":
    main()
