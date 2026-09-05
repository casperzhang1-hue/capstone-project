"""Adapt supplied device helpers to portable workflows."""

from __future__ import annotations

import importlib.util
import inspect
import os
import queue
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any


_SESSION_FOLDER_LOCK = threading.Lock()


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def load_legacy_module(code_root: Path, module_name: str) -> ModuleType:
    """Load one original OpenET module without hard-coding a lab path."""

    path = code_root.resolve() / f"{module_name}.py"
    if not path.exists():
        raise FileNotFoundError(f"Original OpenET module not found: {path}")
    qualified_name = f"openet2_legacy_{module_name}_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(qualified_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load original OpenET module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(path.parent))
        except ValueError:
            pass
    return module


def create_session_folder(code_root: Path, output_root: Path) -> Path:
    """Create a session folder through the supplied legacy helper."""

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    module = load_legacy_module(code_root, "create_data_folder")
    creator = module.create_data_folder
    with _SESSION_FOLDER_LOCK:
        before = {path.resolve() for path in output_root.glob("????_??_??/*") if path.is_dir()}
        parameters = inspect.signature(creator).parameters
        if parameters:
            result = creator(output_root)
        else:
            with _working_directory(output_root):
                result = creator()
        if result is not None:
            result_path = Path(result)
            if not result_path.is_absolute():
                result_path = output_root / result_path
            if result_path.exists():
                return result_path.resolve()

        after = {path.resolve() for path in output_root.glob("????_??_??/*") if path.is_dir()}
        created = sorted(after - before, key=lambda path: (path.stat().st_mtime_ns, path.name))
        if created:
            return created[-1]
    raise RuntimeError("Original OpenET folder creator did not create or return a session folder")


class LegacyGP3Adapter:
    """Lifecycle adapter around the original ``GP3_helpers.py`` protocol code."""

    def __init__(self, helpers: Any, manage_gazepoint_control: bool = True) -> None:
        """Initialise the GP3 adapter."""

        self.helpers = helpers
        self.manage_gazepoint_control = manage_gazepoint_control
        self.socket = None
        self.started = False

    @classmethod
    def from_code_root(
        cls,
        code_root: Path,
        manage_gazepoint_control: bool = True,
    ) -> "LegacyGP3Adapter":
        """Build a GP3 adapter from a legacy code directory."""

        return cls(load_legacy_module(code_root, "GP3_helpers"), manage_gazepoint_control)

    def start(self) -> None:
        """Start the GP3 connection."""

        if self.started:
            return
        if self.manage_gazepoint_control:
            self.helpers.GazePoint_control(True)
        try:
            self.socket = self.helpers.connect_to_GP3HD()
            self.started = True
        except Exception:
            if self.manage_gazepoint_control:
                self.helpers.GazePoint_control(False)
            raise

    def read_sample(self) -> dict[str, object]:
        """Read one GP3 gaze sample."""

        if not self.started or self.socket is None:
            raise RuntimeError("GP3 adapter has not been started")
        fpogx, fpogy, fpogv, cx, cy = self.helpers.receive_data_from_GP3HD(self.socket)
        return {"FPOGX": fpogx, "FPOGY": fpogy, "FPOGV": fpogv, "CX": cx, "CY": cy}

    def stop(self) -> None:
        """Stop the GP3 connection."""

        socket = self.socket
        self.socket = None
        self.started = False
        try:
            if socket is not None:
                socket.close()
        finally:
            if self.manage_gazepoint_control:
                self.helpers.GazePoint_control(False)


class LegacyTobiiAdapter:
    """Adapt the supplied Tobii helper to a managed sample queue."""

    def __init__(self, helpers: Any) -> None:
        """Initialise the Tobii adapter."""

        self.helpers = helpers
        self.tracker = None
        self.samples: queue.Queue[dict[str, object]] = queue.Queue()
        self.started = False

    @classmethod
    def from_code_root(cls, code_root: Path) -> "LegacyTobiiAdapter":
        """Build a Tobii adapter from a legacy code directory."""

        return cls(load_legacy_module(code_root, "tobii_helpers"))

    def _callback(self, gaze_data: dict[str, Any]) -> None:
        """Queue one normalised Tobii gaze sample."""

        left = gaze_data.get("left_gaze_point_on_display_area", (float("nan"), float("nan")))
        right = gaze_data.get("right_gaze_point_on_display_area", (float("nan"), float("nan")))
        left_valid = bool(gaze_data.get("left_gaze_point_validity", True))
        right_valid = bool(gaze_data.get("right_gaze_point_validity", True))
        valid_points = [point for point, valid in ((left, left_valid), (right, right_valid)) if valid]
        if valid_points:
            gaze_x = sum(float(point[0]) for point in valid_points) / len(valid_points)
            gaze_y = sum(float(point[1]) for point in valid_points) / len(valid_points)
            valid = 1
        else:
            gaze_x = gaze_y = float("nan")
            valid = 0
        self.samples.put(
            {
                "system_time_us": gaze_data.get("system_time_stamp"),
                "device_time_us": gaze_data.get("device_time_stamp"),
                "gaze_x": gaze_x,
                "gaze_y": gaze_y,
                "valid": valid,
                "left_gaze_x": left[0],
                "left_gaze_y": left[1],
                "right_gaze_x": right[0],
                "right_gaze_y": right[1],
            }
        )

    def start(self) -> None:
        """Start the Tobii subscription."""

        if self.started:
            return
        tracker = self.helpers.init_tobii_eyetracker()
        if not tracker:
            raise RuntimeError("No Tobii eye tracker was discovered")
        tracker.subscribe_to(self.helpers.tr.EYETRACKER_GAZE_DATA, self._callback, as_dictionary=True)
        self.tracker = tracker
        self.started = True

    def read_sample(self, timeout_s: float = 1.0) -> dict[str, object]:
        """Read one queued Tobii gaze sample."""

        if not self.started:
            raise RuntimeError("Tobii adapter has not been started")
        try:
            return self.samples.get(timeout=timeout_s)
        except queue.Empty as error:
            raise TimeoutError("Timed out waiting for Tobii gaze data") from error

    def stop(self) -> None:
        """Stop the Tobii subscription."""

        tracker = self.tracker
        self.tracker = None
        self.started = False
        if tracker is not None:
            tracker.unsubscribe_from(self.helpers.tr.EYETRACKER_GAZE_DATA, self._callback)
        while not self.samples.empty():
            try:
                self.samples.get_nowait()
            except queue.Empty:
                break
