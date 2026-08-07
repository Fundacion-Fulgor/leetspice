import json
from pathlib import Path

from leetspice.challenge_catalog import _read_package
from leetspice.judge.profile import ProfileJudge
from leetspice.judge.validator import validate_netlist

CHALLENGES = Path(__file__).parents[1] / "challenges"
REQUIRED_TRACKS = {
    "MOS Foundations",
    "Gain Stages",
    "Biasing",
    "Differential",
    "Op Amps",
    "Dynamic Circuits",
    "References",
    "Physical Design",
    "Capstones",
}


def test_challenge_library_is_complete_and_valid() -> None:
    packages = sorted(CHALLENGES.glob("*/challenge.json"))
    assert len(packages) == 31
    tracks = set()
    slugs = set()
    for source in packages:
        slug, values = _read_package(source.parent)
        manifest = json.loads(source.read_text(encoding="utf-8"))
        assert slug not in slugs
        slugs.add(slug)
        tracks.add(values["track"])
        assert values["title"]
        assert values["description"]
        assert values["verification_version"] >= 1
        if values["submission_kind"] == "netlist":
            validate_netlist(
                values["starter_netlist"], values["expected_subckt"], values["expected_pins"]
            )
            if values["judge_backend"] == "characterization":
                assert (source.parent / manifest["judge_config"]["definition"]).is_file()
                assert (source.parent / "judge/reference.spice").is_file()
        else:
            reference = source.parent / manifest["judge_config"]["reference_netlist"]
            assert reference.is_file()
    assert tracks == REQUIRED_TRACKS


def test_profile_starters_pass_their_profile() -> None:
    judge = ProfileJudge()
    for source in sorted(CHALLENGES.glob("*/challenge.json")):
        _, values = _read_package(source.parent)
        if values["judge_backend"] != "profile":
            continue
        result = judge.judge(
            values["starter_netlist"],
            values["expected_subckt"],
            values["expected_pins"],
            values["judge_config"],
        )
        assert result.accepted, f"{source.parent.name}: {result.message}"


def test_private_layout_references_are_not_public_assets() -> None:
    for source in sorted(CHALLENGES.glob("*/challenge.json")):
        manifest = json.loads(source.read_text(encoding="utf-8"))
        if manifest["submission"]["kind"] != "gds":
            continue
        public_paths = {asset["path"] for asset in manifest.get("assets", [])}
        assert manifest["judge_config"]["reference_netlist"] not in public_paths
