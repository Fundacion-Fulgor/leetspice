"""Generate the built-in LeetSpice challenge package library."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "challenges"

ELECTRICAL = [
    (
        "mos-operating-point",
        "MOS Operating Point",
        "MOS Foundations",
        "introductory",
        "mos_op",
        "device",
        ["d", "g", "s", "b"],
        "XMN d g s b sg13_lv_nmos W=1u L=0.13u ng=1 m=1",
    ),
    (
        "mos-gmid",
        "MOS gm/ID Explorer",
        "MOS Foundations",
        "introductory",
        "mos_gmid",
        "device",
        ["d", "g", "s", "b"],
        "XMN d g s b sg13_lv_nmos W=2u L=0.26u ng=1 m=1",
    ),
    (
        "source-follower",
        "Source Follower",
        "MOS Foundations",
        "introductory",
        "source_follower",
        "source_follower",
        ["in", "out", "vdd", "vss"],
        "XMN vdd in out vss sg13_lv_nmos W=4u L=0.26u ng=1 m=1\nRBIAS out vss 20k",
    ),
    (
        "common-source",
        "Common-Source Amplifier",
        "Gain Stages",
        "intermediate",
        "common_source",
        "amplifier",
        ["in", "out", "vdd", "vss"],
        "XMN out in vss vss sg13_lv_nmos W=4u L=0.26u ng=1 m=1\nRLOAD vdd out 20k",
    ),
    (
        "common-gate",
        "Common-Gate Amplifier",
        "Gain Stages",
        "intermediate",
        "common_gate",
        "amplifier_bias",
        ["in", "out", "bias", "vdd", "vss"],
        "XMN out bias in vss sg13_lv_nmos W=4u L=0.26u ng=1 m=1\nRLOAD vdd out 20k",
    ),
    (
        "cascode-gain-stage",
        "Cascode Gain Stage",
        "Gain Stages",
        "intermediate",
        "cascode",
        "amplifier_bias",
        ["in", "out", "bias", "vdd", "vss"],
        "XIN mid in vss vss sg13_lv_nmos W=4u L=0.26u ng=1 m=1\nXCAS out bias mid vss sg13_lv_nmos W=4u L=0.26u ng=1 m=1\nRLOAD vdd out 30k",
    ),
    (
        "basic-current-mirror",
        "Basic Current Mirror",
        "Biasing",
        "introductory",
        "basic_mirror",
        "mirror",
        ["iref", "out", "vss"],
        "XREF iref iref vss vss sg13_lv_nmos W=2u L=0.5u ng=1 m=1\nXOUT out iref vss vss sg13_lv_nmos W=2u L=0.5u ng=1 m=1",
    ),
    (
        "cascode-current-mirror",
        "Cascode Current Mirror",
        "Biasing",
        "intermediate",
        "cascode_mirror",
        "mirror",
        ["iref", "out", "vss"],
        "XREF iref iref vss vss sg13_lv_nmos W=2u L=0.5u ng=1 m=1\nXBIAS bias iref vss vss sg13_lv_nmos W=2u L=0.5u ng=1 m=1\nXCAS out bias mid vss sg13_lv_nmos W=2u L=0.5u ng=1 m=1\nXOUT mid iref vss vss sg13_lv_nmos W=2u L=0.5u ng=1 m=1",
    ),
    (
        "supply-independent-bias",
        "Supply-Independent Bias",
        "References",
        "advanced",
        "supply_bias",
        "reference_current",
        ["vdd", "vss", "out"],
        "XNP out out vss vss sg13_lv_nmos W=4u L=0.5u ng=1 m=1\nXPP out out vdd vdd sg13_lv_pmos W=8u L=0.5u ng=1 m=1\nRSET out vss 40k",
    ),
    (
        "ptat-current-reference",
        "PTAT Current Reference",
        "References",
        "advanced",
        "ptat",
        "reference_current",
        ["vdd", "vss", "out"],
        "XMN out out vss vss sg13_lv_nmos W=4u L=0.5u ng=1 m=1\nXMP out out vdd vdd sg13_lv_pmos W=8u L=0.5u ng=1 m=1\nRPTAT out vss 30k",
    ),
    (
        "differential-pair",
        "Differential Pair",
        "Differential",
        "intermediate",
        "differential_pair",
        "differential",
        ["inp", "inn", "outp", "outn", "vdd", "vss"],
        "XINP outp inp tail vss sg13_lv_nmos W=4u L=0.5u ng=1 m=1\nXINN outn inn tail vss sg13_lv_nmos W=4u L=0.5u ng=1 m=1\nRTAIL tail vss 10k\nRLP vdd outp 20k\nRLN vdd outn 20k",
    ),
    (
        "active-load-differential-pair",
        "Active-Load Differential Pair",
        "Differential",
        "intermediate",
        "active_load_pair",
        "ota",
        ["inp", "inn", "out", "vdd", "vss"],
        "XINP mirror inp tail vss sg13_lv_nmos W=4u L=0.5u ng=1 m=1\nXINN out inn tail vss sg13_lv_nmos W=4u L=0.5u ng=1 m=1\nXLP mirror mirror vdd vdd sg13_lv_pmos W=8u L=0.5u ng=1 m=1\nXLN out mirror vdd vdd sg13_lv_pmos W=8u L=0.5u ng=1 m=1\nRTAIL tail vss 10k",
    ),
    (
        "five-transistor-ota",
        "Five-Transistor OTA",
        "Differential",
        "advanced",
        "five_transistor_ota",
        "ota",
        ["inp", "inn", "out", "vdd", "vss"],
        "XINP mirror inp tail vss sg13_lv_nmos W=4u L=0.5u ng=1 m=1\nXINN out inn tail vss sg13_lv_nmos W=4u L=0.5u ng=1 m=1\nXLP mirror mirror vdd vdd sg13_lv_pmos W=8u L=0.5u ng=1 m=1\nXLN out mirror vdd vdd sg13_lv_pmos W=8u L=0.5u ng=1 m=1\nXTAIL tail bias vss vss sg13_lv_nmos W=8u L=0.5u ng=1 m=1\nRBIAS vdd bias 30k",
    ),
    (
        "one-stage-op-amp",
        "One-Stage Operational Amplifier",
        "Op Amps",
        "advanced",
        "one_stage_opamp",
        "ota",
        ["inp", "inn", "out", "vdd", "vss"],
        "XINP mirror inp tail vss sg13_lv_nmos W=6u L=0.5u ng=1 m=1\nXINN out inn tail vss sg13_lv_nmos W=6u L=0.5u ng=1 m=1\nXLP mirror mirror vdd vdd sg13_lv_pmos W=12u L=0.5u ng=1 m=1\nXLN out mirror vdd vdd sg13_lv_pmos W=12u L=0.5u ng=1 m=1\nRTAIL tail vss 8k",
    ),
    (
        "folded-cascode-op-amp",
        "Folded-Cascode Op Amp",
        "Op Amps",
        "advanced",
        "folded_cascode",
        "complex_opamp",
        ["inp", "inn", "out", "vdd", "vss"],
        "XINP np inp tail vss sg13_lv_nmos W=6u L=0.5u ng=1 m=1\nXINN nn inn tail vss sg13_lv_nmos W=6u L=0.5u ng=1 m=1\nXFP foldp np vdd vdd sg13_lv_pmos W=10u L=0.5u ng=1 m=1\nXFN out nn vdd vdd sg13_lv_pmos W=10u L=0.5u ng=1 m=1\nXCP out bias foldp vss sg13_lv_nmos W=6u L=0.5u ng=1 m=1\nXTAIL tail bias vss vss sg13_lv_nmos W=10u L=0.5u ng=1 m=1\nRBIAS vdd bias 30k",
    ),
    (
        "two-stage-op-amp",
        "Two-Stage Miller Op Amp",
        "Op Amps",
        "advanced",
        "two_stage_opamp",
        "complex_opamp",
        ["inp", "inn", "out", "vdd", "vss"],
        "XINP n1 inp tail vss sg13_lv_nmos W=6u L=0.5u ng=1 m=1\nXINN first inn tail vss sg13_lv_nmos W=6u L=0.5u ng=1 m=1\nXLP n1 n1 vdd vdd sg13_lv_pmos W=12u L=0.5u ng=1 m=1\nXLN first n1 vdd vdd sg13_lv_pmos W=12u L=0.5u ng=1 m=1\nXSECOND out first vss vss sg13_lv_nmos W=20u L=0.5u ng=1 m=1\nRLOAD vdd out 20k\nRTAIL tail vss 8k\nCC first out 1p",
    ),
    (
        "common-mode-feedback",
        "Common-Mode Feedback",
        "Op Amps",
        "advanced",
        "cmfb",
        "cmfb",
        ["outp", "outn", "vcm", "ctrl", "vdd", "vss"],
        "RSP outp sense 20k\nRSN outn sense 20k\nXERR ctrl sense vss vss sg13_lv_nmos W=6u L=0.5u ng=1 m=1\nRREF vcm ctrl 20k\nXLOAD ctrl ctrl vdd vdd sg13_lv_pmos W=4u L=0.5u ng=1 m=1",
    ),
    (
        "mos-sampler",
        "CMOS Sampler",
        "Dynamic Circuits",
        "intermediate",
        "sampler",
        "sampler",
        ["in", "out", "clk", "vdd", "vss"],
        "XNS out clk in vss sg13_lv_nmos W=4u L=0.13u ng=1 m=1\nXPS out clkb in vdd sg13_lv_pmos W=8u L=0.13u ng=1 m=1\nXINV clkb clk vss vss sg13_lv_nmos W=1u L=0.13u ng=1 m=1\nXINVP clkb clk vdd vdd sg13_lv_pmos W=2u L=0.13u ng=1 m=1\nCHOLD out vss 100f",
    ),
    (
        "ring-oscillator",
        "Ring Oscillator",
        "Dynamic Circuits",
        "intermediate",
        "ring_oscillator",
        "oscillator",
        ["out", "vdd", "vss"],
        "X1 n1 out vss vss sg13_lv_nmos W=1u L=0.13u ng=1 m=1\nX1P n1 out vdd vdd sg13_lv_pmos W=2u L=0.13u ng=1 m=1\nX2 n2 n1 vss vss sg13_lv_nmos W=1u L=0.13u ng=1 m=1\nX2P n2 n1 vdd vdd sg13_lv_pmos W=2u L=0.13u ng=1 m=1\nX3 out n2 vss vss sg13_lv_nmos W=1u L=0.13u ng=1 m=1\nX3P out n2 vdd vdd sg13_lv_pmos W=2u L=0.13u ng=1 m=1",
    ),
    (
        "current-starved-vco",
        "Current-Starved VCO",
        "Dynamic Circuits",
        "advanced",
        "vco",
        "oscillator_control",
        ["vctrl", "out", "vdd", "vss"],
        "XSTARVE n1 vctrl vss vss sg13_lv_nmos W=2u L=0.26u ng=1 m=1\nX1 n2 out n1 vss sg13_lv_nmos W=1u L=0.13u ng=1 m=1\nX1P n2 out vdd vdd sg13_lv_pmos W=2u L=0.13u ng=1 m=1\nX2 n3 n2 n1 vss sg13_lv_nmos W=1u L=0.13u ng=1 m=1\nX2P n3 n2 vdd vdd sg13_lv_pmos W=2u L=0.13u ng=1 m=1\nX3 out n3 n1 vss sg13_lv_nmos W=1u L=0.13u ng=1 m=1\nX3P out n3 vdd vdd sg13_lv_pmos W=2u L=0.13u ng=1 m=1",
    ),
    (
        "charge-pump",
        "Matched Charge Pump",
        "Dynamic Circuits",
        "advanced",
        "charge_pump",
        "charge_pump",
        ["up", "dn", "out", "vdd", "vss"],
        "XUP out up vdd vdd sg13_lv_pmos W=8u L=0.5u ng=1 m=1\nXDN out dn vss vss sg13_lv_nmos W=4u L=0.5u ng=1 m=1\nCOUT out vss 200f",
    ),
    (
        "bandgap-reference",
        "Bandgap Reference",
        "References",
        "capstone",
        "bandgap",
        "reference_voltage",
        ["vdd", "vss", "vref"],
        "XMN vref vref vss vss sg13_lv_nmos W=8u L=0.5u ng=1 m=1\nXMP vref vref vdd vdd sg13_lv_pmos W=16u L=0.5u ng=1 m=1\nRSET vref vss 20k\nCFILT vref vss 1p",
    ),
    (
        "low-noise-front-end",
        "Low-Noise Front End",
        "Capstones",
        "capstone",
        "low_noise_frontend",
        "amplifier",
        ["in", "out", "vdd", "vss"],
        "XIN out in vss vss sg13_lv_nmos W=40u L=0.5u ng=4 m=1\nXLOAD out out vdd vdd sg13_lv_pmos W=80u L=0.5u ng=4 m=1\nCLOAD out vss 100f",
    ),
    (
        "compensated-op-amp-capstone",
        "Compensated Op Amp Capstone",
        "Capstones",
        "capstone",
        "compensated_opamp",
        "complex_opamp",
        ["inp", "inn", "out", "vdd", "vss"],
        "XINP n1 inp tail vss sg13_lv_nmos W=10u L=0.5u ng=2 m=1\nXINN first inn tail vss sg13_lv_nmos W=10u L=0.5u ng=2 m=1\nXLP n1 n1 vdd vdd sg13_lv_pmos W=20u L=0.5u ng=2 m=1\nXLN first n1 vdd vdd sg13_lv_pmos W=20u L=0.5u ng=2 m=1\nXSECOND out first vss vss sg13_lv_nmos W=30u L=0.5u ng=2 m=1\nRLOAD vdd out 20k\nRTAIL tail vss 5k\nCC first out 2p",
    ),
    (
        "vco-capstone",
        "PVT VCO Capstone",
        "Capstones",
        "capstone",
        "vco_capstone",
        "oscillator_control",
        ["vctrl", "out", "vdd", "vss"],
        "XSTARVE n1 vctrl vss vss sg13_lv_nmos W=4u L=0.26u ng=1 m=1\nX1 n2 out n1 vss sg13_lv_nmos W=2u L=0.13u ng=1 m=1\nX1P n2 out vdd vdd sg13_lv_pmos W=4u L=0.13u ng=1 m=1\nX2 n3 n2 n1 vss sg13_lv_nmos W=2u L=0.13u ng=1 m=1\nX2P n3 n2 vdd vdd sg13_lv_pmos W=4u L=0.13u ng=1 m=1\nX3 out n3 n1 vss sg13_lv_nmos W=2u L=0.13u ng=1 m=1\nX3P out n3 vdd vdd sg13_lv_pmos W=4u L=0.13u ng=1 m=1",
    ),
]

PHYSICAL = [
    (
        "layout-multifinger-mos",
        "Multifinger MOS Layout",
        "multifinger_mos",
        ["d", "g", "s", "b"],
        "M1 d g s b sg13_lv_nmos W=2u L=0.13u ng=4 m=1",
    ),
    (
        "layout-current-mirror",
        "Matched Current Mirror Layout",
        "current_mirror",
        ["iref", "out", "vss"],
        "M1 iref iref vss vss sg13_lv_nmos W=2u L=0.5u ng=2 m=1\nM2 out iref vss vss sg13_lv_nmos W=2u L=0.5u ng=2 m=1",
    ),
    (
        "layout-common-centroid-pair",
        "Common-Centroid Pair Layout",
        "common_centroid_pair",
        ["inp", "inn", "outp", "outn", "tail", "vss"],
        "M1 outp inp tail vss sg13_lv_nmos W=4u L=0.5u ng=4 m=1\nM2 outn inn tail vss sg13_lv_nmos W=4u L=0.5u ng=4 m=1",
    ),
    (
        "layout-five-transistor-ota",
        "Five-Transistor OTA Layout",
        "ota5",
        ["inp", "inn", "out", "bias", "vdd", "vss"],
        "M1 mirror inp tail vss sg13_lv_nmos W=4u L=0.5u ng=2 m=1\nM2 out inn tail vss sg13_lv_nmos W=4u L=0.5u ng=2 m=1\nM3 tail bias vss vss sg13_lv_nmos W=8u L=0.5u ng=4 m=1\nM4 mirror mirror vdd vdd sg13_lv_pmos W=8u L=0.5u ng=4 m=1\nM5 out mirror vdd vdd sg13_lv_pmos W=8u L=0.5u ng=4 m=1",
    ),
]


def xschem_symbol(top: str, pins: list[str]) -> str:
    lines = [
        "v {xschem version=3.4.4 file_version=1.2}",
        "G {}",
        f'K {{type=subcircuit\nformat="@name @pinlist {top}"\ntemplate="name=x1"\n}}',
        "V {}",
        "S {}",
        "E {}",
        "L 4 -40 -40 40 -40 {}",
        "L 4 40 -40 40 40 {}",
        "L 4 40 40 -40 40 {}",
        "L 4 -40 40 -40 -40 {}",
    ]
    for index, pin in enumerate(pins):
        y = -30 + index * (60 / max(len(pins) - 1, 1))
        left = index % 2 == 0
        x1, x2 = (-42.5, -37.5) if left else (37.5, 42.5)
        direction = "in" if pin not in {"out", "outp", "outn", "d"} else "out"
        lines.append(f"B 5 {x1:g} {y - 2.5:g} {x2:g} {y + 2.5:g} {{name={pin} dir={direction}}}")
    return "\n".join(lines) + "\n"


def xschem_schematic(top: str, pins: list[str]) -> str:
    interface = (
        f".subckt {top} {' '.join(pins)}\n* Add the required SG13G2 circuit here.\n.ends {top}"
    )
    return (
        "v {xschem version=3.4.4 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
        'C {devices/code_shown.sym} 0 0 0 0 {name=INTERFACE only_toplevel=true value="\n'
        f"{interface}\n"
        '"}\n'
    )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    for slug, title, track, difficulty, profile, family, pins, body in ELECTRICAL:
        root = ROOT / slug
        summary = f"Design and optimize an IHP SG13G2 {title.lower()} across server-owned checks."
        manifest = {
            "schema_version": 2,
            "slug": slug,
            "title": title,
            "summary": summary,
            "track": track,
            "difficulty": difficulty,
            "verification_version": 1,
            "starter_file": "starter.cir",
            "specification_file": "specification.md",
            "interface": {"subckt": slug.replace("-", "_"), "pins": pins},
            "submission": {"kind": "netlist"},
            "judge_backend": "profile",
            "judge_config": {"profile": profile, "family": family},
            "score_unit": "points",
            "lower_is_better": False,
            "is_active": True,
        }
        subckt = manifest["interface"]["subckt"]
        starter = f".subckt {subckt} {' '.join(pins)}\n{body}\n.ends {subckt}\n"
        spec = (
            f"# {title}\n\n{summary}\n\n"
            f"Submit exactly one `.subckt {subckt} {' '.join(pins)}` using SG13G2 low-voltage MOS devices, resistors, and capacitors. "
            "Server-owned profile checks enforce circuit-family structure, device mix, and sizing bounds. "
            "Fewer devices and smaller total gate width improve score after all hard limits pass.\n"
        )
        write(root / "challenge.json", json.dumps(manifest, indent=2) + "\n")
        write(root / "starter.cir", starter)
        write(root / "specification.md", spec)

    for slug, title, top, pins, devices in PHYSICAL:
        root = ROOT / slug
        manifest = {
            "schema_version": 2,
            "slug": slug,
            "title": title,
            "summary": f"Create a compact DRC-clean, LVS-correct {title.lower()} in SG13G2.",
            "track": "Physical Design",
            "difficulty": "advanced",
            "verification_version": 1,
            "specification_file": "specification.md",
            "interface": {"top_cell": top, "pins": pins},
            "submission": {"kind": "gds", "maximum_bytes": 8388608, "extensions": [".gds"]},
            "judge_backend": "klayout",
            "judge_config": {"reference_netlist": "reference/design.spice", "drc_density": False},
            "assets": [
                {
                    "id": "schematic",
                    "label": "Xschem starter schematic (.sch)",
                    "path": "starter.sch",
                    "download_name": f"{top}.sch",
                },
                {
                    "id": "symbol",
                    "label": "Xschem symbol (.sym)",
                    "path": "starter.sym",
                    "download_name": f"{top}.sym",
                },
            ],
            "score_unit": "points",
            "lower_is_better": False,
            "is_active": True,
        }
        reference = f".subckt {top} {' '.join(pins)}\n{devices}\n.ends {top}\n"
        spec = (
            f"# {title}\n\nSubmit one raw GDSII file with exactly one top cell named `{top}` and labeled pins "
            f"{', '.join(f'`{pin}`' for pin in pins)}. The judge runs the pinned IHP maximal DRC deck without density, "
            "then strict LVS against a private reference. Score is `1000 / bounding-box area in um^2`. "
            "For matching-oriented challenges, DRC/LVS verifies legality and connectivity; geometric common-centroid quality is a documented design objective, not yet a scored proof.\n"
        )
        write(root / "challenge.json", json.dumps(manifest, indent=2) + "\n")
        write(root / "specification.md", spec)
        write(root / "starter.sch", xschem_schematic(top, pins))
        write(root / "starter.sym", xschem_symbol(top, pins))
        write(root / "reference" / "design.spice", reference)


if __name__ == "__main__":
    main()
