v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/code_shown.sym} 0 0 0 0 {name=TESTBENCH only_toplevel=false value="
.lib CACE\{PDK_ROOT\}/CACE\{PDK\}/libs.tech/ngspice/models/cornerMOSlv.lib mos_CACE\{corner\}
.include CACE\{root\}/submission.spice
.temp CACE\{temperature\}

VDD vdd 0 CACE\{vdd\}
VIN in 0 PULSE(CACE\{vdd\} 0 2n 20p 20p 4n 8n)
CLOAD out 0 CACE\{load\}
XDUT in out vdd 0 inverter

.control
tran 1p 12n
meas tran tplh TRIG v(in) VAL=0.6 FALL=1 TARG v(out) VAL=0.6 RISE=1
meas tran tphl TRIG v(in) VAL=0.6 RISE=1 TARG v(out) VAL=0.6 FALL=1
meas tran rise_time TRIG v(out) VAL=0.12 RISE=1 TARG v(out) VAL=1.08 RISE=1
meas tran fall_time TRIG v(out) VAL=1.08 FALL=1 TARG v(out) VAL=0.12 FALL=1
meas tran average_current AVG i(VDD) FROM=2n TO=10n
meas tran logic_high FIND v(out) AT=5n
meas tran logic_low FIND v(out) AT=9n
echo $&tphl $&tplh $&rise_time $&fall_time $&average_current $&logic_low $&logic_high > timing_CACE\{N\}.data
.endc
"}
