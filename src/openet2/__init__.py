"""OpenET 2 integrated benchmarking package."""

__version__ = "1.6.0"

from .config import QualityThresholds
from .pipeline import PipelineResult, run_pipeline

__all__ = ["PipelineResult", "QualityThresholds", "run_pipeline"]