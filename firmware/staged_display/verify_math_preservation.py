"""Compare unchanged learned mathematics on six existing TRAIN-only ROI inputs.

This is equivalence coverage, not another accuracy selection or held-out score.
Feature3 transaction/cancellation behavior is independently tested with real
client/runtime and controlled stubs by the reviewer.
"""
from pathlib import Path
import ctypes as C, hashlib, json, subprocess
import numpy as np

HERE=Path(__file__).resolve().parent
AW=HERE.parents[2]
OLD=AW/'meter_landmark_expanded_20261103/firmware_prior_domain'
BASE=AW/'meter_landmark_stable3s_20261103/repair_20261104/firmware'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Point(C.Structure):
    _fields_=[('x',C.c_int32),('y',C.c_int32),('peak',C.c_uint16),('margin',C.c_uint16),('valid',C.c_uint8)]
class Needle(C.Structure):
    _fields_=[('angle',C.c_int32),('peak',C.c_uint16),('margin',C.c_uint16),('outside',C.c_uint16),('valid',C.c_uint8)]
class Ring(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['best_sum','far_sum','margin_num','margin_den']]+[(n,C.c_uint16) for n in ['best_keep','far_keep']]+[(n,C.c_int16) for n in ['delta','far_delta']]+[(n,C.c_uint8) for n in ['profile','template','accepted','score','margin','interior','reason']]
class Print(C.Structure):
    _fields_=[('roll',C.c_int32),('sse',C.c_uint32)]+[(n,C.c_uint8) for n in ['accepted','reason','mask','count']]
class Diagnostic(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['active','phase','words','completed','cancelled','epoch','source','job','radius','return_code','psi_word']]+[('hub',Point),('landmark',Point*6),('needle',Needle),('ring',Ring),('print',Print)]+[(n,C.c_uint32) for n in ['neural','reference','reference_kind','read']]+[('roll',C.c_int32),('cycles',C.c_uint32*5)]

def semantic(v):
    if isinstance(v,C.Structure):return {n:semantic(getattr(v,n)) for n,*_ in v._fields_}
    if isinstance(v,C.Array):return [semantic(x) for x in v]
    return int(v)

def main():
    out=HERE/'host';out.mkdir(exist_ok=True)
    names=['mroi_c4.c','mroi_decode.c','reader_numeric.c','reader_runtime.c','reader_sigmoid.c','meter_pose_frontend.c','meter_pose_matcher.c','landmark_geometry.c']
    dll=out/'meter_landmark_reader_staged.dll'
    argv=['C:/Users/Edward/Desktop/mingw64/bin/gcc.exe','-std=c99','-O2','-shared','-Wl,--export-all-symbols','-DMROI_HOST_TEST','-Wall','-Wextra','-Werror','-ffp-contract=off','-fno-strict-aliasing','-o',str(dll),*[str(HERE/'source'/n) for n in names]]
    p=subprocess.run(argv,capture_output=True)
    (out/'compile.stdout').write_bytes(p.stdout);(out/'compile.stderr').write_bytes(p.stderr)
    assert p.returncode==0,p.stderr.decode(errors='replace')
    olddll=OLD/'host/meter_landmark_reader.dll'
    assert sha(olddll)=='21f3f341116be6a5e214cbd5bc61d1529edb5c9c0cb6b9da4941c9bc6f391505'
    libs=[C.CDLL(str(x)) for x in [olddll,dll]]
    assert C.sizeof(Diagnostic)==252
    for lib in libs:
        lib.mroi_reader_diagnostic_size.restype=C.c_uint32
        assert lib.mroi_reader_diagnostic_size()==252
        lib.mroi_reader_host_infer.argtypes=[C.POINTER(C.c_uint8),C.c_uint,C.POINTER(Diagnostic)]
        lib.mroi_reader_host_infer.restype=C.c_int
    cache=AW/'meter_cnn_training_20261102/roi_cache_train.npz'
    z=np.load(cache);images=dict(zip(z['ids'].tolist(),z['images']))
    rows=[]
    for ident in ['D_002','D_013','D_025','E_002','F_002','F_025']:
        im=np.ascontiguousarray(images[ident],np.uint8);assert im.shape==(128,128)
        results=[]
        for lib in libs:
            d=Diagnostic();rc=lib.mroi_reader_host_infer(im.ctypes.data_as(C.POINTER(C.c_uint8)),48,C.byref(d))
            assert rc==1
            results.append(semantic(d))
        assert results[0]==results[1],ident
        rows.append({'id':ident,'input_sha256':hashlib.sha256(im.tobytes()).hexdigest(),'semantic_diagnostic_equal':True,'old':results[0],'staged':results[1]})
    weights={p.name:{'equal':p.read_bytes()==(BASE/'source'/p.name).read_bytes(),'sha256':sha(p)} for p in (HERE/'source').glob('*weights*')}
    objects={p.name:p.read_bytes()==(BASE/'build'/p.name).read_bytes() for p in (HERE/'build').glob('*.o')}
    assert all(x['equal'] for x in weights.values())
    assert [n for n,equal in objects.items() if not equal]==['reader_runtime.o']
    proof={'status':'STAGED_DISPLAY_TRAIN_ONLY_SAME_INPUT_MATH_AND_WEIGHTS_PRESERVATION_PASS','new_ELF_sha256':sha(HERE/'build/meter_landmark_reader.elf'),'old_host_DLL_sha256':sha(olddll),'staged_host_DLL_sha256':sha(dll),'semantic_fields_compared':True,'C_padding_not_compared':True,'TRAIN_only_forward_inputs':6,'C_G_H_images_read':False,'accuracy_reassessment':False,'new_weights_or_training':False,'weights':weights,'same_base_object_bytes':objects,'feature1_host_path':'Host image callback does not advertise stage feature; early submits disabled, final mathematics identical. Feature3 transactions are separate reviewer tests.','rows':rows,'device':False}
    (HERE/'math_preservation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in proof.items() if k not in ['rows','weights','same_base_object_bytes']},indent=2))

if __name__=='__main__':main()
