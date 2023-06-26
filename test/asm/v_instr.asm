# Page 1
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

# Page 2
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
