"""C U8-normalize + Q5-sampling + S8-profile + C matcher on fixed real ROIs.

Coordinate generation is explicitly still the frozen floating PC geometry.
This test proves C integer operators, not whole-MCU inference/deployment.
"""
import ctypes as C,json,time
import numpy as np
import pose_frontend as f
import verify_matcher as m


def u8(a):return a.ctypes.data_as(C.POINTER(C.c_uint8))
def s8(a):return a.ctypes.data_as(C.POINTER(C.c_int8))
def s16(a):return a.ctypes.data_as(C.POINTER(C.c_int16))


def main():
    lib=C.CDLL(str(m.HERE/'meter_pose_frontend.dll'))
    lib.mpf_normalize_workspace_size.restype=C.c_size_t
    lib.mpf_profile_workspace_size.restype=C.c_size_t
    nsize=lib.mpf_normalize_workspace_size();psize=lib.mpf_profile_workspace_size()
    assert nsize==1408 and psize==360
    lib.mpf_normalize9x9_u8.argtypes=[C.POINTER(C.c_uint8),C.POINTER(C.c_uint8),C.c_void_p]
    lib.mpf_profile_q5_s8.argtypes=[C.POINTER(C.c_uint8),C.POINTER(C.c_int16),C.POINTER(C.c_int16),C.POINTER(C.c_int8),C.c_void_p]
    match=m.dll();tt,keep=m.templates(match)
    workspace=C.create_string_buffer(nsize);sample_workspace=C.create_string_buffer(psize)
    manifest=m.load(m.HERE/'frontend_fixture_manifest.json')
    poses=[];counters=dict(ROIs=0,normalize_pixels=0,profile_elements=0,normalize_mismatches=0,profile_mismatches=0)
    start=time.perf_counter();kernel_time=0.
    for r in manifest['records']:
        if not r['actual_model_hub_available']:continue
        z=np.load(m.HERE/'frontend_fixtures'/(r['id']+'.npz'))
        gray=np.ascontiguousarray(z['image'],np.uint8);norm=np.empty_like(gray)
        t=time.perf_counter();assert lib.mpf_normalize9x9_u8(u8(gray),u8(norm),workspace)==0;kernel_time+=time.perf_counter()-t
        counters['normalize_mismatches']+=int((norm!=z['normalized_image']).sum());counters['normalize_pixels']+=norm.size
        ctx=m.Context();match.mp_prepare(C.byref(ctx),r['center_allowed'])
        for j,(dx,dy,scale) in enumerate(f.HYPOTHESES):
            xq,yq,oc,_,_=f.geometry_q5_from_float(z['hub']+[dx,dy],float(z['radius'])*scale)
            xq=np.ascontiguousarray(xq,np.int16);yq=np.ascontiguousarray(yq,np.int16);profile=np.empty((12,360),np.int8)
            t=time.perf_counter();assert lib.mpf_profile_q5_s8(u8(norm),s16(xq),s16(yq),s8(profile),sample_workspace)==0
            kernel_time+=time.perf_counter()-t
            counters['profile_mismatches']+=int((profile!=z['profiles'][j]).sum());counters['profile_elements']+=profile.size
            assert oc==int(z['outside_counts'][j])
            assert match.mp_push(C.byref(ctx),s8(profile),oc,j,tt,2)>=0
        result=m.Result();assert match.mp_finish(C.byref(ctx),C.byref(result))==0
        poses.append(m.make_pose(r,result,z));counters['ROIs']+=1
    assert counters['normalize_mismatches']==0 and counters['profile_mismatches']==0,counters
    report=m.numeric_result({r['id']:r for r in poses});report['status']='C_PIXEL_PROFILE_MATCHER_WITH_FLOAT_COORDINATES_PC_ONLY'
    baseline=m.load(m.OLD/'candidate_B_with_old_B_readout_psi.json');b={r['id']:r for r in baseline['rows']}
    changes=[r['id'] for r in report['rows'] if (r['valid'],r['psi_estimate'])!=(b[r['id']]['valid'],b[r['id']]['psi_estimate'])]
    assert not changes,changes
    m.write(m.HERE/'c_pixel_chain_readout_psi.json',report)
    receipt=dict(status='PASS_C_PIXEL_PROFILE_MATCHER_FROZEN_PSI_OUTPUTS',counts=counters,PSI=report['summary'],
        pressure_output_changes=changes,normalize_workspace_bytes=nsize,profile_workspace_bytes=psize,
        source_frontend_C_sha256=f.sha(m.HERE/'meter_pose_frontend.c'),source_matcher_C_sha256=f.sha(m.HERE/'meter_pose_matcher.c'),
        frontend_dll_sha256=f.sha(m.HERE/'meter_pose_frontend.dll'),matcher_dll_sha256=f.sha(m.HERE/'meter_pose_matcher.dll'),
        geometry_q5_uses_float=True,pressure_geometry_and_neural_models_not_ported_in_this_test=True,
        actual_MCU_memory_behavior_measured=False,MCU_linked=False,MCU_cycles_measured=False,
        host_C_frontend_seconds=kernel_time,total_host_seconds=time.perf_counter()-start,
        H_opened=False,hardware_actions=False)
    m.write(m.HERE/'c_pixel_chain_verification.json',receipt)
    print(receipt['status'],counters,'readings',report['summary']['valid_readings'],'MAE',report['summary']['reading_mae_psi'])


if __name__=='__main__':main()
