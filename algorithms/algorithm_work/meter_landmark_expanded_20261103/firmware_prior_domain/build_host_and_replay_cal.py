"""Relink selected fullC DLL; G raw -> calibration only, no network/C/H reads."""
from pathlib import Path
import ctypes as C,hashlib,json,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];SRC=HERE/'source'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def main():
    out=HERE/'host';out.mkdir(exist_ok=True);dll=out/'meter_landmark_reader.dll'
    names=['mroi_c4.c','mroi_decode.c','reader_numeric.c','reader_runtime.c','reader_sigmoid.c','meter_pose_frontend.c','meter_pose_matcher.c','landmark_geometry.c']
    cmd=['C:/Users/Edward/Desktop/mingw64/bin/gcc.exe','-std=c99','-O2','-shared','-Wl,--export-all-symbols','-DMROI_HOST_TEST','-Wall','-Wextra','-Werror','-ffp-contract=off','-fno-strict-aliasing','-o',str(dll),*[str(SRC/n)for n in names]]
    p=subprocess.run(cmd,capture_output=True);(out/'compile.stdout').write_bytes(p.stdout);(out/'compile.stderr').write_bytes(p.stderr);assert p.returncode==0,p.stderr.decode(errors='replace')
    lib=C.CDLL(str(dll));lib.mroi_reader_diagnostic_size.restype=C.c_uint32;assert lib.mroi_reader_diagnostic_size()==252
    lib.reader_calibrate_psi_q8_domain.argtypes=[C.c_int32,C.c_int32,C.c_int,C.POINTER(C.c_uint16)]
    lib.reader_calibrate_psi_q8.argtypes=[C.c_int32,C.c_int32,C.POINTER(C.c_uint16)]
    old_path=ROOT/'algorithm_work/meter_landmark_mcu_training_20261103/firmware/host/validation_replay.json';old={r['id']:r for r in load(old_path)['rows']}
    matrix_path=HERE.parent/'firmware/host_matrix/validation_matrix.json';matrix=load(matrix_path);checks=0;produced=[]
    def cal(raw,domain,ring=False,default=False):
        allowed=raw['neural_valid']and(raw['ring']['accepted']if ring else raw['selected_reference_kind'])
        q=C.c_uint16();angle=round(raw['angle_deg_image']*65536);roll=round((raw['ring']['roll']if ring else raw['selected_roll'])*65536)
        if default:valid=bool(allowed and lib.reader_calibrate_psi_q8(angle,roll,C.byref(q)))
        else:valid=bool(allowed and lib.reader_calibrate_psi_q8_domain(angle,roll,domain,C.byref(q)))
        return dict(valid=valid,psi=q.value/256 if valid else None)
    for n in matrix['rows']:
        o=old[n['id']];row=dict(id=n['id'])
        for raw,model in [(o,'old'),(n,'new')]:
            for domain,name in [(0,'old_domain'),(1,'corrected_domain')]:
                key=f'{model}_network_{name}';v=cal(raw,domain);want=n[key]
                assert (v['valid'],v['psi'])==(want['valid'],want['psi']),(n['id'],key)
                row[key]=v;checks+=1
        for domain,name in [(0,'old_domain'),(1,'corrected_domain')]:
            key=f'ring_only_{name}';v=cal(o,domain,True);assert(v['valid'],v['psi'])==(n[key]['valid'],n[key]['psi']);checks+=1
        assert cal(o,1,default=True)==row['old_network_corrected_domain'];checks+=1
        produced.append(row)
    # New selected source differs from expanded only in its parameter header.
    differences=[];exp=HERE.parent/'firmware/source'
    for p in SRC.iterdir():
        if p.is_file()and(exp/p.name).exists()and sha(p)!=sha(exp/p.name):differences.append(p.name)
    assert differences==['landmark_weights_q8.h'],differences
    report=dict(status='SELECTED_PRIOR_CORRECTED_FULL_HOST_DLL_LINKED_AND_SHARED_CAL_VERIFIED',selected_point_model='PRIOR_B857',ELF_sha256=sha(HERE/'build/meter_landmark_reader.elf'),DLL=dict(path=str(dll),sha256=sha(dll)),actual_diagnostic_ABI_bytes=252,G_calibration_scalar_checks=checks,old_fullC_source_sha256=sha(old_path),expanded_matrix_sha256=sha(matrix_path),all_four_arms_exactly_reproduced=True,production_default_corrected_confirmed=True,source_difference_from_expanded=differences,network_forward_invocations=0,G_images_read=False,C_H_images_or_labels_read=False,rows=produced)
    write(out/'calibration_replay_receipt.json',report);print(json.dumps({k:v for k,v in report.items()if k!='rows'},indent=2))
if __name__=='__main__':main()
