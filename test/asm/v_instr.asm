# INTEGER
# 0b00xxxx
vadd.vv v1, v2, v3
vadd.vv v1, v2, v3, v0.t
vadd.vi v0, v4, 11
vadd.vx v31, v8, x7
vadd.vx v31, v8, x7, v0.t
vsub.vv v4, v8, v3
vsub.vx v2, v3, x1
vrsub.vx v1, v2, x3
vrsub.vi v1, v2, 7
vminu.vv v1, v2, v3
vminu.vx v1, v2, x3
vmin.vv v1, v2, v3
vmin.vx v1, v2, x3
vmaxu.vv v1, v2, v3
vmaxu.vx v1, v2, x3
vmax.vv v1, v2, v3
vmax.vx v1, v2, x3
vand.vv v1, v2, v3
vand.vx v1, v2, x3
vand.vi v1, v2, 15
vor.vv v1, v2, v3
vor.vx v1, v2, x3
vor.vi v1, v2, -16
vxor.vv v1, v2, v3
vxor.vx v1, v2, x3
vxor.vi v1, v2, 0
vrgather.vv v1, v2, v3
vrgather.vx v1, v2, x3
vrgather.vi v1, v2, 4
vslideup.vx v1, v2, x3
vslideup.vi v1, v2, 2
vrgatherei16.vv v1, v2, v3
vslidedown.vx v1, v2, x3
vslidedown.vi v1, v2, 2

# 0b01xxxx
vadc.vvm v1, v2, v3, v0
vadc.vxm v1, v2, x3, v0
vadc.vim v1, v2, 3, v0
vmadc.vvm v1, v2, v3, v0
vmadc.vxm v1, v2, x3, v0
vmadc.vim v1, v2, 3, v0
vsbc.vvm v1, v2, v3, v0
vsbc.vxm v1, v2, x3, v0
vmsbc.vvm v1, v2, v3, v0
vmsbc.vxm v1, v2, x3, v0
vmerge.vvm v1, v2, v3, v0
vmerge.vxm v1, v2, x3, v0
vmerge.vim v1, v2, 3, v0
vmv.v.v v1, v3
vmv.v.x v1, x3
vmv.v.i v1, 3
vmseq.vv v1, v2, v3
vmseq.vx v1, v2, x3
vmseq.vi v1, v2, 3
vmsne.vv v1, v2, v3
vmsne.vx v1, v2, x3
vmsne.vi v1, v2, 3
vmsltu.vv v1, v2, v3
vmsltu.vx v1, v2, x3
vmslt.vv v1, v2, v3
vmslt.vx v1, v2, x3
vmsleu.vv v1, v2, v3
vmsleu.vx v1, v2, x3
vmsleu.vi v1, v2, 3
vmsle.vv v1, v2, v3
vmsle.vx v1, v2, x3
vmsle.vi v1, v2, 3
vmsgtu.vx v1, v2, x3
vmsgtu.vi v1, v2, 3
vmsgt.vx v1, v2, x3
vmsgt.vi v1, v2, 3

# 0b10xxxx
vsaddu.vv v1, v2, v3
vsaddu.vx v1, v2, x3
vsaddu.vi v1, v2, 3
vsadd.vv v1, v2, v3
vsadd.vx v1, v2, x3
vsadd.vi v1, v2, 3
vssubu.vv v1, v2, v3
vssubu.vx v1, v2, x3
vssub.vv v1, v2, v3
vssub.vx v1, v2, x3
vsll.vv v1, v2, v3
vsll.vx v1, v2, x3
vsll.vi v1, v2, 3
vsmul.vv v1, v2, v3
vsmul.vx v1, v2, x3
vmv1r.v v0, v8
vmv2r.v v0, v8
vmv4r.v v0, v8
vmv8r.v v0, v8
vsrl.vv v1, v2, v3
vsrl.vx v1, v2, x3
vsrl.vi v1, v2, 3
vsra.vv v1, v2, v3
vsra.vx v1, v2, x3
vsra.vi v1, v2, 3
vnsrl.wv v1, v2, v3
vnsrl.wx v1, v2, x3
vnsrl.wi v1, v2, 3
vnsra.wv v1, v2, v3
vnsra.wx v1, v2, x3
vnsra.wi v1, v2, 3
vnclipu.wv v1, v2, v3
vnclipu.wx v1, v2, x3
vnclipu.wi v1, v2, 3
vnclip.wv v1, v2, v3
vnclip.wx v1, v2, x3
vnclip.wi v1, v2, 3

#0b11xxxx
vwredsumu.vs v1, v2, v3
vwredsum.vs v1, v2, v3

# CONTROL
vsetvl x0, x1, x2
vsetvli x0, x0, e32,m8,ta,ma
vsetivli x1, 8, e32,m8,ta,ma
