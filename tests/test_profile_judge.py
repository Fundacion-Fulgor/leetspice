from leetspice.judge.profile import ProfileJudge


def test_profile_judge_rejects_wrong_device_mix() -> None:
    netlist = """.subckt ota inp inn out vdd vss
X1 out inp vss vss sg13_lv_nmos W=1u L=0.13u
X2 out inn vss vss sg13_lv_nmos W=1u L=0.13u
X3 out inp vss vss sg13_lv_nmos W=1u L=0.13u
X4 out inn vss vss sg13_lv_nmos W=1u L=0.13u
X5 out inp vss vss sg13_lv_nmos W=1u L=0.13u
.ends ota
"""
    result = ProfileJudge().judge(
        netlist, "ota", ["inp", "inn", "out", "vdd", "vss"], {"family": "ota"}
    )
    assert result.accepted is False
    assert next(item for item in result.measurements if item.name == "pmos_count").passed is False


def test_profile_judge_scores_smaller_gate_area_higher() -> None:
    template = """.subckt device d g s b
X1 d g s b sg13_lv_nmos W={width} L=0.13u
.ends device
"""
    judge = ProfileJudge()
    small = judge.judge(
        template.format(width="1u"), "device", ["d", "g", "s", "b"], {"family": "device"}
    )
    large = judge.judge(
        template.format(width="10u"), "device", ["d", "g", "s", "b"], {"family": "device"}
    )
    assert small.accepted and large.accepted
    assert small.score > large.score


def test_profile_judge_rejects_disconnected_devices() -> None:
    netlist = """.subckt mirror iref out vss
X1 iref iref vss vss sg13_lv_nmos W=1u L=0.5u
X2 out gate floating floating sg13_lv_nmos W=1u L=0.5u
.ends mirror
"""
    result = ProfileJudge().judge(
        netlist, "mirror", ["iref", "out", "vss"], {"family": "mirror"}
    )
    assert result.accepted is False
    connected = next(item for item in result.measurements if item.name == "connected_network")
    assert connected.passed is False
