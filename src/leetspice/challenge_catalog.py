"""Strict manifest loading for challenge packages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Challenge

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$-]*$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BACKENDS = {"characterization", "klayout"}
KINDS = {"netlist", "gds"}
DIFFICULTIES = {"introductory", "intermediate", "advanced", "capstone"}


def _required_string(data: dict[str, Any], name: str, source: Path) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: {name} must be a non-empty string")
    return value.strip()


def _read_package(path: Path) -> tuple[str, dict[str, Any]]:
    source = path / "challenge.json"
    try:
        manifest = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read challenge manifest {source}: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError(f"{source}: manifest must be an object")

    slug = _required_string(manifest, "slug", source)
    if not SLUG.fullmatch(slug):
        raise ValueError(f"{source}: invalid slug {slug!r}")
    title = _required_string(manifest, "title", source)
    summary = _required_string(manifest, "summary", source)
    track = _required_string(manifest, "track", source)
    difficulty = _required_string(manifest, "difficulty", source)
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"{source}: difficulty must be one of {sorted(DIFFICULTIES)}")
    verification_version = manifest.get("verification_version")
    if (
        not isinstance(verification_version, int)
        or isinstance(verification_version, bool)
        or verification_version < 1
    ):
        raise ValueError(f"{source}: verification_version must be a positive integer")
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        raise ValueError(f"{source}: interface must be an object")
    expected_subckt = interface.get("subckt", interface.get("top_cell"))
    pins = interface.get("pins")
    if not isinstance(expected_subckt, str) or not IDENTIFIER.fullmatch(expected_subckt):
        raise ValueError(f"{source}: invalid interface subckt/top_cell")
    if (
        not isinstance(pins, list)
        or not pins
        or not all(isinstance(pin, str) and IDENTIFIER.fullmatch(pin) for pin in pins)
    ):
        raise ValueError(f"{source}: interface pins must be non-empty identifiers")

    submission = manifest.get("submission", {"kind": "netlist"})
    if not isinstance(submission, dict) or submission.get("kind", "netlist") not in KINDS:
        raise ValueError(f"{source}: invalid submission configuration")
    kind = submission.get("kind", "netlist")
    backend = manifest.get("judge_backend")
    if backend not in BACKENDS:
        raise ValueError(f"{source}: judge_backend must be one of {sorted(BACKENDS)}")
    if (kind == "gds") != (backend == "klayout"):
        raise ValueError(f"{source}: GDS submissions require the klayout backend")

    specification = path / _required_string(manifest, "specification_file", source)
    if not specification.is_file():
        raise ValueError(f"{source}: specification file is missing")
    starter = ""
    starter_name = manifest.get("starter_file")
    if starter_name is not None:
        if not isinstance(starter_name, str):
            raise ValueError(f"{source}: starter_file must be a string")
        starter_path = path / starter_name
        if not starter_path.is_file():
            raise ValueError(f"{source}: starter file is missing")
        starter = starter_path.read_text(encoding="utf-8")

    assets = manifest.get("assets", [])
    judge_config = manifest.get("judge_config", {})
    if not isinstance(assets, list) or not isinstance(judge_config, dict):
        raise ValueError(f"{source}: assets and judge_config must have valid types")
    if backend == "klayout":
        reference = judge_config.get("reference_netlist")
        if not isinstance(reference, str) or not (path / reference).is_file():
            raise ValueError(f"{source}: private LVS reference is missing")
        post_layout = judge_config.get("post_layout_definition")
        if not isinstance(post_layout, str) or not (path / post_layout).is_file():
            raise ValueError(f"{source}: private post-layout definition is missing")
    if backend == "characterization":
        definition = judge_config.get("definition")
        if not isinstance(definition, str) or not (path / definition).is_file():
            raise ValueError(f"{source}: characterization definition is missing")

    return slug, {
        "title": title,
        "summary": summary,
        "description": specification.read_text(encoding="utf-8"),
        "expected_subckt": expected_subckt,
        "expected_pins": pins,
        "starter_netlist": starter,
        "submission_kind": kind,
        "judge_backend": backend,
        "submission_config": {
            "maximum_bytes": int(submission.get("maximum_bytes", 8 * 1024 * 1024)),
            "extensions": submission.get("extensions", [".gds"] if kind == "gds" else []),
        },
        "judge_config": judge_config,
        "fixture_path": path.name,
        "category": str(manifest.get("category", track)),
        "track": track,
        "difficulty": difficulty,
        "verification_version": verification_version,
        "assets": assets,
        "score_unit": str(manifest.get("score_unit", "points")),
        "lower_is_better": bool(manifest.get("lower_is_better", False)),
        "is_active": bool(manifest.get("is_active", True)),
    }


def seed_challenges(session: Session, challenges_path: str | Path) -> None:
    """Validate and upsert every challenge package."""

    root = Path(challenges_path)
    if not root.is_dir():
        raise ValueError(f"challenge root does not exist: {root}")
    packages = [_read_package(path) for path in sorted(root.iterdir()) if path.is_dir()]
    slugs = [slug for slug, _ in packages]
    if len(slugs) != len(set(slugs)):
        raise ValueError("challenge manifests contain duplicate slugs")
    for slug, values in packages:
        challenge = session.scalar(select(Challenge).where(Challenge.slug == slug))
        if challenge is None:
            session.add(Challenge(slug=slug, **values))
        else:
            for name, value in values.items():
                setattr(challenge, name, value)
    session.commit()
