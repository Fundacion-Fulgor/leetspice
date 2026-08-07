#!/usr/bin/env python3
"""Run one challenge's private reference, starter, and behavioral negatives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path

from leetspice.judge.characterization import CharacterizationJudge


def run_case(
    judge: CharacterizationJudge,
    package: Path,
    manifest: dict[str, object],
    path: Path,
) -> dict[str, object]:
    source = path.read_text(encoding="utf-8")
    interface = manifest["interface"]
    assert isinstance(interface, dict)
    config = manifest["judge_config"]
    assert isinstance(config, dict)
    started = time.monotonic()
    result = judge.judge(
        source,
        str(interface["subckt"]),
        list(interface["pins"]),
        package.name,
        config,
    )
    return {
        "file": str(path.relative_to(package)),
        "sha256": hashlib.sha256(source.encode()).hexdigest(),
        "accepted": result.accepted,
        "score": result.score,
        "message": result.message,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "measurements": [measurement.to_dict() for measurement in result.measurements],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("--challenges", type=Path, default=Path("challenges"))
    parser.add_argument(
        "--pdk-root", type=Path, default=Path(os.getenv("PDK_ROOT", "/opt/IHP-Open-PDK"))
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    package = (args.challenges / args.slug).resolve()
    manifest = json.loads((package / "challenge.json").read_text(encoding="utf-8"))
    if manifest.get("judge_backend") != "characterization":
        raise SystemExit("qualification runner currently supports characterization challenges only")
    judge = CharacterizationJudge(challenges_path=args.challenges, pdk_root=args.pdk_root)
    reference = run_case(judge, package, manifest, package / "judge/reference.spice")
    starter = run_case(judge, package, manifest, package / str(manifest["starter_file"]))
    negatives = [
        run_case(judge, package, manifest, path)
        for path in sorted((package / "judge/negative").glob("*.spice"))
    ] if (package / "judge/negative").is_dir() else []
    version_output = subprocess.run(
        ["ngspice", "--version"], capture_output=True, text=True, check=False
    ).stdout.splitlines()
    version = next((line.strip() for line in version_output if "ngspice-" in line), "unknown")
    report = {
        "challenge": args.slug,
        "verification_version": manifest["verification_version"],
        "python": platform.python_version(),
        "ngspice": version,
        "pdk_root": str(args.pdk_root.resolve()),
        "reference": reference,
        "starter": starter,
        "negatives": negatives,
    }
    valid = reference["accepted"] and all(not item["accepted"] for item in negatives)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
