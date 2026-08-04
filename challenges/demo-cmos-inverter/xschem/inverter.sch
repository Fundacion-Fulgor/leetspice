v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/code_shown.sym} 0 0 0 0 {name=DUT only_toplevel=true value="
* Reference submission used to qualify the SG13G2 CACE challenge.
.subckt inverter in out vdd vss
XNMOS out in vss vss sg13_lv_nmos W=1u L=0.13u ng=1 m=1
XPMOS out in vdd vdd sg13_lv_pmos W=2u L=0.13u ng=1 m=1
.ends inverter
"}
