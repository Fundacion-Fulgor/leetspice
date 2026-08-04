"""Submission validation and judge backends."""

from .mock import MockJudge
from .ngspice import NgspiceJudge
from .result import JudgeResult, Measurement
from .validator import validate_netlist

__all__ = [
    "JudgeResult",
    "Measurement",
    "MockJudge",
    "NgspiceJudge",
    "validate_netlist",
]
