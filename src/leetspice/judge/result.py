"""Judge result values shared by all backends."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Measurement:
    """One named quantity produced by a judge backend."""

    name: str
    value: float
    unit: str = ""
    passed: bool = True
    conditions: dict[str, str | float | int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """Portable result which can be stored directly in a JSON column."""

    accepted: bool
    score: float
    measurements: tuple[Measurement, ...] = field(default_factory=tuple)
    message: str = ""
    # Optional structured diagnostics (e.g. per-rule DRC violations) for the UI.
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "accepted": self.accepted,
            "score": self.score,
            "measurements": [measurement.to_dict() for measurement in self.measurements],
            "message": self.message,
        }
        if self.details:
            data["details"] = self.details
        return data
