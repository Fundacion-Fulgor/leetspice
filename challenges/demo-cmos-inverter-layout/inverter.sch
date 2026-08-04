v {xschem version=3.4.6 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
N 40 0 40 20 {lab=out}
N 40 0 80 0 {lab=out}
N 40 -20 40 0 {lab=out}
N -40 0 0 0 {lab=in}
N 0 0 0 50 {lab=in}
N 40 -100 40 -80 {lab=vdd}
N 50 -100 50 -50 {lab=vdd}
N 50 50 50 100 {lab=vss}
N 40 80 40 100 {lab=vss}
N 40 -100 50 -100 {lab=vdd}
N 40 -50 50 -50 {lab=vdd}
N 0 -50 0 0 {lab=in}
N 40 50 50 50 {lab=vss}
N 40 100 50 100 {lab=vss}
N -70 -100 40 -100 {lab=vdd}
N -70 100 40 100 {lab=vss}
C {sg13g2_pr/sg13_lv_nmos.sym} 20 50 0 0 {name=MN0
l=130.00n
w=740.00n
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X
}
C {sg13g2_pr/sg13_lv_pmos.sym} 20 -50 0 0 {name=MP0
l=130.00n
w=1.12u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X
}
C {opin.sym} 80 0 0 0 {name=p1 lab=out}
C {ipin.sym} -40 0 0 0 {name=p2 lab=in}
C {iopin.sym} -70 -100 0 1 {name=p3 lab=vdd}
C {iopin.sym} -70 100 0 1 {name=p4 lab=vss}
