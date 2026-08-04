"""Perform lightweight structural validation of a LeetSpice challenge fixture."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = {
    "schema_version",
    "slug",
    "title",
    "summary",
    "starter_file",
    "specification_file",
    "circuit",
    "checks",
}


def fail(message: str) -> None:
    raise ValueError(message)


def local_file(base: Path, value: object, field: str) -> Path:
    if not isinstance(value, str) or not value:
        fail(f"{field} must be a non-empty string")
    candidate = (base / value).resolve()
    if candidate.parent != base.resolve():
        fail(f"{field} must name a file in the challenge directory")
    if not candidate.is_file():
        fail(f"{field} does not exist: {value}")
    return candidate


def validate(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(str(exc))

    if not isinstance(data, dict):
        fail("fixture root must be a JSON object")
    missing = sorted(REQUIRED_FIELDS - data.keys())
    if missing:
        fail(f"missing required fields: {', '.join(missing)}")
    if data["schema_version"] != 1:
        fail("unsupported schema_version; expected 1")
    if not isinstance(data["checks"], list) or not data["checks"]:
        fail("checks must be a non-empty array")

    local_file(path.parent, data["starter_file"], "starter_file")
    local_file(path.parent, data["specification_file"], "specification_file")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} CHALLENGE.json", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        validate(path)
    except ValueError as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 1
    print(f"{path}: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
